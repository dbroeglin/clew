// Browser-test harness: serves the fixture publication through CanvasApp with a fake Copilot session.
// Protocol: one JSON command per stdin line, one JSON reply per stdout line. Driven by test_browser.py.
import { join } from "node:path";
import { createInterface } from "node:readline";
import { makeVault, REPO } from "./helpers.mjs";

const { CanvasApp } = await import(new URL("../../.github/extensions/clew-canvas/lib/app.mjs", import.meta.url));

const cleanups = [];
const vaultInfo = makeVault({ after: (fn) => cleanups.push(fn) });
const stateDir = join(vaultInfo.root, "state");
const sent = [];
const opened = [];
let openerFails = false;
const session = {
    on: () => {},
    rpc: { agent: { getCurrent: async () => ({ agent: null }) } },
    send: async (message) => sent.push(message),
};

let app = null;
async function start() {
    app = new CanvasApp({
        repoRoot: REPO, sessionId: "browser-test-session", stateDir, debounceMs: 300,
        log: (message) => process.stderr.write(`${message}\n`),
        opener: async (target) => {
            if (openerFails) throw new Error("opener unavailable");
            opened.push(target);
        },
    });
    await app.start();
    app.attach(session);
}

const commands = {
    open: ({ instance, layout = vaultInfo.layout }) =>
        app.open({ instanceId: instance, input: { layout }, session: { workingDirectory: vaultInfo.root } }),
    state: ({ instance, ...input }) => app.getState({ instanceId: instance, input }),
    show: ({ instance, target }) => app.show({ instanceId: instance, input: { target } }),
    digest: () => app.onUserPromptSubmitted(),
    close: ({ instance }) => app.close({ instanceId: instance }),
    sent: () => sent,
    opened: () => opened,
    opener: ({ fails }) => (openerFails = Boolean(fails)),
    pause: () => app.stop(),
    resume: () => start(),
};

await start();
const reply = (value) => process.stdout.write(`${JSON.stringify(value)}\n`);
reply({ ready: true, root: vaultInfo.root, vault: vaultInfo.vault, chapter: vaultInfo.chapter, layout: vaultInfo.layout });

for await (const line of createInterface({ input: process.stdin })) {
    if (!line.trim()) continue;
    const { cmd, ...args } = JSON.parse(line);
    if (cmd === "quit") break;
    try {
        reply({ ok: true, result: (await commands[cmd](args)) ?? null });
    } catch (error) {
        reply({ ok: false, error: error.message });
    }
}
await app?.stop();
cleanups.forEach((fn) => fn());
process.exit(0);
