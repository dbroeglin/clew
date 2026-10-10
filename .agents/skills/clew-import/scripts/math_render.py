"""Browser-free, offline MathJax validation for candidate Markdown."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from pydantic import BaseModel, ConfigDict, ValidationError

HELPER = Path(__file__).with_name("check_math.cjs")
VERSION = "3.2.2"
PACKAGES = ["base", "ams", "newcommand", "configmacros"]
MACROS = {"llbracket": r"\lbrack\!\lbrack", "rrbracket": r"\rbrack\!\rbrack"}


class MathRenderError(Exception):
    """The local rendering check could not run reliably."""


class RenderResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: int
    errors: list[str]


class RenderReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1]
    mathjax_version: Literal["3.2.2"]
    packages: list[str]
    macros: dict[str, str]
    results: list[RenderResult]


def math_expressions(markdown: str) -> list[dict[str, object]]:
    # Match publication parsing without importing or depending on Generate.
    parser = MarkdownIt("commonmark", {"html": False}).enable("table").use(dollarmath_plugin)
    try:
        tokens = parser.parse(markdown)
    except (ValueError, TypeError, RecursionError) as error:
        raise MathRenderError(f"Cannot parse Markdown mathematics: {error}") from error
    expressions: list[dict[str, object]] = []
    for token in tokens:
        if token.map is None:
            continue
        children = [token] if token.type.startswith("math_block") else token.children or []
        for child in children:
            if child.type == "math_inline" or child.type.startswith("math_block"):
                expressions.append({
                    "id": len(expressions) + 1, "tex": child.content,
                    "display": child.type != "math_inline",
                    "start_line": token.map[0] + 1, "end_line": token.map[1],
                })
    return expressions


def wire_expressions(expressions: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {"id": index, "tex": expression["tex"], "display": expression["display"]}
        for index, expression in enumerate(expressions, 1)
    ]


def run_checker(batch: dict[str, object]) -> RenderReport:
    node = shutil.which("node")
    if node is None:
        raise MathRenderError("Node.js >=22 is required for MathJax validation; install Node separately.")
    try:
        process = subprocess.run(
            [node, str(HELPER)], input=json.dumps(batch, ensure_ascii=False),
            capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
        )
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
        raise MathRenderError(f"Cannot run local MathJax checker: {error}") from error
    if process.returncode != 0:
        raise MathRenderError(
            f"Local MathJax checker exited {process.returncode}; check the Node runtime, "
            f"locked dependencies, and run diagnostics. Details: {process.stderr.strip()}"
        )
    if process.stderr.strip():
        raise MathRenderError(f"Unexpected MathJax checker diagnostics: {process.stderr.strip()}")
    try:
        report = RenderReport.model_validate_json(process.stdout)
    except ValidationError as error:
        raise MathRenderError(f"Invalid MathJax checker report: {error}") from error
    expressions = batch["expressions"]
    if (
        report.packages != PACKAGES or report.macros != MACROS
        or [result.id for result in report.results] != [item["id"] for item in expressions]
        or any(not message.strip() for result in report.results for message in result.errors)
    ):
        raise MathRenderError("MathJax checker configuration, result IDs, or errors are inconsistent.")
    return report


def check_math_runtime() -> None:
    report = run_checker({
        "context": [], "expressions": [{"id": 1, "tex": r"\frac{1}{2}", "display": False}],
    })
    if report.results[0].errors:
        raise MathRenderError("MathJax could not render its preflight test expression.")


def check_math(
    markdown: str, page_number: int, context: list[dict[str, object]],
) -> tuple[dict[str, object], list[str], list[dict[str, object]]]:
    expressions = math_expressions(markdown)
    report = run_checker({
        "context": wire_expressions(context), "expressions": wire_expressions(expressions),
    })
    checked = [
        {**expression, "errors": result.errors}
        for expression, result in zip(expressions, report.results, strict=True)
    ]
    issues = []
    for expression in checked:
        for message in expression["errors"]:
            first, last = expression["start_line"], expression["end_line"]
            location = f"line {first}" if first == last else f"lines {first}-{last}"
            issues.append(
                f"Page {page_number}, {location}, math expression {expression['id']}: "
                f"MathJax: {message} in {expression['tex']!r}"
            )
    return {
        "schema_version": 1, "mathjax_version": report.mathjax_version,
        "packages": report.packages, "macros": report.macros,
        "context_expressions": len(context), "expressions": checked,
    }, issues, expressions
