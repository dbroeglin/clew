from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import pymupdf
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import (
    AnalyzeResult,
    BoundingRegion,
    DocumentCaption,
    DocumentFigure,
    DocumentFormula,
    DocumentPage,
    DocumentSpan,
)
from azure.core.exceptions import HttpResponseError
from azure.core.credentials import AzureKeyCredential
from azure.core.pipeline.transport import HttpRequest, HttpResponse, HttpTransport
from openai import DefaultHttpxClient
from openai.types.responses import Response
from PIL import Image
from pydantic import ValidationError
from requests.structures import CaseInsensitiveDict

SKILL_SCRIPTS = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "clew-import" / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
import digest_pdf as ingestion


def make_pdf(path: Path, count: int = 2) -> None:
    kids = " ".join(f"{4 + index * 2} 0 R" for index in range(count))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index in range(count):
        stream = (
            f"BT /F1 18 Tf 72 700 Td (Synthetic page {index + 1}) Tj "
            "0 -30 Td (x^2 + y^2 = 1) Tj ET\n"
            "0 0 1 RG 2 w 72 400 m 400 400 l 400 620 l S\n"
        ).encode()
        rotation = 90 if index == 1 else 0
        objects.extend([
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Rotate {rotation} /Resources << /Font << /F1 3 0 R >> >> "
                f"/Contents {5 + index * 2} 0 R >>"
            ).encode(),
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
            + stream + b"endstream",
        ])
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    path.write_bytes(data)


def png_bytes(color: str = "blue") -> bytes:
    with Image.new("RGB", (180, 100), color) as image, io.BytesIO() as buffer:
        image.save(buffer, format="PNG")
        return buffer.getvalue()


def response(
    value: ingestion.StrictModel | str,
    status: str = "completed",
    *,
    usage: dict[str, object] | None = None,
    model: str = "gpt-6.1-sol",
) -> Mock:
    text = value.model_dump_json() if isinstance(value, ingestion.StrictModel) else value
    result = Mock(status=status, output_text=text, usage=usage, model=model)
    result.model_dump.return_value = {
        "status": status, "output_text": text, "usage": usage, "model": model,
    }
    return result


def page_result(markdown: str = "# Source page") -> str:
    return markdown


def decision(
    disposition: str = "keep", kind: str = "diagram", alt: str = "Axes [x] and y"
) -> ingestion.FigureDecision:
    return ingestion.FigureDecision.model_validate({
        "decision": disposition, "kind": kind,
        "reason": "Synthetic classification for a pipeline test.", "alt_text": alt,
    })


def di_result(
    texts: list[str], *, numbers: list[int] | None = None, figures: list[DocumentFigure] | None = None
) -> AnalyzeResult:
    content = "".join(texts)
    numbers = numbers or list(range(1, len(texts) + 1))
    pages = []
    offset = 0
    for number, text in zip(numbers, texts, strict=True):
        formulas = []
        if ":formula:" in text:
            formulas.append(DocumentFormula(
                kind="display", value=r"x^2 + y^2 = 1",
                span=DocumentSpan(offset=offset + text.index(":formula:"), length=len(":formula:")),
                confidence=1.0, polygon=[1, 1, 2, 1, 2, 2, 1, 2],
            ))
        pages.append(DocumentPage(
            page_number=number, width=8.5, height=11, unit="inch",
            spans=[DocumentSpan(offset=offset, length=len(text))], formulas=formulas,
        ))
        offset += len(text)
    return AnalyzeResult(
        api_version="2024-11-30", model_id="prebuilt-layout",
        string_index_type="unicodeCodePoint", content_format="markdown",
        content=content, pages=pages, figures=figures or [],
    )


def di_figure(identifier: str, pages: tuple[int, ...] = (1,)) -> DocumentFigure:
    return DocumentFigure(
        id=identifier,
        caption=DocumentCaption(content="Source caption", spans=[]),
        bounding_regions=[
            BoundingRegion(page_number=page, polygon=[1, 1, 4, 1, 4, 3, 1, 3])
            for page in pages
        ],
    )


def clients(result: AnalyzeResult, outputs: list[Mock], crops: list[bytes] | None = None) -> tuple[Mock, Mock]:
    document = Mock()
    poller = document.begin_analyze_document.return_value
    poller.result.return_value = result
    poller.details = {"operation_id": "analysis-id"}
    document.get_analyze_result_figure.side_effect = [
        iter([crop]) for crop in crops or []
    ]
    openai = Mock()
    openai.responses.create.side_effect = outputs
    return document, openai


class LocalResponse(HttpResponse):
    def __init__(
        self, request: HttpRequest, status: int, body: bytes, headers: dict[str, str]
    ) -> None:
        super().__init__(request, None)
        self.status_code = status
        self.headers = CaseInsensitiveDict(headers)
        self.content_type = self.headers.get("content-type")
        self.reason = "Synthetic response"
        self._body = body

    def body(self) -> bytes:
        return self._body

    def read(self) -> bytes:
        return self._body

    def json(self) -> object:
        return json.loads(self._body)

    def iter_bytes(self, **kwargs: object):
        return iter([self._body])

    def stream_download(self, pipeline: object, **kwargs: object):
        return iter([self._body])


class LocalDocumentTransport(HttpTransport):
    def __init__(self, result: AnalyzeResult, crop: bytes) -> None:
        self.result = result
        self.crop = crop
        self.requests: list[HttpRequest] = []
        self.uploaded = b""

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def send(self, request: HttpRequest, **kwargs: object) -> HttpResponse:
        self.requests.append(request)
        if request.method == "POST":
            self.uploaded = request.body.read()
            return LocalResponse(request, 202, b"", {
                "operation-location": (
                    "https://di.example.com/documentintelligence/documentModels/"
                    "prebuilt-layout/analyzeResults/analysis-id?api-version=2024-11-30"
                ),
                "retry-after": "0",
            })
        if "/figures/" in request.url:
            return LocalResponse(request, 200, self.crop, {"content-type": "image/png"})
        return LocalResponse(request, 200, json.dumps({
            "status": "succeeded",
            "createdDateTime": "2026-09-19T12:00:00Z",
            "lastUpdatedDateTime": "2026-09-19T12:00:01Z",
            "analyzeResult": self.result.as_dict(),
        }).encode(), {"content-type": "application/json"})


class ConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = {
            "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": "https://di.cognitiveservices.azure.com",
            "AZURE_AI_PROJECT_ENDPOINT": "https://ai.services.ai.azure.com/api/projects/course",
            "AZURE_OPENAI_DEPLOYMENT": "vision-deployment",
        }

    def test_project_endpoint_and_resource_alternative(self) -> None:
        settings = ingestion.settings_from_env(self.env)
        self.assertEqual(
            settings.openai_base_url,
            "https://ai.services.ai.azure.com/api/projects/course/openai/v1/",
        )
        del self.env["AZURE_AI_PROJECT_ENDPOINT"]
        self.env["AZURE_OPENAI_BASE_URL"] = "https://ai.openai.azure.com/openai/v1/"
        self.assertEqual(
            ingestion.settings_from_env(self.env).openai_base_url,
            self.env["AZURE_OPENAI_BASE_URL"],
        )

    def test_configuration_is_explicit_and_does_not_accept_credentials_in_urls(self) -> None:
        for key, value in [
            ("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", ""),
            ("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "http://di.example.com"),
            ("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://user:secret@di.example.com"),
            ("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://di.example.com?key=secret"),
            ("AZURE_AI_PROJECT_ENDPOINT", "https://ai.services.ai.azure.com"),
            ("AZURE_OPENAI_DEPLOYMENT", ""),
        ]:
            with self.subTest(key=key, value=value), self.assertRaises(ingestion.DigestionError):
                ingestion.settings_from_env({**self.env, key: value})
        with self.assertRaisesRegex(ingestion.DigestionError, "exactly one"):
            ingestion.settings_from_env({
                **self.env, "AZURE_OPENAI_BASE_URL": "https://ai.openai.azure.com/openai/v1/"
            })

    def test_page_ranges_are_original_sorted_page_numbers(self) -> None:
        self.assertEqual(ingestion.selected_pages("7,1-3,2", 8), [1, 2, 3, 7])
        self.assertEqual(ingestion.page_ranges([1, 2, 3, 7]), "1-3,7")
        self.assertEqual(ingestion.selected_pages(None, 2), [1, 2])
        for spec in ("", "0", "3-1", "2-4", "1,,2", "1-2-3", "-1"):
            with self.subTest(spec=spec), self.assertRaises(ingestion.DigestionError):
                ingestion.selected_pages(spec, 3)

    def test_page_limits(self) -> None:
        for count in (0, 2001):
            with self.assertRaises(ingestion.DigestionError):
                ingestion.selected_pages(None, count)

    def test_unicode_spans_and_invalid_offsets(self) -> None:
        text = "\U0001f4da\nMath \u03c0 and accents \u00e9"
        self.assertEqual(
            ingestion.span_text(text, [DocumentSpan(offset=2, length=6)]), "Math \u03c0"
        )
        self.assertEqual(
            ingestion.span_text("computing", [
                DocumentSpan(offset=0, length=3), DocumentSpan(offset=3, length=6),
            ]), "computing",
        )
        self.assertEqual(
            ingestion.span_text("one GAP two", [
                DocumentSpan(offset=0, length=3), DocumentSpan(offset=8, length=3),
            ]), "one\ntwo",
        )
        for spans in (
            [DocumentSpan(offset=-1, length=1)],
            [DocumentSpan(offset=0, length=len(text) + 1)],
            [DocumentSpan(offset=3, length=-1)],
            [DocumentSpan(offset=0, length=5), DocumentSpan(offset=4, length=1)],
        ):
            with self.assertRaises(ingestion.DigestionError):
                ingestion.span_text(text, spans)


class OutputContractTests(unittest.TestCase):
    def test_page_prompt_requires_conservative_transcription_and_math_boundaries(self) -> None:
        prompt = ingestion.PAGE_PROMPT
        for instruction in (
            "Make the smallest changes needed",
            "Correct only\nimage-evidenced extraction errors",
            "Preserve source mistakes",
            "LaTeX commands belong only inside math delimiters",
            "ordinary spaces, not\nLaTeX spacing commands",
            "Do not wrap an otherwise textual heading in math",
            "Genuine formulas within headings may use\ninline math",
            "Before returning, check",
            "this is not a source-fidelity check",
            "Return only Markdown",
            "without a JSON envelope",
            "mark remaining uncertainty honestly at its source position in Markdown",
            "return <!-- Blank page. --> rather than\nan empty response",
        ):
            with self.subTest(instruction=instruction):
                self.assertIn(instruction, prompt)
        self.assertNotIn("or validate its contents", prompt)
        self.assertNotIn("fixes", prompt)
        self.assertNotIn("confidence", prompt)

    def test_semantically_invalid_decisions_are_not_accepted(self) -> None:
        for value in (
            decision("keep", "icon"), decision("keep", "logo"),
            decision("keep", "diagram", ""), decision("discard", "unclear"),
        ):
            with self.assertRaises(ingestion.DigestionError):
                ingestion.validate_figure_decision(value)
        ingestion.validate_figure_decision(decision("discard", "icon", ""))

    def test_figure_schema_remains_strict(self) -> None:
        schema = ingestion.FigureDecision.model_json_schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), {"decision", "kind", "reason", "alt_text"})
        with self.assertRaises(ValidationError):
            ingestion.FigureDecision.model_validate({
                **decision().model_dump(), "extra_field": "not allowed",
            })

    def test_markdown_format_parser_accepts_math_tables_html_and_literal_text(self) -> None:
        markdown = (
            "# Algebra\n\n$x$ and $x$.\n\n$$\n\\begin{cases}x=1\\\\y=2\\end{cases}\n$$\n\n"
            "| Symbol | Value |\n| --- | --- |\n| x | 1 |\n\n"
            "<table><tr><td>Source</td></tr></table>\n\n"
            "An unmatched $ and an ordinary {{math:example}} are literal text.\n"
        )
        ingestion.validate_markdown_format(markdown)

    def test_markdown_parser_failure_is_explicit_and_keeps_its_cause(self) -> None:
        error = ValueError("Synthetic parser failure")
        with (
            patch.object(ingestion.MarkdownIt, "parse", side_effect=error),
            self.assertRaisesRegex(ingestion.DigestionError, "Markdown format parser failed") as caught,
        ):
            ingestion.validate_markdown_format("# Source")
        self.assertIs(caught.exception.__cause__, error)

    def test_latex_review_flags_known_commands_in_headings_and_ordinary_text(self) -> None:
        for command in sorted(ingestion.REVIEW_LATEX_COMMANDS):
            for markdown in (
                f"# 1 \\{command} Title",
                f"## 1.5\\{command} Title",
                f"Title \\{command}\n=====",
                f"Ordinary \\{command} text.",
                f"- Ordinary **\\{command}** text.",
                f"| Name | Value |\n| --- | --- |\n| Title | \\{command} |",
            ):
                with self.subTest(command=command, markdown=markdown):
                    issues = ingestion.review_latex_leakage(markdown, 7)
                    self.assertEqual(len(issues), 1)
                    self.assertIn("Page 7,", issues[0])
                    self.assertIn("possible LaTeX leakage", issues[0])
                    self.assertIn(repr(f"\\{command}"), issues[0])

    def test_latex_review_uses_page_local_block_line_ranges(self) -> None:
        markdown = "# Title\n\n## 1.5\\quad Section\n\nFirst line\nthen \\frac{x}{y}."
        issues = ingestion.review_latex_leakage(markdown, 4)
        self.assertEqual(len(issues), 2)
        self.assertIn("Page 4, line 3:", issues[0])
        self.assertIn("Page 4, lines 5-6:", issues[1])
        self.assertIn("1.5\\\\quad Section", issues[0])

    def test_latex_review_ignores_math_code_paths_and_raw_html(self) -> None:
        examples = (
            r"# Formula $x\quad y$",
            r"Inline $\frac{x}{y}$.",
            "$$\nx\\quad y\n$$",
            r"Literal `\quad` and `\mathbb{R}`.",
            "```latex\n\\quad\n```",
            "    \\quad\n",
            r"C:\course\text.txt and D:\mathbb\quad.pdf",
            r"\\server\share\quad.txt",
            r".\folder\mathbb.txt and ..\text\quad.pdf",
            r"[Link](https://example.com/\quad) ![Figure](figures/\quad.png)",
            r'<span title="\quad">Ordinary text</span>',
            '<div>\n\\quad\n</div>',
            r"\quadruple \leftover \textual \custom",
        )
        for markdown in examples:
            with self.subTest(markdown=markdown):
                self.assertEqual(ingestion.review_latex_leakage(markdown, 1), [])

    def test_latex_review_checks_link_labels_but_preserves_valid_math(self) -> None:
        markdown = r"## 2\quad Title $x\qquad y$ and `\quad` [\frac](https://example.com)"
        issues = ingestion.review_latex_leakage(markdown, 2)
        self.assertEqual(len(issues), 2)
        self.assertIn(repr(r"\quad"), issues[0])
        self.assertIn(repr(r"\frac"), issues[1])

    def test_latex_review_bounds_excerpts_and_keeps_parser_errors_explicit(self) -> None:
        issues = ingestion.review_latex_leakage("x" * 1000 + r"\quad " + "y" * 1000, 1)
        self.assertEqual(len(issues), 1)
        self.assertLess(len(issues[0]), 200)
        with (
            patch.object(ingestion.MarkdownIt, "parse", side_effect=ValueError("Broken")),
            self.assertRaisesRegex(ingestion.DigestionError, "Markdown format parser failed"),
        ):
            ingestion.review_latex_leakage("# Title", 1)


class RunDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "existing"
        self.output.mkdir()

    @staticmethod
    def windows_error(code: int) -> OSError:
        error = OSError("Synthetic Windows replacement failure")
        error.winerror = code
        return error

    def test_transient_windows_replacement_errors_retry_without_rewriting_diagnostics(self) -> None:
        original_replace = Path.replace
        run = ingestion.RunDiagnostics(self.root / "source.pdf", self.output)
        run.report_path = self.output / "run.json"
        previous = '{"status": "previous"}'
        for code in (5, 32, 33):
            run.report_path.write_text(previous, encoding="utf-8")
            calls = []

            def replace(pending, target):
                calls.append((pending, target))
                if len(calls) <= 2:
                    raise self.windows_error(code)
                return original_replace(pending, target)

            def wait(delay):
                self.assertEqual(run.report_path.read_text(encoding="utf-8"), previous)
                self.assertEqual(json.loads(calls[-1][0].read_text(encoding="utf-8"))["status"], "running")

            with (
                self.subTest(winerror=code),
                patch.object(Path, "replace", autospec=True, side_effect=replace) as replacing,
                patch.object(ingestion.time, "sleep", side_effect=wait) as sleeping,
                patch.object(ingestion, "write_json", wraps=ingestion.write_json) as writing,
                self.assertLogs("ingestion", "WARNING") as logs,
            ):
                run.update("Saving progress")
            self.assertEqual(replacing.call_count, 3)
            self.assertEqual(writing.call_count, 1)
            self.assertEqual([call.args[0] for call in sleeping.call_args_list], [0.1, 0.2])
            self.assertIn(f"WinError {code}", "\n".join(logs.output))
            self.assertIn("local retry 2/5", "\n".join(logs.output))
            self.assertEqual(json.loads(run.report_path.read_text(encoding="utf-8"))["stage"], "Saving progress")
            self.assertFalse((self.output / "run.json.tmp").exists())

    def test_persistent_windows_replacement_error_exhausts_bounded_backoff(self) -> None:
        run = ingestion.RunDiagnostics(self.root / "source.pdf", self.output)
        run.report_path = self.output / "run.json"
        previous = '{"status": "previous"}'
        run.report_path.write_text(previous, encoding="utf-8")
        error = self.windows_error(5)
        with (
            patch.object(Path, "replace", side_effect=error) as replacing,
            patch.object(ingestion.time, "sleep") as sleeping,
            self.assertLogs("ingestion", "WARNING") as logs,
            self.assertRaises(OSError) as caught,
        ):
            run.save()
        self.assertIs(caught.exception, error)
        self.assertEqual(replacing.call_count, 6)
        self.assertEqual([call.args[0] for call in sleeping.call_args_list], [0.1, 0.2, 0.4, 0.8, 1.6])
        self.assertAlmostEqual(sum(call.args[0] for call in sleeping.call_args_list), 3.1)
        self.assertEqual(len(logs.output), 5)
        self.assertEqual(run.report_path.read_text(encoding="utf-8"), previous)
        self.assertTrue((self.output / "run.json.tmp").is_file())

    def test_other_replacement_errors_and_temporary_write_errors_are_not_retried(self) -> None:
        run = ingestion.RunDiagnostics(self.root / "source.pdf", self.output)
        run.report_path = self.output / "run.json"
        for error in (PermissionError("Non-Windows denial"), self.windows_error(2), self.windows_error(112)):
            with (
                self.subTest(error=error),
                patch.object(Path, "replace", side_effect=error) as replacing,
                patch.object(ingestion.time, "sleep") as sleeping,
                self.assertRaises(OSError) as caught,
            ):
                run.save()
            self.assertIs(caught.exception, error)
            replacing.assert_called_once()
            sleeping.assert_not_called()
        with (
            patch.object(ingestion, "write_json", side_effect=self.windows_error(5)),
            patch.object(Path, "replace") as replacing,
            patch.object(ingestion.time, "sleep") as sleeping,
            self.assertRaises(OSError),
        ):
            run.save()
        replacing.assert_not_called()
        sleeping.assert_not_called()

    def test_backoff_sleep_remains_interruptible(self) -> None:
        run = ingestion.RunDiagnostics(self.root / "source.pdf", self.output)
        run.report_path = self.output / "run.json"
        with (
            patch.object(Path, "replace", side_effect=self.windows_error(32)) as replacing,
            patch.object(ingestion.time, "sleep", side_effect=KeyboardInterrupt()) as sleeping,
            self.assertLogs("ingestion", "WARNING"),
            self.assertRaises(KeyboardInterrupt),
        ):
            run.save()
        replacing.assert_called_once()
        sleeping.assert_called_once_with(0.1)

    @unittest.skipUnless(sys.platform == "win32", "Requires Windows file-sharing semantics")
    def test_real_windows_reader_lock_recovers_after_reader_closes(self) -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        run = ingestion.RunDiagnostics(self.root / "source.pdf", self.output)
        run.report_path = self.output / "run.json"
        previous = '{"status": "previous"}'
        run.report_path.write_text(previous, encoding="utf-8")
        # A reader allows read/write sharing, but not deletion or replacement.
        handle = kernel32.CreateFileW(str(run.report_path), 0x80000000, 3, None, 3, 0x80, None)
        self.assertNotEqual(handle, wintypes.HANDLE(-1).value, str(ctypes.WinError(ctypes.get_last_error())))
        closed = False

        def release_lock(delay):
            nonlocal closed
            self.assertEqual(run.report_path.read_text(encoding="utf-8"), previous)
            self.assertTrue(kernel32.CloseHandle(handle))
            closed = True

        try:
            with (
                patch.object(ingestion.time, "sleep", side_effect=release_lock) as sleeping,
                self.assertLogs("ingestion", "WARNING"),
            ):
                run.update("Saving progress after reader closes")
            sleeping.assert_called_once_with(0.1)
            self.assertEqual(
                json.loads(run.report_path.read_text(encoding="utf-8"))["stage"],
                "Saving progress after reader closes",
            )
            self.assertFalse((self.output / "run.json.tmp").exists())
        finally:
            if not closed:
                kernel32.CloseHandle(handle)

    def test_existing_old_partial_run_explains_that_original_error_is_unavailable(self) -> None:
        sentinel = self.output / "source-extraction.json"
        sentinel.write_text("unchanged", encoding="utf-8")
        with self.assertRaises(ingestion.OutputExistsError) as caught:
            ingestion.ensure_new_output(self.output)
        message = str(caught.exception)
        self.assertIn("No completion manifest", message)
        self.assertIn("No saved failure report", message)
        self.assertIn("did not start PDF analysis", message)
        self.assertIn("--output", message)
        self.assertIn("Do not create that directory first", message)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "unchanged")
        self.assertFalse((self.output / "run.json").exists())

    def test_existing_complete_digest_is_identified_and_preserved(self) -> None:
        manifest = self.output / "manifest.json"
        manifest.write_text('{"status": "needs_review"}', encoding="utf-8")
        (self.output / "document.md").write_text("# Synthetic source", encoding="utf-8")
        with self.assertRaisesRegex(ingestion.OutputExistsError, "completed digest.*needs_review"):
            ingestion.ensure_new_output(self.output)
        self.assertEqual(manifest.read_text(encoding="utf-8"), '{"status": "needs_review"}')

    def test_previous_failure_is_shown_without_overwriting_its_report(self) -> None:
        report = self.output / "run.json"
        text = json.dumps({
            "status": "failed",
            "stage": "OpenAI: reconciling page 4",
            "error": {"message": "Synthetic deployment not found"},
        })
        report.write_text(text, encoding="utf-8")
        with self.assertRaises(ingestion.OutputExistsError) as caught:
            ingestion.ensure_new_output(self.output)
        self.assertIn("OpenAI: reconciling page 4", str(caught.exception))
        self.assertIn("Synthetic deployment not found", str(caught.exception))
        self.assertEqual(report.read_text(encoding="utf-8"), text)

    def test_unreadable_metadata_does_not_disguise_the_output_conflict(self) -> None:
        (self.output / "manifest.json").write_text("{broken", encoding="utf-8")
        (self.output / "run.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(ingestion.OutputExistsError) as caught:
            ingestion.ensure_new_output(self.output)
        self.assertIn("JSONDecodeError", str(caught.exception))
        self.assertIn("Expected a JSON object", str(caught.exception))
        self.assertIn("fresh path", str(caught.exception))

    def test_file_instead_of_output_directory_is_reported(self) -> None:
        path = self.root / "not-a-directory"
        path.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ingestion.OutputExistsError, "path is a file"):
            ingestion.ensure_new_output(path)
        self.assertEqual(path.read_text(encoding="utf-8"), "keep")

    def test_real_cli_output_conflict_produces_actionable_stderr(self) -> None:
        result = subprocess.run(
            [
                sys.executable, str(Path(ingestion.__file__).resolve()),
                str(self.root / "not-opened.pdf"), "--output", str(self.output), "--debug",
            ],
            capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Failed at stage: Preflight", result.stderr)
        self.assertIn("No saved failure report", result.stderr)
        self.assertIn("Choose a fresh path", result.stderr)
        self.assertIn("Traceback (most recent call last)", result.stderr)
        self.assertNotIn("Initializing Azure clients", result.stderr)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_diagnostic_write_error_does_not_replace_the_original_failure(self) -> None:
        run = ingestion.RunDiagnostics(self.root / "source.pdf", self.output)
        run.report_path = self.output / "run.json"
        with (
            patch.object(run, "save", side_effect=PermissionError("Synthetic disk lock")),
            self.assertLogs("ingestion", "ERROR") as logs,
            self.assertRaisesRegex(ingestion.DigestionError, "Original failure"),
            run,
        ):
            raise ingestion.DigestionError("Original failure")
        self.assertIn("Could not save diagnostics", " ".join(logs.output))
        self.assertEqual(run.error["message"], "Original failure")
        self.assertFalse(run.failure_saved)

    def test_unexpected_programming_error_is_saved_but_not_swallowed(self) -> None:
        run = ingestion.RunDiagnostics(self.root / "source.pdf", self.output)
        run.report_path = self.output / "run.json"
        run.update("Synthetic failing stage")
        with self.assertRaisesRegex(TypeError, "Synthetic bug"), run:
            raise TypeError("Synthetic bug")
        saved = json.loads(run.report_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["stage"], "Synthetic failing stage")
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["error"]["type"], "TypeError")
        self.assertIn("Traceback", saved["error"]["traceback"])
        self.assertFalse((self.output / "run.json.tmp").exists())

    def test_underlying_connection_cause_is_visible_without_debug(self) -> None:
        error = ingestion.APIConnectionError(request=Mock())
        error.__cause__ = OSError("Synthetic certificate verification failure")
        run = ingestion.RunDiagnostics(self.root / "source.pdf", self.output)
        run.stage = "OpenAI: reconciling page 1"
        with self.assertLogs("ingestion", "ERROR") as logs:
            ingestion.report_failure(run, error, debug=False)
        self.assertIn("Synthetic certificate verification failure", "\n".join(logs.output))
        self.assertIn("do not disable TLS", "\n".join(logs.output))
        self.assertNotIn("Traceback (most recent call last)", "\n".join(logs.output))


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.pdf"
        self.output = self.root / "digest"
        make_pdf(self.source)

    def run_digest(
        self, result: AnalyzeResult, outputs: list[Mock], crops: list[bytes] | None = None,
        **options: object,
    ) -> tuple[dict[str, object], Mock, Mock]:
        document, openai = clients(result, outputs, crops)
        options.setdefault("page_review", False)
        manifest = ingestion.digest_pdf(
            self.source, self.output, document, openai, "vision-deployment", dpi=72, **options
        )
        return manifest, document, openai

    def test_source_is_preserved_byte_for_byte_and_linked_in_manifest(self) -> None:
        original = self.source.read_bytes()
        manifest, document, _ = self.run_digest(
            di_result(["One", "Two"]),
            [response(page_result("One")), response(page_result("Two"))],
        )
        retained = self.output / manifest["source"]["path"]
        self.assertEqual(retained.read_bytes(), original)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(manifest["source"]["name"], self.source.name)
        self.assertEqual(manifest["source"]["sha256"], ingestion.hashlib.sha256(original).hexdigest())
        document.begin_analyze_document.assert_called_once()

    def test_selected_pages_still_preserve_the_complete_source(self) -> None:
        original = self.source.read_bytes()
        manifest, _, _ = self.run_digest(
            di_result(["Two"], numbers=[2]), [response(page_result("Two"))], pages="2",
        )
        retained = self.output / manifest["source"]["path"]
        self.assertEqual(retained.read_bytes(), original)
        with pymupdf.open(retained) as pdf:
            self.assertEqual(len(pdf), 2)
        self.assertEqual([page["number"] for page in manifest["pages"]], [2])

    def test_copy_failure_is_diagnosed_before_cloud_submission(self) -> None:
        document, openai = clients(di_result(["One", "Two"]), [])
        with (
            patch.object(ingestion.shutil, "copyfile", side_effect=OSError("Copy denied")),
            self.assertRaisesRegex(OSError, "Copy denied"),
        ):
            ingestion.digest_pdf(self.source, self.output, document, openai, "vision", dpi=72)
        document.begin_analyze_document.assert_not_called()
        openai.responses.create.assert_not_called()
        report = json.loads((self.output / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["stage"], "Preserving original PDF")
        self.assertFalse((self.output / "manifest.json").exists())

    def test_corrupt_copy_cannot_submit_to_cloud(self) -> None:
        document, openai = clients(di_result(["One", "Two"]), [])
        def corrupt_copy(source: Path, destination: Path) -> None:
            destination.write_bytes(b"wrong bytes")
        with (
            patch.object(ingestion.shutil, "copyfile", side_effect=corrupt_copy),
            self.assertRaisesRegex(ingestion.DigestionError, "does not match"),
        ):
            ingestion.digest_pdf(self.source, self.output, document, openai, "vision", dpi=72)
        document.begin_analyze_document.assert_not_called()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_full_digest_curates_native_crops_preserves_math_and_provenance(self) -> None:
        result = di_result(
            ["# G\u00e9om\u00e9trie \U0001f4da\n:formula:\n", "# Application\n"],
            figures=[di_figure("opaque/figure-A"), di_figure("opaque/logo")],
        )
        corrected = page_result(
            "# G\u00e9om\u00e9trie\n\n$$\nx^2+y^2=1\n$$\n\n"
            "![Axes](figures/figure-0001.png)\nSource caption",
        )
        crop, logo = png_bytes(), png_bytes("red")
        manifest, document, openai = self.run_digest(
            result,
            [response(decision()), response(decision("discard", "logo", "")),
             response(corrected), response(page_result("# Application"))],
            [crop, logo], high_resolution_ocr=True,
        )
        self.assertEqual(manifest["schema_version"], 3)
        self.assertEqual(manifest["status"], "extracted")
        self.assertEqual(manifest["source"]["page_count"], 2)
        self.assertEqual(len(manifest["source"]["sha256"]), 64)
        self.assertEqual(
            [path.name for path in (self.output / "figures").iterdir()], ["figure-0001.png"]
        )
        self.assertEqual((self.output / "figures" / "figure-0001.png").read_bytes(), crop)
        self.assertEqual((self.output / "raw" / "figures" / "figure-0002.png").read_bytes(), logo)
        self.assertEqual(
            (self.output / "raw" / "document-intelligence.md").read_text(encoding="utf-8"),
            result.content,
        )
        markdown = (self.output / "document.md").read_text(encoding="utf-8")
        self.assertIn("<!-- page: 1 -->", markdown)
        self.assertIn("<!-- page: 2 -->", markdown)
        self.assertIn("$$\nx^2+y^2=1\n$$", markdown)
        self.assertNotIn(":formula:", markdown)
        self.assertNotIn("figure-0002.png", markdown)
        self.assertEqual(
            (self.output / "document.md").read_bytes(),
            (
                f"<!-- page: 1 -->\n\n{corrected}"
                "\n\n<!-- page: 2 -->\n\n# Application"
            ).encode("utf-8"),
        )
        self.assertFalse((self.output / "pages").exists())
        self.assertFalse((self.output / "raw" / "pages" / "page-0001.di.md").exists())
        saved = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["figures"][1]["decision"], "discard")
        self.assertEqual(saved["figures"][0]["caption"], "Source caption")
        self.assertEqual(saved["configuration"]["page_reasoning_effort"], "high")
        self.assertEqual(saved["configuration"]["figure_reasoning_effort"], "model_default")
        self.assertEqual(saved["costs"]["openai"]["api_calls"], 4)
        self.assertEqual(saved["costs"]["document_intelligence"]["pages_processed"], 2)
        self.assertTrue(saved["costs"]["document_intelligence"]["high_resolution_ocr"])
        run = json.loads((self.output / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(run["schema_version"], 1)
        self.assertEqual(run["status"], "extracted")
        self.assertEqual(run["stage"], "Complete")
        self.assertEqual(run["pages"], "1-2")
        self.assertEqual(run["document_intelligence_operation_id"], "analysis-id")
        self.assertIsNone(run["error"])
        request = document.begin_analyze_document.call_args.kwargs
        self.assertEqual(request["pages"], "1-2")
        self.assertEqual(request["string_index_type"], "unicodeCodePoint")
        self.assertEqual(request["output_content_format"], "markdown")
        self.assertEqual(request["output"], ["figures"])
        self.assertEqual(request["features"], ["formulas", "ocrHighResolution"])
        self.assertEqual(
            document.get_analyze_result_figure.call_args_list[0].kwargs,
            {"model_id": "prebuilt-layout", "result_id": "analysis-id", "figure_id": "opaque/figure-A"},
        )
        self.assertEqual(openai.responses.create.call_count, 4)
        for index, call in enumerate(openai.responses.create.call_args_list):
            self.assertFalse(call.kwargs["store"])
            if index < 2:
                self.assertNotIn("reasoning", call.kwargs)
                self.assertEqual(call.kwargs["text"]["format"]["type"], "json_schema")
                self.assertTrue(call.kwargs["text"]["format"]["strict"])
                self.assertEqual(call.kwargs["text"]["format"]["name"], "FigureDecision")
                self.assertEqual(
                    call.kwargs["text"]["format"]["schema"],
                    ingestion.FigureDecision.model_json_schema(),
                )
            else:
                self.assertEqual(call.kwargs["reasoning"], {"effort": "high"})
                self.assertEqual(call.kwargs["text"]["format"], {"type": "text"})
            self.assertEqual(call.kwargs["model"], "vision-deployment")
            self.assertTrue(all(item["type"] == "message" for item in call.kwargs["input"]))
        page_request = openai.responses.create.call_args_list[2].kwargs
        context = json.loads(page_request["input"][1]["content"][0]["text"])
        self.assertEqual(context["figures"][0]["asset_path"], "figures/figure-0001.png")
        self.assertNotIn("id", context["detected_formulas"][0])
        with Image.open(self.output / "raw" / "pages" / "page-0002.png") as rotated:
            self.assertEqual(rotated.size, (792, 612))

    def test_selected_page_uses_original_pdf_number_and_rotation(self) -> None:
        manifest, document, _ = self.run_digest(
            di_result(["Second page"], numbers=[2]),
            [response(page_result("Second page"))], pages="2",
        )
        self.assertEqual([page["number"] for page in manifest["pages"]], [2])
        self.assertEqual(document.begin_analyze_document.call_args.kwargs["pages"], "2")
        self.assertFalse((self.output / "pages").exists())
        markdown = (self.output / "document.md").read_text(encoding="utf-8")
        self.assertEqual(markdown, "<!-- page: 2 -->\n\nSecond page")
        with Image.open(self.output / "raw" / "pages" / "page-0002.png") as image:
            self.assertEqual(image.size, (792, 612))

    def test_page_groups_process_only_the_requested_original_pages(self) -> None:
        make_pdf(self.source, count=4)
        manifest, document, openai = self.run_digest(
            di_result(["Second", "Fourth"], numbers=[2, 4]),
            [response(page_result("Second")), response(page_result("Fourth"))],
            pages="4,2",
        )
        self.assertEqual([page["number"] for page in manifest["pages"]], [2, 4])
        self.assertEqual(manifest["source"]["page_count"], 4)
        self.assertEqual(document.begin_analyze_document.call_args.kwargs["pages"], "2,4")
        self.assertEqual(openai.responses.create.call_count, 2)
        self.assertEqual([path.name for path in self.output.glob("*.md")], ["document.md"])
        self.assertEqual(
            (self.output / "document.md").read_text(encoding="utf-8"),
            "<!-- page: 2 -->\n\nSecond\n\n<!-- page: 4 -->\n\nFourth",
        )

    def test_direct_markdown_preserves_tex_unicode_quotes_and_whitespace(self) -> None:
        result = di_result([":formula:"])
        result.pages[0].formulas[0].value = "s i"
        result.pages[0].formulas[0].kind = "inline"
        page = page_result(
            "  si la condition est vraie, \"G\u00e9om\u00e9trie\" \U0001f4da\n\n"
            r"$\boldsymbol{R}$, $\mathcal{D}_f$, $\mathbb{R}$ et $\varphi$."
            "\n\n$$\n" r"\begin{aligned}x&=\frac{1}{2}\\y&=\text{oui}\end{aligned}"
            "\n$$\n\n",
        )
        with self.assertLogs("ingestion", "WARNING"):
            manifest, _, _ = self.run_digest(result, [response(page)], pages="1")
        self.assertEqual(manifest["status"], "needs_review")
        self.assertIn(r"Undefined control sequence \boldsymbol", manifest["issues"][0])
        self.assertNotIn("fixes", manifest["pages"][0])
        self.assertNotIn("formulas", manifest["pages"][0])
        self.assertNotIn("formula_corrections", manifest["pages"][0])
        expected = f"<!-- page: 1 -->\n\n{page}".encode("utf-8")
        self.assertEqual((self.output / "document.md").read_bytes(), expected)
        self.assertEqual((self.output / "raw" / "assembled.md").read_bytes(), expected)
        raw = json.loads(
            (self.output / "raw" / "pages" / "page-0001.response.json").read_text(encoding="utf-8")
        )
        self.assertEqual(raw["output_text"], page)

    def test_real_sdk_page_text_survives_outer_json_without_inner_decoding(self) -> None:
        markdown = '  "G\u00e9om\u00e9trie"\n\n' + r"$\boldsymbol{R}$ et $\text{oui}$." + "\n"
        sdk_response = Response.model_validate_json(json.dumps({
            "id": "resp-test", "created_at": 0, "model": "vision", "object": "response",
            "status": "completed", "parallel_tool_calls": False, "tool_choice": "auto",
            "tools": [], "output": [{
                "id": "msg-test", "type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": markdown, "annotations": []}],
            }],
        }))
        client = Mock()
        client.responses.create.return_value = sdk_response
        raw_path = self.root / "page.response.json"
        extracted = ingestion.analyze_image(
            client, "vision", ingestion.PAGE_PROMPT, {"page_number": "0001"},
            png_bytes(), None, raw_path, 16000, ingestion.UsageTotals(), "page_transcription",
        )
        self.assertEqual(extracted, markdown)
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        self.assertEqual(raw, sdk_response.model_dump(mode="json"))
        self.assertEqual(raw["output"][0]["content"][0]["text"], markdown)

    def test_latex_leakage_requires_review_without_rewriting_or_retrying(self) -> None:
        page = page_result("## 1.5\\quad Title\n\n$x\\quad y$\n")
        with self.assertLogs("ingestion", "WARNING") as logs:
            manifest, _, openai = self.run_digest(
                di_result(["Second page"], numbers=[2]),
                [response(page)], pages="2",
            )
        self.assertEqual(manifest["status"], "needs_review")
        self.assertEqual(len(manifest["issues"]), 1)
        self.assertIn("Page 2, line 1:", manifest["issues"][0])
        self.assertIn(manifest["issues"][0], "\n".join(logs.output))
        self.assertEqual(openai.responses.create.call_count, 1)
        expected = f"<!-- page: 2 -->\n\n{page}".encode("utf-8")
        self.assertEqual((self.output / "document.md").read_bytes(), expected)
        self.assertEqual((self.output / "raw" / "assembled.md").read_bytes(), expected)
        raw = json.loads(
            (self.output / "raw" / "pages" / "page-0002.response.json").read_text(encoding="utf-8")
        )
        self.assertEqual(raw["output_text"], page)
        run = json.loads((self.output / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(run["status"], "needs_review")
        saved = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["issues"], manifest["issues"])

    def test_latex_and_figure_issues_are_collected_together(self) -> None:
        result = di_result(
            ["First page", "Second page"], figures=[di_figure("cross-page", (1, 2))]
        )
        with self.assertLogs("ingestion", "WARNING"):
            manifest, _, openai = self.run_digest(
                result,
                [response(page_result("# 1\\quad Title")), response(page_result("Second"))],
                [png_bytes()],
            )
        self.assertEqual(manifest["status"], "needs_review")
        self.assertEqual(len(manifest["issues"]), 2)
        self.assertIn("figure-0001:", manifest["issues"][0])
        self.assertIn("Page 1, line 1:", manifest["issues"][1])
        self.assertEqual(openai.responses.create.call_count, 2)

    def test_real_di_sdk_serialization_polling_and_crop_download(self) -> None:
        result = di_result(["First", "Second"], figures=[di_figure("opaque-id")])
        transport = LocalDocumentTransport(result, png_bytes())
        openai = Mock()
        openai.responses.create.side_effect = [
            response(decision()),
            response(page_result("First\n![Diagram](figures/figure-0001.png)")),
            response(page_result("Second")),
        ]
        with DocumentIntelligenceClient(
            "https://di.example.com", AzureKeyCredential("synthetic-test-key"),
            transport=transport, polling_interval=0, api_version=ingestion.DI_API_VERSION,
        ) as document:
            manifest = ingestion.digest_pdf(
                self.source, self.output, document, openai, "vision-deployment", dpi=72,
                page_review=False,
            )
        self.assertEqual(manifest["status"], "extracted")
        self.assertEqual(transport.uploaded, self.source.read_bytes())
        self.assertEqual(len(transport.requests), 3)
        analyze, poll, crop = transport.requests
        query = parse_qs(urlsplit(analyze.url).query)
        self.assertEqual(query["api-version"], ["2024-11-30"])
        self.assertEqual(query["stringIndexType"], ["unicodeCodePoint"])
        self.assertEqual(query["features"], ["formulas"])
        self.assertEqual(query["outputContentFormat"], ["markdown"])
        self.assertEqual(query["output"], ["figures"])
        self.assertIn("/analyzeResults/analysis-id", poll.url)
        self.assertIn("/analyzeResults/analysis-id/figures/opaque-id", crop.url)
        self.assertEqual(
            (self.output / "figures" / "figure-0001.png").read_bytes(), transport.crop
        )

    def test_real_openai_sdk_sends_explicit_multimodal_messages_and_response_formats(self) -> None:
        for schema in (None, ingestion.FigureDecision, ingestion.PageReview):
            with self.subTest(schema=schema):
                self.assert_openai_wire_format(schema)

    def assert_openai_wire_format(self, schema: type[ingestion.StrictModel] | None) -> None:
        with (
            DefaultHttpxClient() as transport,
            patch.object(transport, "send", side_effect=OSError("Offline wire capture")) as send,
            ingestion.OpenAI(
                base_url="https://example.invalid/openai/v1/",
                api_key="synthetic-test-key", http_client=transport, max_retries=0,
            ) as client,
            self.assertRaises((ingestion.APIConnectionError, OSError)),
        ):
            ingestion.analyze_image(
                client, "vision", ingestion.PAGE_PROMPT if schema is None else ingestion.PAGE_REVIEW_PROMPT,
                {"page_number": "0001"}, png_bytes(), schema, self.root / "response.json", 16000,
                ingestion.UsageTotals(), "page_review",
            )
        send.assert_called_once()
        request = send.call_args.args[0]
        payload = json.loads(request.content)
        self.assertEqual([item["type"] for item in payload["input"]], ["message", "message"])
        self.assertEqual(payload["input"][0]["role"], "system")
        self.assertEqual(payload["input"][0]["content"][0]["type"], "input_text")
        self.assertEqual(payload["input"][1]["role"], "user")
        self.assertEqual(
            [item["type"] for item in payload["input"][1]["content"]],
            ["input_text", "input_image"],
        )
        self.assertTrue(
            payload["input"][1]["content"][1]["image_url"].startswith("data:image/png;base64,")
        )
        self.assertFalse(payload["store"])
        self.assertEqual(payload["max_output_tokens"], 16000)
        if schema is None:
            self.assertEqual(payload["text"]["format"], {"type": "text"})
        else:
            self.assertEqual(payload["text"]["format"], {
                "type": "json_schema", "name": schema.__name__, "strict": True,
                "schema": schema.model_json_schema(),
            })

    def test_uncertainty_and_cross_page_crops_require_review(self) -> None:
        result = di_result(
            ["First page", "Second page"], figures=[di_figure("cross-page", (1, 2))]
        )
        manifest, _, openai = self.run_digest(
            result,
            [
                response(page_result(
                    "First page\n<!-- Figure requires review. -->",
                )),
                response(page_result("Second page")),
            ],
            [png_bytes()],
        )
        self.assertEqual(manifest["status"], "needs_review")
        self.assertEqual(openai.responses.create.call_count, 2)
        self.assertEqual(manifest["figures"][0]["pages"], (1, 2))
        self.assertEqual(list((self.output / "figures").iterdir()), [])
        self.assertEqual(len(manifest["issues"]), 1)
        self.assertIn(
            "requires review", (self.output / "document.md").read_text(encoding="utf-8")
        )

    def test_subset_service_response_never_publishes_complete_digest(self) -> None:
        document, openai = clients(di_result(["Page one"]), [])
        with self.assertRaisesRegex(ingestion.DigestionError, "returned"):
            ingestion.digest_pdf(self.source, self.output, document, openai, "vision")
        self.assertTrue((self.output / "raw" / "document-intelligence.json").exists())
        self.assertFalse((self.output / "manifest.json").exists())
        self.assertFalse((self.output / "document.md").exists())
        openai.responses.create.assert_not_called()

    def test_existing_output_is_untouched(self) -> None:
        self.output.mkdir()
        sentinel = self.output / "existing.txt"
        sentinel.write_text("keep", encoding="utf-8")
        document, openai = clients(di_result(["Page one"]), [])
        with self.assertRaisesRegex(ingestion.DigestionError, "already exists"):
            ingestion.digest_pdf(self.source, self.output, document, openai, "vision")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
        document.begin_analyze_document.assert_not_called()

    def test_bad_input_is_rejected_before_upload(self) -> None:
        document, openai = clients(di_result(["Page one"]), [])
        for options in ({"pages": "0"}, {"dpi": 10}, {"max_output_tokens": 0}):
            with self.subTest(options=options), self.assertRaises(ingestion.DigestionError):
                ingestion.digest_pdf(self.source, self.output, document, openai, "vision", **options)
        document.begin_analyze_document.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_password_protected_pdf_is_rejected_before_upload(self) -> None:
        encrypted = self.root / "encrypted.pdf"
        with pymupdf.open(self.source) as pdf:
            pdf.save(
                encrypted, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                owner_pw="synthetic-owner", user_pw="synthetic-reader",
            )
        document, openai = clients(di_result(["One", "Two"]), [])
        with self.assertRaisesRegex(ingestion.DigestionError, "password-protected"):
            ingestion.digest_pdf(encrypted, self.output, document, openai, "vision")
        document.begin_analyze_document.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_image_with_pdf_extension_is_rejected_before_upload(self) -> None:
        self.source.write_bytes(png_bytes())
        document, openai = clients(di_result(["One"]), [])
        with self.assertRaisesRegex(ingestion.DigestionError, "not a PDF"):
            ingestion.digest_pdf(self.source, self.output, document, openai, "vision")
        document.begin_analyze_document.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_empty_pdf_is_rejected_before_upload(self) -> None:
        self.source.write_bytes(b"")
        document, openai = clients(di_result(["One"]), [])
        with self.assertRaises(pymupdf.FileDataError):
            ingestion.digest_pdf(self.source, self.output, document, openai, "vision")
        document.begin_analyze_document.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_refusal_truncation_or_whitespace_response_is_not_success(self) -> None:
        for index, output in enumerate([
            response(""), response("Partial Markdown", "incomplete"), response(" \t\r\n"),
        ]):
            target = self.root / f"failed-{index}"
            document, openai = clients(di_result(["One", "Two"]), [output])
            with self.subTest(index=index), self.assertRaises(ingestion.DigestionError):
                ingestion.digest_pdf(self.source, target, document, openai, "vision", dpi=72)
            raw_path = target / "raw" / "pages" / "page-0001.response.json"
            self.assertEqual(
                json.loads(raw_path.read_text(encoding="utf-8")), output.model_dump(mode="json"),
            )
            self.assertFalse((target / "manifest.json").exists())
            self.assertFalse((target / "document.md").exists())

    def test_malformed_figure_json_is_not_success(self) -> None:
        document, openai = clients(
            di_result(["One", "Two"], figures=[di_figure("diagram")]),
            [response("not JSON")], [png_bytes()],
        )
        with self.assertRaises(ValidationError):
            ingestion.digest_pdf(self.source, self.output, document, openai, "vision", dpi=72)
        raw = self.output / "raw" / "figures" / "figure-0001.response.json"
        self.assertEqual(json.loads(raw.read_text(encoding="utf-8"))["output_text"], "not JSON")
        self.assertFalse((self.output / "manifest.json").exists())
        self.assertFalse((self.output / "document.md").exists())

    def test_model_content_is_not_rejected_or_reconstructed_from_ocr(self) -> None:
        model_markdown = "Literal {{math:example}} and an unmatched $ in a quoted example."
        manifest, _, _ = self.run_digest(
            di_result([":formula:", "Other page"]),
            [response(page_result(model_markdown)), response(page_result("<!-- Blank page. -->"))],
        )
        self.assertEqual(manifest["status"], "extracted")
        self.assertEqual(
            (self.output / "document.md").read_bytes(),
            (
                f"<!-- page: 1 -->\n\n{model_markdown}"
                "\n\n<!-- page: 2 -->\n\n<!-- Blank page. -->"
            ).encode("utf-8"),
        )

    def test_document_is_only_published_after_the_whole_requested_pass(self) -> None:
        document, openai = clients(di_result(["First", "Second"]), [])
        responses = iter([page_result("First"), page_result("Second")])

        def return_page(**kwargs: object) -> Mock:
            self.assertFalse((self.output / "document.md").exists())
            self.assertFalse((self.output / "pages").exists())
            self.assertEqual(list(self.output.glob("page-*.md")), [])
            return response(next(responses))

        openai.responses.create.side_effect = return_page
        ingestion.digest_pdf(
            self.source, self.output, document, openai, "vision", dpi=72, page_review=False,
        )
        self.assertTrue((self.output / "document.md").is_file())
        self.assertFalse((self.output / "pages").exists())

    def test_format_check_runs_on_the_assembled_document_and_rejects_parse_errors(self) -> None:
        document, openai = clients(
            di_result(["First", "Second"]),
            [response(page_result("# First")), response(page_result("# Second"))],
        )
        with (
            patch.object(
                ingestion.MarkdownIt, "parse",
                side_effect=[[], [], [], [], ValueError("Synthetic invalid syntax")],
            ) as parse,
            self.assertRaisesRegex(ingestion.DigestionError, "Markdown format parser failed"),
        ):
            ingestion.digest_pdf(
                self.source, self.output, document, openai, "vision", dpi=72, page_review=False,
            )
        expected = "<!-- page: 1 -->\n\n# First\n\n<!-- page: 2 -->\n\n# Second"
        self.assertEqual(openai.responses.create.call_count, 2)
        self.assertEqual(
            [call.args[0] for call in parse.call_args_list],
            ["# First", "# First", "# Second", "# Second", expected],
        )
        self.assertEqual(
            (self.output / "raw" / "assembled.md").read_bytes(), expected.encode("utf-8")
        )
        self.assertFalse((self.output / "document.md").exists())
        self.assertFalse((self.output / "manifest.json").exists())
        self.assertFalse((self.output / "pages").exists())
        run = json.loads((self.output / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(run["stage"], "Checking assembled Markdown format")
        self.assertEqual(run["status"], "failed")

    def test_later_page_failure_keeps_evidence_without_publishing_or_splitting(self) -> None:
        document, openai = clients(di_result(["First", "Second"]), [])
        openai.responses.create.side_effect = [
            response(page_result("Authoritative first page")), HttpResponseError("Second page unavailable"),
        ]
        with self.assertRaises(HttpResponseError):
            ingestion.digest_pdf(
                self.source, self.output, document, openai, "vision", dpi=72, page_review=False,
            )
        self.assertTrue((self.output / "raw" / "pages" / "page-0001.response.json").exists())
        self.assertFalse((self.output / "document.md").exists())
        self.assertFalse((self.output / "manifest.json").exists())
        self.assertFalse((self.output / "pages").exists())

    def test_failed_crop_download_is_not_a_silent_no_figure_result(self) -> None:
        document, openai = clients(
            di_result(["One", "Two"], figures=[di_figure("figure")]), []
        )
        document.get_analyze_result_figure.side_effect = HttpResponseError("Crop unavailable")
        with self.assertRaises(HttpResponseError):
            ingestion.digest_pdf(self.source, self.output, document, openai, "vision")
        self.assertFalse((self.output / "manifest.json").exists())
        openai.responses.create.assert_not_called()

    def test_schema_rejects_non_png_crops(self) -> None:
        with Image.new("RGB", (10, 10)) as image, io.BytesIO() as buffer:
            image.save(buffer, format="JPEG")
            with self.assertRaisesRegex(ingestion.DigestionError, "Expected a PNG"):
                ingestion.image_url(buffer.getvalue())

    def test_rendered_vector_drawing_is_not_lost(self) -> None:
        with pymupdf.open(self.source) as pdf:
            png = ingestion.render_page_image(pdf, 1, 72)
        with Image.open(io.BytesIO(png)) as image, image.convert("RGB") as rgb:
            colors = rgb.getcolors(maxcolors=rgb.width * rgb.height)
            self.assertIsNotNone(colors)
            blue_pixels = sum(
                count for count, (red, green, blue) in colors
                if blue > 200 and red < 40 and green < 40
            )
            self.assertGreater(blue_pixels, 500)

    def test_rendering_preserves_rotated_cropbox_and_requested_dpi(self) -> None:
        with pymupdf.open(self.source) as pdf:
            pdf[1].set_cropbox(pymupdf.Rect(72, 80, 500, 700))
            png = ingestion.render_page_image(pdf, 2, 144)
        with Image.open(io.BytesIO(png)) as image:
            self.assertEqual(image.size, (1240, 856))
            self.assertEqual(image.mode, "RGB")
            self.assertAlmostEqual(image.info["dpi"][0], 144, delta=0.1)

    def test_oversized_page_is_rejected_before_allocating_a_pixmap(self) -> None:
        pdf = Mock(spec=pymupdf.Document)
        page = pdf.load_page.return_value
        page.rect = pymupdf.Rect(0, 0, 10000, 10000)
        with self.assertRaisesRegex(ingestion.DigestionError, "40 megapixels"):
            ingestion.render_page_image(pdf, 1, 72)
        page.get_pixmap.assert_not_called()


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.pdf"
        self.output = self.root / "digest"
        make_pdf(self.source)

    def configured_main(
        self, document: Mock, openai: Mock, *extra_args: str
    ) -> tuple[int, str]:
        settings = ingestion.Settings(
            "https://di.example.com", "https://ai.example.com/openai/v1/", "vision"
        )
        with (
            patch.object(ingestion, "settings_from_env", return_value=settings),
            patch.object(ingestion, "DefaultAzureCredential"),
            patch.object(ingestion, "DocumentIntelligenceClient") as document_factory,
            patch.object(ingestion, "get_bearer_token_provider"),
            patch.object(ingestion, "OpenAI") as openai_factory,
            self.assertLogs("ingestion", "INFO") as logs,
        ):
            document_factory.return_value.__enter__.return_value = document
            openai_factory.return_value.__enter__.return_value = openai
            code = ingestion.main([
                str(self.source), "--output", str(self.output), "--dpi", "72", *extra_args,
            ])
        return code, "\n".join(logs.output)

    def test_missing_configuration_is_a_clear_nonzero_failure(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            patch.object(ingestion, "check_math_runtime"),
            self.assertLogs("ingestion", "ERROR") as logs,
        ):
            code = ingestion.main([str(self.source), "--output", str(self.output)])
        self.assertEqual(code, 1)
        self.assertIn("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", " ".join(logs.output))
        self.assertIn("Loading Azure configuration", " ".join(logs.output))
        self.assertFalse(self.output.exists())

    def test_existing_output_is_diagnosed_before_credentials_are_loaded(self) -> None:
        self.output.mkdir()
        with (
            patch.object(ingestion, "settings_from_env") as load_settings,
            patch.object(ingestion, "DefaultAzureCredential") as credential,
            self.assertLogs("ingestion", "ERROR") as logs,
        ):
            code = ingestion.main([str(self.source), "--output", str(self.output)])
        self.assertEqual(code, 1)
        load_settings.assert_not_called()
        credential.assert_not_called()
        self.assertIn("Preflight", " ".join(logs.output))
        self.assertIn("Existing files were left unchanged", " ".join(logs.output))
        self.assertNotIn("No completed digest was published", " ".join(logs.output))
        self.assertEqual(list(self.output.iterdir()), [])

    def test_service_failure_reports_status_request_id_and_keeps_traceback(self) -> None:
        document, openai = clients(di_result(["One", "Two"]), [])
        service_response = LocalResponse(
            HttpRequest("POST", "https://di.example.com/analyze"), 403,
            b'{"error":{"code":"AuthorizationFailed","message":"Synthetic access denied"}}',
            {
                "content-type": "application/json", "x-ms-request-id": "request-123",
                "Authorization": "Bearer synthetic-header-secret",
            },
        )
        document.begin_analyze_document.side_effect = HttpResponseError(
            message="Synthetic access denied", response=service_response
        )
        code, logs = self.configured_main(document, openai)
        self.assertEqual(code, 1)
        self.assertIn("Document Intelligence: submitting 2 PDF pages", logs)
        self.assertIn("http_status: 403", logs)
        self.assertIn("request-123", logs)
        self.assertIn("az login", logs)
        self.assertNotIn("Traceback (most recent call last)", logs)
        report_text = (self.output / "run.json").read_text(encoding="utf-8")
        report = json.loads(report_text)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["error"]["http_status"], 403)
        self.assertIn("Traceback (most recent call last)", report["error"]["traceback"])
        self.assertNotIn("synthetic-header-secret", logs + report_text)
        self.assertFalse((self.output / "manifest.json").exists())

    def test_empty_model_output_identifies_page_and_raw_response(self) -> None:
        document, openai = clients(di_result(["One", "Two"]), [response("")])
        code, logs = self.configured_main(document, openai)
        self.assertEqual(code, 1)
        self.assertIn("OpenAI: reconciling page 1", logs)
        self.assertIn("OpenAI returned no extraction", logs)
        self.assertIn("page-0001.response.json", logs)
        report = json.loads((self.output / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(report["error"]["type"], "DigestionError")
        self.assertTrue(Path(report["artifact"]).is_file())

    def test_debug_prints_the_traceback_without_enabling_sdk_debug_logs(self) -> None:
        document, openai = clients(
            di_result(["One", "Two"], figures=[di_figure("diagram")]),
            [response("not JSON")], [png_bytes()],
        )
        code, logs = self.configured_main(document, openai, "--debug")
        self.assertEqual(code, 1)
        self.assertIn("Traceback (most recent call last)", logs)
        self.assertIn("model_validate_json", logs)
        self.assertIn("figure-0001.response.json", logs)
        self.assertNotIn("Authorization:", logs)

    def test_interrupt_preserves_last_stage_and_returns_130(self) -> None:
        document, openai = clients(di_result(["One", "Two"]), [])
        document.begin_analyze_document.side_effect = KeyboardInterrupt()
        code, logs = self.configured_main(document, openai)
        self.assertEqual(code, 130)
        report = json.loads((self.output / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "interrupted")
        self.assertEqual(report["stage"], "Document Intelligence: submitting 2 PDF pages")
        self.assertIn("may still finish server-side", logs)

    def test_retry_reveals_saved_failure_without_making_another_cloud_request(self) -> None:
        document, openai = clients(di_result(["One", "Two"]), [response("")])
        code, _ = self.configured_main(document, openai)
        self.assertEqual(code, 1)
        previous = (self.output / "run.json").read_bytes()
        with (
            patch.object(ingestion, "settings_from_env") as load_settings,
            self.assertLogs("ingestion", "ERROR") as logs,
        ):
            code = ingestion.main([str(self.source), "--output", str(self.output)])
        self.assertEqual(code, 1)
        self.assertIn("Previous run stage: 'OpenAI: reconciling page 1'", "\n".join(logs.output))
        load_settings.assert_not_called()
        self.assertEqual((self.output / "run.json").read_bytes(), previous)

    def test_manifest_review_status_has_distinct_exit_code(self) -> None:
        settings = ingestion.Settings(
            "https://di.example.com", "https://ai.example.com/openai/v1/", "vision"
        )
        with (
            patch.object(ingestion, "settings_from_env", return_value=settings),
            patch.object(ingestion, "DefaultAzureCredential"),
            patch.object(ingestion, "DocumentIntelligenceClient"),
            patch.object(ingestion, "get_bearer_token_provider"),
            patch.object(ingestion, "OpenAI"),
            patch.object(ingestion, "digest_pdf", return_value={"status": "needs_review"}),
            self.assertLogs("ingestion", "WARNING"),
        ):
            self.assertEqual(ingestion.main(["source.pdf", "--output", "unused"]), 2)

    def test_successful_cli_run_displays_usage_and_reference_cost(self) -> None:
        usage = {
            "input_tokens": 1000,
            "input_tokens_details": {"cached_tokens": 100},
            "output_tokens": 100,
            "output_tokens_details": {"reasoning_tokens": 20},
        }
        document, openai = clients(
            di_result(["One", "Two"]),
            [response("One", usage=usage), response("Two", usage=usage)],
        )
        code, logs = self.configured_main(document, openai, "--no-page-review")
        self.assertEqual(code, 0)
        self.assertIn("OpenAI usage: 2 response(s)", logs)
        self.assertIn("OpenAI reference estimate:", logs)
        self.assertIn("Document Intelligence usage: 2 page(s)", logs)
        self.assertIn("not an Azure bill", logs)
        saved = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(saved["costs"]["openai"]["estimated_cost_usd"], 0.00562)

    def test_real_digest_latex_review_returns_exit_2_and_preserves_artifacts(self) -> None:
        page = page_result("# 1 \\quad Title\n\n$x\\quad y$")
        document, openai = clients(
            di_result(["One", "Two"]),
            [response(page), response(page_result("Second page"))],
        )
        code, logs = self.configured_main(document, openai, "--no-page-review")
        self.assertEqual(code, 2)
        self.assertIn("Page 1, line 1: possible LaTeX leakage", logs)
        self.assertEqual(openai.responses.create.call_count, 2)
        saved = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "needs_review")
        self.assertEqual(len(saved["issues"]), 1)
        self.assertEqual(
            (self.output / "document.md").read_bytes(),
            f"<!-- page: 1 -->\n\n{page}\n\n<!-- page: 2 -->\n\nSecond page".encode("utf-8"),
        )
        self.assertTrue((self.output / "raw" / "pages" / "page-0001.response.json").is_file())
        self.assertEqual(
            (self.output / "source" / self.source.name).read_bytes(), self.source.read_bytes(),
        )

    def test_cli_enables_page_review_by_default_and_can_disable_it(self) -> None:
        for args, expected in (((), True), (("--no-page-review",), False)):
            with (
                self.subTest(args=args),
                patch.object(ingestion, "digest_pdf", return_value={"status": "extracted"}) as digest,
            ):
                code, _ = self.configured_main(Mock(), Mock(), *args)
            self.assertEqual(code, 0)
            self.assertEqual(digest.call_args.kwargs["page_review"], expected)

    def test_unresolved_judge_findings_return_exit_2_without_deleting_or_rerunning_di(self) -> None:
        report = ingestion.PageReview(findings=[ingestion.PageFinding(
            category="uncertain", location="bottom formula",
            description="The denominator is not readable.",
            source_evidence="The source image is blurred at the denominator.",
            instruction="Keep an unreadable marker, do not guess.",
        )])
        document, openai = clients(
            di_result(["One", "Two"]),
            [response("One"), response(report), response("Two"), response(ingestion.PageReview(findings=[]))],
        )
        code, logs = self.configured_main(document, openai)
        self.assertEqual(code, 2)
        self.assertIn("Page 1, bottom formula: LLM uncertain", logs)
        self.assertEqual(openai.responses.create.call_count, 4)
        document.begin_analyze_document.assert_called_once()
        self.assertTrue((self.output / "document.md").is_file())
        self.assertTrue((self.output / "raw" / "pages" / "page-0001.attempt-01.review.response.json").is_file())

    def test_pdf_backend_error_is_reported_as_failure(self) -> None:
        settings = ingestion.Settings(
            "https://di.example.com", "https://ai.example.com/openai/v1/", "vision"
        )
        with (
            patch.object(ingestion, "settings_from_env", return_value=settings),
            patch.object(ingestion, "DefaultAzureCredential"),
            patch.object(ingestion, "DocumentIntelligenceClient"),
            patch.object(ingestion, "get_bearer_token_provider"),
            patch.object(ingestion, "OpenAI"),
            patch.object(ingestion, "digest_pdf", side_effect=pymupdf.FileDataError("Broken PDF")),
            self.assertLogs("ingestion", "ERROR") as logs,
        ):
            self.assertEqual(ingestion.main(["source.pdf", "--output", "unused"]), 1)
        self.assertIn("Broken PDF", " ".join(logs.output))


if __name__ == "__main__":
    unittest.main()
