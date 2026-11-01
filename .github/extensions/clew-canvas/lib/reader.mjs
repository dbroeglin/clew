/** One live publication: compile, watch, record activity and answer the front-end and the agent. */
import { existsSync, mkdirSync, readFileSync, watch } from "node:fs";
import { basename, dirname, extname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { ActivityStore } from "./activity.mjs";
import { compileData } from "./compile.mjs";
import { htmlToText, indexData } from "./data.mjs";
import { askPrompt, digestText } from "./digest.mjs";
import { minutes, replay, studentEvent, withContext } from "./events.mjs";
import { isInside, toPosix, vaultPath } from "./paths.mjs";
import { renderSummary } from "./summary.mjs";

const SOURCE_FILE = /\.(md|png|jpe?g|gif|webp)$/i;
export const ASK_INTERVAL_MS = 5000;

export class RequestError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
    }
}

const decodeEntities = (text) => text.replace(/&amp;/g, "&").replace(/&quot;/g, "\"").replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">");

/** External link targets present in the compiled HTML: the only ones the front-end may open. */
export function publishedLinks(data) {
    const links = new Set();
    const visit = (value) => {
        if (typeof value === "string") {
            for (const match of value.matchAll(/<a\b[^>]*\bhref="([^"#][^"]*)"/g)) links.add(decodeEntities(match[1]));
        } else if (Array.isArray(value)) value.forEach(visit);
        else if (value && typeof value === "object") Object.values(value).forEach(visit);
    };
    visit([data.exercises, data.worksheet, data.questions, data.courses]);
    return links;
}

/** Topmost directories among `dirs`, so recursive watchers never overlap. */
export function topmost(dirs) {
    const sorted = [...new Set(dirs.map((dir) => resolve(dir)))].sort((a, b) => a.length - b.length);
    const kept = [];
    for (const dir of sorted) if (!kept.some((root) => isInside(root, dir))) kept.push(dir);
    return kept;
}

export class Reader {
    constructor({ rid, layout, vault, repoRoot, session, cacheDir, compile = compileData, now = () => new Date(),
                  debounceMs = 1500, watchFiles = true, log = () => {} }) {
        Object.assign(this, { rid, layout, vault, repoRoot, session, cacheDir, compile, now, debounceMs, watchFiles, log });
        this.layoutRel = vaultPath(vault, layout);
        this.status = "idle";
        this.error = null;
        this.version = 0;
        this.data = null;
        this.dataText = null;
        this.index = null;
        this.links = new Set();
        this.store = null;
        this.header = null;
        this.events = [];
        this.state = {};
        this.pending = [];
        this.instances = new Set();
        this.clients = new Set();
        this.watchers = [];
        this.compiling = null;
        this.dirty = false;
        this.timer = null;
        this.lastAsk = new Map();
    }

    get title() {
        return this.data?.title ?? basename(this.layout, extname(this.layout));
    }

    start() {
        if (this.status === "idle") this.compileNow();
        return this.compiling ?? Promise.resolve();
    }

    /** Like start, but also retries after a failed compilation. */
    retry() {
        if (this.status === "error" || this.status === "stale") this.compileNow();
        return this.start();
    }

    compileNow() {
        if (this.compiling) {
            this.dirty = true;
            return this.compiling;
        }
        this.status = this.data ? "updating" : "compiling";
        this.broadcastStatus();
        const target = join(this.cacheDir, `${this.rid}.json`);
        this.compiling = (async () => {
            mkdirSync(this.cacheDir, { recursive: true });
            const result = await this.compile({ repoRoot: this.repoRoot, layout: this.layout, target, base: this.vault });
            if (!result.ok) throw new Error(result.error);
            const text = readFileSync(target, "utf8");
            this.applyData(JSON.parse(text), text);
        })().then(() => {
            this.status = "ready";
            this.error = null;
        }, (error) => {
            this.status = this.data ? "stale" : "error";
            this.error = error.message;
            this.log(`Clew canvas compile failed: ${error.message}`, "warning");
        }).finally(() => {
            this.compiling = null;
            this.broadcastStatus();
            if (this.dirty) {
                this.dirty = false;
                this.schedule();
            }
        });
        return this.compiling;
    }

    schedule() {
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.compileNow(), this.debounceMs);
        this.timer.unref?.();
    }

    knownNotes() {
        const notes = new Map((this.header?.notes ?? []).map((note) => [note.id, note]));
        for (const event of this.events) {
            if (event.type !== "content_changed") continue;
            for (const note of event.notes ?? []) notes.set(note.id, note);
            for (const id of event.removed ?? []) notes.delete(id);
        }
        return notes;
    }

    applyData(data, text = JSON.stringify(data)) {
        const index = indexData(data);
        if (!this.store) {
            const store = new ActivityStore({ vault: this.vault, layout: this.layout, session: this.session, now: this.now });
            const { header, events } = store.open(data);
            Object.assign(this, { store, header, events, state: store.readState() });
        }
        Object.assign(this, { data, dataText: text, index, links: publishedLinks(data) });
        this.version += 1;
        for (const event of this.pending.splice(0)) this.record(event);
        const known = this.knownNotes();
        const current = (data.sources ?? []).map(({ id, path, sha256 }) => ({ id, path, sha256 }));
        const notes = current.filter((note) => {
            const previous = known.get(note.id);
            return !previous || previous.sha256 !== note.sha256 || previous.path !== note.path;
        });
        const ids = new Set(current.map((note) => note.id));
        const removed = [...known.keys()].filter((id) => !ids.has(id));
        const layout = this.store.snapshotLayout(readFileSync(this.layout, "utf8"));
        if (notes.length || removed.length || layout) {
            this.record({ v: 1, ts: this.now().toISOString(), type: "content_changed", actor: "system", notes, removed, layout });
        } else {
            this.writeSummary();
        }
        if (this.watchFiles) this.watchSources();
    }

    writeSummary() {
        if (!this.store || !this.index) return;
        try {
            this.store.writeSummary(renderSummary({ header: this.header, events: this.events, index: this.index }));
        } catch (error) {
            this.log(`Clew canvas could not write summary.md: ${error.message}`, "warning");
        }
    }

    record(event) {
        if (!this.store) {
            this.pending.push(event);
            return event;
        }
        this.events.push(event);
        this.store.append(event);
        this.writeSummary();
        return event;
    }

    lifecycle(type, instance) {
        return this.record({ v: 1, ts: this.now().toISOString(), type, actor: "system", instance });
    }

    open(instance) {
        this.instances.add(instance);
        this.lifecycle("canvas_opened", instance);
        this.retry();
    }

    rehydrate(instance) {
        if (this.instances.has(instance)) return;
        this.instances.add(instance);
        this.lifecycle("canvas_rehydrated", instance);
    }

    close(instance) {
        this.lifecycle("canvas_closed", instance);
        this.instances.delete(instance);
        if (!this.instances.size) this.stopWatching();
    }

    requireData() {
        if (!this.index) throw new RequestError(503, this.error ?? "La publication est en cours de compilation.");
        return this.index;
    }

    recordStudent(input) {
        const index = this.requireData();
        const event = studentEvent(input, index, this.now());
        const progress = replay(this.events);
        if (event.type === "exercise_started" && progress.exercises.get(event.exercise)?.started) return null;
        if (event.type === "hint_revealed" && (progress.questions.get(event.question)?.hints ?? 0) >= event.index) return null;
        return this.record(event);
    }

    /** Classify a published external link; PDFs inside the vault get a vault-relative path. */
    resolveLink(href) {
        this.requireData();
        if (typeof href !== "string" || !this.links.has(href)) throw new RequestError(400, "Lien absent de la publication.");
        if (/^(https?|mailto):/i.test(href)) return { type: "link_opened", url: href };
        const at = href.indexOf("#");
        const path = at < 0 ? href : href.slice(0, at);
        const page = Number(/(?:^|&)page=(\d+)/.exec(at < 0 ? "" : href.slice(at + 1))?.[1]) || undefined;
        const file = path.startsWith("file:") ? fileURLToPath(path) : resolve(this.vault, decodeURIComponent(path));
        if (!/\.pdf$/i.test(file)) throw new RequestError(400, "Seuls les PDF locaux peuvent être ouverts.");
        if (!existsSync(file)) throw new RequestError(404, `PDF introuvable : ${basename(file)}`);
        const inside = isInside(this.vault, file);
        return { type: "pdf_opened", url: inside ? vaultPath(this.vault, file) : pathToFileURL(file).href, page, file, inside };
    }

    /** Absolute path of a published PDF served from the vault, or null. */
    pdfFile(rel) {
        if (!this.index) return null;
        for (const href of this.links) {
            if (/^(https?|mailto|file):/i.test(href)) continue;
            const path = href.split("#")[0];
            if (toPosix(decodeURIComponent(path)) === rel && /\.pdf$/i.test(path)) {
                const file = resolve(this.vault, rel);
                return isInside(this.vault, file) && existsSync(file) ? file : null;
            }
        }
        return null;
    }

    recordLink(link, question) {
        const event = { v: 1, ts: this.now().toISOString(), type: link.type, actor: "student", url: link.url };
        if (link.page) event.page = link.page;
        return this.record(withContext(event, { question }, this.index, { strict: false }));
    }

    /** Record a tutor request and build the hidden prompt, or null when rate limited. */
    ask(address, instance) {
        const index = this.requireData();
        const question = index.questions.get(address);
        if (!question) throw new RequestError(400, "Question inconnue.");
        const time = this.now().getTime();
        if (time - (this.lastAsk.get(address) ?? -Infinity) < ASK_INTERVAL_MS) return null;
        this.lastAsk.set(address, time);
        const unseen = this.events.slice(this.cursor());
        this.record(withContext({ v: 1, ts: this.now().toISOString(), type: "tutor_requested", actor: "student" },
            { question: address }, index));
        const state = replay(this.events).questions.get(address);
        const recent = digestText({ title: this.title, instances: [...this.instances], events: unseen, index });
        this.advanceCursor();
        return askPrompt({ title: this.title, instance, question, exercise: index.exerciseOf.get(address), state, recent });
    }

    cursor() {
        return Math.min(Number.isInteger(this.state.digest) ? this.state.digest : 0, this.events.length);
    }

    advanceCursor() {
        if (!this.store || this.state.digest === this.events.length) return;
        this.state = { ...this.state, digest: this.events.length };
        try {
            this.store.writeState(this.state);
        } catch (error) {
            this.log(`Clew canvas could not write state.json: ${error.message}`, "warning");
        }
    }

    /** Digest of events the agent has not seen, advancing the cursor. */
    takeDigest() {
        if (!this.store || !this.index) return null;
        const text = digestText({ title: this.title, instances: [...this.instances], events: this.events.slice(this.cursor()),
            index: this.index });
        this.advanceCursor();
        return text;
    }

    agentState({ question, courses } = {}) {
        const base = { status: this.status, error: this.error ?? undefined, title: this.title, layout: this.layoutRel,
            activity: this.store ? vaultPath(this.vault, this.store.folder) : undefined, instances: [...this.instances] };
        if (!this.index) return base;
        const index = this.index;
        const progress = replay(this.events);
        const questionState = (q) => {
            const s = progress.questions.get(q.address);
            if (!s) return null;
            return { address: q.address, label: q.label, hints: `${s.hints}/${q.hints.length}`, correction_viewed: s.correctionSeen,
                method_views: s.method, explanation_views: s.explanations, tutor_requests: s.tutor, time: minutes(s.ms) };
        };
        const exercises = this.data.exercises.map((exercise) => {
            const items = exercise.questions.map((id) => index.questionsById.get(id)).filter(Boolean);
            const touched = items.map(questionState).filter(Boolean);
            const state = progress.exercises.get(exercise.address);
            const entry = { address: exercise.address, title: exercise.title, questions: items.length };
            if (!state && !touched.length) return entry;
            const ms = (state?.ms ?? 0) + items.reduce((sum, q) => sum + (progress.questions.get(q.address)?.ms ?? 0), 0);
            return { ...entry, started: Boolean(state?.started), time: minutes(ms), progress: touched };
        });
        const result = { ...base, focus: progress.focus ?? undefined, exercises,
            courses_opened: [...progress.courses].map(([address, count]) => ({ address, title: index.courses.get(address)?.title, count })) };
        if (courses) {
            result.courses = [...index.courses.values()].map((course) => ({ address: course.address, title: course.title }));
        }
        if (question) {
            const q = index.questions.get(question);
            if (!q) throw new RequestError(400, `Unknown question address: ${question}. Use addresses from get_state.`);
            const exercise = index.exerciseOf.get(question);
            const s = progress.questions.get(question);
            result.question = {
                address: q.address, label: q.label, exercise: exercise && { address: exercise.address, title: exercise.title },
                statement: htmlToText(q.html, 3000),
                hints: { revealed: s?.hints ?? 0, total: q.hints.length }, method_available: Boolean(q.method),
                correction: { available: q.corrections.length > 0, viewed: Boolean(s?.correctionSeen) },
                explanations_available: q.explanations.length > 0,
                courses: q.courses.map((id) => index.coursesById.get(id)).filter(Boolean)
                    .map((course) => ({ address: course.address, title: course.title })),
                progress: questionState(q) ?? undefined,
            };
        }
        return result;
    }

    resolveTarget(address) {
        const index = this.requireData();
        if (index.questions.has(address)) return "question";
        if (index.exercises.has(address)) return "exercise";
        if (index.courses.has(address)) return "course";
        throw new RequestError(400, `Unknown target address: ${address}. Use a question, exercise or course address from get_state.`);
    }

    show(address, instance) {
        const kind = this.resolveTarget(address);
        this.record(withContext({ v: 1, ts: this.now().toISOString(), type: "tutor_show", actor: "tutor" },
            { [kind]: address }, this.index));
        const delivered = this.broadcast({ type: "show", kind, address }, instance);
        return { shown: kind, address, delivered: delivered > 0 };
    }

    frontState() {
        const progress = replay(this.events);
        const hints = {};
        for (const [address, state] of progress.questions) if (state.hints) hints[address] = state.hints;
        const started = [...progress.exercises].filter(([, state]) => state.started).map(([address]) => address);
        return { status: this.status, error: this.error, version: this.version, title: this.title, hints, started };
    }

    addClient(res, instance) {
        const client = { res, instance };
        this.clients.add(client);
        return () => this.clients.delete(client);
    }

    broadcast(message, instance) {
        let count = 0;
        const line = `data: ${JSON.stringify(message)}\n\n`;
        for (const client of this.clients) {
            if (instance && client.instance !== instance) continue;
            client.res.write(line);
            count += 1;
        }
        return count;
    }

    broadcastStatus() {
        this.broadcast({ type: "status", status: this.status, error: this.error, version: this.version });
    }

    watchSources() {
        this.stopWatching();
        const dirs = (this.data.sources ?? []).map((source) => dirname(resolve(this.vault, source.path)));
        try {
            const layout = JSON.parse(readFileSync(this.layout, "utf8"));
            for (const entry of Array.isArray(layout.notes) ? layout.notes : []) {
                const path = resolve(dirname(this.layout), String(entry));
                if (existsSync(path)) dirs.push(extname(path) ? dirname(path) : path);
            }
        } catch {
            // The compiled sources already cover the layout's notes.
        }
        const activity = join(this.vault, "Activity");
        const roots = topmost(dirs.filter((dir) => isInside(this.vault, dir) && !isInside(activity, dir)));
        for (const root of roots) {
            this.addWatcher(root, true, (file) => {
                const parts = file.split(/[\\/]/);
                return SOURCE_FILE.test(file) && !parts.some((part) => part.startsWith("."))
                    && !isInside(activity, resolve(root, file));
            });
        }
        const name = basename(this.layout);
        this.addWatcher(dirname(this.layout), false, (file) => file === name);
    }

    addWatcher(dir, recursive, accept) {
        try {
            const watcher = watch(dir, { recursive }, (type, file) => {
                if (file && accept(String(file))) this.schedule();
            });
            watcher.on("error", (error) => this.log(`Clew canvas watcher stopped: ${error.message}`, "warning"));
            this.watchers.push(watcher);
        } catch (error) {
            this.log(`Clew canvas cannot watch ${dir}: ${error.message}`, "warning");
        }
    }

    stopWatching() {
        for (const watcher of this.watchers.splice(0)) watcher.close();
        clearTimeout(this.timer);
    }

    dispose() {
        this.stopWatching();
        for (const client of this.clients) client.res.end();
        this.clients.clear();
    }
}
