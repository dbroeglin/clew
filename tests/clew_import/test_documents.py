"""Synthetic whole-document preparation, preservation, and negative checks."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

SCRIPTS = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "clew-import" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from bundle_sources import load_bundle
from document_edits import compile_document, verify_projection
from document_formats import Plan
from document_io import digest
from markdown_source import MarkdownSource
from prepare_documents import check, materialize, plan_hash
from validate_documents import validate


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        (self.vault / "Maths").mkdir(parents=True)

    def bundle(self, name, text, *, count=2, issues=None, status="extracted", pdf_name=None):
        root = self.root / "inputs" / name
        (root / "source").mkdir(parents=True)
        (root / "raw" / "pages").mkdir(parents=True)
        (root / "figures").mkdir()
        pdf_name = pdf_name or name + ".pdf"
        with pymupdf.open() as pdf:
            for _ in range(count):
                pdf.new_page()
            pdf.save(root / "source" / pdf_name)
        (root / "document.md").write_bytes(text.encode("utf-8"))
        (root / "figures" / "a.png").write_bytes(b"synthetic retained asset")
        numbers = list(MarkdownSource(text).markers.values())
        pages = []
        for number in numbers:
            image, response = f"raw/pages/{number}.png", f"raw/pages/{number}.json"
            (root / image).write_bytes(b"synthetic page")
            (root / response).write_text("{}", encoding="utf-8")
            pages.append({"number": number, "raw_image": image, "raw_response": response})
        manifest = {
            "schema_version": 3, "status": status, "document": "document.md",
            "source": {"name": pdf_name, "path": "source/" + pdf_name,
                       "sha256": digest((root / "source" / pdf_name).read_bytes()), "page_count": count},
            "pages": pages, "figures": [{"asset": "figures/a.png"}], "issues": issues or [],
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return root

    def document(self, identifier, text, role="course", **kwargs):
        root = self.bundle(identifier, text, **kwargs)
        bundle = load_bundle(root)
        return {"id": identifier, "bundle": str(root), "fingerprint": bundle.fingerprint,
                "role": role, "operations": []}

    def block(self, document, text, *, kind=None):
        source = load_bundle(Path(document["bundle"])).markdown
        matches = [block.id for block in source.blocks.values()
                   if (kind is None or block.kind == kind)
                   and "".join(source.lines[block.start:block.end]).strip().startswith(text)]
        self.assertTrue(matches, (text, source.inventory()))
        return matches[-1] if kind == "item" else matches[0]

    def plan(self, documents):
        return Plan.model_validate({
            "schema_version": 1, "id": "sequences", "title": "Sequences",
            "destination": str(self.vault / "Maths" / "Sequences"),
            "placement": {"vault": str(self.vault), "parent": "Maths",
                          "rationale": "Use the fixture's mathematics container."},
            "documents": documents,
        })

    def course(self, *, newline="\n"):
        text = ("<!-- page: 1 -->\n\n# Course\n\n## Geometric limits\n\n"
                "### Theorem 1\n\nIf $|q|<1$, then $q^n$ tends to zero.\n\n"
                "$$\nq^n \\longrightarrow 0\n$$\n\n"
                "1. First case.\n2. Second case.\n\n![Diagram](figures/a.png)\n")
        text = text.replace("\n", newline)
        document = self.document("course", text)
        first, section, theorem = [self.block(document, heading, kind="heading")
                                   for heading in ("# Course", "## Geometric limits", "### Theorem 1")]
        last = self.block(document, "![Diagram]", kind="paragraph")
        document["operations"] = [
            {"op": "unit", "kind": "section", "id": "sec-course", "start": first, "end": last},
            {"op": "unit", "kind": "section", "id": "sec-geometric", "start": section, "end": last},
            {"op": "callout", "kind": "theorem", "id": "thm-geometric", "start": theorem, "end": last},
        ]
        return document

    def pipeline_plan(self):
        course = self.course()
        exercises = self.document("sheet", "<!-- page: 1 -->\n\n# Exercises\n\n## Exercise 1\n\n"
                                  "Let $u_n=7(2/5)^n$.\n\n1. Determine its limit.\n\n"
                                  "2. Find a bound.\n", role="exercise")
        answers = self.document("solutions", "<!-- page: 1 -->\n\n# Solutions\n\n## Correction 1\n\n"
                                "1. The limit is $0$.\n\n2. Use the inequality.\n", role="correction")
        for document, kind, root, heading, first, last in [
            (exercises, "exercise", "# Exercises", "## Exercise 1", "1. Determine", "2. Find"),
            (answers, "correction", "# Solutions", "## Correction 1", "1. The limit", "2. Use"),
        ]:
            a = self.block(document, root, kind="heading")
            b = self.block(document, heading, kind="heading")
            q1 = self.block(document, first, kind="item")
            q2 = self.block(document, last, kind="item")
            unit = {"op": "unit", "kind": kind, "id": "ex-1" if kind == "exercise" else "corr-1",
                    "start": b, "end": q2}
            if kind == "correction":
                unit["exercise"] = {"target": {"document": "sheet", "anchor": "ex-1"},
                                    "evidence": [{"document": "solutions", "start": q1, "end": q2}]}
            operations = [{"op": "unit", "kind": "section", "id": "sec-root", "start": a, "end": q2},
                          unit]
            for number, block in enumerate((q1, q2), 1):
                operation = {"op": "callout", "kind": "question" if kind == "exercise" else "answer",
                             "id": f"q-{number}" if kind == "exercise" else f"r-{number}",
                             "owner": unit["id"], "start": block, "end": block}
                if kind == "correction":
                    operation["question"] = {
                        "target": {"document": "sheet", "anchor": f"q-{number}"},
                        "evidence": [{"document": "solutions", "start": block, "end": block}]}
                operations.append(operation)
            document["operations"] = operations
        return self.plan([course, exercises, answers])

    def codes(self, report):
        return {finding["code"] for finding in report["findings"]}

    def test_whole_documents_and_relative_relationships(self):
        plan = self.pipeline_plan()
        checked = check(plan)
        self.assertEqual(checked["errors"], 0, checked)
        self.assertEqual(checked["status"], "validated", checked)
        self.assertFalse(Path(plan.destination).exists())
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["status"], "validated", report)
        root = Path(plan.destination)
        self.assertEqual(sorted(path.relative_to(root).as_posix() for path in root.rglob("*.md")
                                if ".clew" not in path.parts),
                         sorted(["Course-course/course.md", "Correction-solutions/solutions.md",
                                 "Exercise-sheet/sheet.md", "index.md"]))
        answer = (root / "Correction-solutions" / "solutions.md").read_text(encoding="utf-8")
        self.assertIn("../Exercise-sheet/sheet.md#^q-1", answer)
        self.assertIn("> [Question](../Exercise-sheet/sheet.md#^q-1)", answer)
        self.assertEqual(validate(root)["status"], "validated")

    def test_crlf_fidelity_preserves_math_lists_and_figures(self):
        plan = self.plan([self.course(newline="\r\n")])
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["errors"], 0, report)
        root = Path(plan.destination)
        text = (root / "Course-course" / "course.md").read_bytes().decode("utf-8")
        self.assertIn("> q^n \\longrightarrow 0\r\n", text)
        self.assertIn("> 1. First case.\r\n", text)
        baseline = (root / ".clew" / "baselines" / "course" / "document.md").read_bytes()
        self.assertEqual(baseline, (Path(plan.documents[0].bundle) / "document.md").read_bytes())
        self.assertEqual(validate(root, fidelity=True)["errors"], 0)

    def test_manual_edit_is_accepted_only_by_current_mode(self):
        plan = self.plan([self.course()])
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        path = root / "Course-course" / "course.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("First case.", "First case, with a handwritten clarification."), encoding="utf-8")
        self.assertEqual(validate(root)["errors"], 0)
        self.assertIn("source-fidelity", self.codes(validate(root, fidelity=True)))

    def test_section_heading_links_replace_generated_section_block_ids(self):
        plan = self.plan([self.course()])
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        path = root / "Course-course" / "course.md"
        text = path.read_text()
        self.assertNotIn("^sec-", text)
        with (root / "index.md").open("a", encoding="utf-8") as stream:
            stream.write("\n[Section](Course-course/course.md#Geometric%20limits)\n")
        self.assertEqual(validate(root)["errors"], 0)
        path.write_text(text.replace("## Geometric limits", "## Renamed section"))
        self.assertIn("missing-heading", self.codes(validate(root)))

    def test_section_scope_requires_an_existing_heading(self):
        document = self.document("no-heading", "<!-- page: 1 -->\n\nParagraph only.\n")
        block = self.block(document, "Paragraph only.", kind="paragraph")
        document["operations"] = [
            {"op": "unit", "kind": "section", "id": "sec", "start": block, "end": block},
        ]
        with self.assertRaisesRegex(ValueError, "existing source heading"):
            check(self.plan([document]))

    def test_question_without_enclosing_exercise_is_rejected(self):
        plan = self.pipeline_plan()
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        path = root / "Exercise-sheet" / "sheet.md"
        text = path.read_text().replace("%% /clew:unit ex-1 %%", "")
        text = text.replace("> [!question] Question 1", "%% /clew:unit ex-1 %%\n\n> [!question] Question 1")
        path.write_text(text)
        self.assertIn("unit-owner", self.codes(validate(root)))

    def test_local_links_are_aggregated_and_code_math_lookalikes_are_ignored(self):
        plan = self.plan([self.course()])
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        path = root / "Course-course" / "course.md"
        with path.open("a", encoding="utf-8") as stream:
            stream.write("\n[Bad](missing.md) [Wrong](course.md#^absent)\n"
                         "\n`[Code](missing-code.md)` and $[Math](missing-math.md)$\n")
        report = validate(root)
        self.assertEqual(report["status"], "invalid")
        self.assertEqual(report["errors"], 2, report)
        self.assertEqual(self.codes(report), {"missing-link", "missing-anchor"})

    def test_unmatched_answers_and_structure_are_visible(self):
        plan = self.pipeline_plan()
        data = plan.model_dump()
        correction = data["documents"][-1]
        correction["operations"][1].pop("exercise")
        for operation in correction["operations"][2:]:
            operation.pop("question")
        plan = Plan.model_validate(data)
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["status"], "needs_review", report)
        root = Path(plan.destination)
        text = (root / "Correction-solutions" / "solutions.md").read_text(encoding="utf-8")
        self.assertIn("> [!warning] Clew review", text)
        self.assertIn("no verified question match", text)
        self.assertIn("unmatched-answer", (root / "index.md").read_text(encoding="utf-8"))
        self.assertEqual(validate(root, fidelity=True)["errors"], 0)

    def test_reviews_follow_all_source_units_and_preserve_delimiter_messages(self):
        document = self.course(newline="\r\n")
        data = self.plan([document]).model_dump()
        data["documents"][0]["reviews"] = [
            {"code": "manual-review", "message": "Check literal %% and <!-- -->.",
             "block": self.block(document, "### Theorem", kind="heading")},
        ]
        plan = Plan.model_validate(data)
        report = materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        text = (root / "Course-course" / "course.md").read_bytes().decode("utf-8")
        self.assertEqual(report["errors"], 0, report)
        self.assertGreater(text.index("**Review required**"), text.rindex("%% /clew:unit"))
        self.assertNotIn("clew:review", text[:text.index("**Review required**")])
        self.assertIn(r"Check literal \%\% and", text)
        self.assertIn(r"\u0025\u0025", text)
        self.assertEqual(validate(root, fidelity=True)["errors"], 0)

    def test_compact_pdf_links_at_entries_and_callout_footers_only(self):
        document = self.course()
        source = Path(document["bundle"]) / "document.md"
        text = source.read_text().replace("$$\nq^n", "<!-- page: 2 -->\n\n$$\nq^n")
        source.write_text(text)
        manifest = Path(document["bundle"]) / "manifest.json"
        metadata = json.loads(manifest.read_text())
        metadata["pages"].append({**metadata["pages"][0], "number": 2})
        manifest.write_text(json.dumps(metadata))
        document["fingerprint"] = load_bundle(Path(document["bundle"])).fingerprint
        for operation in document["operations"]:
            operation["end"] = self.block(document, "![Diagram]", kind="paragraph")
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        output = (root / "Course-course" / "course.md").read_text()
        self.assertEqual(report["errors"], 0, report)
        self.assertEqual(output.count("(course.pdf#page="), 3)
        self.assertIn("[PDF p. 1](course.pdf#page=1)", output)
        self.assertNotIn("^sec-geometric", output)
        self.assertIn("> ![Diagram](figures/a.png)\n>\n> [PDF p. 1](course.pdf#page=1)", output)
        self.assertNotIn("Source:", output)
        self.assertNotIn("PDF, page", output)
        self.assertNotIn("<!-- page:", output)
        self.assertEqual(validate(root, fidelity=True)["errors"], 0)

    def test_malformed_native_structural_comments_are_rejected(self):
        plan = self.plan([self.course()])
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        path = root / "Course-course" / "course.md"
        text = path.read_text().replace("%% /clew:unit sec-course %%", "%% /clew:unit sec-course")
        path.write_text(text)
        self.assertIn("structural-marker", self.codes(validate(root)))

    def test_relationship_links_follow_source(self):
        plan = self.pipeline_plan()
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        path = root / "Correction-solutions" / "solutions.md"
        text = path.read_text()
        self.assertIn("> [Question](../Exercise-sheet/sheet.md#^q-1)\n"
                      "> [PDF p. 1](solutions.pdf#page=1)", text)
        self.assertLess(text.index("> 1. The limit"), text.index("> [Question]"))
        self.assertGreater(text.index("[Exercise]"), text.index("^r-2"))
        self.assertNotIn("::", text)
        self.assertNotIn("[Correction]", text)
        sheet = (root / "Exercise-sheet" / "sheet.md").read_text()
        self.assertNotIn("[Exercise]", sheet)
        self.assertEqual(validate(root, fidelity=True)["errors"], 0)

    def test_plain_relationship_footer_cannot_hide_missing_or_multiple_targets(self):
        plan = self.pipeline_plan()
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        path = root / "Correction-solutions" / "solutions.md"
        path.write_text(path.read_text().replace(
            "[Question](../Exercise-sheet/sheet.md#^q-1)",
            "[Question](../Exercise-sheet/sheet.md#^q-1) [Other](solutions.md#^corr-1)"))
        self.assertIn("malformed-field", self.codes(validate(root)))

    def test_existing_callout_footer_precedes_reused_native_anchor(self):
        document = self.document("existing", "<!-- page: 1 -->\n\n"
                                 "> [!definition] Existing definition\n> Source-authored statement.\n\n"
                                 "^def-existing\n\n<!-- Source-authored comment. -->\n")
        document["operations"] = [
            {"op": "callout", "kind": "definition", "id": "def-existing",
             "start": self.block(document, "> [!definition]", kind="quote"),
             "end": self.block(document, "^def-existing", kind="paragraph")},
        ]
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        output = (root / "Course-existing" / "existing.md").read_text()
        self.assertEqual(report["errors"], 0, report)
        self.assertIn("> Source-authored statement.\n>\n> [PDF p. 1](existing.pdf#page=1)\n\n"
                      "^def-existing", output)
        self.assertEqual(output.count("^def-existing"), 1)
        self.assertIn("<!-- Source-authored comment. -->", output)
        self.assertEqual(validate(root, fidelity=True)["errors"], 0)

    def test_callout_footer_adds_safe_separator_after_source_without_final_newline(self):
        document = self.document("no-newline", "<!-- page: 1 -->\n\n## Definition\n\nExact body.")
        document["operations"] = [
            {"op": "callout", "kind": "definition", "id": "def",
             "start": self.block(document, "## Definition", kind="heading"),
             "end": self.block(document, "Exact body.", kind="paragraph")},
        ]
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["errors"], 0, report)
        self.assertEqual(validate(Path(plan.destination), fidelity=True)["errors"], 0)

    def test_native_marker_lookalikes_in_code_and_math_are_not_structure(self):
        document = self.document("native-code", "<!-- page: 1 -->\n\n"
                                 "```\n%% clew:unit exercise fake %%\n"
                                 "%% /clew:unit fake %%\n[Hidden](absent.md)\n```\n\n"
                                 "$$\n%% clew:unit exercise math %%\n$$\n")
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["errors"], 0, report)
        self.assertEqual(validate(Path(plan.destination), fidelity=True)["errors"], 0)

    def test_stale_sources_and_approval_are_blocked(self):
        plan = self.plan([self.course()])
        with self.assertRaisesRegex(ValueError, "changed since approval"):
            materialize(plan, "0" * 64)
        source = Path(plan.documents[0].bundle) / "document.md"
        source.write_bytes(source.read_bytes() + b"\nNew source content.\n")
        with self.assertRaisesRegex(ValueError, "source changed"):
            check(plan)
        self.assertFalse(Path(plan.destination).exists())

    def test_unsafe_math_boundary_and_unknown_operations_are_rejected(self):
        document = self.course()
        data = self.plan([document]).model_dump()
        data["documents"][0]["operations"][0]["end"] = "b-9999"
        with self.assertRaisesRegex(ValueError, "selector"):
            check(Plan.model_validate(data))
        data = self.plan([document]).model_dump()
        data["documents"][0]["operations"].append({"op": "replace", "text": "regenerated"})
        with self.assertRaises(ValueError):
            Plan.model_validate(data)

    def test_relocated_chapter_does_not_need_external_inputs(self):
        plan = self.pipeline_plan()
        materialize(plan, plan_hash(plan))
        moved = self.root / "another-vault" / "Sequences"
        moved.parent.mkdir()
        shutil.move(plan.destination, moved)
        for document in plan.documents:
            shutil.rmtree(document.bundle)
        self.assertEqual(validate(moved)["errors"], 0)
        self.assertEqual(validate(moved, fidelity=True)["errors"], 0)

    def test_invalid_pdf_pages_and_duplicate_anchors_are_errors(self):
        plan = self.plan([self.course()])
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        path = root / "Course-course" / "course.md"
        with path.open("a", encoding="utf-8") as stream:
            stream.write("\nDuplicate. ^thm-geometric\n\n[Wrong page](course.pdf#page=3)\n")
        report = validate(root)
        self.assertTrue({"duplicate-anchor", "pdf-page"} <= self.codes(report), report)

    def test_incomplete_write_is_preserved(self):
        plan = self.plan([self.course()])
        with patch("prepare_documents.shutil.copyfileobj", side_effect=OSError("Synthetic copy failure")):
            with self.assertRaisesRegex(ValueError, "preserve partial output"):
                materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        self.assertEqual(json.loads((root / ".clew" / "preparation.json").read_text())["status"], "writing")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            validate(root)
        with self.assertRaisesRegex(ValueError, "already exists"):
            materialize(plan, plan_hash(plan))

    def test_unknown_and_mixed_roles_keep_the_pdf_basename(self):
        for role in ("unknown", "mixed"):
            with self.subTest(role=role):
                document = self.document(role, "<!-- page: 1 -->\n\nPlain supplied text.\n", role=role)
                plan = self.plan([document])
                data = plan.model_dump()
                data["destination"] += "-" + role
                plan = Plan.model_validate(data)
                report = materialize(plan, plan_hash(plan))
                root = Path(plan.destination)
                self.assertEqual(report["status"], "needs_review", report)
                self.assertTrue((root / role / (role + ".md")).is_file())
                self.assertIn("Document role is", (root / role / (role + ".md")).read_text(encoding="utf-8"))

    def test_duplicate_basenames_require_explicit_folder_decisions(self):
        a = self.document("first", "<!-- page: 1 -->\n\nFirst.\n", pdf_name="same.pdf")
        b = self.document("second", "<!-- page: 1 -->\n\nSecond.\n", pdf_name="same.pdf")
        with self.assertRaisesRegex(ValueError, "collide"):
            check(self.plan([a, b]))
        a["folder"], b["folder"] = "Course-first", "Course-second"
        self.assertEqual(check(self.plan([a, b]))["errors"], 0)

    def test_setext_heading_callout_preserves_exact_title_and_body(self):
        document = self.document("setext", "<!-- page: 1 -->\n\nTheorem 1\n---------\n\n"
                                 "Statement with $\\alpha$.\n\n$$\\alpha=1$$")
        heading = self.block(document, "Theorem", kind="heading")
        final = self.block(document, "$$", kind="math_block")
        document["operations"] = [{"op": "callout", "kind": "theorem", "id": "theorem",
                                   "start": heading, "end": final}]
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["errors"], 0, report)
        text = (Path(plan.destination) / "Course-setext" / "setext.md").read_text()
        self.assertIn("> [!theorem] Theorem 1", text)
        self.assertIn("> $$\\alpha=1$$", text)

    def test_heading_adjustment_does_not_rewrite_the_title(self):
        document = self.document("heading", "<!-- page: 1 -->\n\n# Course\n\n#### Detail with $x$\n\nText.\n")
        heading = self.block(document, "#### Detail", kind="heading")
        document["operations"] = [{"op": "heading", "block": heading, "level": 2}]
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["errors"], 0, report)
        text = (Path(plan.destination) / "Course-heading" / "heading.md").read_text()
        self.assertIn("## Detail with $x$", text)
        self.assertNotIn("Heading level jumps", text)

    def test_original_pdf_and_self_heading_links_are_remapped_exactly(self):
        document = self.document("links", "<!-- page: 1 -->\n\n## Theorem 1\n\nStatement.\n\n"
                                 "[Statement](#Theorem%201) and [PDF](source/links.pdf#page=1 \"Caption\").\n")
        heading = self.block(document, "## Theorem", kind="heading")
        body = self.block(document, "Statement.", kind="paragraph")
        document["operations"] = [{"op": "callout", "kind": "theorem", "id": "thm",
                                   "start": heading, "end": body}]
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["errors"], 0, report)
        text = (Path(plan.destination) / "Course-links" / "links.md").read_text()
        self.assertIn("[Statement](#^thm)", text)
        self.assertIn('[PDF](links.pdf#page=1 "Caption")', text)

    def test_reference_definition_remap_keeps_source_labels(self):
        document = self.document("reference", "<!-- page: 1 -->\r\n\r\n[Original][pdf]\r\n\r\n"
                                 '[pdf]: <source/reference.pdf> "Original title"\r\n')
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["errors"], 0, report)
        text = (Path(plan.destination) / "Course-reference" / "reference.md").read_bytes().decode()
        self.assertIn('[pdf]: <reference.pdf> "Original title"\r\n', text)

    def test_discontiguous_pdf_entry_links_use_original_starting_page(self):
        document = self.document("pages", "<!-- page: 2 -->\n\n# Selected pages\n\nFirst selected page.\n\n"
                                 "<!-- page: 4 -->\n\nSecond selected page.\n", count=4)
        document["operations"] = [
            {"op": "unit", "kind": "section", "id": "sec-pages",
             "start": self.block(document, "# Selected pages", kind="heading"),
             "end": self.block(document, "Second selected", kind="paragraph")},
        ]
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["errors"], 0, report)
        text = (Path(plan.destination) / "Course-pages" / "pages.md").read_text()
        self.assertIn("pages.pdf#page=2", text)
        self.assertNotIn("pages.pdf#page=4", text)
        self.assertIn("source_pages: [2, 4]", text)
        self.assertEqual(text.count("(pages.pdf#page="), 1)
        self.assertNotIn("#page=1", text)
        self.assertNotIn("#page=2-4", text)
        self.assertEqual(validate(Path(plan.destination), fidelity=True)["errors"], 0)

    def test_broken_links_undefined_refs_and_unsafe_schemes_block_initial_preparation(self):
        document = self.document("bad", "<!-- page: 1 -->\n\n[Missing][unknown] "
                                 "[Bad PDF page](source/bad.pdf#page=3) [Unsafe](javascript:alert(1)).\n")
        plan = self.plan([document])
        report = check(plan)
        self.assertEqual(report["status"], "invalid", report)
        self.assertTrue({"undefined-reference", "pdf-page", "unsafe-link"} <= self.codes(report), report)
        with self.assertRaisesRegex(ValueError, "invalid"):
            materialize(plan, plan_hash(plan))
        self.assertFalse(Path(plan.destination).exists())

    def test_wrong_answer_owner_is_rejected(self):
        plan = self.pipeline_plan()
        data = plan.model_dump()
        data["documents"][-1]["operations"][-1]["owner"] = "sec-root"
        with self.assertRaisesRegex(ValueError, "wrong unit kind"):
            check(Plan.model_validate(data))

    def test_current_relationship_edit_cannot_point_to_a_theorem(self):
        plan = self.pipeline_plan()
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        path = root / "Correction-solutions" / "solutions.md"
        path.write_text(path.read_text().replace("../Exercise-sheet/sheet.md#^q-1",
                                                "../Course-course/course.md#^thm-geometric"))
        self.assertIn("relationship-kind", self.codes(validate(root)))

    def test_parsed_fence_marker_lookalikes_are_preserved(self):
        document = self.document("code", "<!-- page: 1 -->\n\n```\n<!-- clew:unit exercise fake -->\n"
                                 "<!-- page: 8 -->\n[Hidden](absent.md)\n```\n")
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["errors"], 0, report)
        text = (Path(plan.destination) / "Course-code" / "code.md").read_text()
        self.assertIn("<!-- page: 8 -->", text)

    def test_suspicious_heading_warnings_and_source_order_are_preserved(self):
        text = "<!-- page: 1 -->\n\n# Course\n\n#### Theorem 9\n\nFirst.\n\nFirst.\n"
        document = self.document("structure", text)
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["errors"], 0, report)
        self.assertTrue({"heading-gap", "unclassified-unit"} <= self.codes(report))
        output = (Path(plan.destination) / "Course-structure" / "structure.md").read_text()
        self.assertIn("> [!warning] Clew review", output)
        self.assertIn("#### Theorem 9\n\nFirst.\n\nFirst.", output)

    def test_baseline_and_retained_asset_edits_are_detected_in_current_mode(self):
        plan = self.plan([self.course()])
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        (root / "Course-course" / "figures" / "a.png").write_bytes(b"modified figure")
        self.assertIn("retained-source", self.codes(validate(root)))
        (root / ".clew" / "baselines" / "course" / "document.md").write_bytes(b"modified baseline")
        self.assertIn("retained-source", self.codes(validate(root)))

    def test_tampered_records_do_not_hide_source_content_changes(self):
        plan = self.plan([self.course()])
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        note = root / "Course-course" / "course.md"
        note.write_text(note.read_text().replace("First case.", "Lost original wording."))
        record_path = root / ".clew" / "preparation.json"
        record = json.loads(record_path.read_text())
        record["documents"][0]["prepared_sha256"] = digest(note.read_bytes())
        record_path.write_text(json.dumps(record))
        self.assertIn("source-fidelity", self.codes(validate(root, fidelity=True)))

    def test_existing_source_anchor_is_reused(self):
        document = self.document("anchor", "<!-- page: 1 -->\n\nPlain text. ^existing\n")
        block = self.block(document, "Plain text", kind="paragraph")
        document["operations"] = [{"op": "anchor", "id": "existing", "block": block}]
        plan = self.plan([document])
        materialize(plan, plan_hash(plan))
        text = (Path(plan.destination) / "Course-anchor" / "anchor.md").read_text()
        self.assertEqual(text.count("^existing"), 1)

    def test_table_callout_retains_table_structure_and_reference_links(self):
        document = self.document("table", "<!-- page: 1 -->\n\n## Property 1\n\n"
                                 "| A | B |\n| - | - |\n| $x$ | [PDF][pdf] |\n\n"
                                 "[pdf]: source/table.pdf\n")
        heading = self.block(document, "## Property", kind="heading")
        last = self.block(document, "[pdf]:", kind="reference")
        document["operations"] = [{"op": "callout", "kind": "property", "id": "property",
                                   "start": heading, "end": last}]
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["errors"], 0, report)

    def test_missing_internal_structure_is_visible_for_unheaded_exercise_lists(self):
        document = self.document("list", "<!-- page: 1 -->\n\n1. A question.\n\n2. Another question.\n",
                                 role="exercise")
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        self.assertIn("unclassified-item", self.codes(report))
        text = (Path(plan.destination) / "Exercise-list" / "list.md").read_text()
        self.assertIn("no addressed question block", text)

    def test_native_heading_with_markup_and_case_insensitive_note_link(self):
        document = self.document("headings", "<!-- page: 1 -->\n\n## **Geometric** limits\n\n"
                                 "[Section](document.md#Geometric%20limits).\n")
        plan = self.plan([document])
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["errors"], 0, report)

    def test_checked_cli_is_read_only_and_reports_review_exit_code(self):
        document = self.document("cli", "<!-- page: 1 -->\n\n# Unclassified heading\n\nText.\n")
        plan = self.plan([document])
        path = self.root / "approved-plan.json"
        path.write_text(plan.model_dump_json(), encoding="utf-8")
        before = {item: item.read_bytes() for item in self.root.rglob("*") if item.is_file()}
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "prepare_documents.py"),
                                 str(path), "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["status"], "needs_review")
        self.assertEqual(before, {item: item.read_bytes() for item in before})
        self.assertFalse(Path(plan.destination).exists())

    def test_prepared_and_legacy_roots_are_excluded_from_pdf_discovery(self):
        import plan_imports
        plan = self.plan([self.course()])
        materialize(plan, plan_hash(plan))
        sources, conflicts, excluded = plan_imports.discover(self.vault)
        self.assertEqual((sources, conflicts), ([], []))
        self.assertIn(plan.destination, excluded)
        record = self.vault / "Maths" / "Legacy" / "ingest.json"
        record.parent.mkdir()
        record.write_text(json.dumps({"schema_version": 3, "status": "complete",
                                      "plan": {}, "sources": {"legacy": {}}}))
        (record.parent / "retained.pdf").write_bytes(b"must not be inspected")
        sources, conflicts, excluded = plan_imports.discover(self.vault)
        self.assertEqual((sources, conflicts), ([], []))
        self.assertIn(str(record.parent), excluded)
        record.write_text("{}")
        _, conflicts, _ = plan_imports.discover(self.vault)
        self.assertTrue(conflicts)

    def test_vault_import_inventory_does_not_claim_chapter_ownership(self):
        private = self.vault / ".clew"
        private.mkdir()
        inventory = private / "imports.json"
        inventory.write_text('{"imports":[]}', encoding="utf-8")
        before = inventory.read_bytes()
        report = check(self.plan([self.course()]))
        self.assertEqual(report["errors"], 0, report)
        self.assertEqual(inventory.read_bytes(), before)
        self.assertFalse(Path(report["destination"]).exists())

    def test_preparation_markers_and_partial_baselines_still_block_nesting(self):
        private = self.vault / ".clew"
        private.mkdir()
        plan = self.plan([self.course()])
        marker = private / "preparation.json"
        marker.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "owned root"):
            check(plan)
        marker.unlink()
        (private / "baselines").mkdir()
        with self.assertRaisesRegex(ValueError, "owned root"):
            check(plan)

    def test_real_converter_handoff_uses_current_bundle_without_reconversion(self):
        from test_digest_pdf import clients, di_result, ingestion, make_pdf, response
        pdf = self.root / "real-source.pdf"
        make_pdf(pdf)
        output = self.root / "converted"
        document_client, openai_client = clients(di_result(["Source"], numbers=[2]),
                                                 [response("## Course\n\n$1+1=2$.\n")])
        ingestion.digest_pdf(pdf, output, document_client, openai_client, "vision",
                             pages="2", dpi=72, page_review=False)
        bundle = load_bundle(output)
        document = {"id": "real-source", "role": "course", "bundle": str(output),
                    "fingerprint": bundle.fingerprint, "operations": []}
        plan = self.plan([document])
        before_calls = openai_client.responses.create.call_count
        report = materialize(plan, plan_hash(plan))
        self.assertEqual(report["errors"], 0, report)
        self.assertEqual(openai_client.responses.create.call_count, before_calls)
        self.assertEqual((Path(plan.destination) / "Course-real-source" / "real-source.pdf").read_bytes(),
                         pdf.read_bytes())

    def test_standalone_copy_prepares_and_validates_without_repository_runtime(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from runtime_fixtures import build_wheelhouse
        plan = self.plan([self.course()])
        standalone = self.root / "standalone"
        shutil.copytree(SCRIPTS.parent, standalone)
        exported = subprocess.run([
            "uv", "export", "--package", "clew-import", "--locked", "--no-dev",
            "--no-emit-project", "--no-hashes", "--format", "requirements-txt"],
            cwd=SCRIPTS.parents[3], capture_output=True, encoding="utf-8")
        self.assertEqual(exported.returncode, 0, exported.stderr)
        wheels = self.root / "wheels"
        from importlib.metadata import PackageNotFoundError, version
        requirements = []
        for line in exported.stdout.splitlines():
            if not line or line.startswith("#") or line[0].isspace():
                continue
            requirement = line.split(";", 1)[0].strip()
            name, _, expected = requirement.partition("==")
            try:
                installed = version(name)
            except PackageNotFoundError:
                continue
            self.assertEqual(installed, expected)
            requirements.append(requirement)
        build_wheelhouse(wheels, "\n".join(requirements))
        executable = standalone / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        for args in [
            ["uv", "venv", str(standalone / ".venv"), "--python", sys.executable],
            ["uv", "pip", "install", "--python", str(executable), "--offline", "--no-index",
             "--find-links", str(wheels), str(standalone)],
        ]:
            if args[1:3] == ["pip", "install"]:
                # Install declared runtime requirements, without invoking a missing build backend.
                args[-1:] = requirements
            setup = subprocess.run(args, capture_output=True, encoding="utf-8")
            self.assertEqual(setup.returncode, 0, setup.stderr)
        plan_path = self.root / "standalone-plan.json"
        plan_path.write_text(plan.model_dump_json(), encoding="utf-8")
        for script, args in [
            ("prepare_documents.py", [str(plan_path), "--check"]),
            ("prepare_documents.py", [str(plan_path), "--plan-sha256", plan_hash(plan)]),
            ("validate_documents.py", [plan.destination, "--fidelity"]),
        ]:
            result = subprocess.run([str(executable), "-B", str(standalone / "scripts" / script), *args],
                                    cwd=standalone, capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            self.assertEqual(json.loads(result.stdout)["errors"], 0)


class SourceTests(unittest.TestCase):
    def test_maps_original_destinations_with_parentheses_titles_and_crlf(self):
        text = ('![A](<figures/a(b).png> "Caption") and [**B**](source/b.pdf#page=2).\r\n'
                '\r\n`[Code](hidden.md)` and $[Math](hidden.md)$\r\n')
        source = MarkdownSource(text)
        links = source.links
        self.assertEqual(len(links), 2)
        self.assertEqual(text[links[0].destination_start:links[0].destination_end], "figures/a(b).png")
        self.assertEqual(text[links[1].destination_start:links[1].destination_end], "source/b.pdf#page=2")

    def test_protected_blocks_have_no_interior_selectors(self):
        for text in ("$$\nx^2\n$$\n", "```\n# Heading\n```\n",
                     "| A | B |\n| - | - |\n| 1 | 2 |\n", "> one\n> two\n"):
            source = MarkdownSource(text)
            self.assertFalse(any(block.start == 1 for block in source.blocks.values()), text)

    def test_undefined_references_and_wikilinks_are_exposed(self):
        source = MarkdownSource("[a][missing] and [[Course#^theorem|Theorem]].\n")
        self.assertEqual(source.unresolved_references, [(1, "MISSING")])
        self.assertEqual(source.links[0].target, "Course#^theorem")


if __name__ == "__main__":
    unittest.main()
