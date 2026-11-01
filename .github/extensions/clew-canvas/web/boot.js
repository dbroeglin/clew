// Runs before MathJax and the stylesheet-dependent UI: theme selection and MathJax configuration.
(() => {
  "use strict";
  const root = document.documentElement;
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  function apply() {
    const host = root.getAttribute("data-color-mode") || document.body?.getAttribute("data-color-mode");
    const theme = host === "dark" || host === "light" ? host : media.matches ? "dark" : "light";
    if (root.getAttribute("data-theme") !== theme) root.setAttribute("data-theme", theme);
  }
  apply();
  media.addEventListener?.("change", apply);
  new MutationObserver(apply).observe(root, {attributes: true, attributeFilter: ["data-color-mode"]});
  document.addEventListener("DOMContentLoaded", () => {
    apply();
    new MutationObserver(apply).observe(document.body, {attributes: true, attributeFilter: ["data-color-mode"]});
  });
})();

window.MathJax = {
  loader: {load: []},
  tex: {
    packages: ["base", "ams", "newcommand", "configmacros"],
    inlineMath: [["$", "$"]],
    displayMath: [["$$", "$$"]],
    macros: {llbracket: "\\lbrack\\!\\lbrack", rrbracket: "\\rbrack\\!\\rbrack"},
  },
  svg: {fontCache: "local"},
  startup: {typeset: false},
  options: {
    enableMenu: false,
    skipHtmlTags: ["script", "noscript", "style", "textarea", "pre", "code"],
  },
};
