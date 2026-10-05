"""Synthetic stage handoffs; subprocesses isolate skill-local helper modules."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

import test_ingest as fixtures

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / ".agents" / "skills"


class PipelineTests(unittest.TestCase):
    def setUp(self):
        builder = fixtures.IngestTests()
        self.addCleanup(builder.doCleanups)
        builder.setUp()
        self.root = builder.root
        data = builder.headed_plan().model_dump()
        course = next(source for source in data["sources"] if source["id"] == "cours")
        path = Path(course["bundle"]) / "document.md"
        text = ("<!-- page: 1 -->\n\n# Course\n\n## Addition\n\n"
                "Addition of positive integers gives their sum, for example $1+1=2$.\n"
                "Doubling $x$ means adding it to itself: $2x=x+x$.\n")
        path.write_text(text, encoding="utf-8")
        course["fingerprint"] = fixtures.load_bundle(path.parent).fingerprint
        data["notes"][0]["parts"][0]["end"] = len(text.splitlines())
        self.chapter = Path(data["destination"])
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps(data), encoding="utf-8")
        self.sources = [Path(source["bundle"]) for source in data["sources"]]

    def stage(self, skill, script, *arguments):
        process = subprocess.run(
            [sys.executable, "-B", str(SKILLS / skill / "scripts" / script),
             *map(str, arguments)], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
        return json.loads(process.stdout)

    def publish(self, name):
        layout = self.root / f"{name}.json"
        output = self.root / f"{name}.html"
        layout.write_text(json.dumps({
            "schema_version": 1, "title": "Synthetic arithmetic",
            "notes": [str(self.chapter)], "output": str(output),
        }), encoding="utf-8")
        report = self.stage("clew-generate", "generate_html.py", layout)
        self.assertEqual((report["exercises"], report["questions"]), (2, 4))
        match = re.search(r'<script id="publication" type="application/json">(.*?)</script>',
                          output.read_text(encoding="utf-8"), re.S)
        self.assertIsNotNone(match)
        return json.loads(match[1])

    def test_native_units_work_before_and_after_optional_enrichment_without_producer_record(self):
        inspected = self.stage("clew-ingest", "inspect_bundles.py", *self.sources)
        self.assertEqual(len(inspected["bundles"]), 3)
        self.assertTrue(all("outline" in bundle for bundle in inspected["bundles"]))
        checked = self.stage("clew-ingest", "write_ingest.py", self.plan, "--check")
        self.assertEqual(len(checked["structure"]["units"]), 4)
        self.assertEqual(checked["issues"], [])
        written = self.stage("clew-ingest", "write_ingest.py", self.plan,
                             "--plan-sha256", checked["plan_sha256"])
        self.assertEqual(written["status"], "validated")
        self.assertEqual(self.stage("clew-ingest", "validate_ingest.py", self.chapter)["status"],
                         "validated")
        record = json.loads((self.chapter / "ingest.json").read_text(encoding="utf-8"))
        self.assertEqual((record["schema_version"], record["status"]), (3, "complete"))

        inventory = self.stage("clew-generate", "inspect_notes.py", self.chapter)
        units = [(note["id"], note["type"], note["blocks"]) for note in inventory["notes"]]
        self.assertEqual(len(units), 5)
        originals = {path: path.read_bytes() for path in self.chapter.rglob("*") if path.is_file()}
        before = self.publish("before")
        expected = [f"algebre-exercise-{unit}#^q-{question}"
                    for unit in (1, 2) for question in (1, 2)]
        self.assertEqual([question["address"] for question in before["questions"]], expected)
        self.assertEqual([exercise["address"] for exercise in before["exercises"]],
                         ["algebre-exercise-1", "algebre-exercise-2"])
        self.assertEqual([len(exercise["questions"]) for exercise in before["exercises"]], [2, 2])
        self.assertTrue(all(question["corrections"] for question in before["questions"]))
        self.assertTrue(all(not question["hints"] and not question["explanations"]
                            for question in before["questions"]))
        first = before["questions"][0]["corrections"][0]
        self.assertIn("Exercise 7", first)
        self.assertIn("Use the definitions", first)
        self.assertNotIn("Exercise 9", first)
        self.assertIn("BONUS", str(before["exercises"][1]["segments"]))

        baseline = self.root / "enrich-before.json"
        self.stage("clew-enrich", "validate_enrich.py", self.chapter, "--capture", baseline)
        aids = self.chapter / "aides"
        aids.mkdir()
        for unit in (1, 2):
            correction = (f'correction: "[[algebre-correction-{unit}#^r-1]]"\n'
                          if unit == 1 else "")
            explanation = ("\n> [!explanation]\n> The supplied answer adds the two given integers.\n"
                           "> See [[algebre-cours#Addition|the addition rule]].\n\n^explanation-1\n"
                           if unit == 1 else "")
            (aids / f"exercise-{unit}.md").write_text(
                f"---\nschema_version: 1\nid: aid-{unit}\ntype: help\n"
                f'question: "[[algebre-exercise-{unit}#^q-1]]"\n{correction}---\n\n'
                "> [!hint]\n> Use the two values in the statement and\n"
                "> [[algebre-cours#Addition|the addition rule]].\n\n^hint-1\n"
                + explanation, encoding="utf-8")
        enriched = self.stage("clew-enrich", "validate_enrich.py", self.chapter, "--before", baseline)
        self.assertEqual((enriched["questions"], enriched["supplied_answers"],
                          enriched["hints"], enriched["explanations"]), (4, 4, 2, 1))
        self.assertEqual(len(enriched["new_aids"]), 2)
        self.assertEqual(originals, {path: path.read_bytes() for path in originals})
        inventory = self.stage("clew-generate", "inspect_notes.py", self.chapter)
        self.assertEqual(units, [(note["id"], note["type"], note["blocks"])
                                 for note in inventory["notes"] if note["type"] != "help"])

        after = self.publish("after")
        self.assertEqual([question["address"] for question in after["questions"]], expected)
        self.assertEqual(before["exercises"], after["exercises"])
        self.assertEqual([question["corrections"] for question in before["questions"]],
                         [question["corrections"] for question in after["questions"]])
        self.assertEqual([len(question["hints"]) for question in after["questions"]], [1, 0, 1, 0])
        self.assertEqual([len(question["explanations"]) for question in after["questions"]], [1, 0, 0, 0])
        (self.chapter / "ingest.json").unlink()
        self.assertEqual(after, self.publish("without-record"))


if __name__ == "__main__":
    unittest.main()
