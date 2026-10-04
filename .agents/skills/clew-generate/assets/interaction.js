(() => {
  "use strict";
  const data = JSON.parse(document.getElementById("publication").textContent);
  const questions = new Map(data.questions.map(item => [item.id, item]));
  const courses = new Map(data.courses.map(item => [item.id, item]));
  const panel = document.getElementById("panel-content");
  const panelTitle = document.getElementById("panel-title");
  let queue = Promise.resolve();

  function error(message) {
    const box = document.getElementById("error");
    box.hidden = false;
    box.textContent = message;
  }
  function typeset(target) {
    queue = queue.then(() => MathJax.startup.promise).then(() => {
      MathJax.typesetClear([target]);
      return MathJax.typesetPromise([target]);
    }).then(() => {
      if (target.querySelector("mjx-merror, [data-mjx-error]")) {
        error("Une formule n'a pas pu être rendue. Vérifiez le contenu mathématique des notes.");
      }
    }).catch(reason => error("Erreur de rendu mathématique : " + reason.message));
    return queue;
  }
  function required(root, selector) {
    const node = root.querySelector(selector);
    if (!node) throw new Error("Missing template hook: " + selector);
    return node;
  }
  function clone(name) {
    const template = document.getElementById("template-" + name);
    if (!(template instanceof HTMLTemplateElement)) {
      throw new Error("Missing HTML template: " + name);
    }
    return document.importNode(template.content, true);
  }
  function slot(root, name) {
    return required(root, '[data-slot="' + name + '"]');
  }
  function action(root, name) {
    return required(root, '[data-action="' + name + '"]');
  }
  function content(markup) {
    const fragment = clone("content");
    slot(fragment, "content").innerHTML = markup;
    return fragment;
  }
  function setPanel(title, fragment) {
    MathJax.typesetClear([panel]);
    panelTitle.textContent = title;
    panel.replaceChildren(fragment);
    panel.querySelectorAll("[id]").forEach(node => {
      if (document.getElementById(node.id) !== node) node.removeAttribute("id");
    });
    typeset(panel);
    panelTitle.focus({preventScroll: true});
    if (window.innerWidth <= 1000) panelTitle.scrollIntoView({block: "start"});
  }
  function courseButtons(ids, container) {
    ids.forEach(id => {
      const course = courses.get(id);
      const fragment = clone("course-link");
      slot(fragment, "title").textContent = course.title;
      required(fragment, "button").addEventListener("click", () =>
        setPanel(course.title, content(course.html)));
      container.append(fragment);
    });
  }
  const correctionControls = [];
  function renderQuestion(item) {
    const fragment = clone("question");
    const section = slot(fragment, "question");
    section.id = item.id;
    slot(section, "label").textContent = item.label;
    slot(section, "statement").innerHTML = item.html;
    const actions = slot(section, "actions");
    const method = required(section, '[data-help="method"]');
    if (item.method) {
      method.addEventListener("click", () => {
        const methodView = clone("method");
        slot(methodView, "content").innerHTML = item.method;
        setPanel(method.textContent + " · " + item.label, methodView);
      });
    } else method.remove();
    const hints = required(section, '[data-help="hints"]');
    if (item.hints.length) {
      hints.addEventListener("click", () => {
        const hintsView = clone("hints");
        const container = slot(hintsView, "hints");
        item.hints.forEach((markup, index) => {
          const hintView = clone("hint");
          const hint = slot(hintView, "hint");
          hint.innerHTML = markup;
          hint.hidden = index > 0;
          container.append(hintView);
        });
        const reveal = action(hintsView, "reveal");
        reveal.addEventListener("click", () => {
          const next = container.querySelector('[data-slot="hint"][hidden]');
          if (next) next.hidden = false;
          reveal.hidden = !container.querySelector('[data-slot="hint"][hidden]');
          typeset(panel);
        });
        reveal.hidden = item.hints.length < 2;
        setPanel(hints.textContent + " · " + item.label, hintsView);
      });
    } else hints.remove();
    courseButtons(item.courses, actions);
    if (item.corrections.length) {
      const correctionView = clone("correction");
      const correction = slot(correctionView, "correction");
      const answers = slot(correctionView, "answers");
      item.corrections.forEach(markup => answers.append(content(markup)));
      const explanations = required(correctionView, '[data-help="explanations"]');
      if (item.explanations.length) {
        explanations.addEventListener("click", () => {
          const view = clone("explanations");
          const container = slot(view, "explanations");
          item.explanations.forEach(markup => container.append(content(markup)));
          setPanel(explanations.textContent + " · " + item.label, view);
        });
      } else explanations.remove();
      courseButtons(item.courses, slot(correctionView, "courses"));
      const toggle = action(correctionView, "correction");
      toggle.addEventListener("click", () => {
        const open = correction.hidden;
        correctionControls.forEach(([other, control]) => {
          other.hidden = true;
          control.textContent = control.dataset.labelOpen;
          control.setAttribute("aria-expanded", "false");
        });
        correction.hidden = !open;
        toggle.textContent = open ? toggle.dataset.labelClose : toggle.dataset.labelOpen;
        toggle.setAttribute("aria-expanded", String(open));
        if (open) typeset(correction);
      });
      correction.id = item.id + "-correction";
      toggle.setAttribute("aria-controls", correction.id);
      correctionControls.push([correction, toggle]);
      section.append(correctionView);
    }
    return section;
  }
  data.reading.forEach(id => {
    const course = courses.get(id);
    const fragment = clone("course");
    const details = required(fragment, "details");
    slot(details, "title").textContent = course.title;
    const body = slot(details, "body");
    body.innerHTML = course.html;
    document.getElementById("reading").append(fragment);
    details.addEventListener("toggle", () => { if (details.open) typeset(body); });
  });
  data.exercises.forEach(exercise => {
    const fragment = clone("exercise");
    const details = required(fragment, "details");
    slot(details, "title").textContent = exercise.title;
    action(details, "start").addEventListener("click", event => {
      event.preventDefault();
      event.stopPropagation();
      details.open = true;
    });
    const body = slot(details, "body");
    slot(details, "context").innerHTML = exercise.context;
    exercise.segments.forEach(segment => {
      if (segment.question) body.append(renderQuestion(questions.get(segment.question)));
      else body.append(content(segment.html));
    });
    details.addEventListener("toggle", () => { if (details.open) typeset(body); });
    document.getElementById("exercises").append(fragment);
  });
  document.addEventListener("click", event => {
    const link = event.target.closest('a[href^="#"]');
    if (!link) return;
    const courseId = data.course_links[link.hash.slice(1)];
    if (courseId) {
      event.preventDefault();
      const course = courses.get(courseId);
      setPanel(course.title, content(course.html));
      return;
    }
    let target = document.getElementById(link.hash.slice(1));
    if (!target) {
      const course = data.courses.find(item =>
        item.html.includes('id="' + link.hash.slice(1) + '"'));
      if (course) {
        setPanel(course.title, content(course.html));
        target = document.getElementById(link.hash.slice(1));
      }
      if (!target) {
        const marker = 'id="' + link.hash.slice(1) + '"';
        const item = data.questions.find(question =>
          question.method.includes(marker) || question.hints.some(hint => hint.includes(marker)) ||
          question.explanations.some(explanation => explanation.includes(marker)));
        if (item) {
          const kind = item.method.includes(marker) ? "method" :
            item.hints.some(hint => hint.includes(marker)) ? "hints" : "explanations";
          const section = document.getElementById(item.id);
          if (kind === "explanations") {
            const correction = required(section, '[data-slot="correction"]');
            if (correction.hidden) action(section, "correction").click();
          }
          section.querySelector('[data-help="' + kind + '"]').click();
          target = document.getElementById(link.hash.slice(1));
          if (target?.closest('[data-slot="hint"]')) {
            for (const hint of panel.querySelectorAll('[data-slot="hint"]')) {
              hint.hidden = false;
              if (hint.contains(target)) break;
            }
            action(panel, "reveal").hidden = !panel.querySelector('[data-slot="hint"][hidden]');
          }
        }
      }
    }
    if (target) {
      for (let parent = target.parentElement; parent; parent = parent.parentElement) {
        if (parent.tagName === "DETAILS") parent.open = true;
        if (parent.dataset.slot === "correction") {
          const entry = correctionControls.find(([node]) => node === parent);
          if (entry && parent.hidden) entry[1].click();
        }
      }
      typeset(target.parentElement);
    }
  });
  MathJax.startup.promise.catch(reason => error("Impossible d'initialiser les mathématiques : " + reason.message));
})();
