import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync, appendFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, test } from "node:test";
import { pathToFileURL } from "node:url";
import { clock, fixtureData, makeVault, SESSION } from "./helpers.mjs";

const { findVault, isInside, localDate, slugify, writeAtomic } = await import(new URL("../../.github/extensions/clew-canvas/lib/paths.mjs", import.meta.url));
const { indexData, htmlToText, splitAddress } = await import(new URL("../../.github/extensions/clew-canvas/lib/data.mjs", import.meta.url));
const { replay, studentEvent, eventTime, minutes, GAP_CAP_MS } = await import(new URL("../../.github/extensions/clew-canvas/lib/events.mjs", import.meta.url));
const { renderSummary } = await import(new URL("../../.github/extensions/clew-canvas/lib/summary.mjs", import.meta.url));
const { askPrompt, digestText } = await import(new URL("../../.github/extensions/clew-canvas/lib/digest.mjs", import.meta.url));
const { isTutorAgent, targetPaths, vaultWriteDenial } = await import(new URL("../../.github/extensions/clew-canvas/lib/guard.mjs", import.meta.url));
const { compileArgs, compileData, explainFailure, SETUP_COMMAND } = await import(new URL("../../.github/extensions/clew-canvas/lib/compile.mjs", import.meta.url));
const { ActivityStore, readJsonl } = await import(new URL("../../.github/extensions/clew-canvas/lib/activity.mjs", import.meta.url));

const index = indexData(await fixtureData());
const Q1 = "sheet#^q-1";
const at = (minute, extra) => ({ v: 1, ts: new Date(Date.UTC(2026, 10, 1, 10, minute)).toISOString(), ...extra });

describe("paths", () => {
    test("vault discovery, containment, slugs and atomic writes", (t) => {
        const { vault, chapter, layout } = makeVault(t);
        assert.equal(findVault(layout), vault);
        assert.equal(findVault(chapter), vault);
        assert.equal(findVault(join(chapter, "missing.md")), vault);
        assert.equal(findVault(tmpdir()), null);
        assert.ok(isInside(vault, chapter));
        assert.ok(isInside(vault, vault));
        assert.ok(!isInside(chapter, vault));
        assert.ok(!isInside(vault, `${vault}-other`));
        assert.equal(slugify("Suites · Révision : chapitre 1"), "suites-revision-chapitre-1");
        assert.equal(slugify("···"), "publication");
        assert.equal(localDate(new Date(2026, 0, 5, 23, 59)), "2026-01-05");
        const file = join(vault, "x.txt");
        writeAtomic(file, "one");
        writeAtomic(file, "two");
        assert.equal(readFileSync(file, "utf8"), "two");
        assert.deepEqual(readdirSync(vault).filter((name) => name.endsWith(".tmp")), []);
    });
});

describe("data", () => {
    test("index addresses and plain text for the agent", () => {
        assert.equal(index.questions.get(Q1).label, "Question 1");
        assert.equal(index.exerciseOf.get(Q1).address, "sheet#^ex-1");
        assert.equal(index.courses.get("course#^theorem").title, "Geometric limit result");
        assert.deepEqual(splitAddress("sheet#^q-1"), ["sheet", "^q-1"]);
        assert.deepEqual(splitAddress("course"), ["course", ""]);
        assert.equal(htmlToText("<p>a &lt; b &amp; $x^2$</p><p>c&#233;&#x41;</p>"), "a < b & $x^2$\ncéA");
        assert.equal(htmlToText("abcdef", 3), "abc…");
    });
});

describe("events", () => {
    const now = new Date("2026-11-01T10:00:00.000Z");

    test("student events are validated against the publication", () => {
        const hint = studentEvent({ type: "hint_revealed", question: Q1, index: 2 }, index, now);
        assert.deepEqual(hint, { v: 1, ts: now.toISOString(), type: "hint_revealed", actor: "student", question: Q1,
            exercise: "sheet#^ex-1", index: 2, total: 2 });
        assert.equal(studentEvent({ type: "course_opened", course: "course" }, index, now).course, "course");
        for (const [input, message] of [
            [{ type: "tutor_show", question: Q1 }, /Unsupported/],
            [{ type: "method_shown" }, /requires question/],
            [{ type: "exercise_started", question: Q1, exercise: "sheet#^nope" }, /Unknown exercise/],
            [{ type: "course_opened", course: "course#^missing" }, /Unknown course/],
            [{ type: "hint_revealed", question: Q1, index: 3 }, /Invalid hint index/],
            [{ type: "hint_revealed", question: "sheet#^q-2", index: 1 }, /Invalid hint index/],
            [null, /object/],
        ]) assert.throws(() => studentEvent(input, index, now), message);
    });

    test("client timestamps are kept only when plausible", () => {
        assert.equal(eventTime("2026-11-01T09:59:00.000Z", now), "2026-11-01T09:59:00.000Z");
        assert.equal(eventTime("2026-11-01T10:00:30.000Z", now), now.toISOString());
        assert.equal(eventTime("2026-11-01T11:00:00.000Z", now), now.toISOString());
        assert.equal(eventTime("2020-01-01T00:00:00.000Z", now), now.toISOString());
        assert.equal(eventTime("nonsense", now), now.toISOString());
    });

    test("replay derives progress and capped time from gaps", () => {
        const progress = replay([
            at(0, { type: "canvas_opened", actor: "system" }),
            at(1, { type: "exercise_started", actor: "student", exercise: "sheet#^ex-1" }),
            at(3, { type: "hint_revealed", actor: "student", question: Q1, exercise: "sheet#^ex-1", index: 1, total: 2 }),
            at(4, { type: "hint_revealed", actor: "student", question: Q1, exercise: "sheet#^ex-1", index: 2, total: 2 }),
            at(5, { type: "tutor_show", actor: "tutor", course: "course" }),
            at(40, { type: "correction_shown", actor: "student", question: Q1, exercise: "sheet#^ex-1" }),
            at(41, { type: "correction_hidden", actor: "student", question: Q1, exercise: "sheet#^ex-1" }),
            at(42, { type: "canvas_closed", actor: "system" }),
            at(50, { type: "course_opened", actor: "student", course: "course" }),
            at(51, { type: "course_opened", actor: "student", course: "course" }),
            at(52, { type: "pdf_opened", actor: "student", url: "a.pdf", page: 2 }),
            at(53, { type: "tutor_requested", actor: "student", question: "sheet#^q-2", exercise: "sheet#^ex-1" }),
        ]);
        const q1 = progress.questions.get(Q1);
        assert.equal(q1.hints, 2);
        assert.equal(q1.correctionSeen, true);
        assert.equal(q1.correction, false);
        assert.equal(q1.ms, 60_000 + GAP_CAP_MS + 60_000 + 60_000);
        assert.equal(progress.exercises.get("sheet#^ex-1").ms, 2 * 60_000);
        assert.equal(progress.exercises.get("sheet#^ex-1").started, true);
        assert.equal(progress.courses.get("course"), 2);
        assert.equal(progress.links.length, 1);
        assert.equal(progress.tutorShows, 1);
        assert.equal(progress.questions.get("sheet#^q-2").tutor, 1);
        assert.equal(progress.focus.question, "sheet#^q-2");
        assert.equal(minutes(0), "—");
        assert.equal(minutes(59_000), "<1 min");
        assert.equal(minutes(150_000), "~3 min");
    });
});

describe("summary", () => {
    const header = { ts: at(0).ts, session: SESSION, title: "Suites | révision", layout: "Activity/Layouts/suites.json" };

    test("is deterministic, links notes and escapes labels in tables", () => {
        const events = [
            at(1, { type: "hint_revealed", actor: "student", question: Q1, exercise: "sheet#^ex-1", index: 1, total: 2 }),
            at(3, { type: "correction_shown", actor: "student", question: Q1, exercise: "sheet#^ex-1" }),
            at(4, { type: "course_opened", actor: "student", course: "course#^theorem" }),
            at(5, { type: "pdf_opened", actor: "student", url: "Maths/Suites révision/Exercise-sheet/sheet.pdf", page: 2 }),
            at(6, { type: "pdf_opened", actor: "student", url: "Maths/Suites révision/Exercise-sheet/sheet.pdf", page: 2 }),
            at(7, { type: "pdf_opened", actor: "student", url: pathToFileURL(join(tmpdir(), "outside.pdf")).href }),
            at(8, { type: "link_opened", actor: "student", url: "https://example.com/a" }),
        ];
        const text = renderSummary({ header, events, index });
        assert.equal(text, renderSummary({ header, events, index }));
        assert.match(text, /^---\ntype: clew-activity\npublication: "Suites \| révision"\n/);
        assert.match(text, /# Activité · Suites révision\n/);
        assert.match(text, /\| \[\[Maths\/Suites révision\/Exercise-sheet\/sheet#\^q-1\\\|Question 1\]\] \| 1\/2 \| vue \| — \| ~3 min \|/);
        assert.match(text, /- \[\[Maths\/Suites révision\/Course-course\/course#\^theorem\|Geometric limit result\]\] · 1 fois/);
        assert.match(text, /- PDF \[\[Maths\/Suites révision\/Exercise-sheet\/sheet\.pdf#page=2\|sheet\.pdf p\. 2\]\] · 2 fois/);
        assert.match(text, /- <file:\/\/\/.*outside\.pdf>\n/);
        assert.doesNotMatch(text, /\[\[file:/);
        assert.match(text, /- <https:\/\/example\.com\/a>/);
        assert.match(text, /- 1 notes d'aide\n$/);
        assert.doesNotMatch(text, /\r/);
    });

    test("states when nothing has been done", () => {
        const text = renderSummary({ header, events: [], index });
        assert.match(text, /_Aucun exercice commencé._/);
        assert.match(text, /_Aucun passage de cours ouvert._/);
        assert.match(text, /_Aucun lien ouvert._/);
        assert.match(text, /started: "2026-11-01T10:00:00.000Z"/);
    });
});

describe("digest", () => {
    test("skips tutor actions, bounds length and names the canvas", () => {
        const events = Array.from({ length: 35 }, (_, n) =>
            at(n, { type: "method_shown", actor: "student", question: Q1, exercise: "sheet#^ex-1" }));
        assert.equal(digestText({ title: "T", instances: [], events: [at(1, { type: "tutor_show", actor: "tutor" })], index }), null);
        const text = digestText({ title: "T", instances: ["c1"], events, index });
        assert.match(text, /^Clew canvas activity since the previous message \(publication "T", canvas instance "c1"\):/);
        assert.match(text, /\(5 earlier events omitted\)/);
        assert.match(text, /10:34:00Z Student opened the method for Question 1 of Exercise 1 \[sheet#\^q-1\]\./);
        assert.match(digestText({ title: "T", instances: [], events, index }), /canvas instance closed/);
    });

    test("tutor request carries progress but never hint, explanation or correction content", () => {
        const question = index.questions.get(Q1);
        const prompt = askPrompt({ title: "T", instance: "c1", question, exercise: index.exerciseOf.get(Q1),
            state: { hints: 1, correctionSeen: false, explanations: 0, tutor: 2, ms: 120_000 }, recent: "RECENT" });
        assert.match(prompt, /pressed "Ask the tutor" on Question 1 of Exercise 1 \[sheet#\^q-1\]/);
        assert.match(prompt, /hints revealed 1\/2; supplied correction not viewed; method not available/);
        assert.match(prompt, /Determine its limit\./);
        assert.match(prompt, /RECENT/);
        assert.match(prompt, /do not give the answer/);
        for (const secret of ["Compare", "Apply", "the limit is", "Another supplied argument", "ratio has absolute value"]) {
            assert.ok(!prompt.includes(secret), `prompt leaks "${secret}"`);
        }
    });
});

describe("guard", () => {
    test("denies vault writes except publication layouts", (t) => {
        const { vault, sheet, root } = makeVault(t);
        const deny = (toolName, toolArgs, cwd = root) => vaultWriteDenial({ toolName, toolArgs, cwd });
        assert.match(deny("edit", { path: sheet }), /"Maths\/Suites révision\/Exercise-sheet\/sheet\.md" is inside the Obsidian vault/);
        assert.match(deny("create", { path: join(vault, "Activity", "x", "summary.md") }), /read-only/);
        assert.match(deny("create", { path: "Vault/Activity/Layouts/nested/x.json" }), /read-only/);
        assert.equal(deny("create", { path: join(vault, "Activity", "Layouts", "new.json") }), null);
        assert.equal(deny("create", { path: "Activity/Layouts/new.json" }, vault), null);
        assert.equal(deny("create", { path: join(root, "outside.md") }), null);
        assert.equal(deny("view", { path: sheet }), null);
        assert.equal(deny("send_session_message", { message: `edit ${sheet}` }), null);
        assert.match(deny("apply_patch", { input: `*** Begin Patch\n*** Update File: ${sheet}\n@@\n-a\n+b\n*** End Patch` }), /read-only/);
        assert.match(deny("move_file", { source: join(root, "a.md"), destination: join(vault, "a.md") }), /"a\.md"/);
        assert.deepEqual(targetPaths({ paths: ["a", 1, ""], files: ["b"], message: "c" }), ["a", "b"]);
    });

    test("recognises the tutor agent names", () => {
        for (const name of ["clew-tutor", "Clew Tutor", " clew_tutor "]) assert.ok(isTutorAgent(name), name);
        for (const name of ["clew", "tutor", "clew-tutor-2", undefined]) assert.ok(!isTutorAgent(name), String(name));
    });
});

describe("compile", () => {
    test("runs the locked clew-generate data mode and explains failures", async () => {
        const args = compileArgs({ repoRoot: "R", layout: "L.json", target: "T.json", base: "V" });
        assert.deepEqual(args.slice(0, 7), ["run", "--package", "clew-generate", "--locked", "--no-sync", "python", "-B"]);
        assert.deepEqual(args.slice(-5), ["L.json", "--data", "T.json", "--base", "V"]);
        assert.match(args[7], /clew-generate[\\/]scripts[\\/]generate_html\.py$/);
        assert.match(explainFailure({ code: "ENOENT" }), new RegExp(SETUP_COMMAND));
        assert.equal(explainFailure({ code: 1 }, "trace\nGenerate error: Missing note: x\n"), "Missing note: x");
        assert.match(explainFailure({ code: 1 }, "ModuleNotFoundError: No module named 'yaml'"), /uv sync --all-packages --locked/);
        assert.equal(explainFailure({ killed: true }, ""), "Compilation timed out.");
        const run = (result) => (command, argv, options, done) => {
            assert.equal(command, "uv");
            assert.equal(options.env.PYTHONIOENCODING, "utf-8");
            done(...result);
        };
        assert.deepEqual(await compileData({ repoRoot: "R" }, run([null, '{"status":"data"}', ""])), { ok: true, report: { status: "data" } });
        assert.match((await compileData({ repoRoot: "R" }, run([null, "oops", ""]))).error, /Unexpected compiler output/);
        assert.deepEqual(await compileData({ repoRoot: "R" }, run([{ code: 1 }, "", "Generate error: bad"])), { ok: false, error: "bad" });
    });
});

describe("activity store", () => {
    test("creates, locates and reopens one folder per session and layout", async (t) => {
        const { vault, layout } = makeVault(t);
        const data = await fixtureData();
        const now = clock("2026-11-01T12:00:00.000Z");
        const store = new ActivityStore({ vault, layout, session: SESSION, now });
        assert.equal(store.locate(), null);
        const first = store.open(data);
        assert.equal(store.folder, join(vault, "Activity", "2026-11-01-suites-revision-01234567"));
        assert.equal(first.header.layout, "Activity/Layouts/suites.json");
        assert.deepEqual(first.header.notes.map((n) => n.id), data.sources.map((s) => s.id));
        assert.deepEqual(first.events, []);
        store.append(at(1, { type: "method_shown", actor: "student", question: Q1 }));
        appendFileSync(store.journal, '{"v":1,"type":"hint_rev');
        now.set("2026-11-03T12:00:00.000Z");
        const again = new ActivityStore({ vault, layout, session: SESSION, now });
        const reopened = again.open({ ...data, title: "Renamed" });
        assert.equal(again.folder, store.folder);
        assert.equal(reopened.events.length, 1);
        again.append(at(2, { type: "method_shown", actor: "student", question: Q1 }));
        assert.equal(readJsonl(again.journal).length, 3);
        assert.match(readFileSync(again.journal, "utf8"), /"type":"hint_rev\n\{/);

        const other = join(vault, "Activity", "Layouts", "other.json");
        writeFileSync(other, readFileSync(layout));
        const second = new ActivityStore({ vault, layout: other, session: SESSION, now: clock("2026-11-01T12:00:00.000Z") });
        second.open(data);
        assert.equal(second.folder, `${store.folder}-2`);
        const otherSession = new ActivityStore({ vault, layout, session: "fedcba9876543210", now });
        otherSession.open(data);
        assert.notEqual(otherSession.folder, store.folder);
    });

    test("snapshots the layout, keeps state and rewrites the summary only on change", async (t) => {
        const { vault, layout } = makeVault(t);
        const store = new ActivityStore({ vault, layout, session: SESSION });
        store.open(await fixtureData());
        assert.equal(store.snapshotLayout("{}"), false);
        assert.equal(store.snapshotLayout("{}"), false);
        assert.equal(store.snapshotLayout('{"a":1}'), true);
        assert.equal(readFileSync(join(store.internal, "layout.json"), "utf8"), '{"a":1}');
        assert.deepEqual(store.readState(), {});
        store.writeState({ digest: 3 });
        assert.deepEqual(store.readState(), { digest: 3 });
        assert.equal(store.writeSummary("x"), true);
        assert.equal(store.writeSummary("x"), false);
    });

    test("refuses a journal without header", (t) => {
        const root = mkdtempSync(join(tmpdir(), "clew-canvas-store-"));
        t.after(() => rmSync(root, { recursive: true, force: true }));
        mkdirSync(join(root, ".obsidian"));
        const store = new ActivityStore({ vault: root, layout: join(root, "l.json"), session: SESSION });
        store.folder = join(root, "Activity", "f");
        mkdirSync(store.folder, { recursive: true });
        writeFileSync(store.journal, '{"type":"method_shown","ts":"x"}\n');
        assert.throws(() => store.load(), /no header/);
    });
});
