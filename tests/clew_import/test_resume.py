from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from test_digest_pdf import clients, decision, di_figure, di_result, ingestion, make_pdf, png_bytes, response
from test_page_review import finding, review
from digestion_checkpoint import DigestionCheckpoint, output_lock, saved_response
import digestion_checkpoint as checkpoints
import plan_imports as planner


USAGE = {
    "input_tokens": 100, "output_tokens": 10,
    "input_tokens_details": {"cached_tokens": 0},
    "output_tokens_details": {"reasoning_tokens": 2},
}


class ResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / "chapter.pdf"
        self.output = self.root / "chapter"
        make_pdf(self.source)
        self.settings = ingestion.Settings("https://di.example.com", "https://ai.example.com/openai/v1/", "vision")
        runtime = patch.object(ingestion, "check_math_runtime")
        runtime.start()
        self.addCleanup(runtime.stop)

    def digest(self, document: Mock, openai: Mock, **options: object) -> dict[str, object]:
        return ingestion.digest_pdf(
            self.source, self.output, document, openai, self.settings.deployment,
            dpi=72, settings=self.settings, **options,
        )

    def binding(self, **options: object) -> dict[str, object]:
        defaults = {
            "pages": None, "dpi": 72, "high_resolution_ocr": False,
            "max_output_tokens": 16000, "page_review": True, "settings": self.settings,
        }
        defaults.update(options)
        return ingestion.resume_binding(self.source, self.settings.deployment, **defaults)

    def checkpoint(self) -> DigestionCheckpoint:
        return DigestionCheckpoint.load(self.output, self.binding())

    def snapshot(self) -> dict[str, bytes]:
        return {
            str(path.relative_to(self.output)): path.read_bytes()
            for path in self.output.rglob("*") if path.is_file()
        }

    def interrupt_second_page(self) -> tuple[Mock, Mock]:
        document, openai = clients(di_result(["One", "Two"]), [
            response("One", usage=USAGE), response(review(), usage=USAGE), KeyboardInterrupt(),
        ])
        with self.assertRaises(KeyboardInterrupt):
            self.digest(document, openai)
        return document, openai

    def test_completed_page_and_di_layout_are_reused_and_usage_is_not_double_counted(self) -> None:
        self.interrupt_second_page()
        evidence = {
            path: data for path, data in self.snapshot().items()
            if path.startswith(str(Path("raw") / "checkpoints"))
        }
        document, openai = clients(di_result(["Unused"]), [
            response("Two", usage=USAGE), response(review(), usage=USAGE),
        ])
        manifest = self.digest(document, openai, resume=True)
        document.begin_analyze_document.assert_not_called()
        document.get_analyze_result_figure.assert_not_called()
        openai.responses.create.assert_called()
        self.assertEqual(openai.responses.create.call_count, 2)
        self.assertEqual(manifest["costs"]["openai"]["api_calls"], 4)
        self.assertEqual(manifest["costs"]["openai"]["input_tokens"], 400)
        self.assertEqual(manifest["costs"]["openai"]["unobserved_request_attempts"], 1)
        self.assertIsNone(manifest["costs"]["openai"]["estimated_cost_usd"])
        self.assertEqual(manifest["costs"]["document_intelligence"]["pages_processed"], 2)
        self.assertEqual(
            (self.output / "document.md").read_bytes(),
            b"<!-- page: 1 -->\n\nOne\n\n<!-- page: 2 -->\n\nTwo",
        )
        for path, data in evidence.items():
            self.assertEqual((self.output / path).read_bytes(), data)
        self.assertTrue(self.checkpoint().record.complete)

    def test_mid_page_resume_only_requests_missing_judgment(self) -> None:
        document, openai = clients(di_result(["One"], numbers=[1]), [
            response("One"), KeyboardInterrupt(),
        ])
        with self.assertRaises(KeyboardInterrupt):
            self.digest(document, openai, pages="1")
        document, openai = clients(di_result(["Unused"]), [response(review())])
        manifest = self.digest(document, openai, pages="1", resume=True)
        self.assertEqual(openai.responses.create.call_count, 1)
        self.assertEqual(openai.responses.create.call_args.kwargs["text"]["format"]["name"], "PageReview")
        self.assertEqual(manifest["pages"][0]["review"]["status"], "passed")
        document.begin_analyze_document.assert_not_called()

    def test_rejected_judge_response_is_preserved_and_only_that_call_is_retried(self) -> None:
        document, openai = clients(di_result(["One"], numbers=[1]), [
            response("One", usage=USAGE), response("invalid JSON", usage=USAGE),
        ])
        with self.assertRaises(ingestion.ValidationError):
            self.digest(document, openai, pages="1")
        bad_response = self.output / "raw" / "checkpoints" / "response-000002.json"
        original = bad_response.read_bytes()
        document, openai = clients(di_result(["Unused"]), [response(review(), usage=USAGE)])
        manifest = self.digest(document, openai, pages="1", resume=True)
        self.assertEqual(openai.responses.create.call_count, 1)
        self.assertEqual(bad_response.read_bytes(), original)
        self.assertEqual(manifest["costs"]["openai"]["api_calls"], 3)
        self.assertTrue(manifest["costs"]["openai"]["estimate_complete"])

    def test_corrective_budget_and_previous_feedback_survive_resume(self) -> None:
        document, openai = clients(di_result(["One"], numbers=[1]), [
            response("Draft"), response(review(finding())), KeyboardInterrupt(),
        ])
        with self.assertLogs("ingestion", "WARNING"), self.assertRaises(KeyboardInterrupt):
            self.digest(document, openai, pages="1")
        document, openai = clients(di_result(["Unused"]), [
            response("Revision"), response(review(finding())),
            response("Final"), response(review(finding())),
        ])
        with self.assertLogs("ingestion", "WARNING"):
            manifest = self.digest(document, openai, pages="1", resume=True)
        self.assertEqual(openai.responses.create.call_count, 4)
        context = json.loads(openai.responses.create.call_args_list[0].kwargs["input"][1]["content"][0]["text"])
        self.assertEqual(context["previous_markdown"], "Draft")
        self.assertEqual(manifest["status"], "needs_review")
        self.assertEqual([attempt["number"] for attempt in manifest["pages"][0]["review"]["attempts"]], [1, 2, 3])

    def test_figure_crop_and_classification_are_reused(self) -> None:
        document, openai = clients(
            di_result(["One"], numbers=[1], figures=[di_figure("figure")]),
            [response(decision()), KeyboardInterrupt()], [png_bytes()],
        )
        with self.assertRaises(KeyboardInterrupt):
            self.digest(document, openai, pages="1")
        document, openai = clients(di_result(["Unused"]), [response("One"), response(review())])
        manifest = self.digest(document, openai, pages="1", resume=True)
        document.begin_analyze_document.assert_not_called()
        document.get_analyze_result_figure.assert_not_called()
        self.assertEqual(openai.responses.create.call_count, 2)
        self.assertEqual(manifest["figures"][0]["decision"], "keep")

    def test_polling_resumes_the_same_di_operation_without_submitting(self) -> None:
        document, openai = clients(di_result(["One", "Two"]), [])
        document.begin_analyze_document.return_value.result.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.digest(document, openai)
        document, openai = clients(di_result(["Unused"]), [
            response("One"), response(review()), response("Two"), response(review()),
        ])
        document.send_request.side_effect = [
            Mock(status_code=200, json=Mock(return_value={"status": "running"})),
            Mock(status_code=200, json=Mock(return_value={
                "status": "succeeded", "analyzeResult": di_result(["One", "Two"]).as_dict(),
            })),
        ]
        with patch.object(ingestion.time, "sleep") as sleep:
            self.digest(document, openai, resume=True)
        document.begin_analyze_document.assert_not_called()
        self.assertEqual(document.send_request.call_count, 2)
        request = document.send_request.call_args.args[0]
        self.assertEqual(request.method, "GET")
        self.assertIn("/analyzeResults/analysis-id?api-version=2024-11-30", request.url)
        sleep.assert_called_once_with(2)

    def test_unknown_di_submission_is_blocked_without_mutating_output(self) -> None:
        document, openai = clients(di_result(["One", "Two"]), [])
        document.begin_analyze_document.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.digest(document, openai)
        before = self.snapshot()
        document, openai = clients(di_result(["Unused"]), [])
        with self.assertRaisesRegex(ingestion.DigestionError, "outcome is unknown"):
            self.digest(document, openai, resume=True)
        self.assertEqual(self.snapshot(), before)
        document.begin_analyze_document.assert_not_called()
        openai.responses.create.assert_not_called()

    def test_unavailable_di_operation_does_not_resubmit(self) -> None:
        document, openai = clients(di_result(["One", "Two"]), [])
        document.begin_analyze_document.return_value.result.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.digest(document, openai)
        document, openai = clients(di_result(["Unused"]), [])
        document.send_request.return_value = Mock(
            status_code=200, json=Mock(return_value={"status": "failed"}),
        )
        with self.assertRaisesRegex(ingestion.DigestionError, "no PDF was resubmitted"):
            self.digest(document, openai, resume=True)
        document.begin_analyze_document.assert_not_called()
        openai.responses.create.assert_not_called()

    def test_source_options_configuration_and_runtime_changes_are_blocked(self) -> None:
        self.interrupt_second_page()
        before = self.snapshot()
        for changes in (
            {"pages": "1"}, {"dpi": 144}, {"high_resolution_ocr": True},
            {"max_output_tokens": 32000}, {"page_review": False},
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(ingestion.DigestionError, "changed"):
                DigestionCheckpoint.load(self.output, self.binding(**changes))
        with patch.object(ingestion, "runtime_fingerprint", return_value="different"):
            with self.assertRaisesRegex(ingestion.DigestionError, "changed"):
                self.checkpoint()
        changed = ingestion.Settings("https://other.example.com", self.settings.openai_base_url, "vision")
        with self.assertRaisesRegex(ingestion.DigestionError, "changed"):
            DigestionCheckpoint.load(self.output, self.binding(settings=changed))
        self.source.write_bytes(self.source.read_bytes() + b"\n% Changed")
        with self.assertRaisesRegex(ingestion.DigestionError, "changed"):
            self.checkpoint()
        self.assertEqual(self.snapshot(), before)

    def test_modified_artifact_or_unexpected_file_is_blocked(self) -> None:
        self.interrupt_second_page()
        raw = self.output / "raw" / "pages" / "page-0001.attempt-01.md"
        original = raw.read_bytes()
        raw.write_bytes(b"Human edit")
        with self.assertRaisesRegex(ingestion.DigestionError, "changed"):
            self.checkpoint()
        raw.write_bytes(original)
        note = self.output / "notes.txt"
        note.write_bytes(b"Human note")
        with self.assertRaisesRegex(ingestion.DigestionError, "Unexpected file"):
            self.checkpoint()
        self.assertEqual(note.read_bytes(), b"Human note")

    def test_active_process_lock_is_refused_and_released_after_interruption(self) -> None:
        self.interrupt_second_page()
        with output_lock(self.output):
            with self.assertRaisesRegex(ingestion.DigestionError, "Another process"):
                ingestion.inspect_resume(
                    self.source, self.output, "vision", dpi=72, settings=self.settings,
                )
        self.assertFalse(ingestion.inspect_resume(
            self.source, self.output, "vision", dpi=72, settings=self.settings,
        )["complete"])

    def test_redirected_artifacts_and_enumeration_failures_are_explicit(self) -> None:
        self.interrupt_second_page()
        raw = self.output / "raw"
        original = checkpoints.redirected
        with patch.object(checkpoints, "redirected", side_effect=lambda path: path == raw or original(path)):
            with self.assertRaisesRegex(ingestion.DigestionError, "redirects"):
                self.checkpoint()

        def walk(*args, **kwargs):
            kwargs["onerror"](PermissionError("Cannot hydrate directory"))

        with patch.object(checkpoints.os, "walk", walk):
            with self.assertRaisesRegex(PermissionError, "Cannot hydrate"):
                self.checkpoint()

    def test_completed_resume_is_a_read_only_no_op(self) -> None:
        document, openai = clients(di_result(["One", "Two"]), [
            response("One"), response(review()), response("Two"), response(review()),
        ])
        original = self.digest(document, openai)
        before = self.snapshot()
        document, openai = clients(di_result(["Unused"]), [])
        self.assertEqual(self.digest(document, openai, resume=True), original)
        self.assertEqual(self.snapshot(), before)
        document.begin_analyze_document.assert_not_called()
        openai.responses.create.assert_not_called()

    def test_pre_checkpoint_output_remains_unsupported(self) -> None:
        self.output.mkdir()
        (self.output / "run.json").write_bytes(b'{"status":"interrupted"}')
        before = self.snapshot()
        document, openai = clients(di_result(["Unused"]), [])
        with self.assertRaisesRegex(ingestion.DigestionError, "No resumable checkpoint"):
            self.digest(document, openai, resume=True)
        self.assertEqual(self.snapshot(), before)

    def test_response_written_before_checkpoint_commit_is_recovered_without_new_transcription(self) -> None:
        document, openai = clients(di_result(["One"], numbers=[1]), [response("One")])
        original_save = DigestionCheckpoint.save
        interrupted = False

        def save(checkpoint):
            nonlocal interrupted
            if not interrupted and "raw/checkpoints/response-000001.json" in checkpoint.record.files:
                interrupted = True
                raise KeyboardInterrupt()
            original_save(checkpoint)

        with patch.object(DigestionCheckpoint, "save", save), self.assertRaises(KeyboardInterrupt):
            self.digest(document, openai, pages="1")
        document, openai = clients(di_result(["Unused"]), [response(review())])
        self.digest(document, openai, pages="1", resume=True)
        self.assertEqual(openai.responses.create.call_count, 1)
        self.assertEqual(openai.responses.create.call_args.kwargs["text"]["format"]["name"], "PageReview")

    def test_interrupted_publication_replays_locally_without_cloud_calls(self) -> None:
        document, openai = clients(di_result(["One"], numbers=[1]), [response("One"), response(review())])
        original_write = DigestionCheckpoint.write_json

        def write(checkpoint, path, value):
            if path.name == "manifest.json":
                raise KeyboardInterrupt()
            original_write(checkpoint, path, value)

        with patch.object(DigestionCheckpoint, "write_json", write), self.assertRaises(KeyboardInterrupt):
            self.digest(document, openai, pages="1")
        document, openai = clients(di_result(["Unused"]), [])
        manifest = self.digest(document, openai, pages="1", resume=True)
        self.assertEqual(manifest["status"], "extracted")
        document.begin_analyze_document.assert_not_called()
        openai.responses.create.assert_not_called()

    def test_incomplete_temporary_write_is_preserved_across_another_failed_resume(self) -> None:
        self.interrupt_second_page()
        checkpoint = self.checkpoint()
        math_path = self.output / "raw" / "pages" / "page-0002.math.json"
        _, pending, _ = checkpoint.prepare_write(math_path, checkpoints.fingerprint("unfinished"))
        pending.write_bytes(b"{")
        document, openai = clients(di_result(["Unused"]), [KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt):
            self.digest(document, openai, resume=True)
        self.assertEqual(pending.read_bytes(), b"{")
        document, openai = clients(di_result(["Unused"]), [response("Two"), response(review())])
        self.digest(document, openai, resume=True)
        self.assertFalse(pending.exists())

    def test_checkpoint_fingerprint_rechecks_plan_approval(self) -> None:
        self.interrupt_second_page()
        before = self.snapshot()
        document, openai = clients(di_result(["Unused"]), [])
        with self.assertRaisesRegex(ingestion.DigestionError, "changed since approval"):
            self.digest(document, openai, resume=True, checkpoint_sha256="wrong")
        self.assertEqual(self.snapshot(), before)
        openai.responses.create.assert_not_called()

    def test_transient_checkpoint_lock_retries_locally_without_repeating_model_calls(self) -> None:
        document, openai = clients(di_result(["One"], numbers=[1]), [response("One"), response(review())])
        original_replace = Path.replace
        blocked = False

        def replace(pending, target):
            nonlocal blocked
            if (
                target.name == "checkpoint.json" and not blocked
                and "raw/checkpoints/response-000001.json" in json.loads(pending.read_bytes())["files"]
            ):
                blocked = True
                error = PermissionError("Synthetic sharing violation")
                error.winerror = 32
                raise error
            return original_replace(pending, target)

        with (
            patch.object(Path, "replace", autospec=True, side_effect=replace),
            patch.object(ingestion.time, "sleep") as sleep,
            self.assertLogs("ingestion", "WARNING"),
        ):
            self.digest(document, openai, pages="1")
        self.assertTrue(blocked)
        sleep.assert_called_once_with(0.1)
        self.assertEqual(openai.responses.create.call_count, 2)

    def test_cache_reads_recheck_artifacts_changed_after_loading(self) -> None:
        self.interrupt_second_page()
        checkpoint = self.checkpoint()
        call = checkpoint.record.calls[0]
        (self.output / call.response).write_bytes(b'{"status":"completed","output_text":"Human edit"}')
        with self.assertRaisesRegex(ingestion.DigestionError, "changed during this run"):
            checkpoint.response_data(call)
        with self.assertRaisesRegex(ingestion.DigestionError, "changed during this run"):
            checkpoint.copy(self.output / call.response, self.output / "raw" / "copy.json")

    def test_macro_context_is_replayed_from_selected_prior_page(self) -> None:
        first = r"$\newcommand{\foo}{x}\foo$"
        second = r"$\foo^2$"
        document, openai = clients(di_result(["One", "Two"]), [
            response(first), response(review()), KeyboardInterrupt(),
        ])
        with self.assertRaises(KeyboardInterrupt):
            self.digest(document, openai)
        document, openai = clients(di_result(["Unused"]), [response(second), response(review())])
        manifest = self.digest(document, openai, resume=True)
        self.assertEqual(manifest["status"], "extracted")
        math = json.loads((self.output / "raw" / "pages" / "page-0002.math.json").read_bytes())
        self.assertEqual(math["context_expressions"], 1)
        self.assertEqual(math["expressions"][0]["errors"], [])

    def test_no_review_resume_preserves_single_transcription_behavior(self) -> None:
        document, openai = clients(di_result(["One", "Two"]), [response("One"), KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt):
            self.digest(document, openai, page_review=False)
        document, openai = clients(di_result(["Unused"]), [response("Two")])
        manifest = self.digest(document, openai, resume=True, page_review=False)
        self.assertEqual(openai.responses.create.call_count, 1)
        self.assertNotIn("review", manifest["pages"][0])

    def test_real_responses_api_json_text_is_reloaded_without_inner_json_decoding(self) -> None:
        text = "  Source\r\n" + r"$\frac{1}{2}$" + "\r"
        raw = {
            "status": "completed", "model": "gpt-6.1-sol", "usage": USAGE,
            "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
        }
        restored = saved_response(raw)
        self.assertEqual(restored.output_text, text)
        self.assertEqual(restored.usage, USAGE)

    def test_resume_planner_is_read_only_binds_checkpoint_and_counts_remaining_calls(self) -> None:
        self.interrupt_second_page()
        project = self.root / "project"
        project.mkdir()
        (project / ".venv").mkdir()
        for name in ("pyproject.toml", "uv.lock", ".env", "package.json", "package-lock.json"):
            (project / name).write_bytes(b"fixture")
        env = {
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": self.settings.document_endpoint,
            "AZURE_OPENAI_BASE_URL": self.settings.openai_base_url,
            "AZURE_OPENAI_DEPLOYMENT": self.settings.deployment,
        }
        before = self.snapshot()
        with (
            patch.dict(os.environ, env, clear=True),
            patch.object(planner.shutil, "which", return_value="uv"),
            patch.object(planner, "check_math_runtime"),
        ):
            plan = planner.build_plan(self.source, project=project, resume=True, check_env=True, dpi=72)
            custom = planner.build_plan(
                self.source, project=project, resume=True, check_env=True, dpi=72, output_path=self.output,
            )
        entry = plan["entries"][0]
        self.assertEqual(entry["classification"], "resume")
        self.assertIn("--resume", entry["argv"])
        self.assertIn("--checkpoint-sha256", entry["argv"])
        self.assertEqual(entry["resume"]["completed_page_model_requests"], 2)
        self.assertEqual(entry["resume"]["uncertain_model_requests"], 1)
        self.assertEqual(entry["page_model_requests"], {"minimum": 2, "maximum": 10})
        self.assertEqual(custom["entries"][0]["classification"], "resume")
        self.assertEqual(self.snapshot(), before)

    def test_cli_resumes_and_rejects_changed_settings_before_credentials(self) -> None:
        self.interrupt_second_page()
        before = self.snapshot()
        changed = ingestion.Settings("https://other.example.com", self.settings.openai_base_url, "vision")
        with (
            patch.object(ingestion, "settings_from_env", return_value=changed),
            patch.object(ingestion, "DefaultAzureCredential") as credential,
            self.assertLogs("ingestion", "ERROR"),
        ):
            code = ingestion.main([
                str(self.source), "--output", str(self.output), "--dpi", "72", "--resume",
            ])
        self.assertEqual(code, 1)
        credential.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        document, openai = clients(di_result(["Unused"]), [response("Two"), response(review())])
        with (
            patch.object(ingestion, "settings_from_env", return_value=self.settings),
            patch.object(ingestion, "DefaultAzureCredential"),
            patch.object(ingestion, "get_bearer_token_provider"),
            patch.object(ingestion, "DocumentIntelligenceClient") as di_factory,
            patch.object(ingestion, "OpenAI") as ai_factory,
            self.assertLogs("ingestion", "INFO"),
        ):
            di_factory.return_value.__enter__.return_value = document
            ai_factory.return_value.__enter__.return_value = openai
            code = ingestion.main([
                str(self.source), "--output", str(self.output), "--dpi", "72", "--resume",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(openai.responses.create.call_count, 2)
        document.begin_analyze_document.assert_not_called()


if __name__ == "__main__":
    unittest.main()
