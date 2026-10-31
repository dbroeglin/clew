"""Publishing prepared chapters through Git and installing them in another vault."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "clew-import" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import test_documents
from document_formats import Plan
from install_chapter import draft as install_draft, install
from prepare_documents import materialize, plan_hash
import publish_chapter
from publish_chapter import draft as publish_draft, publish
from validate_documents import validate

HELP = ('---\nclew_schema: 1\ntype: help\nquestion: "[[sheet#^q-1|Question 1]]"\n---\n\n'
        "> [!hint]\n> Compare the ratio with one.\n\n^hint-1\n")


class PublishedChapter(unittest.TestCase):
    def setUp(self):
        fixture = test_documents.DocumentTests("codes")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.plan = fixture.pipeline_plan()
        materialize(self.plan, plan_hash(self.plan))
        self.chapter = Path(self.plan.destination)
        self.root = fixture.root
        self.output = self.root / "repo" / "Courses" / "Sequences"
        self.student = self.root / "student"
        (self.student / "Courses").mkdir(parents=True)

    def codes(self, report):
        return {finding["code"] for finding in report["findings"]}

    def record(self, root):
        return json.loads((root / ".clew" / "preparation.json").read_text(encoding="utf-8"))

    def add_help(self, root):
        (root / "aides").mkdir(exist_ok=True)
        (root / "aides" / "hint.md").write_bytes(HELP.encode("utf-8"))

    def publish(self, output=None):
        output = output or self.output
        report = publish_draft(self.chapter, output)[0]
        self.assertEqual(report["status"], "ready", report)
        return publish(self.chapter, output, report["publish_sha256"])

    def copy(self, name):
        target = self.root / "copies" / name
        shutil.copytree(self.output, target)
        return target

    def note(self, root, role):
        [document] = [item for item in self.record(root)["documents"] if item["role"] == role]
        return root / document["path"]


class PublishTests(PublishedChapter):
    def test_help_notes_are_left_to_enrich(self):
        self.add_help(self.chapter)
        self.assertEqual(validate(self.chapter)["errors"], 0, validate(self.chapter))
        (self.chapter / "aides" / "notes.md").write_text("# Notes\n", encoding="utf-8")
        report = validate(self.chapter)
        self.assertIn("aides/notes.md", {item["path"] for item in report["findings"]}, report)
        (self.chapter / "aides" / "notes.md").unlink()
        (self.chapter / "help.md").write_bytes(HELP.encode("utf-8"))
        report = validate(self.chapter)
        self.assertIn("help.md", {item["path"] for item in report["findings"]}, report)

    def test_publish_writes_public_snapshot(self):
        self.add_help(self.chapter)
        (self.chapter / ".private.md").write_text("hidden", encoding="utf-8")
        report = publish_draft(self.chapter, self.output)[0]
        self.assertEqual((report["status"], report["target"]), ("ready", "new"), report)
        names = [item["path"] for item in report["files"]]
        self.assertIn("aides/hint.md", names)
        self.assertIn("index.md", names)
        self.assertFalse([name for name in names if name.startswith(".")], names)
        self.assertEqual(report["total_bytes"], sum(item["bytes"] for item in report["files"]))
        self.assertFalse(self.output.exists())

        result = publish(self.chapter, self.output, report["publish_sha256"])
        self.assertEqual((result["status"], result["validation"]), ("published", "validated"), result)
        self.assertEqual((self.output / ".gitattributes").read_bytes(), publish_chapter.GITATTRIBUTES)
        self.assertEqual([path.name for path in (self.output / ".clew").iterdir()], ["preparation.json"])
        record = self.record(self.output)
        self.assertEqual((record["kind"], record["chapter"]), ("published", {"id": "sequences", "title": "Sequences"}))
        source = self.record(self.chapter)["documents"]
        self.assertEqual(record["documents"],
                         [{"id": item["id"], "path": item["path"], "role": item["role"]} for item in source])
        visible = {path.relative_to(self.output).as_posix() for path in self.output.rglob("*")
                   if path.is_file() and not path.relative_to(self.output).as_posix().startswith(".")}
        self.assertEqual(set(record["files"]), visible)
        for name in visible:
            self.assertEqual((self.output / name).read_bytes(), (self.chapter / name).read_bytes(), name)
        self.assertEqual(validate(self.output, fidelity=True)["status"], "validated")

    def test_publish_requires_the_approved_check(self):
        report = publish_draft(self.chapter, self.output)[0]
        with self.assertRaisesRegex(ValueError, "changed since approval"):
            publish(self.chapter, self.output, "0" * 64)
        other = self.root / "repo" / "Courses" / "Other"
        with self.assertRaisesRegex(ValueError, "changed since approval"):
            publish(self.chapter, other, report["publish_sha256"])
        note = self.note(self.chapter, "course")
        note.write_bytes(note.read_bytes() + b"\nTeacher addition.\n")
        with self.assertRaisesRegex(ValueError, "changed since approval"):
            publish(self.chapter, self.output, report["publish_sha256"])
        self.assertFalse(self.output.exists())

    def test_publish_reports_large_files(self):
        with patch.object(publish_chapter, "WARN_BYTES", 1):
            report = publish_draft(self.chapter, self.output)[0]
            self.assertEqual(report["status"], "needs_review", report)
            with patch.object(publish_chapter, "LIMIT_BYTES", 1):
                report = publish_draft(self.chapter, self.output)[0]
                self.assertEqual(report["status"], "invalid", report)
                self.assertIn("file-size", self.codes(report))
                with self.assertRaisesRegex(ValueError, "Publication is invalid"):
                    publish(self.chapter, self.output, report["publish_sha256"])
        self.assertFalse(self.output.exists())

    def test_publish_rejects_invalid_sources_and_outputs(self):
        with self.assertRaisesRegex(ValueError, "absolute"):
            publish_draft(self.chapter, Path("Courses") / "Sequences")
        with self.assertRaisesRegex(ValueError, "inside the source"):
            publish_draft(self.chapter, self.chapter / "copy")
        with self.assertRaisesRegex(ValueError, "visible"):
            publish_draft(self.chapter, self.root / "repo" / ".hidden")
        (self.root / "taken").mkdir()
        (self.root / "taken" / "notes.md").write_text("mine", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "other content"):
            publish_draft(self.chapter, self.root / "taken")
        (self.chapter / "index.md").write_text("broken", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Chapter is invalid"):
            publish_draft(self.chapter, self.output)

    def test_republish_replaces_only_the_same_chapter(self):
        self.publish()
        report = publish_draft(self.chapter, self.output)[0]
        self.assertEqual(report["target"], "republish", report)
        with self.assertRaisesRegex(ValueError, "Remove the previous published copy"):
            publish(self.chapter, self.output, report["publish_sha256"])
        other = self.copy("other")
        record = self.record(other)
        record["chapter"]["id"] = "limits"
        (other / ".clew" / "preparation.json").write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "other content"):
            publish_draft(self.chapter, other)
        shutil.rmtree(self.output)
        self.add_help(self.chapter)
        self.assertEqual(self.publish()["status"], "published")
        self.assertIn("aides/hint.md", self.record(self.output)["files"])

    def test_published_validation_detects_changes(self):
        self.publish()
        edited = self.copy("edited")
        note = self.note(edited, "course")
        note.write_bytes(note.read_bytes() + b"\nStudent remark.\n")
        self.add_help(edited)
        self.assertEqual(validate(edited)["errors"], 0, validate(edited))
        report = validate(edited, fidelity=True)
        self.assertTrue({"published-file", "published-inventory"} <= self.codes(report), report)

        pdf = next(name for name in self.record(self.output)["files"] if name.endswith(".pdf"))
        damaged = self.copy("damaged")
        (damaged / pdf).write_bytes((damaged / pdf).read_bytes() + b"%changed\n")
        self.assertIn("published-file", self.codes(validate(damaged)))

        moved = self.copy("moved")
        note = self.note(moved, "exercise")
        note.rename(note.with_name("renamed.md"))
        self.assertIn("document-identity", self.codes(validate(moved)))

        relabeled = self.copy("relabeled")
        record = self.record(relabeled)
        record["chapter"]["id"] = "limits"
        (relabeled / ".clew" / "preparation.json").write_text(json.dumps(record), encoding="utf-8")
        self.assertIn("chapter-index", self.codes(validate(relabeled)))

        hidden = self.copy("hidden")
        record = self.record(hidden)
        record["files"][".obsidian/workspace.json"] = "0" * 64
        (hidden / ".clew" / "preparation.json").write_text(json.dumps(record), encoding="utf-8")
        self.assertIn("published-manifest", self.codes(validate(hidden)))

    def test_install_copies_the_published_files(self):
        self.add_help(self.chapter)
        self.publish()
        report = install_draft(self.output, str(self.student), "Courses", None, False)[0]
        destination = self.student / "Courses" / "Sequences"
        self.assertEqual((report["status"], report["destination"], report["create_directories"]),
                         ("ready", str(destination), []), report)
        self.assertFalse(destination.exists())
        with self.assertRaisesRegex(ValueError, "changed since approval"):
            install(self.output, str(self.student), "Courses", None, False, "0" * 64)
        result = install(self.output, str(self.student), "Courses", None, False, report["install_sha256"])
        self.assertEqual((result["status"], result["validation"]), ("installed", "validated"), result)
        installed = {path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()}
        self.assertEqual(installed, set(self.record(self.output)["files"]) | {".clew/preparation.json"})
        self.assertEqual(self.record(destination), self.record(self.output))
        self.assertEqual(validate(destination, fidelity=True)["status"], "validated")
        with self.assertRaisesRegex(ValueError, "already exists"):
            install_draft(self.output, str(self.student), "Courses", None, False)

    def test_install_placement_and_source_checks(self):
        self.publish()
        with self.assertRaisesRegex(ValueError, "create_parent"):
            install_draft(self.output, str(self.student), "Maths/Analysis", "Suites", False)
        report = install_draft(self.output, str(self.student), "Maths/Analysis", "Suites", True)[0]
        self.assertEqual(report["create_directories"],
                         [str(self.student / "Maths"), str(self.student / "Maths" / "Analysis")])
        result = install(self.output, str(self.student), "Maths/Analysis", "Suites", True, report["install_sha256"])
        self.assertEqual(result["destination"], str(self.student / "Maths" / "Analysis" / "Suites"))
        for name in (".hidden", "a/b"):
            with self.assertRaisesRegex(ValueError, "one visible, portable name"):
                install_draft(self.output, str(self.student), "Courses", name, False)
        with self.assertRaisesRegex(ValueError, "already exists"):
            install_draft(self.output, str(self.output.parent.parent), "Courses", None, False)
        with self.assertRaisesRegex(ValueError, "owned root"):
            install_draft(self.output, str(self.output), "aides", None, False)
        with self.assertRaisesRegex(ValueError, "Only chapters published"):
            install_draft(self.chapter, str(self.student), "Courses", None, False)
        with self.assertRaisesRegex(ValueError, "existing or unrecognized owned root"):
            install_draft(self.output, str(self.fixture.vault), "Maths/Sequences", "Copy", False)
        (self.output / "extra.md").write_text("# Extra\n", encoding="utf-8")
        report = install_draft(self.output, str(self.student), "Courses", "Other", False)[0]
        self.assertEqual(report["status"], "invalid", report)
        with self.assertRaisesRegex(ValueError, "Published chapter is invalid"):
            install(self.output, str(self.student), "Courses", "Other", False, report["install_sha256"])
        self.assertFalse((self.student / "Courses" / "Other").exists())


@unittest.skipUnless(shutil.which("git"), "git is required for the Git round trip")
class GitRoundTripTests(PublishedChapter):
    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-c", "user.name=Teacher", "-c", "user.email=teacher@example.invalid",
                               "-c", "commit.gpgsign=false", *args], cwd=cwd, check=True,
                              capture_output=True, text=True).stdout.strip()

    def push(self, clone, name, message):
        self.git("-C", str(clone), "add", "--", f"Courses/{name}")
        self.git("-C", str(clone), "commit", "-q", "-m", message)
        self.git("-C", str(clone), "push", "-q", "origin", "HEAD:refs/heads/main")

    def test_teacher_publishes_and_student_installs(self):
        remote, teacher = self.root / "remote.git", self.root / "teacher"
        self.git("init", "-q", "--bare", "--initial-branch=main", str(remote))
        self.git("clone", "-q", "--no-recurse-submodules", "-c", "core.autocrlf=false", "--", str(remote), str(teacher))
        self.output = teacher / "Courses" / "Sequences"
        self.publish()
        self.push(teacher, "Sequences", "Publish Sequences")

        limits = Plan.model_validate({**self.plan.model_dump(), "id": "limits", "title": "Limits",
                                      "destination": str(self.fixture.vault / "Maths" / "Limits")})
        materialize(limits, plan_hash(limits))
        report = publish_draft(Path(limits.destination), teacher / "Courses" / "Limits")[0]
        publish(Path(limits.destination), teacher / "Courses" / "Limits", report["publish_sha256"])
        self.push(teacher, "Limits", "Publish Limits")

        self.add_help(self.chapter)
        self.assertEqual(publish_draft(self.chapter, self.output)[0]["target"], "republish")
        self.git("-C", str(teacher), "rm", "-r", "-q", "--", "Courses/Sequences")
        self.publish()
        self.push(teacher, "Sequences", "Republish Sequences")

        # A student's global autocrlf must not change published bytes.
        student = self.root / "download"
        self.git("clone", "-q", "--depth", "1", "--no-recurse-submodules", "-c", "core.symlinks=false",
                 "-c", "core.autocrlf=true", "--", str(remote), str(student))
        self.assertEqual(self.git("-C", str(teacher), "rev-list", "--count", "HEAD"), "3")
        for name, chapter_id in (("Sequences", "sequences"), ("Limits", "limits")):
            report = validate(student / "Courses" / name, fidelity=True)
            self.assertEqual(report["status"], "validated", report)
            self.assertEqual(self.record(student / "Courses" / name)["chapter"]["id"], chapter_id)
        source = student / "Courses" / "Sequences"
        report = install_draft(source, str(self.student), "Courses", None, False)[0]
        result = install(source, str(self.student), "Courses", None, False, report["install_sha256"])
        self.assertEqual(result["status"], "installed", result)
        self.assertTrue((self.student / "Courses" / "Sequences" / "aides" / "hint.md").is_file())
        self.assertFalse((self.student / "Courses" / "Sequences" / ".git").exists())


if __name__ == "__main__":
    unittest.main()
