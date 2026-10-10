"use strict";

const fs = require("node:fs");
const {mathjax} = require("mathjax-full/js/mathjax.js");
const {TeX} = require("mathjax-full/js/input/tex.js");
const {SVG} = require("mathjax-full/js/output/svg.js");
const {liteAdaptor} = require("mathjax-full/js/adaptors/liteAdaptor.js");
const {RegisterHTMLHandler} = require("mathjax-full/js/handlers/html.js");
require("mathjax-full/js/input/tex/ams/AmsConfiguration.js");
require("mathjax-full/js/input/tex/newcommand/NewcommandConfiguration.js");
require("mathjax-full/js/input/tex/configmacros/ConfigMacrosConfiguration.js");

const VERSION = "3.2.2";
const PACKAGES = ["base", "ams", "newcommand", "configmacros"];
const MACROS = {llbracket: "\\lbrack\\!\\lbrack", rrbracket: "\\rbrack\\!\\rbrack"};
const ACTIVE_COMMAND = /\\(?:require|href|url|htmlClass|htmlId|htmlStyle|includegraphics)\b/;

function validateBatch(batch) {
  if (!batch || Object.keys(batch).sort().join(",") !== "context,expressions") {
    throw new Error("Expected context and expressions arrays.");
  }
  for (const group of [batch.context, batch.expressions]) {
    if (!Array.isArray(group)) throw new Error("Expected an array of expressions.");
    for (const expression of group) {
      if (!expression || Object.keys(expression).sort().join(",") !== "display,id,tex"
          || !Number.isInteger(expression.id) || expression.id < 1
          || typeof expression.tex !== "string" || typeof expression.display !== "boolean") {
        throw new Error("Invalid math expression.");
      }
    }
    if (new Set(group.map(expression => expression.id)).size !== group.length) {
      throw new Error("Duplicate math expression IDs.");
    }
  }
}

function checkMath(batch) {
  validateBatch(batch);
  if (Number(process.versions.node.split(".")[0]) < 22) throw new Error("Node.js >=22 is required.");
  if (require("mathjax-full/package.json").version !== VERSION) {
    throw new Error(`Expected mathjax-full ${VERSION}; install the locked npm dependencies.`);
  }
  const adaptor = liteAdaptor();
  RegisterHTMLHandler(adaptor);
  let errors = [];
  const tex = new TeX({
    packages: PACKAGES,
    macros: MACROS,
    formatError(jax, error) {
      errors.push(error.message);
      return jax.formatError(error);
    }
  });
  const document = mathjax.document("", {
    InputJax: tex,
    OutputJax: new SVG({fontCache: "local"}),
    compileError(_document, _math, error) { throw error; },
    typesetError(_document, _math, error) { throw error; }
  });
  function convert(expression) {
    errors = [];
    const controls = [...new Set(expression.tex.match(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g) || [])];
    if (controls.length) {
      errors.push("Unexpected control characters " + controls.map(
        character => "U+" + character.codePointAt(0).toString(16).toUpperCase().padStart(4, "0")
      ).join(", ") + ".");
    } else if (ACTIVE_COMMAND.test(expression.tex)) {
      errors.push("Unsupported active or externally loaded TeX command.");
    } else {
      const node = document.convert(expression.tex, {display: expression.display});
      if (adaptor.tags(node, "g").some(item => adaptor.getAttribute(item, "data-mml-node") === "merror")
          && errors.length === 0) {
        errors.push("MathJax produced an error node.");
      }
    }
    return {id: expression.id, errors: [...new Set(errors)]};
  }
  // Replay only selected prior pages, never discarded attempts, to recover macro context.
  for (const expression of batch.context) convert(expression);
  return {
    schema_version: 1, mathjax_version: VERSION,
    packages: PACKAGES, macros: MACROS,
    results: batch.expressions.map(convert)
  };
}

if (require.main === module) {
  try {
    const batch = process.argv[2] === "--check"
      ? {context: [], expressions: [{id: 1, tex: "\\frac{1}{2}", display: false}]}
      : JSON.parse(fs.readFileSync(0, "utf8"));
    process.stdout.write(JSON.stringify(checkMath(batch)) + "\n");
  } catch (error) {
    process.stderr.write(`MathJax checker failed: ${error.message}\n`);
    process.exitCode = 1;
  }
}

module.exports = {checkMath, VERSION, PACKAGES, MACROS};
