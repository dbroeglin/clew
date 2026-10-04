from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "clew-ingest" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from bundle_sources import load_bundle
from formats import Plan
from ingest_io import fingerprint, no_redirect, relative_path
from inspect_bundles import inspect
from inspect_vault import inspect as inspect_vault
from markdown_source import MarkdownSource
from plan_checks import plan_hash
from validate_ingest import validate
from write_ingest import check, materialize
from runtime_fixtures import build_wheelhouse


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".obsidian").mkdir()
        (self.root / "courses").mkdir()

    def placement(self):
        return {"vault": str(self.root), "parent": "courses",
                "rationale": "Use the existing course container confirmed in this fixture."}

    def bundle(self, name, text, *, status="extracted", issues=None):
        root = self.root / name
        (root / "source").mkdir(parents=True)
        (root / "raw" / "pages").mkdir(parents=True)
        (root / "figures").mkdir()
        pdf = root / "source" / "same.pdf"
        pdf.write_bytes(b"%PDF synthetic retained source " + name.encode())
        (root / "document.md").write_bytes(text.encode("utf-8"))
        figure = root / "figures" / "same.png"
        figure.write_bytes(b"synthetic image " + name.encode())
        numbers = list(MarkdownSource(text).markers.values())
        pages = []
        for number in numbers:
            image, response = f"raw/pages/{number}.png", f"raw/pages/{number}.json"
            (root / image).write_bytes(b"synthetic image")
            (root / response).write_text("{}", encoding="utf-8")
            pages.append({"number": number, "raw_image": image, "raw_response": response})
        manifest = {
            "schema_version": 3, "status": status, "document": "document.md",
            "source": {"name": "same.pdf", "path": "source/same.pdf",
                       "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                       "page_count": max(numbers)},
            "pages": pages, "figures": [{"asset": "figures/same.png"}],
            "issues": issues or [],
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return root

    def plan(self):
        course = self.bundle("course", "<!-- page: 1 -->\n\n# Course\n\n"
                             "Statement.\n\n$$x^2 + y^2 = 1$$\n\nProof.\n\n"
                             "![Figure](figures/same.png)\n")
        exercise = self.bundle("exercise", "<!-- page: 1 -->\n\nContext.\n\n"
                               "1. Determine the kernel.\n\n"
                               "2. Using question 1, determine the image.\n")
        correction = self.bundle("correction", "<!-- page: 1 -->\n\n"
                                 "Answer 1: $\\ker f = E$.\n\n"
                                 "Answer 2: $\\mathrm{Im} f = \\{0\\}$.\n")
        sources = [{"id": source_id, "bundle": str(root),
                    "fingerprint": load_bundle(root).fingerprint}
                   for source_id, root in (("cours", course), ("feuille", exercise), ("corrige", correction))]
        notes = [
            {"id": "algebre-cours", "type": "course", "title": "Course",
             "title_origin": "source", "order": 10,
             "parts": [{"source": "cours", "start": 1, "end": 11}]},
            {"id": "algebre-exercice", "type": "exercise", "title": "Kernel and image",
             "title_origin": "agent", "order": 10,
             "parts": [{"source": "feuille", "start": 1, "end": 4},
                       {"source": "feuille", "start": 5, "end": 6,
                        "role": "question", "id": "q-kernel", "label": "1."},
                       {"source": "feuille", "start": 7, "end": 7,
                        "role": "question", "id": "q-image", "label": "2."}]},
            {"id": "algebre-correction", "type": "correction", "title": "Correction",
             "title_origin": "agent", "order": 10,
             "parts": [{"source": "corrige", "start": 1, "end": 4,
                        "role": "answer", "id": "r-kernel", "label": "1."},
                       {"source": "corrige", "start": 5, "end": 5,
                        "role": "answer", "id": "r-image", "label": "2."}]},
        ]
        evidence = [{"source": "feuille", "start": 7, "end": 7}]
        relationships = [
            {"rel": "course", "origin": "algebre-exercice", "target": "algebre-cours",
             "evidence": [{"source": "cours", "start": 3, "end": 3}]},
            {"rel": "correction", "origin": "algebre-correction", "target": "algebre-exercice",
             "evidence": [{"source": "corrige", "start": 3, "end": 3}]},
            {"rel": "question", "origin": "algebre-correction#^r-kernel",
             "target": "algebre-exercice#^q-kernel", "evidence": [{"source": "corrige", "start": 3, "end": 3}]},
            {"rel": "question", "origin": "algebre-correction#^r-image",
             "target": "algebre-exercice#^q-image", "evidence": [{"source": "corrige", "start": 5, "end": 5}]},
            {"rel": "needs", "origin": "algebre-exercice#^q-image",
             "target": "algebre-exercice#^q-kernel", "evidence": evidence},
        ]
        return Plan.model_validate({"schema_version": 2, "ingest_id": "algebre",
                                    "title": "Algebre", "destination": str(self.root / "courses" / "output"),
                                    "placement": self.placement(),
                                    "sources": sources, "notes": notes,
                                    "relationships": relationships, "issues": []})

    def mutate(self, plan, edit):
        data = plan.model_dump()
        edit(data)
        return Plan.model_validate(data)

    def test_separate_sources_collision_safe_copies_links_and_offline_validation(self):
        plan = self.plan()
        report, bundles = check(plan)
        self.assertFalse(Path(plan.destination).exists())
        self.assertEqual(report["issues"], [])
        result = materialize(plan, report["plan_sha256"])
        self.assertEqual(result["status"], "validated")
        root = Path(plan.destination)
        self.assertFalse((root / "sections").exists())
        self.assertFalse((root / "_imports").exists())
        self.assertEqual(set(result["files"]), {path.relative_to(root).as_posix()
                         for path in root.rglob("*") if path.is_file()})
        for source, bundle in bundles.items():
            for name in bundle.files:
                self.assertEqual((root / "sources" / source / bundle.retained_path(name)).read_bytes(),
                                 (bundle.root / name).read_bytes())
            self.assertFalse((root / "sources" / source / "raw").exists())
            self.assertFalse((root / "sources" / source / "source").exists())
            self.assertTrue((bundle.root / "source" / "same.pdf").is_file())
        course = (root / "courses" / "algebre-cours.md").read_text(encoding="utf-8")
        self.assertIn("../sources/cours/figures/same.png", course)
        self.assertIn("cours: [page 1](../sources/cours/same.pdf#page=1)", course)
        self.assertIn('"file": "sources/cours/same.pdf"', course)
        self.assertIn("$$x^2 + y^2 = 1$$", course)
        self.assertNotIn("<!-- page:", course)
        exercise = (root / "exercices" / "algebre-exercice.md").read_text(encoding="utf-8")
        self.assertIn("[needs:: [[algebre-exercice#^q-kernel]]]", exercise)
        self.assertIn('corrections: ["[[algebre-correction]]"]', exercise)
        for source in plan.sources:
            self.assertEqual(Path(source.bundle).parent, self.root)
            shutil.rmtree(Path(source.bundle))
        relocated = self.root / "relocated"
        shutil.copytree(root, relocated)
        self.assertEqual(validate(relocated)["status"], "validated")

    def test_one_mixed_source_and_shared_courses_directory(self):
        parts = ["<!-- page: 1 -->\n\nIntroduction.\n\n",
                 "# Kernel\n\nStatement.\n\nProof.\n\n",
                 "Question.\n\n", "Answer.\n"]
        text = "".join(parts)
        root = self.bundle("mixed", text)
        ranges = []
        start = 1
        for value in parts:
            end = start + len(value.splitlines()) - 1
            ranges.append((start, end))
            start = end + 1
        notes = []
        for index, kind in enumerate(("course", "section", "exercise", "correction")):
            start, end = ranges[index]
            part = {"source": "poly", "start": start, "end": end}
            if kind in {"exercise", "correction"}:
                part.update(role="question" if kind == "exercise" else "answer",
                            id="q-one" if kind == "exercise" else "r-one")
            notes.append({"id": "mixed-" + kind, "type": kind, "title": kind,
                          "title_origin": "agent", "order": 10, "parts": [part]})
        evidence = [{"source": "poly", "start": ranges[1][0], "end": ranges[1][1]}]
        plan = Plan.model_validate({
            "schema_version": 2, "ingest_id": "mixed", "title": "Mixed",
            "destination": str(self.root / "courses" / "mixed-output"), "placement": self.placement(),
            "sources": [{"id": "poly", "bundle": str(root), "fingerprint": load_bundle(root).fingerprint}],
            "notes": notes,
            "relationships": [{"rel": "course", "origin": "mixed-section", "target": "mixed-course",
                               "evidence": evidence}], "issues": []})
        result = materialize(plan, plan_hash(plan))
        self.assertEqual(result["status"], "needs_review")
        self.assertTrue((Path(plan.destination) / "courses" / "mixed-section.md").exists())
        self.assertIn("unmatched-answer", {issue["code"] for issue in result["issues"]})

    def test_course_only_and_partial_pages_needs_review(self):
        root = self.bundle("partial", "<!-- page: 3 -->\n\n# Course only\n",
                           status="needs_review", issues=[{"z": "Uncertain figure", "a": 3}])
        plan = Plan.model_validate({
            "schema_version": 2, "ingest_id": "partial", "title": "Partial course",
            "destination": str(self.root / "courses" / "out"), "placement": self.placement(),
            "sources": [{"id": "cours", "bundle": str(root), "fingerprint": load_bundle(root).fingerprint}],
            "notes": [{"id": "partial-course", "type": "course", "title": "Course only",
                       "title_origin": "source", "order": 1,
                       "parts": [{"source": "cours", "start": 1, "end": 3}]}],
            "relationships": [], "issues": []})
        result = materialize(plan, plan_hash(plan))
        self.assertEqual(result["status"], "needs_review")
        self.assertFalse((Path(plan.destination) / "exercices").exists())
        self.assertFalse((Path(plan.destination) / "corriges").exists())
        self.assertEqual(load_bundle(root).metadata["pages"], [3])
        note = (Path(plan.destination) / "courses" / "partial-course.md").read_text()
        self.assertIn("[page 3](../sources/cours/same.pdf#page=3)", note)
        self.assertNotIn("#page=1", note)
        self.assertIn("[PDF, page 3](sources/cours/same.pdf#page=3)",
                      (Path(plan.destination) / "index.md").read_text())

    def test_multiple_supplied_answers_and_ambiguity(self):
        plan = self.plan()
        data = plan.model_dump()
        data["relationships"] = [edge for edge in data["relationships"]
                                 if edge["rel"] != "question" or "r-image" not in edge["origin"]]
        data["issues"] = [{"code": "ambiguous-numbering", "message": "Keep unmatched answer.",
                           "note": "algebre-correction"}]
        changed = Plan.model_validate(data)
        issues = check(changed)[0]["issues"]
        self.assertIn("unmatched-answer", {item["code"] for item in issues})
        data["relationships"].append({
            "rel": "question", "origin": "algebre-correction#^r-image",
            "target": "algebre-exercice#^q-kernel",
            "evidence": [{"source": "corrige", "start": 5, "end": 5}]})
        self.assertIn("missing-answer", {item["code"] for item in check(Plan.model_validate(data))[0]["issues"]})

    def test_malformed_plans_and_relationships(self):
        plan = self.plan()
        mutations = [
            lambda d: d["notes"][0]["parts"][0].update(end=10),
            lambda d: d["notes"][0]["parts"].append(copy.deepcopy(d["notes"][0]["parts"][0])),
            lambda d: d["notes"][1]["parts"][1].update(id="r-wrong"),
            lambda d: d["notes"][1].update(id="wrong-namespace"),
            lambda d: d["relationships"][-1].update(target="algebre-exercice#^q-image"),
            lambda d: d["relationships"][-1].update(target="unknown#^q-one"),
            lambda d: d["relationships"][0].update(target="algebre-correction"),
            lambda d: d["relationships"][1].update(target="algebre-cours"),
            lambda d: d["relationships"].append(copy.deepcopy(d["relationships"][0])),
            lambda d: d["relationships"][0]["evidence"][0].update(start=2, end=2),
            lambda d: d["sources"].append(copy.deepcopy(d["sources"][0])),
            lambda d: d["notes"].append(copy.deepcopy(d["notes"][0])),
            lambda d: d["notes"][0].update(title="Bad\nTitle"),
            lambda d: d["notes"][1]["parts"][0].update(source="unknown"),
        ]
        for index, edit in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(ValueError):
                check(self.mutate(plan, edit))
        self.assertFalse(Path(plan.destination).exists())

    def test_changed_plan_source_pdf_markdown_and_assets_block_writes(self):
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, "Plan changed"):
            materialize(self.mutate(plan, lambda d: d.update(title="Changed")), plan_hash(plan))
        for path in ("document.md", "source/same.pdf", "figures/same.png", "manifest.json"):
            target = Path(plan.sources[0].bundle) / path
            original = target.read_bytes()
            target.write_bytes(original + b"\n")
            with self.subTest(path=path), self.assertRaises(ValueError):
                check(plan)
            target.write_bytes(original)
        self.assertFalse(Path(plan.destination).exists())

    def test_existing_and_input_nested_destinations_blocked(self):
        plan = self.plan()
        root = Path(plan.destination)
        root.mkdir()
        (root / "human.md").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already exists"):
            materialize(plan, plan_hash(plan))
        self.assertEqual((root / "human.md").read_text(), "keep")
        nested = self.mutate(plan, lambda d: d.update(
            destination=str(Path(d["sources"][0]["bundle"]) / "nested")))
        nested.placement.parent = "course"
        with self.assertRaisesRegex(ValueError, "inside an input"):
            check(nested)

    def test_incomplete_failure_is_preserved_and_not_reused(self):
        plan = self.plan()
        with patch("write_ingest.shutil.copyfileobj", side_effect=OSError("synthetic failure")):
            with self.assertRaisesRegex(ValueError, "preserve partial output"):
                materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        self.assertEqual(json.loads((root / "ingest.json").read_text())["status"], "writing")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            validate(root)
        with self.assertRaisesRegex(ValueError, "already exists"):
            materialize(plan, plan_hash(plan))

    def test_persisted_changed_content_assets_or_extra_files_are_rejected(self):
        plan = self.plan()
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        for name in ("courses/algebre-cours.md", "sources/cours/same.pdf",
                     "sources/cours/figures/same.png", "index.md"):
            path = root / name
            original = path.read_bytes()
            path.write_bytes(original + b"edit")
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate(root)
            path.write_bytes(original)
        (root / "human.md").write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            validate(root)

    def test_independent_fidelity_check_not_just_output_hash(self):
        plan = self.plan()
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        path = root / "courses" / "algebre-cours.md"
        path.write_bytes(path.read_bytes().replace(b"Statement.", b"Wrong text."))
        record_path = root / "ingest.json"
        record = json.loads(record_path.read_text())
        record["files"]["courses/algebre-cours.md"] = hashlib.sha256(path.read_bytes()).hexdigest()
        record_path.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "fidelity"):
            validate(root)

    def test_inspection_is_read_only_and_reports_duplicate_selection(self):
        plan = self.plan()
        paths = [Path(source.bundle) for source in plan.sources]
        before = {str(path): path.read_bytes() for root in paths for path in root.rglob("*") if path.is_file()}
        report = inspect(paths)
        self.assertEqual(len(report["bundles"]), 3)
        self.assertEqual(before, {str(path): path.read_bytes() for root in paths for path in root.rglob("*") if path.is_file()})
        with self.assertRaisesRegex(ValueError, "twice"):
            inspect([paths[0], paths[0]])

    def test_bundle_integrity_missing_artifacts_and_traversal(self):
        plan = self.plan()
        root = Path(plan.sources[0].bundle)
        manifest_path = root / "manifest.json"
        original = manifest_path.read_bytes()
        edits = [
            lambda d: d.update(schema_version=2),
            lambda d: d.update(status="failed"),
            lambda d: d["source"].update(path="../same.pdf"),
            lambda d: d["pages"][0].update(number=4),
            lambda d: d["pages"].append(copy.deepcopy(d["pages"][0])),
            lambda d: d["pages"][0].update(raw_image="../outside.png"),
            lambda d: d["figures"][0].update(asset="figures/missing.png"),
        ]
        for edit in edits:
            value = json.loads(original)
            edit(value)
            manifest_path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_bundle(root)
        manifest_path.write_bytes(original)

    def test_portable_paths_and_cloud_placeholders(self):
        for value in ("../escape", "/absolute", "C:\\escape", "a\\b", "a/../b",
                      "a/CON.md", "a/name.", "a//b", "a/name:stream"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                relative_path(value)
        path = self.root
        actual = path.lstat()
        for tag, accepted in ((0x9000001A, True), (0xA0000003, False), (0, False)):
            info = SimpleNamespace(st_mode=actual.st_mode, st_file_attributes=0x400,
                                   st_reparse_tag=tag)
            with patch.object(Path, "lstat", return_value=info):
                if accepted:
                    self.assertEqual(no_redirect(path), path)
                else:
                    with self.assertRaises(ValueError):
                        no_redirect(path)

    def test_cli_and_copied_skill_do_not_require_repository_files(self):
        plan = self.plan()
        copied = self.root / "portable"
        shutil.copytree(SCRIPTS.parent, copied)
        argv = [sys.executable, "-B", str(copied / "scripts" / "inspect_bundles.py"),
                plan.sources[0].bundle]
        result = subprocess.run(argv, cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["bundles"]), 1)
        self.assertFalse((copied / "tests").exists())
        for script in ("inspect_bundles", "inspect_vault", "slice_markdown", "write_ingest", "validate_ingest"):
            result = subprocess.run([sys.executable, "-B", str(copied / "scripts" / (script + ".py")), "--help"],
                                    cwd=self.root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([sys.executable, "-B", str(copied / "scripts" / "inspect_vault.py"),
                                 str(self.root), "--within", "courses"],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["scope"], "courses")
        plan_path = self.root / "plan.json"
        plan_path.write_text(plan.model_dump_json(), encoding="utf-8")
        result = subprocess.run([sys.executable, "-B", str(copied / "scripts" / "write_ingest.py"),
                                 str(plan_path), "--check"], cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["requires_approval"])
        self.assertFalse(Path(plan.destination).exists())
        result = subprocess.run([sys.executable, "-B", str(copied / "scripts" / "write_ingest.py"),
                                 str(plan_path), "--plan-sha256", plan_hash(plan)],
                                cwd=self.root, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([sys.executable, "-B", str(copied / "scripts" / "validate_ingest.py"),
                                 plan.destination], cwd=self.root, capture_output=True,
                                text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "validated")

    def test_relocated_output_validates_after_original_vault_disappears(self):
        plan = self.plan()
        vault = self.root / "old-vault"
        (vault / "courses").mkdir(parents=True)
        data = plan.model_dump()
        data["placement"]["vault"] = str(vault)
        data["destination"] = str(vault / "courses" / "chapter")
        plan = Plan.model_validate(data)
        materialize(plan, plan_hash(plan))
        moved = self.root / "relocated-chapter"
        shutil.move(plan.destination, moved)
        shutil.rmtree(vault)
        self.assertFalse(vault.exists())
        self.assertEqual(validate(moved)["status"], "validated")

    def test_reference_definitions_cannot_cross_notes_or_callout_context(self):
        plan = self.plan()
        root = Path(plan.sources[0].bundle)
        text = "<!-- page: 1 -->\n\n![Alt][fig]\n\n[fig]: figures/same.png\n"
        (root / "document.md").write_text(text, encoding="utf-8")
        data = plan.model_dump()
        data["sources"][0]["fingerprint"] = load_bundle(root).fingerprint
        data["notes"][0]["parts"] = [{"source": "cours", "start": 1, "end": 5}]
        data["relationships"][0]["evidence"] = [{"source": "cours", "start": 3, "end": 3}]
        good = Plan.model_validate(data)
        self.assertEqual(check(good)[0]["status"], "checked")
        data["notes"][0]["parts"][0]["end"] = 4
        data["notes"].append({
            "id": "algebre-definitions", "type": "section", "title": "Definitions",
            "title_origin": "agent", "order": 20,
            "parts": [{"source": "cours", "start": 5, "end": 5}]})
        data["relationships"].append({
            "rel": "course", "origin": "algebre-definitions", "target": "algebre-cours",
            "evidence": [{"source": "cours", "start": 3, "end": 3}]})
        with self.assertRaisesRegex(ValueError, "crosses"):
            check(Plan.model_validate(data))

    def test_slicer_hash_utf8_and_unknown_plan_fields(self):
        root = self.bundle("unicode", "<!-- page: 1 -->\n\nTh\u00e9or\u00e8me: $\\alpha$.\n")
        markdown = root / "document.md"
        digest = hashlib.sha256(markdown.read_bytes()).hexdigest()
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "slice_markdown.py"),
                                 str(markdown), "--start", "1", "--end", "3", "--sha256", digest],
                                capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Th\u00e9or\u00e8me", result.stdout)
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "slice_markdown.py"),
                                 str(markdown), "--start", "1", "--end", "3", "--sha256", "0" * 64],
                                capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertIn("changed", result.stderr)
        data = self.plan().model_dump()
        data["rewrite_source"] = True
        with self.assertRaises(ValueError):
            Plan.model_validate(data)

    def test_rich_question_projection_preserves_exact_content(self):
        text = ("<!-- page: 1 -->\r\n\r\nTh\u00e9or\u00e8me: $\\alpha$.\r\n\r\n"
                "$$\r\nx^2 + y^2 = 1\r\n$$\r\n\r\n"
                "| A | B |\r\n| --- | --- |\r\n| 1 | 2 |\r\n\r\n"
                "1. First item.\r\n   Continuation.\r\n2. Second item.\r\n\r\n"
                "![One](figures/same.png) and ![Two](<figures/%73ame.png>)\r\n\r\n"
                "```\r\n<!-- page: 1 -->\r\nA\u2028B\r\n```\r\n\r\n"
                "<!-- page: 2 -->\r\n\r\nRepeated.\r\n\r\nRepeated.")
        root = self.bundle("rich", text)
        plan = Plan.model_validate({
            "schema_version": 2, "ingest_id": "rich", "title": "Rich question",
            "destination": str(self.root / "courses" / "rich-output"), "placement": self.placement(),
            "sources": [{"id": "sheet", "bundle": str(root), "fingerprint": load_bundle(root).fingerprint}],
            "notes": [{"id": "rich-exercise", "type": "exercise", "title": "Question",
                       "title_origin": "agent", "order": 1,
                       "parts": [{"source": "sheet", "start": 1, "end": len(MarkdownSource(text).lines),
                                  "role": "question", "id": "q-one"}]}],
            "relationships": [], "issues": []})
        result = materialize(plan, plan_hash(plan))
        self.assertEqual(result["status"], "needs_review")
        self.assertEqual((Path(plan.destination) / "sources" / "sheet" / "document.md").read_bytes(),
                         text.encode("utf-8"))
        self.assertEqual(validate(Path(plan.destination))["status"], "needs_review")

    def test_offline_standalone_uv_install_and_complete_ingest(self):
        plan = self.plan()
        copied = self.root / "offline-standalone"
        shutil.copytree(SCRIPTS.parent, copied)
        exported = subprocess.run([
            "uv", "export", "--package", "clew-ingest", "--locked",
            "--no-emit-project", "--no-hashes", "--format", "requirements-txt"],
            cwd=SCRIPTS.parents[3], capture_output=True, encoding="utf-8")
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertNotIn("azure-", exported.stdout)
        wheelhouse = self.root / "wheelhouse"
        build_wheelhouse(wheelhouse, exported.stdout)
        result = subprocess.run([
            "uv", "sync", "--offline", "--no-index", "--find-links", str(wheelhouse),
            "--project", str(copied), "--python", sys.executable],
            capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((copied / "uv.lock").exists())
        executable = (copied / ".venv" / "Scripts" / "python.exe" if os.name == "nt"
                      else copied / ".venv" / "bin" / "python")
        plan_path = self.root / "standalone-plan.json"
        plan_path.write_text(plan.model_dump_json(), encoding="utf-8")
        commands = [
            ["inspect_bundles.py", plan.sources[0].bundle],
            ["write_ingest.py", str(plan_path), "--check"],
            ["write_ingest.py", str(plan_path), "--plan-sha256", plan_hash(plan)],
            ["validate_ingest.py", plan.destination],
        ]
        for script, *arguments in commands:
            result = subprocess.run([str(executable), "-B", str(copied / "scripts" / script), *arguments],
                                    cwd=copied, capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)
        result = subprocess.run([str(executable), "-c",
                                 "import importlib.util; assert importlib.util.find_spec('azure') is None"],
                                cwd=copied, capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(os.environ.get("CLEW_TEST_STANDALONE") == "1",
                         "Opt-in dependency-resolution test; contacts PyPI.")
    def test_standalone_uv_environment_with_only_declared_dependencies(self):
        plan = self.plan()
        copied = self.root / "standalone"
        shutil.copytree(SCRIPTS.parent, copied)
        result = subprocess.run(["uv", "sync", "--system-certs", "--project", str(copied),
                                 "--python", sys.executable, "--default-index", "https://pypi.org/simple"],
                                capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run(["uv", "run", "--project", str(copied), "--locked", "--no-sync",
                                 "python", "-B", str(copied / "scripts" / "inspect_bundles.py"),
                                 plan.sources[0].bundle], capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["bundles"]), 1)
        self.assertTrue((copied / "uv.lock").exists())

    def test_malformed_persisted_record_is_explicit_cli_error(self):
        root = self.root / "broken"
        root.mkdir()
        (root / "ingest.json").write_text('{"schema_version":3,"status":"complete"}', encoding="utf-8")
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "validate_ingest.py"), str(root)],
                                capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ValidationError", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_original_pdf_links_use_flat_retained_copy_and_preserve_import_paths(self):
        text = "<!-- page: 1 -->\n\n[Original PDF](<source/Cours%203.pdf>)\n"
        bundle_root = self.bundle("pdf-link", text)
        (bundle_root / "source" / "same.pdf").rename(bundle_root / "source" / "Cours 3.pdf")
        manifest_path = bundle_root / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["source"].update(name="Cours 3.pdf", path="source/Cours 3.pdf")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        plan = Plan.model_validate({
            "schema_version": 2, "ingest_id": "pdf", "title": "PDF references",
            "destination": str(self.root / "courses" / "pdf-output"), "placement": self.placement(),
            "sources": [{"id": "poly", "bundle": str(bundle_root),
                         "fingerprint": load_bundle(bundle_root).fingerprint}],
            "notes": [{"id": "pdf-course", "type": "course", "title": "PDF",
                       "title_origin": "agent", "order": 1,
                       "parts": [{"source": "poly", "start": 1, "end": 3}]}],
            "relationships": [], "issues": []})
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        self.assertTrue((root / "sources" / "poly" / "Cours 3.pdf").is_file())
        self.assertFalse((root / "sources" / "poly" / "source").exists())
        self.assertEqual((root / "sources" / "poly" / "document.md").read_bytes(), text.encode())
        note = (root / "courses" / "pdf-course.md").read_text(encoding="utf-8")
        self.assertIn("[Original PDF](<../sources/poly/Cours%203.pdf>)", note)
        self.assertIn("[PDF, page 1](sources/poly/Cours%203.pdf#page=1)", (root / "index.md").read_text())
        record = json.loads((root / "ingest.json").read_text())
        self.assertEqual(record["schema_version"], 3)
        self.assertEqual(record["sources"]["poly"]["metadata"]["source"]["path"], "source/Cours 3.pdf")
        self.assertIn("source/Cours 3.pdf", record["sources"]["poly"]["files"])
        self.assertIn("sources/poly/Cours 3.pdf", record["files"])
        self.assertEqual(validate(root)["status"], "validated")

    def test_old_output_version_and_approved_hash_are_not_silently_upgraded(self):
        plan = self.plan()
        for stale in (fingerprint(plan.model_dump()),
                      fingerprint({"output_version": 2, "plan": plan.model_dump()})):
            with self.assertRaisesRegex(ValueError, "including output version"):
                materialize(plan, stale)
        self.assertFalse(Path(plan.destination).exists())
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        record_path = root / "ingest.json"
        record = json.loads(record_path.read_text())
        for version in (1, 2):
            record["schema_version"] = version
            record_path.write_text(json.dumps(record), encoding="utf-8")
            before = {path.relative_to(root): path.read_bytes()
                      for path in root.rglob("*") if path.is_file()}
            with self.assertRaisesRegex(ValueError, "Existing outputs are not migrated"):
                validate(root)
            self.assertEqual(before, {path.relative_to(root): path.read_bytes()
                                     for path in root.rglob("*") if path.is_file()})

    def test_vault_root_outside_and_configuration_placements_are_blocked(self):
        plan = self.plan()
        edits = [
            lambda d: d.update(destination=str(self.root / "root-chapter")),
            lambda d: d.update(destination=str(self.root.parent / "outside-chapter")),
            lambda d: d["placement"].update(parent="."),
            lambda d: d["placement"].update(parent="../outside"),
            lambda d: d["placement"].update(parent=str(self.root / "courses")),
            lambda d: d["placement"].update(parent=".obsidian"),
            lambda d: d["placement"].update(parent=".github"),
            lambda d: d["placement"].update(parent="courses/.git"),
            lambda d: d.update(destination=str(self.root / "courses" / ".obsidian")),
            lambda d: d["placement"].update(vault=str(self.root / "missing-vault")),
            lambda d: d["placement"].update(rationale=""),
        ]
        for edit in edits:
            with self.assertRaises(ValueError):
                check(self.mutate(plan, edit))
        self.assertFalse(Path(plan.destination).exists())
        legacy = plan.model_dump()
        legacy["schema_version"] = 1
        legacy.pop("placement")
        with self.assertRaises(ValueError):
            Plan.model_validate(legacy)
        legacy["schema_version"] = 2
        with self.assertRaises(ValueError):
            Plan.model_validate(legacy)

    def test_parent_creation_is_explicit_read_only_until_approved(self):
        plan = self.plan()
        data = plan.model_dump()
        data["placement"].update(parent="courses/PT/maths", create_parent=False)
        data["destination"] = str(self.root / "courses" / "PT" / "maths" / "chapter")
        with self.assertRaisesRegex(ValueError, "approve create_parent"):
            check(Plan.model_validate(data))
        self.assertFalse((self.root / "courses" / "PT").exists())
        data["placement"]["create_parent"] = True
        approved = Plan.model_validate(data)
        report, _ = check(approved)
        self.assertEqual(report["create_directories"], [
            str(self.root / "courses" / "PT"), str(self.root / "courses" / "PT" / "maths")])
        self.assertEqual(report["placement"]["rationale"], approved.placement.rationale)
        self.assertFalse((self.root / "courses" / "PT").exists())
        materialize(approved, report["plan_sha256"])
        self.assertTrue((Path(approved.destination) / "index.md").is_file())
        self.assertEqual(validate(Path(approved.destination))["status"], "validated")

    def test_placement_changes_invalidate_approval_and_preserve_parent_files(self):
        plan = self.plan()
        changed = self.mutate(plan, lambda d: d["placement"].update(rationale="Different location reasoning."))
        with self.assertRaisesRegex(ValueError, "Plan changed"):
            materialize(changed, plan_hash(plan))
        self.assertFalse(Path(plan.destination).exists())
        parent_file = self.root / "existing-file"
        parent_file.write_bytes(b"keep")
        data = plan.model_dump()
        data["placement"].update(parent="existing-file", create_parent=True)
        data["destination"] = str(parent_file / "chapter")
        with self.assertRaisesRegex(ValueError, "not a directory"):
            check(Plan.model_validate(data))
        self.assertEqual(parent_file.read_bytes(), b"keep")

    def test_placement_cannot_nest_an_ingest_inside_an_existing_one(self):
        plan = self.plan()
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        before = {path.relative_to(root): path.read_bytes()
                  for path in root.rglob("*") if path.is_file()}
        data = plan.model_dump()
        data["placement"]["parent"] = "courses/output/exercices"
        data["destination"] = str(root / "exercices" / "nested-chapter")
        with self.assertRaisesRegex(ValueError, "inside an existing or unrecognized ingest"):
            check(Plan.model_validate(data))
        self.assertEqual(before, {path.relative_to(root): path.read_bytes()
                                 for path in root.rglob("*") if path.is_file()})
        self.assertEqual(validate(root)["status"], "validated")

    def test_every_selected_source_page_gets_a_separate_pdf_fragment(self):
        text = "<!-- page: 3 -->\n\nPrinted page 100.\n\n<!-- page: 5 -->\n\nContinuation.\n"
        source = self.bundle("disjoint-pages", text)
        plan = Plan.model_validate({
            "schema_version": 2, "ingest_id": "pages", "title": "Page references",
            "destination": str(self.root / "courses" / "pages-output"), "placement": self.placement(),
            "sources": [{"id": "poly", "bundle": str(source), "fingerprint": load_bundle(source).fingerprint}],
            "notes": [{"id": "pages-course", "type": "course", "title": "Pages",
                       "title_origin": "agent", "order": 1,
                       "parts": [{"source": "poly", "start": 1, "end": len(MarkdownSource(text).lines)}]}],
            "relationships": [], "issues": []})
        materialize(plan, plan_hash(plan))
        note = (Path(plan.destination) / "courses" / "pages-course.md").read_text()
        self.assertIn("poly: [page 3](../sources/poly/same.pdf#page=3), "
                      "[page 5](../sources/poly/same.pdf#page=5)", note)
        self.assertNotIn("#page=3-5", note)
        self.assertNotIn("#page=100", note)
        self.assertEqual(validate(Path(plan.destination))["status"], "validated")

    def test_exercise_links_to_original_page_two(self):
        text = "<!-- page: 2 -->\n\nCalculate 2 + 2.\n"
        source = self.bundle("page-two-exercise", text)
        plan = Plan.model_validate({
            "schema_version": 2, "ingest_id": "sum", "title": "Exercise",
            "destination": str(self.root / "courses" / "sum-output"), "placement": self.placement(),
            "sources": [{"id": "feuille", "bundle": str(source), "fingerprint": load_bundle(source).fingerprint}],
            "notes": [{"id": "sum-question", "type": "exercise", "title": "Sum",
                       "title_origin": "agent", "order": 1,
                       "parts": [{"source": "feuille", "start": 1, "end": 3,
                                  "role": "question", "id": "q-sum"}]}],
            "relationships": [], "issues": []})
        materialize(plan, plan_hash(plan))
        root = Path(plan.destination)
        self.assertIn("[page 2](../sources/feuille/same.pdf#page=2)",
                      (root / "exercices" / "sum-question.md").read_text())
        self.assertEqual((root / "sources" / "feuille" / "document.md").read_bytes(), text.encode())
        self.assertEqual(validate(root)["status"], "needs_review")


class VaultInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / ".obsidian").mkdir()
        (self.root / ".obsidian" / "private.json").write_text("must not be read")
        chapter = self.root / "courses" / "PT" / "maths" / "existing-chapter"
        chapter.mkdir(parents=True)
        (chapter / "course.md").write_text("---\nlevel: pt\nsubject: maths\n---\n")

    def test_inventory_is_read_only_and_returns_paths_not_note_contents(self):
        before = {path.relative_to(self.root): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}
        with patch.object(Path, "read_text", side_effect=AssertionError("Inventory must not read file contents")):
            report = inspect_vault(self.root)
        self.assertTrue(report["obsidian_marker"])
        chapter = next(item for item in report["directories"]
                       if item["path"] == "courses/PT/maths/existing-chapter")
        self.assertEqual(chapter["markdown_samples"], ["courses/PT/maths/existing-chapter/course.md"])
        self.assertNotIn("must not be read", json.dumps(report))
        self.assertNotIn("subject: maths", json.dumps(report))
        self.assertEqual(before, {path.relative_to(self.root): path.read_bytes()
                                 for path in self.root.rglob("*") if path.is_file()})
        self.assertEqual(report, inspect_vault(self.root))

    def test_limits_are_visible_and_focused_inspection_does_not_escape(self):
        limited = inspect_vault(self.root, depth=1)
        self.assertIn({"path": "courses/PT", "reason": "depth limit"}, limited["omitted"])
        bounded = inspect_vault(self.root, max_directories=1)
        self.assertEqual(len(bounded["directories"]), 1)
        self.assertIn({"path": "courses", "reason": "directory limit"}, bounded["omitted"])
        focused = inspect_vault(self.root, within="courses/PT/maths", depth=1)
        self.assertEqual(focused["scope"], "courses/PT/maths")
        self.assertEqual(len(focused["directories"]), 2)
        for scope in ("../outside", ".obsidian"):
            with self.assertRaises(ValueError):
                inspect_vault(self.root, within=scope)

    def test_cli_inventory_works_without_an_obsidian_installation(self):
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "inspect_vault.py"), str(self.root)],
                                capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["requires_agent_review"])

    def test_existing_ingest_markers_and_sample_limits_are_visible(self):
        chapter = self.root / "courses" / "PT" / "maths" / "existing-chapter"
        (chapter / "ingest.json").write_text("{}")
        (chapter / "second.md").write_text("second note")
        report = inspect_vault(self.root, within="courses/PT/maths/existing-chapter", samples=1)
        self.assertTrue(report["directories"][0]["has_ingest_record"])
        self.assertEqual(report["directories"][0]["markdown_count"], 2)
        self.assertEqual(len(report["directories"][0]["markdown_samples"]), 1)

    def test_redirected_vaults_and_scope_paths_are_blocked(self):
        directory = self.root / "courses"
        redirect = directory.lstat()
        with patch.object(Path, "lstat", return_value=SimpleNamespace(st_mode=0o120777)):
            with self.assertRaisesRegex(ValueError, "Redirected path"):
                inspect_vault(self.root)
        original = Path.lstat

        def linked_scope(path, *args, **kwargs):
            return SimpleNamespace(st_mode=0o120777) if path == directory else original(path, *args, **kwargs)

        with patch.object(Path, "lstat", linked_scope):
            with self.assertRaisesRegex(ValueError, "Redirected path"):
                inspect_vault(self.root, within="courses")
        self.assertEqual(directory.lstat(), redirect)


class MarkdownTests(unittest.TestCase):
    def test_complete_ordered_list_items_are_safe_question_cuts(self):
        source = MarkdownSource("1. First question.\n\n2. Second question.\n")
        self.assertEqual(source.select(1, 2), "1. First question.\n\n")
        self.assertEqual(source.select(3, 3), "2. Second question.\n")

    def test_protected_math_table_code_and_list_boundaries(self):
        constructs = ["$$\nx^2\n$$\n", "| A | B |\n| --- | --- |\n| 1 | 2 |\n",
                      "```python\nprint(1)\n```\n", "- first\n  continued\n- second\n",
                      "> first\n> second\n", "Paragraph\ncontinued.\n"]
        for text in constructs:
            source = MarkdownSource(text)
            with self.subTest(text=text), self.assertRaises(ValueError):
                source.select(1, 1)
            self.assertEqual(source.select(1, len(text.splitlines())), text)

    def test_exact_whitespace_newlines_and_marker_lookalikes(self):
        text = "<!-- page: 1 -->\r\n\r\n```\r\n<!-- page: 1 -->\r\n```\r\n\r\nRepeated.\r\n\r\nRepeated."
        source = MarkdownSource(text)
        self.assertEqual(source.select(1, len(source.lines)), text)
        expected = text[len("<!-- page: 1 -->\r\n"):]
        self.assertEqual(source.rewrite(1, len(source.lines), {}), expected)
        self.assertEqual(len(MarkdownSource("A\u2028B\n").lines), 1)

    def test_asset_rewrites_preserve_prose_code_and_titles(self):
        text = "<!-- page: 1 -->\n\n![Alt](figures/a.png \"Caption\")\n\n`![code](figures/a.png)`\n\n"
        source = MarkdownSource(text)
        output = source.rewrite(1, len(source.lines), {"figures/a.png": "../sources/a/figures/a.png"})
        self.assertIn('![Alt](../sources/a/figures/a.png "Caption")', output)
        self.assertIn("`![code](figures/a.png)`", output)
        self.assertEqual(len(source.links), 1)

    def test_angle_paths_references_external_links_and_unknown_syntax(self):
        source = MarkdownSource("![Alt](<figures/a%20b.png>)\n\n"
                                "![Ref][fig]\n\n[fig]: figures/a.png\n\n[web](https://example.test)\n")
        self.assertEqual({link.path for link in source.links}, {"figures/a b.png", "figures/a.png"})
        output = source.rewrite(1, len(source.lines),
                                {"figures/a b.png": "../sources/a/figures/a%20b.png",
                                 "figures/a.png": "../sources/a/figures/a.png"})
        self.assertIn("https://example.test", output)
        with self.assertRaisesRegex(ValueError, "safely"):
            MarkdownSource("![Alt](figures/a(b).png)\n")
        with self.assertRaises(ValueError):
            MarkdownSource("![Alt](../outside.png)\n")


if __name__ == "__main__":
    unittest.main()
