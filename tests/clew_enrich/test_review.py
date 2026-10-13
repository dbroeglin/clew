"""Scratch proposal and exact-content verification with synthetic chapters."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SKILL = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "clew-enrich"
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(SKILL / "scripts"))

from review_enrich import review, verify_approved
from validate_enrich import EnrichError, capture, inventory, sha256


class ReviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.chapter = self.root / "chapter"
        shutil.copytree(FIXTURES / "chapter", self.chapter)
        self.before = self.root / "before.json"
        capture(self.chapter, self.before)
        self.drafts = self.root / "drafts"
        self.drafts.mkdir()
        self.aid = self.drafts / "q-1.md"
        shutil.copyfile(FIXTURES / "enriched" / "aides" / "q-1.md", self.aid)
        self.proposal = self.root / "proposal.md"

    def create_proposal(self):
        return review(self.chapter, self.before, [self.drafts], self.proposal)

    def persist(self):
        shutil.copyfile(self.aid, self.chapter / "aides" / self.aid.name)

    def test_review_preserves_chapter_and_emits_exact_content_mappings_and_hashes(self):
        before = inventory(self.chapter)
        baseline_bytes = self.before.read_bytes()
        result = self.create_proposal()
        self.assertEqual(result["status"], "drafts-validated")
        self.assertEqual(result["questions_without_aid"], ["exercise-document#^q-3"])
        self.assertEqual(inventory(self.chapter), before)
        self.assertEqual(self.before.read_bytes(), baseline_bytes)
        manifest = json.loads(self.proposal.with_suffix(".json").read_text(encoding="utf-8"))
        detail = manifest["aid_details"][0]
        self.assertEqual(detail["source"], str(self.aid))
        self.assertEqual(detail["path"], "aides/q-1.md")
        self.assertEqual(detail["sha256"], sha256(self.aid.read_bytes()))
        self.assertEqual((detail["hints"], detail["explanations"]), (1, 1))
        self.assertEqual((manifest["new_hints"], manifest["new_explanations"],
                          manifest["new_aids_with_explanations"], manifest["new_hint_only_aids"]),
                         (1, 1, 1, 0))
        self.assertIn("Exercise 1 - question 1", detail["question"])
        self.assertEqual(len(detail["course_links"]), 2)
        self.assertIn(self.aid.read_text(encoding="utf-8"), self.proposal.read_text(encoding="utf-8"))
        self.assertEqual(sha256(self.proposal.read_bytes()), result["proposal_sha256"])

    def test_approved_persisted_bytes_and_original_baseline_are_verified(self):
        result = self.create_proposal()
        self.persist()
        report = verify_approved(self.chapter, self.before, self.proposal, result["manifest_sha256"])
        self.assertTrue(report["approved_bytes_identical"])

    def test_combined_import_footers_support_review_and_exact_verification(self):
        for index, newline in enumerate(["\n", "\r\n", "\r"]):
            with self.subTest(newline=repr(newline)):
                chapter = self.root / f"combined-{index}"
                shutil.copytree(FIXTURES / "chapter", chapter)
                correction = chapter / "Correction-solutions" / "solutions.md"
                text = correction.read_text(encoding="utf-8").replace(
                    ")\n> [PDF p. 1](solutions.pdf#page=1)",
                    ") · [PDF p. 1](solutions.pdf#page=1)")
                correction.write_bytes(text.replace("\n", newline).encode("utf-8"))
                baseline = self.root / f"combined-{index}-before.json"
                capture(chapter, baseline)
                original = inventory(chapter)
                proposal = self.root / f"combined-{index}-proposal.md"
                result = review(chapter, baseline, [self.drafts], proposal)
                self.assertEqual(result["new_explanations"], 1)
                self.assertEqual(inventory(chapter), original)
                shutil.copyfile(self.aid, chapter / "aides" / self.aid.name)
                report = verify_approved(chapter, baseline, proposal, result["manifest_sha256"])
                self.assertTrue(report["approved_bytes_identical"])
                self.assertEqual(report["questions_without_correction"], ["exercise-document#^q-3"])

    def test_equivalent_newlines_are_not_identical_approved_bytes(self):
        result = self.create_proposal()
        self.persist()
        path = self.chapter / "aides" / self.aid.name
        newline = "\n" if b"\r\n" in self.aid.read_bytes() else "\r\n"
        path.write_bytes(self.aid.read_text(encoding="utf-8").replace("\n", newline).encode("utf-8"))
        with self.assertRaisesRegex(EnrichError, "differs from approval"):
            verify_approved(self.chapter, self.before, self.proposal, result["manifest_sha256"])

    def test_edited_preview_or_manifest_is_not_accepted_as_original_approval(self):
        result = self.create_proposal()
        self.persist()
        original = self.proposal.read_bytes()
        self.proposal.write_bytes(original + b"\nChanged preview.")
        with self.assertRaisesRegex(EnrichError, "Proposal content changed"):
            verify_approved(self.chapter, self.before, self.proposal, result["manifest_sha256"])
        self.proposal.write_bytes(original)
        manifest = self.proposal.with_suffix(".json")
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        with self.assertRaisesRegex(EnrichError, "manifest changed"):
            verify_approved(self.chapter, self.before, self.proposal, result["manifest_sha256"])

    def test_changed_baseline_is_rejected_without_recapture(self):
        result = self.create_proposal()
        self.persist()
        self.before.write_bytes(self.before.read_bytes() + b"\n")
        with self.assertRaisesRegex(EnrichError, "Original baseline changed"):
            verify_approved(self.chapter, self.before, self.proposal, result["manifest_sha256"])

    def test_missing_or_extra_persisted_aids_are_rejected(self):
        result = self.create_proposal()
        with self.assertRaisesRegex(EnrichError, "approved set"):
            verify_approved(self.chapter, self.before, self.proposal, result["manifest_sha256"])
        self.persist()
        extra = self.chapter / "aides" / "q-3.md"
        text = self.aid.read_text(encoding="utf-8").split("> [!explanation]")[0]
        text = "\n".join(line for line in text.splitlines() if not line.startswith("correction:"))
        extra.write_text(text.replace("id: aid-q-1", "id: aid-q-3").replace("#^q-1", "#^q-3"),
                         encoding="utf-8")
        with self.assertRaisesRegex(EnrichError, "approved set"):
            verify_approved(self.chapter, self.before, self.proposal, result["manifest_sha256"])

    def test_unapproved_empty_aid_directories_are_rejected(self):
        result = self.create_proposal()
        self.persist()
        (self.chapter / "aides" / "unapproved").mkdir()
        with self.assertRaisesRegex(EnrichError, "directories differ"):
            verify_approved(self.chapter, self.before, self.proposal, result["manifest_sha256"])

    def test_multiple_batches_combine_but_duplicate_destinations_fail(self):
        other = self.root / "batch-2"
        other.mkdir()
        text = self.aid.read_text(encoding="utf-8").split("> [!explanation]")[0]
        text = "\n".join(line for line in text.splitlines() if not line.startswith("correction:"))
        (other / "q-3.md").write_text(
            text.replace("id: aid-q-1", "id: aid-q-3").replace("#^q-1", "#^q-3"), encoding="utf-8")
        result = review(self.chapter, self.before, [self.drafts, other], self.proposal)
        self.assertEqual(result["aids"], 2)
        self.assertEqual(result["questions_without_aid"], [])
        shutil.copyfile(self.aid, other / self.aid.name)
        with self.assertRaisesRegex(EnrichError, "Duplicate draft destination"):
            review(self.chapter, self.before, [self.drafts, other], self.root / "another.md")

    def test_case_only_destination_collisions_are_rejected_on_every_platform(self):
        other = self.root / "case-only-batch"
        other.mkdir()
        shutil.copyfile(self.aid, other / "Q-1.MD")
        with self.assertRaisesRegex(EnrichError, "Duplicate draft destination"):
            review(self.chapter, self.before, [self.drafts, other], self.proposal)
        existing = self.drafts / "EXISTING-Q-2.MD"
        shutil.copyfile(self.aid, existing)
        with self.assertRaisesRegex(EnrichError, "overwrite"):
            self.create_proposal()

    def test_drafts_cannot_duplicate_question_or_overwrite_existing_aid(self):
        text = self.aid.read_text(encoding="utf-8")
        duplicate = self.drafts / "duplicate.md"
        duplicate.write_text(text.replace("id: aid-q-1", "id: duplicate"), encoding="utf-8")
        with self.assertRaisesRegex(EnrichError, "same question"):
            self.create_proposal()
        duplicate.unlink()
        existing = self.drafts / "existing-q-2.md"
        existing.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(EnrichError, "overwrite"):
            self.create_proposal()

    def test_new_aid_cannot_duplicate_an_existing_question_target(self):
        text = self.aid.read_text(encoding="utf-8").split("> [!explanation]")[0]
        text = "\n".join(line for line in text.splitlines() if not line.startswith("correction:"))
        self.aid.write_text(text.replace("#^q-1", "#^q-2"), encoding="utf-8")
        with self.assertRaisesRegex(EnrichError, "same question"):
            self.create_proposal()

    def test_uppercase_markdown_extension_is_supported(self):
        renamed = self.aid.with_suffix(".MD")
        self.aid.rename(renamed)
        self.aid = renamed
        result = self.create_proposal()
        self.persist()
        self.assertTrue(verify_approved(self.chapter, self.before, self.proposal,
                                        result["manifest_sha256"])["approved_bytes_identical"])

    def test_hidden_draft_names_and_redirected_files_are_rejected(self):
        hidden = self.drafts / ".hidden.md"
        shutil.copyfile(self.aid, hidden)
        with self.assertRaisesRegex(EnrichError, "Hidden aid filename"):
            self.create_proposal()
        hidden.unlink()
        link = self.drafts / "linked.md"
        try:
            link.symlink_to(self.aid)
        except OSError as error:
            self.skipTest(f"File symlink creation unavailable: {error}")
        with self.assertRaisesRegex(EnrichError, "Redirected path"):
            self.create_proposal()

    def test_proposal_refuses_replacement_and_inside_chapter_outputs(self):
        self.create_proposal()
        with self.assertRaisesRegex(EnrichError, "already exist"):
            self.create_proposal()
        with self.assertRaisesRegex(EnrichError, "outside the chapter"):
            review(self.chapter, self.before, [self.drafts], self.chapter / "proposal.md")
        with self.assertRaisesRegex(EnrichError, "outside draft directories"):
            review(self.chapter, self.before, [self.drafts], self.drafts / "proposal.md")

    def test_sources_changed_after_capture_block_draft_review(self):
        source = self.chapter / "Course-course" / "course.md"
        source.write_bytes(source.read_bytes() + b"\nChanged source.")
        with self.assertRaisesRegex(EnrichError, "Original file changed"):
            self.create_proposal()
        self.assertFalse(self.proposal.exists())

    def test_new_schema_and_course_fragment_errors_block_preview(self):
        original = self.aid.read_text(encoding="utf-8")
        for before, after, diagnostic in [
            ("schema_version: 1", "clew_schema: 1", "schema_version"),
            ("#Geometric limits", "#Absent", "course heading"),
        ]:
            self.aid.write_text(original.replace(before, after), encoding="utf-8")
            with self.assertRaisesRegex(EnrichError, diagnostic):
                self.create_proposal()
            self.assertFalse(self.proposal.exists())

    def test_draft_review_requires_unchanged_preedit_inventory(self):
        self.persist()
        with self.assertRaisesRegex(EnrichError, "unchanged pre-edit"):
            self.create_proposal()

    def test_proposal_preserves_crlf_draft_bytes_and_nested_fences(self):
        text = self.aid.read_text(encoding="utf-8") + "\n````text\n```nested\n````\n"
        self.aid.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        result = self.create_proposal()
        self.assertIn(self.aid.read_bytes(), self.proposal.read_bytes())
        self.assertIn(b"`````markdown", self.proposal.read_bytes())
        self.persist()
        self.assertTrue(verify_approved(self.chapter, self.before, self.proposal,
                                        result["manifest_sha256"])["approved_bytes_identical"])

    def test_copied_skill_reviews_and_verifies_without_repository_assets(self):
        copied = self.root / "standalone"
        shutil.copytree(SKILL, copied, ignore=shutil.ignore_patterns("__pycache__"))
        script = copied / "scripts" / "review_enrich.py"
        command = [sys.executable, "-B", str(script), str(self.chapter), "--before", str(self.before)]
        result = subprocess.run(command + ["--drafts", str(self.drafts), "--proposal", str(self.proposal)],
                                cwd=copied, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest_hash = json.loads(result.stdout)["manifest_sha256"]
        self.persist()
        result = subprocess.run(command + ["--approved", str(self.proposal),
                                           "--manifest-sha256", manifest_hash],
                                cwd=copied, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["approved_bytes_identical"])

    def test_review_cli_fails_explicitly_without_writing_invalid_drafts(self):
        self.aid.write_text(self.aid.read_text(encoding="utf-8").replace("#Geometric limits", "#Absent"),
                            encoding="utf-8")
        before = inventory(self.chapter)
        result = subprocess.run(
            [sys.executable, "-B", str(SKILL / "scripts" / "review_enrich.py"), str(self.chapter),
             "--before", str(self.before), "--drafts", str(self.drafts), "--proposal", str(self.proposal)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Enrich review error:", result.stderr)
        self.assertEqual(inventory(self.chapter), before)
        self.assertFalse(self.proposal.exists())


if __name__ == "__main__":
    unittest.main()
