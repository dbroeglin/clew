import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { request } from "node:http";
import { join, relative } from "node:path";
import { describe, test } from "node:test";
import { fakeCompile, fixtureData, makeVault, REPO, until } from "./helpers.mjs";

const { CanvasApp, DISPLAY_PROMPT, readerId, sessionPort } = await import(new URL("../../.github/extensions/clew-canvas/lib/app.mjs", import.meta.url));

const data = await fixtureData();
const Q1 = "sheet#^q-1";
const SHEET_PDF = "Maths/Suites%20r%C3%A9vision/Exercise-sheet/sheet.pdf#page=2";

function fakeSession() {
    const handlers = [];
    const session = {
        sent: [],
        on: (handler) => handlers.push(handler),
        emit: (type, data) => handlers.forEach((handler) => handler({ type, data })),
        rpc: { agent: { getCurrent: async () => ({ agent: null }) } },
        send: async (message) => session.sent.push(message),
    };
    return session;
}

async function startApp(t, { vaultInfo = makeVault(t), stateDir, compile = fakeCompile(data), opener, session = fakeSession() } = {}) {
    const opened = [];
    const app = new CanvasApp({ repoRoot: REPO, sessionId: "session-under-test", stateDir: stateDir ?? join(vaultInfo.root, "state"),
        compile, opener: opener ?? (async (target) => opened.push(target)), watchFiles: false });
    await app.start();
    if (session) app.attach(session);
    t.after(() => app.stop());
    return { app, session, opened, vaultInfo };
}

/** Raw HTTP call so Host and Origin headers can be controlled. */
function call(app, method, path, { body, headers = {} } = {}) {
    return new Promise((done, fail) => {
        const payload = body === undefined ? undefined : typeof body === "string" ? body : JSON.stringify(body);
        const req = request({ host: "127.0.0.1", port: app.port, method, path,
            headers: { ...(payload ? { "content-type": "application/json" } : {}), ...headers } }, (res) => {
            const chunks = [];
            res.on("data", (chunk) => chunks.push(chunk));
            res.on("end", () => {
                const text = Buffer.concat(chunks).toString("utf8");
                let json;
                try {
                    json = JSON.parse(text);
                } catch {
                    json = undefined;
                }
                done({ status: res.statusCode, headers: res.headers, text, json });
            });
        });
        req.on("error", fail);
        req.end(payload);
    });
}

function openCanvas(app, vaultInfo, instanceId = "c1", layout = vaultInfo.layout) {
    const result = app.open({ instanceId, input: { layout: relative(vaultInfo.root, layout) }, session: { workingDirectory: vaultInfo.root } });
    const url = new URL(result.url);
    const base = url.pathname;
    const token = url.searchParams.get("t");
    return { result, base, token, path: (route) => `${base}${route}${route.includes("?") ? "&" : "?"}t=${token}` };
}

/** Collect server-sent events from the canvas stream. */
function stream(app, path) {
    const messages = [];
    let req;
    const ready = new Promise((done, fail) => {
        req = request({ host: "127.0.0.1", port: app.port, path }, (res) => {
            res.setEncoding("utf8");
            let buffer = "";
            res.on("data", (chunk) => {
                buffer += chunk;
                for (let at = buffer.indexOf("\n\n"); at >= 0; at = buffer.indexOf("\n\n")) {
                    const block = buffer.slice(0, at);
                    buffer = buffer.slice(at + 2);
                    const line = block.split("\n").find((l) => l.startsWith("data: "));
                    if (line) messages.push(JSON.parse(line.slice(6)));
                }
            });
            done(res);
        });
        req.on("error", fail);
        req.end();
    });
    return { messages, ready, close: () => req.destroy() };
}

describe("canvas app", () => {
    test("derives stable reader ids and session ports", () => {
        assert.match(readerId("C:\\Vault\\Activity\\Layouts\\a.json"), /^[0-9a-f]{12}$/);
        assert.equal(readerId("/v/a.json"), readerId("/v/a.json"));
        const port = sessionPort("abc");
        assert.ok(port >= 41000 && port < 49000);
        assert.equal(port, sessionPort("abc"));
    });

    test("opens a vault layout and rejects anything else", async (t) => {
        const { app, vaultInfo } = await startApp(t);
        assert.throws(() => app.open({ instanceId: "x", input: {} }), /input\.layout/);
        assert.throws(() => app.open({ instanceId: "x", input: { layout: join(vaultInfo.root, "missing.json") } }), /Layout not found/);
        assert.throws(() => app.open({ instanceId: "x", input: { layout: vaultInfo.sheet } }), /Layout not found/);
        const outside = join(vaultInfo.root, "outside.json");
        (await import("node:fs")).writeFileSync(outside, "{}");
        assert.throws(() => app.open({ instanceId: "x", input: { layout: outside } }), /inside an Obsidian vault/);
        const { result } = openCanvas(app, vaultInfo);
        assert.equal(result.title, "Clew · Suites · révision");
        assert.equal(result.status, "Compilation…");
        assert.match(result.url, new RegExp(`^http://127\\.0\\.0\\.1:${app.port}/r/[0-9a-f]{12}/\\?t=[0-9a-f]{48}&i=c1$`));
        await app.ready(app.instanceReader("c1"));
        assert.equal(openCanvas(app, vaultInfo).result.status, "Prêt");
        assert.throws(() => app.instanceReader("other"), /not open/);
    });

    test("serves only token-bearing loopback requests", async (t) => {
        const { app, vaultInfo } = await startApp(t);
        const canvas = openCanvas(app, vaultInfo);
        const page = await call(app, "GET", canvas.path(""));
        assert.equal(page.status, 200);
        assert.match(page.headers["content-security-policy"], /script-src 'self'/);
        assert.match(page.text, /<script src="\/web\/app\.js"/);
        assert.equal((await call(app, "GET", `${canvas.base}`)).status, 403);
        assert.equal((await call(app, "GET", `${canvas.base}?t=${"0".repeat(48)}`)).status, 403);
        assert.equal((await call(app, "GET", canvas.path(""), { headers: { host: "evil.example" } })).status, 403);
        assert.equal((await call(app, "GET", `${canvas.base}api/state`, { headers: { "x-clew-token": canvas.token } })).status, 200);
        assert.equal((await call(app, "POST", canvas.path("api/event"), { body: { events: [] },
            headers: { origin: "https://evil.example" } })).status, 403);
        assert.equal((await call(app, "POST", canvas.path("api/event"), { body: { events: [] },
            headers: { origin: `http://127.0.0.1:${app.port}` } })).status, 200);
        assert.equal((await call(app, "GET", canvas.path("../../etc"))).status, 404);
        assert.equal((await call(app, "GET", `/r/ffffffffffff/?t=${canvas.token}`)).status, 404);
        for (const asset of ["/web/app.js", "/web/boot.js", "/web/canvas.css", "/assets/style.css", "/assets/mathjax/tex-svg.js"]) {
            assert.equal((await call(app, "GET", asset)).status, 200, asset);
        }
        assert.equal((await call(app, "GET", "/web/index.html")).status, 404);
    });

    test("delivers data, records events and opens published links", async (t) => {
        const { app, vaultInfo, opened } = await startApp(t);
        const canvas = openCanvas(app, vaultInfo);
        const reader = app.instanceReader("c1");
        await app.ready(reader);
        const loaded = await call(app, "GET", canvas.path("api/data"));
        assert.equal(loaded.status, 200);
        assert.equal(loaded.headers["x-clew-version"], "1");
        assert.equal(loaded.json.title, "Suites · révision");
        const posted = await call(app, "POST", canvas.path("api/event"), { body: { events: [
            { type: "exercise_started", exercise: "sheet#^ex-1" },
            { type: "hint_revealed", question: Q1, index: 3 },
            { type: "correction_shown", question: Q1 },
        ] } });
        assert.deepEqual(posted.json, { recorded: 2, rejected: [{ position: 1, error: `Invalid hint index for ${Q1}.` }] });
        assert.equal((await call(app, "POST", canvas.path("api/event"), { body: { events: Array(201).fill({}) } })).status, 400);
        assert.equal((await call(app, "POST", canvas.path("api/event"), { body: "{nope" })).status, 400);
        const link = await call(app, "POST", canvas.path("api/open"), { body: { href: SHEET_PDF, question: Q1 } });
        assert.equal(link.status, 200);
        assert.equal(opened.length, 1);
        const target = new URL(opened[0]);
        assert.equal(target.hash, "#page=2");
        const pdf = await call(app, "GET", `${target.pathname}${target.search}`);
        assert.deepEqual([pdf.status, pdf.headers["content-type"], pdf.text], [200, "application/pdf", "%PDF-1.4\n%fixture\n"]);
        assert.equal((await call(app, "GET", `${target.pathname}`)).status, 403);
        assert.equal((await call(app, "GET", canvas.path("vault/Maths/Suites%20r%C3%A9vision/Exercise-sheet/sheet.md"))).status, 404);
        assert.equal((await call(app, "POST", canvas.path("api/open"), { body: { href: "https://evil.example/" } })).status, 400);
        assert.deepEqual(reader.events.map((e) => e.type), ["canvas_opened", "exercise_started", "correction_shown", "pdf_opened"]);
    });

    test("an opener failure is reported and not recorded", async (t) => {
        const { app, vaultInfo } = await startApp(t, { opener: async () => { throw new Error("no handler"); } });
        const canvas = openCanvas(app, vaultInfo);
        await app.ready(app.instanceReader("c1"));
        const result = await call(app, "POST", canvas.path("api/open"), { body: { href: SHEET_PDF } });
        assert.deepEqual([result.status, result.json.error], [502, "Impossible d'ouvrir le lien : no handler"]);
        assert.ok(!app.instanceReader("c1").events.some((e) => e.type === "pdf_opened"));
    });

    test("asks the tutor through the session with a fixed visible prompt", async (t) => {
        const { app, vaultInfo, session } = await startApp(t);
        const canvas = openCanvas(app, vaultInfo);
        await app.ready(app.instanceReader("c1"));
        const ask = () => call(app, "POST", canvas.path("api/ask"), { body: { question: Q1, instance: "c1" } });
        assert.equal((await ask()).status, 200);
        assert.equal((await ask()).status, 429);
        assert.equal(session.sent.length, 1);
        assert.equal(session.sent[0].displayPrompt, DISPLAY_PROMPT);
        assert.equal(session.sent[0].mode, "enqueue");
        assert.match(session.sent[0].prompt, /^\[Clew canvas\] The student pressed "Ask the tutor" on Question 1/);
        assert.equal((await call(app, "POST", canvas.path("api/ask"), { body: { question: "nope" } })).status, 400);
        assert.equal(app.onUserPromptSubmitted(), undefined, "the ask prompt already carried the digest");
    });

    test("asking without a connected session is refused", async (t) => {
        const { app, vaultInfo } = await startApp(t, { session: null });
        const canvas = openCanvas(app, vaultInfo);
        await app.ready(app.instanceReader("c1"));
        assert.equal((await call(app, "POST", canvas.path("api/ask"), { body: { question: Q1 } })).status, 503);
    });

    test("streams status, rehydrates instances and routes show", async (t) => {
        let release;
        const gate = new Promise((done) => {
            release = done;
        });
        const { app, vaultInfo } = await startApp(t, { compile: fakeCompile(async () => (await gate, data)) });
        const canvas = openCanvas(app, vaultInfo);
        const events = stream(app, canvas.path("api/stream?i=c2"));
        t.after(() => events.close());
        await events.ready;
        await until(() => events.messages.length >= 1);
        assert.deepEqual(events.messages[0], { type: "status", status: "compiling", error: null, version: 0 });
        assert.equal((await call(app, "GET", canvas.path("api/data"))).status, 503);
        release();
        await until(() => events.messages.some((m) => m.status === "ready"));
        const reader = app.instanceReader("c2");
        assert.equal(reader, app.instanceReader("c1"));
        assert.ok(reader.events.some((e) => e.type === "canvas_rehydrated" && e.instance === "c2"));
        assert.deepEqual(await app.show({ instanceId: "c2", input: { target: Q1 } }), { shown: "question", address: Q1, delivered: true });
        await until(() => events.messages.some((m) => m.type === "show"));
        assert.deepEqual(events.messages.at(-1), { type: "show", kind: "question", address: Q1 });
        assert.equal((await app.show({ instanceId: "c1", input: { target: Q1 } })).delivered, false);
        await assert.rejects(app.show({ instanceId: "c1", input: { target: "nope" } }), /Unknown target/);
        const state = await app.getState({ instanceId: "c1", input: { question: Q1 } });
        assert.equal(state.question.label, "Question 1");
        assert.deepEqual(state.instances.sort(), ["c1", "c2"]);
    });

    test("a restarted extension keeps its port, token and readers", async (t) => {
        const vaultInfo = makeVault(t);
        const stateDir = join(vaultInfo.root, "state");
        const first = await startApp(t, { vaultInfo, stateDir });
        const canvas = openCanvas(first.app, vaultInfo);
        await first.app.ready(first.app.instanceReader("c1"));
        const port = first.app.port;
        await first.app.stop();
        const registry = JSON.parse(readFileSync(join(stateDir, "registry.json"), "utf8"));
        assert.deepEqual(Object.keys(registry).sort(), ["instances", "port", "readers", "token"]);
        const second = await startApp(t, { vaultInfo, stateDir });
        assert.equal(second.app.port, port);
        assert.equal(second.app.token, canvas.token);
        const restored = await call(second.app, "GET", canvas.path("api/state"));
        assert.equal(restored.status, 200);
        assert.equal(restored.json.status, "idle");
        assert.equal((await second.app.getState({ instanceId: "c1", input: {} })).status, "ready");
        const reader = second.app.instanceReader("c1");
        assert.equal(reader.store.folder, first.app.readers.values().next().value.store.folder);
        second.app.close({ instanceId: "c1" });
        assert.equal(reader.events.at(-1).type, "canvas_closed");
        assert.throws(() => second.app.instanceReader("c1"), /not open/);
    });

    test("reopening an instance on another layout closes the previous reader", async (t) => {
        const { app, vaultInfo } = await startApp(t);
        openCanvas(app, vaultInfo);
        const first = app.instanceReader("c1");
        await app.ready(first);
        const other = join(vaultInfo.vault, "Activity", "Layouts", "other.json");
        (await import("node:fs")).writeFileSync(other, readFileSync(vaultInfo.layout));
        openCanvas(app, vaultInfo, "c1", other);
        assert.equal(first.events.at(-1).type, "canvas_closed");
        assert.notEqual(app.instanceReader("c1"), first);
    });

    test("digests new activity once per prompt", async (t) => {
        const { app, vaultInfo } = await startApp(t);
        openCanvas(app, vaultInfo);
        const reader = app.instanceReader("c1");
        await app.ready(reader);
        const digest = app.onUserPromptSubmitted();
        assert.match(digest.additionalContext, /Student opened the canvas\./);
        assert.equal(app.onUserPromptSubmitted(), undefined);
        reader.recordStudent({ type: "method_shown", question: Q1 });
        assert.match(app.onUserPromptSubmitted().additionalContext, /opened the method/);
    });

    test("guards vault writes only while the tutor agent is active", async (t) => {
        const { app, vaultInfo, session } = await startApp(t);
        const edit = { toolName: "edit", toolArgs: { path: vaultInfo.sheet }, workingDirectory: vaultInfo.root };
        assert.equal(app.onPreToolUse(edit), undefined);
        assert.equal(app.onPreToolUse({ ...edit, agentType: "clew-tutor" }).permissionDecision, "deny");
        session.emit("subagent.selected", { agentName: "clew-tutor", agentDisplayName: "Clew tutor" });
        const denied = app.onPreToolUse(edit);
        assert.equal(denied.permissionDecision, "deny");
        assert.match(denied.permissionDecisionReason, /read-only for the tutor/);
        assert.equal(app.onPreToolUse({ ...edit, toolArgs: { path: join(vaultInfo.vault, "Activity", "Layouts", "n.json") } }), undefined);
        session.emit("subagent.selected", { agentName: "other" });
        assert.equal(app.onPreToolUse(edit), undefined);
        session.emit("subagent.selected", { agentName: "clew-tutor" });
        session.emit("subagent.deselected", {});
        assert.equal(app.onPreToolUse(edit), undefined);
        const current = fakeSession();
        current.rpc.agent.getCurrent = async () => ({ agent: { name: "clew-tutor" } });
        app.attach(current);
        await until(() => app.tutorActive);
        assert.equal(app.onPreToolUse(edit).permissionDecision, "deny");
        assert.ok(existsSync(vaultInfo.sheet));
    });
});
