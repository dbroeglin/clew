"""Prepared-document enrichment checks with synthetic notes only."""
from __future__ import annotations

import json
import os
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

from validate_enrich import EnrichError, capture, validate


class EnrichTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.chapter = self.root / "chapter"
        shutil.copytree(FIXTURES / "chapter", self.chapter)
        self.before = self.root / "before.json"
        capture(self.chapter, self.before)
        shutil.copytree(FIXTURES / "enriched", self.chapter, dirs_exist_ok=True)

    def test_prepared_documents_and_additive_aid(self):
        report = validate(self.chapter, self.before)
        self.assertEqual((report["documents"], report["questions"], report["supplied_answers"],
                          report["hints"], report["explanations"]), (3, 3, 2, 2, 1))
        self.assertEqual(report["new_aids"], ["aides/q-1.md"])
        self.assertEqual(report["questions_without_correction"], ["sheet#^q-3"])

    def test_imported_documents_preparation_record_and_retained_files_are_immutable(self):
        path = self.chapter / "Exercise-sheet" / "sheet.md"
        original = path.read_bytes()
        path.write_bytes(original + b"\nEdited source.")
        with self.assertRaisesRegex(EnrichError, "Original file changed"):
            validate(self.chapter, self.before)
        path.write_bytes(original)
        (self.chapter / ".clew" / "preparation.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(EnrichError, "Original file changed"):
            validate(self.chapter, self.before)

    def test_only_new_markdown_aids_are_allowed(self):
        path = self.chapter / "unrelated.txt"
        path.write_text("No.", encoding="utf-8")
        with self.assertRaisesRegex(EnrichError, "Only new Markdown aid notes"):
            validate(self.chapter, self.before)

    def test_existing_aids_are_immutable(self):
        path = self.chapter / "aides" / "existing-q-2.md"
        path.write_text(path.read_text(encoding="utf-8").replace("Start by", "Begin by"),
                        encoding="utf-8")
        with self.assertRaisesRegex(EnrichError, "Original file changed"):
            validate(self.chapter, self.before)

    def test_aid_question_and_supplied_answer_must_match(self):
        aid = self.chapter / "aides" / "q-1.md"
        text = aid.read_text(encoding="utf-8")
        aid.write_text(text.replace("solutions#^r-1", "solutions#^r-2"), encoding="utf-8")
        with self.assertRaisesRegex(EnrichError, "Aid correction/question mismatch"):
            validate(self.chapter, self.before)

    def test_course_links_must_resolve_to_precise_course_passages(self):
        aid = self.chapter / "aides" / "q-1.md"
        text = aid.read_text(encoding="utf-8")
        aid.write_text(text.replace("#Geometric limits", "#Absent"), encoding="utf-8")
        with self.assertRaisesRegex(EnrichError, "Missing or ambiguous course heading"):
            validate(self.chapter, self.before)
        aid.write_text(text.replace("[[course#Geometric limits|the geometric limit result]]",
                                    "`[[course#Geometric limits|the geometric limit result]]`"),
                       encoding="utf-8")
        with self.assertRaisesRegex(EnrichError, "Aid needs a precise course link"):
            validate(self.chapter, self.before)

    def test_legacy_chapter_is_rejected(self):
        legacy = self.root / "legacy"
        (legacy / "exercices").mkdir(parents=True)
        (legacy / "exercices" / "exercise.md").write_text(
            "---\nid: exercise\ntype: exercise\n---\n", encoding="utf-8")
        (legacy / "index.md").write_text(
            "---\nclew_schema: 1\nid: chapter\ntype: chapter\n---\n", encoding="utf-8")
        (legacy / ".clew").mkdir()
        (legacy / ".clew" / "preparation.json").write_text(
            '{"schema_version":1,"status":"complete","documents":[]}', encoding="utf-8")
        baseline = self.root / "legacy-before.json"
        with self.assertRaisesRegex(EnrichError, "no documents"):
            capture(legacy, baseline)

    def test_correction_answer_cannot_target_a_question_owned_by_another_exercise(self):
        chapter = self.root / "mismatch"
        shutil.copytree(FIXTURES / "chapter", chapter)
        exercise = chapter / "Exercise-sheet" / "sheet.md"
        text = exercise.read_text(encoding="utf-8")
        insertion = (
            "%% clew:unit exercise ex-2 %%\n\n## Exercise 2\n\nExercise ^ex-2\n\n"
            "> [!question] Question 1\n> 1. A question owned by another exercise.\n"
            "> [PDF p. 1](sheet.pdf#page=1)\n\n^other-q\n\n"
            "%% /clew:unit ex-2 %%\n\n"
        )
        text = text.replace("%% /clew:unit sec-sheet %%", insertion + "%% /clew:unit sec-sheet %%")
        exercise.write_text(text, encoding="utf-8")
        correction = chapter / "Correction-solutions" / "solutions.md"
        text = correction.read_text(encoding="utf-8").replace("#^q-2", "#^other-q")
        correction.write_text(text, encoding="utf-8")
        baseline = self.root / "mismatch-before.json"
        capture(chapter, baseline)
        with self.assertRaisesRegex(EnrichError, "disagree on exercise owner"):
            validate(chapter, baseline)

    def test_capture_requires_an_existing_external_path_and_refuses_replacement(self):
        with self.assertRaisesRegex(EnrichError, "outside the chapter"):
            capture(self.chapter, self.chapter / "before.json")
        with self.assertRaises(FileExistsError):
            capture(self.chapter, self.before)

    def test_unit_marker_lookalikes_inside_code_are_not_structure(self):
        chapter = self.root / "code-lookalike"
        shutil.copytree(FIXTURES / "chapter", chapter)
        course = chapter / "Course-course" / "course.md"
        course.write_text(
            course.read_text(encoding="utf-8") +
            "\n```text\n%% clew:unit exercise fake %%\n%% /clew:unit fake %%\n```\n",
            encoding="utf-8")
        baseline = self.root / "code-lookalike-before.json"
        capture(chapter, baseline)
        self.assertEqual(validate(chapter, baseline)["status"], "validated")

    def test_cli_failure_is_explicit_and_does_not_repair_notes(self):
        aid = self.chapter / "aides" / "q-1.md"
        aid.write_text(aid.read_text(encoding="utf-8").replace("#Geometric limits", "#Missing"),
                       encoding="utf-8")
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
        baseline = self.root / "copied-before.json"
        for mode, path in [("--capture", baseline), ("--before", baseline)]:
            result = subprocess.run(
                [sys.executable, "-B", str(copied / "scripts" / "validate_enrich.py"),
                 str(self.chapter), mode, str(path)],
                cwd=copied, capture_output=True, text=True, env=os.environ.copy())
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "captured" if mode == "--capture" else "validated")


if __name__ == "__main__":
    unittest.main()
