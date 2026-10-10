from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_digest_pdf import ingestion
import math_render


class MathRenderingTests(unittest.TestCase):
    def test_parser_matches_publication_math_and_excludes_code_paths_and_image_alt(self):
        markdown = (
            "# Heading $x$\n\n"
            "> quoted $y$\n\n"
            "| First | Second |\n| --- | --- |\n| $z$ | `ignored $a$` |\n\n"
            "![ignored $b$](figure.png)\n\n"
            "```\n$ignored$\n```\n\n"
            "$$\n\\frac{1}{2}\n$$\n"
        )
        expressions = math_render.math_expressions(markdown)
        self.assertEqual([item["tex"] for item in expressions], ["x", "y", "z", "\n\\frac{1}{2}\n"])
        self.assertEqual([item["display"] for item in expressions], [False, False, False, True])
        self.assertEqual(expressions[0]["start_line"], 1)
        self.assertEqual(expressions[-1]["start_line"], 15)
        self.assertEqual(expressions[-1]["end_line"], 17)

    def test_real_renderer_returns_located_errors_without_mutating_input(self):
        markdown = "# Source\n\n$\\bb{R}$ and $\\mathbb{R}$.\n"
        report, issues, expressions = math_render.check_math(markdown, 8, [])
        self.assertEqual(len(report["expressions"]), 2)
        self.assertEqual(report["expressions"][0]["tex"], expressions[0]["tex"])
        self.assertIn("Page 8, line 3, math expression 1", issues[0])
        self.assertIn(r"Undefined control sequence \bb", issues[0])
        self.assertEqual(report["expressions"][1]["errors"], [])
        self.assertEqual(markdown, "# Source\n\n$\\bb{R}$ and $\\mathbb{R}$.\n")

    def test_selected_context_is_replayed_and_new_candidate_context_is_fresh(self):
        context = math_render.math_expressions(r"$\newcommand{\printedmacro}{x}$")
        report, issues, _ = math_render.check_math(r"$\printedmacro^2$", 2, context)
        self.assertEqual(issues, [])
        self.assertEqual(report["context_expressions"], 1)
        _, issues, _ = math_render.check_math(r"$\printedmacro^2$", 2, [])
        self.assertIn("Undefined control sequence", issues[0])

    def test_renderer_failures_are_explicit_not_render_passes(self):
        with patch.object(math_render.shutil, "which", return_value=None):
            with self.assertRaisesRegex(math_render.MathRenderError, "Node.js >=22"):
                math_render.check_math_runtime()
        for failure in (
            OSError("Cannot launch"), UnicodeError("Cannot decode"),
            subprocess.TimeoutExpired("node", 60),
        ):
            with patch.object(math_render.subprocess, "run", side_effect=failure):
                with self.assertRaisesRegex(math_render.MathRenderError, "Cannot run"):
                    math_render.check_math_runtime()
        valid = {
            "schema_version": 1, "mathjax_version": "3.2.2", "packages": math_render.PACKAGES,
            "macros": math_render.MACROS, "results": [{"id": 1, "errors": []}],
        }
        invalid = [
            SimpleNamespace(returncode=1, stderr="Missing mathjax-full", stdout=""),
            SimpleNamespace(returncode=0, stderr="Unexpected warning", stdout=json.dumps(valid)),
            SimpleNamespace(returncode=0, stderr="", stdout="not JSON"),
            SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({**valid, "results": []})),
            SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({**valid, "mathjax_version": "4.0.0"})),
            SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({**valid, "packages": ["base"]})),
        ]
        for result in invalid:
            with self.subTest(result=result), patch.object(math_render.subprocess, "run", return_value=result):
                with self.assertRaises(math_render.MathRenderError):
                    math_render.check_math_runtime()

    def test_subprocess_is_one_offline_batch_without_shell_or_browser(self):
        report = {
            "schema_version": 1, "mathjax_version": "3.2.2", "packages": math_render.PACKAGES,
            "macros": math_render.MACROS, "results": [{"id": 1, "errors": []}, {"id": 2, "errors": []}],
        }
        with patch.object(math_render.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stderr="", stdout=json.dumps(report),
        )) as run:
            math_render.check_math("$x$ $y$", 1, [])
        run.assert_called_once()
        arguments = run.call_args
        self.assertEqual(arguments.args[0][1], str(math_render.HELPER))
        self.assertEqual(arguments.kwargs["timeout"], 60)
        self.assertFalse(arguments.kwargs.get("shell", False))
        batch = json.loads(arguments.kwargs["input"])
        self.assertEqual([item["tex"] for item in batch["expressions"]], ["x", "y"])

    def test_math_runtime_failure_prevents_output_creation_and_cloud_calls(self):
        from test_digest_pdf import clients, di_result, make_pdf
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source.pdf", root / "digest"
            make_pdf(source)
            document, openai = clients(di_result(["Source"]), [])
            with patch.object(ingestion, "check_math_runtime", side_effect=math_render.MathRenderError("Unavailable")):
                with self.assertRaises(math_render.MathRenderError):
                    ingestion.digest_pdf(source, output, document, openai, "vision", dpi=72)
            self.assertFalse(output.exists())
            document.begin_analyze_document.assert_not_called()
            openai.responses.create.assert_not_called()

    def test_copied_checker_runs_from_its_own_declared_dependencies(self):
        skill = math_render.HELPER.parent.parent
        root = skill.parents[2]
        lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            standalone = Path(directory) / "copied-import"
            shutil.copytree(skill, standalone)
            for reference, package in lock["packages"].items():
                if reference.startswith("node_modules/") and not package.get("link"):
                    shutil.copytree(root / reference, standalone / reference)
            declared = json.loads((standalone / "package.json").read_text(encoding="utf-8"))
            self.assertEqual(declared["dependencies"], {"mathjax-full": "3.2.2"})
            result = subprocess.run(
                [shutil.which("node"), str(standalone / "scripts" / "check_math.cjs"), "--check"],
                cwd=standalone, capture_output=True, text=True, encoding="utf-8", timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["results"][0]["errors"], [])
            self.assertFalse((standalone / "docs").exists())


if __name__ == "__main__":
    unittest.main()
