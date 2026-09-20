"""Check that the example vault stays a publishable, importable course repository.

The example is the only end-to-end artefact in the repository: it is what a
producer's output looks like and what a learner imports. These tests fail when
the committed content drifts away from what the generator, the finalizer, the
validator and the import script agree on.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import fixtures

VAULT = ROOT / "examples" / "reader-vault"
COURSES = ("mechanics", "proportional-reasoning")
IMPORT = ROOT / ".agents" / "skills" / "clew-import" / "scripts" / "import_course.py"


def run(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *arguments], cwd=ROOT,
                          capture_output=True, text=True)


class ExampleVaultTest(unittest.TestCase):
    def test_courses_are_finalized(self):
        """The committed notes match what clew_finalize.py would write."""
        for course in COURSES:
            with self.subTest(course=course):
                done = run(str(ROOT / "scripts" / "clew_finalize.py"),
                           "--root", str(VAULT), "--course", course, "--check")
                self.assertEqual(done.returncode, 0, done.stderr)
                report = json.loads(done.stdout)
                self.assertEqual(report["changed"], [])
                self.assertTrue(report["ok"])

    def test_shared_concept_spans_both_courses(self):
        """The example demonstrates the collision the import script reconciles."""
        text = (VAULT / "concepts" / "math-ratios.md").read_text(encoding="utf-8")
        for course in COURSES:
            self.assertIn(f"courses/{course}/sections/", text)

    def test_sources_are_reproducible(self):
        """Regenerating the sources leaves the committed PDFs byte for byte."""
        before = {path: path.read_bytes() for path in VAULT.rglob("*.pdf")}
        self.assertTrue(before)
        done = run(str(ROOT / "examples" / "make_reader_vault_sources.py"))
        self.assertEqual(done.returncode, 0, done.stderr)
        for path, data in before.items():
            with self.subTest(path=path.name):
                self.assertEqual(path.read_bytes(), data)

    @unittest.skipUnless(fixtures.validator_available(), "jsonschema is not installed")
    def test_courses_pass_strict_validation(self):
        for course in COURSES:
            with self.subTest(course=course):
                report = fixtures.validate(VAULT, course, strict=True)
                self.assertEqual(report["errors"], [])
                self.assertTrue(report["ok"])

    @unittest.skipUnless(fixtures.validator_available(), "jsonschema is not installed")
    def test_import_produces_a_valid_vault(self):
        """A learner importing both courses gets content the validator accepts."""
        vault = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, vault, ignore_errors=True)
        done = run(str(IMPORT), "--source", str(VAULT), "--vault", str(vault),
                   *[argument for course in COURSES for argument in ("--course", course)])
        self.assertEqual(done.returncode, 0, done.stderr)
        for course in COURSES:
            with self.subTest(course=course):
                report = fixtures.validate(vault, course, strict=True)
                self.assertEqual(report["errors"], [])
        for path in VAULT.rglob("*.pdf"):
            copied = vault / path.relative_to(VAULT)
            self.assertEqual(copied.read_bytes(), path.read_bytes())
        record = json.loads((vault / ".clew" / "imports.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["course_path"] for entry in record["courses"]],
                         [f"courses/{name}" for name in COURSES])

    @unittest.skipUnless(fixtures.validator_available(), "jsonschema is not installed")
    def test_importing_one_course_narrows_shared_evidence(self):
        """Evidence pointing into a course left behind is dropped, not dangling."""
        vault = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, vault, ignore_errors=True)
        done = run(str(IMPORT), "--source", str(VAULT), "--vault", str(vault),
                   "--course", "mechanics")
        self.assertEqual(done.returncode, 0, done.stderr)
        text = (vault / "concepts" / "math-ratios.md").read_text(encoding="utf-8")
        self.assertIn("courses/mechanics/sections/average-speed", text)
        self.assertNotIn("courses/proportional-reasoning/", text)
        self.assertEqual(fixtures.validate(vault, "mechanics", strict=True)["errors"], [])


if __name__ == "__main__":
    unittest.main()
