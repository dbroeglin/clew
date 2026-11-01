/** Loopback HTTP server, canvas lifecycle, agent actions and session hooks for the Clew canvas. */
import { execFile } from "node:child_process";
import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import { createReadStream, existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import { createServer } from "node:http";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { compileData } from "./compile.mjs";
import { isTutorAgent, vaultWriteDenial } from "./guard.mjs";
import { findVault, writeAtomic } from "./paths.mjs";
import { Reader, RequestError } from "./reader.mjs";

export const DISPLAY_PROMPT = "I need help with this question";
const WEB = fileURLToPath(new URL("../web/", import.meta.url));
const MAX_BODY = 1 << 20;

export function openExternal(target) {
    const [command, args] = process.platform === "win32" ? ["rundll32.exe", ["url.dll,FileProtocolHandler", target]]
        : process.platform === "darwin" ? ["open", [target]] : ["xdg-open", [target]];
    return new Promise((done, fail) => {
        execFile(command, args, { windowsHide: true }, (error) => (error ? fail(error) : done()));
    });
}

export function readerId(layout) {
    const key = process.platform === "win32" ? layout.toLowerCase() : layout;
    return createHash("sha256").update(key).digest("hex").slice(0, 12);
}

export function sessionPort(sessionId) {
    return 41000 + (parseInt(createHash("sha256").update(String(sessionId)).digest("hex").slice(0, 8), 16) % 8000);
}

const sameToken = (a, b) => typeof a === "string" && a.length === b.length && timingSafeEqual(Buffer.from(a), Buffer.from(b));
const wait = (ms) => new Promise((done) => setTimeout(done, ms).unref?.());

function send(res, status, body, type = "application/json; charset=utf-8") {
    res.writeHead(status, { "Content-Type": type, "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
    res.end(typeof body === "string" || Buffer.isBuffer(body) ? body : JSON.stringify(body));
}

function readBody(req) {
    return new Promise((done, fail) => {
        let size = 0;
        const chunks = [];
        req.on("data", (chunk) => {
            size += chunk.length;
            if (size > MAX_BODY) {
                fail(new RequestError(413, "Requête trop volumineuse."));
                req.destroy();
            } else chunks.push(chunk);
        });
        req.on("end", () => {
            try {
                done(JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}"));
            } catch {
                fail(new RequestError(400, "JSON invalide."));
            }
        });
        req.on("error", fail);
    });
}

export class CanvasApp {
    constructor({ repoRoot, sessionId, stateDir, compile = compileData, opener = openExternal, log = () => {},
                  watchFiles = true, now = () => new Date(), debounceMs = 1500 }) {
        Object.assign(this, { repoRoot, sessionId, stateDir, compile, opener, log, watchFiles, now, debounceMs });
        this.readers = new Map();
        this.session = null;
        this.tutorActive = false;
        this.registryPath = join(stateDir, "registry.json");
        this.static = new Map([
            ["/web/app.js", [join(WEB, "app.js"), "text/javascript; charset=utf-8"]],
            ["/web/boot.js", [join(WEB, "boot.js"), "text/javascript; charset=utf-8"]],
            ["/web/canvas.css", [join(WEB, "canvas.css"), "text/css; charset=utf-8"]],
            ["/assets/style.css", [join(repoRoot, ".agents", "skills", "clew-generate", "assets", "style.css"), "text/css; charset=utf-8"]],
            ["/assets/mathjax/tex-svg.js",
                [join(repoRoot, ".agents", "skills", "clew-generate", "assets", "mathjax", "tex-svg.js"), "text/javascript; charset=utf-8"]],
        ]);
    }

    async start() {
        mkdirSync(this.stateDir, { recursive: true });
        try {
            this.registry = JSON.parse(readFileSync(this.registryPath, "utf8"));
        } catch {
            this.registry = {};
        }
        this.registry.readers ??= {};
        this.registry.instances ??= {};
        this.token = typeof this.registry.token === "string" && this.registry.token.length === 48
            ? this.registry.token : randomBytes(24).toString("hex");
        this.server = createServer((req, res) => {
            this.handle(req, res).catch((error) => {
                const status = error instanceof RequestError ? error.status : 500;
                if (status === 500) this.log(`Clew canvas request failed: ${error.stack ?? error}`, "error");
                if (!res.headersSent) send(res, status, { error: error.message });
                else res.end();
            });
        });
        const preferred = Number.isInteger(this.registry.port) ? this.registry.port : sessionPort(this.sessionId);
        try {
            await this.listen(preferred);
        } catch {
            await this.listen(0);
        }
        this.port = this.server.address().port;
        this.registry.token = this.token;
        this.registry.port = this.port;
        this.saveRegistry();
        return this;
    }

    listen(port) {
        return new Promise((done, fail) => {
            const onError = (error) => fail(error);
            this.server.once("error", onError);
            this.server.listen(port, "127.0.0.1", () => {
                this.server.off("error", onError);
                done();
            });
        });
    }

    async stop() {
        for (const reader of this.readers.values()) reader.dispose();
        await new Promise((done) => (this.server ? this.server.close(() => done()) : done()));
    }

    saveRegistry() {
        try {
            writeAtomic(this.registryPath, `${JSON.stringify(this.registry, null, 2)}\n`);
        } catch (error) {
            this.log(`Clew canvas could not save its registry: ${error.message}`, "warning");
        }
    }

    attach(session) {
        this.session = session;
        session.on?.((event) => {
            if (event.type === "subagent.selected") {
                this.tutorActive = isTutorAgent(event.data?.agentName) || isTutorAgent(event.data?.agentDisplayName);
            } else if (event.type === "subagent.deselected") {
                this.tutorActive = false;
            }
        });
        Promise.resolve(session.rpc?.agent?.getCurrent?.()).then((result) => {
            if (result?.agent) this.tutorActive = isTutorAgent(result.agent.name) || isTutorAgent(result.agent.displayName);
        }).catch(() => {});
    }

    reader(rid) {
        if (this.readers.has(rid)) return this.readers.get(rid);
        const layout = this.registry.readers[rid];
        if (!layout || !existsSync(layout)) return null;
        const vault = findVault(layout);
        if (!vault) return null;
        const reader = new Reader({ rid, layout, vault, repoRoot: this.repoRoot, session: this.sessionId,
            cacheDir: join(this.stateDir, "cache"), compile: this.compile, now: this.now, debounceMs: this.debounceMs,
            watchFiles: this.watchFiles, log: this.log });
        try {
            reader.layoutTitle = JSON.parse(readFileSync(layout, "utf8")).title;
        } catch {
            // The compiler reports invalid layouts.
        }
        this.readers.set(rid, reader);
        return reader;
    }

    url(reader, instance) {
        return `http://127.0.0.1:${this.port}/r/${reader.rid}/?t=${this.token}&i=${encodeURIComponent(instance)}`;
    }

    instanceReader(instance) {
        const reader = this.reader(this.registry.instances[instance]);
        if (!reader) throw new Error(`Canvas instance "${instance}" is not open. Open the clew-canvas first.`);
        return reader;
    }

    open(ctx) {
        const raw = ctx?.input?.layout;
        if (typeof raw !== "string" || !raw.trim()) throw new Error("input.layout must be the path of a publication layout JSON file.");
        const layout = resolve(ctx.session?.workingDirectory ?? process.cwd(), raw);
        if (!/\.json$/i.test(layout) || !existsSync(layout) || !statSync(layout).isFile()) {
            throw new Error(`Layout not found: ${layout}`);
        }
        const vault = findVault(layout);
        if (!vault) throw new Error(`The layout must be inside an Obsidian vault (a folder containing .obsidian/): ${layout}`);
        const rid = readerId(layout);
        this.registry.readers[rid] = layout;
        const previous = this.registry.instances[ctx.instanceId];
        if (previous && previous !== rid) this.reader(previous)?.close(ctx.instanceId);
        this.registry.instances[ctx.instanceId] = rid;
        this.saveRegistry();
        const reader = this.reader(rid);
        if (!reader.instances.has(ctx.instanceId)) reader.open(ctx.instanceId);
        else reader.retry();
        return { title: `Clew · ${reader.data?.title ?? reader.layoutTitle ?? "publication"}`, url: this.url(reader, ctx.instanceId),
            status: reader.data ? "Prêt" : "Compilation…" };
    }

    close(ctx) {
        const rid = this.registry.instances[ctx.instanceId];
        this.reader(rid)?.close(ctx.instanceId);
        delete this.registry.instances[ctx.instanceId];
        this.saveRegistry();
    }

    async ready(reader, ms = 60_000) {
        await Promise.race([reader.start(), wait(ms)]);
    }

    async getState(ctx) {
        const reader = this.instanceReader(ctx.instanceId);
        await this.ready(reader);
        const input = ctx.input ?? {};
        return reader.agentState({ question: input.question, courses: Boolean(input.courses) });
    }

    async show(ctx) {
        const reader = this.instanceReader(ctx.instanceId);
        await this.ready(reader);
        if (!reader.index) throw new Error(reader.error ?? "The publication is still compiling.");
        return reader.show(ctx.input?.target, ctx.instanceId);
    }

    onUserPromptSubmitted() {
        const texts = [];
        for (const reader of this.readers.values()) {
            const text = reader.takeDigest();
            if (text) texts.push(text);
        }
        return texts.length ? { additionalContext: texts.join("\n\n") } : undefined;
    }

    onPreToolUse(input) {
        if (!this.tutorActive && !isTutorAgent(input?.agentType)) return undefined;
        const reason = vaultWriteDenial({ toolName: input.toolName, toolArgs: input.toolArgs,
            cwd: input.workingDirectory ?? process.cwd() });
        return reason ? { permissionDecision: "deny", permissionDecisionReason: reason } : undefined;
    }

    async handle(req, res) {
        const allowed = [`127.0.0.1:${this.port}`, `localhost:${this.port}`];
        if (!allowed.includes(req.headers.host)) return send(res, 403, { error: "Hôte refusé." });
        if (req.method === "POST" && req.headers.origin && !allowed.map((h) => `http://${h}`).includes(req.headers.origin)) {
            return send(res, 403, { error: "Origine refusée." });
        }
        const url = new URL(req.url, `http://127.0.0.1:${this.port}`);
        const asset = this.static.get(url.pathname);
        if (asset && req.method === "GET") {
            res.writeHead(200, { "Content-Type": asset[1], "Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff" });
            return void createReadStream(asset[0]).on("error", () => res.end()).pipe(res);
        }
        const match = /^\/r\/([0-9a-f]{12})\/(.*)$/.exec(url.pathname);
        if (!match) return send(res, 404, { error: "Introuvable." });
        if (!sameToken(url.searchParams.get("t") ?? req.headers["x-clew-token"], this.token)) {
            return send(res, 403, { error: "Jeton invalide." });
        }
        const reader = this.reader(match[1]);
        if (!reader) return send(res, 404, { error: "Publication inconnue. Rouvrez le canevas." });
        const route = `${req.method} ${match[2].startsWith("vault/") ? "vault/" : match[2]}`;
        switch (route) {
            case "GET ": return this.page(res);
            case "GET api/data":
                reader.start();
                if (!reader.dataText) return send(res, 503, reader.frontState());
                res.setHeader("X-Clew-Version", String(reader.version));
                return send(res, 200, reader.dataText);
            case "GET api/state": return send(res, 200, reader.frontState());
            case "GET api/stream": return this.stream(req, res, reader, url.searchParams.get("i") ?? "");
            case "POST api/event": return this.events(req, res, reader);
            case "POST api/open": return this.openLink(req, res, reader);
            case "POST api/ask": return this.ask(req, res, reader);
            case "GET vault/": {
                const file = reader.pdfFile(decodeURIComponent(match[2].slice("vault/".length)));
                if (!file) return send(res, 404, { error: "PDF introuvable." });
                res.writeHead(200, { "Content-Type": "application/pdf", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
                return void createReadStream(file).on("error", () => res.end()).pipe(res);
            }
            default: return send(res, 404, { error: "Introuvable." });
        }
    }

    page(res) {
        res.writeHead(200, {
            "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; " +
                "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'",
        });
        res.end(readFileSync(join(WEB, "index.html")));
    }

    stream(req, res, reader, instance) {
        res.writeHead(200, { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-store", Connection: "keep-alive" });
        res.write("retry: 3000\n\n");
        if (instance) {
            if (this.registry.instances[instance] !== reader.rid) {
                this.registry.instances[instance] = reader.rid;
                this.saveRegistry();
            }
            reader.rehydrate(instance);
        }
        const remove = reader.addClient(res, instance);
        res.write(`data: ${JSON.stringify({ type: "status", status: reader.status, error: reader.error, version: reader.version })}\n\n`);
        reader.start();
        const heartbeat = setInterval(() => res.write(": ping\n\n"), 25_000);
        heartbeat.unref?.();
        req.on("close", () => {
            clearInterval(heartbeat);
            remove();
        });
    }

    async events(req, res, reader) {
        const body = await readBody(req);
        if (!Array.isArray(body.events) || body.events.length > 200) throw new RequestError(400, "events doit être une liste.");
        const rejected = [];
        let recorded = 0;
        body.events.forEach((input, position) => {
            try {
                if (reader.recordStudent(input)) recorded += 1;
            } catch (error) {
                if (error instanceof RequestError) throw error;
                rejected.push({ position, error: error.message });
            }
        });
        send(res, 200, { recorded, rejected });
    }

    async openLink(req, res, reader) {
        const body = await readBody(req);
        const link = reader.resolveLink(body.href);
        const target = link.type === "pdf_opened" && link.inside
            ? `http://127.0.0.1:${this.port}/r/${reader.rid}/vault/${link.url.split("/").map(encodeURIComponent).join("/")}` +
              `?t=${this.token}${link.page ? `#page=${link.page}` : ""}`
            : link.type === "pdf_opened" ? link.file : link.url;
        try {
            await this.opener(target);
        } catch (error) {
            throw new RequestError(502, `Impossible d'ouvrir le lien : ${error.message}`);
        }
        reader.recordLink(link, body.question);
        send(res, 200, { ok: true });
    }

    async ask(req, res, reader) {
        const body = await readBody(req);
        if (!this.session) throw new RequestError(503, "La session Copilot n'est pas connectée.");
        const prompt = reader.ask(body.question, typeof body.instance === "string" ? body.instance : "");
        if (!prompt) throw new RequestError(429, "Demande déjà envoyée. Patientez quelques secondes.");
        await this.session.send({ prompt, displayPrompt: DISPLAY_PROMPT, mode: "enqueue" });
        send(res, 200, { ok: true });
    }
}
