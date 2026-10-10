"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ROOT = path.resolve(__dirname, "..", "..");
const {checkMath, VERSION, PACKAGES, MACROS} = require(
  path.join(ROOT, ".agents", "skills", "clew-import", "scripts", "check_math.cjs")
);
const expression = (id, tex, display = false) => ({id, tex, display});

test("valid inline, display, AMS, configured macros and source-owned mistakes render", () => {
  const report = checkMath({context: [], expressions: [
    expression(1, "\\mathbb{R}\\quad x\\leq y"),
    expression(2, "\\begin{aligned}x&=\\frac{1}{2}\\\\y&=0\\end{aligned}", true),
    expression(3, "\\llbracket 1,n\\rrbracket"),
    expression(4, "\\boxed{u_n\\sim v_n\\nRightarrow\\ln(u_n)\\sim\\ln(v_n)}", true),
    expression(5, "1+1=3"),
  ]});
  assert.equal(report.mathjax_version, "3.2.2");
  assert.deepEqual(report.results.map(result => result.errors), [[], [], [], [], []]);
});

test("known transcription failures yield renderer errors, not success-shaped SVG", () => {
  const expressions = [
    "\\bb{R}", "\\varphi:\\mathbb{N}\\to\\mathbb{N}}",
    "\\begin{aligned}x&=y\\tag{3}\\end{aligned}",
    "\\frac{1}", "\\unavailablecommand{x}", "\\require{color}", "\\href{https://example.com}{x}",
  ].map((tex, index) => expression(index + 1, tex, index === 2));
  const report = checkMath({context: [], expressions});
  assert.ok(report.results.every(result => result.errors.length > 0));
  assert.match(report.results[0].errors[0], /Undefined control sequence \\bb/);
  assert.match(report.results[1].errors[0], /Extra close brace/);
  assert.match(report.results[2].errors[0], /tag not allowed in aligned/);
});

test("unexpected controls are rejected before they can crash MathJax", () => {
  const report = checkMath({context: [], expressions: [
    expression(1, "\x08oldsymbol{R}"), expression(2, "\x1b[1m\\mathcal{D}_f"),
    expression(3, "\n\\frac{1}{2}\r\n\t"),
  ]});
  assert.match(report.results[0].errors[0], /U\+0008/);
  assert.match(report.results[1].errors[0], /U\+001B/);
  assert.deepEqual(report.results[2].errors, []);
});

test("macro definitions persist within a page and selected prior context, not between attempts", () => {
  const context = [expression(1, "\\newcommand{\\printedmacro}{\\mathbb{R}}")];
  const report = checkMath({context, expressions: [
    expression(1, "\\printedmacro"), expression(2, "\\newcommand{\\pagemacro}{x}"),
    expression(3, "\\pagemacro^2"),
  ]});
  assert.deepEqual(report.results.map(result => result.errors), [[], [], []]);
  const fresh = checkMath({context: [], expressions: [expression(1, "\\pagemacro")]});
  assert.match(fresh.results[0].errors[0], /Undefined control sequence/);
});

test("unsupported extensions are not silently loaded", () => {
  const report = checkMath({context: [], expressions: [
    expression(1, "\\cancel{x}"), expression(2, "\\boldsymbol{R}"),
  ]});
  assert.ok(report.results.every(result => result.errors.length > 0));
});

test("malformed protocol is a checker failure", () => {
  for (const batch of [
    {expressions: []},
    {context: [], expressions: [{id: 1, tex: "x", display: "false"}]},
    {context: [], expressions: [expression(1, "x"), expression(1, "y")]},
  ]) {
    assert.throws(() => checkMath(batch));
  }
});

test("declared version, packages and macros match offline Generate without runtime coupling", () => {
  const template = fs.readFileSync(path.join(ROOT, ".agents", "skills", "clew-generate", "assets", "template.html"), "utf8");
  const configuration = template.match(/window\.MathJax = \{[\s\S]*?\n\};/)[0];
  const context = {window: {}};
  vm.runInNewContext(configuration, context);
  assert.deepEqual(Array.from(context.window.MathJax.tex.packages), PACKAGES);
  assert.deepEqual(JSON.parse(JSON.stringify(context.window.MathJax.tex.macros)), MACROS);
  assert.equal(require(path.join(ROOT, "node_modules", "mathjax-full", "package.json")).version, VERSION);
  assert.deepEqual(
    fs.readFileSync(path.join(ROOT, "node_modules", "mathjax-full", "es5", "tex-svg.js")),
    fs.readFileSync(path.join(ROOT, ".agents", "skills", "clew-generate", "assets", "mathjax", "tex-svg.js")),
  );
});

test("npm workspace has one root lock and a fully hoisted dependency tree", () => {
  const lock = JSON.parse(fs.readFileSync(path.join(ROOT, "package-lock.json"), "utf8"));
  assert.deepEqual(lock.packages[""].workspaces, [".agents/skills/clew-import"]);
  assert.ok(!Object.keys(lock.packages).some(reference =>
    /^\.agents.*node_modules/.test(reference) || /node_modules.*node_modules/.test(reference)));
  assert.ok(!fs.existsSync(path.join(ROOT, ".agents", "skills", "clew-import", "node_modules")));
  assert.ok(!fs.existsSync(path.join(ROOT, ".agents", "skills", "clew-import", "package-lock.json")));
});
