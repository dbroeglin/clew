"""Preview or install one published chapter from a local Git checkout into a vault."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from document_formats import PublishedRecord
from document_io import (command, contained, digest, fingerprint, json_text,
                         no_redirect, relative_path, require, write_new)
from validate_documents import RECORD, load_record, validate
from vault_placement import missing_parents_in_vault, parent_in_vault


def errors_of(report: dict) -> str:
    return "; ".join(f"{item['path']}: {item['message']}" for item in report["findings"]
                     if item["severity"] == "error")


def draft(source: Path, vault: str, parent: str, name: str | None,
          create_parent: bool) -> tuple[dict, PublishedRecord, Path, list[Path]]:
    source = no_redirect(source)
    require(source.is_dir(), f"Published chapter is missing: {source}")
    record = load_record(source)
    require(isinstance(record, PublishedRecord),
            "Only chapters published with clew-export can be installed this way.")
    validation = validate(source, fidelity=True)
    name = name or source.name
    require(relative_path(name).parts == (name,) and not name.startswith("."),
            "Chapter folder name must be one visible, portable name.")
    parent_dir = parent_in_vault(vault, parent)
    missing = missing_parents_in_vault(vault, parent, create_parent)
    destination = no_redirect(parent_dir / name)
    require(not os.path.lexists(destination), f"Install destination already exists: {destination}")
    require(not destination.is_relative_to(source) and not source.is_relative_to(destination),
            "Install destination must not contain or be inside the downloaded chapter.")
    report = {
        "schema_version": 1,
        "status": "invalid" if validation["errors"] else "needs_review" if validation["reviews"] else "ready",
        "chapter": record.chapter.model_dump(), "source": str(source), "destination": str(destination),
        "create_directories": [str(path) for path in missing], "requires_approval": True,
        "install_sha256": fingerprint({"format_version": 1, "destination": str(destination),
                                       "create_directories": [str(path) for path in missing],
                                       "record": record.model_dump()}),
        "files": sorted([*record.files, RECORD]),
        "errors": validation["errors"], "reviews": validation["reviews"], "findings": validation["findings"],
    }
    return report, record, destination, missing


def install(source: Path, vault: str, parent: str, name: str | None, create_parent: bool,
            expected_hash: str) -> dict:
    report, record, destination, missing = draft(source, vault, parent, name, create_parent)
    require(report["install_sha256"] == expected_hash, "Published chapter or destination changed since approval.")
    require(report["errors"] == 0, "Published chapter is invalid: " + errors_of(report))
    source = no_redirect(source)
    for directory in missing:
        no_redirect(directory)
        directory.mkdir(exist_ok=True)
        require(no_redirect(directory).is_dir(), f"Approved parent is not a directory: {directory}")
    destination.mkdir()
    try:
        for item, expected in record.files.items():
            data = contained(source, item).read_bytes()
            require(digest(data) == expected, f"Published file changed during installation: {item}")
            write_new(contained(destination, item, exists=False), data)
        # The record is written last: its presence marks a complete installation.
        write_new(contained(destination, RECORD, exists=False), json_text(record.model_dump()).encode("utf-8"))
        persisted = validate(destination, fidelity=True)
        require(persisted["errors"] == 0, "Installed chapter failed validation: " + errors_of(persisted))
    except (ValueError, OSError) as error:
        raise ValueError(f"Installation failed; preserve partial output at {destination}: {error}") from error
    return {"schema_version": 1, "status": "installed", "chapter": record.chapter.model_dump(),
            "destination": str(destination), "files": len(record.files) + 1,
            "validation": persisted["status"], "reviews": persisted["reviews"]}


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("chapter", type=Path, help="Published chapter folder, e.g. <clone>/Courses/<chapter-name>")
    cli.add_argument("--vault", required=True, help="Absolute vault root")
    cli.add_argument("--parent", required=True, help="Vault-relative, non-root parent folder")
    cli.add_argument("--name", help="New chapter folder name (default: the published folder name)")
    cli.add_argument("--create-parent", action="store_true", help="Create the approved missing parent folders")
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Preview and validate without writing")
    mode.add_argument("--install-sha256", help="Install only the user-approved checked chapter")
    args = cli.parse_args()
    return command(lambda: draft(args.chapter, args.vault, args.parent, args.name, args.create_parent)[0]
                   if args.check else install(args.chapter, args.vault, args.parent, args.name,
                                              args.create_parent, args.install_sha256))


if __name__ == "__main__":
    raise SystemExit(main())
