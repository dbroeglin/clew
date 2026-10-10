"""Read-only current structure/link checks, optionally with exact initial fidelity."""
from __future__ import annotations

import argparse
from pathlib import Path

from pydantic import ValidationError
import pymupdf
import yaml

from document_edits import verify_projection, verify_syntax
from document_formats import Finding, PreparationRecord
from document_io import (command, contained, digest, fingerprint, no_redirect,
                         read_json, relative_path, require, sha256)
from document_structure import Note, validate_notes
from markdown_source import MarkdownSource

FileData = bytes | Path


def file_bytes(data: FileData) -> bytes:
    return data if isinstance(data, bytes) else no_redirect(data).read_bytes()


def file_hash(data: FileData) -> str:
    return digest(data) if isinstance(data, bytes) else sha256(data)


def page_count(data: FileData) -> int:
    pdf = pymupdf.open(stream=data, filetype="pdf") if isinstance(data, bytes) else pymupdf.open(no_redirect(data))
    with pdf:
        require(pdf.is_pdf and not pdf.needs_pass and len(pdf) > 0, "Expected an unlocked, nonempty PDF.")
        return len(pdf)


def validate_files(files: dict[str, FileData], record: PreparationRecord, *,
                   fidelity: bool = False) -> dict:
    findings: list[Finding] = []
    notes: dict[str, Note] = {}
    counts = {}

    def error(code, path, message):
        findings.append(Finding(code=code, severity="error", path=path, line=1, message=message))

    require(fingerprint({"format_version": 1, "plan": record.plan.model_dump()}) == record.plan_sha256,
            "Preparation plan fingerprint differs.")
    seen_paths = set()
    for name, data in files.items():
        if name.casefold() in seen_paths:
            error("path-collision", name, "Case-insensitive file path collision.")
        seen_paths.add(name.casefold())
        if name.startswith(".clew/"):
            continue
        if name.lower().endswith(".md"):
            try:
                notes[name] = Note(name, file_bytes(data).decode("utf-8"))
            except (ValueError, UnicodeError, OSError, yaml.YAMLError) as exc:
                error("note-format", name, str(exc))
        elif name.lower().endswith(".pdf"):
            try:
                counts[name] = page_count(data)
            except (ValueError, OSError, pymupdf.FileDataError) as exc:
                error("invalid-pdf", name, str(exc))
    findings.extend(validate_notes(notes, set(files), counts))
    by_id: dict[str, list[Note]] = {}
    for note in notes.values():
        if note.metadata.type == "document":
            by_id.setdefault(note.metadata.id, []).append(note)
    expected_ids = {source.id for source in record.documents}
    if len(expected_ids) != len(record.documents) or expected_ids != {doc.id for doc in record.plan.documents}:
        error("source-record", ".clew/preparation.json", "Recorded document identities differ from the plan.")
    for identifier, candidates in by_id.items():
        if identifier not in expected_ids:
            error("untracked-document", candidates[0].path, "Document is not part of this preparation record.")
    for source in record.documents:
        candidates = by_id.get(source.id, [])
        if len(candidates) != 1:
            error("document-identity", source.path, "Recorded document is missing or its ID is ambiguous.")
            continue
        note = candidates[0]
        try:
            relative_path(source.baseline)
            require(source.baseline == f".clew/baselines/{source.id}/document.md",
                    "Baseline is outside the documented private source location.")
            require(source.baseline in files, "Immutable Markdown baseline is missing.")
            original = file_bytes(files[source.baseline])
            require(digest(original) == source.baseline_sha256, "Immutable Markdown baseline was modified.")
            require(source.pages == sorted(set(source.pages))
                    and all(type(number) is int and 1 <= number <= source.page_count for number in source.pages),
                    "Invalid original imported page coverage.")
            require(note.metadata.source_pdf == source.pdf, "Source PDF metadata differs from the retained identity.")
            require(note.metadata.source_pages == source.pages, "Imported page metadata differs from the retained scope.")
            require(source.pdf in source.retained_files, "Retained PDF has no recorded source hash.")
            for name, expected in source.retained_files.items():
                relative_path(name)
                require(name == source.pdf or name.startswith("figures/"), "Unexpected retained source artifact.")
                path = str(Path(note.path).parent / Path(name)).replace("\\", "/")
                require(path in files, f"Retained source artifact is missing: {path}")
                require(file_hash(files[path]) == expected, f"Retained source artifact was modified: {path}")
            pdf_path = str(Path(note.path).parent / source.pdf).replace("\\", "/")
            require(counts.get(pdf_path) == source.page_count, "Retained PDF page count differs.")
            if fidelity:
                require(note.path == source.path, "Document was moved since initial preparation.")
                require(file_hash(files[note.path]) == source.prepared_sha256,
                        "Editable document differs from its initial prepared snapshot.")
                verify_projection(note.text, original.decode("utf-8"), source.changes)
                verify_syntax(MarkdownSource(original.decode("utf-8")), note.source)
        except (ValueError, OSError, UnicodeError) as exc:
            error("source-fidelity" if fidelity else "retained-source", note.path, str(exc))
    if "index.md" not in notes or notes["index.md"].metadata.type != "chapter":
        error("chapter-index", "index.md", "Chapter needs an index with type: chapter.")
    if fidelity:
        expected = {"index.md"} | {source.path for source in record.documents} \
            | {source.baseline for source in record.documents} \
            | {str(Path(source.path).parent / name).replace("\\", "/")
               for source in record.documents for name in source.retained_files}
        actual = set(files) - {".clew/preparation.json"}
        if expected != actual:
            error("initial-inventory", ".clew/preparation.json",
                  f"Initial owned files differ: {sorted(expected ^ actual)}")
        if "index.md" in files and file_hash(files["index.md"]) != record.index_sha256:
            error("index-fidelity", "index.md", "Chapter index differs from the initial prepared snapshot.")
    findings.sort(key=lambda finding: (finding.path, finding.line, finding.code))
    errors = sum(item.severity == "error" for item in findings)
    reviews = sum(item.severity == "review" for item in findings)
    return {"schema_version": 1, "status": "invalid" if errors else "needs_review" if reviews else "validated",
            "mode": "fidelity" if fidelity else "current", "documents": len(by_id),
            "errors": errors, "reviews": reviews,
            "findings": [item.model_dump(exclude_none=True) for item in findings]}


def inventory(root: Path) -> tuple[dict[str, FileData], list[Finding]]:
    files, findings = {}, []

    def visit(directory: Path):
        for child in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
            name = child.relative_to(root).as_posix()
            if child.name.startswith(".") and name != ".clew" and not name.startswith(".clew/"):
                continue
            try:
                no_redirect(child)
                if child.is_dir():
                    visit(child)
                else:
                    require(child.is_file(), "Unsupported filesystem entry.")
                    files[name] = child
            except (ValueError, OSError) as exc:
                findings.append(Finding(code="filesystem", severity="error", path=name, line=1, message=str(exc)))

    visit(root)
    return files, findings


def validate(root: Path, *, fidelity: bool = False, incomplete: bool = False) -> dict:
    root = no_redirect(root)
    require(root.is_dir(), f"Prepared chapter is missing: {root}")
    record = PreparationRecord.model_validate(read_json(contained(root, ".clew/preparation.json")))
    require(record.status == "complete" or incomplete and record.status == "writing",
            "Preparation is incomplete; preserve its partial output.")
    files, filesystem_findings = inventory(root)
    report = validate_files(files, record, fidelity=fidelity)
    if filesystem_findings:
        report["findings"].extend(item.model_dump(exclude_none=True) for item in filesystem_findings)
        report["errors"] += len(filesystem_findings)
        report["status"] = "invalid"
    report["root"] = str(root)
    return report


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("chapter", type=Path)
    cli.add_argument("--fidelity", action="store_true", help="Also require the exact initial source-preserving snapshot")
    args = cli.parse_args()
    return command(lambda: validate(args.chapter, fidelity=args.fidelity))


if __name__ == "__main__":
    raise SystemExit(main())
