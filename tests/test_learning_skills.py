"""Check local skill packaging and evaluation inputs, not tutoring behavior."""

import json
import re
import runpy
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("study-plan", "synthesise", "active-recall", "repair-attempt")


class LearningSkillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validate = staticmethod(runpy.run_path(
            str(ROOT / ".agents/skills/skill-creator/scripts/quick_validate.py")
        )["validate_skill"])

    def test_local_skill_metadata_and_size(self):
        manifest = (ROOT / "apm.yml").read_text(encoding="utf-8")
        for name in SKILLS:
            with self.subTest(skill=name):
                directory = ROOT / ".agents/skills" / name
                valid, message = self.validate(directory)
                self.assertTrue(valid, message)
                text = (directory / "SKILL.md").read_text(encoding="utf-8")
                self.assertRegex(text, rf"(?m)^name: {re.escape(name)}$")
                self.assertLess(len(text.splitlines()), 500)
                self.assertNotIn(f"/skills/{name}#", manifest)

    def test_evaluation_definitions_and_fixture_paths(self):
        for name in SKILLS:
            with self.subTest(skill=name):
                data = json.loads((
                    ROOT / ".agents/skills" / name / "evals/evals.json"
                ).read_text(encoding="utf-8"))
                self.assertEqual(data["skill_name"], name)
                cases = data["evals"]
                self.assertGreaterEqual(len(cases), 3)
                ids = [case["id"] for case in cases]
                self.assertTrue(all(type(identity) is int for identity in ids))
                self.assertEqual(len(ids), len(set(ids)))
                for case in cases:
                    with self.subTest(case=case["id"]):
                        for key in ("prompt", "expected_output"):
                            self.assertIsInstance(case[key], str)
                            self.assertTrue(case[key].strip())
                        self.assertIsInstance(case["assertions"], list)
                        self.assertTrue(case["assertions"])
                        for assertion in case["assertions"]:
                            self.assertIsInstance(assertion, str)
                            self.assertTrue(assertion.strip())
                        self.assertIsInstance(case["files"], list)
                        for filename in case["files"]:
                            self.assertIsInstance(filename, str)
                            self.assertFalse(Path(filename).is_absolute())
                            target = (ROOT / filename).resolve()
                            self.assertTrue(target.is_relative_to(ROOT))
                            self.assertTrue(target.exists(), filename)
                        if "turns" in case:
                            self.assertIsInstance(case["turns"], list)
                            self.assertTrue(case["turns"])
                            for turn in case["turns"]:
                                self.assertIsInstance(turn, str)
                                self.assertTrue(turn.strip())

    def test_bundled_markdown_references_resolve(self):
        for name in SKILLS:
            directory = ROOT / ".agents/skills" / name
            for document in directory.rglob("*.md"):
                text = document.read_text(encoding="utf-8")
                for link in re.findall(r"\[[^\]\n]*\]\(([^)\s]+)\)", text):
                    if link.startswith("#") or "://" in link:
                        continue
                    with self.subTest(document=document, link=link):
                        target = (document.parent / unquote(link.split("#")[0])).resolve()
                        self.assertTrue(target.is_relative_to(ROOT))
                        self.assertTrue(target.exists(), link)

    def test_tutor_and_readme_expose_all_four_skills(self):
        tutor = (ROOT / ".github/agents/clew-tutor.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for name in SKILLS:
            with self.subTest(skill=name):
                self.assertIn(f"`{name}`", tutor)
                self.assertIn(f".agents/skills/{name}/SKILL.md", readme)


if __name__ == "__main__":
    unittest.main()
