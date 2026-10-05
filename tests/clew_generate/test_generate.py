"""Local synthetic regression checks; no document or cloud service is used."""
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
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from generate_html import generate
from notes import GenerateError, Library, list_chapters
from publication import compile_layout, load_layout
from render_html import Renderer
from runtime_fixtures import build_wheelhouse


def fixture(root: Path) -> Path:
    course = root / "cours.md"
    course.write_text(
        '---\nid: cours\ntype: course\ntitle: "Algèbre"\n---\n'
        '# Sous-espace\n\nCritère $f+\\lambda g$.\n\n'
        '$$\\begin{pmatrix}1&0\\\\0&1\\end{pmatrix}$$\n\n'
        '## Exemple\n\nUne table :\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n'
        '![Figure](figure.png)\n\n[Source](original.pdf#page=2)\n',
        encoding="utf-8")
    (root / "figure.png").write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aO1cAAAAASUVORK5CYII="))
    (root / "original.pdf").write_bytes(b"%PDF-1.4\n")
    notes = [course.name]
    for number, count in [(1, 2), (2, 1), (3, 3)]:
        answer = [f'---\nid: corrige-{number}\ntype: correction\n'
                  f'exercises: ["[[ex-{number}]]"]\n---\n'
                  f'Shared correction context {number}.\n\n']
        filename = f"exercice-{number}.md"
        notes.append(filename)
        text = (f'---\nid: ex-{number}\ntype: exercise\ntitle: Exercice {number}\n'
                'courses: ["[[cours#Sous-espace]]"]\n---\n'
                f'Contexte commun {number}.\n\n')
        for question in range(1, count + 1):
            text += (f'<!-- clew-part:{question} -->\n'
                     f'> [!question] Question {question}\n'
                     '> [src:: feuille; pages 1]\n'
                     f'> Énoncé {number}-{question} : $x_{question}^2$.\n\n'
                     f'^q-{question}\n<!-- /clew-part:{question} -->\n\n')
            answer.append(f'> [!reponse] Réponse {question}\n'
                          f'> [src:: corrige-{number}; pages 1] [question:: [[ex-{number}#^q-{question}]]]\n'
                          f'> Correction {number}-{question} : $\\frac{{1}}{{2}}$.\n\n'
                          f'^r-{number}-{question}\n\n')
        (root / filename).write_text(text, encoding="utf-8")
        correction = f"corrige-{number}.md"
        (root / correction).write_text("".join(answer), encoding="utf-8")
        notes.append(correction)
    (root / "aides.md").write_text(
        '---\nid: aides\ntype: help\nquestion: "[[ex-1#^q-1]]"\n---\n'
        '> [!method]\n> Méthode distincte du corrigé.\n\n^methode\n\n'
        '> [!hint]\n> Premier indice $x$.\n\n^indice-1\n\n'
        '> [!hint]\n> Deuxième indice $y$.\n\n^indice-2\n\n'
        '> [!hint]\n> Troisième indice $z$.\n\n^indice-3\n',
        encoding="utf-8")
    notes.append("aides.md")
    layout = root / "layout.json"
    layout.write_text(json.dumps({"schema_version": 1, "title": "Algèbre",
                                 "notes": notes, "output": "publication.html"}),
                      encoding="utf-8")
    return layout


class GenerateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.layout = fixture(self.root)

    def model(self):
        layout, library = load_layout(self.layout)
        renderer = Renderer(library, Path(layout["output"]))
        model = compile_layout(layout, library, renderer)
        renderer.validate_links()
        return model

    def modify(self, **changes):
        data = json.loads(self.layout.read_text(encoding="utf-8"))
        data.update(changes)
        self.layout.write_text(json.dumps(data), encoding="utf-8")

    def test_six_questions_fidelity_and_optional_aids(self):
        model = self.model()
        self.assertEqual([e["address"] for e in model["exercises"]], ["ex-1", "ex-2", "ex-3"])
        self.assertEqual([q["address"] for q in model["questions"]],
                         ["ex-1#^q-1", "ex-1#^q-2", "ex-2#^q-1",
                          "ex-3#^q-1", "ex-3#^q-2", "ex-3#^q-3"])
        self.assertEqual([len(e["questions"]) for e in model["exercises"]], [2, 1, 3])
        self.assertEqual(len(model["questions"]), 6)
        self.assertEqual(len(model["questions"][0]["hints"]), 3)
        self.assertTrue(all(not q["hints"] for q in model["questions"][1:]))
        self.assertTrue(all(len(q["corrections"]) == 1 for q in model["questions"]))
        self.assertNotIn("src::", str(model))
        self.assertNotIn("clew-part:", str(model))
        self.assertIn("data:image/png;base64,", str(model))
        self.assertIn("original.pdf#page=2", str(model))

    def test_check_writes_nothing_and_output_is_deterministic(self):
        self.assertEqual(generate(self.layout, check=True)["status"], "checked")
        self.assertFalse((self.root / "publication.html").exists())
        generate(self.layout)
        first = (self.root / "publication.html").read_bytes()
        with self.assertRaisesRegex(GenerateError, "Output exists"):
            generate(self.layout)
        generate(self.layout, overwrite=True)
        self.assertEqual(first, (self.root / "publication.html").read_bytes())
        self.assertNotIn(b'<script src=', first)
        self.assertNotIn(b'<link ', first)

    def test_current_edits_are_used_without_ingest_record(self):
        path = self.root / "exercice-1.md"
        path.write_text(path.read_text(encoding="utf-8").replace("Énoncé 1-1", "Énoncé édité"),
                        encoding="utf-8")
        self.assertIn("Énoncé édité", self.model()["questions"][0]["html"])

    def question_range(self, number=1):
        lines = (self.root / "exercice-1.md").read_text(encoding="utf-8").splitlines()
        start = lines.index(f"> [!question] Question {number}") + 1
        end = lines.index(f"^q-{number}") + 1
        if end < len(lines) and lines[end] == f"<!-- /clew-part:{number} -->":
            end += 1
        return f"ex-1#L{start}-L{end}"

    def test_disjoint_question_selectors_group_by_exercise_and_source_order(self):
        self.modify(exercises=["ex-1#^q-2", "[[exercice-1#^q-1|First]]", "ex-2#^q-1"])
        model = self.model()
        self.assertEqual([e["address"] for e in model["exercises"]], ["ex-1", "ex-2"])
        self.assertEqual([len(e["questions"]) for e in model["exercises"]], [2, 1])
        self.assertEqual([q["address"] for q in model["questions"]],
                         ["ex-1#^q-1", "ex-1#^q-2", "ex-2#^q-1"])
        self.assertIn("Correction 1-1", model["questions"][0]["corrections"][0])
        self.assertNotIn("Correction 2-1", model["questions"][0]["corrections"][0])
        self.assertEqual(len(model["questions"][0]["hints"]), 3)

    def test_heading_and_range_containers_keep_internal_questions_and_context(self):
        path = self.root / "exercice-1.md"
        text = path.read_text(encoding="utf-8").replace("Contexte commun 1.", "## Container\n\nContexte commun 1.")
        text = text.replace("<!-- clew-part:2 -->", "Intermediate instruction.\n\n<!-- clew-part:2 -->")
        path.write_text(text, encoding="utf-8")
        start = text.splitlines().index("## Container") + 1
        for selector in ("ex-1#Container", f"ex-1#L{start}-L{len(text.splitlines())}"):
            with self.subTest(selector=selector):
                self.modify(exercises=[selector], questions={"ex-1#^q-2": {"hints": []}})
                model = self.model()
                self.assertEqual([q["address"] for q in model["questions"]],
                                 ["ex-1#^q-1", "ex-1#^q-2"])
                segments = model["exercises"][0]["segments"]
                self.assertIn("Contexte commun 1", segments[0]["html"])
                self.assertEqual(segments[1]["question"], "question-1")
                self.assertIn("Intermediate instruction", segments[2]["html"])
                self.assertEqual(segments[3]["question"], "question-2")
                self.assertEqual(len(model["exercises"]), 1)

    def test_question_range_uses_its_canonical_internal_address(self):
        self.modify(exercises=[self.question_range()],
                    questions={"ex-1#^q-1": {"hints": []}})
        model = self.model()
        self.assertEqual(model["questions"][0]["address"], "ex-1#^q-1")
        self.assertTrue(model["questions"][0]["corrections"])
        self.assertFalse(model["questions"][0]["hints"])

    def test_whole_child_alias_heading_and_range_overlaps_are_rejected(self):
        path = self.root / "exercice-1.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "Contexte commun 1.", "## Container\n\nContexte commun 1."), encoding="utf-8")
        cases = [
            ["ex-1", "ex-1#^q-1"],
            ["ex-1#^q-1", "exercice-1.md#^q-1"],
            ["ex-1#Container", "ex-1#^q-2"],
            [self.question_range(), "ex-1#^q-1"],
            ["ex-1", "[[exercice-1]]"],
        ]
        for selectors in cases:
            with self.subTest(selectors=selectors):
                self.modify(exercises=selectors)
                with self.assertRaisesRegex(GenerateError, "Duplicate/overlapping exercise selection"):
                    self.model()

    def test_disjoint_context_and_question_selections_keep_one_unit(self):
        path = self.root / "exercice-1.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "Contexte commun 1.", "Selected instructions.\n\n^instructions"), encoding="utf-8")
        self.modify(exercises=["ex-1#^q-2", "ex-1#^instructions", self.question_range()])
        model = self.model()
        self.assertEqual(len(model["exercises"]), 1)
        segments = model["exercises"][0]["segments"]
        self.assertIn("Selected instructions", segments[0]["html"])
        self.assertEqual([segment["question"] for segment in segments if "question" in segment],
                         ["question-1", "question-2"])
        self.modify(exercises=["ex-1#^instructions"])
        with self.assertRaisesRegex(GenerateError, "contains no questions"):
            self.model()

    def test_unit_link_resolves_when_only_internal_questions_are_selected(self):
        path = self.root / "exercice-1.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "Énoncé 1-1", "[[ex-1|Owning exercise]] : Énoncé 1-1"), encoding="utf-8")
        self.modify(exercises=["ex-1#^q-1"])
        self.assertIn("Owning exercise", self.model()["questions"][0]["html"])

    def test_correction_context_is_preserved_once_per_selected_unit(self):
        path = self.root / "corrige-1.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "[[ex-1#^q-2]]", "[[ex-1#^q-1]]"), encoding="utf-8")
        question = self.model()["questions"][0]
        self.assertEqual(len(question["corrections"]), 1)
        panel = question["corrections"][0]
        self.assertEqual(panel.count("Shared correction context 1."), 1)
        self.assertLess(panel.index("Shared correction context"), panel.index("Correction 1-1"))
        self.assertLess(panel.index("Correction 1-1"), panel.index("Correction 1-2"))

    def test_supplied_correction_variants_remain_separate_panels(self):
        variant = self.root / "variant.md"
        text = (self.root / "corrige-1.md").read_text(encoding="utf-8")
        variant.write_text(text.replace("id: corrige-1\n", "id: variant\n"), encoding="utf-8")
        data = json.loads(self.layout.read_text(encoding="utf-8"))
        self.modify(notes=[*data["notes"], variant.name])
        panels = self.model()["questions"][0]["corrections"]
        self.assertEqual(len(panels), 2)
        self.assertTrue(all(panel.count("Shared correction context 1.") == 1 for panel in panels))

    def test_unlinked_supplied_answer_is_warned_not_auto_matched(self):
        path = self.root / "corrige-2.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            " [question:: [[ex-2#^q-1]]]", ""), encoding="utf-8")
        self.modify(exercises=["ex-2"])
        report = generate(self.layout, check=True)
        self.assertIn("Unmatched supplied answer: corrige-2#^r-2-1", report["warnings"])
        self.assertFalse(self.model()["questions"][0]["corrections"])

    def test_empty_explicit_correction_cannot_create_an_empty_control(self):
        path = self.root / "corrige-1.md"
        path.write_text('---\nid: corrige-1\ntype: correction\nexercises: ["[[ex-1]]"]\n---\n',
                        encoding="utf-8")
        self.modify(questions={"ex-1#^q-1": {"corrections": ["corrige-1"]}})
        with self.assertRaisesRegex(GenerateError, "Empty correction selection"):
            self.model()

    def test_wrong_but_resolvable_correction_owner_is_rejected(self):
        path = self.root / "corrige-1.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "[[ex-1#^q-1]]", "[[ex-2#^q-1]]"), encoding="utf-8")
        with self.assertRaisesRegex(GenerateError, "different exercise than its correction unit"):
            self.model()

    def test_undeclared_correction_cannot_combine_exercise_owners(self):
        path = self.root / "corrige-1.md"
        text = path.read_text(encoding="utf-8").replace('exercises: ["[[ex-1]]"]\n', "")
        path.write_text(text.replace("[[ex-1#^q-2]]", "[[ex-2#^q-1]]"), encoding="utf-8")
        with self.assertRaisesRegex(GenerateError, "different exercise than its correction unit"):
            self.model()

    def test_explicit_correction_selector_must_belong_to_the_published_exercise(self):
        self.modify(questions={"ex-2#^q-1": {"corrections": ["corrige-1#^r-1-1"]}})
        with self.assertRaisesRegex(GenerateError, "belongs to another exercise"):
            self.model()
        self.modify(questions={"ex-1#^q-2": {"corrections": ["corrige-1#^r-1-1"]}})
        with self.assertRaisesRegex(GenerateError, "Correction/question mismatch"):
            self.model()

    def test_duplicate_unit_ids_cannot_be_hidden_by_filename_selectors(self):
        path = self.root / "duplicate.md"
        path.write_text("---\nid: ex-1\ntype: exercise\n---\nA different exercise.", encoding="utf-8")
        data = json.loads(self.layout.read_text(encoding="utf-8"))
        self.modify(notes=[*data["notes"], path.name], exercises=["exercice-1.md", "duplicate.md"])
        with self.assertRaisesRegex(GenerateError, "Duplicate learning-note IDs"):
            self.model()

    def test_template_tokens_in_content_are_not_expanded(self):
        self.modify(title="{{DATA}}")
        generate(self.layout)
        page = (self.root / "publication.html").read_text(encoding="utf-8")
        self.assertIn("<title>{{DATA}}</title>", page)
        self.assertIn('"title":"{{DATA}}"', page)

    def test_repeated_markup_is_owned_by_native_html_templates(self):
        template = (SKILL / "assets" / "template.html").read_text(encoding="utf-8")
        script = (SKILL / "assets" / "interaction.js").read_text(encoding="utf-8")
        for name in ("course", "exercise", "question", "course-link", "content",
                     "method", "hints", "hint", "correction"):
            self.assertIn(f'<template id="template-{name}">', template)
        self.assertNotIn("createElement", script)
        self.assertNotIn('<p class=', script)
        self.assertNotIn('<div>', script)
        self.assertIn('data-label-open="Afficher la correction"', template)

    def test_course_only_and_unnumbered_exercise(self):
        self.modify(exercises=[], courses=["cours"])
        self.assertEqual(len(self.model()["reading"]), 1)
        (self.root / "simple.md").write_text("Une seule question $x$.", encoding="utf-8")
        self.modify(notes=["simple.md"], courses=[], exercises=["simple"])
        model = self.model()
        self.assertEqual(len(model["questions"]), 1)
        self.assertEqual(model["exercises"][0]["context"], "")
        self.assertEqual(str(model).count("Une seule question"), 1)

    def chapter_fixture(self) -> Path:
        chapter = self.root / "vault" / "courses" / "PT" / "maths" / "algebre"
        chapter.mkdir(parents=True)
        for role in ("courses", "exercices", "corriges", "sources"):
            (chapter / role).mkdir()
        for filename, role in [("cours.md", "courses"), ("exercice-1.md", "exercices"),
                               ("exercice-2.md", "exercices"), ("exercice-3.md", "exercices"),
                               ("corrige-1.md", "corriges"), ("corrige-2.md", "corriges"),
                               ("corrige-3.md", "corriges")]:
            shutil.copyfile(self.root / filename, chapter / role / filename)
        for filename in ("figure.png", "original.pdf"):
            shutil.copyfile(self.root / filename, chapter / "courses" / filename)
        shutil.copyfile(self.root / "aides.md", chapter / "aides.md")
        (chapter / "index.md").write_text(
            '---\ntype: ingest\nid: algebre\ntitle: "Révision algèbre"\n---\n'
            '[[cours]]\n[[ex-1]]\n[[corrige-1]]\n[[corrige-2]]\n[[corrige-3]]\n', encoding="utf-8")
        (chapter / "ingest.json").write_text("Not consulted by Generate", encoding="utf-8")
        (chapter / "sources" / "document.md").write_text(
            "---\n: deliberately malformed frontmatter\n---\n", encoding="utf-8")
        (chapter / ".obsidian").mkdir()
        (chapter / ".obsidian" / "private.md").write_text("not a learning note", encoding="utf-8")
        for filename, value in [("exercice-1.md", 30), ("exercice-2.md", 10),
                                 ("exercice-3.md", 20)]:
            path = chapter / "exercices" / filename
            path.write_text(path.read_text(encoding="utf-8").replace(
                "type: exercise", f"type: exercise\norder: {value}"), encoding="utf-8")
        return chapter

    def test_discover_ingest_chapter_and_index_with_metadata_order(self):
        chapter = self.chapter_fixture()
        for selected in (chapter, chapter / "index.md"):
            library = Library([selected])
            self.assertEqual(len(library.notes), 8)
            self.assertEqual(library.chapters[0]["title"], "Révision algèbre")
            exercises = [note.id for note in library.notes if note.metadata.get("type") == "exercise"]
            self.assertEqual(exercises, ["ex-2", "ex-3", "ex-1"])
            self.assertFalse(any(note.path.parent.name == "sources" for note in library.notes))
        self.modify(notes=[str(chapter)])
        model = self.model()
        self.assertEqual([exercise["title"] for exercise in model["exercises"]],
                         ["Exercice 2", "Exercice 3", "Exercice 1"])
        self.assertTrue(all(len(question["corrections"]) == 1 for question in model["questions"]))
        generate(self.layout)

    def test_find_chapter_within_vault_without_publishing_entire_vault(self):
        chapter = self.chapter_fixture()
        vault = self.root / "vault"
        report = list_chapters(vault)
        self.assertEqual(report["chapters"], [{"root": str(chapter), "title": "Révision algèbre"}])
        self.assertEqual(report["omitted"], [])
        with self.assertRaisesRegex(GenerateError, "list-chapters"):
            Library([vault])
        limited = list_chapters(vault, depth=1)
        self.assertFalse(limited["chapters"])
        self.assertTrue(limited["omitted"])

    def test_course_only_topology_without_ingest_metadata(self):
        chapter = self.root / "simple-chapter"
        (chapter / "courses").mkdir(parents=True)
        (chapter / "courses" / "cours.md").write_text("# Cours\n\nTexte actuel.", encoding="utf-8")
        self.modify(notes=[str(chapter)])
        model = self.model()
        self.assertEqual(len(model["reading"]), 1)
        self.assertFalse(model["exercises"])

    def test_discovered_sections_follow_their_parent_and_inspector_reports_links(self):
        chapter = self.chapter_fixture()
        (chapter / "courses" / "section.md").write_text(
            '---\nid: section\ntype: section\norder: 1\ncourses: ["[[cours]]"]\n---\n'
            '## Section\n\nTexte.', encoding="utf-8")
        library = Library([chapter, chapter / "index.md"])
        courses = [note.id for note in library.notes
                   if note.metadata.get("type") in {"course", "section"}]
        self.assertEqual(courses, ["cours", "section"])
        result = subprocess.run(
            [sys.executable, "-B", str(SKILL / "scripts" / "inspect_notes.py"), str(chapter)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        section = next(note for note in report["notes"] if note["id"] == "section")
        self.assertEqual(section["relationships"]["courses"], ["[[cours]]"])
        self.assertEqual(section["order"], 1)
        result = subprocess.run(
            [sys.executable, "-B", str(SKILL / "scripts" / "inspect_notes.py"),
             str(self.root / "vault"), "--list-chapters"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["containers"][0]["chapters"]), 1)

    def test_plain_heading_and_block_overrides(self):
        (self.root / "simple.md").write_text("# Question\n\nCalculer $x$.\n\n^q\n",
                                           encoding="utf-8")
        self.modify(notes=["simple.md", "cours.md"], courses=["cours"],
                    exercises=["simple#^q"], questions={"simple#^q": {
                        "corrections": ["cours#Sous-espace"], "hints": ["cours#Exemple"]}})
        self.assertEqual(len(self.model()["questions"][0]["corrections"]), 1)

    def test_shared_context_stays_in_source_order_and_code_markers_survive(self):
        path = self.root / "exercice-1.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "<!-- clew-part:2 -->", "Instruction intermédiaire.\n\n<!-- clew-part:2 -->"),
            encoding="utf-8")
        segments = self.model()["exercises"][0]["segments"]
        self.assertIn("Contexte commun", segments[0]["html"])
        self.assertEqual(segments[1]["question"], "question-1")
        self.assertIn("Instruction intermédiaire", segments[2]["html"])
        self.assertEqual(segments[3]["question"], "question-2")
        path.write_text("```\n<!-- clew-part:1 -->\n> [!question]\n```\n", encoding="utf-8")
        library = Library([path])
        self.assertIn("clew-part:1", library.notes[0].select())
        self.assertNotIn("question", [part.kind for part in library.notes[0].parts])

    def test_internal_block_links_and_heading_links_within_whole_course(self):
        path = self.root / "cours.md"
        path.write_text(path.read_text(encoding="utf-8") +
                        "\nDéfinition importante.\n\n^definition\n\n"
                        "[[cours#^definition|Définition]] et [[cours#Exemple]].\n",
                        encoding="utf-8")
        model = self.model()
        self.assertIn('href="#note-1-XmRlZmluaXRpb24"', str(model))
        self.assertIn('id="note-1-XmRlZmluaXRpb24"', str(model))

    def test_errors_and_safe_source_html(self):
        self.modify(questions={"ex-1#^q-1": {"method": "absent"}})
        with self.assertRaisesRegex(GenerateError, "Missing or ambiguous"):
            self.model()
        self.modify(questions={"ex-1#^q-1": {"unknown": []}})
        with self.assertRaisesRegex(GenerateError, "Invalid question options"):
            self.model()
        self.modify(questions={})
        path = self.root / "exercice-1.md"
        path.write_text(path.read_text(encoding="utf-8").replace("Énoncé 1-1",
                        "<script>alert(1)</script>"), encoding="utf-8")
        self.assertNotIn("<script>", self.model()["questions"][0]["html"])

    def test_missing_svg_and_active_math_are_rejected(self):
        path = self.root / "cours.md"
        original = path.read_text(encoding="utf-8")
        for replacement, message in [("figure.svg", "Unsupported or invalid"),
                                     ("missing.png", "Missing figure")]:
            if replacement.endswith(".svg"):
                (self.root / replacement).write_text("<svg/>", encoding="utf-8")
            path.write_text(original.replace("figure.png", replacement), encoding="utf-8")
            with self.assertRaisesRegex(GenerateError, message):
                self.model()
        path.write_text(original + "\n$\\require{html}$\n", encoding="utf-8")
        with self.assertRaisesRegex(GenerateError, "externally loaded"):
            self.model()

    def test_unsafe_line_range_and_ambiguous_id(self):
        library = Library([self.root / "cours.md"])
        with self.assertRaisesRegex(GenerateError, "bisects"):
            library.notes[0].select("L18-L18")
        duplicate = self.root / "duplicate.md"
        duplicate.write_text("---\nid: cours\n---\nDuplicate", encoding="utf-8")
        library = Library([self.root / "cours.md", duplicate])
        with self.assertRaisesRegex(GenerateError, "ambiguous"):
            library.resolve("cours")

    def test_id_reference_resolution_does_not_restat_selected_notes(self):
        library = Library([self.root / "cours.md", self.root / "exercice-1.md"])
        with patch("notes.local_path", side_effect=AssertionError("unexpected filesystem access")):
            note, fragment = library.resolve("cours#Sous-espace", library.notes[1])
        self.assertEqual(note.id, "cours")
        self.assertEqual(fragment, "Sous-espace")

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
                                 "python", "-B", "scripts\\generate_html.py", str(self.layout)],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["questions"], 6)
        self.assertTrue((self.root / "publication.html").is_file())

    @unittest.skipUnless(os.environ.get("CLEW_TEST_BROWSER") == "1",
                         "Set CLEW_TEST_BROWSER=1 for local browser checks.")
    def test_browser_offline_file_and_interactions(self):
        from playwright.sync_api import sync_playwright
        self.modify(exercises=["ex-1#^q-2", "ex-1#^q-1", "ex-2", "ex-3"])
        assets = self.root / "edited-assets"
        shutil.copytree(SKILL / "assets", assets)
        template = assets / "template.html"
        markup = template.read_text(encoding="utf-8")
        markup = markup.replace(
            '<section class="question" data-slot="question">',
            '<article class="question" data-slot="question">').replace(
            "</section>\n</template>", "</article>\n</template>")
        markup = markup.replace('<div data-slot="statement"></div>',
                                '<div class="edited-layout"><div data-slot="statement"></div></div>')
        template.write_text(markup, encoding="utf-8")
        shutil.copyfile(SKILL / "LICENSE", self.root / "LICENSE")
        with patch("render_html.ASSETS", assets):
            generate(self.layout)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            page = browser.new_page()
            failures = []
            requests = []
            page.on("pageerror", lambda error: failures.append(str(error)))
            page.route("http://**/*", lambda route: (requests.append(route.request.url), route.abort()))
            page.route("https://**/*", lambda route: (requests.append(route.request.url), route.abort()))
            page.goto((self.root / "publication.html").as_uri())
            page.wait_for_function("!!window.MathJax?.startup?.document")
            self.assertEqual(page.locator("article.question .edited-layout").count(), 6)
            self.assertEqual(page.locator('[data-help="method"]').count(), 1)
            self.assertEqual(page.locator('[data-help="hints"]').count(), 1)
            self.assertEqual(page.locator(".exercise").count(), 3)
            page.get_by_role("button", name="Commencer l'exercice").first.click()
            self.assertEqual(page.locator(".exercise[open]").count(), 1)
            page.wait_for_selector(".exercise[open] mjx-container svg")
            page.get_by_role("button", name="Méthode", exact=True).click()
            page.get_by_role("heading", name="Méthode · Question 1").wait_for()
            self.assertTrue(page.get_by_role("heading", name="Méthode · Question 1").evaluate(
                "node => node === document.activeElement"))
            page.get_by_role("button", name="Indices", exact=True).click()
            page.wait_for_function("document.querySelectorAll('#panel-content .hint:not([hidden])').length === 1")
            reveal = page.get_by_role("button", name="Révéler l'indice suivant")
            reveal.click()
            self.assertEqual(page.locator("#panel-content .hint:not([hidden])").count(), 2)
            reveal.click()
            self.assertTrue(reveal.is_hidden())
            page.get_by_role("button", name="Indices", exact=True).click()
            self.assertEqual(page.locator("#panel-content .hint:not([hidden])").count(), 1)
            first = page.locator(".question").first.locator('[data-action="correction"]')
            first.click()
            self.assertEqual(page.locator(".correction:not([hidden])").count(), 1)
            self.assertEqual(first.get_attribute("aria-expanded"), "true")
            page.locator(".question").nth(1).get_by_role("button", name="Afficher la correction").click()
            self.assertEqual(page.locator(".correction:not([hidden])").count(), 1)
            self.assertEqual(first.get_attribute("aria-expanded"), "false")
            page.get_by_role("button", name="Masquer la correction").click()
            self.assertEqual(page.locator(".correction:not([hidden])").count(), 0)
            page.locator(".question").first.get_by_role("button", name="Cours · Sous-espace").first.click()
            page.wait_for_selector("#panel-content mjx-container svg")
            self.assertTrue(page.locator("#error").is_hidden())
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator(".question").first.get_by_role("button", name="Indices", exact=True).click()
            self.assertEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
            self.assertFalse(failures, failures)
            self.assertFalse(requests, requests)
            if os.environ.get("CLEW_TEST_SCREENSHOT"):
                page.screenshot(path=os.environ["CLEW_TEST_SCREENSHOT"], full_page=True)
            browser.close()


if __name__ == "__main__":
    unittest.main()
