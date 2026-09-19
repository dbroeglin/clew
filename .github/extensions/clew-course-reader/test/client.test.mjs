import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { webcrypto } from "node:crypto";
import test from "node:test";
import vm from "node:vm";

const source = await readFile(new URL("../reader-client.js", import.meta.url), "utf8");
const html = await readFile(new URL("../reader.html", import.meta.url), "utf8");
const css = await readFile(new URL("../reader.css", import.meta.url), "utf8");
const settle = () => new Promise((resolve) => setImmediate(resolve));

function page(revision = 1, overrides = {}) {
  const text = "# Welcome\n\nRead this course text.\n";
  return {
    course: "courses/reader-tour", path: "01-start.md", title: "Welcome", revision,
    html: '<h1 id="welcome">Welcome</h1><p>Read this course text.</p><h2 id="practice">Practice</h2>',
    anchor: null,
    headings: [{ id: "welcome", text: "Welcome", level: 1 }, { id: "practice", text: "Practice", level: 2 }],
    previous: null,
    next: { reference: "02-next.md", path: "02-next.md", label: "Next idea", available: true, error: null },
    canAskInChat: true,
    excerpt: { text, truncated: false, totalCharacters: text.length },
    ...overrides,
  };
}

// A deliberately small DOM/transport double exercises the real browser entry point,
// without adding a frontend runtime or a test dependency to the extension.
function harness({ hostTheme, reducedMotion = false } = {}) {
  const calls = [];
  const streams = [];
  const observers = [];
  const focus = [];
  const scrolls = [];
  const order = [];
  const nodes = new Map();
  const document = {};

  class Element {
    constructor(tagName = "div", id = "") {
      this.tagName = tagName.toUpperCase();
      this.nodeType = 1;
      this.id = id;
      this.dataset = {};
      this.style = {};
      this.attributes = new Map();
      this.children = [];
      this.listeners = new Map();
      this.hidden = false;
      this.disabled = false;
      this.open = false;
      this.complete = false;
      this.naturalWidth = 0;
      this.alt = "";
      this._text = "";
    }
    get textContent() { return this._text + this.children.map((node) => node.textContent).join(""); }
    set textContent(text) { this._text = String(text); this.replaceChildren(); }
    get childElementCount() { return this.children.length; }
    get childNodes() { return this.children; }
    get innerHTML() { return this._html || ""; }
    set innerHTML(value) {
      this._html = value;
      this._text = "";
      this.replaceChildren();
      for (const match of value.matchAll(/<(h[1-6]|img)\b([^>]*)>([^<]*)/g)) {
        const node = new Element(match[1]);
        for (const attribute of match[2].matchAll(/([\w-]+)="([^"]*)"/g)) node.setAttribute(attribute[1], attribute[2]);
        node.textContent = match[1] === "img" ? "" : match[3];
        this.append(node);
      }
    }
    setAttribute(name, value) {
      this.attributes.set(name, String(value));
      if (name === "id" || name === "alt") this[name] = String(value);
      if (name.startsWith("data-")) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = String(value);
    }
    getAttribute(name) { return this.attributes.get(name) ?? null; }
    hasAttribute(name) { return this.attributes.has(name); }
    set href(value) { this.setAttribute("href", value); }
    get href() { return this.getAttribute("href"); }
    append(...children) {
      for (const child of children) { child.parent = this; this.children.push(child); }
    }
    replaceChildren(...children) {
      for (const child of this.children) child.parent = null;
      this.children = [];
      this.append(...children);
    }
    replaceWith(node) {
      const index = this.parent.children.indexOf(this);
      this.parent.children.splice(index, 1, node);
      node.parent = this.parent;
      this.parent = null;
    }
    contains(node) { return this === node || this.children.some((child) => child.contains(node)); }
    compareDocumentPosition(node) {
      let root = this;
      while (root.parent) root = root.parent;
      const ordered = [root, ...root.querySelectorAll("*")];
      const difference = ordered.indexOf(node) - ordered.indexOf(this);
      return difference === 0 ? 0 : difference > 0 ? 4 : 2;
    }
    querySelectorAll(selector) {
      const descendants = this.children.flatMap((child) => [child, ...child.querySelectorAll("*")]);
      return descendants.filter((node) => selector === "*" || (selector === "[id]" ? node.id : node.tagName.toLowerCase() === selector));
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    closest(selector) { return this.tagName.toLowerCase() === selector ? this : this.parent?.closest(selector) || null; }
    addEventListener(type, callback) {
      const listeners = this.listeners.get(type) || [];
      listeners.push(callback);
      this.listeners.set(type, listeners);
    }
    emit(type, extra = {}) {
      const event = { target: this, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...extra };
      for (const callback of this.listeners.get(type) || []) callback(event);
      return event;
    }
    click() { if (!this.disabled && !this.hidden) this.emit("click"); }
    focus() { document.activeElement = this; focus.push(this.id); this.emit("focus"); }
    scrollIntoView(options) { scrolls.push({ target: this.id, ...options }); }
    getBoundingClientRect() { return { width: 128, height: 36 }; }
  }

  document.body = new Element("body");
  document.documentElement = new Element("html");
  document.activeElement = document.body;
  document.createElement = (tag) => new Element(tag);
  document.getElementById = (id) => nodes.get(id);
  const documentEvents = new Element("document");
  document.addEventListener = documentEvents.addEventListener.bind(documentEvents);
  document.emit = documentEvents.emit.bind(documentEvents);
  if (hostTheme) document.documentElement.setAttribute("data-color-mode", hostTheme);
  for (const match of html.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
    const node = new Element(match[1], match[3]);
    node.hidden = /\bhidden\b/.test(match[2]);
    node.disabled = /\bdisabled\b/.test(match[2]);
    nodes.set(node.id, node);
  }

  class EventSource extends Element {
    static OPEN = 1;
    static CLOSED = 2;
    constructor(url) {
      super();
      this.url = url;
      this.readyState = 0;
      streams.push(this);
      order.push("events");
    }
    push(type, data) { this.emit(type, { data: JSON.stringify(data) }); }
    close() { this.readyState = EventSource.CLOSED; }
  }

  const window = new Element("window");
  window.location = { search: "?scoutTheme=light" };
  window.innerWidth = 800;
  window.innerHeight = 600;
  window.scrollY = 120;
  window.scrollX = 0;
  window.scrollTo = (options) => scrolls.push({ ...options });
  window.requestAnimationFrame = (callback) => queueMicrotask(callback);
  window.matchMedia = (query) => ({
    matches: query.includes("reduced-motion") ? reducedMotion : false,
    addEventListener() {},
  });
  let ranges = [];
  const selection = {
    get rangeCount() { return ranges.length; },
    get isCollapsed() { return !ranges.length; },
    toString: () => ranges.map((range) => range.text).join(""),
    getRangeAt: (index) => ranges[index],
    removeAllRanges() { ranges = []; queueMicrotask(() => document.emit("selectionchange")); },
    addRange(range) { ranges.push(range); queueMicrotask(() => document.emit("selectionchange")); },
  };
  window.getSelection = () => selection;
  const select = (text, {
    node = nodes.get("page-content").querySelector("h1"), endNode = node, startOffset = 0,
    rect = { left: 20, right: 200, top: 50, bottom: 70, width: 180, height: 20 },
  } = {}) => {
    ranges = text ? [{
      text, startContainer: node, endContainer: endNode, startOffset, endOffset: startOffset + text.length,
      cloneRange() { return { ...this }; },
      getClientRects: () => [rect],
    }] : [];
    document.emit("selectionchange");
  };
  const navigator = { onLine: true };
  const context = vm.createContext({
    document, window, navigator, EventSource, URLSearchParams, AbortController,
    Node: { ELEMENT_NODE: 1, DOCUMENT_POSITION_FOLLOWING: 4 },
    crypto: { getRandomValues: (array) => webcrypto.getRandomValues(array) },
    MutationObserver: class {
      constructor(callback) { this.callback = callback; observers.push(this); }
      observe() {}
    },
    setTimeout: () => 1,
    clearTimeout() {},
    fetch: (url, options) => new Promise((resolve, reject) => {
      calls.push({ url, options, resolve, reject });
      order.push(url);
    }),
  });
  vm.runInContext(source, context, { filename: "reader-client.js" });
  const respond = (index, value, status = 200) => calls[index].resolve({ ok: status < 400, status, json: async () => value });
  const link = (attributes, container = nodes.get("page-content")) => {
    const anchor = new Element("a");
    for (const [name, value] of Object.entries(attributes)) anchor.setAttribute(name, value);
    container.append(anchor);
    return () => container.emit("click", { target: anchor });
  };
  return { calls, streams, observers, document, window, navigator, focus, scrolls, order, respond, link, select, selection, get: (id) => nodes.get(id) };
}

async function loaded(value = page(), options) {
  const reader = harness(options);
  reader.respond(0, value);
  await settle();
  return reader;
}

test("HTML keeps only the agreed controls, native collapsed Contents, and local themed assets", () => {
  const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)];
  assert.equal(scripts.length, 2);
  assert.match(scripts[0][1], /nonce="__CSP_NONCE__"/);
  assert.match(scripts[0][2], /get\("scoutTheme"\)/);
  assert.match(scripts[0][2], /prefers-color-scheme: dark/);
  assert.match(scripts[1][1], /type="module" src="reader-client\.js"/);
  assert.match(html, /href="reader\.css"/);
  const stylesheets = [...html.matchAll(/<link rel="stylesheet" href="([^"]+)">/g)].map((match) => match[1]);
  assert.deepEqual(stylesheets, ["katex/katex.min.css", "reader.css"]);
  assert.doesNotMatch(html, /<(?:script|link)[^>]+(?:src|href)="(?:https?:|\/)/);
  assert.doesNotMatch(html, /<style\b|\sstyle=|\son\w+=/);
  assert.deepEqual([...html.matchAll(/<button\b[^>]*\bid="([^"]+)"/g)].map((match) => match[1]),
    ["previous-button", "next-button", "ask-button"]);
  assert.match(html, /id="ask-button"[^>]*hidden[^>]*>Ask in chat<\/button>/);
  assert.match(html, /<summary>Contents<\/summary>/);
  assert.doesNotMatch(html, /<details[^>]*\bopen\b|<dialog\b|Refresh|Explain this page|Send excerpt|Read only|course-path|document-path/);
  assert.doesNotMatch(source, /api\/discuss|api\/refresh|postMessage|clipboard|session\.send|state\.excerpt/);
});

test("KaTeX styles contain wide display math and expose parse errors without changing math fonts or baselines", () => {
  const display = css.match(/\.markdown-body \.katex-display \{([^}]+)\}/)?.[1];
  assert.ok(display);
  assert.match(display, /max-width: 100%/);
  assert.match(display, /overflow-x: auto/);
  assert.match(css, /\.katex-display > \.katex \{ min-width: max-content;/);
  assert.match(css, /\.katex-error \{ color: var\(--cp-danger\) !important;/);
  for (const rule of css.matchAll(/[^{}]*\.katex[^{}]*\{([^}]+)\}/g)) {
    assert.doesNotMatch(rule[1], /\b(?:font(?:-family)?|vertical-align)\s*:/);
  }
});

test("SSE connects immediately; an older initial GET cannot overwrite newer live state or steal focus", async () => {
  const reader = harness();
  assert.deepEqual(reader.order, ["events", "api/state"]);
  reader.document.activeElement = reader.get("previous-button");
  reader.streams[0].push("state", page(3, {
    path: "live.md", title: "Live page", html: '<h1 id="practice">Live page</h1>', anchor: "practice",
  }));
  reader.respond(0, page(1));
  await settle();
  assert.equal(reader.document.title, "Live page · Reader tour");
  assert.equal(reader.get("course-name").textContent, "Reader tour");
  assert.equal(reader.get("page-title").hidden, true);
  assert.equal(reader.get("page-content").hidden, false);
  assert.equal(reader.document.activeElement, reader.get("previous-button"));
  assert.deepEqual(reader.focus, []);
});

test("navigation uses revisions, locks buttons, and ignores a late mutation response", async () => {
  const reader = await loaded();
  reader.select("A passage before navigating");
  reader.get("next-button").click();
  assert.equal(reader.calls[1].url, "api/navigate");
  assert.deepEqual(JSON.parse(reader.calls[1].options.body), { direction: "next", expectedRevision: 1 });
  for (const id of ["next-button", "previous-button", "ask-button"]) {
    assert.equal(reader.get(id).disabled, true, id);
  }
  assert.equal(reader.get("ask-button").hidden, true);
  assert.equal(reader.selection.toString(), "");
  reader.streams[0].push("state", page(5, { path: "latest.md", title: "Latest page" }));
  reader.respond(1, page(2, { path: "older.md" }));
  await settle();
  assert.equal(reader.document.title, "Latest page · Reader tour");
  assert.equal(reader.get("next-button").disabled, false);
  assert.equal(reader.get("previous-button").disabled, true);
  assert.equal(reader.get("previous-detail").hidden, true);
  assert.ok(reader.focus.includes("page-title"));
});

test("disconnects, provider errors, and malformed updates retain the readable page", async () => {
  const reader = await loaded();
  const original = reader.get("page-content").innerHTML;
  reader.streams[0].emit("error");
  assert.match(reader.get("connection-error").textContent, /Reconnecting/);
  reader.window.emit("offline");
  assert.match(reader.get("connection-error").textContent, /Offline/);
  reader.streams[0].emit("open");
  assert.equal(reader.get("connection-error").hidden, true);
  reader.streams[0].push("reader_error", { error: { code: "missing", message: "The next page is missing." } });
  assert.equal(reader.get("error-message").textContent, "The next page is missing.");
  reader.streams[0].push("state", { ...page(2), headings: [null] });
  assert.match(reader.get("error-message").textContent, /incomplete page/);
  assert.equal(reader.get("page-content").innerHTML, original);
  assert.equal(reader.get("page-content").hidden, false);
  assert.equal(reader.calls.length, 1);
});

test("broken endpoints explain why; local links are followed but external links are not intercepted", async () => {
  const reader = await loaded(page(1, {
    next: { reference: "missing.md", path: null, label: "Missing page", available: false, error: "The linked page was not found." },
  }));
  assert.equal(reader.get("next-button").disabled, true);
  assert.equal(reader.get("next-detail").textContent, "The linked page was not found.");
  const external = reader.link({ href: "https://example.com", target: "_blank", rel: "noopener noreferrer" })();
  assert.equal(external.defaultPrevented, false);
  assert.equal(reader.calls.length, 1);
  const local = reader.link({ href: "#", "data-reader-reference": "[[02-next#practice]]", "data-reader-kind": "wikilink" })();
  assert.equal(local.defaultPrevented, true);
  assert.equal(reader.calls[1].url, "api/follow");
  assert.deepEqual(JSON.parse(reader.calls[1].options.body), { reference: "[[02-next#practice]]", kind: "wikilink", expectedRevision: 1 });
  reader.respond(1, page(2, { path: "02-next.md", anchor: "practice" }));
  await settle();
  assert.ok(reader.focus.includes("practice"));
});

test("same-page anchors focus locally, respect reduced motion, and do not call the provider", async () => {
  const reader = await loaded(page(), { reducedMotion: true });
  const anchor = reader.link({ href: "#practice" })();
  assert.equal(anchor.defaultPrevented, true);
  assert.equal(reader.calls.length, 1);
  assert.deepEqual(reader.scrolls.at(-1), { target: "practice", behavior: "auto", block: "start" });
  assert.ok(reader.focus.includes("practice"));
});

test("Contents contains page headings and retains its toggle choice through navigation and hidden pages", async () => {
  const reader = await loaded();
  const contents = reader.get("page-outline");
  assert.equal(contents.open, false);
  assert.equal(contents.hidden, false);
  assert.equal(reader.get("outline-list").textContent, "WelcomePractice");
  contents.open = true;
  reader.get("next-button").click();
  reader.respond(1, page(2, { path: "02-next.md" }));
  await settle();
  assert.equal(contents.open, true);
  reader.streams[0].push("state", page(3, { path: "plain.md", html: "<p>No headings.</p>", headings: [] }));
  assert.equal(contents.hidden, true);
  assert.equal(contents.open, true);
  reader.streams[0].push("state", page(4, { path: "back.md" }));
  assert.equal(contents.hidden, false);
  assert.equal(contents.open, true);
  contents.open = false;
  reader.get("next-button").click();
  reader.respond(2, page(5, { path: "another.md" }));
  await settle();
  assert.equal(contents.open, false);
});

test("Ask in chat is absent without an explicit capability or a complete article selection", async () => {
  for (const canAskInChat of [undefined, false, "true"]) {
    const reader = await loaded(page(1, { canAskInChat }));
    reader.select("A passage");
    assert.equal(reader.get("ask-button").hidden, true);
    assert.equal(reader.calls.length, 1);
  }
  const reader = await loaded();
  assert.equal(reader.get("ask-button").hidden, true);
  reader.select("A passage");
  assert.equal(reader.get("ask-button").hidden, false);
  reader.select("");
  assert.equal(reader.get("ask-button").hidden, true);
  reader.select("Outside", { node: reader.document.body });
  assert.equal(reader.get("ask-button").hidden, true);
  reader.select("Partly outside", { endNode: reader.document.body });
  assert.equal(reader.get("ask-button").hidden, true);
  reader.select("A passage");
  reader.streams[0].push("state", page(2, { canAskInChat: false }));
  assert.equal(reader.get("ask-button").hidden, true);
  assert.equal(reader.calls.length, 1);
});

test("selecting never sends; explicit Ask stages the entire passage beyond 12000 characters once", async () => {
  const reader = await loaded();
  const text = `\n  ${"A grounded passage: x² + y².\n".repeat(600)}  \n`;
  assert.ok(text.length > 12000);
  reader.select(text);
  const ask = reader.get("ask-button");
  assert.equal(ask.hidden, false);
  assert.equal(reader.calls.length, 1);
  assert.equal(ask.emit("mousedown").defaultPrevented, true);
  assert.equal(reader.selection.toString(), text);
  ask.click();
  const body = JSON.parse(reader.calls[1].options.body);
  assert.equal(reader.calls[1].url, "api/attach");
  assert.equal(body.text, text);
  assert.equal(body.expectedRevision, 1);
  assert.equal(body.headingId, "welcome");
  assert.match(body.requestId, /^[0-9a-f]{32}$/);
  assert.deepEqual(Object.keys(body).sort(), ["expectedRevision", "headingId", "requestId", "text"]);
  ask.click();
  assert.equal(reader.calls.length, 2);
  reader.respond(1, { staged: true, path: "01-start.md" });
  await settle();
  assert.equal(ask.hidden, true);
  assert.equal(reader.selection.toString(), "");
  assert.equal(reader.get("notice").textContent, "Added to chat. Write your question there.");
});

test("selection references use the starting section and omit a heading when none exists", async () => {
  const reader = await loaded();
  reader.select("Practice passage", { node: reader.get("page-content").querySelector("h2") });
  reader.get("ask-button").click();
  assert.equal(JSON.parse(reader.calls[1].options.body).headingId, "practice");
  reader.respond(1, { staged: true, path: "01-start.md" });
  await settle();

  const plain = await loaded(page(1, { html: "<p>No heading.</p>", headings: [] }));
  plain.select("No heading.", { node: plain.get("page-content") });
  plain.get("ask-button").click();
  assert.equal(JSON.parse(plain.calls[1].options.body).headingId, null);
  plain.respond(1, { staged: true, path: "01-start.md" });
  await settle();
});

test("failed attachments preserve the passage and retry ID; a new selection gets a new ID", async () => {
  const reader = await loaded();
  const ask = reader.get("ask-button");
  reader.select("  Keep the complete passage.\n");
  ask.focus();
  ask.click();
  const first = JSON.parse(reader.calls[1].options.body);
  reader.calls[1].reject(new TypeError("connection lost"));
  await settle();
  assert.match(reader.get("error-message").textContent, /attachment could not be confirmed/);
  assert.equal(ask.hidden, false);
  assert.equal(ask.disabled, false);
  assert.equal(reader.document.activeElement, ask);
  assert.equal(reader.selection.toString(), first.text);
  reader.document.emit("selectionchange");
  ask.click();
  assert.deepEqual(JSON.parse(reader.calls[2].options.body), first);
  reader.respond(2, { error: { code: "host_limit", message: "The host rejected this attachment." } }, 413);
  await settle();
  assert.equal(reader.get("error-message").textContent, "The host rejected this attachment.");
  assert.equal(ask.disabled, false);
  assert.equal(reader.calls.length, 3);
  reader.select(first.text, { startOffset: 2 });
  ask.click();
  assert.notEqual(JSON.parse(reader.calls[3].options.body).requestId, first.requestId);
  reader.respond(3, { staged: true, path: "01-start.md" });
  await settle();
});

test("keyboard focus preserves the captured passage and the contextual action stays inside the viewport", async () => {
  const reader = await loaded();
  const rect = { left: 790, right: 799, top: 575, bottom: 595, width: 9, height: 20 };
  reader.select("Keyboard passage", { rect });
  const ask = reader.get("ask-button");
  reader.selection.removeAllRanges();
  ask.focus();
  await settle();
  assert.equal(reader.selection.toString(), "Keyboard passage");
  assert.equal(ask.hidden, false);
  assert.ok(Number.parseFloat(ask.style.left) + 128 <= 792);
  assert.ok(Number.parseFloat(ask.style.top) + 36 <= 592);
  reader.window.innerWidth = 320;
  reader.window.innerHeight = 180;
  reader.window.emit("resize");
  assert.equal(ask.hidden, true);
  Object.assign(rect, { left: 310, right: 319, top: 158, bottom: 178 });
  reader.window.emit("scroll");
  assert.equal(ask.hidden, false);
  assert.ok(Number.parseFloat(ask.style.left) >= 8);
  assert.ok(Number.parseFloat(ask.style.left) + 128 <= 312);
  assert.ok(Number.parseFloat(ask.style.top) >= 8);
  assert.ok(Number.parseFloat(ask.style.top) + 36 <= 172);
});

test("new revisions and stale attachment errors invalidate the selection without replaying the action", async () => {
  const reader = await loaded();
  reader.select("Old passage");
  reader.streams[0].push("state", page(2));
  await settle();
  assert.equal(reader.get("ask-button").hidden, true);
  assert.equal(reader.selection.toString(), "");
  reader.streams[0].push("state", page(1));
  reader.select("Fresh passage");
  reader.get("ask-button").click();
  assert.equal(JSON.parse(reader.calls[1].options.body).expectedRevision, 2);
  reader.respond(1, { error: { code: "stale_view", message: "The page changed." } }, 409);
  await settle();
  assert.equal(reader.calls[2].url, "api/state");
  assert.equal(reader.calls[2].options.method, "GET");
  assert.equal(reader.get("ask-button").hidden, true);
  reader.respond(2, page(3));
  await settle();
  assert.equal(reader.calls.filter((call) => call.options.method === "POST").length, 1);
  assert.match(reader.get("error-message").textContent, /Select the passage again/);
  assert.equal(reader.get("ask-button").hidden, true);
  reader.select("A new selection");
  reader.get("ask-button").click();
  assert.equal(JSON.parse(reader.calls[3].options.body).expectedRevision, 3);
  reader.respond(3, { staged: true, path: "01-start.md" });
  await settle();
});

test("a live stale-view error waits for the active request before resynchronizing", async () => {
  const reader = await loaded();
  reader.get("next-button").click();
  reader.streams[0].push("reader_error", { error: { code: "stale_view", message: "The page changed." } });
  assert.equal(reader.calls.length, 2);
  reader.respond(1, page(2));
  await settle();
  assert.equal(reader.calls[2].url, "api/state");
  reader.respond(2, page(3));
  await settle();
  assert.equal(reader.calls.length, 3);
  assert.match(reader.get("error-message").textContent, /choose the action again/);
});

test("same-page live updates preserve scroll and failed navigation retains the readable page", async () => {
  const reader = await loaded();
  reader.streams[0].push("state", page(2, { html: '<h1 id="welcome">Welcome</h1><p>Updated text.</p>' }));
  await settle();
  assert.deepEqual(reader.scrolls.at(-1), { top: 120, left: 0, behavior: "instant" });
  assert.deepEqual(reader.focus, []);
  const updated = reader.get("page-content").innerHTML;
  reader.get("next-button").click();
  reader.respond(1, { error: { code: "missing", message: "The next page could not be opened." } }, 404);
  await settle();
  assert.equal(reader.get("page-content").innerHTML, updated);
  assert.equal(reader.get("next-button").disabled, false);
  assert.equal(reader.get("error-message").textContent, "The next page could not be opened.");
});

test("a new anchor request focuses the heading even when its path and anchor are unchanged", async () => {
  const reader = await loaded(page(1, { anchor: "practice" }));
  assert.deepEqual(reader.focus, []);
  reader.streams[0].push("state", page(2, { anchor: "practice" }));
  await settle();
  assert.deepEqual(reader.focus, ["practice"]);
});

test("navigation keeps a supplied title in view when the Markdown has no matching H1", async () => {
  const reader = await loaded();
  reader.streams[0].push("state", page(2, {
    path: "02-next.md", title: "A new idea", html: "<p>Start reading here.</p>", headings: [],
  }));
  await settle();
  assert.equal(reader.get("page-title").hidden, false);
  assert.equal(reader.get("page-title").textContent, "A new idea");
  assert.ok(reader.focus.includes("page-title"));
});

test("initial errors are honest and live state can recover without an extra control or polling", async () => {
  const reader = harness();
  reader.calls[0].reject(new TypeError("offline"));
  await settle();
  assert.equal(reader.get("initial-message").textContent, "The course could not be loaded.");
  assert.equal(reader.get("refresh-button"), undefined);
  reader.streams[0].push("state", page());
  await settle();
  assert.equal(reader.get("initial-message").hidden, true);
  assert.equal(reader.get("page-content").hidden, false);
  assert.equal(reader.get("error-message").hidden, true);
  assert.equal(reader.calls.length, 1);
});

test("broken images get visible descriptive fallback text", async () => {
  const reader = await loaded(page(1, { html: '<h1 id="welcome">Welcome</h1><img src="asset?document=01-start.md" alt="A cell diagram">' }));
  const article = reader.get("page-content");
  article.querySelector("img").emit("error");
  const replacement = article.children.find((node) => node.className === "image-fallback");
  assert.match(replacement.textContent, /Image unavailable.*A cell diagram/);
  assert.equal(replacement.getAttribute("aria-label"), "Image unavailable. A cell diagram");
  assert.equal(article.querySelector("img"), null);
});

test("documented host color mode takes precedence and can change at runtime", async () => {
  const reader = await loaded(page(), { hostTheme: "dark" });
  assert.equal(reader.document.documentElement.getAttribute("data-theme"), "dark");
  reader.document.documentElement.setAttribute("data-color-mode", "light");
  reader.observers[0].callback();
  assert.equal(reader.document.documentElement.getAttribute("data-theme"), "light");
});
