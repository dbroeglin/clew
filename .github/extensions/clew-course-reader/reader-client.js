const element = (id) => document.getElementById(id);
const ui = {
  course: element("course-name"),
  connection: element("connection-error"),
  previous: element("previous-button"),
  next: element("next-button"),
  ask: element("ask-button"),
  error: element("error-message"),
  notice: element("notice"),
  surface: element("reading-surface"),
  initial: element("initial-message"),
  title: element("page-title"),
  article: element("page-content"),
  outline: element("page-outline"),
  outlineList: element("outline-list"),
};

let state = null;
let pending = null;
let selectedPassage = null;
let events = null;
let staleResyncQueued = false;
let noticeTimer;

function message(target, text = "") {
  target.textContent = text;
  target.hidden = !text;
}

function announce(text = "") {
  clearTimeout(noticeTimer);
  message(ui.notice, text);
  if (text) noticeTimer = setTimeout(() => message(ui.notice), 5000);
}

function syncTheme() {
  const hostTheme = document.documentElement.getAttribute("data-color-mode")
    || document.body.getAttribute("data-color-mode");
  const requested = new URLSearchParams(window.location.search).get("scoutTheme");
  const theme = hostTheme === "dark" || hostTheme === "light" ? hostTheme
    : requested === "dark" || requested === "light" ? requested
      : window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", theme);
}

syncTheme();
const themeObserver = new MutationObserver(syncTheme);
for (const root of [document.documentElement, document.body]) {
  themeObserver.observe(root, { attributes: true, attributeFilter: ["data-color-mode"] });
}
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", syncTheme);

function updateControls() {
  const busy = pending !== null;
  ui.previous.disabled = busy || !state?.previous?.available;
  ui.next.disabled = busy || !state?.next?.available;
  ui.surface.setAttribute("aria-busy", String(busy));
  positionSelectionAction();
}

async function operate(kind, action) {
  if (pending) return;
  pending = { kind };
  message(ui.error);
  updateControls();
  try {
    await action();
  } finally {
    pending = null;
    updateControls();
    if (staleResyncQueued) resyncAfterLiveError();
  }
}

class ReaderError extends Error {
  constructor(code, text) {
    super(text);
    this.code = code;
  }
}

async function request(endpoint, body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(endpoint, {
      method: body === undefined ? "GET" : "POST",
      cache: "no-store",
      credentials: "same-origin",
      headers: body === undefined ? { Accept: "application/json" }
        : { Accept: "application/json", "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: controller.signal,
    });
    let result;
    try {
      result = await response.json();
    } catch {
      throw new ReaderError("invalid_response", "The course provider returned an unreadable response.");
    }
    if (!response.ok) {
      throw new ReaderError(result?.error?.code || "request_failed",
        result?.error?.message || `The course provider could not complete the request (${response.status}).`);
    }
    return result;
  } catch (error) {
    if (error instanceof ReaderError) throw error;
    throw new ReaderError("network_error", controller.signal.aborted
      ? "The request timed out."
      : "The course provider could not be reached.");
  } finally {
    clearTimeout(timeout);
  }
}

function validState(value) {
  const validLink = (link) => link === null || (link
    && typeof link.reference === "string" && typeof link.label === "string"
    && typeof link.available === "boolean"
    && (link.path === null || typeof link.path === "string")
    && (link.error === null || typeof link.error === "string"));
  return value && Number.isSafeInteger(value.revision) && value.revision >= 0
    && ["course", "path", "title", "html"].every((key) => typeof value[key] === "string")
    && (value.anchor === null || typeof value.anchor === "string")
    && Array.isArray(value.headings) && value.headings.every((heading) => heading
      && typeof heading.id === "string" && typeof heading.text === "string"
      && Number.isInteger(heading.level) && heading.level >= 1 && heading.level <= 6)
    && validLink(value.previous) && validLink(value.next);
}

function readableName(path) {
  const name = (path.split(/[\\/]/).filter(Boolean).pop() || "Course").replace(/[-_]+/g, " ");
  return name.charAt(0).toLocaleUpperCase() + name.slice(1);
}

function renderStep(direction, link) {
  const detail = element(`${direction}-detail`);
  message(detail, link && !link.available ? link.error || "This course link is unavailable." : "");
}

function headingTarget(id) {
  return [...ui.article.querySelectorAll("[id]")].find((node) => node.id === id);
}

function goToHeading(id, focus = true) {
  const target = (id && headingTarget(id)) || (ui.title.hidden ? ui.article : ui.title);
  if (focus) {
    target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
  }
  target.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    block: "start",
  });
}

function renderOutline(headings) {
  ui.outlineList.replaceChildren();
  for (const heading of headings) {
    if (typeof heading.id !== "string" || !heading.id || typeof heading.text !== "string") continue;
    const item = document.createElement("li");
    item.dataset.level = String(Math.min(6, Math.max(1, Number(heading.level) || 1)));
    const link = document.createElement("a");
    link.href = `#${encodeURIComponent(heading.id)}`;
    link.textContent = heading.text;
    item.append(link);
    ui.outlineList.append(item);
  }
  ui.outline.hidden = ui.outlineList.childElementCount === 0;
}

function watchImages() {
  for (const image of ui.article.querySelectorAll("img")) {
    const showFailure = () => {
      if (!ui.article.contains(image)) return;
      const replacement = document.createElement("span");
      const title = document.createElement("strong");
      const detail = document.createElement("span");
      const description = image.alt.trim() || "This image could not be loaded from the course.";
      replacement.className = "image-fallback";
      replacement.setAttribute("role", "img");
      replacement.setAttribute("aria-label", `Image unavailable. ${description}`);
      title.textContent = "Image unavailable";
      detail.textContent = description;
      replacement.append(title, detail);
      image.replaceWith(replacement);
    };
    image.addEventListener("error", showFailure, { once: true });
    if (image.complete && image.naturalWidth === 0) showFailure();
  }
}

function articleRanges(selection) {
  if (!selection || selection.isCollapsed || !selection.rangeCount) return [];
  const ranges = Array.from({ length: selection.rangeCount }, (_, index) => selection.getRangeAt(index));
  return ranges.every((range) => ui.article.contains(range.startContainer) && ui.article.contains(range.endContainer))
    ? ranges : [];
}

function passageHeading(range) {
  const container = range.startContainer;
  const start = container.nodeType === Node.ELEMENT_NODE
    ? container.childNodes[range.startOffset] || container : container;
  let id = null;
  for (const heading of state.headings) {
    const target = headingTarget(heading.id);
    if (!target) continue;
    if (target.contains(start) || (target.compareDocumentPosition(start) & Node.DOCUMENT_POSITION_FOLLOWING)) {
      id = heading.id;
    } else break;
  }
  return id;
}

function invalidatePassage(clearNative = false) {
  selectedPassage = null;
  ui.ask.hidden = true;
  ui.ask.disabled = true;
  const selection = window.getSelection();
  if (clearNative && articleRanges(selection).length) selection.removeAllRanges();
}

function capturePassage() {
  const selection = window.getSelection();
  const ranges = articleRanges(selection);
  const text = selection?.toString() || "";
  if (state?.canAskInChat !== true || !ranges.length || !text.trim()) {
    invalidatePassage();
    return;
  }
  const unchanged = selectedPassage?.revision === state.revision && selectedPassage.text === text
    && selectedPassage.ranges.length === ranges.length
    && ranges.every((range, index) => {
      const previous = selectedPassage.ranges[index];
      return ["startContainer", "startOffset", "endContainer", "endOffset"].every((key) => range[key] === previous[key]);
    });
  if (!unchanged) {
    selectedPassage = {
      text, revision: state.revision, headingId: passageHeading(ranges[0]),
      ranges: ranges.map((range) => range.cloneRange()), requestId: null,
    };
    announce();
  }
  positionSelectionAction();
}

function positionSelectionAction() {
  const available = state?.canAskInChat === true && selectedPassage?.revision === state.revision;
  ui.ask.disabled = !available || pending !== null;
  ui.ask.hidden = !available;
  if (!available) return;
  const viewport = window.visualViewport;
  const left = viewport?.offsetLeft || 0;
  const top = viewport?.offsetTop || 0;
  const right = left + (viewport?.width || window.innerWidth);
  const bottom = top + (viewport?.height || window.innerHeight);
  const rect = selectedPassage.ranges.flatMap((range) => [...range.getClientRects()])
    .reverse().find((box) => box.width > 0 && box.height > 0
      && box.bottom > top && box.top < bottom && box.right > left && box.left < right);
  if (!rect) {
    ui.ask.hidden = true;
    return;
  }
  const button = ui.ask.getBoundingClientRect();
  const y = rect.bottom + 8 + button.height <= bottom - 8 ? rect.bottom + 8 : rect.top - button.height - 8;
  ui.ask.style.left = `${Math.max(left + 8, Math.min(rect.left, right - button.width - 8))}px`;
  ui.ask.style.top = `${Math.max(top + 8, Math.min(y, bottom - button.height - 8))}px`;
}

function preservePassageOnFocus() {
  if (!selectedPassage || ui.ask.hidden) return;
  const selection = window.getSelection();
  if (selection && selection.isCollapsed) {
    // Focusing the action must not replace the passage captured for a keyboard activation.
    selection.removeAllRanges();
    for (const range of selectedPassage.ranges) selection.addRange(range.cloneRange());
  } else {
    capturePassage();
  }
}

function applyState(next, intent = pending?.kind) {
  if (!validState(next)) {
    throw new ReaderError("invalid_state", "The course provider returned an incomplete page. The current page has not been replaced.");
  }
  // GET, mutation responses, and SSE can arrive in a different order.
  if (state && next.revision <= state.revision) return;
  const initial = state === null;
  const pageChanged = !initial && (next.path !== state.path || next.course !== state.course);
  const anchorRequested = !initial && next.anchor && intent !== "refresh";
  const htmlChanged = initial || pageChanged || next.html !== state.html;
  const scroll = { top: window.scrollY, left: window.scrollX };
  invalidatePassage(true);
  state = next;

  ui.course.textContent = readableName(state.course);
  const title = state.title || readableName(state.path.replace(/\.md$/i, ""));
  document.title = `${title} · ${ui.course.textContent}`;
  renderStep("previous", state.previous);
  renderStep("next", state.next);
  if (htmlChanged) {
    // Only the provider's sanitized Markdown output is inserted as HTML.
    ui.article.innerHTML = state.html;
    watchImages();
  }
  const firstH1 = ui.article.querySelector("h1");
  const normalized = (text) => text.trim().replace(/\s+/g, " ").toLocaleLowerCase();
  ui.title.textContent = title;
  ui.title.hidden = Boolean(firstH1 && normalized(firstH1.textContent) === normalized(ui.title.textContent));
  ui.article.setAttribute("aria-label", title);
  ui.article.hidden = false;
  ui.initial.hidden = true;
  if (initial) message(ui.error);
  renderOutline(state.headings);
  updateControls();

  const revision = state.revision;
  window.requestAnimationFrame(() => {
    if (state.revision !== revision) return;
    if (pageChanged || anchorRequested) {
      goToHeading(state.anchor);
    } else if (initial && state.anchor
      && [document.body, document.documentElement].includes(document.activeElement)) {
      goToHeading(state.anchor, false);
    } else if (!initial && htmlChanged) {
      window.scrollTo({ ...scroll, behavior: "instant" });
    }
  });
}

async function handleFailure(error, attempt = null) {
  if (error.code === "stale_view") {
    invalidatePassage(true);
    try {
      applyState(await request("api/state"));
      message(ui.error, attempt
        ? "The page changed. Select the passage again before using Ask in chat."
        : "The page changed in another view. The latest page is shown; please choose the action again.");
    } catch (refreshError) {
      message(ui.error, `The view is out of date. ${refreshError.message}`);
    }
  } else {
    let text = error.message || "The request could not be completed. Please try again.";
    if (attempt && selectedPassage === attempt && (error.code === "network_error" || error.code === "invalid_response")) {
      text += " The attachment could not be confirmed. Retry Ask in chat for this same selection.";
    }
    message(ui.error, text);
  }
  if (!state) {
    ui.initial.textContent = "The course could not be loaded.";
  }
}

function resyncAfterLiveError() {
  invalidatePassage(true);
  message(ui.error, "The page changed in another view. Checking the latest page before you try again.");
  staleResyncQueued = true;
  if (pending) return;
  staleResyncQueued = false;
  void operate("resync", () => handleFailure(new ReaderError("stale_view", "")));
}

async function loadState() {
  await operate("load", async () => {
    try {
      applyState(await request("api/state"));
    } catch (error) {
      await handleFailure(error);
    }
  });
}

async function mutate(endpoint, body, kind) {
  if (!state || pending) return;
  const expectedRevision = state.revision;
  invalidatePassage(true);
  await operate(kind, async () => {
    try {
      applyState(await request(endpoint, { ...body, expectedRevision }), kind);
    } catch (error) {
      await handleFailure(error);
    }
  });
}

async function attachPassage() {
  if (pending) return;
  capturePassage();
  if (!selectedPassage || ui.ask.hidden) return;
  const attempt = selectedPassage;
  const restoreFocus = document.activeElement === ui.ask;
  let staged = false;
  await operate("attach", async () => {
    try {
      // randomUUID needs a secure ancestor context; getRandomValues also works in embedded canvases.
      attempt.requestId ??= [...crypto.getRandomValues(new Uint8Array(16))]
        .map((byte) => byte.toString(16).padStart(2, "0")).join("");
      const result = await request("api/attach", {
        text: attempt.text,
        headingId: attempt.headingId,
        expectedRevision: attempt.revision,
        requestId: attempt.requestId,
      });
      if (result?.staged !== true || typeof result.path !== "string") {
        throw new ReaderError("invalid_response", "The host did not confirm the attachment.");
      }
      staged = true;
      if (selectedPassage === attempt) invalidatePassage(true);
      announce("Added to chat. Write your question there.");
    } catch (error) {
      await handleFailure(error, attempt);
    }
  });
  if (restoreFocus && !pending) {
    if (selectedPassage === attempt && !ui.ask.hidden) ui.ask.focus({ preventScroll: true });
    else if (staged && !selectedPassage) ui.article.focus({ preventScroll: true });
  }
}

function followAnchor(event, link) {
  const href = link.getAttribute("href");
  if (!href?.startsWith("#")) return;
  event.preventDefault();
  try {
    const id = decodeURIComponent(href.slice(1));
    if (headingTarget(id)) {
      invalidatePassage(true);
      goToHeading(id);
    }
    else message(ui.error, "That heading is not available on this page.");
  } catch {
    message(ui.error, "That heading link could not be opened.");
  }
}

ui.article.addEventListener("click", (event) => {
  const link = event.target.closest("a");
  if (!link || !ui.article.contains(link)) return;
  if (link.hasAttribute("data-reader-reference")) {
    event.preventDefault();
    if (pending) return;
    const { readerReference: reference, readerKind: kind } = link.dataset;
    if (!reference || !["path", "wikilink"].includes(kind)) {
      message(ui.error, "That course link could not be opened.");
      return;
    }
    void mutate("api/follow", { reference, kind }, "follow");
  } else {
    followAnchor(event, link);
  }
});

ui.outlineList.addEventListener("click", (event) => {
  const link = event.target.closest("a");
  if (link && ui.outlineList.contains(link)) followAnchor(event, link);
});
ui.previous.addEventListener("click", () => {
  if (state?.previous?.available) void mutate("api/navigate", { direction: "previous" }, "navigate");
});
ui.next.addEventListener("click", () => {
  if (state?.next?.available) void mutate("api/navigate", { direction: "next" }, "navigate");
});
ui.ask.addEventListener("mousedown", (event) => event.preventDefault());
ui.ask.addEventListener("focus", preservePassageOnFocus);
ui.ask.addEventListener("click", () => { void attachPassage(); });
document.addEventListener("selectionchange", capturePassage);
window.addEventListener("scroll", positionSelectionAction, { passive: true });
window.addEventListener("resize", positionSelectionAction);
window.visualViewport?.addEventListener("scroll", positionSelectionAction, { passive: true });
window.visualViewport?.addEventListener("resize", positionSelectionAction);

function connect() {
  events?.close();
  try {
    events = new EventSource("events");
    events.addEventListener("open", () => message(ui.connection));
    events.addEventListener("state", (event) => {
      try {
        applyState(JSON.parse(event.data));
      } catch (error) {
        message(ui.error, error instanceof ReaderError ? error.message
          : "A live page update could not be read. Your last page is still available.");
      }
    });
    events.addEventListener("reader_error", (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data?.error?.code === "stale_view") resyncAfterLiveError();
        else void handleFailure(new ReaderError(data?.error?.code,
          data?.error?.message || "The course provider reported an error. Your last page is still available."));
      } catch {
        message(ui.error, "The course provider reported an unreadable error. Your last page is still available.");
      }
    });
    events.addEventListener("error", () => {
      if (navigator.onLine === false) message(ui.connection, "Offline. Live page updates are unavailable.");
      else if (events.readyState === EventSource.CLOSED) message(ui.connection, "Live page updates have stopped. Your last page is still available.");
      else message(ui.connection, "Reconnecting… Your last page is still available.");
    });
  } catch {
    message(ui.connection, "Live page updates are unavailable.");
  }
}

window.addEventListener("offline", () => message(ui.connection, "Offline. Live page updates are unavailable."));
window.addEventListener("online", () => {
  if (events?.readyState === EventSource.OPEN) message(ui.connection);
  else {
    message(ui.connection, "Reconnecting… Your last page is still available.");
    if (!events || events.readyState === EventSource.CLOSED) connect();
  }
});
window.addEventListener("pagehide", () => events?.close());
window.addEventListener("pageshow", (event) => { if (event.persisted) connect(); });

connect();
void loadState();
