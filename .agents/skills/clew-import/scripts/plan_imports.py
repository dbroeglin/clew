"""Read-only PDF import discovery and command planning. Never execute a plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit

import pymupdf

import digest_pdf

PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONVERTER = Path(__file__).with_name("digest_pdf.py")
COMPLETE_STATUSES = {"extracted", "needs_review"}


class InspectionError(Exception):
    """An input or existing output cannot safely be classified."""


def is_link(path: Path) -> bool:
    """Reject path redirection, not non-redirecting OneDrive cloud placeholders."""
    attributes = path.lstat()
    if stat.S_ISLNK(attributes.st_mode):
        return True
    if not getattr(attributes, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        return False
    tag = getattr(attributes, "st_reparse_tag", 0)
    # WinNT.h's name-surrogate bit identifies namespace redirection.
    return tag == 0 or bool(tag & 0x20000000)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_object(path: Path) -> dict[str, object]:
    try:
        if is_link(path):
            raise InspectionError(f"Metadata redirects its path or has an unavailable reparse tag: {path}")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        detail = str(error) if isinstance(error, OSError) else type(error).__name__
        raise InspectionError(f"Cannot read metadata at {path}: {detail}") from error
    if not isinstance(value, dict):
        raise InspectionError(f"Metadata is not a JSON object: {path}")
    return value


def source_record(manifest: Mapping[str, object]) -> dict[str, object]:
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise InspectionError("Manifest source is missing or invalid.")
    name, digest, count = source.get("name"), source.get("sha256"), source.get("page_count")
    if (
        not isinstance(name, str) or Path(name).name != name
        or PureWindowsPath(name).name != name or Path(name).suffix.lower() != ".pdf"
        or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
        or type(count) is not int or not 1 <= count <= 2000
        or source.get("path") != f"source/{name}"
    ):
        raise InspectionError("Manifest source name, path, hash, or page count is invalid.")
    return source


def artifact(output: Path, reference: object) -> Path:
    if not isinstance(reference, str) or not reference:
        raise InspectionError("A manifest artifact path is missing or invalid.")
    relative = Path(reference)
    windows = PureWindowsPath(reference)
    if (
        relative.is_absolute() or windows.is_absolute() or windows.drive
        or ".." in relative.parts or ".." in windows.parts
    ):
        raise InspectionError("A manifest artifact path is outside the import bundle.")
    target = output / relative
    for path in (target, *target.parents):
        if path == output:
            break
        if os.path.lexists(path) and is_link(path):
            raise InspectionError(f"Artifact redirects its path or has an unavailable reparse tag: {path}")
    if not target.resolve().is_relative_to(output.resolve()):
        raise InspectionError("A manifest artifact path escapes the import bundle.")
    if not target.is_file():
        raise InspectionError(f"Required artifact is missing: {target}")
    return target


def bundle_marker(directory: Path) -> tuple[bool, str | None]:
    """Identify bundles for traversal exclusion, even when their source is stale."""
    manifest_path, report_path = directory / "manifest.json", directory / "run.json"
    if manifest_path.exists():
        try:
            manifest = read_object(manifest_path)
            if manifest.get("document") == "document.md":
                source_record(manifest)
                status = manifest.get("status")
                if (
                    manifest.get("schema_version") != 3
                    or not isinstance(status, str) or status not in COMPLETE_STATUSES
                    or not isinstance(manifest.get("pages"), list)
                    or not isinstance(manifest.get("figures"), list)
                ):
                    raise InspectionError("Unrecognized completion manifest.")
                return True, None
        except InspectionError as error:
            return False, str(error)
    if report_path.exists():
        try:
            report = read_object(report_path)
            source, output = report.get("source"), report.get("output")
            status = report.get("status")
            if (
                report.get("schema_version") == 1
                and isinstance(status, str)
                and status in {"running", "failed", "interrupted", *COMPLETE_STATUSES}
                and isinstance(source, str) and isinstance(output, str)
                and Path(source).is_absolute() and Path(output).is_absolute()
                and Path(output).resolve() == directory.resolve()
                and Path(source).with_suffix("").resolve() == directory.resolve()
                and Path(source).suffix.lower() == ".pdf"
                and isinstance(report.get("stage"), str)
                and (directory / "raw").is_dir()
            ):
                return True, None
            raise InspectionError("Run metadata does not identify a sibling import output.")
        except InspectionError as error:
            return False, str(error)
    if (directory / "document.md").is_file() and (directory / "raw").is_dir():
        return False, "Import-like directory has no recognizable source metadata."
    return False, None


def discover(input_path: Path) -> tuple[list[Path], list[dict[str, str]], list[str]]:
    sources: list[Path] = []
    conflicts: list[dict[str, str]] = []
    excluded: list[str] = []

    def visit(directory: Path) -> None:
        recognized, problem = bundle_marker(directory)
        if recognized:
            excluded.append(str(directory))
            return
        if problem:
            conflicts.append({"path": str(directory), "reason": problem})
            return
        for child in sorted(directory.iterdir(), key=lambda path: (path.name.casefold(), path.name)):
            if is_link(child):
                conflicts.append({"path": str(child), "reason": "Path redirection or unavailable reparse tag was not traversed."})
            elif child.is_dir():
                visit(child)
            elif child.is_file() and child.suffix.lower() == ".pdf":
                sources.append(child)

    if not os.path.lexists(input_path):
        raise InspectionError(f"Input does not exist: {input_path}")
    if is_link(input_path):
        raise InspectionError("Input redirects its path or has an unavailable reparse tag; supply a real local path.")
    input_path = input_path.resolve()
    if input_path.is_dir():
        visit(input_path)
    elif input_path.is_file() and input_path.suffix.lower() == ".pdf":
        sources.append(input_path)
    else:
        raise InspectionError("Input must be a local PDF or directory.")
    sources.sort(key=lambda path: (str(path).casefold(), str(path)))
    return sources, conflicts, excluded


def inspect_pdf(source: Path, pages: str | None) -> tuple[str, int, list[int]]:
    if source.stat().st_size > 500_000_000:
        raise InspectionError("PDF exceeds Document Intelligence's 500 MB limit.")
    try:
        with pymupdf.open(source) as pdf:
            if not pdf.is_pdf or pdf.needs_pass:
                raise InspectionError("Input must be a valid, unlocked PDF.")
            count = len(pdf)
            wanted = digest_pdf.selected_pages(pages, count)
    except (pymupdf.FileDataError, digest_pdf.DigestionError) as error:
        raise InspectionError(str(error)) from error
    return sha256(source), count, wanted


def inspect_completed(
    source: Path, output: Path, digest: str, count: int, wanted: list[int],
) -> list[str]:
    manifest = read_object(artifact(output, "manifest.json"))
    status = manifest.get("status")
    if (
        manifest.get("schema_version") != 3
        or not isinstance(status, str) or status not in COMPLETE_STATUSES
    ):
        raise InspectionError("Target has no recognized completed import.")
    record = source_record(manifest)
    if record["name"] != source.name or record["sha256"] != digest or record["page_count"] != count:
        raise InspectionError("Existing import is stale or belongs to a different source.")
    if manifest.get("document") != "document.md":
        raise InspectionError("Manifest does not reference document.md.")
    artifact(output, manifest["document"])
    for reference in ("run.json", "raw/document-intelligence.json",
                      "raw/document-intelligence.md", "raw/assembled.md"):
        artifact(output, reference)
    retained = artifact(output, record["path"])
    if sha256(retained) != digest:
        raise InspectionError("Retained original does not match the source hash.")
    pages, figures, issues = manifest.get("pages"), manifest.get("figures"), manifest.get("issues")
    if (
        not isinstance(pages, list) or not isinstance(figures, list)
        or not isinstance(issues, list) or not all(isinstance(issue, str) for issue in issues)
    ):
        raise InspectionError("Manifest pages, figures, or review issues are invalid.")
    numbers = []
    for page in pages:
        if not isinstance(page, dict) or type(page.get("number")) is not int:
            raise InspectionError("Manifest page record is invalid.")
        numbers.append(page["number"])
        artifact(output, page.get("raw_image"))
        artifact(output, page.get("raw_response"))
    if sorted(numbers) != wanted:
        raise InspectionError("Existing import page coverage does not match the requested scope.")
    for figure in figures:
        if (
            not isinstance(figure, dict) or not isinstance(figure.get("decision"), str)
            or figure["decision"] not in {"keep", "discard", "review"}
        ):
            raise InspectionError("Manifest figure record is invalid.")
        artifact(output, figure.get("raw_crop"))
        if figure["decision"] == "keep":
            artifact(output, figure.get("asset"))
        elif figure.get("asset") is not None:
            raise InspectionError("Rejected/review figure has an unexpected published asset.")
    return issues


def powershell_command(argv: Sequence[str]) -> str:
    return "& " + " ".join("'" + argument.replace("'", "''") + "'" for argument in argv)


def environment_blockers(project: Path, check_env: bool) -> list[str]:
    blockers = []
    for name in ("pyproject.toml", "uv.lock", ".env"):
        if not (project / name).is_file():
            blockers.append(f"Project root is missing {name}.")
    if not (project / ".venv").is_dir():
        blockers.append("Project environment is missing; approve uv sync --locked before planning.")
    if shutil.which("uv") is None:
        blockers.append("UV is unavailable; no global-Python conversion fallback is allowed.")
    if check_env:
        try:
            settings = digest_pdf.settings_from_env(os.environ)
            if any(re.search(r"YOUR[-_]|CHANGE[-_]?ME|PLACEHOLDER", value, re.IGNORECASE)
                   for value in (settings.document_endpoint, settings.openai_base_url, settings.deployment)):
                blockers.append("Effective Azure configuration contains placeholder values.")
        except digest_pdf.DigestionError as error:
            blockers.append(str(error))
    else:
        blockers.append("Effective Azure configuration has not been checked; use --check-env with UV's --env-file.")
    return blockers


def configuration_summary() -> dict[str, object]:
    settings = digest_pdf.settings_from_env(os.environ)
    values = [settings.document_endpoint, settings.openai_base_url, settings.deployment]
    return {
        "fingerprint": hashlib.sha256(json.dumps(values).encode("utf-8")).hexdigest(),
        "document_intelligence_host": urlsplit(settings.document_endpoint).hostname,
        "openai_host": urlsplit(settings.openai_base_url).hostname,
    }


def build_plan(
    input_path: Path, *, project: Path = PROJECT_ROOT, pages: str | None = None,
    dpi: int = 200, max_output_tokens: int = 16000,
    high_resolution_ocr: bool = False, debug: bool = False, check_env: bool = False,
) -> dict[str, object]:
    if not 72 <= dpi <= 600 or max_output_tokens < 1:
        raise InspectionError("Use DPI between 72 and 600 and a positive output token budget.")
    sources, conflicts, excluded = discover(input_path)
    entries: list[dict[str, object]] = []
    targets: dict[str, list[Path]] = {}
    for source in sources:
        key = os.path.normcase(str(source.with_suffix("")))
        targets.setdefault(key, []).append(source)
    for source in sources:
        output = source.with_suffix("")
        entry: dict[str, object] = {"source": str(source), "output": str(output)}
        try:
            if len(targets[os.path.normcase(str(output))]) > 1:
                raise InspectionError("Multiple source PDFs map to the same target.")
            digest, count, wanted = inspect_pdf(source, pages)
            entry.update(sha256=digest, page_count=count, pages=wanted)
            if os.path.lexists(output):
                if is_link(output) or not output.is_dir():
                    raise InspectionError("Target is a file, redirects its path, or has an unavailable reparse tag.")
                issues = inspect_completed(source, output, digest, count, wanted)
                entry.update(classification="already_converted", reason="Source, artifacts, and page scope match.",
                             review_issues=issues)
            else:
                argv = [
                    "uv", "run", "--locked", "--env-file", ".env",
                    "python", str(CONVERTER), str(source), "--output", str(output),
                    "--dpi", str(dpi), "--max-output-tokens", str(max_output_tokens),
                ]
                if pages is not None:
                    argv.extend(["--pages", pages])
                if high_resolution_ocr:
                    argv.append("--high-resolution-ocr")
                if debug:
                    argv.append("--debug")
                entry.update(classification="convert", reason="Valid PDF and target does not exist.",
                             argv=argv, command=powershell_command(argv))
        except (InspectionError, OSError) as error:
            entry.update(classification="blocked", reason=str(error))
        entries.append(entry)
    blockers = environment_blockers(project, check_env)
    configuration = None
    if check_env:
        try:
            configuration = configuration_summary()
        except digest_pdf.DigestionError:
            # The explicit configuration error is already included in blockers.
            configuration = None
    return {
        "schema_version": 1, "working_directory": str(project),
        "input": str(input_path.resolve()), "entries": entries,
        "excluded_bundles": excluded, "discovery_conflicts": conflicts,
        "preflight_blockers": blockers,
        "configuration": configuration,
        "setup_required": not (project / ".venv").is_dir(),
        "setup_command": powershell_command(["uv", "sync", "--locked"]),
        "requires_approval": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Local PDF or recursively scanned directory")
    parser.add_argument("--pages", help="Original PDF page groups; default: all")
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--max-output-tokens", type=int, default=16000)
    parser.add_argument("--high-resolution-ocr", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--check-env", action="store_true", help="Validate effective environment without printing values")
    args = parser.parse_args(argv)
    try:
        plan = build_plan(
            args.input, pages=args.pages, dpi=args.dpi, max_output_tokens=args.max_output_tokens,
            high_resolution_ocr=args.high_resolution_ocr, debug=args.debug, check_env=args.check_env,
        )
    except (InspectionError, OSError) as error:
        print(f"Inspection failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(plan, indent=2, ensure_ascii=True))
    blocked = (
        bool(plan["discovery_conflicts"]) or bool(plan["preflight_blockers"])
        or any(entry["classification"] == "blocked" for entry in plan["entries"])
    )
    return 2 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
