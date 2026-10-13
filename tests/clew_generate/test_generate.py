"""Current-document publication, preservation, portability and offline checks."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "clew-generate"
FIXTURE = Path(__file__).parent / "fixtures" / "chapter"
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from generate_html import generate
from notes import GenerateError, Library, list_chapters, read_note
from publication import compile_layout, load_layout
from render_html import Renderer
from runtime_fixtures import build_wheelhouse


class GenerateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.chapter = self.root / "chapter"
        shutil.copytree(FIXTURE, self.chapter)
        self.sheet = self.chapter / "Exercise-sheet" / "sheet.md"
        self.solutions = self.chapter / "Correction-solutions" / "solutions.md"
        self.course = self.chapter / "Course-course" / "course.md"
        self.aid = self.chapter / "aides" / "q-1.md"
        self.layout = self.root / "layout.json"
        self.layout.write_text(json.dumps({
            "schema_version": 1, "title": "Sequences", "notes": [str(self.chapter)],
            "output": "publication.html",
        }), encoding="utf-8")

    def model(self):
        layout, library = load_layout(self.layout)
        renderer = Renderer(library, Path(layout["output"]))
        data = compile_layout(layout, library, renderer)
        renderer.validate_links()
        return data

    def modify(self, **changes):
        layout = json.loads(self.layout.read_text(encoding="utf-8"))
        layout.update(changes)
        self.layout.write_text(json.dumps(layout), encoding="utf-8")

    def edit(self, path, old, new):
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")

    def test_document_units_and_optional_aids(self):
        model = self.model()
        self.assertEqual([e["address"] for e in model["exercises"]], ["sheet#^ex-1", "sheet#^ex-2"])
        self.assertEqual([e["title"] for e in model["exercises"]], ["Exercise 1", "Exercise 2"])
        self.assertEqual([len(e["questions"]) for e in model["exercises"]], [2, 1])
        self.assertEqual([q["address"] for q in model["questions"]],
                         ["sheet#^q-1", "sheet#^q-2", "sheet#^q-3"])
        self.assertEqual([len(q["corrections"]) for q in model["questions"]], [2, 1, 0])
        self.assertEqual([len(q["hints"]) for q in model["questions"]], [2, 0, 0])
        self.assertEqual([len(q["explanations"]) for q in model["questions"]], [1, 0, 0])
        self.assertNotIn("clew:unit", str(model))
        self.assertNotIn("clew:review", str(model))
        self.assertNotIn("Exercise ^ex", str(model))

    def test_document_context_and_review_are_kept_once_in_order(self):
        stream = self.model()["worksheet"]
        self.assertIn("Worksheet introduction", stream[1]["html"])
        first = next(i for i, item in enumerate(stream) if item.get("exercise") == "sheet#^ex-1")
        second = next(i for i, item in enumerate(stream) if item.get("exercise") == "sheet#^ex-2")
        self.assertIn("Shared section instruction", str(stream[first + 1:second]))
        self.assertIn("Check the unanswered question", str(stream[second + 1:]))
        self.assertEqual(str(stream).count("Worksheet introduction"), 1)
        self.assertIn("Review required in sheet", str(generate(self.layout, check=True)["warnings"]))

    def test_correction_context_is_unit_scoped_and_variants_are_separate(self):
        panels = self.model()["questions"][0]["corrections"]
        self.assertEqual(len(panels), 2)
        self.assertEqual(panels[0].count("Shared correction context 1."), 1)
        self.assertNotIn("Variant context", panels[0])
        self.assertNotIn("Use the inequality", panels[0])
        self.assertIn("Variant context", panels[1])
        self.assertNotIn("Shared correction context 1.", panels[1])

    def test_current_edits_and_no_producer_record(self):
        self.assertFalse((self.chapter / ".clew").exists())
        self.edit(self.sheet, "Determine its limit", "Determine its edited limit")
        self.assertIn("edited limit", self.model()["questions"][0]["html"])
        generate(self.layout)

    def test_no_aids_or_corrections_are_valid(self):
        self.aid.unlink()
        self.solutions.unlink()
        model = self.model()
        self.assertEqual(len(model["questions"]), 3)
        self.assertTrue(all(not q["corrections"] and not q["hints"] for q in model["questions"]))

    def test_explicit_files_and_index_are_equivalent(self):
        base = self.model()
        for paths in ([str(self.chapter / "index.md")],
                      [str(self.sheet), str(self.solutions), str(self.course), str(self.aid)]):
            self.modify(notes=paths)
            self.assertEqual([e["address"] for e in self.model()["exercises"]],
                             [e["address"] for e in base["exercises"]])

    def test_chapter_discovery_excludes_private_and_retained_sources(self):
        for name in (".clew", ".obsidian", "sources"):
            folder = self.chapter / name
            folder.mkdir()
            (folder / "private.md").write_text("not a learning note", encoding="utf-8")
        library = Library([self.chapter, self.chapter / "index.md", self.sheet])
        self.assertEqual(len(library.notes), 4)
        self.assertFalse(library.chapters[0]["omitted"])
        report = list_chapters(self.root)
        self.assertEqual(report["chapters"], [{"root": str(self.chapter), "title": "Sequence worksheet"}])
        self.assertTrue(list_chapters(self.root, depth=0)["omitted"])
        with self.assertRaisesRegex(GenerateError, "list-chapters"):
            Library([self.root])

    def test_inventory_has_units_owners_and_native_section_headings(self):
        result = subprocess.run([sys.executable, "-B", str(SKILL / "scripts" / "inspect_notes.py"),
                                 str(self.chapter)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        notes = json.loads(result.stdout)["notes"]
        sheet = next(note for note in notes if note["id"] == "sheet")
        self.assertEqual(sheet["units"][0]["ref"], None)
        self.assertEqual(sheet["blocks"][1]["owner"], "ex-1")
        self.assertIn("Exercise 1", sheet["headings"])
        with self.assertRaisesRegex(GenerateError, "Missing block"):
            read_note(self.sheet).select("^sec-sheet")

    def test_document_navigation_anchor_precedes_exercise_views(self):
        model = self.model()
        self.assertIn('id="note-', model["worksheet"][0]["html"])

    def test_course_only_and_exercise_only(self):
        self.modify(exercises=[])
        self.assertFalse(self.model()["exercises"])
        self.modify(exercises=["sheet"], courses=[])
        model = self.model()
        self.assertFalse(model["reading"])
        self.assertEqual(len(model["course_links"]), 2)
        self.assertIn("Geometric limit result", str(model["courses"]))

    def test_course_callout_excerpt_keeps_title_and_body(self):
        self.modify(courses=["course#^theorem"], exercises=[])
        html = self.model()["courses"][0]["html"]
        self.assertIn("Geometric limit result", html)
        self.assertIn("tends to zero", html)
        self.assertNotIn("[!theorem]", html)
        self.assertNotIn("Bounds", html)

    def test_partial_questions_group_in_source_order_with_context(self):
        self.modify(exercises=["sheet#^q-2", "sheet.md#^q-1"])
        model = self.model()
        self.assertEqual(len(model["exercises"]), 1)
        self.assertEqual([q["address"] for q in model["questions"]], ["sheet#^q-1", "sheet#^q-2"])
        self.assertIn("Let", str(model["exercises"][0]["segments"]))
        self.assertIn("Intermediate instruction", str(model["exercises"][0]["segments"]))
        self.assertNotIn("Worksheet introduction", str(model["worksheet"]))

    def test_unit_entry_selection_expands_scope_but_native_anchor_does_not(self):
        self.assertEqual(read_note(self.sheet).select("^ex-1"), "")
        self.modify(exercises=["sheet#^ex-1"])
        self.assertEqual(len(self.model()["questions"]), 2)

    def test_source_entry_anchor_and_human_edits_are_not_scaffolding(self):
        self.edit(self.sheet, "Exercise ^ex-1", "Keep this source instruction. ^ex-1")
        self.modify(exercises=["sheet#^ex-1"])
        self.assertEqual(read_note(self.sheet).select("^ex-1"), "Keep this source instruction.")
        self.assertIn("Keep this source instruction", str(self.model()["exercises"][0]["segments"]))

    def test_heading_and_safe_range_keep_question_addresses(self):
        lines = self.sheet.read_text(encoding="utf-8").splitlines()
        first = lines.index("> [!question] Question 1") + 1
        last = lines.index("^q-1") + 1
        for selector, count in (("sheet#Exercise 1", 2), (f"sheet#L{first}-L{last}", 1)):
            self.modify(exercises=[selector])
            self.assertEqual(len(self.model()["exercises"]), 1)
            self.assertEqual(len(self.model()["questions"]), count)
            self.assertEqual(self.model()["questions"][0]["address"], "sheet#^q-1")
        self.modify(exercises=[f"sheet#L{first + 2}-L{last}"])
        with self.assertRaisesRegex(GenerateError, "bisects"):
            self.model()

    def test_setext_exercise_heading_keeps_its_title(self):
        self.edit(self.sheet, "## Exercise 1", "Exercise 1\n----------")
        self.assertEqual(self.model()["exercises"][0]["title"], "Exercise 1")

    def test_overlaps_and_aliases_are_rejected(self):
        for refs in (["sheet", "sheet#^q-1"], ["sheet#^ex-1", "sheet#^q-1"],
                     ["sheet#^q-1", "sheet.md#^q-1"], ["sheet#Exercise 1", "sheet#^q-1"]):
            self.modify(exercises=refs)
            with self.assertRaisesRegex(GenerateError, "overlapping"):
                self.model()

    def test_repeated_local_anchors_in_different_documents_are_distinct(self):
        another = self.chapter / "Exercise-sheet" / "another.md"
        another.write_text(self.sheet.read_text(encoding="utf-8").replace("id: sheet", "id: another")
                           .replace("sheet.md#^q-3", "another.md#^q-3"), encoding="utf-8")
        self.modify(exercises=["sheet#^q-1", "another#^q-1"])
        model = self.model()
        self.assertEqual([e["address"] for e in model["exercises"]], ["sheet#^ex-1", "another#^ex-1"])
        self.assertFalse(model["questions"][1]["corrections"])
        self.assertFalse(model["questions"][1]["hints"])

    def test_unmatched_answer_is_warned_and_can_be_explicitly_selected(self):
        self.edit(self.solutions, "[Question](../Exercise-sheet/sheet.md#^q-2) · ", "")
        report = generate(self.layout, check=True)
        self.assertIn("Unmatched supplied answer: solutions#^r-2", report["warnings"])
        self.assertFalse(self.model()["questions"][1]["corrections"])
        self.modify(questions={"sheet#^q-2": {"corrections": ["solutions#^r-2"]}})
        self.assertTrue(self.model()["questions"][1]["corrections"])

    def test_compact_and_separate_relationship_footers(self):
        original = self.model()["questions"][0]["corrections"]
        self.edit(self.solutions, ") · [PDF", ")\n> [PDF")
        self.assertEqual(len(self.model()["questions"][0]["corrections"]), len(original))

    def test_wrong_unit_and_question_links_are_rejected(self):
        self.edit(self.solutions, "sheet.md#^ex-1", "sheet.md#^ex-2")
        with self.assertRaisesRegex(GenerateError, "exercise owner"):
            self.model()

    def test_explicit_answer_and_correction_unit_selection(self):
        self.modify(questions={"sheet#^q-1": {"corrections": ["solutions#^corr-1"]}})
        panel = self.model()["questions"][0]["corrections"][0]
        self.assertIn("limit is", panel)
        self.assertNotIn("Use the inequality", panel)
        self.modify(questions={"sheet#^q-1": {"corrections": ["solutions"]}})
        with self.assertRaisesRegex(GenerateError, "multi-unit"):
            self.model()
        self.modify(questions={"sheet#^q-1": {"corrections": ["solutions#^r-2"]}})
        with self.assertRaisesRegex(GenerateError, "Correction/question mismatch"):
            self.model()
        self.modify(questions={"sheet#^q-3": {"corrections": ["solutions#^r-1"]}})
        with self.assertRaisesRegex(GenerateError, "another exercise"):
            self.model()

    def test_aid_suppression_and_answer_filtering(self):
        self.modify(questions={"sheet#^q-1": {"corrections": []}})
        question = self.model()["questions"][0]
        self.assertFalse(question["corrections"])
        self.assertFalse(question["explanations"])
        self.assertEqual(len(question["hints"]), 2)
        self.modify(questions={"sheet#^q-1": {"hints": [], "explanations": []}})
        self.assertFalse(self.model()["questions"][0]["hints"])

    def test_bad_aid_mappings_fail_explicitly(self):
        self.edit(self.aid, "solutions#^r-1", "solutions#^r-2")
        with self.assertRaisesRegex(GenerateError, "correction/question mismatch"):
            self.model()

    def test_explanation_needs_selected_answer(self):
        self.modify(questions={"sheet#^q-1": {
            "corrections": ["solutions#^r-variant"],
            "explanations": ["aid-q-1#^explanation"],
        }})
        with self.assertRaisesRegex(GenerateError, "unselected correction"):
            self.model()

    def test_markdown_course_links_resolve_url_encoded_paths(self):
        renamed = self.course.with_name("course name.md")
        self.course.rename(renamed)
        self.edit(self.aid, "[[course#^theorem|the geometric limit result]]",
                  "[the geometric limit result](../Course-course/course%20name.md#%5Etheorem)")
        self.assertEqual(len(self.model()["course_links"]), 2)

    def test_relative_self_links_precede_ambiguous_filename_aliases(self):
        folder = self.chapter / "Another-sheet"
        folder.mkdir()
        duplicate = folder / "sheet.md"
        duplicate.write_text(self.sheet.read_text(encoding="utf-8").replace(
            "id: sheet", "id: another"), encoding="utf-8")
        library = Library([self.sheet, duplicate])
        target, fragment = library.resolve("sheet.md#^q-1", library.notes[0])
        self.assertEqual((target.id, fragment), ("sheet", "^q-1"))
        with self.assertRaisesRegex(GenerateError, "ambiguous"):
            library.resolve("sheet.md#^q-1")

    def test_methods_are_consumed_not_authored(self):
        self.aid.write_text(self.aid.read_text(encoding="utf-8") +
                            "\n> [!method]\n> Use [[course#^theorem]].\n\n^method\n", encoding="utf-8")
        self.assertIn("Use", self.model()["questions"][0]["method"])
        self.modify(questions={"sheet#^q-1": {"method": None}})
        self.assertFalse(self.model()["questions"][0]["method"])

    def test_mixed_documents_use_explicit_scopes(self):
        self.edit(self.sheet, "role: exercise", "role: mixed")
        self.assertEqual(len(self.model()["exercises"]), 2)

    def test_unstructured_unit_is_not_an_invented_question(self):
        self.aid.unlink()
        self.solutions.unlink()
        text = self.sheet.read_text(encoding="utf-8")
        start = text.index("> [!question]")
        end = text.index("[PDF p. 1](sheet.pdf#page=1)\n\n%% /clew:unit ex-1")
        self.sheet.write_text(text[:start] + "Preserved unstructured exercise.\n\n" + text[end:],
                              encoding="utf-8")
        self.modify(exercises=["sheet#^ex-1"])
        self.assertFalse(self.model()["questions"])
        self.assertIn("Preserved unstructured exercise", str(self.model()))

    def test_legacy_inputs_and_missing_frontmatter_are_rejected(self):
        for text in ("Plain legacy note.", "---\nid: legacy\ntype: exercise\n---\nText"):
            path = self.root / "legacy.md"
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(GenerateError, "[Ll]egacy"):
                Library([path])

    def test_duplicate_identity_anchor_and_invalid_units(self):
        original = self.sheet.read_text(encoding="utf-8")
        for text, message in ((original.replace("^q-2", "^q-1"), "Duplicate block"),
                              (original.replace("%% /clew:unit ex-1 %%", ""), "nested unit"),
                              (original.replace("Exercise ^ex-1", "Exercise"), "entry anchor"),
                              (original.replace("%% clew:unit exercise ex-2 %%",
                                                "%% clew:unit exercise ex-1 %%"), "Duplicate unit")):
            self.sheet.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(GenerateError, message):
                self.model()
        self.sheet.write_text(original, encoding="utf-8")
        duplicate = self.chapter / "duplicate.md"
        shutil.copyfile(self.sheet, duplicate)
        with self.assertRaisesRegex(GenerateError, "Duplicate learning-note IDs"):
            self.model()

    def test_unowned_question_is_rejected(self):
        self.sheet.write_text(self.sheet.read_text(encoding="utf-8") +
                              "\n> [!question]\n> Outside unit.\n\n^outside\n", encoding="utf-8")
        with self.assertRaisesRegex(GenerateError, "owner"):
            self.model()

    def test_code_math_and_comment_lookalikes_are_not_structure(self):
        text = ("\n```\n%% clew:unit exercise fake %%\n> [!question]\n^q-1\n```\n\n"
                "$$\n\\text{%% clew:unit exercise fake %%}\n$$\n\n"
                "Source %%hidden comment%% text and `%%literal%%`.\n")
        self.course.write_text(self.course.read_text(encoding="utf-8") + text, encoding="utf-8")
        note = read_note(self.course)
        self.assertEqual(len(note.units), 1)
        self.assertIn("%%literal%%", note.select())
        self.assertNotIn("hidden comment", note.select())
        self.assertIn("exercise fake", note.select())

    def test_all_supported_newlines_and_relocation_preserve_inputs(self):
        for newline in ("\n", "\r\n", "\r"):
            with self.subTest(newline=repr(newline)):
                for path in self.chapter.rglob("*.md"):
                    text = path.read_text(encoding="utf-8")
                    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
                before = {path: path.read_bytes() for path in self.chapter.rglob("*") if path.is_file()}
                self.assertEqual(len(self.model()["questions"]), 3)
                generate(self.layout, check=True)
                self.assertEqual(before, {path: path.read_bytes() for path in before})
        moved = self.root / "relocated"
        self.chapter.rename(moved)
        self.modify(notes=[str(moved)])
        self.assertEqual(len(self.model()["questions"]), 3)

    def test_check_determinism_atomic_output_and_input_preservation(self):
        before = {path: path.read_bytes() for path in self.chapter.rglob("*") if path.is_file()}
        generate(self.layout, check=True)
        output = self.root / "publication.html"
        self.assertFalse(output.exists())
        generate(self.layout)
        first = output.read_bytes()
        with self.assertRaisesRegex(GenerateError, "Output exists"):
            generate(self.layout)
        generate(self.layout, overwrite=True)
        self.assertEqual(first, output.read_bytes())
        self.modify(questions={"sheet#^q-1": {"method": "missing"}})
        with self.assertRaises(GenerateError):
            generate(self.layout, overwrite=True)
        self.assertEqual(first, output.read_bytes())
        self.assertFalse(list(self.root.glob("*.tmp")))
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        self.assertNotIn(b'<script src=', first)
        self.assertNotIn(b'<link ', first)

    def test_figures_tables_and_pdf_rebasing(self):
        (self.course.parent / "figure.png").write_bytes(base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aO1cAAAAASUVORK5CYII="))
        self.course.write_text(self.course.read_text(encoding="utf-8") +
                               "\n![Figure](figure.png)\n\n| A | B |\n|---|---|\n| 1 | 2 |\n",
                               encoding="utf-8")
        model = self.model()
        self.assertIn("data:image/png;base64,", str(model))
        self.assertIn("<table>", str(model))
        self.assertIn("Course-course/course.pdf#page=1", str(model))

    def test_unsupported_assets_html_plugins_and_math(self):
        original = self.course.read_text(encoding="utf-8")
        (self.course.parent / "figure.svg").write_text("<svg/>", encoding="utf-8")
        for text, message in (("![Figure](figure.svg)", "Unsupported or invalid"),
                              ("![Figure](missing.png)", "Missing figure"),
                              ("![Figure](https://example.com/figure.png)", "local raster"),
                              ("![[sheet.md]]", "transclusion"),
                              ("```dataview\nTABLE\n```", "Dataview"),
                              ("$\\require{html}$", "externally loaded")):
            self.course.write_text(original + "\n" + text, encoding="utf-8")
            with self.assertRaisesRegex(GenerateError, message):
                self.model()
        self.course.write_text(original + "\n<script>alert(1)</script>", encoding="utf-8")
        self.assertNotIn("<script>", str(self.model()["courses"]))

    def test_invalid_layout_unused_overrides_and_unpublished_targets(self):
        self.modify(questions={"sheet#^q-3": {"unknown": []}})
        with self.assertRaisesRegex(GenerateError, "Invalid question options"):
            self.model()
        self.modify(exercises=["sheet#^q-1"], questions={"sheet#^q-3": {"hints": []}})
        with self.assertRaisesRegex(GenerateError, "unpublished questions"):
            self.model()
        self.modify(exercises=["sheet#^q-1"], questions={})
        self.edit(self.sheet, "Determine its limit.", "Determine its limit. [[sheet#^q-3]]")
        with self.assertRaisesRegex(GenerateError, "outside the publication"):
            self.model()

    def test_heading_aliases_ambiguity_and_block_navigation(self):
        self.course.write_text(self.course.read_text(encoding="utf-8") +
                               "\n## *A formula* $f(I)\\\\subset I$\n\nText.\n",
                               encoding="utf-8")
        note = read_note(self.course)
        self.assertIn("Text", note.select(r"A formula $f(I)\subset I$"))
        self.course.write_text(self.course.read_text(encoding="utf-8") +
                               "\n## Bounds\n\nAnother bound.\n", encoding="utf-8")
        with self.assertRaisesRegex(GenerateError, "ambiguous heading"):
            read_note(self.course).select("Bounds")

    def test_template_hooks_and_tokens_are_preserved(self):
        self.modify(title="{{DATA}}")
        generate(self.layout)
        page = (self.root / "publication.html").read_text(encoding="utf-8")
        self.assertIn("<title>{{DATA}}</title>", page)
        template = (SKILL / "assets" / "template.html").read_text(encoding="utf-8")
        script = (SKILL / "assets" / "interaction.js").read_text(encoding="utf-8")
        for name in ("course", "exercise", "question", "content", "method", "hints",
                     "hint", "correction", "explanations"):
            self.assertIn(f'<template id="template-{name}">', template)
        self.assertNotIn("createElement", script)

    def test_multiple_methods_require_explicit_selection(self):
        self.aid.write_text(self.aid.read_text(encoding="utf-8") +
                            "\n> [!method]\n> First.\n\n^method-1\n\n"
                            "> [!method]\n> Second.\n\n^method-2\n", encoding="utf-8")
        with self.assertRaisesRegex(GenerateError, "Multiple methods"):
            self.model()
        self.modify(questions={"sheet#^q-1": {"method": "aid-q-1#^method-2"}})
        self.assertIn("Second", self.model()["questions"][0]["method"])

    def test_id_resolution_does_not_restat_notes(self):
        library = Library([self.course, self.sheet])
        with patch("notes.local_path", side_effect=AssertionError("unexpected filesystem access")):
            note, fragment = library.resolve("course#^theorem", library.notes[1])
        self.assertEqual((note.id, fragment), ("course", "^theorem"))

    def test_copied_skill_without_repository_runtime(self):
        copied = self.root / "standalone"
        shutil.copytree(SKILL, copied, ignore=shutil.ignore_patterns("__pycache__"))
        exported = subprocess.run([
            "uv", "export", "--package", "clew-generate", "--locked", "--no-dev",
            "--no-emit-project", "--no-hashes", "--format", "requirements-txt"],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(exported.returncode, 0, exported.stderr)
        wheelhouse = self.root / "wheelhouse"
        build_wheelhouse(wheelhouse, exported.stdout)
        setup = subprocess.run(["uv", "sync", "--directory", str(copied), "--offline",
                                "--no-index", "--find-links", str(wheelhouse),
                                "--python", sys.executable, "--quiet"],
                               cwd=self.root, capture_output=True, text=True)
        self.assertEqual(setup.returncode, 0, setup.stderr)
        result = subprocess.run(["uv", "run", "--directory", str(copied), "--no-sync",
                                 "python", "-B", str(copied / "scripts" / "generate_html.py"),
                                 str(self.layout)], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["questions"], 3)

    @unittest.skipUnless(os.environ.get("CLEW_TEST_BROWSER") == "1",
                         "Set CLEW_TEST_BROWSER=1 for local browser checks.")
    def test_browser_offline_file_and_interactions(self):
        from playwright.sync_api import sync_playwright
        self.test_methods_are_consumed_not_authored()
        self.modify(questions={})
        self.edit(self.sheet, "Worksheet introduction.", "Worksheet introduction. $x^2$.")
        self.course.write_text(self.course.read_text(encoding="utf-8") +
                               "\n$$\\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}$$\n",
                               encoding="utf-8")
        assets = self.root / "edited-assets"
        shutil.copytree(SKILL / "assets", assets)
        template = assets / "template.html"
        template.write_text(template.read_text(encoding="utf-8").replace(
            '<div data-slot="statement"></div>',
            '<div class="edited-layout"><div data-slot="statement"></div></div>'),
            encoding="utf-8")
        shutil.copyfile(SKILL / "LICENSE", self.root / "LICENSE")
        with patch("render_html.ASSETS", assets):
            generate(self.layout)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page()
            failures, requests = [], []
            page.on("pageerror", lambda error: failures.append(str(error)))
            page.route("http://**/*", lambda route: (requests.append(route.request.url), route.abort()))
            page.route("https://**/*", lambda route: (requests.append(route.request.url), route.abort()))
            page.goto((self.root / "publication.html").as_uri())
            page.wait_for_function("!!window.MathJax?.startup?.document")
            self.assertEqual(page.locator(".exercise").count(), 2)
            self.assertEqual(page.locator(".question").count(), 3)
            self.assertEqual(page.locator(".edited-layout").count(), 3)
            self.assertEqual(page.get_by_text("Worksheet introduction.", exact=False).count(), 1)
            page.wait_for_selector('#exercises > [data-slot="content"] mjx-container svg')
            back = page.get_by_role("button", name="Retour", exact=True)
            self.assertTrue(back.is_hidden())
            page.get_by_role("button", name="Commencer l'exercice").first.click()
            question = page.locator(".question").first
            question.get_by_role("button", name="Méthode", exact=True).click()
            self.assertTrue(page.locator("#panel-title").evaluate("node => node === document.activeElement"))
            page.go_back()
            page.wait_for_function("document.getElementById('panel-title').textContent === 'Aide contextuelle'")
            self.assertTrue(back.is_hidden())
            self.assertIn("Choisissez", page.locator("#panel-content").inner_text())
            page.go_forward()
            page.wait_for_function("document.getElementById('panel-title').textContent.startsWith('Méthode')")
            question.get_by_role("button", name="Indices", exact=True).click()
            self.assertEqual(page.locator("#panel-content .hint:not([hidden])").count(), 1)
            reveal = page.get_by_role("button", name="Révéler l'indice suivant")
            for width in (1280, 390):
                page.set_viewport_size({"width": width, "height": 844})
                hint_box = page.locator("#panel-content .hint:not([hidden])").bounding_box()
                button_box = reveal.bounding_box()
                self.assertGreaterEqual(button_box["y"] - hint_box["y"] - hint_box["height"], 12)
                self.assertLessEqual(button_box["x"] + button_box["width"], width)
            page.set_viewport_size({"width": 1280, "height": 844})
            page.locator("#panel-content").get_by_role("link", name="the geometric limit result").click()
            self.assertIn("Geometric limit result", page.locator("#panel-content").inner_text())
            page.go_back()
            page.wait_for_function("document.getElementById('panel-title').textContent.startsWith('Indices')")
            self.assertEqual(page.locator("#panel-content .hint:not([hidden])").count(), 1)
            self.assertTrue(page.locator("#panel-content").get_by_role(
                "link", name="the geometric limit result").evaluate("node => node === document.activeElement"))
            page.get_by_role("button", name="Révéler l'indice suivant").click()
            self.assertEqual(page.locator("#panel-content .hint:not([hidden])").count(), 2)
            page.go_forward()
            page.wait_for_function("document.getElementById('panel-title').textContent.includes('Geometric')")
            back.click()
            page.wait_for_function("document.getElementById('panel-title').textContent.startsWith('Indices')")
            self.assertEqual(page.locator("#panel-content .hint:not([hidden])").count(), 2)
            self.assertTrue(reveal.is_hidden())
            page.locator("#panel-content").get_by_role("link", name="the geometric limit result").click()
            self.assertIn("Geometric limit result", page.locator("#panel-content").inner_text())
            self.assertNotIn("Bounds", page.locator("#panel-content").inner_text())
            question.get_by_role("button", name="Afficher la correction").click()
            question.get_by_role("button", name="Explications").click()
            self.assertIn("supplied answer", page.locator("#panel-content").inner_text())
            page.locator("#panel-content").get_by_role("link", name="the theorem", exact=True).click()
            back.click()
            page.wait_for_function("document.getElementById('panel-title').textContent.startsWith('Explications')")
            self.assertIn("supplied answer", page.locator("#panel-content").inner_text())
            page.locator(".question").nth(1).get_by_role("button", name="Afficher la correction").click()
            self.assertEqual(page.locator(".correction:not([hidden])").count(), 1)
            self.assertEqual(page.locator(".question").nth(2).locator('[data-action="correction"]').count(), 0)
            page.set_viewport_size({"width": 390, "height": 844})
            question.get_by_role("button", name="Indices", exact=True).click()
            page.wait_for_selector("#panel-content mjx-container svg")
            page.locator("#panel-content").get_by_role("link", name="the geometric limit result").click()
            back.click()
            page.wait_for_function("document.getElementById('panel-title').textContent.startsWith('Indices')")
            self.assertEqual(page.locator("#panel-content .hint:not([hidden])").count(), 1)
            reveal.click()
            self.assertEqual(page.locator("#panel-content .hint:not([hidden])").count(), 2)
            self.assertEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
            self.assertTrue(page.locator("#error").is_hidden())
            self.assertFalse(failures, failures)
            self.assertFalse(requests, requests)
            browser.close()


if __name__ == "__main__":
    unittest.main()
