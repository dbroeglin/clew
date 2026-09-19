import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { startReaderServer } from "../server.mjs";
import { fixture } from "./fixtures.mjs";

async function serverFixture(t) {
    const fixtureData = await fixture(t);
    const server = await startReaderServer(fixtureData.reader, { stageAttachment: fixtureData.stageAttachment });
    t.after(() => server.close());
    const post = (resource, input, headers = {}) => fetch(`${server.url}${resource}`, {
        method: "POST",
        headers: { Origin: new URL(server.url).origin, "Content-Type": "application/json", ...headers },
        body: typeof input === "string" ? input : JSON.stringify(input),
    });
    return { ...fixtureData, server, post };
}

test("serve a nonce-protected reader and state only behind the per-panel URL", async (t) => {
    const { server } = await serverFixture(t);
    const response = await fetch(server.url);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("referrer-policy"), "no-referrer");
    assert.match(response.headers.get("content-security-policy"), /default-src 'none'/);
    const html = await response.text();
    assert.match(html, /nonce="/);
    assert.doesNotMatch(html, /__CSP_NONCE__/);
    const state = await (await fetch(`${server.url}api/state`)).json();
    assert.equal(state.path, "hub.md");
    assert.equal(state.canAskInChat, true);
    assert.match(state.html, /Course home/);
    assert.equal((await fetch(`${new URL(server.url).origin}/api/state`)).status, 403);
    assert.equal((await fetch(`${server.url}../reader.mjs`)).status, 403);
    assert.equal((await fetch(`${server.url}reader.mjs`)).status, 404);
});

test("KaTeX CSS and fonts are served locally through the authorized reader URL", async (t) => {
    const { server } = await serverFixture(t);
    const css = await fetch(`${server.url}katex/katex.min.css`);
    assert.equal(css.status, 200);
    assert.match(css.headers.get("content-type"), /text\/css/);
    assert.match(await css.text(), /fonts\/KaTeX_Main-Regular\.woff2/);
    const font = await fetch(`${server.url}katex/fonts/KaTeX_Main-Regular.woff2`);
    assert.equal(font.status, 200);
    assert.equal(font.headers.get("content-type"), "font/woff2");
    assert.ok((await font.arrayBuffer()).byteLength > 1000);
    assert.match(font.headers.get("content-security-policy"), /font-src 'self'/);
    assert.equal((await fetch(`${server.url}katex/package.json`)).status, 404);
    assert.equal((await fetch(`${server.url}katex/fonts/KaTeX_Missing.woff2`)).status, 404);
});

test("HTTP commands share controller behavior and validate origin, shape and size", async (t) => {
    const { post, reader, attachments } = await serverFixture(t);
    assert.equal((await post("api/navigate", { direction: "next", expectedRevision: 1 }, { Origin: "https://example.org" })).status, 403);
    assert.equal((await post("api/navigate", { direction: "next" })).status, 400);
    assert.equal((await post("api/navigate", { direction: "next", expectedRevision: 1, surprise: true })).status, 400);
    assert.equal((await post("api/refresh", "{broken")).status, 400);
    assert.equal((await post("api/refresh", JSON.stringify({ expectedRevision: 1, large: "x".repeat(17000) }))).status, 413);
    const response = await post("api/navigate", { direction: "next", expectedRevision: 1 });
    assert.equal(response.status, 200);
    assert.equal((await response.json()).path, "lessons/one.md");
    assert.equal(reader.snapshot().path, "lessons/one.md");
    const stale = await post("api/navigate", { direction: "next", expectedRevision: 1 });
    assert.equal(stale.status, 409);
    assert.equal((await stale.json()).error.code, "stale_view");
    assert.equal(attachments.length, 0);
    assert.equal((await post("api/discuss", { expectedRevision: 2, requestId: "old-flow" })).status, 404);
    const staged = await post("api/attach", { text: "Some grounded text.", expectedRevision: 2, requestId: "http-intent-1" });
    assert.equal(staged.status, 200);
    assert.deepEqual(await staged.json(), { staged: true, path: "lessons/one.md" });
    assert.equal(attachments.length, 1);
});

test("full UTF-8 selections exceed the old excerpt and transport caps without truncation", async (t) => {
    const { reader, post, courseRoot, attachments } = await serverFixture(t);
    const text = "\u{1F9F5}".repeat(14000);
    await writeFile(path.join(courseRoot, "hub.md"), "# Whole selection\n\n" + text);
    await reader.refresh();
    const response = await post("api/attach", { text, expectedRevision: reader.revision, requestId: "full-selection" });
    assert.equal(response.status, 200);
    assert.equal(attachments[0].payload.text, text);
    assert.equal(reader.snapshot().excerpt.truncated, true);
});

test("unsupported hosts do not advertise or fabricate composer handoff", async (t) => {
    const { reader, attachments } = await fixture(t);
    const server = await startReaderServer(reader);
    t.after(() => server.close());
    const state = await (await fetch(`${server.url}api/state`)).json();
    assert.equal(state.canAskInChat, false);
    const response = await fetch(`${server.url}api/attach`, {
        method: "POST",
        headers: { Origin: new URL(server.url).origin, "Content-Type": "application/json" },
        body: JSON.stringify({ text: "Start here.", expectedRevision: 1, requestId: "unsupported" }),
    });
    assert.equal(response.status, 503);
    assert.equal((await response.json()).error.code, "composer_unavailable");
    assert.equal(attachments.length, 0);
});

test("session-side mutations push the same state to every browser instance over SSE", async (t) => {
    const { reader, server } = await serverFixture(t);
    const another = await startReaderServer(reader);
    t.after(() => another.close());
    const abort = new AbortController();
    t.after(() => abort.abort());
    const streams = await Promise.all([server, another].map(async (entry) => {
        const response = await fetch(`${entry.url}events`, { signal: abort.signal });
        const stream = response.body.getReader();
        assert.match(new TextDecoder().decode((await stream.read()).value), /"path":"hub.md"/);
        return stream;
    }));
    await reader.navigate({ direction: "next" });
    for (const stream of streams) {
        const event = new TextDecoder().decode((await stream.read()).value);
        assert.match(event, /event: state/);
        assert.match(event, /"path":"lessons\/one.md"/);
    }
    abort.abort();
});
