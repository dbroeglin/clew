"""Small English synthetic worksheets; no private material or cloud calls."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".agents" / "skills" / "clew-enrich"
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from validate_enrich import EnrichError, Note, capture, validate
from runtime_fixtures import build_wheelhouse


class EnrichTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.chapter = self.root / "chapter"
        shutil.copytree(FIXTURES / "chapter", self.chapter)
        (self.chapter / "sources").mkdir()
        (self.chapter / "sources" / "original.md").write_text("Synthetic retained source.\n", encoding="utf-8")
        (self.chapter / "ingest.json").write_text("Untouched opaque Ingest record.\n", encoding="utf-8")
        self.before = self.root / "before.json"
        capture(self.chapter, self.before)
        shutil.copytree(FIXTURES / "enriched", self.chapter, dirs_exist_ok=True)

    def edit(self, relative, old, new):
        path = self.chapter / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")

    def test_small_representative_chapter_and_preservation(self):
        report = validate(self.chapter, self.before)
        self.assertEqual((report["questions"], report["supplied_answers"],
                          report["hints"], report["explanations"]), (4, 3, 6, 3))
        self.assertEqual(len(report["new_aids"]), 4)
        self.assertEqual(report["questions_without_correction"],
                         ["sequences-demo-exercises#^q-ex2-2"])
        self.assertLessEqual(sum(path.stat().st_size for path in FIXTURES.rglob("*.md")), 12_000)
        self.assertFalse(any(ord(char) > 127 for path in self.chapter.rglob("*.md")
                             for char in path.read_text(encoding="utf-8")))

    def test_source_changes_and_blank_line_losses_are_rejected(self):
        path = "exercices/sequences-demo-exercises.md"
        for old, new in [("u_n=7(2/5)^n", "u_n=8(2/5)^n"),
                         ("Justify each answer.", ""),
                         ("> 2. Determine", "> 3. Determine"),
                         ("> 2. Determine the limit of $(u_n)$.\n>\n",
                          "> 2. Determine the limit of $(u_n)$.\n")]:
            with self.subTest(new=new):
                original = (self.chapter / path).read_text(encoding="utf-8")
                self.edit(path, old, new)
                with self.assertRaisesRegex(EnrichError, "Supplied text/formatting changed"):
                    validate(self.chapter, self.before)
                (self.chapter / path).write_text(original, encoding="utf-8")

    def test_formula_indentation_and_frontmatter_are_preserved(self):
        self.edit("corriges/sequences-demo-corrections.md", ">    $$", "> $$")
        with self.assertRaisesRegex(EnrichError, "Supplied text/formatting changed"):
            validate(self.chapter, self.before)
        shutil.copyfile(FIXTURES / "enriched" / "corriges" / "sequences-demo-corrections.md",
                        self.chapter / "corriges" / "sequences-demo-corrections.md")
        self.edit("exercices/sequences-demo-exercises.md", "status: draft", "status: complete")
        with self.assertRaisesRegex(EnrichError, "frontmatter changed"):
            validate(self.chapter, self.before)

    def test_immutable_files_and_unexpected_new_files(self):
        for name in ["courses/sequences-demo-course.md", "index.md", "ingest.json", "sources/original.md"]:
            with self.subTest(name=name):
                path = self.chapter / name
                original = path.read_bytes()
                path.write_bytes(original + b"\nChanged.")
                with self.assertRaisesRegex(EnrichError, "Untouched file changed"):
                    validate(self.chapter, self.before)
                path.write_bytes(original)
        (self.chapter / "notes.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(EnrichError, "Only new Markdown aid notes"):
            validate(self.chapter, self.before)

    def test_original_file_removal_is_rejected(self):
        (self.chapter / "sources" / "original.md").unlink()
        with self.assertRaisesRegex(EnrichError, "Original files removed"):
            validate(self.chapter, self.before)

    def test_unexpected_empty_directory_is_rejected(self):
        (self.chapter / "unrelated").mkdir()
        with self.assertRaisesRegex(EnrichError, "Only new aid directories"):
            validate(self.chapter, self.before)

    def test_wrong_answer_question_association(self):
        self.edit("aides/ex1-q1.md", "#^r-ex1-1", "#^r-ex1-2")
        with self.assertRaisesRegex(EnrichError, "correction/question mismatch"):
            validate(self.chapter, self.before)

    def test_new_aid_cannot_be_silently_classified_as_another_role(self):
        self.edit("aides/ex1-q1.md", "type: help", "type: exercise")
        with self.assertRaisesRegex(EnrichError, "New aid note needs type: help"):
            validate(self.chapter, self.before)

    def test_explanation_cannot_invent_a_missing_answer(self):
        self.edit("aides/ex2-q2.md", "[!hint]", "[!explanation]")
        with self.assertRaisesRegex(EnrichError, "needs a supplied correction"):
            validate(self.chapter, self.before)

    def test_missing_ambiguous_and_imprecise_course_links(self):
        path = "aides/ex1-q1.md"
        for old, new, error in [
            ("#Geometric sequences", "#Missing", "Missing or ambiguous course heading"),
            ("#Geometric sequences", "", "needs a heading or block"),
            ("sequences-demo-course#", "absent#", "Missing or ambiguous note reference"),
        ]:
            with self.subTest(error=error):
                original = (self.chapter / path).read_text(encoding="utf-8")
                self.edit(path, old, new)
                with self.assertRaisesRegex(EnrichError, error):
                    validate(self.chapter, self.before)
                (self.chapter / path).write_text(original, encoding="utf-8")
        course = self.chapter / "courses" / "sequences-demo-course.md"
        course.write_text(course.read_text(encoding="utf-8") + "\n## Geometric sequences\n",
                          encoding="utf-8")
        second = self.root / "second.json"
        capture(self.chapter, second)
        with self.assertRaisesRegex(EnrichError, "ambiguous course heading"):
            validate(self.chapter, second)

    def test_code_does_not_count_as_a_course_reference(self):
        self.edit("aides/ex1-q1.md", "[[sequences-demo-course#Geometric sequences|geometric sequences]]",
                  "`[[sequences-demo-course#Geometric sequences|geometric sequences]]`")
        with self.assertRaisesRegex(EnrichError, "needs a precise course link"):
            validate(self.chapter, self.before)

    def test_wikilink_heading_can_contain_inline_mathematics(self):
        self.edit("courses/sequences-demo-course.md", "## Geometric sequences",
                  "## Geometric sequences $(u_n)$")
        self.edit("aides/ex1-q1.md", "#Geometric sequences|", "#Geometric sequences $(u_n)$|")
        baseline = self.root / "math-heading.json"
        capture(self.chapter, baseline)
        self.assertEqual(validate(self.chapter, baseline)["status"], "validated")

    def test_duplicate_ids_anchors_and_missing_question(self):
        path = "aides/ex1-q1.md"
        original = (self.chapter / path).read_text(encoding="utf-8")
        self.edit(path, "^explanation-1", "^hint-1")
        with self.assertRaisesRegex(EnrichError, "Duplicate anchor"):
            validate(self.chapter, self.before)
        (self.chapter / path).write_text(original, encoding="utf-8")
        self.edit(path, "id: sequences-demo-aid-ex1-1", "id: sequences-demo-aid-ex1-2")
        with self.assertRaisesRegex(EnrichError, "Duplicate learning-note IDs"):
            validate(self.chapter, self.before)
        (self.chapter / path).write_text(original, encoding="utf-8")
        self.edit(path, "#^q-ex1-1", "#^absent")
        with self.assertRaisesRegex(EnrichError, "Expected anchored question"):
            validate(self.chapter, self.before)

    def test_existing_anchored_notes_and_aids_are_preserved(self):
        second = self.root / "second.json"
        capture(self.chapter, second)
        self.assertEqual(validate(self.chapter, second)["new_aids"], [])
        self.edit("aides/ex1-q1.md", "Compare", "Compare carefully")
        with self.assertRaisesRegex(EnrichError, "Untouched file changed"):
            validate(self.chapter, second)
        shutil.copyfile(FIXTURES / "enriched" / "aides" / "ex1-q1.md",
                        self.chapter / "aides" / "ex1-q1.md")
        self.edit("exercices/sequences-demo-exercises.md", "Exercise 1 - Question 1",
                  "Different label")
        with self.assertRaisesRegex(EnrichError, "Existing block changed"):
            validate(self.chapter, second)

    def test_source_fields_survive_added_question_links(self):
        path = self.chapter / "corriges" / "sequences-demo-corrections.md"
        old = ('---\nid: solutions\ntype: correction\n---\n'
               '> [!reponse] Answer\n> [src:: original; pages 1]\n> Supplied text.\n>\n\n^answer\n\n')
        new = old.replace("[src:: original; pages 1]",
                          "[src:: original; pages 1] [question:: [[worksheet#^q]]]")
        self.assertEqual(Note(path, old, "correction").projection(),
                         Note(path, new, "correction").projection())
        self.assertNotEqual(Note(path, old, "correction").projection(),
                            Note(path, new.replace("pages 1", "pages 2"), "correction").projection())

    def test_existing_plain_block_anchor_is_reused(self):
        path = self.chapter / "exercices" / "sequences-demo-exercises.md"
        old = "1. Supplied question.\n\n^existing\n\nNext instruction.\n"
        new = "> [!question] Question\n> 1. Supplied question.\n\n^existing\n\nNext instruction.\n"
        self.assertEqual(Note(path, old, "exercise").projection(),
                         Note(path, new, "exercise").projection())

    def test_existing_unanchored_callout_label_is_preserved(self):
        chapter = self.root / "existing"
        (chapter / "exercices").mkdir(parents=True)
        path = chapter / "exercices" / "question.md"
        old = '> [!question] Original label\n> Supplied question.\n>\n'
        path.write_text(old, encoding="utf-8")
        baseline = self.root / "existing.json"
        capture(chapter, baseline)
        path.write_text(old + "\n^question\n\n", encoding="utf-8")
        self.assertEqual(validate(chapter, baseline)["questions"], 1)
        path.write_text((old + "\n^question\n\n").replace("Original label", "Changed label"),
                        encoding="utf-8")
        with self.assertRaisesRegex(EnrichError, "Existing unanchored callout changed"):
            validate(chapter, baseline)

    def test_capture_is_outside_chapter_exclusive_and_hidden_entries_excluded(self):
        with self.assertRaisesRegex(EnrichError, "outside the chapter"):
            capture(self.chapter, self.chapter / "before.json")
        with self.assertRaises(FileExistsError):
            capture(self.chapter, self.before)
        (self.chapter / ".obsidian").mkdir()
        (self.chapter / ".obsidian" / "config.json").write_text("not read", encoding="utf-8")
        self.assertEqual(validate(self.chapter, self.before)["status"], "validated")
        self.assertNotIn(".obsidian", self.before.read_text(encoding="utf-8"))

    def test_cli_failure_is_explicit_and_does_not_repair_notes(self):
        self.edit("aides/ex1-q1.md", "#Geometric sequences", "#Missing")
        before = {path: path.read_bytes() for path in self.chapter.rglob("*") if path.is_file()}
        result = subprocess.run([sys.executable, "-B", str(SKILL / "scripts" / "validate_enrich.py"),
                                 str(self.chapter), "--before", str(self.before)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Enrich error:", result.stderr)
        self.assertEqual(before, {path: path.read_bytes() for path in before})

    def test_copied_skill_without_repository_runtime(self):
        copied = self.root / "standalone"
        shutil.copytree(SKILL, copied, ignore=shutil.ignore_patterns("__pycache__"))
        exported = subprocess.run([
            "uv", "export", "--package", "clew-enrich", "--locked", "--no-dev",
            "--no-emit-project", "--no-hashes", "--format", "requirements-txt"],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(exported.returncode, 0, exported.stderr)
        wheelhouse = self.root / "wheels"
        build_wheelhouse(wheelhouse, exported.stdout)
        result = subprocess.run(["uv", "sync", "--offline", "--no-index", "--find-links",
                                 str(wheelhouse), "--python", sys.executable, "--quiet"],
                                cwd=copied, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for mode, baseline in [("--capture", self.root / "copied-before.json"),
                               ("--before", self.root / "copied-before.json")]:
            result = subprocess.run(["uv", "run", "--locked", "--no-sync", "python", "-B",
                                     str(copied / "scripts" / "validate_enrich.py"), str(self.chapter),
                                     mode, str(baseline)], cwd=copied, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(json.loads(result.stdout)["status"], {"captured", "validated"})


if __name__ == "__main__":
    unittest.main()
