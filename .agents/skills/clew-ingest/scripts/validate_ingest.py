"""Validate a persisted ingest using only its retained sources and approved plan."""
from __future__ import annotations

import argparse
from pathlib import Path

from bundle_sources import load_snapshot
from content_projection import verify_projection
from formats import OUTPUT_VERSION, IngestRecord, Plan
from ingest_io import command, contained, no_redirect, read_json, require, sha256
from plan_checks import check_plan, note_path, output_paths, plan_hash
from render_notes import render_index, render_note


def verify(root: Path, record: dict, *, incomplete: bool = False) -> dict:
    root = no_redirect(root)
    require(isinstance(record, dict), "Invalid ingest record.")
    require(type(record.get("schema_version")) is int and record["schema_version"] == OUTPUT_VERSION,
            f"Unsupported ingest output version; expected {OUTPUT_VERSION}. "
            "Existing outputs are not migrated; create a fresh approved ingest.")
    IngestRecord.model_validate(record)
    require(isinstance(record, dict)
            and set(record) == {"schema_version", "status", "plan", "plan_sha256",
                                "sources", "issues", "files"},
            "Invalid ingest record.")
    require(record["status"] == "complete" or
            (incomplete and record["status"] == "writing"), "Ingest is incomplete.")
    plan = Plan.model_validate(record["plan"])
    require(plan_hash(plan) == record["plan_sha256"], "Persisted plan fingerprint differs.")
    require(isinstance(record["sources"], dict) and isinstance(record["files"], dict),
            "Invalid retained-source/file records.")
    require(set(record["sources"]) == {source.id for source in plan.sources},
            "Retained sources differ from the plan.")
    bundles = {source: load_snapshot(no_redirect(root / "sources" / source), snapshot)
               for source, snapshot in record["sources"].items()}
    issues = check_plan(plan, bundles)
    require(issues == record["issues"], "Persisted review issues differ from the plan.")
    expected = output_paths(plan, bundles)
    require(set(record["files"]) == set(expected) - {"ingest.json"}, "Owned files differ from the plan.")
    expected_dirs = set()
    for name in expected:
        expected_dirs.update(str(parent).replace("\\", "/")
                             for parent in Path(name).parents if str(parent) != ".")
    found = set()

    def walk(directory: Path) -> None:
        for child in directory.iterdir():
            no_redirect(child)
            name = child.relative_to(root).as_posix()
            if child.is_dir():
                require(name in expected_dirs, f"Unexpected directory: {name}")
                walk(child)
            else:
                require(child.is_file(), f"Unexpected filesystem entry: {name}")
                found.add(name)

    walk(root)
    require(found == set(expected), f"Missing/unexpected owned files: {sorted(found ^ set(expected))}")
    for name, digest in record["files"].items():
        require(isinstance(digest, str) and sha256(contained(root, name)) == digest,
                f"Output file changed: {name}")
    for note in plan.notes:
        content = contained(root, note_path(note)).read_bytes()
        verify_projection(content.decode("utf-8"), note, bundles)
        require(content == render_note(note, plan, bundles),
                f"Content/metadata fidelity differs: {note.id}")
    require(contained(root, "index.md").read_bytes() == render_index(plan, issues, bundles),
            "Ingest index differs from the plan.")
    return {"schema_version": 1, "status": "needs_review" if issues else "validated",
            "root": str(root), "ingest_id": plan.ingest_id, "files": expected,
            "issues": issues, "plan_sha256": record["plan_sha256"]}


def validate(root: Path) -> dict:
    return verify(root, read_json(contained(root, "ingest.json")))


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("ingest", type=Path)
    args = cli.parse_args()
    return command(lambda: validate(args.ingest))


if __name__ == "__main__":
    raise SystemExit(main())
