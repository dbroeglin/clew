import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.vault import cli, storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="clew-test-")
        self.root = Path(self.temporary.name)
        self.config = self.root / "clone" / ".clew.local.json"
        self.config.parent.mkdir()
        self.patches = [
            patch.object(storage, "ROOT", self.config.parent),
            patch.object(storage, "CONFIG", self.config),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(lambda: [item.stop() for item in self.patches])

    def test_requires_explicit_external_vault(self):
        with self.assertRaises(storage.VaultError):
            storage.vault_path()
        for invalid in [self.config.parent, self.root, Path("relative")]:
            with self.subTest(invalid=invalid), self.assertRaises(storage.VaultError):
                storage.vault_path(invalid)

    def test_configuration_does_not_create_model_content(self):
        vault = self.root / "external vault"
        vault.mkdir()
        result = storage.configure(vault)
        self.assertEqual(result["vault"], str(vault.resolve()))
        self.assertFalse((vault / "model").exists())
        self.assertFalse((vault / "artifacts").exists())
        self.assertFalse((vault / ".git").exists())

    def test_git_privacy_and_tracked_conflict(self):
        vault = self.root / "versioned-vault"
        vault.mkdir()
        subprocess.run(["git", "init", "--quiet", str(vault)], check=True)
        (vault / ".gitignore").write_text("keep-me\n", encoding="utf-8")
        storage.configure(vault)
        self.assertIn("keep-me\n", (vault / ".gitignore").read_text(encoding="utf-8"))
        self.assertIn("/model/", (vault / ".gitignore").read_text(encoding="utf-8"))
        (vault / "model").mkdir()
        (vault / "model" / "private.md").write_text("original", encoding="utf-8")
        subprocess.run(["git", "-C", str(vault), "add", "-f", "model"], check=True)
        with self.assertRaisesRegex(storage.VaultError, "already tracked"):
            storage.configure(vault)

    def test_malformed_settings_fail_without_rewriting(self):
        for content in ["[]", "{bad", '{"version":2,"vault":"x"}', '{"vault":"x"}']:
            self.config.write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(storage.VaultError):
                storage.status()
            self.assertEqual(self.config.read_text(encoding="utf-8"), content)

    def test_status_is_read_only(self):
        vault = self.root / "existing vault"
        vault.mkdir()
        storage.configure(vault)
        subprocess.run(["git", "init", "--quiet", str(vault)], check=True)
        result = storage.status()
        self.assertEqual(result["git"]["ignore_rules_missing"], ["/model/", "/artifacts/"])
        self.assertFalse((vault / ".gitignore").exists())

    def test_reserved_paths_are_reported_not_adopted(self):
        vault = self.root / "existing vault"
        vault.mkdir()
        (vault / "Model").write_bytes(b"teacher file")
        (vault / "artifacts").mkdir()
        (vault / "artifacts" / "example.md").write_bytes(b"original")
        result = storage.configure(vault)
        self.assertEqual(result["existing_private_paths"], ["Model", "artifacts"])
        self.assertTrue(result["warnings"])
        self.assertEqual((vault / "Model").read_bytes(), b"teacher file")
        self.assertEqual((vault / "artifacts" / "example.md").read_bytes(), b"original")

    def test_cli_json_and_nonzero_absent_config(self):
        with contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(cli.main(["status"]), 1)
        self.assertIn("configure", error.getvalue())
        vault = self.root / "my vault"
        vault.mkdir()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(["configure", "--vault", str(vault)]), 0)
        self.assertEqual(json.loads(output.getvalue())["vault"], str(vault.resolve()))


if __name__ == "__main__":
    unittest.main()
