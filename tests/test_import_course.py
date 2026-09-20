"""Importing published courses is additive, hash-guarded and confined to content."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import clew_finalize
from tests import fixtures

SCRIPT = ROOT / ".agents/skills/clew-import/scripts/import_course.py"


def load_script():
    specification = importlib.util.spec_from_file_location("clew_import_course", SCRIPT)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


importer = load_script()


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="clew-import-tests-")
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name).resolve()
        self.repository = fixtures.distribution_repo(base / "repository")
        for course in ("mechanics", "proportional-reasoning"):
            clew_finalize.finalize(self.repository, course)
        self.vault = base / "vault"
        self.vault.mkdir()

    def run_import(self, *courses, source=None, **options):
        return importer.import_courses(
            str(source or self.repository), list(courses), self.vault, **options)

    def read(self, relative: str) -> str:
        return (self.vault / relative).read_text(encoding="utf-8")

    def imports(self) -> dict:
        return json.loads(self.read(".clew/imports.json"))

    def test_importing_copies_the_course_and_the_concepts_it_grounds(self):
        result = self.run_import("mechanics")
        self.assertEqual(result["source_kind"], "directory")
        for relative in (
            "courses/mechanics/course.md",
            "courses/mechanics/sections/average-speed.md",
            "courses/mechanics/support/source-map.json",
            "courses/mechanics/sources/mechanics.pdf",
            "concepts/math-ratios.md",
            "concepts/physics-average-speed.md",
        ):
            self.assertTrue((self.vault / relative).is_file(), relative)
        self.assertFalse((self.vault / "courses/proportional-reasoning").exists())

    def test_pdf_bytes_survive_the_copy(self):
        self.run_import("mechanics")
        self.assertEqual(
            (self.vault / "courses/mechanics/sources/mechanics.pdf").read_bytes(),
            (self.repository / "courses/mechanics/sources/mechanics.pdf").read_bytes())

    def test_evidence_is_filtered_to_what_the_vault_can_resolve(self):
        self.run_import("mechanics")
        ratios = self.read("concepts/math-ratios.md")
        self.assertIn("[[courses/mechanics/sections/average-speed]]", ratios)
        self.assertNotIn("proportional-reasoning", ratios)
        self.assertEqual(ratios.count("## Evidence"), 1)

    def test_a_later_course_merges_its_evidence_back(self):
        self.run_import("mechanics")
        self.run_import("proportional-reasoning")
        ratios = self.read("concepts/math-ratios.md")
        for target, title in (
            ("courses/mechanics/sections/average-speed", "Average speed"),
            ("courses/proportional-reasoning/sections/ratios-basics", "Reading a ratio"),
        ):
            self.assertIn(f'  - "[[{target}]]"', ratios)
            self.assertIn(f"- [[{target}|{title}]]", ratios)
        self.assertEqual(ratios.count("## Evidence"), 1)
        self.assertEqual(self.imports()["courses"][0]["course_path"], "courses/mechanics")
        self.assertEqual(len(self.imports()["courses"]), 2)

    def test_both_orders_of_import_agree(self):
        self.run_import("mechanics")
        self.run_import("proportional-reasoning")
        together = Path(self.temporary.name).resolve() / "together"
        together.mkdir()
        importer.import_courses(str(self.repository),
                                ["mechanics", "proportional-reasoning"], together)
        self.assertEqual(
            self.read("concepts/math-ratios.md"),
            (together / "concepts/math-ratios.md").read_text(encoding="utf-8"))

    def test_a_concept_reached_through_relations_must_also_be_satisfiable(self):
        with self.assertRaises(importer.ImportFailure) as caught:
            self.run_import("proportional-reasoning")
        message = str(caught.exception)
        self.assertIn("concepts/physics-average-speed.md has no evidence", message)
        self.assertIn("Add one of these courses: mechanics", message)
        self.assertEqual(list(self.vault.iterdir()), [])

    def test_import_records_provenance_and_hashes(self):
        self.run_import("mechanics")
        entry = self.imports()["courses"][0]
        self.assertEqual(entry["schema"] if "schema" in entry else "clew-imports/v1",
                         "clew-imports/v1")
        self.assertEqual(entry["course_id"], "course.mechanics")
        self.assertEqual(entry["source_kind"], "directory")
        self.assertIn("concepts/math-ratios.md", entry["concepts"])
        import hashlib

        for relative, recorded in entry["files"].items():
            self.assertEqual(
                hashlib.sha256((self.vault / relative).read_bytes()).hexdigest(), recorded)
        self.assertNotIn("concepts/math-ratios.md", entry["files"])

    def test_dry_run_writes_nothing(self):
        result = self.run_import("mechanics", dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["written"])
        self.assertEqual(list(self.vault.iterdir()), [])

    def test_reimport_refuses_to_discard_local_edits(self):
        self.run_import("mechanics")
        target = self.vault / "courses/mechanics/sections/acceleration.md"
        target.write_text(target.read_text(encoding="utf-8") + "\nMy own note.\n",
                          encoding="utf-8", newline="\n")
        with self.assertRaises(importer.ImportFailure) as caught:
            self.run_import("mechanics")
        self.assertIn("acceleration.md (modified)", str(caught.exception))
        self.run_import("mechanics", force=True)
        self.assertNotIn("My own note.", self.read("courses/mechanics/sections/acceleration.md"))

    def test_reimport_notices_added_and_missing_files(self):
        self.run_import("mechanics")
        fixtures.write(self.vault / "courses/mechanics/sections/mine.md", "---\n---\n\n# Mine\n")
        (self.vault / "courses/mechanics/sections/acceleration.md").unlink()
        with self.assertRaises(importer.ImportFailure) as caught:
            self.run_import("mechanics")
        self.assertIn("mine.md (added)", str(caught.exception))
        self.assertIn("acceleration.md (missing)", str(caught.exception))

    def test_reimport_removes_files_the_producer_deleted(self):
        self.run_import("mechanics")
        removed = "courses/mechanics/sections/balanced-forces.md"
        chapter = self.repository / "courses/mechanics/chapters/forces.md"
        (self.repository / removed).unlink()
        chapter.unlink()
        entry = self.repository / "courses/mechanics/course.md"
        entry.write_text(entry.read_text(encoding="utf-8").replace(
            '  - "[[courses/mechanics/chapters/forces]]"\n', ""), encoding="utf-8", newline="\n")
        self.trim_source_map("mechanics", "course.mechanics.balanced-forces")
        clew_finalize.finalize(self.repository, "mechanics")
        self.run_import("mechanics")
        self.assertFalse((self.vault / removed).exists())
        self.assertFalse((self.vault / "courses/mechanics/chapters/forces.md").exists())

    def trim_source_map(self, course: str, identity: str) -> None:
        path = self.repository / f"courses/{course}/support/source-map.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["sections"] = [item for item in data["sections"] if item["id"] != identity]
        data["sources"][0]["page_count"] = len(data["sections"])
        fixtures.write(path, json.dumps(data, indent=2) + "\n")

    def test_an_unmanaged_course_directory_is_never_overwritten(self):
        fixtures.write(self.vault / "courses/mechanics/course.md", "---\n---\n\n# Mine\n")
        with self.assertRaises(importer.ImportFailure) as caught:
            self.run_import("mechanics")
        self.assertIn("was not imported by Clew", str(caught.exception))

    def test_files_outside_the_fixed_layout_are_refused(self):
        fixtures.write(self.repository / "courses/mechanics/notes.txt", "hello")
        with self.assertRaises(importer.ImportFailure) as caught:
            self.run_import("mechanics")
        self.assertIn("outside the fixed course layout", str(caught.exception))
        self.assertFalse((self.vault / "courses").exists())

    def test_symlinks_are_refused(self):
        link = self.repository / "courses/mechanics/sections/elsewhere.md"
        link.symlink_to(self.repository / "courses/mechanics/course.md")
        with self.assertRaises(importer.ImportFailure) as caught:
            self.run_import("mechanics")
        self.assertIn("symlink", str(caught.exception).lower())

    def test_unsatisfiable_concept_evidence_names_the_missing_course(self):
        fixtures.concept(
            self.repository, "proportion-model", "Proportion model",
            "A model of two quantities scaling together.",
            "Two quantities are proportional when their ratio is constant.",
            [fixtures.RATIOS_BASICS])
        path = self.repository / "concepts/math-ratios.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            '  - "[[concepts/physics-average-speed]]"',
            '  - "[[concepts/physics-average-speed]]"\n  - "[[concepts/proportion-model]]"',
        ).replace("- [[concepts/physics-average-speed]]",
                  "- [[concepts/physics-average-speed]]\n- [[concepts/proportion-model]]"),
            encoding="utf-8", newline="\n")
        with self.assertRaises(importer.ImportFailure) as caught:
            self.run_import("mechanics")
        message = str(caught.exception)
        self.assertIn("concepts/proportion-model.md has no evidence", message)
        self.assertIn("proportional-reasoning", message)

    def test_a_redefined_concept_stops_the_import(self):
        self.run_import("mechanics")
        self.redefine_vault_concept()
        with self.assertRaises(importer.ImportFailure) as caught:
            self.run_import("proportional-reasoning")
        self.assertIn("different definition", str(caught.exception))

    def test_keep_and_replace_both_merge_evidence(self):
        self.run_import("mechanics")
        self.redefine_vault_concept()
        self.run_import("proportional-reasoning", policy="keep")
        kept = self.read("concepts/math-ratios.md")
        self.assertIn("My own wording of a ratio.", kept)
        self.assertIn("[[courses/proportional-reasoning/sections/ratios-basics]]", kept)

        self.setUp()
        self.run_import("mechanics")
        self.redefine_vault_concept()
        self.run_import("proportional-reasoning", policy="replace")
        replaced = self.read("concepts/math-ratios.md")
        self.assertNotIn("My own wording of a ratio.", replaced)
        self.assertIn("[[courses/mechanics/sections/average-speed]]", replaced)
        self.assertIn("[[courses/proportional-reasoning/sections/ratios-basics]]", replaced)

    def redefine_vault_concept(self) -> None:
        path = self.vault / "concepts/math-ratios.md"
        text = path.read_text(encoding="utf-8")
        start = text.index("## Definition")
        end = text.index("## ", start + 3)
        path.write_text(text[:start] + "## Definition\n\nMy own wording of a ratio.\n\n"
                        + text[end:], encoding="utf-8", newline="\n")

    def test_git_sources_are_fetched_shallowly(self):
        bare = Path(self.temporary.name).resolve() / "published.git"
        subprocess.run(["git", "init", "--quiet", "-b", "main", str(self.repository)],
                       check=True, capture_output=True)
        for command in (
            ["add", "-A"],
            ["-c", "user.email=t@example.com", "-c", "user.name=Teacher",
             "commit", "--quiet", "-m", "Publish courses"],
        ):
            subprocess.run(["git", "-C", str(self.repository), *command],
                           check=True, capture_output=True)
        subprocess.run(["git", "clone", "--bare", "--quiet", str(self.repository), str(bare)],
                       check=True, capture_output=True)
        result = self.run_import("mechanics", source=bare)
        self.assertEqual(result["source_kind"], "git")
        self.assertRegex(result["commit"], r"^[0-9a-f]{40}$")
        self.assertTrue((self.vault / "courses/mechanics/course.md").is_file())
        self.assertFalse((self.vault / "courses/proportional-reasoning").exists())

    def test_reserved_learner_paths_are_never_written(self):
        self.run_import("mechanics", "proportional-reasoning")
        self.assertEqual(
            sorted(item.name for item in self.vault.iterdir()),
            [".clew", "concepts", "courses"])

    @unittest.skipUnless(fixtures.validator_available(), "jsonschema is not installed")
    def test_the_imported_vault_validates(self):
        self.run_import("mechanics")
        report = fixtures.validate(self.vault, "mechanics")
        self.assertEqual(report["errors"], [])
        self.assertIn("concepts/math-ratios.md", report["scope"]["concepts"])

    @unittest.skipUnless(fixtures.validator_available(), "jsonschema is not installed")
    def test_both_courses_validate_after_a_shared_import(self):
        self.run_import("mechanics", "proportional-reasoning")
        for course in ("mechanics", "proportional-reasoning"):
            with self.subTest(course=course):
                self.assertEqual(fixtures.validate(self.vault, course)["errors"], [])


if __name__ == "__main__":
    unittest.main()
