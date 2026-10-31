"""Preview or write a public copy of one prepared chapter for sharing through Git."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from document_formats import Finding, PreparationRecord, PublishedRecord
from document_io import (command, contained, digest, fingerprint, json_text,
                         no_redirect, relative_path, require, sha256, write_new)
from validate_documents import RECORD, inventory, load_record, read_notes, validate

# Git must store and check out every published byte unchanged (no EOL, LFS or encoding conversion).
GITATTRIBUTES = b"* -text -filter -ident -working-tree-encoding\n"
WARN_BYTES = 50 * 1024 * 1024
LIMIT_BYTES = 100 * 1024 * 1024


def errors_of(report: dict) -> str:
    return "; ".join(f"{item['path']}: {item['message']}" for item in report["findings"]
                     if item["severity"] == "error")


def check_output(output: Path, chapter: Path, chapter_id: str) -> str:
    require(output.is_absolute(), "Publication output must be an absolute path.")
    output = no_redirect(output)
    relative_path(output.name)
    require(not output.name.startswith("."), "Published chapter folder must be visible.")
    require(not output.is_relative_to(chapter) and not chapter.is_relative_to(output),
            "Publication output must not contain or be inside the source chapter.")
    if not os.path.lexists(output):
        return "new"
    require(output.is_dir(), f"Publication output is not a directory: {output}")
    try:
        existing = load_record(output)
    except (ValueError, OSError):
        existing = None
    require(isinstance(existing, PublishedRecord) and existing.chapter.id == chapter_id,
            f"Publication output holds other content: {output}. Choose another chapter folder name.")
    return "republish"


def draft(chapter: Path, output: Path) -> tuple[dict, PublishedRecord, dict[str, Path]]:
    chapter = no_redirect(chapter)
    validation = validate(chapter)
    require(validation["errors"] == 0, "Chapter is invalid; fix it before publishing: " + errors_of(validation))
    record = load_record(chapter)
    files, _ = inventory(chapter)
    public = {name: path for name, path in files.items() if not name.startswith(".clew/")}
    for name in public:
        relative_path(name)
    notes, _ = read_notes(public, lambda *_: None)
    documents = []
    for source in record.documents:
        [note] = [note for note in notes.values()
                  if note.metadata.type == "document" and note.metadata.id == source.id]
        documents.append({"id": source.id, "path": note.path, "role": note.metadata.role})
    index = notes["index.md"].metadata
    fallback = record.plan.title if isinstance(record, PreparationRecord) else record.chapter.title
    published = PublishedRecord(
        schema_version=1, status="complete", kind="published",
        chapter={"id": index.id, "title": index.title or fallback},
        documents=documents, files={name: sha256(path) for name, path in public.items()})
    target = check_output(output, chapter, published.chapter.id)
    findings = [Finding.model_validate(item) for item in validation["findings"]]
    sizes = {name: os.path.getsize(path) for name, path in public.items()}
    for name, size in sizes.items():
        if size > LIMIT_BYTES:
            findings.append(Finding(code="file-size", severity="error", path=name, line=1,
                                    message="File exceeds the 100 MiB per-file limit of Git hosts."))
        elif size > WARN_BYTES:
            findings.append(Finding(code="file-size", severity="review", path=name, line=1,
                                    message="File exceeds 50 MiB; Git hosts may warn or reject it."))
    errors = sum(item.severity == "error" for item in findings)
    reviews = sum(item.severity == "review" for item in findings)
    report = {
        "schema_version": 1, "status": "invalid" if errors else "needs_review" if reviews else "ready",
        "chapter": published.chapter.model_dump(), "source": str(chapter), "output": str(no_redirect(output)),
        "target": target, "requires_approval": True,
        "publish_sha256": fingerprint({"format_version": 1, "output": str(no_redirect(output)),
                                       "record": published.model_dump()}),
        "files": [{"path": name, "bytes": sizes[name]} for name in sorted(sizes)],
        "total_bytes": sum(sizes.values()), "errors": errors, "reviews": reviews,
        "findings": [item.model_dump(exclude_none=True) for item in findings],
    }
    return report, published, public


def publish(chapter: Path, output: Path, expected_hash: str) -> dict:
    report, record, files = draft(chapter, output)
    require(report["publish_sha256"] == expected_hash, "Chapter or output changed since approval.")
    require(report["errors"] == 0, "Publication is invalid: " + errors_of(report))
    output = no_redirect(output)
    require(not os.path.lexists(output),
            f"Publication output exists: {output}. Remove the previous published copy first.")
    output.mkdir(parents=True)
    try:
        for name, source in files.items():
            data = no_redirect(source).read_bytes()
            require(digest(data) == record.files[name], f"Chapter file changed during publication: {name}")
            write_new(contained(output, name, exists=False), data)
        write_new(contained(output, ".gitattributes", exists=False), GITATTRIBUTES)
        write_new(contained(output, RECORD, exists=False), json_text(record.model_dump()).encode("utf-8"))
        persisted = validate(output, fidelity=True)
        require(persisted["errors"] == 0, "Published copy failed validation: " + errors_of(persisted))
    except (ValueError, OSError) as error:
        raise ValueError(f"Publication failed; inspect or discard partial output at {output}: {error}") from error
    return {"schema_version": 1, "status": "published", "chapter": record.chapter.model_dump(),
            "output": str(output), "files": len(record.files) + 2,
            "validation": persisted["status"], "reviews": persisted["reviews"]}


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("chapter", type=Path, help="Prepared chapter folder in the vault")
    cli.add_argument("--output", type=Path, required=True,
                     help="Absolute published chapter folder, e.g. <clone>/Courses/<chapter-name>")
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Preview and validate without writing output")
    mode.add_argument("--publish-sha256", help="Write only the user-approved checked publication")
    args = cli.parse_args()
    return command(lambda: draft(args.chapter, args.output)[0] if args.check
                   else publish(args.chapter, args.output, args.publish_sha256))


if __name__ == "__main__":
    raise SystemExit(main())
