/** Shared fixtures: a temporary Obsidian vault holding the clew-generate test chapter. */
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { compileData } from "../../.github/extensions/clew-canvas/lib/compile.mjs";

export const REPO = fileURLToPath(new URL("../../", import.meta.url));
export const LIB = new URL("../../.github/extensions/clew-canvas/lib/", import.meta.url);
const FIXTURE = fileURLToPath(new URL("../clew_generate/fixtures/chapter/", import.meta.url));
export const CHAPTER = "Maths/Suites révision";
export const SESSION = "0123456789abcdef-session";

/** Vault with `.obsidian/`, the fixture chapter, a sheet PDF and a layout in Activity/Layouts. */
export function makeVault(t, { title = "Suites · révision" } = {}) {
    const root = mkdtempSync(join(tmpdir(), "clew-canvas-test-"));
    t.after(() => rmSync(root, { recursive: true, force: true }));
    const vault = join(root, "Vault");
    mkdirSync(join(vault, ".obsidian"), { recursive: true });
    const chapter = join(vault, ...CHAPTER.split("/"));
    cpSync(FIXTURE, chapter, { recursive: true });
    writeFileSync(join(chapter, "Exercise-sheet", "sheet.pdf"), "%PDF-1.4\n%fixture\n");
    const layouts = join(vault, "Activity", "Layouts");
    mkdirSync(layouts, { recursive: true });
    const layout = join(layouts, "suites.json");
    writeFileSync(layout, JSON.stringify({ schema_version: 1, title, notes: [`../../${CHAPTER}`] }, null, 2));
    return { root, vault, chapter, layout, sheet: join(chapter, "Exercise-sheet", "sheet.md") };
}

let compiled = null;

/** Compile the fixture once per process with the real clew-generate data mode. */
export function fixtureData() {
    compiled ??= (async () => {
        const cleanups = [];
        try {
            const { root, vault, layout } = makeVault({ after: (fn) => cleanups.push(fn) });
            const target = join(root, "data.json");
            const result = await compileData({ repoRoot: REPO, layout, target, base: vault });
            if (!result.ok) throw new Error(result.error);
            return readFileSync(target, "utf8");
        } finally {
            cleanups.forEach((fn) => fn());
        }
    })();
    return compiled.then((text) => JSON.parse(text));
}

/** Compile stand-in that writes the given data (or a function of the call count) to the target. */
export function fakeCompile(source) {
    const calls = [];
    const compile = async (options) => {
        calls.push(options);
        const data = typeof source === "function" ? await source(calls.length, options) : source;
        if (data instanceof Error) return { ok: false, error: data.message };
        writeFileSync(options.target, typeof data === "string" ? data : JSON.stringify(data));
        return { ok: true, report: { status: "data" } };
    };
    compile.calls = calls;
    return compile;
}

/** Deterministic clock advancing by `step` ms per call. */
export function clock(start = "2026-11-01T10:00:00.000Z", step = 0) {
    let time = Date.parse(start);
    const now = () => {
        const date = new Date(time);
        time += step;
        return date;
    };
    now.advance = (ms) => {
        time += ms;
    };
    now.set = (iso) => {
        time = Date.parse(iso);
    };
    return now;
}

export const until = async (predicate, { timeout = 10_000, interval = 25 } = {}) => {
    const start = Date.now();
    for (;;) {
        const value = await predicate();
        if (value) return value;
        if (Date.now() - start > timeout) throw new Error("Timed out waiting for condition.");
        await new Promise((done) => setTimeout(done, interval));
    }
};
