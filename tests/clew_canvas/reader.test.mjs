import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, test } from "node:test";
import { pathToFileURL } from "node:url";
import { clock, fakeCompile, fixtureData, makeVault, SESSION, until } from "./helpers.mjs";

const { Reader, publishedLinks, topmost, ASK_INTERVAL_MS } = await import(new URL("../../.github/extensions/clew-canvas/lib/reader.mjs", import.meta.url));
const { readJsonl } = await import(new URL("../../.github/extensions/clew-canvas/lib/activity.mjs", import.meta.url));

const data = await fixtureData();
const Q1 = "sheet#^q-1";
const SHEET_PDF = "Maths/Suites%20r%C3%A9vision/Exercise-sheet/sheet.pdf#page=2";

function makeReader(t, { compile = fakeCompile(data), now = clock("2026-11-01T12:00:00.000Z", 1000), watchFiles = false,
                         vaultInfo = makeVault(t), debounceMs = 50 } = {}) {
    const logs = [];
    const reader = new Reader({ rid: "0123456789ab", layout: vaultInfo.layout, vault: vaultInfo.vault, repoRoot: "R",
        session: SESSION, cacheDir: join(vaultInfo.root, "cache"), compile, now, debounceMs, watchFiles,
        log: (message, level) => logs.push([level, message]) });
    t.after(() => reader.dispose());
    return Object.assign(reader, { logs, vaultInfo, now });
}

const sink = () => {
    const messages = [];
    return { messages, res: { write: (line) => messages.push(JSON.parse(line.replace(/^data: /, ""))), end() {} } };
};

describe("reader", () => {
    test("helpers list published links and non-overlapping roots", () => {
        const links = publishedLinks(data);
        assert.ok(links.has(SHEET_PDF));
        assert.ok(![...links].some((href) => href.startsWith("#")));
        assert.deepEqual(topmost(["/a/b", "/a", "/c", "/a/b/c"]).map((dir) => dir.replace(/^[A-Z]:/i, "").replace(/\\/g, "/")),
            ["/a", "/c"]);
    });

    test("records lifecycle before the first compile and keeps it after", async (t) => {
        const reader = makeReader(t);
        const status = sink();
        reader.addClient(status.res, "");
        reader.open("c1");
        assert.equal(reader.status, "compiling");
        assert.throws(() => reader.requireData(), (error) => error.status === 503);
        await reader.start();
        assert.equal(reader.status, "ready");
        assert.equal(reader.version, 1);
        assert.deepEqual(status.messages.map((m) => m.status), ["compiling", "ready"]);
        assert.deepEqual(reader.events.map((e) => e.type), ["canvas_opened"]);
        assert.deepEqual(readJsonl(reader.store.journal).map((r) => r.type), ["header", "canvas_opened"]);
        assert.match(readFileSync(reader.store.summaryPath, "utf8"), /type: clew-activity/);
        assert.equal(readFileSync(join(reader.store.internal, "layout.json"), "utf8"), readFileSync(reader.layout, "utf8"));
    });

    test("compile failures are reported, retried and keep the last good data", async (t) => {
        let fail = true;
        const compile = fakeCompile(() => (fail ? new Error("Missing note: x") : data));
        const reader = makeReader(t, { compile });
        await reader.start();
        assert.deepEqual([reader.status, reader.error], ["error", "Missing note: x"]);
        assert.equal(reader.frontState().error, "Missing note: x");
        await reader.start();
        assert.equal(compile.calls.length, 1, "start does not retry");
        fail = false;
        await reader.retry();
        assert.equal(reader.status, "ready");
        fail = true;
        await reader.compileNow();
        assert.deepEqual([reader.status, reader.version, Boolean(reader.index)], ["stale", 1, true]);
        assert.ok(reader.logs.some(([level]) => level === "warning"));
    });

    test("student events are validated and deduplicated", async (t) => {
        const reader = makeReader(t);
        await reader.start();
        assert.ok(reader.recordStudent({ type: "exercise_started", exercise: "sheet#^ex-1" }));
        assert.equal(reader.recordStudent({ type: "exercise_started", exercise: "sheet#^ex-1" }), null);
        assert.ok(reader.recordStudent({ type: "hint_revealed", question: Q1, index: 2 }));
        assert.equal(reader.recordStudent({ type: "hint_revealed", question: Q1, index: 1 }), null);
        assert.throws(() => reader.recordStudent({ type: "hint_revealed", question: Q1, index: 9 }), /Invalid hint/);
        assert.ok(reader.recordStudent({ type: "method_shown", question: "sheet#^q-2" }));
        assert.deepEqual(reader.frontState().hints, { [Q1]: 2 });
        assert.deepEqual(reader.frontState().started, ["sheet#^ex-1"]);
    });

    test("only published links open, and PDFs stay inside the vault when possible", async (t) => {
        const reader = makeReader(t);
        await reader.start();
        assert.throws(() => reader.resolveLink("https://evil.example/"), (e) => e.status === 400);
        assert.throws(() => reader.resolveLink("Maths/Suites%20r%C3%A9vision/Course-course/course.pdf#page=1"),
            (e) => e.status === 404);
        const pdf = reader.resolveLink(SHEET_PDF);
        assert.deepEqual([pdf.type, pdf.url, pdf.page, pdf.inside], ["pdf_opened", "Maths/Suites révision/Exercise-sheet/sheet.pdf", 2, true]);
        assert.equal(reader.pdfFile("Maths/Suites révision/Exercise-sheet/sheet.pdf"), pdf.file);
        assert.equal(reader.pdfFile("Maths/Suites révision/Exercise-sheet/sheet.md"), null);
        assert.equal(reader.pdfFile("../outside.pdf"), null);
        reader.links.add("https://example.com/x");
        assert.deepEqual(reader.resolveLink("https://example.com/x"), { type: "link_opened", url: "https://example.com/x" });
        const outside = pathToFileURL(join(reader.vaultInfo.root, "outside.pdf")).href;
        writeFileSync(join(reader.vaultInfo.root, "outside.pdf"), "%PDF");
        reader.links.add(`${outside}#page=3`);
        const external = reader.resolveLink(`${outside}#page=3`);
        assert.deepEqual([external.url, external.page, external.inside], [outside, 3, false]);
        reader.recordLink(pdf, Q1);
        reader.recordLink(external, "sheet#^nope");
        assert.deepEqual(reader.events.slice(-2).map((e) => [e.type, e.question, e.exercise]),
            [["pdf_opened", Q1, "sheet#^ex-1"], ["pdf_opened", undefined, undefined]]);
    });

    test("tutor requests are rate limited and consume the digest cursor", async (t) => {
        const now = clock("2026-11-01T12:00:00.000Z");
        const reader = makeReader(t, { now });
        reader.open("c1");
        await reader.start();
        reader.recordStudent({ type: "hint_revealed", question: Q1, index: 1 });
        const prompt = reader.ask(Q1, "c1");
        assert.match(prompt, /canvas instance "c1"/);
        assert.match(prompt, /Student revealed hint 1\/2/);
        assert.match(prompt, /tutor requests 1 including this one/);
        assert.equal(reader.ask(Q1, "c1"), null);
        assert.ok(reader.ask("sheet#^q-2", "c1"), "the limit is per question");
        now.advance(ASK_INTERVAL_MS);
        assert.match(reader.ask(Q1, "c1"), /tutor requests 2 including this one/);
        assert.throws(() => reader.ask("sheet#^nope", "c1"), (e) => e.status === 400);
        assert.equal(reader.takeDigest(), null);
        reader.recordStudent({ type: "correction_shown", question: Q1 });
        assert.match(reader.takeDigest(), /showed the supplied correction/);
        assert.equal(reader.takeDigest(), null);
        assert.deepEqual(reader.store.readState(), { digest: reader.events.length });
    });

    test("a restarted reader resumes the same record and cursor", async (t) => {
        const vaultInfo = makeVault(t);
        const first = makeReader(t, { vaultInfo });
        first.open("c1");
        await first.start();
        first.recordStudent({ type: "hint_revealed", question: Q1, index: 1 });
        first.takeDigest();
        first.recordStudent({ type: "method_shown", question: Q1 });
        first.dispose();

        const second = makeReader(t, { vaultInfo });
        const front = sink();
        second.addClient(front.res, "c1");
        second.rehydrate("c1");
        second.rehydrate("c1");
        await second.start();
        assert.equal(second.store.folder, first.store.folder);
        assert.deepEqual(second.events.map((e) => e.type), ["canvas_opened", "hint_revealed", "method_shown", "canvas_rehydrated"]);
        assert.deepEqual(second.frontState().hints, { [Q1]: 1 });
        const digest = second.takeDigest();
        assert.doesNotMatch(digest, /revealed hint/);
        assert.match(digest, /opened the method[\s\S]*reconnected to the canvas/);
    });

    test("note and layout changes are journaled once", async (t) => {
        let current = data;
        const reader = makeReader(t, { compile: fakeCompile(() => current) });
        await reader.start();
        current = structuredClone(data);
        current.sources = current.sources.filter((s) => s.id !== "aid-q-1");
        current.sources.find((s) => s.id === "sheet").sha256 = "f".repeat(64);
        await reader.compileNow();
        await reader.compileNow();
        writeFileSync(reader.layout, `${readFileSync(reader.layout, "utf8")}\n`);
        await reader.compileNow();
        const changes = reader.events.filter((e) => e.type === "content_changed");
        assert.deepEqual(changes.map((e) => [e.notes.map((n) => n.id), e.removed, e.layout]),
            [[["sheet"], ["aid-q-1"], false], [[], [], true]]);
        assert.equal(reader.version, 4);
    });

    test("show reaches only the targeted canvas and is journaled as a tutor action", async (t) => {
        const reader = makeReader(t);
        await reader.start();
        const [one, two] = [sink(), sink()];
        reader.addClient(one.res, "c1");
        const remove = reader.addClient(two.res, "c2");
        assert.deepEqual(reader.show("course#^theorem", "c1"), { shown: "course", address: "course#^theorem", delivered: true });
        assert.deepEqual(one.messages, [{ type: "show", kind: "course", address: "course#^theorem" }]);
        assert.deepEqual(two.messages, []);
        remove();
        assert.equal(reader.show("sheet#^ex-2", "c2").delivered, false);
        assert.throws(() => reader.show("nope", "c1"), /Unknown target address/);
        assert.deepEqual(reader.events.map((e) => [e.type, e.actor, e.course ?? e.exercise]),
            [["tutor_show", "tutor", "course#^theorem"], ["tutor_show", "tutor", "sheet#^ex-2"]]);
        const state = reader.agentState({ question: Q1, courses: true });
        assert.deepEqual(state.question.hints, { revealed: 0, total: 2 });
        assert.equal(state.courses.length, 3);
        assert.throws(() => reader.agentState({ question: "x" }), /Unknown question address/);
    });

    test("watches source notes and the layout but not Activity or dot folders", async (t) => {
        const vaultInfo = makeVault(t);
        const compile = fakeCompile(data);
        const reader = makeReader(t, { vaultInfo, compile, watchFiles: true });
        reader.open("c1");
        await reader.start();
        assert.equal(compile.calls.length, 1);
        await new Promise((done) => setTimeout(done, 200));
        writeFileSync(join(vaultInfo.vault, "Activity", "noise.md"), "x");
        writeFileSync(join(vaultInfo.vault, ".obsidian", "workspace.json"), "{}");
        writeFileSync(join(vaultInfo.chapter, "Exercise-sheet", "notes.txt"), "x");
        await new Promise((done) => setTimeout(done, 400));
        assert.equal(compile.calls.length, 1, "unrelated files do not recompile");
        const settle = () => new Promise((done) => setTimeout(done, 400));
        writeFileSync(vaultInfo.sheet, `${readFileSync(vaultInfo.sheet, "utf8")}\nEdited.\n`);
        await until(() => compile.calls.length >= 2);
        await settle();
        const afterNote = compile.calls.length;
        writeFileSync(vaultInfo.layout, readFileSync(vaultInfo.layout, "utf8"));
        await until(() => compile.calls.length > afterNote);
        await settle();
        reader.close("c1");
        assert.equal(reader.watchers.length, 0);
        const closed = compile.calls.length;
        writeFileSync(vaultInfo.sheet, "closed");
        await settle();
        assert.equal(compile.calls.length, closed);
    });
});
