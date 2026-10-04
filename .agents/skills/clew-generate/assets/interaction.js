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
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }
  function button(text, handler) {
    const node = element("button", "", text);
    node.type = "button";
    node.addEventListener("click", handler);
    return node;
  }
  function setPanel(title, markup) {
    MathJax.typesetClear([panel]);
    panelTitle.textContent = title;
    panel.innerHTML = markup;
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
      container.append(button("Cours · " + course.title, () => setPanel(course.title, course.html)));
    });
  }
  const correctionControls = [];
  function renderQuestion(item) {
    const section = element("section", "question");
    section.id = item.id;
    section.append(element("span", "question-label", item.label));
    const statement = element("div");
    statement.innerHTML = item.html;
    section.append(statement);
    const actions = element("div", "actions");
    if (item.method) {
      const method = button("Méthode", () =>
        setPanel("Méthode · " + item.label,
          '<p class="aid-label">Aide ajoutée · distincte de la correction fournie</p>' + item.method));
      method.dataset.help = "method";
      actions.append(method);
    }
    if (item.hints.length) {
      const hints = button("Indices", () => {
      setPanel("Indices · " + item.label, '<p class="aid-label">Aides ajoutées · révélation progressive</p>');
      item.hints.forEach((markup, index) => {
        const hint = element("div", "hint");
        hint.innerHTML = markup;
        hint.hidden = index > 0;
        panel.append(hint);
      });
      const reveal = button("Révéler l'indice suivant", () => {
        const next = panel.querySelector(".hint[hidden]");
        if (next) next.hidden = false;
        reveal.hidden = !panel.querySelector(".hint[hidden]");
        typeset(panel);
      });
      reveal.hidden = item.hints.length < 2;
      panel.append(reveal);
      typeset(panel);
      });
      hints.dataset.help = "hints";
      actions.append(hints);
    }
    courseButtons(item.courses, actions);
    section.append(actions);
    if (item.corrections.length) {
      const correction = element("div", "correction");
      correction.hidden = true;
      correction.innerHTML = '<p class="correction-title">Correction fournie</p>' +
        item.corrections.map(markup => '<div>' + markup + '</div>').join("");
      const courseActions = element("div", "actions");
      courseButtons(item.courses, courseActions);
      correction.append(courseActions);
      const toggle = button("Afficher la correction", () => {
        const open = correction.hidden;
        correctionControls.forEach(([other, control]) => {
          other.hidden = true;
          control.textContent = "Afficher la correction";
          control.setAttribute("aria-expanded", "false");
        });
        correction.hidden = !open;
        toggle.textContent = open ? "Masquer la correction" : "Afficher la correction";
        toggle.setAttribute("aria-expanded", String(open));
        if (open) typeset(correction);
      });
      correction.id = item.id + "-correction";
      toggle.setAttribute("aria-controls", correction.id);
      toggle.setAttribute("aria-expanded", "false");
      correctionControls.push([correction, toggle]);
      section.append(toggle, correction);
    }
    return section;
  }
  data.reading.forEach(id => {
    const course = courses.get(id);
    const details = element("details");
    details.append(element("summary", "", course.title));
    const body = element("div", "course-body");
    body.innerHTML = course.html;
    details.append(body);
    document.getElementById("reading").append(details);
    details.addEventListener("toggle", () => { if (details.open) typeset(body); });
  });
  data.exercises.forEach(exercise => {
    const details = element("details", "exercise");
    const summary = element("summary");
    summary.append(element("span", "exercise-title", exercise.title));
    const start = button("Commencer l'exercice", event => {
      event.preventDefault();
      event.stopPropagation();
      details.open = true;
    });
    start.className = "start";
    summary.append(start);
    const body = element("div", "exercise-body");
    const context = element("div");
    context.innerHTML = exercise.context;
    body.append(context);
    exercise.segments.forEach(segment => {
      if (segment.question) body.append(renderQuestion(questions.get(segment.question)));
      else {
        const shared = element("div");
        shared.innerHTML = segment.html;
        body.append(shared);
      }
    });
    details.append(summary, body);
    details.addEventListener("toggle", () => { if (details.open) typeset(body); });
    document.getElementById("exercises").append(details);
  });
  document.addEventListener("click", event => {
    const link = event.target.closest('a[href^="#"]');
    if (!link) return;
    let target = document.getElementById(link.hash.slice(1));
    if (!target) {
      const course = data.courses.find(item =>
        item.html.includes('id="' + link.hash.slice(1) + '"'));
      if (course) {
        setPanel(course.title, course.html);
        target = document.getElementById(link.hash.slice(1));
      }
      if (!target) {
        const marker = 'id="' + link.hash.slice(1) + '"';
        const item = data.questions.find(question =>
          question.method.includes(marker) || question.hints.some(hint => hint.includes(marker)));
        if (item) {
          const kind = item.method.includes(marker) ? "method" : "hints";
          document.getElementById(item.id).querySelector('[data-help="' + kind + '"]').click();
          target = document.getElementById(link.hash.slice(1));
          if (target?.closest(".hint")) {
            for (const hint of panel.querySelectorAll(".hint")) {
              hint.hidden = false;
              if (hint.contains(target)) break;
            }
            panel.querySelector("button").hidden = !panel.querySelector(".hint[hidden]");
          }
        }
      }
    }
    if (target) {
      for (let parent = target.parentElement; parent; parent = parent.parentElement) {
        if (parent.tagName === "DETAILS") parent.open = true;
        if (parent.classList.contains("correction")) {
          const entry = correctionControls.find(([node]) => node === parent);
          if (entry && parent.hidden) entry[1].click();
        }
      }
      typeset(target.parentElement);
    }
  });
  MathJax.startup.promise.catch(reason => error("Impossible d'initialiser les mathématiques : " + reason.message));
})();
