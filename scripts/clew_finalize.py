"""Regenerate the derived parts of one clew/v1 course: navigation, links and hashes.

Authored prose, fidelity, checks and limitations stay untouched. This helper only
rebuilds what the Clew validator derives from the authored hierarchy and source map.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from src.vault.storage import VaultError, atomic_write, plain_path
except ImportError as error:  # pragma: no cover - exercised only outside a checkout
    raise SystemExit(
        "Clew: run this helper from a Clew checkout; src/vault/storage.py was not found."
    ) from error

try:
    import pymupdf
except ImportError:
    pymupdf = None

from scripts.clew_notes import (
    NoteError, join_note, note_link, page_link, properties, scalar,
    sequence_property, set_property, split_note, target_path,
)

COURSE_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
NAV_START = "<!-- clew:nav -->"
NAV_END = "<!-- /clew:nav -->"
UNRESOLVED = "No section maps this page yet."
UNCOMPARED = "Not yet compared against the source."


class FinalizeError(NoteError):
    """An actionable course finalization failure."""


def content_root(value: str | Path) -> Path:
    """Accept any existing content root, including one inside this clone."""
    path = plain_path(Path(value))
    if not path.exists():
        raise FinalizeError(f"Content root does not exist: {path}")
    if not path.is_dir():
        raise FinalizeError(f"Content root is not a directory: {path}")
    return path


class Course:
    """One course's authored notes and support records."""

    def __init__(self, root: Path, course: str):
        if not COURSE_KEY.fullmatch(course):
            raise FinalizeError(f"Course keys are lowercase kebab-case: {course}")
        self.root = root
        self.prefix = f"courses/{course}"
        self.entry = f"{self.prefix}/course.md"
        self.notes: dict[str, tuple[list[str], str, dict]] = {}
        self.output: dict[str, bytes] = {}
        self.load()

    def path(self, name: str) -> Path:
        path = plain_path(self.root / name)
        if self.root not in path.parents:
            raise FinalizeError(f"Path escapes the content root: {name}")
        return path

    def read_note(self, name: str) -> tuple[list[str], str, dict]:
        if name not in self.notes:
            path = self.path(name)
            if not path.is_file():
                raise FinalizeError(f"Missing note: {name}")
            lines, body = split_note(path.read_bytes(), name)
            self.notes[name] = (lines, body, properties(lines, name))
        return self.notes[name]

    def children(self, name: str) -> list[str]:
        data = self.read_note(name)[2]
        values = data.get("children") or []
        if not isinstance(values, list):
            raise FinalizeError(f"children must be a list: {name}")
        return [target_path(value) for value in values]

    def load(self) -> None:
        self.read_note(self.entry)
        self.chapters = self.children(self.entry)
        self.sequence: list[str] = []
        self.parents: dict[str, str] = {}
        for chapter in self.chapters:
            for section in self.children(chapter):
                self.parents[section] = chapter
                self.sequence.append(section)
        for name in (*self.chapters, *self.sequence):
            self.read_note(name)
        self.course_id = self.read_note(self.entry)[2]["id"]
        self.source_map = self.document("source-map.json")
        self.sources = {source["id"]: source for source in self.source_map["sources"]}
        self.records = {record["path"]: record for record in self.source_map["sections"]}
        missing = [name for name in self.sequence if name not in self.records]
        if missing:
            raise FinalizeError("Source map is missing sections: " + ", ".join(missing))

    def document(self, name: str) -> dict:
        path = self.path(f"{self.prefix}/support/{name}")
        if not path.is_file():
            raise FinalizeError(f"Missing support record: {self.prefix}/support/{name}")
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except ValueError as error:
            raise FinalizeError(f"Invalid JSON in {self.prefix}/support/{name}: {error}") from error
        if not isinstance(data, dict):
            raise FinalizeError(f"Expected a JSON object: {self.prefix}/support/{name}")
        return data

    def title(self, name: str) -> str:
        return self.read_note(name)[2].get("title") or PurePosixPath(name).stem

    def refs(self, records: list[dict], first_only: bool) -> list[tuple[str, int]]:
        """Mirror the validator's primary-coverage expansion exactly."""
        seen: set = set()
        result: list[tuple[str, int]] = []
        for record in records:
            for span in record["spans"]:
                source = self.sources.get(span["source_id"])
                if source is None or source["path"] is None:
                    continue
                start, end = span["page_start"], span["page_end"]
                if not 1 <= start <= end <= source["page_count"]:
                    continue
                for page in range(int(start), int(end) + 1):
                    key = source["path"] if first_only else (source["path"], page)
                    if key not in seen:
                        seen.add(key)
                        result.append((source["path"], page))
                    if first_only:
                        break
        return result

    def source_refs(self, name: str) -> list[tuple[str, int]]:
        data = self.read_note(name)[2]
        return self.refs(self.mapped(name), first_only=data["kind"] != "section")

    def mapped(self, name: str) -> list[dict]:
        data = self.read_note(name)[2]
        if data["kind"] == "section":
            return [self.records[name]]
        order = self.children(name) if data["kind"] == "chapter" else self.sequence
        return [self.records[child] for child in order if child in self.records]

    def navigation(self, name: str) -> list[str]:
        data = self.read_note(name)[2]
        kind, block = data["kind"], []
        if kind == "section":
            chapter = self.parents[name]
            block.append(
                f"Course: {note_link(self.entry, self.title(self.entry))} · "
                f"Chapter: {note_link(chapter, self.title(chapter))}"
            )
            index = self.sequence.index(name)
            previous = self.sequence[index - 1] if index else None
            following = self.sequence[index + 1] if index + 1 < len(self.sequence) else None
            steps = [
                f"Previous: {note_link(previous, self.title(previous))}" if previous else "Previous: none",
                f"Next: {note_link(following, self.title(following))}" if following else "Next: none",
            ]
            block.append(" · ".join(steps))
        elif kind == "chapter":
            block.append(f"Course: {note_link(self.entry, self.title(self.entry))}")
        originals = [page_link(path, page) for path, page in self.source_refs(name)]
        if originals:
            block.append("Originals: " + " · ".join(originals))
        for identity in dict.fromkeys(
            span["source_id"] for record in self.mapped(name) for span in record["spans"]
        ):
            source = self.sources.get(identity)
            if source and source["path"] is None:
                block.append(
                    f"Original not included: {source['filename']} — {source['omission_reason']}"
                )
        return block

    def contents(self, name: str) -> list[str]:
        items = []
        for position, child in enumerate(self.children(name), 1):
            summary = self.read_note(child)[2].get("summary", "").strip()
            entry = f"{position}. {note_link(child, self.title(child))}"
            items.append(f"{entry} — {summary}" if summary else entry)
        return items

    def apply_body(self, body: str, navigation: list[str], contents: list[str] | None) -> str:
        block = "\n".join([NAV_START, *navigation, NAV_END])
        if NAV_START in body and NAV_END in body:
            start, end = body.index(NAV_START), body.index(NAV_END) + len(NAV_END)
            body = body[:start] + block + body[end:]
        else:
            heading = re.search(r"(?m)^# .+$", body)
            if heading is None:
                raise FinalizeError("Every note needs one title heading before its navigation.")
            body = body[:heading.end()] + "\n\n" + block + body[heading.end():]
        if contents is None:
            return body
        section = "\n".join(["## Contents", "", *contents])
        match = re.search(r"(?m)^## Contents[ \t]*$", body)
        if match is None:
            return body.rstrip() + "\n\n" + section + "\n"
        tail = body[match.end():]
        following = re.search(r"(?m)^#{1,2} ", tail)
        rest = tail[following.start():] if following else ""
        return body[:match.start()] + section + ("\n\n" + rest if rest else "\n")

    def render_notes(self) -> None:
        for name in (self.entry, *self.chapters, *self.sequence):
            lines, body, data = self.read_note(name)
            kind = data["kind"]
            if kind == "section":
                index = self.sequence.index(name)
                previous = self.sequence[index - 1] if index else None
                following = self.sequence[index + 1] if index + 1 < len(self.sequence) else None
                lines = set_property(lines, "previous", scalar(
                    "previous", note_link(previous) if previous else None))
                lines = set_property(lines, "next", scalar(
                    "next", note_link(following) if following else None))
            links = [f"[[{path}#page={page}]]" for path, page in self.source_refs(name)]
            lines = set_property(lines, "source_refs", sequence_property("source_refs", links))
            contents = self.contents(name) if kind in {"course", "chapter"} else None
            body = self.apply_body(body, self.navigation(name), contents)
            self.output[name] = join_note(lines, body)

    def render_source_map(self) -> None:
        for source in self.source_map["sources"]:
            if source["path"] is None:
                continue
            path = self.path(source["path"])
            if not path.is_file():
                raise FinalizeError(f"Declared source is missing: {source['path']}")
            source["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            source["page_count"] = page_count(path)
        self.output[f"{self.prefix}/support/source-map.json"] = serialize(self.source_map)

    def render_verification(self) -> None:
        name = f"{self.prefix}/support/verification.json"
        try:
            report = self.document("verification.json")
        except FinalizeError:
            report = {"schema": "clew-verification/v1", "sections": [], "pages": []}
        previous_sections = {record["id"]: record for record in report.get("sections", [])}
        previous_pages = {
            (record["source_id"], record["page"]): record for record in report.get("pages", [])
        }
        coverage: dict[str, list[tuple[int, int, str]]] = {identity: [] for identity in self.sources}
        sections = []
        for path in self.sequence:
            record = self.records[path]
            identity = record["id"]
            for spans in [record["spans"], *(item["spans"] for item in record.get("alternatives", []))]:
                for span in spans:
                    if span["source_id"] in coverage:
                        coverage[span["source_id"]].append(
                            (span["page_start"], span["page_end"], identity))
            fidelity = self.read_note(path)[2]["fidelity"]
            existing = previous_sections.get(identity, {})
            checks = list(existing.get("checks", []))
            limitations = list(existing.get("limitations", []))
            if fidelity != "verified" and not limitations:
                limitations = [UNCOMPARED]
            if fidelity == "verified":
                limitations = []
                if not checks:
                    raise FinalizeError(
                        f"{path} claims verified fidelity but its verification record has no checks. "
                        "Record the actual comparison evidence, or lower the fidelity."
                    )
            sections.append({
                "id": identity,
                "markdown_sha256": hashlib.sha256(self.output[path]).hexdigest(),
                "fidelity": fidelity,
                "checks": checks,
                "limitations": limitations,
            })
        pages = []
        for identity, source in self.sources.items():
            for page in range(1, source["page_count"] + 1):
                mapped = sorted({
                    section for start, end, section in coverage[identity] if start <= page <= end
                })
                existing = previous_pages.get((identity, page), {})
                if mapped:
                    status, reason = "mapped", None
                else:
                    status = existing.get("status") if existing.get("status") != "mapped" else None
                    status = status or "unresolved"
                    reason = existing.get("reason") or UNRESOLVED
                pages.append({
                    "source_id": identity, "page": page, "status": status,
                    "section_ids": mapped, "reason": reason,
                })
        self.output[name] = serialize({
            "schema": "clew-verification/v1",
            "course_id": self.course_id,
            "source_map_sha256": hashlib.sha256(
                self.output[f"{self.prefix}/support/source-map.json"]).hexdigest(),
            "sections": sections,
            "pages": pages,
        })

    def finalize(self) -> dict[str, bytes]:
        self.render_notes()
        self.render_source_map()
        self.render_verification()
        return self.output


def serialize(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def page_count(path: Path) -> int:
    if pymupdf is None:
        raise FinalizeError("PyMuPDF is required to count source pages; use the project environment.")
    with pymupdf.open(path) as document:
        return document.page_count


def finalize(root: str | Path, course: str, check: bool = False) -> dict:
    base = content_root(root)
    output = Course(base, course).finalize()
    changed = [
        name for name in sorted(output)
        if not (base / name).is_file() or (base / name).read_bytes() != output[name]
    ]
    if not check:
        for name in changed:
            atomic_write(base / name, output[name])
    return {
        "schema": "clew-finalize/v1",
        "course": f"courses/{course}",
        "checked": check,
        "changed": changed,
        "ok": not (check and changed),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="Course repository or vault holding courses/")
    parser.add_argument("--course", required=True, help="Course directory key, such as mechanics")
    parser.add_argument("--check", action="store_true", help="Report drift without writing")
    arguments = parser.parse_args(argv)
    try:
        result = finalize(arguments.root, arguments.course, arguments.check)
    except (NoteError, VaultError, OSError, UnicodeError, ValueError) as error:
        print(f"Clew: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
