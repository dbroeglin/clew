from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_digest_pdf import clients, di_result, ingestion, make_pdf, page_result, response
import plan_imports as planner


class PlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inputs = self.root / "courses"
        self.inputs.mkdir()
        self.project = self.root / "project"
        self.project.mkdir()
        for name in ("pyproject.toml", "uv.lock", ".env"):
            (self.project / name).write_text("synthetic fixture", encoding="utf-8")
        (self.project / ".venv").mkdir()
        self.config = {
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://di.example.com",
            "AZURE_AI_PROJECT_ENDPOINT": "https://ai.example.com/api/projects/test",
            "AZURE_OPENAI_DEPLOYMENT": "test-vision",
        }

    def pdf(self, name: str = "chapter_1.pdf", count: int = 2) -> Path:
        source = self.inputs / name
        source.parent.mkdir(parents=True, exist_ok=True)
        make_pdf(source, count)
        return source

    def plan(self, input_path: Path | None = None, **options: object) -> dict[str, object]:
        with patch.dict(os.environ, self.config, clear=True), patch.object(planner.shutil, "which", return_value="uv"):
            return planner.build_plan(
                input_path or self.inputs, project=self.project, check_env=True, **options,
            )

    def bundle(self, source: Path, pages: str | None = None) -> Path:
        numbers = ingestion.selected_pages(pages, 2)
        text = ["Page " + str(number) for number in numbers]
        document, openai = clients(
            di_result(text, numbers=numbers), [response(page_result(value)) for value in text],
        )
        output = source.with_suffix("")
        ingestion.digest_pdf(source, output, document, openai, "test-vision", pages=pages, dpi=72)
        return output

    def edit_manifest(self, output: Path, edit) -> None:
        path = output / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        edit(manifest)
        path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_nested_discovery_names_outputs_and_proposes_all_commands(self) -> None:
        second = self.pdf("nested/Chapter 2.PDF")
        first = self.pdf()
        plan = self.plan()
        entries = plan["entries"]
        self.assertEqual([entry["source"] for entry in entries], [str(first), str(second)])
        self.assertEqual([entry["output"] for entry in entries],
                         [str(first.with_suffix("")), str(second.with_suffix(""))])
        self.assertTrue(plan["requires_approval"])
        self.assertEqual(plan["preflight_blockers"], [])
        for entry in entries:
            self.assertEqual(entry["classification"], "convert")
            self.assertEqual(entry["argv"][0:4], ["uv", "run", "--locked", "--env-file"])
            self.assertIn("--output", entry["argv"])
            self.assertIn(entry["source"], entry["command"])
            self.assertEqual(entry["argv"][entry["argv"].index("--env-file") + 1], ".env")
            self.assertFalse(Path(entry["output"]).exists())
        self.assertIn("sync", plan["setup_command"])

    def test_existing_complete_bundle_is_skipped_and_its_copy_is_excluded(self) -> None:
        source = self.pdf()
        output = self.bundle(source)
        plan = self.plan()
        self.assertEqual(len(plan["entries"]), 1)
        self.assertEqual(plan["entries"][0]["classification"], "already_converted")
        self.assertNotIn("command", plan["entries"][0])
        self.assertEqual(plan["excluded_bundles"], [str(output)])

    def test_review_result_is_reported_without_reconversion(self) -> None:
        source = self.pdf()
        output = self.bundle(source)
        self.edit_manifest(output, lambda data: data.update(status="needs_review", issues=["Inspect figure"]))
        entry = self.plan()["entries"][0]
        self.assertEqual(entry["classification"], "already_converted")
        self.assertEqual(entry["review_issues"], ["Inspect figure"])

    def test_partial_page_digest_blocks_full_conversion_but_matches_explicit_scope(self) -> None:
        source = self.pdf()
        self.bundle(source, pages="2")
        entry = self.plan()["entries"][0]
        self.assertEqual(entry["classification"], "blocked")
        self.assertIn("page coverage", entry["reason"])
        self.assertEqual(self.plan(pages="2")["entries"][0]["classification"], "already_converted")

    def test_changed_source_is_blocked_not_overwritten(self) -> None:
        source = self.pdf()
        output = self.bundle(source)
        before = (output / "manifest.json").read_bytes()
        make_pdf(source, 3)
        entry = self.plan()["entries"][0]
        self.assertEqual(entry["classification"], "blocked")
        self.assertIn("stale", entry["reason"])
        self.assertEqual((output / "manifest.json").read_bytes(), before)

    def test_corrupt_retained_source_is_blocked(self) -> None:
        source = self.pdf()
        output = self.bundle(source)
        (output / "source" / source.name).write_bytes(b"changed")
        self.assertIn("Retained original", self.plan()["entries"][0]["reason"])

    def test_missing_markdown_and_page_artifacts_block_existing_outputs(self) -> None:
        for reference in (
            "document.md", "raw/pages/page-0001.png", "raw/pages/page-0001.response.json",
            "run.json", "raw/document-intelligence.json", "raw/document-intelligence.md", "raw/assembled.md",
        ):
            with self.subTest(reference=reference):
                source = self.pdf(reference.replace("/", "_") + ".pdf")
                output = self.bundle(source)
                (output / reference).unlink()
                entry = self.plan(source)["entries"][0]
                self.assertEqual(entry["classification"], "blocked")
                self.assertIn("missing", entry["reason"])

    def test_missing_kept_figure_is_blocked(self) -> None:
        source = self.pdf()
        output = self.bundle(source)
        (output / "raw" / "figures" / "figure.png").write_bytes(b"synthetic")
        self.edit_manifest(output, lambda data: data["figures"].append({
            "decision": "keep", "raw_crop": "raw/figures/figure.png", "asset": "figures/figure.png",
        }))
        self.assertEqual(self.plan()["entries"][0]["classification"], "blocked")

    def test_partial_failed_bundle_is_excluded_and_blocked(self) -> None:
        source = self.pdf()
        document, openai = clients(di_result(["One", "Two"]), [])
        document.begin_analyze_document.side_effect = OSError("Synthetic service failure")
        with self.assertRaisesRegex(OSError, "Synthetic"):
            ingestion.digest_pdf(source, source.with_suffix(""), document, openai, "test-vision")
        plan = self.plan()
        self.assertEqual(len(plan["entries"]), 1)
        self.assertEqual(plan["entries"][0]["classification"], "blocked")
        self.assertEqual(plan["excluded_bundles"], [str(source.with_suffix(""))])
        self.assertTrue((source.with_suffix("") / "source" / source.name).is_file())

    def test_unrelated_directory_blocks_target_but_does_not_hide_other_sources(self) -> None:
        source = self.pdf()
        nested = self.pdf("chapter_1/other.pdf")
        entries = self.plan()["entries"]
        by_source = {entry["source"]: entry for entry in entries}
        self.assertEqual(by_source[str(source)]["classification"], "blocked")
        self.assertEqual(by_source[str(nested)]["classification"], "convert")

    def test_output_file_blocks_conversion(self) -> None:
        source = self.pdf()
        source.with_suffix("").write_text("keep", encoding="utf-8")
        entry = self.plan()["entries"][0]
        self.assertEqual(entry["classification"], "blocked")
        self.assertEqual(source.with_suffix("").read_text(encoding="utf-8"), "keep")

    def test_extension_case_collision_blocks_both_inputs(self) -> None:
        source = self.pdf()
        if os.name == "nt":
            with patch.object(planner, "discover", return_value=([source, source], [], [])):
                entries = self.plan()["entries"]
        else:
            self.pdf("chapter_1.PDF")
            entries = self.plan()["entries"]
        self.assertTrue(all(entry["classification"] == "blocked" for entry in entries))
        self.assertTrue(all("same target" in entry["reason"] for entry in entries))

    def test_corrupt_metadata_reports_conflict_without_importing_copies(self) -> None:
        source = self.pdf()
        output = self.bundle(source)
        (output / "manifest.json").write_text("not JSON", encoding="utf-8")
        plan = self.plan()
        self.assertEqual(len(plan["entries"]), 1)
        self.assertEqual(plan["entries"][0]["classification"], "blocked")
        self.assertEqual(plan["discovery_conflicts"][0]["path"], str(output))

    def test_artifact_traversal_and_absolute_paths_are_blocked(self) -> None:
        source = self.pdf()
        output = self.bundle(source)
        for reference in ("../outside.png", str(self.root / "outside.png"), "C:\\outside.png"):
            with self.subTest(reference=reference):
                self.edit_manifest(output, lambda data: data["pages"][0].update(raw_image=reference))
                entry = self.plan(source)["entries"][0]
                self.assertEqual(entry["classification"], "blocked")
                self.assertIn("outside", entry["reason"])

    def test_unhashable_status_and_figure_decision_are_blocked_not_crashes(self) -> None:
        source = self.pdf()
        output = self.bundle(source)
        self.edit_manifest(output, lambda data: data.update(status=[]))
        plan = self.plan()
        self.assertEqual(plan["entries"][0]["classification"], "blocked")
        self.assertTrue(plan["discovery_conflicts"])
        self.edit_manifest(output, lambda data: data.update(status="extracted", figures=[{"decision": []}]))
        self.assertEqual(self.plan(source)["entries"][0]["classification"], "blocked")

    def test_linked_directory_is_not_traversed(self) -> None:
        source = self.pdf()
        output = source.with_suffix("")
        output.mkdir()
        original = planner.is_link
        with patch.object(planner, "is_link", side_effect=lambda path: path == output or original(path)):
            plan = self.plan()
        self.assertEqual(plan["entries"][0]["classification"], "blocked")
        self.assertEqual(plan["discovery_conflicts"][0]["path"], str(output))

    def test_real_symlink_is_not_traversed(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        make_pdf(outside / "outside.pdf")
        link = self.inputs / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlink creation is unavailable: {error}")
        plan = self.plan()
        self.assertEqual(plan["entries"], [])
        self.assertEqual(plan["discovery_conflicts"][0]["path"], str(link))
        self.assertFalse((outside / "outside").exists())

    def test_broken_pdf_and_invalid_page_scope_are_explicitly_blocked(self) -> None:
        invalid = self.inputs / "broken.pdf"
        invalid.write_bytes(b"not a pdf")
        source = self.pdf()
        plan = self.plan()
        self.assertEqual(plan["entries"][0]["classification"], "blocked")
        self.assertEqual(self.plan(source, pages="9")["entries"][0]["classification"], "blocked")

    def test_options_are_in_plan_and_not_silently_enabled(self) -> None:
        source = self.pdf("chapter's notes.pdf")
        plain = self.plan()["entries"][0]
        self.assertNotIn("--high-resolution-ocr", plain["argv"])
        entry = self.plan(pages="2", dpi=144, max_output_tokens=3000,
                          high_resolution_ocr=True, debug=True)["entries"][0]
        argv = entry["argv"]
        self.assertEqual(entry["pages"], [2])
        for option, value in (("--dpi", "144"), ("--max-output-tokens", "3000"), ("--pages", "2")):
            self.assertEqual(argv[argv.index(option) + 1], value)
        self.assertIn("--high-resolution-ocr", argv)
        self.assertIn("--debug", argv)
        self.assertIn("chapter''s notes", entry["command"])
        self.assertFalse(source.with_suffix("").exists())

    def test_inspection_is_read_only_and_never_calls_cloud_or_cleanup(self) -> None:
        source = self.pdf()
        output = self.bundle(source)
        before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with (
            patch.object(ingestion, "digest_pdf", side_effect=AssertionError("Must not convert")),
            patch.object(ingestion, "DefaultAzureCredential", side_effect=AssertionError("Must not authenticate")),
            patch.object(planner.shutil, "rmtree", side_effect=AssertionError("Must not delete")),
            patch.object(subprocess, "run", side_effect=AssertionError("Must not execute")),
        ):
            self.plan()
        after = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(output.is_dir())

    def test_configuration_validation_uses_effective_environment_and_redacts_values(self) -> None:
        self.pdf()
        with patch.dict(os.environ, self.config, clear=True):
            os.environ["AZURE_OPENAI_BASE_URL"] = "https://private.example.com/openai/v1/"
            blockers = planner.environment_blockers(self.project, True)
        self.assertTrue(any("exactly one" in item for item in blockers))
        self.assertNotIn("private.example.com", json.dumps(blockers))
        with patch.dict(os.environ, {}, clear=True):
            blockers = planner.environment_blockers(self.project, True)
        self.assertTrue(any("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT" in item for item in blockers))

    def test_placeholder_configuration_and_missing_env_block_conversion(self) -> None:
        self.pdf()
        config = dict(self.config, AZURE_OPENAI_DEPLOYMENT="YOUR-DEPLOYMENT")
        with patch.dict(os.environ, config, clear=True):
            self.assertTrue(any("placeholder" in item for item in planner.environment_blockers(self.project, True)))
        (self.project / ".env").unlink()
        self.assertIn("Project root is missing .env.", self.plan()["preflight_blockers"])

    def test_configuration_summary_is_redacted_and_detects_changes(self) -> None:
        self.pdf()
        plan = self.plan()
        configuration = plan["configuration"]
        self.assertEqual(configuration["document_intelligence_host"], "di.example.com")
        self.assertEqual(configuration["openai_host"], "ai.example.com")
        self.assertNotIn("test-vision", json.dumps(configuration))
        self.config["AZURE_OPENAI_DEPLOYMENT"] = "another-deployment"
        self.assertNotEqual(configuration["fingerprint"], self.plan()["configuration"]["fingerprint"])

    def test_actual_uv_env_file_loading_checks_inherited_endpoint_conflict(self) -> None:
        uv = shutil.which("uv")
        if uv is None:
            self.skipTest("UV is unavailable for the environment-file integration check.")
        source = self.pdf()
        env_file = self.project / ".env"
        env_file.write_text(
            "\n".join(f"{key}={value}" for key, value in self.config.items()),
            encoding="utf-8",
        )
        inherited = dict(os.environ)
        for key in (*self.config, "AZURE_OPENAI_BASE_URL"):
            inherited.pop(key, None)
        inherited["AZURE_OPENAI_BASE_URL"] = "https://private.example.com/openai/v1/"
        result = subprocess.run(
            [uv, "run", "--project", str(planner.PROJECT_ROOT),
             "--locked", "--no-sync", "--env-file", ".env",
             "python", "-B", str(Path(planner.__file__).resolve()), str(source), "--check-env"],
            cwd=self.project, env=inherited, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertTrue(result.stdout, result.stderr)
        plan = json.loads(result.stdout)
        self.assertTrue(any("exactly one" in item for item in plan["preflight_blockers"]))
        self.assertIsNone(plan["configuration"])
        self.assertNotIn("private.example.com", result.stdout + result.stderr)
        self.assertFalse(source.with_suffix("").exists())

    def test_no_input_and_invalid_options_fail_explicitly(self) -> None:
        with self.assertRaisesRegex(planner.InspectionError, "does not exist"):
            self.plan(self.inputs / "absent")
        with self.assertRaisesRegex(planner.InspectionError, "DPI"):
            self.plan(dpi=1)

    def test_planner_cli_codes_do_not_execute_generated_commands(self) -> None:
        self.pdf()
        with (
            patch.object(planner, "environment_blockers", return_value=[]),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(planner.main([str(self.inputs)]), 0)
        self.assertTrue(json.loads(output.getvalue())["requires_approval"])
        with patch.object(planner, "environment_blockers", return_value=["Missing .env"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(planner.main([str(self.inputs)]), 2)
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(planner.main([str(self.inputs / "absent")]), 1)
        self.assertIn("Inspection failed", error.getvalue())


if __name__ == "__main__":
    unittest.main()
