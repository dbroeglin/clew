// THROWAWAY SPIKE for the Clew canvas design. Will be removed after findings are recorded.
import { createServer } from "node:http";
import { appendFileSync, mkdirSync, writeFileSync, readFileSync, watch, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, extname } from "node:path";
import { fileURLToPath } from "node:url";
import { execFile } from "node:child_process";
import { joinSession, createCanvas } from "@github/copilot-sdk/extension";

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
const dir = join(tmpdir(), "clew-spike");
mkdirSync(dir, { recursive: true });
let session;
const logPath = () => join(dir, `${session?.sessionId ?? "pending"}.jsonl`);
const record = (kind, data) => {
    try { appendFileSync(logPath(), JSON.stringify({ ts: new Date().toISOString(), kind, ...data }) + "\n"); } catch {}
};
const watchEvents = [];
const watchers = new Map();

let pdfPath = "";
const page = () => `<!doctype html><html><head><meta charset="utf-8"><title>spike</title></head>
<body style="font-family: var(--font-sans, system-ui); color: var(--color-fg-default, #222); background: var(--color-canvas-default, #fff); padding: 1rem">
<h1>Clew spike</h1>
<p><a id="ext" href="https://example.com/" target="_blank" rel="noopener">external target=_blank</a></p>
<p><a id="ext2" href="https://example.com/?same">external same frame</a></p>
<p><a id="pdf" href="/file?path=${encodeURIComponent(pdfPath)}#page=2" target="_blank">pdf via server target=_blank</a></p>
<iframe src="/file?path=${encodeURIComponent(pdfPath)}#page=2" style="width:100%;height:200px"></iframe>
<p><button id="b" onclick="navigator.sendBeacon('/beacon', JSON.stringify({clicked:'button', at: Date.now()}))">beacon</button>
<button onclick="window.open('https://example.com/?wo','_blank')">window.open</button>
<button onclick="fetch('/send?mode=enqueue&display=I%20need%20help%20with%20this%20question&prompt=' + encodeURIComponent('HIDDEN-CONTEXT q=note#^q-1 hints=1/2'))">ask tutor</button></p>
<pre id="theme"></pre>
<script>
document.querySelectorAll('a').forEach(a => a.addEventListener('click', () => navigator.sendBeacon('/beacon', JSON.stringify({clicked: a.id}))));
const vars = []; for (const sheet of document.styleSheets) { try { for (const r of sheet.cssRules) { if (r.style) for (const p of r.style) if (p.startsWith('--')) vars.push(p); } } catch {} }
document.getElementById('theme').textContent = 'css vars seen: ' + vars.length + '\\n' + vars.slice(0, 40).join('\\n');
navigator.sendBeacon('/beacon', JSON.stringify({loaded: true, ua: navigator.userAgent, vars: vars.length, dark: matchMedia('(prefers-color-scheme: dark)').matches, href: location.href}));
</script></body></html>`;

const json = (res, value, status = 200) => { res.writeHead(status, { "Content-Type": "application/json" }); res.end(JSON.stringify(value)); };
const body = (req) => new Promise((ok) => { let b = ""; req.on("data", (c) => (b += c)); req.on("end", () => ok(b)); });

const server = createServer(async (req, res) => {
    const url = new URL(req.url, "http://127.0.0.1");
    const q = Object.fromEntries(url.searchParams);
    try {
        switch (url.pathname) {
            case "/": res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }); return res.end(page());
            case "/pdf": pdfPath = q.path; return json(res, { ok: true });
            case "/beacon": { const b = await body(req); record("beacon", { body: b }); return json(res, { ok: true }); }
            case "/log": await session.log(q.msg ?? "spike log", { level: q.level ?? "info", ephemeral: q.ephemeral === "1" }); return json(res, { ok: true });
            case "/send": {
                const id = await session.send({ prompt: q.prompt ?? "spike", displayPrompt: q.display, mode: q.mode ?? "enqueue" });
                record("send", { q, id }); return json(res, { ok: true, id });
            }
            case "/write": { mkdirSync(resolve(q.path, ".."), { recursive: true }); writeFileSync(q.path, q.text ?? "spike\n"); return json(res, { ok: true }); }
            case "/compile": {
                const t0 = Date.now();
                const args = ["run", "--package", "clew-generate", "--locked", "--no-sync", "python", "-B", join(repoRoot, ".agents/skills/clew-generate/scripts/generate_html.py"), q.layout, "--check"];
                execFile("uv", args, { cwd: repoRoot, maxBuffer: 64 << 20 }, (err, stdout, stderr) => json(res, { ms: Date.now() - t0, code: err?.code ?? 0, stdout: stdout.slice(0, 2000), stderr: stderr.slice(0, 2000) }));
                return;
            }
            case "/watch": {
                if (!watchers.has(q.path)) watchers.set(q.path, watch(q.path, { recursive: true }, (type, file) => watchEvents.push({ ts: Date.now(), type, file })));
                return json(res, { ok: true });
            }
            case "/watch-events": return json(res, watchEvents);
            case "/events": { const ev = await session.getEvents(); return json(res, { count: ev.length, tail: ev.slice(-Number(q.n ?? 10)).map((e) => ({ type: e.type, data: e.data })) }); }
            case "/canvases": return json(res, session.openCanvases);
            case "/file": {
                if (!existsSync(q.path)) return json(res, { error: "missing" }, 404);
                res.writeHead(200, { "Content-Type": extname(q.path).toLowerCase() === ".pdf" ? "application/pdf" : "application/octet-stream" });
                return res.end(readFileSync(q.path));
            }
            default: return json(res, { error: "not found" }, 404);
        }
    } catch (e) { record("error", { path: url.pathname, message: String(e?.stack ?? e) }); json(res, { error: String(e) }, 500); }
});
await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
const port = server.address().port;

session = await joinSession({
    hooks: {
        onUserPromptSubmitted: async (input) => {
            record("hook.userPrompt", { prompt: input.prompt });
            return { additionalContext: `CLEW-SPIKE-MARKER ${new Date().toISOString()}: the student revealed hint 1/2 of question Q1.` };
        },
        onPreToolUse: async (input) => {
            const args = JSON.stringify(input.toolArgs ?? {});
            record("hook.preToolUse", { tool: input.toolName, args: args.slice(0, 300) });
            if (args.includes("clew-spike-forbidden")) return { permissionDecision: "deny", permissionDecisionReason: "Clew spike guard: this path is read-only." };
            return undefined;
        },
    },
    canvases: [
        createCanvas({
            id: "clew-spike",
            displayName: "Clew spike",
            description: "Throwaway spike canvas for the Clew canvas design.",
            inputSchema: { type: "object", properties: { note: { type: "string" } } },
            actions: [{ name: "get_state", description: "Return spike state", handler: async (ctx) => ({ ok: true, instanceId: ctx.instanceId, port }) }],
            open: async (ctx) => { record("canvas.open", { ctx }); return { title: "Clew spike", url: `http://127.0.0.1:${port}/` }; },
            onClose: async (ctx) => { record("canvas.close", { ctx }); },
        }),
    ],
});
session.on((event) => { if (!/delta|streaming/i.test(event.type)) record("event", { type: event.type }); });
const info = { port, sessionId: session.sessionId, workspacePath: session.workspacePath, cwd: process.cwd(), pid: process.pid, repoRoot };
writeFileSync(join(dir, `${session.sessionId}.json`), JSON.stringify(info, null, 2));
writeFileSync(join(dir, "latest.json"), JSON.stringify(info, null, 2));
record("started", info);
