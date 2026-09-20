"""Protect the compact learner-memory deployment and student runtime boundary."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class StudentSurfaceTests(unittest.TestCase):
    def test_only_vault_setup_is_local_runtime_code(self):
        files = {
            path.relative_to(ROOT / "src").as_posix()
            for path in (ROOT / "src").rglob("*.py")
        }
        self.assertEqual(files, {"vault/__init__.py", "vault/cli.py", "vault/storage.py"})
        self.assertFalse((ROOT / "requirements.txt").exists())

    def test_runtime_packages_share_one_immutable_revision(self):
        manifest = (ROOT / "apm.yml").read_text(encoding="utf-8")
        references = re.findall(
            r"francesco-kruk/clew-skills/([^\s#]+)#([0-9a-f]{40})\b", manifest
        )
        self.assertEqual(
            {path for path, _ in references},
            {"skills/course-content", "skills/learner-model"},
        )
        self.assertEqual(len(references), 2)
        self.assertEqual(len({revision for _, revision in references}), 1)

    def test_installed_learner_contract_uses_compact_memory(self):
        package = ROOT / ".agents" / "skills" / "learner-model"
        self.assertRegex(
            (package / "apm.yml").read_text(encoding="utf-8"),
            r"(?m)^version:\s*3\.0\.0\s*$",
        )
        specification = (
            package / "references" / "learner-model-spec.md"
        ).read_text(encoding="utf-8")
        self.assertIn("<!-- clew-learning-memory: v1 -->", specification)
        self.assertIn("model/learner.md", specification)
        self.assertFalse((package / "evals").exists())


if __name__ == "__main__":
    unittest.main()
