// Clew canvas front-end: renders the compiled publication like clew-generate's offline HTML,
// records semantic student actions and follows live updates and tutor requests from the extension.
(() => {
  "use strict";
  const params = new URLSearchParams(window.location.search);
  const token = params.get("t") || "";
  const instance = params.get("i") || "";
  const base = window.location.pathname.replace(/[^/]*$/, "");
  const query = "?t=" + encodeURIComponent(token) + (instance ? "&i=" + encodeURIComponent(instance) : "");
  const byId = id => document.getElementById(id);
  const panel = byId("panel-content");
  const panelTitle = byId("panel-title");
  const panelBack = byId("panel-back");
  const panelClose = byId("panel-close");
  const aside = panel.closest(".panel");
  const placeholder = {title: panelTitle.textContent, text: panel.textContent};
  const LABELS = {method: "Méthode", hints: "Indices", explanations: "Explications"};
  const STATUS = {
    idle: "Démarrage…", compiling: "Compilation de la publication…", updating: "Mise à jour…",
    ready: "", error: "Erreur de compilation", stale: "Contenu non actualisé",
  };

  let data = null;
  let version = 0;
  let questions = new Map();
  let questionsByAddress = new Map();
  let courses = new Map();
  let coursesByAddress = new Map();
  let exercises = new Map();
  let correctionControls = [];
  let stack = [];
  let typesetQueue = Promise.resolve();
  const hints = new Map();
  const started = new Set();

  function error(message) {
    const box = byId("error");
    box.hidden = false;
    box.textContent = message;
  }
  let toastTimer = 0;
  function toast(message) {
    const box = byId("toast");
    box.textContent = message;
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { box.hidden = true; }, 6000);
  }

  // Requests and the event outbox.
  async function call(path, options = {}) {
    const response = await fetch(base + "api/" + path + query, {
      ...options, cache: "no-store", headers: {"Content-Type": "application/json", "x-clew-token": token},
    });
    let body = null;
    try { body = await response.json(); } catch { body = null; }
    return {ok: response.ok, status: response.status, body, headers: response.headers};
  }
  const outbox = [];
  let flushing = null;
  let retryTimer = 0;
  let retryDelay = 1000;
  function record(type, fields) {
    outbox.push({type, ts: new Date().toISOString(), ...fields});
    flush();
  }
  function flush() {
    if (!flushing) flushing = drain().finally(() => { flushing = null; });
    return flushing;
  }
  async function drain() {
    while (outbox.length) {
      const batch = outbox.slice(0, 50);
      let result;
      try {
        result = await call("event", {method: "POST", body: JSON.stringify({events: batch})});
      } catch {
        result = null;
      }
      if (!result || result.status >= 500 || result.status === 429) {
        clearTimeout(retryTimer);
        retryTimer = setTimeout(flush, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 30000);
        return;
      }
      retryDelay = 1000;
      outbox.splice(0, batch.length);
      if (!result.ok || result.body?.rejected?.length) console.warn("Clew : événements refusés", result.body);
    }
  }

  // Rendering helpers shared with clew-generate's templates.
  function typeset(target) {
    typesetQueue = typesetQueue.then(() => MathJax.startup.promise).then(() => {
      MathJax.typesetClear([target]);
      return MathJax.typesetPromise([target]);
    }).then(() => {
      if (target.querySelector("mjx-merror, [data-mjx-error]")) {
        error("Une formule n'a pas pu être rendue. Vérifiez le contenu mathématique des notes.");
      }
    }).catch(reason => error("Erreur de rendu mathématique : " + reason.message));
    return typesetQueue;
  }
  function required(root, selector) {
    const node = root.querySelector(selector);
    if (!node) throw new Error("Missing template hook: " + selector);
    return node;
  }
  function clone(name) {
    const template = byId("template-" + name);
    if (!(template instanceof HTMLTemplateElement)) throw new Error("Missing HTML template: " + name);
    return document.importNode(template.content, true);
  }
  const slot = (root, name) => required(root, '[data-slot="' + name + '"]');
  const action = (root, name) => required(root, '[data-action="' + name + '"]');
  function content(markup) {
    const fragment = clone("content");
    slot(fragment, "content").innerHTML = markup;
    return fragment;
  }
  /** Open a <details> without recording it as a student action. */
  function openQuietly(details) {
    if (details.open) return;
    details.dataset.quiet = "1";
    details.open = true;
  }

  // Contextual panel: a canvas-local stack of views (no browser history inside the host iframe).
  function build(view) {
    const item = view.question && questions.get(view.question);
    if (view.kind === "course") {
      const course = courses.get(view.id);
      return course && {title: course.title, fragment: content(course.html)};
    }
    if (!item) return null;
    const title = LABELS[view.kind] + " · " + item.label;
    if (view.kind === "method" && item.method) {
      const fragment = clone("method");
      slot(fragment, "content").innerHTML = item.method;
      return {title, fragment};
    }
    if (view.kind === "explanations" && item.explanations.length) {
      const fragment = clone("explanations");
      const container = slot(fragment, "explanations");
      item.explanations.forEach(markup => container.append(content(markup)));
      return {title, fragment};
    }
    if (view.kind === "hints" && item.hints.length) {
      const fragment = clone("hints");
      const container = slot(fragment, "hints");
      const shown = Math.max(1, hints.get(item.address) || 0);
      item.hints.forEach((markup, index) => {
        const hintView = clone("hint");
        const hint = slot(hintView, "hint");
        hint.innerHTML = markup;
        hint.hidden = index >= shown;
        container.append(hintView);
      });
      const reveal = action(fragment, "reveal");
      reveal.hidden = shown >= item.hints.length;
      reveal.addEventListener("click", () => revealHints(item, container, reveal, null));
      return {title, fragment};
    }
    return null;
  }
  /** Reveal the next hint, or every hint up to `target`, and record the highest index. */
  function revealHints(item, container, reveal, target) {
    const all = [...container.querySelectorAll('[data-slot="hint"]')];
    let count = all.filter(hint => !hint.hidden).length;
    for (const hint of all) {
      if (!hint.hidden) continue;
      hint.hidden = false;
      count += 1;
      if (!target || hint.contains(target)) break;
    }
    reveal.hidden = count >= all.length;
    if (count > (hints.get(item.address) || 0)) {
      hints.set(item.address, count);
      record("hint_revealed", {question: item.address, index: count});
    }
    typeset(panel);
  }
  function display(built, scrollTop = 0, focus = true) {
    MathJax.typesetClear?.([panel]);
    panelTitle.textContent = built.title;
    panel.replaceChildren(built.fragment);
    panel.querySelectorAll("[id]").forEach(node => {
      if (document.getElementById(node.id) !== node) node.removeAttribute("id");
    });
    panelBack.hidden = stack.length < 2;
    panelClose.hidden = false;
    aside.classList.add("open");
    aside.scrollTop = scrollTop;
    typeset(panel);
    if (focus) panelTitle.focus({preventScroll: true});
  }
  function recordView(view) {
    if (view.kind === "course") {
      record("course_opened", {course: courses.get(view.id).address});
      return;
    }
    const address = questions.get(view.question).address;
    if (view.kind === "method") record("method_shown", {question: address});
    else if (view.kind === "explanations") record("explanation_opened", {question: address});
    else if (view.kind === "hints" && !(hints.get(address) >= 1)) {
      hints.set(address, 1);
      record("hint_revealed", {question: address, index: 1});
    }
  }
  function openPanel(view, {student = true} = {}) {
    const built = build(view);
    if (!built) return false;
    if (stack.length) stack[stack.length - 1].scroll = aside.scrollTop;
    stack.push(view);
    if (student) recordView(view);
    display(built);
    return true;
  }
  function resetPanel() {
    stack = [];
    MathJax.typesetClear?.([panel]);
    panelTitle.textContent = placeholder.title;
    panel.textContent = placeholder.text;
    panelBack.hidden = true;
    panelClose.hidden = true;
    aside.classList.remove("open");
  }
  function back() {
    stack.pop();
    while (stack.length) {
      const view = stack[stack.length - 1];
      const built = build(view);
      if (built) return display(built, view.scroll || 0);
      stack.pop();
    }
    resetPanel();
  }
  panelBack.addEventListener("click", back);
  panelClose.addEventListener("click", resetPanel);
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && aside.classList.contains("open")) resetPanel();
  });

  function courseButtons(ids, container) {
    ids.forEach(id => {
      const course = courses.get(id);
      if (!course) return;
      const fragment = clone("course-link");
      slot(fragment, "title").textContent = course.title;
      required(fragment, "button").addEventListener("click", () => openPanel({kind: "course", id}));
      container.append(fragment);
    });
  }
  async function ask(item, button) {
    button.disabled = true;
    try {
      await flush();
      const result = await call("ask", {method: "POST", body: JSON.stringify({question: item.address, instance})});
      toast(result.ok ? "Demande envoyée au tuteur : sa réponse s'affiche dans la conversation Copilot."
        : (result.body?.error || "Le tuteur n'est pas joignable pour le moment."));
    } catch {
      toast("Le tuteur n'est pas joignable pour le moment.");
    }
    setTimeout(() => { button.disabled = false; }, 5000);
  }
  function renderQuestion(item) {
    const fragment = clone("question");
    const section = slot(fragment, "question");
    section.id = item.id;
    section.dataset.address = item.address;
    slot(section, "label").textContent = item.label;
    slot(section, "statement").innerHTML = item.html;
    const actions = slot(section, "actions");
    const method = required(section, '[data-help="method"]');
    if (item.method) method.addEventListener("click", () => openPanel({kind: "method", question: item.id}));
    else method.remove();
    const hintButton = required(section, '[data-help="hints"]');
    if (item.hints.length) hintButton.addEventListener("click", () => openPanel({kind: "hints", question: item.id}));
    else hintButton.remove();
    const askButton = action(section, "ask");
    askButton.addEventListener("click", () => ask(item, askButton));
    courseButtons(item.courses, actions);
    actions.append(askButton);
    if (item.corrections.length) {
      const correctionView = clone("correction");
      const correction = slot(correctionView, "correction");
      const answers = slot(correctionView, "answers");
      item.corrections.forEach(markup => answers.append(content(markup)));
      const explanations = required(correctionView, '[data-help="explanations"]');
      if (item.explanations.length) {
        explanations.addEventListener("click", () => openPanel({kind: "explanations", question: item.id}));
      } else explanations.remove();
      courseButtons(item.courses, slot(correctionView, "courses"));
      const toggle = action(correctionView, "correction");
      toggle.addEventListener("click", () => setCorrection(item, correction.hidden, true));
      correction.id = item.id + "-correction";
      toggle.setAttribute("aria-controls", correction.id);
      correctionControls.push({item, correction, toggle});
      section.append(correctionView);
    }
    return section;
  }
  /** Show or hide a question's supplied correction; only one stays open, as in the offline HTML. */
  function setCorrection(item, open, student) {
    for (const entry of correctionControls) {
      const target = entry.item === item;
      const next = target ? open : false;
      if (entry.correction.hidden === !next) continue;
      entry.correction.hidden = !next;
      entry.toggle.textContent = next ? entry.toggle.dataset.labelClose : entry.toggle.dataset.labelOpen;
      entry.toggle.setAttribute("aria-expanded", String(next));
      if (next) typeset(entry.correction);
      if (student) record(next ? "correction_shown" : "correction_hidden", {question: entry.item.address});
    }
  }

  function render(next, nextVersion) {
    const previous = data ? capture() : null;
    data = next;
    version = nextVersion;
    questions = new Map(data.questions.map(item => [item.id, item]));
    questionsByAddress = new Map(data.questions.map(item => [item.address, item]));
    courses = new Map(data.courses.map(item => [item.id, item]));
    coursesByAddress = new Map();
    data.courses.forEach(item => { if (!coursesByAddress.has(item.address)) coursesByAddress.set(item.address, item); });
    exercises = new Map(data.exercises.map(item => [item.address, item]));
    correctionControls = [];
    document.title = data.title;
    byId("title").textContent = data.title;
    const reading = byId("reading");
    const sheet = byId("exercises");
    MathJax.typesetClear?.([reading, sheet]);
    reading.replaceChildren();
    sheet.replaceChildren();
    data.reading.forEach(id => {
      const course = courses.get(id);
      const fragment = clone("course");
      const details = required(fragment, "details");
      details.dataset.address = course.address;
      details.dataset.course = id;
      slot(details, "title").textContent = course.title;
      const body = slot(details, "body");
      body.innerHTML = course.html;
      reading.append(fragment);
      details.addEventListener("toggle", () => {
        if (!details.open) return;
        if (!details.dataset.quiet) record("course_opened", {course: course.address});
        delete details.dataset.quiet;
        typeset(body);
      });
    });
    data.worksheet.forEach(segment => {
      if (!segment.exercise) {
        const fragment = content(segment.html);
        const target = slot(fragment, "content");
        sheet.append(fragment);
        typeset(target);
        return;
      }
      const exercise = exercises.get(segment.exercise);
      const fragment = clone("exercise");
      const details = required(fragment, "details");
      details.dataset.address = exercise.address;
      slot(details, "title").textContent = exercise.title;
      action(details, "start").addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        details.open = true;
      });
      const body = slot(details, "body");
      slot(details, "context").innerHTML = exercise.context;
      exercise.segments.forEach(part => {
        if (part.question) body.append(renderQuestion(questions.get(part.question)));
        else body.append(content(part.html));
      });
      details.addEventListener("toggle", () => {
        if (!details.open) return;
        if (!details.dataset.quiet && !started.has(exercise.address)) {
          started.add(exercise.address);
          record("exercise_started", {exercise: exercise.address});
        }
        delete details.dataset.quiet;
        typeset(body);
      });
      sheet.append(fragment);
    });
    if (previous) restore(previous);
    else resetPanel();
  }
  /** UI state kept across live reloads, keyed by stable addresses. */
  function capture() {
    return {
      open: [...document.querySelectorAll(".sheet details[open]")].map(node => node.dataset.address),
      corrections: correctionControls.filter(entry => !entry.correction.hidden).map(entry => entry.item.address),
      stack: stack.map(view => ({
        kind: view.kind, scroll: view.scroll,
        id: view.kind === "course" ? courses.get(view.id)?.address : questions.get(view.question)?.address,
      })),
      panelScroll: aside.scrollTop,
      scrollY: window.scrollY,
    };
  }
  function restore(state) {
    const opened = new Set(state.open);
    document.querySelectorAll(".sheet details").forEach(node => { if (opened.has(node.dataset.address)) openQuietly(node); });
    state.corrections.forEach(address => {
      const item = questionsByAddress.get(address);
      if (item) setCorrection(item, true, false);
    });
    stack = state.stack.map(view => {
      if (view.kind === "course") {
        const course = coursesByAddress.get(view.id);
        return course && {kind: "course", id: course.id, scroll: view.scroll};
      }
      const item = questionsByAddress.get(view.id);
      return item && {kind: view.kind, question: item.id, scroll: view.scroll};
    }).filter(Boolean);
    while (stack.length && !build(stack[stack.length - 1])) stack.pop();
    if (stack.length) display(build(stack[stack.length - 1]), state.panelScroll, false);
    else resetPanel();
    window.scrollTo(0, state.scrollY);
  }

  // Links: internal anchors stay in the canvas; published external links and PDFs open via the extension.
  function questionOf(node) {
    const section = node.closest(".sheet [data-address].question");
    if (section) return section.dataset.address;
    if (panel.contains(node)) {
      const view = stack[stack.length - 1];
      if (view?.question) return questions.get(view.question)?.address;
    }
    return undefined;
  }
  async function openExternal(href, question) {
    try {
      const result = await call("open", {method: "POST", body: JSON.stringify({href, question})});
      toast(result.ok ? "Ouvert dans le navigateur." : (result.body?.error || "Impossible d'ouvrir ce lien."));
    } catch {
      toast("Impossible d'ouvrir ce lien : le lecteur Clew n'est pas joignable.");
    }
  }
  function followAnchor(event, link) {
    const id = link.hash.slice(1);
    const before = stack.length ? stack[stack.length - 1] : null;
    const courseId = data.course_links[id];
    if (courseId) {
      event.preventDefault();
      openPanel({kind: "course", id: courseId});
      return;
    }
    let target = document.getElementById(id);
    const marker = 'id="' + id + '"';
    if (!target) {
      const course = data.courses.find(item => item.html.includes(marker));
      if (course) {
        openPanel({kind: "course", id: course.id});
        target = document.getElementById(id);
      }
    }
    if (!target) {
      const item = data.questions.find(question => question.method.includes(marker) ||
        question.hints.some(hint => hint.includes(marker)) || question.explanations.some(text => text.includes(marker)));
      if (item) {
        const kind = item.method.includes(marker) ? "method" : item.hints.some(hint => hint.includes(marker)) ? "hints" : "explanations";
        if (kind === "explanations") setCorrection(item, true, true);
        openPanel({kind, question: item.id});
        target = document.getElementById(id);
        if (target?.closest('[data-slot="hint"]')?.hidden) {
          revealHints(item, slot(panel, "hints"), action(panel, "reveal"), target);
        }
      }
    }
    if (!target) return;
    for (let parent = target.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === "DETAILS") parent.open = true;
      if (parent.dataset.slot === "correction" && parent.hidden) {
        const entry = correctionControls.find(control => control.correction === parent);
        if (entry) setCorrection(entry.item, true, true);
      }
    }
    typeset(target.parentElement);
    if ((stack.length ? stack[stack.length - 1] : null) !== before) {
      event.preventDefault();
      target.scrollIntoView({block: "start"});
    }
  }
  document.addEventListener("click", event => {
    const link = event.target.closest("a[href]");
    if (!link || !data) return;
    const href = link.getAttribute("href");
    if (href.startsWith("#")) {
      followAnchor(event, link);
      return;
    }
    event.preventDefault();
    openExternal(href, questionOf(link));
  });

  // Tutor "show": scroll to and highlight a target without recording a student action.
  function highlight(node) {
    node.classList.remove("clew-shown");
    void node.offsetWidth;
    node.classList.add("clew-shown");
    setTimeout(() => node.classList.remove("clew-shown"), 6000);
  }
  function show(message) {
    if (!data) return;
    if (message.kind === "course") {
      const reading = document.querySelector('#reading details[data-address="' + CSS.escape(message.address) + '"]');
      const course = coursesByAddress.get(message.address);
      if (reading) {
        openQuietly(reading);
        reading.scrollIntoView({block: "start", behavior: "smooth"});
        highlight(reading);
      } else if (course) {
        openPanel({kind: "course", id: course.id}, {student: false});
        highlight(panel);
      }
      if (course) toast("Le tuteur vous montre : " + course.title);
      return;
    }
    const node = document.querySelector('.sheet [data-address="' + CSS.escape(message.address) + '"]');
    if (!node) return;
    for (let parent = node; parent; parent = parent.parentElement) {
      if (parent.tagName === "DETAILS") openQuietly(parent);
    }
    node.scrollIntoView({block: "start", behavior: "smooth"});
    highlight(node);
    const title = message.kind === "question" ? questionsByAddress.get(message.address)?.label
      : exercises.get(message.address)?.title;
    if (title) toast("Le tuteur vous montre : " + title);
  }

  // Data, status and the live stream.
  let loading = false;
  let reloadAgain = false;
  async function load() {
    if (loading) {
      reloadAgain = true;
      return;
    }
    loading = true;
    try {
      const response = await fetch(base + "api/data" + query, {cache: "no-store", headers: {"x-clew-token": token}});
      if (response.status === 503) {
        showStatus(await response.json(), false);
        return;
      }
      if (!response.ok) throw new Error((await response.json().catch(() => null))?.error || "HTTP " + response.status);
      const next = await response.json();
      const nextVersion = Number(response.headers.get("X-Clew-Version")) || 0;
      const state = await call("state");
      if (state.ok) {
        Object.entries(state.body.hints || {}).forEach(([address, count]) => {
          hints.set(address, Math.max(count, hints.get(address) || 0));
        });
        (state.body.started || []).forEach(address => started.add(address));
      }
      render(next, nextVersion);
    } catch (reason) {
      if (!data) error("Impossible de charger la publication : " + reason.message);
    } finally {
      loading = false;
      if (reloadAgain) {
        reloadAgain = false;
        load();
      }
    }
  }
  function showStatus(state, reload = true) {
    const line = byId("status");
    let text = STATUS[state.status] ?? "";
    if ((state.status === "error" || state.status === "stale") && state.error) text += " : " + state.error;
    line.textContent = text;
    line.hidden = !text;
    line.dataset.status = state.status;
    if (reload && state.version && state.version !== version) load();
  }
  let pausedTimer = 0;
  function connect() {
    const stream = new EventSource(base + "api/stream" + query);
    stream.onopen = () => {
      clearTimeout(pausedTimer);
      pausedTimer = 0;
      byId("server-error").hidden = true;
      flush();
    };
    stream.onmessage = event => {
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (message.type === "status") showStatus(message);
      else if (message.type === "show") show(message);
    };
    stream.onerror = () => {
      // Reconnection attempts fail every few seconds while the session is away; keep the first timer.
      if (pausedTimer) return;
      pausedTimer = setTimeout(() => {
        pausedTimer = 0;
        if (stream.readyState !== EventSource.OPEN) byId("server-error").hidden = false;
      }, 3500);
    };
  }

  MathJax.startup.promise.catch(reason => error("Impossible d'initialiser les mathématiques : " + reason.message));
  resetPanel();
  connect();
  load();
})();
