"""clew_finalize rebuilds exactly what the validator derives, and nothing else."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import clew_finalize
from tests import fixtures


class FinalizeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="clew-finalize-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        fixtures.minimal_course(self.root)

    def read(self, name: str) -> str:
        return (self.root / name).read_text(encoding="utf-8")

    def support(self, name: str) -> dict:
        return json.loads(self.read(f"courses/mechanics/support/{name}"))

    def finalize(self, **options) -> dict:
        return clew_finalize.finalize(self.root, "mechanics", **options)

    def test_reports_drift_without_writing(self):
        before = self.read("courses/mechanics/sections/average-speed.md")
        result = self.finalize(check=True)
        self.assertFalse(result["ok"])
        self.assertIn("courses/mechanics/sections/average-speed.md", result["changed"])
        self.assertEqual(before, self.read("courses/mechanics/sections/average-speed.md"))

    def test_finalizing_is_idempotent(self):
        self.assertTrue(self.finalize()["changed"])
        again = self.finalize()
        self.assertEqual(again["changed"], [])
        self.assertTrue(self.finalize(check=True)["ok"])

    def test_sequence_links_flatten_across_chapters(self):
        self.finalize()
        first = self.read("courses/mechanics/sections/average-speed.md")
        middle = self.read("courses/mechanics/sections/acceleration.md")
        last = self.read("courses/mechanics/sections/balanced-forces.md")
        self.assertIn("previous: null", first)
        self.assertIn('next: "[[courses/mechanics/sections/acceleration]]"', first)
        self.assertIn('previous: "[[courses/mechanics/sections/average-speed]]"', middle)
        self.assertIn('next: "[[courses/mechanics/sections/balanced-forces]]"', middle)
        self.assertIn("next: null", last)

    def test_every_reference_is_visible_in_the_body(self):
        self.finalize()
        body = self.read("courses/mechanics/sections/acceleration.md").split("---\n", 2)[2]
        for target in (
            "courses/mechanics/course",
            "courses/mechanics/chapters/motion",
            "courses/mechanics/sections/average-speed",
            "courses/mechanics/sections/balanced-forces",
            "courses/mechanics/sources/motion.pdf#page=2",
        ):
            self.assertIn(f"[[{target}", body)

    def test_section_refs_list_pages_and_index_refs_list_first_pages(self):
        self.finalize()
        section = self.read("courses/mechanics/sections/acceleration.md")
        self.assertIn('  - "[[courses/mechanics/sources/motion.pdf#page=2]]"', section)
        chapter = self.read("courses/mechanics/chapters/motion.md")
        self.assertIn('  - "[[courses/mechanics/sources/motion.pdf#page=1]]"', chapter)
        self.assertNotIn("page=2", chapter.split("---\n", 2)[1])

    def test_contents_follow_children_order(self):
        self.finalize()
        contents = self.read("courses/mechanics/course.md").split("## Contents", 1)[1]
        self.assertLess(contents.index("chapters/motion"), contents.index("chapters/forces"))
        self.assertIn("1. [[courses/mechanics/chapters/motion|Motion]]", contents)

    def test_omitted_sources_are_named_rather_than_linked(self):
        self.finalize()
        body = self.read("courses/mechanics/sections/balanced-forces.md")
        self.assertIn("Original not included: forces.pdf", body)
        self.assertIn("source_refs: []", body)
        self.assertNotIn("forces.pdf", self.read("courses/mechanics/sections/acceleration.md"))

    def test_source_hashes_and_page_counts_are_measured(self):
        path = self.root / "courses/mechanics/sources/motion.pdf"
        source_map = self.support("source-map.json")
        source_map["sources"][0]["sha256"] = "f" * 64
        source_map["sources"][0]["page_count"] = 9
        fixtures.write(self.root / "courses/mechanics/support/source-map.json",
                       json.dumps(source_map, indent=2) + "\n")
        self.finalize()
        rebuilt = self.support("source-map.json")["sources"][0]
        self.assertEqual(rebuilt["page_count"], 2)
        self.assertNotEqual(rebuilt["sha256"], "f" * 64)
        self.assertEqual(len(rebuilt["sha256"]), 64)
        self.assertTrue(path.is_file())

    def test_verification_covers_every_page_of_every_source(self):
        self.finalize()
        report = self.support("verification.json")
        pages = {(record["source_id"], record["page"]): record for record in report["pages"]}
        self.assertEqual(sorted(pages), [
            ("forces-handout", 1), ("motion-notes", 1), ("motion-notes", 2)])
        self.assertEqual(pages[("motion-notes", 1)]["section_ids"], ["mechanics.average-speed"])
        self.assertEqual(pages[("motion-notes", 1)]["status"], "mapped")
        self.assertIsNone(pages[("motion-notes", 1)]["reason"])
        self.assertEqual({record["id"] for record in report["sections"]}, {
            "mechanics.average-speed", "mechanics.acceleration", "mechanics.balanced-forces"})

    def test_unverified_sections_keep_an_honest_limitation(self):
        self.finalize()
        record = next(item for item in self.support("verification.json")["sections"]
                      if item["id"] == "mechanics.acceleration")
        self.assertEqual(record["fidelity"], "partial")
        self.assertTrue(record["limitations"])
        self.assertEqual(record["checks"], [])

    def test_verified_fidelity_without_checks_is_refused(self):
        path = self.root / "courses/mechanics/sections/acceleration.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "fidelity: partial", "fidelity: verified"), encoding="utf-8", newline="\n")
        with self.assertRaises(clew_finalize.FinalizeError) as caught:
            self.finalize()
        self.assertIn("verified", str(caught.exception))

    def test_authored_checks_survive_regeneration(self):
        self.finalize()
        report = self.support("verification.json")
        for record in report["sections"]:
            if record["id"] == "mechanics.acceleration":
                record["checks"] = ["Compared the derivation against page 2."]
        fixtures.write(self.root / "courses/mechanics/support/verification.json",
                       json.dumps(report, indent=2) + "\n")
        self.finalize()
        record = next(item for item in self.support("verification.json")["sections"]
                      if item["id"] == "mechanics.acceleration")
        self.assertEqual(record["checks"], ["Compared the derivation against page 2."])

    def test_hashes_describe_the_finalized_bytes(self):
        import hashlib

        self.finalize()
        report = self.support("verification.json")
        self.assertEqual(
            report["source_map_sha256"],
            hashlib.sha256(
                (self.root / "courses/mechanics/support/source-map.json").read_bytes()).hexdigest())
        record = next(item for item in report["sections"] if item["id"] == "mechanics.acceleration")
        self.assertEqual(
            record["markdown_sha256"],
            hashlib.sha256(
                (self.root / "courses/mechanics/sections/acceleration.md").read_bytes()).hexdigest())

    def test_authored_prose_is_preserved(self):
        path = self.root / "courses/mechanics/sections/acceleration.md"
        path.write_text(path.read_text(encoding="utf-8").rstrip()
                        + "\n\n## Worked example\n\nA car reaching $20\\ \\mathrm{m/s}$.\n",
                        encoding="utf-8", newline="\n")
        self.finalize()
        self.finalize()
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text.count("## Worked example"), 1)
        self.assertIn("$20\\ \\mathrm{m/s}$", text)
        self.assertEqual(text.count(clew_finalize.NAV_START), 1)

    def test_unknown_course_and_bad_keys_fail_loudly(self):
        for course in ("Mechanics", "../escape", "missing"):
            with self.subTest(course=course), self.assertRaises(clew_finalize.FinalizeError):
                clew_finalize.finalize(self.root, course)

    def test_cli_reports_drift_as_failure(self):
        quiet = io.StringIO()
        with contextlib.redirect_stdout(quiet):
            self.assertEqual(clew_finalize.main(
                ["--root", str(self.root), "--course", "mechanics", "--check"]), 1)
            self.assertEqual(clew_finalize.main(
                ["--root", str(self.root), "--course", "mechanics"]), 0)
            self.assertEqual(clew_finalize.main(
                ["--root", str(self.root), "--course", "mechanics", "--check"]), 0)

    @unittest.skipUnless(fixtures.validator_available(), "jsonschema is not installed")
    def test_finalized_course_satisfies_the_validator(self):
        self.finalize()
        report = fixtures.validate(self.root, "mechanics")
        self.assertEqual(report["errors"], [])
        self.assertTrue(report["ok"])


if __name__ == "__main__":
    unittest.main()
