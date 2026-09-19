import assert from "node:assert/strict";
import { mkdir, readFile, realpath, symlink, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { CourseReader, MAX_EXCERPT_CHARACTERS, MAX_NOTE_BYTES, parseNote, resolveCourse } from "../reader.mjs";
import { renderMarkdown } from "../renderer.mjs";
import { fixture } from "./fixtures.mjs";

test("parse top-level YAML navigation without leaking unrelated metadata", () => {
    const parsed = parseNote("\uFEFF---\r\ntitle: Welcome\r\nprevious: null\r\nnext: '[[Next|Go]]'\r\nprivate: hidden\r\n---\r\n# Hello");
    assert.deepEqual(parsed, { title: "Welcome", previous: null, next: "[[Next|Go]]", body: "# Hello" });
    assert.equal(parseNote("# Plain Markdown").title, null);
    assert.equal(parseNote("---\n---\nBody").body, "Body");
});

test("invalid, ambiguous, aliased and non-scalar frontmatter is reported", () => {
    for (const source of [
        "---\nnext: foo",
        "---\nnext: [one, two]\n---\nBody",
        "---\nnext: 23\n---\nBody",
        "---\nnext: one\nnext: two\n---\nBody",
        "---\n- next\n---\nBody",
        "---\na: &alias hello\nnext: *alias\n---\nBody",
        "---\nnext: !unknown value\n---\nBody",
    ]) {
        assert.throws(() => parseNote(source), { code: "invalid_frontmatter" });
    }
});

test("render headings, code, tables and local links without executing course HTML", () => {
    const { html, headings } = renderMarkdown([
        "# Hello", "# Hello", "",
        "| A | B |", "| --- | --- |", "| one | two |", "",
        "```js", "<script>alert(1)</script>", "```", "",
        "[[next|Continue]] [Local](chapter.md) [Web](https://example.org)",
        '<img src=x onerror="alert(1)">',
        "[Unsafe](javascript:alert(1))",
        "![Remote](https://example.org/tracker.png)",
        "![Local](picture.png)",
    ].join("\n"), "hub.md");
    assert.deepEqual(headings.map((heading) => heading.id), ["hello", "hello-1"]);
    assert.match(html, /<table>/);
    assert.match(html, /&lt;script&gt;/);
    assert.doesNotMatch(html, /<script>|<img src=x|href="javascript:/);
    assert.match(html, /data-reader-kind="wikilink"/);
    assert.match(html, /data-reader-reference="chapter.md"/);
    assert.match(html, /rel="noopener noreferrer"/);
    assert.match(html, /remote images are not loaded/);
    assert.doesNotMatch(html, /<img[^>]*src="https:/);
    assert.match(html, /src="asset\?document=hub.md/);
});

test("KaTeX renders dollar, bracket and fenced math as HTML plus accessible MathML", () => {
    for (const source of [
        String.raw`Inline $E=mc^2$`,
        String.raw`Inline \(a^2+b^2=c^2\)`,
        "$$\n\\frac{1}{2}\n$$",
        "\\[\n\\int_0^1 x^2\\,dx\n\\]",
        "```math\n\\sum_{n=1}^{N}n\n```",
    ]) {
        const { html } = renderMarkdown(source, "math.md");
        assert.match(html, /class="katex"/);
        assert.match(html, /<math /);
        assert.match(html, /class="katex-html"/);
        assert.doesNotMatch(html, /katex-error/);
    }
    assert.match(renderMarkdown("$$x^2$$", "math.md").html, /katex-display/);
    const literal = renderMarkdown("`$x$`\n\n```text\n$$not math$$\n```\n\nA price of $5.", "math.md").html;
    assert.doesNotMatch(literal, /class="katex"/);
    assert.match(literal, /\$5/);
});

test("math failures remain readable, dangerous commands stay untrusted, and macros are page-local", (t) => {
    t.mock.method(console, "error", () => {});
    assert.match(renderMarkdown(String.raw`$\notarealcommand{x}$`, "bad.md").html, /katex-error/);
    assert.match(renderMarkdown(String.raw`$\def\loop{\loop}\loop$`, "bad.md").html, /katex-error/);
    const unsafe = renderMarkdown(String.raw`$\href{javascript:alert(1)}{click}$ $\includegraphics{https://example.org/tracker.png}$`, "bad.md").html;
    assert.doesNotMatch(unsafe, /href="javascript:|<img[^>]*src="https:/);
    assert.doesNotMatch(renderMarkdown(String.raw`$\gdef\coursedef{xyz}\coursedef$`, "one.md").html, /katex-error/);
    assert.match(renderMarkdown(String.raw`$\coursedef$`, "two.md").html, /katex-error/);
});

test("navigate both ways through paths and wikilinks without staging attachments", async (t) => {
    const { reader, attachments } = await fixture(t);
    assert.equal(reader.snapshot().previous, null);
    await assert.rejects(reader.navigate({ direction: "previous" }), { code: "end_of_course" });
    await reader.navigate({ direction: "next", expectedRevision: 1 });
    assert.equal(reader.snapshot().path, "lessons/one.md");
    assert.equal(reader.snapshot().previous.label, "Home");
    await reader.navigate({ direction: "next" });
    assert.equal(reader.snapshot().path, "two.md");
    assert.equal(reader.snapshot().next, null);
    await reader.navigate({ direction: "previous" });
    await reader.navigate({ direction: "previous" });
    await reader.refresh();
    assert.equal(reader.snapshot().path, "hub.md");
    assert.equal(attachments.length, 0);
});

test("link aliases, headings, extensions and source-relative paths work", async (t) => {
    const { reader } = await fixture(t);
    await reader.follow({ reference: "[[two#A heading|Read on]]", kind: "wikilink" });
    assert.equal(reader.snapshot().anchor, "a-heading");
    await reader.openPage({ path: "lessons/one" });
    await reader.follow({ reference: "../hub.md", kind: "path" });
    assert.equal(reader.snapshot().path, "hub.md");
    await assert.rejects(reader.follow({ reference: "[[two#Missing]]", kind: "wikilink" }), { code: "heading_not_found" });
    await assert.rejects(reader.follow({ reference: "[[two#^block]]", kind: "wikilink" }), { code: "unsupported_link" });
    assert.equal(reader.snapshot().path, "hub.md");
});

test("missing and ambiguous navigation targets remain visible as disabled links", async (t) => {
    const { reader, courseRoot } = await fixture(t);
    await writeFile(path.join(courseRoot, "lessons", "two.md"), "# Duplicate");
    await reader.openPage({ path: "lessons/one.md" });
    assert.equal(reader.snapshot().next.available, false);
    assert.match(reader.snapshot().next.error, /More than one/);
    await assert.rejects(reader.navigate({ direction: "next" }), { code: "ambiguous_link" });
    await writeFile(path.join(courseRoot, "missing.md"), "---\nnext: does-not-exist.md\n---\n# Still readable");
    await reader.openPage({ path: "missing.md" });
    assert.match(reader.snapshot().html, /Still readable/);
    assert.equal(reader.snapshot().next.available, false);
    await assert.rejects(reader.navigate({ direction: "next" }), { code: "not_found" });
    assert.equal(reader.snapshot().path, "missing.md");
});

test("reject vault-wide, private, absolute and traversal roots or note references", async (t) => {
    const { reader, vaultPath } = await fixture(t);
    await mkdir(path.join(vaultPath, "model"));
    await writeFile(path.join(vaultPath, "model", "private.md"), "# Synthetic private record");
    for (const coursePath of [".", "..", "model", "courses/../model"]) {
        await assert.rejects(resolveCourse({ vaultPath, coursePath }));
    }
    await assert.rejects(resolveCourse({ vaultPath: ".", coursePath: "courses/demo" }), { code: "invalid_input" });
    for (const reference of ["../../model/private.md", "..\\..\\model\\private.md", "/etc/passwd", "C:\\secret.md", "file:///secret.md", "%2e%2e/%2e%2e/model/private.md"]) {
        await assert.rejects(reader.follow({ reference, kind: "path" }), { code: "outside_course" });
    }
    assert.equal(reader.snapshot().path, "hub.md");
});

test("canonical containment rejects directory symlinks escaping the course", async (t) => {
    const { reader, courseRoot, vaultPath } = await fixture(t);
    const external = path.join(vaultPath, "outside");
    await mkdir(external);
    await writeFile(path.join(external, "secret.md"), "# Synthetic outside note");
    await symlink(external, path.join(courseRoot, "escape"), process.platform === "win32" ? "junction" : "dir");
    await assert.rejects(reader.openPage({ path: "escape/secret.md" }), { code: "outside_course" });
});

test("reading position survives a new reader and stores no reading history or content", async (t) => {
    const { reader, options } = await fixture(t);
    await reader.openPage({ path: "two.md" });
    const bookmark = JSON.parse(await readFile(reader.stateFile, "utf8"));
    assert.deepEqual(bookmark, { version: 1, path: "two.md" });
    const replacement = new CourseReader(options);
    await replacement.initialize("hub.md");
    assert.equal(replacement.snapshot().path, "two.md");
    await writeFile(reader.stateFile, "{broken");
    await assert.rejects(new CourseReader(options).initialize(), { code: "invalid_bookmark" });
});

test("serialized mutations reject stale views rather than skipping two pages", async (t) => {
    const { reader } = await fixture(t);
    const first = reader.navigate({ direction: "next", expectedRevision: 1 });
    const second = reader.navigate({ direction: "next", expectedRevision: 1 });
    await first;
    await assert.rejects(second, { code: "stale_view" });
    assert.equal(reader.snapshot().path, "lessons/one.md");
    await reader.navigate({ direction: "next", expectedRevision: 2 });
    assert.equal(reader.snapshot().path, "two.md");
});

test("refresh replaces rendered text; malformed edits and oversized files retain the last page", async (t) => {
    const { reader, courseRoot } = await fixture(t);
    await writeFile(path.join(courseRoot, "hub.md"), "# Updated\n\nAuthoritative revision.");
    await reader.refresh({ expectedRevision: 1 });
    assert.match(reader.snapshot().html, /Authoritative revision/);
    assert.equal(reader.snapshot({ forAgent: true }).html, undefined);
    await writeFile(path.join(courseRoot, "hub.md"), "---\nnext: [broken]\n---");
    await assert.rejects(reader.refresh(), { code: "invalid_frontmatter" });
    assert.equal(reader.snapshot().title, "Updated");
    await writeFile(path.join(courseRoot, "huge.md"), "x".repeat(MAX_NOTE_BYTES + 1));
    await assert.rejects(reader.openPage({ path: "huge.md" }), { code: "file_too_large" });
});

test("only explicit selection staging attaches the entire passage; retries deduplicate", async (t) => {
    const { reader, courseRoot, attachments, stageAttachment } = await fixture(t);
    const selection = "  " + "\u{1F9F5}".repeat(MAX_EXCERPT_CHARACTERS + 1) + "\ncomplete selection  ";
    const body = "# Public course\n\n" + selection;
    await writeFile(path.join(courseRoot, "hub.md"), "---\nprivate: never-send-this\n---\n" + body);
    await reader.refresh();
    const preview = reader.snapshot().excerpt;
    assert.equal([...preview.text].length, MAX_EXCERPT_CHARACTERS);
    assert.equal(preview.totalCharacters, [...body].length);
    assert.equal(preview.truncated, true);
    const input = { text: selection, expectedRevision: reader.revision, requestId: "intent-1" };
    const result = await reader.attachSelection(input, stageAttachment);
    assert.deepEqual(result, { staged: true, path: "hub.md" });
    assert.deepEqual(await reader.attachSelection(input, stageAttachment), result);
    assert.equal(attachments.length, 1);
    assert.deepEqual(attachments[0], {
        type: "extension_context",
        title: "Course excerpt: Public course",
        payload: {
            course: "courses/demo", path: "hub.md",
            filePath: await realpath(path.join(courseRoot, "hub.md")), heading: null, text: selection,
        },
    });
    assert.doesNotMatch(JSON.stringify(attachments[0]), /never-send-this/);
    await assert.rejects(reader.attachSelection({ ...input, text: "Different selection" }, stageAttachment), { code: "invalid_request_id" });
});

test("excerpt references identify the actual file and a verified heading without attaching the file", async (t) => {
    const { reader, courseRoot, attachments, stageAttachment } = await fixture(t);
    await reader.openPage({ path: "two.md" });
    const input = { text: "The end.", headingId: "a-heading", expectedRevision: reader.revision, requestId: "source-reference" };
    await reader.attachSelection(input, stageAttachment);
    assert.equal(attachments.length, 1);
    assert.equal(attachments[0].type, "extension_context");
    assert.equal(attachments[0].payload.filePath, await realpath(path.join(courseRoot, "two.md")));
    assert.deepEqual(attachments[0].payload.heading, { id: "a-heading", text: "A heading" });
    assert.equal(attachments[0].payload.text, "The end.");
    await assert.rejects(reader.attachSelection({ ...input, requestId: "unknown-heading", headingId: "not-in-this-note" }, stageAttachment),
        { code: "invalid_heading" });
    await assert.rejects(reader.attachSelection({ ...input, headingId: "second-lesson" }, stageAttachment),
        { code: "invalid_request_id" });
    assert.equal(attachments.length, 1);
});

test("source changes and host rejections do not fabricate success or poison retries", async (t) => {
    let calls = 0;
    const { reader, courseRoot, stageAttachment } = await fixture(t, { stageAttachment: async () => {
        calls += 1;
        if (calls === 1) throw new Error("Host attachment limit reached");
    } });
    const input = { text: "Start here.", expectedRevision: 1, requestId: "retry-1" };
    await assert.rejects(reader.attachSelection(input, stageAttachment), {
        code: "composer_rejected", message: "The host could not add the passage to the composer: Host attachment limit reached",
    });
    assert.equal((await reader.attachSelection(input, stageAttachment)).staged, true);
    await writeFile(path.join(courseRoot, "hub.md"), "# Changed after selection");
    await assert.rejects(reader.attachSelection({ ...input, requestId: "new-intent" }, stageAttachment), { code: "content_changed" });
    assert.equal(calls, 2);
});

test("invalid or stale selections and absent composer support cannot stage anything", async (t) => {
    const { reader, stageAttachment, attachments } = await fixture(t);
    const input = { text: "Start here.", expectedRevision: 1, requestId: "selection" };
    assert.throws(() => reader.attachSelection(input), { code: "composer_unavailable" });
    assert.throws(() => reader.attachSelection({ ...input, text: "  " }, stageAttachment), { code: "empty_selection" });
    await reader.navigate({ direction: "next" });
    await assert.rejects(reader.attachSelection(input, stageAttachment), { code: "stale_view" });
    assert.equal(attachments.length, 0);
});

test("local raster assets are bounded and no other files are served as images", async (t) => {
    const { reader, courseRoot } = await fixture(t);
    await writeFile(path.join(courseRoot, "picture.png"), Buffer.from([137, 80, 78, 71]));
    const image = await reader.readAsset("hub.md", "picture.png");
    assert.equal(image.contentType, "image/png");
    assert.equal(image.data.length, 4);
    await assert.rejects(reader.readAsset("hub.md", "two.md"), { code: "unsupported_image" });
    await assert.rejects(reader.readAsset("hub.md", "https://example.org/image.png"), { code: "outside_course" });
});
