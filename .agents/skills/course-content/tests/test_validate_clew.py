"""Synthetic Clew vaults; no real course PDFs or learner records are used."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_clew.py"
SPEC = importlib.util.spec_from_file_location("validate_clew", SCRIPT)
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def link(path):
    return f"[[{path.removesuffix('.md')}]]"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class Vault:
    def __init__(self, root, whole_pdf=False):
        self.root = root
        self.prefix = "courses/mechanics"
        self.entry = f"{self.prefix}/course.md"
        self.chapter_paths = [f"{self.prefix}/chapters/{name}.md" for name in ("motion", "forces")]
        self.section_paths = [
            f"{self.prefix}/sections/{name}.md" for name in ("distance", "average-speed", "forces")
        ]
        self.ratios = "concepts/math-ratios.md"
        self.speed = "concepts/physics-average-speed.md"
        self.notes = {}
        self.body_edits = {}
        self.pdfs = {}
        self.assets = {f"{self.prefix}/assets/diagram.png": b"synthetic-image"}
        self.source_path = f"{self.prefix}/support/source-map.json"
        self.report_path = f"{self.prefix}/support/verification.json"
        self.source_map = {
            "schema": "clew-source-map/v1", "course_id": "course.mechanics",
            "sources": [], "sections": [],
        }
        source_names = [("mechanics", 3)] if whole_pdf else [("motion", 2), ("forces", 1)]
        for name, count in source_names:
            path = f"{self.prefix}/sources/{name}.pdf"
            self.pdfs[path] = f"%PDF-1.4\nSynthetic {name} fixture, not a transcription.\n%%EOF".encode()
            self.source_map["sources"].append({
                "id": f"source.mechanics.{name}", "filename": f"{name}.pdf",
                "path": path, "sha256": digest(self.pdfs[path]), "page_count": count,
                "citation": "Original synthetic test material.",
                "edition": None, "omission_reason": None,
            })
        for index, path in enumerate(self.section_paths):
            name = Path(path).stem
            source_name = "mechanics" if whole_pdf else "motion" if index < 2 else "forces"
            page = index + 1 if whole_pdf or index < 2 else 1
            metadata = self.note("section", f"section.mechanics.{name}", name.title())
            metadata.update({
                "course": link(self.entry),
                "parent": link(self.chapter_paths[0 if index < 2 else 1]),
                "previous": link(self.section_paths[index - 1]) if index else None,
                "next": link(self.section_paths[index + 1]) if index < 2 else None,
                "source_refs": [f"[[{self.prefix}/sources/{source_name}.pdf#page={page}]]"],
                "fidelity": "verified",
            })
            if index == 0:
                metadata["teaches"] = [link(self.ratios)]
            if index == 1:
                metadata["teaches"] = [link(self.speed)]
                metadata["prerequisites"] = [link(self.ratios)]
            self.notes[path] = metadata
            self.source_map["sections"].append({
                "id": metadata["id"], "path": path,
                "spans": [{"source_id": f"source.mechanics.{source_name}", "page_start": page, "page_end": page}],
            })
        for index, path in enumerate(self.chapter_paths):
            metadata = self.note("chapter", f"chapter.mechanics.{index + 1}", Path(path).stem.title())
            metadata.update({
                "course": link(self.entry), "parent": link(self.entry),
                "children": [link(item) for item in (self.section_paths[:2] if index == 0 else self.section_paths[2:])],
                "source_refs": list(self.notes[self.section_paths[0 if index == 0 else 2]]["source_refs"]),
            })
            self.notes[path] = metadata
        self.notes[self.entry] = {
            **self.note("course", "course.mechanics", "Mechanics"),
            "children": [link(path) for path in self.chapter_paths],
            "source_refs": [self.notes[self.section_paths[0]]["source_refs"][0]] + (
                [] if whole_pdf else [self.notes[self.section_paths[2]]["source_refs"][0]]
            ),
        }
        self.notes[self.ratios] = {
            **self.note("concept", "concept.math.ratios", "Ratios"),
            "evidence": [link(self.section_paths[0])],
        }
        self.notes[self.speed] = {
            **self.note("concept", "concept.physics.average-speed", "Average speed"),
            "evidence": [link(self.section_paths[1])], "prerequisites": [link(self.ratios)],
        }

    @staticmethod
    def note(kind, identity, title):
        return {"schema": "clew/v1", "id": identity, "kind": kind, "title": title,
                "summary": "A short, synthetic retrieval summary."}

    def put(self, path, raw):
        destination = self.root.joinpath(*path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)

    def json(self, path, value):
        self.put(path, (json.dumps(value, indent=2) + "\n").encode())

    def body(self, path, data):
        lines = [f"# {data['title']}", ""]
        if data["kind"] == "concept":
            lines += [
                "## Definition", "", "This is a self-contained synthetic concept definition.",
                "", "## Evidence", "",
            ]
        else:
            lines += ["A complete synthetic explanation with its assumptions and example.", ""]
        if "children" in data:
            lines += ["## Contents", ""]
            lines += [f"{index}. {child} - A short retrieval summary." for index, child in enumerate(data["children"], 1)]
            lines += ["", "## Navigation", ""]
        for field in ("course", "parent", "previous", "next", "source_refs", "evidence", *validator.RELATIONS):
            if field not in data or data[field] is None:
                continue
            values = data[field] if isinstance(data[field], list) else [data[field]]
            lines += [f"{field}: {target}. This link supplies the stated context." for target in values]
        if path == self.section_paths[0]:
            lines += ["", f"![Synthetic diagram]({self.prefix}/assets/diagram.png)", ""]
        if data.get("fidelity") in {"partial", "needs-review"}:
            lines += ["", "Content limitation: this synthetic source still needs review.", ""]
        body = "\n".join(lines) + "\n"
        return self.body_edits[path](body) if path in self.body_edits else body

    def write(self):
        for path, raw in {**self.pdfs, **self.assets}.items():
            self.put(path, raw)
        for path, data in self.notes.items():
            raw = "---\n" + yaml.safe_dump(data, sort_keys=False) + "---\n\n" + self.body(path, data)
            self.put(path, raw.encode())
        self.json(self.source_path, self.source_map)
        report = {
            "schema": "clew-verification/v1", "course_id": "course.mechanics",
            "source_map_sha256": digest(self.root.joinpath(*self.source_path.split("/")).read_bytes()),
            "sections": [], "pages": [],
        }
        for path in self.section_paths:
            data = self.notes[path]
            state = data["fidelity"]
            report["sections"].append({
                "id": data["id"], "markdown_sha256": digest(self.root.joinpath(*path.split("/")).read_bytes()),
                "fidelity": state, "checks": ["Compared synthetic fixture content."] if state == "verified" else [],
                "limitations": [] if state == "verified" else ["Synthetic source comparison is unfinished."],
            })
        for source in self.source_map["sources"]:
            for page in range(1, source["page_count"] + 1):
                assigned = set()
                for record in self.source_map["sections"]:
                    spans = record["spans"] + [
                        span for alternate in record.get("alternatives", []) for span in alternate["spans"]
                    ]
                    if any(span["source_id"] == source["id"] and span["page_start"] <= page <= span["page_end"] for span in spans):
                        assigned.add(record["id"])
                report["pages"].append({
                    "source_id": source["id"], "page": page,
                    "status": "mapped" if assigned else "excluded",
                    "section_ids": sorted(assigned), "reason": None if assigned else "Outside the synthetic conversion scope.",
                })
        self.json(self.report_path, report)
        return report

    def validate(self, strict=False):
        return validator.validate_course(self.root, "mechanics", strict)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="clew-validator-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vault = Vault(self.root)

    def assert_code(self, result, code):
        self.assertFalse(result["ok"], result)
        self.assertIn(code, {error["code"] for error in result["errors"]}, result)

    def test_valid_course_in_both_modes_and_read_only(self):
        self.vault.write()
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        for strict in (False, True):
            result = self.vault.validate(strict)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["warnings"], [])
            self.assertEqual(result["scope"]["concepts"], sorted([self.vault.ratios, self.vault.speed]))
        after = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_whole_course_pdf_keeps_note_structure(self):
        alternate = Vault(self.root / "whole", whole_pdf=True)
        alternate.write()
        self.assertEqual(self.vault.section_paths, alternate.section_paths)
        self.assertEqual(
            [self.vault.notes[path]["id"] for path in self.vault.section_paths],
            [alternate.notes[path]["id"] for path in alternate.section_paths],
        )
        result = alternate.validate(True)
        self.assertTrue(result["ok"], result)

    def test_one_section_can_span_multiple_pdfs(self):
        section = self.vault.section_paths[1]
        extra = {"source_id": "source.mechanics.forces", "page_start": 1, "page_end": 1}
        self.vault.source_map["sections"][1]["spans"].append(extra)
        reference = f"[[{self.vault.prefix}/sources/forces.pdf#page=1]]"
        self.vault.notes[section]["source_refs"].append(reference)
        self.vault.notes[self.vault.chapter_paths[0]]["source_refs"].append(reference)
        self.vault.write()
        result = self.vault.validate(True)
        self.assertTrue(result["ok"], result)

    def test_equivalent_whole_pdf_is_not_another_transcription(self):
        path = f"{self.vault.prefix}/sources/whole.pdf"
        raw = b"%PDF-1.4\nEquivalent synthetic whole-course material.\n%%EOF"
        self.vault.pdfs[path] = raw
        self.vault.source_map["sources"].append({
            "id": "source.mechanics.whole", "filename": "whole.pdf", "path": path,
            "sha256": digest(raw), "page_count": 3, "citation": "Equivalent synthetic material.",
            "edition": None, "omission_reason": None,
        })
        for index, section in enumerate(self.vault.source_map["sections"], 1):
            section["alternatives"] = [{
                "spans": [{"source_id": "source.mechanics.whole", "page_start": index, "page_end": index}],
                "equivalence_evidence": "Compared the corresponding synthetic source content.",
            }]
        self.vault.write()
        result = self.vault.validate(True)
        self.assertTrue(result["ok"], result)

    def test_pdfs_are_hashed_without_reading_them_into_the_note_cache(self):
        self.vault.write()
        original = validator.ClewValidator.read

        def guarded(instance, name):
            self.assertFalse(name.lower().endswith(".pdf"))
            return original(instance, name)

        with mock.patch.object(validator.ClewValidator, "read", guarded):
            self.assertTrue(self.vault.validate()["ok"])

    def test_pdf_filename_case_and_spaces_are_preserved(self):
        source = self.vault.source_map["sources"][0]
        old = source["path"]
        new = f"{self.vault.prefix}/sources/Motion Original.PDF"
        source["path"] = new
        self.vault.pdfs[new] = self.vault.pdfs.pop(old)
        for note in self.vault.notes.values():
            if "source_refs" in note:
                note["source_refs"] = [value.replace(old, new) for value in note["source_refs"]]
        self.vault.write()
        result = self.vault.validate(True)
        self.assertTrue(result["ok"], result)

    def test_chunk_size_is_a_warning_not_a_hard_split(self):
        self.vault.body_edits[self.vault.section_paths[0]] = lambda body: body + "\n" + "word " * 1300
        self.vault.write()
        result = self.vault.validate(True)
        self.assertTrue(result["ok"], result)
        self.assertIn("chunk-size", {item["code"] for item in result["warnings"]})

    def test_drafts_warn_and_strict_rejects(self):
        for state in ("needs-review", "partial"):
            with self.subTest(state=state):
                self.vault.notes[self.vault.section_paths[1]]["fidelity"] = state
                self.vault.write()
                result = self.vault.validate()
                self.assertTrue(result["ok"], result)
                self.assertIn("fidelity", {item["code"] for item in result["warnings"]})
                self.assert_code(self.vault.validate(True), "fidelity")

    def test_unresolved_page_warns_and_strict_rejects(self):
        report = self.vault.write()
        report["pages"][0].update(status="unresolved", reason="A source region remains unreadable.")
        self.vault.json(self.vault.report_path, report)
        result = self.vault.validate()
        self.assertTrue(result["ok"], result)
        self.assertIn("coverage", {item["code"] for item in result["warnings"]})
        self.assert_code(self.vault.validate(True), "coverage")

    def test_sequence_crosses_chapter_boundary(self):
        self.vault.notes[self.vault.section_paths[1]]["next"] = None
        self.vault.write()
        self.assert_code(self.vault.validate(), "sequence")

    def test_missing_and_duplicate_children(self):
        for children in ([link(self.vault.section_paths[0])], [link(self.vault.section_paths[0])] * 2):
            with self.subTest(children=children):
                self.vault.notes[self.vault.chapter_paths[0]]["children"] = children
                self.vault.write()
                self.assertFalse(self.vault.validate()["ok"])

    def test_wrong_parent(self):
        self.vault.notes[self.vault.section_paths[0]]["parent"] = link(self.vault.chapter_paths[1])
        self.vault.write()
        self.assert_code(self.vault.validate(), "hierarchy")

    def test_stale_visible_contents(self):
        self.vault.body_edits[self.vault.entry] = lambda body: body.replace("1. ", "Not an ordered item: ", 1)
        self.vault.write()
        self.assert_code(self.vault.validate(), "contents")

    def test_invisible_navigation(self):
        self.vault.body_edits[self.vault.section_paths[1]] = lambda body: body.replace(
            f"previous: {link(self.vault.section_paths[0])}", "previous: missing"
        )
        self.vault.write()
        self.assert_code(self.vault.validate(), "visible-link")

    def test_missing_or_unknown_note_schema(self):
        for marker in (None, "clew-sectioned/v1", "clew/v9"):
            with self.subTest(marker=marker):
                self.vault.notes[self.vault.entry]["schema"] = marker
                self.vault.write()
                self.assert_code(self.vault.validate(), "schema")

    def test_duplicate_ids_and_wrong_role(self):
        first, second = self.vault.section_paths[:2]
        self.vault.notes[second]["id"] = self.vault.notes[first]["id"]
        self.vault.write()
        self.assert_code(self.vault.validate(), "identity")

    def test_valid_metadata_in_wrong_directory_is_rejected(self):
        self.vault.write()
        concept = self.root.joinpath(*self.vault.speed.split("/")).read_bytes()
        self.vault.put(self.vault.section_paths[2], concept)
        self.assert_code(self.vault.validate(), "kind")

    def test_shared_concept_cannot_have_course_owner(self):
        self.vault.notes[self.vault.speed]["course"] = link(self.vault.entry)
        self.vault.write()
        self.assert_code(self.vault.validate(), "schema")

    def test_concept_requires_actual_definition(self):
        self.vault.body_edits[self.vault.speed] = lambda body: body.replace(
            "This is a self-contained synthetic concept definition.", f"!{link(self.vault.section_paths[1])}"
        )
        self.vault.write()
        self.assert_code(self.vault.validate(), "definition")

    def test_concept_evidence_must_be_a_section(self):
        self.vault.notes[self.vault.speed]["evidence"] = [link(self.vault.entry)]
        self.vault.write()
        self.assert_code(self.vault.validate(), "kind")

    def test_prerequisite_cycles_fail_but_related_cycles_pass(self):
        self.vault.notes[self.vault.ratios]["prerequisites"] = [link(self.vault.speed)]
        self.vault.write()
        self.assert_code(self.vault.validate(), "prerequisite-cycle")
        del self.vault.notes[self.vault.ratios]["prerequisites"]
        self.vault.notes[self.vault.ratios]["related"] = [link(self.vault.speed)]
        self.vault.notes[self.vault.speed]["related"] = [link(self.vault.ratios)]
        self.vault.write()
        self.assertTrue(self.vault.validate()["ok"])

    def test_external_evidence_is_bounded(self):
        target = "courses/algebra/sections/ratios.md"
        data = dict(self.vault.notes[self.vault.section_paths[0]])
        data["id"] = "section.algebra.ratios"
        self.vault.put(target, ("---\n" + yaml.safe_dump(data) + "---\n# Ratios\n\nAn external explanation.\n").encode())
        self.vault.put("courses/algebra/sections/unrelated.md", b"Invalid unrelated course data.")
        self.vault.put("concepts/unrelated.md", b"Invalid unrelated concept data.")
        self.vault.notes[self.vault.ratios]["evidence"] = [link(target)]
        self.vault.write()
        result = self.vault.validate(True)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["scope"]["external_notes"], [target])
        self.assertNotIn("concepts/unrelated.md", result["scope"]["concepts"])
        self.assertIn("external-evidence", {item["code"] for item in result["warnings"]})

    def test_missing_concept_and_course_local_concept_fail(self):
        self.vault.notes[self.vault.section_paths[0]]["teaches"] = ["[[concepts/absent]]"]
        self.vault.write()
        self.assert_code(self.vault.validate(), "missing")
        self.vault.put(f"{self.vault.prefix}/concepts/local.md", b"# Not a shared concept")
        self.assert_code(self.vault.validate(), "layout")

    def test_hashes_are_binding(self):
        for relative in (
            self.vault.section_paths[0],
            self.vault.source_path,
            next(iter(self.vault.pdfs)),
        ):
            with self.subTest(path=relative):
                self.vault.write()
                path = self.root.joinpath(*relative.split("/"))
                path.write_bytes(path.read_bytes() + b"\n")
                self.assert_code(self.vault.validate(), "hash")

    def test_note_and_report_fidelity_must_agree(self):
        report = self.vault.write()
        report["sections"][0].update(fidelity="partial", limitations=["Untranscribed source region."])
        self.vault.json(self.vault.report_path, report)
        self.assert_code(self.vault.validate(), "fidelity")

    def test_verified_needs_evidence_and_no_limitations(self):
        report = self.vault.write()
        report["sections"][0]["checks"] = []
        self.vault.json(self.vault.report_path, report)
        self.assert_code(self.vault.validate(), "schema")

    def test_missing_and_duplicate_page_records(self):
        for change in ("missing", "duplicate", "assignment"):
            with self.subTest(change=change):
                report = self.vault.write()
                if change == "missing":
                    report["pages"].pop()
                elif change == "duplicate":
                    report["pages"].append(report["pages"][0])
                else:
                    report["pages"][0]["section_ids"] = ["section.mechanics.forces"]
                self.vault.json(self.vault.report_path, report)
                self.assertFalse(self.vault.validate()["ok"])

    def test_source_span_bounds_and_printed_labels(self):
        span = self.vault.source_map["sections"][0]["spans"][0]
        for change in ({"page_end": 99}, {"page_start": 2, "page_end": 1}, {"printed_pages": {"9": "iv"}}):
            with self.subTest(change=change):
                span.clear()
                span.update(source_id="source.mechanics.motion", page_start=1, page_end=1)
                span.update(change)
                self.vault.write()
                self.assert_code(self.vault.validate(), "source-span")

    def test_source_refs_must_match_map(self):
        self.vault.notes[self.vault.section_paths[0]]["source_refs"] = [
            f"[[{self.vault.prefix}/sources/motion.pdf#page=2]]"
        ]
        self.vault.write()
        self.assert_code(self.vault.validate(), "source-refs")

    def test_missing_section_mapping(self):
        self.vault.source_map["sections"].pop()
        self.vault.write()
        self.assert_code(self.vault.validate(), "source")

    def test_omitted_pdf_has_citations_and_warning_even_in_strict(self):
        source = self.vault.source_map["sources"][0]
        del self.vault.pdfs[source["path"]]
        source.update(path=None, omission_reason="Not included in this synthetic distribution.")
        for path, note in self.vault.notes.items():
            if "source_refs" in note:
                note["source_refs"] = [value for value in note["source_refs"] if "/motion.pdf" not in value]
                self.vault.body_edits[path] = lambda body: body + "\nSource: motion.pdf, physical pages 1-2; PDF omitted.\n"
        self.vault.write()
        result = self.vault.validate(True)
        self.assertTrue(result["ok"], result)
        self.assertIn("source-omitted", {item["code"] for item in result["warnings"]})

    def test_missing_asset_and_orphan_asset(self):
        self.vault.assets[f"{self.vault.prefix}/assets/orphan.png"] = b"unused"
        self.vault.write()
        self.assert_code(self.vault.validate(), "asset")
        self.root.joinpath(*f"{self.vault.prefix}/assets/diagram.png".split("/")).unlink()
        self.assertFalse(self.vault.validate()["ok"])

    def test_item_mapping_anchor_and_containment(self):
        self.vault.source_map["sections"][0]["items"] = [{
            "anchor": "Distance", "spans": [
                {"source_id": "source.mechanics.motion", "page_start": 1, "page_end": 1, "rect": [0, 0, 10, 10]}
            ],
            "asset_path": f"{self.vault.prefix}/assets/diagram.png",
        }]
        self.vault.write()
        self.assertTrue(self.vault.validate()["ok"])
        self.vault.source_map["sections"][0]["items"][0]["spans"][0].update(page_start=2, page_end=2)
        self.vault.write()
        self.assert_code(self.vault.validate(), "source-span")

    def test_native_links_code_examples_and_pdf_selection(self):
        target = self.vault.section_paths[0]
        self.vault.body_edits[target] = lambda body: body + (
            "\nA stable paragraph. ^stable\n\n[[#^stable]]\n"
            f"\n[Heading]({target}#Distance)\n"
            f"\n[Referenced][sample]\n\n[sample]: {target}#Distance\n"
            f"\n[[{self.vault.prefix}/sources/motion.pdf#page=1&selection=0,0,1,2]]\n"
            "\n`[[model/private]]`\n\n```markdown\n[[model/private]]\n```\n"
            "\n[External citation](https://example.com/source)\n"
        )
        self.vault.write()
        result = self.vault.validate()
        self.assertTrue(result["ok"], result)

    def test_missing_and_ambiguous_anchors(self):
        for suffix in (
            "\n[[#Absent]]\n",
            "\n## Duplicate\n\nOne.\n\n## Duplicate\n\nTwo.\n\n[[#Duplicate]]\n",
            "\n[Missing reference][undefined]\n",
        ):
            with self.subTest(suffix=suffix):
                self.vault.body_edits[self.vault.section_paths[0]] = lambda body, suffix=suffix: body + suffix
                self.vault.write()
                self.assertFalse(self.vault.validate()["ok"])

    def test_noncanonical_and_private_links_are_rejected_without_read(self):
        private = self.root / "model" / "private.md"
        self.vault.put("model/private.md", b"Must never be read.")
        original = Path.read_bytes
        for target in (
            "model/private.md", "../../model/private.md", "distance",
            "courses/mechanics/../../model/private.md", "courses/mechanics/%2e%2e/secret.md",
            "courses/mechanics/%252e%252e/secret.md", "C:\\private.md", "//server/share/private.md",
        ):
            with self.subTest(target=target):
                self.vault.body_edits[self.vault.section_paths[0]] = lambda body, target=target: body + f"\n[[{target}]]\n"
                self.vault.write()

                def guarded(path):
                    self.assertNotEqual(path, private)
                    return original(path)

                with mock.patch.object(Path, "read_bytes", guarded):
                    self.assertFalse(self.vault.validate()["ok"])

    def test_unsafe_source_paths_are_rejected(self):
        self.vault.source_map["sources"][0]["path"] = "model/private.pdf"
        self.vault.write()
        self.assert_code(self.vault.validate(), "source")

    def test_case_mismatch(self):
        self.vault.notes[self.vault.speed]["evidence"] = [
            "[[courses/mechanics/sections/Average-speed]]"
        ]
        self.vault.write()
        self.assert_code(self.vault.validate(), "case")

    def test_symlinks_do_not_escape_the_scope(self):
        self.vault.write()
        target = self.root / "private.md"
        target.write_text("private", encoding="utf-8")
        path = self.root / "concepts" / "linked.md"
        try:
            path.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"Symlink creation not available: {exc}")
        self.vault.notes[self.vault.speed]["related"] = ["[[concepts/linked]]"]
        self.vault.write()
        self.assert_code(self.vault.validate(), "path")

    def test_duplicate_yaml_and_json_keys_are_errors(self):
        self.vault.write()
        entry = self.root.joinpath(*self.vault.entry.split("/"))
        entry.write_bytes(entry.read_bytes().replace(b"schema: clew/v1", b"schema: clew/v1\nschema: clew/v1"))
        self.assert_code(self.vault.validate(), "metadata")
        self.vault.write()
        self.vault.put(self.vault.source_path, b'{"schema":"clew-source-map/v1","schema":"clew-source-map/v1"}')
        self.assert_code(self.vault.validate(), "json")

    def test_cli_json_and_exit_codes(self):
        self.vault.notes[self.vault.section_paths[1]]["fidelity"] = "needs-review"
        self.vault.write()
        command = [sys.executable, str(SCRIPT), "--vault", str(self.root), "--course", "mechanics"]
        for extra, status in (([], 0), (["--strict"], 1)):
            with self.subTest(extra=extra):
                process = subprocess.run(command + extra, cwd=self.root, text=True, capture_output=True, check=False)
                self.assertEqual(process.returncode, status, process.stderr + process.stdout)
                result = json.loads(process.stdout)
                self.assertEqual(result["ok"], status == 0)
                self.assertEqual(process.stderr, "")
        process = subprocess.run([sys.executable, str(SCRIPT), "--package", str(self.root)],
                                 text=True, capture_output=True, check=False)
        self.assertEqual(process.returncode, 2)

    def test_bad_api_arguments_and_missing_dependencies(self):
        for course, strict in (("../outside", False), ("Mechanics", False), ("mechanics", "strict")):
            self.assert_code(validator.validate_course(self.root, course, strict), "argument")
        with mock.patch.object(validator, "yaml", None):
            result = self.vault.validate()
            self.assert_code(result, "dependency")
            self.assertIn("uv add --project", result["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
