"""Check an agent plan or materialize it into a new, wholly owned output root."""
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

from bundle_sources import Bundle
from formats import OUTPUT_VERSION, Plan
from ingest_io import (command, contained, json_text, no_redirect, require,
                       sha256, write_new)
from plan_checks import (check_destination, check_plan, inspect_plan, note_path,
                         output_paths, plan_hash, read_plan)
from render_notes import render_index, render_note
from validate_ingest import validate, verify
from vault_placement import missing_parents


def check(plan: Plan) -> tuple[dict, dict[str, Bundle]]:
    bundles = inspect_plan(plan)
    destination = check_destination(plan, bundles)
    issues = check_plan(plan, bundles)
    return {
        "schema_version": 1, "status": "checked", "destination": str(destination),
        "plan_sha256": plan_hash(plan), "requires_approval": True,
        "placement": plan.placement.model_dump(),
        "create_directories": [str(path) for path in missing_parents(plan)],
        "files": output_paths(plan, bundles), "issues": issues,
    }, bundles


def materialize(plan: Plan, expected_hash: str) -> dict:
    require(plan_hash(plan) == expected_hash, "Plan changed since approval (including output version).")
    report, bundles = check(plan)
    root = check_destination(plan, bundles)
    notes = {note_path(note): render_note(note, plan, bundles) for note in plan.notes}
    notes["index.md"] = render_index(plan, report["issues"], bundles)
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in notes.items()}
    snapshots = {}
    for source, bundle in bundles.items():
        snapshots[source] = {"metadata": bundle.metadata, "files": bundle.files,
                             "fingerprint": bundle.fingerprint}
        hashes.update({f"sources/{source}/{bundle.retained_path(name)}": digest
                       for name, digest in bundle.files.items()})
    record = {"schema_version": OUTPUT_VERSION, "status": "writing", "plan": plan.model_dump(),
              "plan_sha256": expected_hash, "sources": snapshots,
              "issues": report["issues"], "files": hashes}
    initial = json_text(record).encode("utf-8")
    for directory in missing_parents(plan):
        no_redirect(directory)
        directory.mkdir(exist_ok=True)
        no_redirect(directory)
        require(directory.is_dir(), f"Placement parent is not a directory: {directory}")
    root.mkdir()
    record_path = root / "ingest.json"
    try:
        write_new(record_path, initial)
        for name, data in notes.items():
            write_new(contained(root, name, exists=False), data)
        for source, bundle in bundles.items():
            for name, digest in bundle.files.items():
                target = contained(root, f"sources/{source}/{bundle.retained_path(name)}", exists=False)
                target.parent.mkdir(parents=True, exist_ok=True)
                no_redirect(target)
                with contained(bundle.root, name).open("rb") as incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
                require(sha256(target) == digest, f"Source changed during copy: {source}/{name}")
        inspect_plan(plan)
        verify(root, record, incomplete=True)
        require(record_path.read_bytes() == initial, "Ingest record changed during execution.")
        record["status"] = "complete"
        pending = contained(root, "ingest.json.pending", exists=False)
        write_new(pending, json_text(record).encode("utf-8"))
        no_redirect(record_path)
        require(record_path.read_bytes() == initial, "Ingest record changed before completion.")
        pending.replace(record_path)
        return validate(root)
    except (ValueError, OSError, UnicodeError) as error:
        raise ValueError(f"Ingest failed; preserve partial output at {root}: {error}") from error


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("plan", type=Path)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Read-only validation; no output writes")
    mode.add_argument("--plan-sha256", help="Materialize the exact user-approved plan hash")
    args = cli.parse_args()

    def execute():
        plan = read_plan(args.plan)
        if args.check:
            return check(plan)[0]
        return materialize(plan, args.plan_sha256)

    return command(execute)


if __name__ == "__main__":
    raise SystemExit(main())
