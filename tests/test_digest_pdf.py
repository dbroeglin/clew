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
from PIL import Image
from pydantic import ValidationError
from requests.structures import CaseInsensitiveDict

from scripts import digest_pdf as ingestion


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


def response(value: ingestion.StrictModel | str, status: str = "completed") -> Mock:
    text = value.model_dump_json() if isinstance(value, ingestion.StrictModel) else value
    result = Mock(status=status, output_text=text)
    result.model_dump.return_value = {"status": status, "output_text": text}
    return result


def page_result(markdown: str = "# Source page", **kwargs: object) -> ingestion.PageExtraction:
    return ingestion.PageExtraction.model_validate({
        "markdown": markdown, "fixes": [], **kwargs,
    })


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
    def test_semantically_invalid_decisions_are_not_accepted(self) -> None:
        for value in (
            decision("keep", "icon"), decision("keep", "logo"),
            decision("keep", "diagram", ""), decision("discard", "unclear"),
        ):
            with self.assertRaises(ingestion.DigestionError):
                ingestion.validate_figure_decision(value)
        ingestion.validate_figure_decision(decision("discard", "icon", ""))

    def test_structured_schema_is_strict(self) -> None:
        schema = ingestion.PageExtraction.model_json_schema()
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), {"markdown", "fixes"})
        fix = schema["$defs"]["ReportedFix"]
        self.assertFalse(fix["additionalProperties"])
        self.assertEqual(set(fix["required"]), {"description", "confidence"})
        self.assertNotIn("minimum", fix["properties"]["confidence"])
        self.assertNotIn("maximum", fix["properties"]["confidence"])
        with self.assertRaises(ValidationError):
            page_result("text", extra_field="not allowed")

    def test_markdown_and_fix_confidence_are_not_semantically_checked(self) -> None:
        markdown = "An unmatched $ and literal {{math:example}} are model-authored content."
        page = page_result(
            markdown, fixes=[{"description": "A self-reported correction.", "confidence": 1.2}]
        )
        self.assertEqual(page.markdown, markdown)
        self.assertEqual(page.fixes[0].confidence, 1.2)

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


class RunDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "existing"
        self.output.mkdir()

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
        manifest = ingestion.digest_pdf(
            self.source, self.output, document, openai, "vision-deployment", dpi=72, **options
        )
        return manifest, document, openai

    def test_full_digest_curates_native_crops_preserves_math_and_provenance(self) -> None:
        result = di_result(
            ["# G\u00e9om\u00e9trie \U0001f4da\n:formula:\n", "# Application\n"],
            figures=[di_figure("opaque/figure-A"), di_figure("opaque/logo")],
        )
        corrected = page_result(
            "# G\u00e9om\u00e9trie\n\n$$\nx^2+y^2=1\n$$\n\n"
            "![Axes](figures/figure-0001.png)\nSource caption",
            fixes=[{"description": "Reconstructed the displayed equation.", "confidence": 0.96}],
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
                f"<!-- page: 1 -->\n\n{corrected.markdown}"
                "\n\n<!-- page: 2 -->\n\n# Application"
            ).encode("utf-8"),
        )
        self.assertFalse((self.output / "pages").exists())
        self.assertFalse((self.output / "raw" / "pages" / "page-0001.di.md").exists())
        saved = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["figures"][1]["decision"], "discard")
        self.assertEqual(saved["figures"][0]["caption"], "Source caption")
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
        for call in openai.responses.create.call_args_list:
            self.assertFalse(call.kwargs["store"])
            self.assertTrue(call.kwargs["text"]["format"]["strict"])
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

    def test_fixes_are_displayed_but_do_not_gate_the_authoritative_markdown(self) -> None:
        result = di_result([":formula:"])
        result.pages[0].formulas[0].value = "s i"
        result.pages[0].formulas[0].kind = "inline"
        page = page_result(
            "  si la condition est vraie\n\n$x$ and $x$.\n",
            fixes=[{"description": "The conjunction is prose.", "confidence": 0.01}],
        )
        with self.assertLogs("ingestion", "INFO") as logs:
            manifest, _, _ = self.run_digest(result, [response(page)], pages="1")
        self.assertEqual(manifest["status"], "extracted")
        self.assertEqual(manifest["issues"], [])
        self.assertIn("model confidence 0.01", "\n".join(logs.output))
        self.assertIn("The conjunction is prose.", "\n".join(logs.output))
        self.assertNotIn("fixes", manifest["pages"][0])
        self.assertNotIn("formulas", manifest["pages"][0])
        self.assertNotIn("formula_corrections", manifest["pages"][0])
        self.assertEqual(
            (self.output / "document.md").read_bytes(),
            f"<!-- page: 1 -->\n\n{page.markdown}".encode("utf-8"),
        )

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
                self.source, self.output, document, openai, "vision-deployment", dpi=72
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

    def test_real_openai_sdk_sends_explicit_multimodal_message_types(self) -> None:
        with (
            DefaultHttpxClient() as transport,
            patch.object(transport, "send", side_effect=OSError("Offline wire capture")) as send,
            ingestion.OpenAI(
                base_url="https://example.invalid/openai/v1/",
                api_key="synthetic-test-key", http_client=transport, max_retries=0,
            ) as client,
            self.assertRaises(ingestion.APIConnectionError),
        ):
            ingestion.analyze_image(
                client, "vision", ingestion.PAGE_PROMPT, {"page_number": "0001"},
                png_bytes(), ingestion.PageExtraction, self.root / "response.json", 16000,
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

    def test_uncertainty_and_cross_page_crops_require_review(self) -> None:
        result = di_result(
            ["First page", "Second page"], figures=[di_figure("cross-page", (1, 2))]
        )
        manifest, _, openai = self.run_digest(
            result,
            [
                response(page_result(
                    "First page\n<!-- Figure requires review. -->",
                    fixes=[{"description": "A denominator is illegible.", "confidence": 0.1}],
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

    def test_refusal_truncation_or_malformed_json_is_not_success(self) -> None:
        for index, output in enumerate([
            response(""), response("{}", "incomplete"), response("not JSON"),
        ]):
            target = self.root / f"failed-{index}"
            document, openai = clients(di_result(["One", "Two"]), [output])
            with self.subTest(index=index), self.assertRaises((ingestion.DigestionError, ValidationError)):
                ingestion.digest_pdf(self.source, target, document, openai, "vision", dpi=72)
            self.assertTrue((target / "raw" / "pages" / "page-0001.response.json").exists())
            self.assertFalse((target / "manifest.json").exists())
            self.assertFalse((target / "document.md").exists())

    def test_model_content_is_not_rejected_or_reconstructed_from_ocr(self) -> None:
        model_markdown = "Literal {{math:example}} and an unmatched $ in a quoted example."
        manifest, _, _ = self.run_digest(
            di_result([":formula:", "Other page"]),
            [response(page_result(model_markdown)), response(page_result(""))],
        )
        self.assertEqual(manifest["status"], "extracted")
        self.assertEqual(
            (self.output / "document.md").read_bytes(),
            f"<!-- page: 1 -->\n\n{model_markdown}\n\n<!-- page: 2 -->\n\n".encode("utf-8"),
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
        ingestion.digest_pdf(self.source, self.output, document, openai, "vision", dpi=72)
        self.assertTrue((self.output / "document.md").is_file())
        self.assertFalse((self.output / "pages").exists())

    def test_format_check_runs_on_the_assembled_document_and_rejects_parse_errors(self) -> None:
        document, openai = clients(
            di_result(["First", "Second"]),
            [response(page_result("# First")), response(page_result("# Second"))],
        )
        with (
            patch.object(
                ingestion.MarkdownIt, "parse", side_effect=ValueError("Synthetic invalid syntax")
            ) as parse,
            self.assertRaisesRegex(ingestion.DigestionError, "Markdown format parser failed"),
        ):
            ingestion.digest_pdf(self.source, self.output, document, openai, "vision", dpi=72)
        expected = "<!-- page: 1 -->\n\n# First\n\n<!-- page: 2 -->\n\n# Second"
        self.assertEqual(openai.responses.create.call_count, 2)
        parse.assert_called_once_with(expected)
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
            ingestion.digest_pdf(self.source, self.output, document, openai, "vision", dpi=72)
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
        with patch.dict("os.environ", {}, clear=True), self.assertLogs("ingestion", "ERROR") as logs:
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

    def test_invalid_model_output_identifies_page_and_raw_response(self) -> None:
        document, openai = clients(di_result(["One", "Two"]), [response("not JSON")])
        code, logs = self.configured_main(document, openai)
        self.assertEqual(code, 1)
        self.assertIn("OpenAI: reconciling page 1", logs)
        self.assertIn("ValidationError", logs)
        self.assertIn("page-0001.response.json", logs)
        report = json.loads((self.output / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(report["error"]["type"], "ValidationError")
        self.assertTrue(Path(report["artifact"]).is_file())

    def test_debug_prints_the_traceback_without_enabling_sdk_debug_logs(self) -> None:
        document, openai = clients(di_result(["One", "Two"]), [response("not JSON")])
        code, logs = self.configured_main(document, openai, "--debug")
        self.assertEqual(code, 1)
        self.assertIn("Traceback (most recent call last)", logs)
        self.assertIn("model_validate_json", logs)
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
        document, openai = clients(di_result(["One", "Two"]), [response("not JSON")])
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
