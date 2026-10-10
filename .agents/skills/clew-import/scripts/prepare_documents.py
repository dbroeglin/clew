"""Preview or execute an approved, source-preserving whole-document preparation."""
from __future__ import annotations

import argparse
import difflib
import os
from pathlib import Path
import posixpath
import shutil

from bundle_sources import Bundle, load_bundle
from document_edits import (address_link, check_operations, compile_document,
                            document_path, escape_text, frontmatter, relative_link)
from document_formats import Plan, PreparationRecord, PreparedSource
from document_io import (command, contained, digest, fingerprint, json_text,
                         no_redirect, read_json, relative_path, require, sha256, write_new)
from validate_documents import FileData, validate, validate_files
from vault_placement import missing_parents, placement_parent


def plan_hash(plan: Plan) -> str:
    return fingerprint({"format_version": 1, "plan": plan.model_dump()})


def inspect_plan(plan: Plan) -> dict[str, Bundle]:
    bundles = {}
    for document in plan.documents:
        require(document.id not in bundles, f"Duplicate document ID: {document.id}")
        require(Path(document.bundle).is_absolute(), "Conversion bundle paths must be absolute.")
        bundle = load_bundle(Path(document.bundle))
        require(bundle.fingerprint == document.fingerprint, f"Converted source changed: {document.id}")
        bundles[document.id] = bundle
    require(len({str(bundle.root).casefold() for bundle in bundles.values()}) == len(bundles),
            "The same conversion bundle was selected twice.")
    return bundles


def check_destination(plan: Plan, bundles: dict[str, Bundle]) -> Path:
    require(Path(plan.destination).is_absolute(), "Preparation destination must be absolute.")
    root = no_redirect(Path(plan.destination))
    require(not os.path.lexists(root), f"Preparation destination already exists: {root}")
    relative_path(root.name)
    require(not root.name.startswith("."), "Chapter destination must be visible.")
    require(root.parent == placement_parent(plan), "Chapter must be a direct child of its approved vault parent.")
    missing_parents(plan)
    require(all(not root.is_relative_to(bundle.root) and not bundle.root.is_relative_to(root)
                for bundle in bundles.values()), "Preparation must not contain or be inside a selected input bundle.")
    return root


def render_index(plan: Plan, sources: list[PreparedSource], findings: list) -> bytes:
    text = frontmatter({"clew_schema": 1, "type": "chapter", "id": plan.id, "title": plan.title}, "\n")
    text += "# " + escape_text(plan.title) + "\n\n## Documents\n\n"
    for source in sources:
        label = f"{source.role}: {posixpath.basename(source.path)[:-3]}"
        pdf = posixpath.join(posixpath.dirname(source.path), source.pdf)
        text += "- " + relative_link("index.md", source.path, escape_text(label))
        text += " / " + relative_link("index.md", pdf, "PDF", f"#page={source.pages[0]}") + "\n"
    if findings:
        text += "\n## Review required\n\n"
        text += "These are generated Clew findings, not source-authored content.\n\n"
        for finding in findings:
            fragment = "#^" + finding.anchor if finding.anchor else ""
            text += "- " + relative_link("index.md", finding.path, escape_text(finding.code), fragment)
            text += ": " + escape_text(finding.message) + "\n"
    return text.encode("utf-8")


def draft(plan: Plan) -> tuple[dict, dict[str, FileData], PreparationRecord]:
    bundles = inspect_plan(plan)
    root = check_destination(plan, bundles)
    paths = {document.id: document_path(document, bundles[document.id]) for document in plan.documents}
    require(len({path.casefold() for path in paths.values()}) == len(paths),
            "Document folders/filenames collide; explicitly approve distinct folder names.")
    require(len({posixpath.dirname(path).casefold() for path in paths.values()}) == len(paths),
            "Each PDF needs its own document folder.")
    check_operations(plan, bundles)
    files: dict[str, FileData] = {}
    sources = []
    findings = []
    previews = []
    for document in plan.documents:
        bundle, path = bundles[document.id], paths[document.id]
        compiled = compile_document(document, bundle, path, paths)
        files[path] = compiled.text.encode("utf-8")
        baseline = f".clew/baselines/{document.id}/document.md"
        files[baseline] = contained(bundle.root, "document.md").read_bytes()
        retained = {}
        for name, expected in bundle.files.items():
            if name == "document.md":
                continue
            relative = bundle.source["name"] if name == bundle.source["path"] else name
            target = posixpath.join(posixpath.dirname(path), relative)
            require(target not in files, "Retained source collides with the editable note.")
            files[target] = contained(bundle.root, name)
            retained[relative] = expected
        sources.append(PreparedSource(
            id=document.id, path=path, role=document.role, pdf=bundle.source["name"],
            page_count=bundle.source["page_count"], pages=bundle.pages, baseline=baseline,
            baseline_sha256=bundle.files["document.md"], retained_files=retained,
            changes=compiled.changes, prepared_sha256=digest(files[path])))
        findings.extend(compiled.findings)
        previews.append({"document": document.id, "path": path,
                         "sha256": digest(files[path]), "operations": len(document.operations),
                         "diff": "".join(difflib.unified_diff(
                             bundle.markdown.text.splitlines(keepends=True),
                             compiled.text.splitlines(keepends=True),
                             fromfile=f"{document.id}/converted.md", tofile=path))})
    index = render_index(plan, sources, findings)
    files["index.md"] = index
    record = PreparationRecord(schema_version=1, status="writing", plan=plan,
                               plan_sha256=plan_hash(plan), documents=sources, findings=findings,
                               index_sha256=digest(index))
    report = validate_files(files, record, fidelity=True)
    report.update(destination=str(root), plan_sha256=record.plan_sha256, requires_approval=True,
                  placement=plan.placement.model_dump(),
                  create_directories=[str(path) for path in missing_parents(plan)],
                  files=sorted([*files, ".clew/preparation.json"]), previews=previews)
    return report, files, record


def check(plan: Plan) -> dict:
    return draft(plan)[0]


def materialize(plan: Plan, expected_hash: str) -> dict:
    require(plan_hash(plan) == expected_hash, "Preparation plan changed since approval.")
    report, files, record = draft(plan)
    require(report["errors"] == 0, "Preparation is invalid: " + "; ".join(
        finding["message"] for finding in report["findings"] if finding["severity"] == "error"))
    bundles = inspect_plan(plan)
    root = check_destination(plan, bundles)
    for directory in missing_parents(plan):
        no_redirect(directory)
        directory.mkdir(exist_ok=True)
        require(no_redirect(directory).is_dir(), f"Approved parent is not a directory: {directory}")
    root.mkdir()
    initial = json_text(record.model_dump()).encode("utf-8")
    record_path = root / ".clew" / "preparation.json"
    try:
        write_new(record_path, initial)
        for name, data in files.items():
            target = contained(root, name, exists=False)
            if isinstance(data, bytes):
                write_new(target, data)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                no_redirect(target)
                with no_redirect(data).open("rb") as incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
        inspect_plan(plan)
        persisted = validate(root, fidelity=True, incomplete=True)
        require(persisted["errors"] == 0, "Persisted preparation failed validation: " + "; ".join(
            finding["message"] for finding in persisted["findings"] if finding["severity"] == "error"))
        require(no_redirect(record_path).read_bytes() == initial, "Preparation record changed during execution.")
        completed = record.model_copy(update={"status": "complete"})
        pending = contained(root, ".clew/preparation.pending", exists=False)
        write_new(pending, json_text(completed.model_dump()).encode("utf-8"))
        require(record_path.read_bytes() == initial, "Preparation record changed before completion.")
        pending.replace(record_path)
        return validate(root, fidelity=True)
    except (ValueError, OSError, UnicodeError) as error:
        raise ValueError(f"Preparation failed; preserve partial output at {root}: {error}") from error


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("plan", type=Path)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Preview and validate without writing output")
    mode.add_argument("--plan-sha256", help="Execute only the concrete user-approved checked plan")
    args = cli.parse_args()

    def execute():
        plan = Plan.model_validate(read_json(args.plan))
        return check(plan) if args.check else materialize(plan, args.plan_sha256)

    return command(execute)


if __name__ == "__main__":
    raise SystemExit(main())
