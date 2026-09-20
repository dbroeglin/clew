"""Import a published Clew course from a git repository or directory into a vault.

The course was converted once by its producer. Importing copies the finished
Markdown, its original PDFs and the shared concepts it grounds, without calling
a model and without re-reading a PDF.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from src.vault.storage import VaultError, atomic_write, plain_path, read_json, vault_path
except ImportError as error:  # pragma: no cover - exercised only outside a checkout
    raise SystemExit(
        "Clew: run this script from a Clew checkout; src/vault/storage.py was not found."
    ) from error

from scripts.clew_notes import (
    NoteError, join_note, note_link, properties, sequence_property, set_property,
    split_note, targets,
)

COURSE_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
SUPPORT = {"source-map.json", "verification.json"}
RESERVED = {"model", "artifacts"}
CANONICAL = ("title", "summary")
RELATIONS = ("prerequisites", "similar", "related")
REFERENCES = ("teaches", "prerequisites", "similar", "related")
IMPORTS = ".clew/imports.json"
SCHEMA = "clew-imports/v1"


class ImportFailure(NoteError):
    """An actionable import failure."""


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, check=True, capture_output=True, text=True)


def head(path: Path) -> str | None:
    try:
        return run(["git", "-C", str(path), "rev-parse", "HEAD"]).stdout.strip() or None
    except (subprocess.CalledProcessError, OSError):
        return None


def fetch(target: Path, source: str, ref: str) -> None:
    """Fetch one revision with as little history and as few blobs as the server allows."""
    failure: Exception | None = None
    for options in (["--filter=blob:none"], []):
        try:
            run(["git", "-C", str(target), "fetch", "--depth", "1", "--quiet",
                 *options, "origin", ref])
            return
        except subprocess.CalledProcessError as error:
            failure = error
    detail = getattr(failure, "stderr", "") or failure
    raise ImportFailure(f"Could not fetch {ref} from {source}: {str(detail).strip()}")


def stage(source: str, ref: str | None, courses: list[str], workspace: Path) -> dict:
    """Make the published content readable locally, without trusting it yet."""
    local = Path(source).expanduser()
    if local.is_dir() and (local / "courses").is_dir():
        root = plain_path(local)
        return {"root": root, "kind": "directory", "ref": ref,
                "commit": head(root), "source": root.as_posix()}
    target = workspace / "repository"
    target.mkdir()
    revision = ref or "HEAD"
    try:
        run(["git", "init", "--quiet", str(target)])
        run(["git", "-C", str(target), "remote", "add", "origin", source])
        run(["git", "-C", str(target), "sparse-checkout", "set", "--cone", "concepts",
             *(f"courses/{course}" for course in courses)])
    except subprocess.CalledProcessError as error:
        raise ImportFailure(f"Could not prepare a checkout of {source}: "
                            f"{(error.stderr or '').strip() or error}") from error
    except OSError as error:
        raise ImportFailure(f"git is required to import from {source}: {error}") from error
    fetch(target, source, revision)
    try:
        run(["git", "-C", str(target), "checkout", "--quiet", "FETCH_HEAD"])
    except subprocess.CalledProcessError as error:
        raise ImportFailure(f"Could not check out {revision} from {source}: "
                            f"{(error.stderr or '').strip() or error}") from error
    return {"root": target, "kind": "git", "ref": ref, "commit": head(target),
            "source": source}


def safe(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    return bool(parts) and not any(
        part in {"", ".", ".."} or part != part.strip() or part.endswith(".")
        for part in parts
    )


def walk(root: Path, base: Path) -> list[str]:
    """List regular files under base, refusing symlinks and unsafe names."""
    found = []
    for current, directories, names in os.walk(base, followlinks=False):
        directories.sort()
        for name in list(directories):
            if (Path(current) / name).is_symlink():
                raise ImportFailure(
                    "Refusing a symlinked directory: "
                    f"{(Path(current) / name).relative_to(root).as_posix()}")
        for name in sorted(names):
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise ImportFailure(f"Refusing a symlinked file: {relative}")
            if not safe(relative):
                raise ImportFailure(f"Refusing an unsafe path: {relative}")
            found.append(relative)
    return sorted(found)


def course_files(root: Path, course: str) -> list[str]:
    """Enforce the validator's fixed course layout before anything is copied."""
    if not COURSE_KEY.fullmatch(course):
        raise ImportFailure(f"Course keys are lowercase kebab-case: {course}")
    base = root / "courses" / course
    if not base.is_dir():
        raise ImportFailure(f"The source has no courses/{course} directory.")
    if not (base / "course.md").is_file():
        raise ImportFailure(f"courses/{course} has no course.md entry note.")
    prefix = f"courses/{course}"
    files = walk(root, base)
    for relative in files:
        local = PurePosixPath(relative).relative_to(prefix).parts
        suffix = PurePosixPath(relative).suffix.lower()
        allowed = (
            local == ("course.md",)
            or len(local) == 2 and (
                local[0] in {"chapters", "sections"} and suffix == ".md"
                or local[0] == "sources" and suffix == ".pdf"
                or local[0] == "assets" and suffix in IMAGES
                or local[0] == "support" and local[1] in SUPPORT
            )
        )
        if not allowed:
            raise ImportFailure(f"File is outside the fixed course layout: {relative}")
    return files


class Note:
    """One note held in memory while it is reconciled."""

    def __init__(self, relative: str, raw: bytes):
        self.relative = relative
        self.lines, self.body = split_note(raw, relative)
        self.data = properties(self.lines, relative)

    @classmethod
    def read(cls, root: Path, relative: str) -> "Note":
        return cls(relative, (root / relative).read_bytes())

    def rendered(self) -> bytes:
        return join_note(self.lines, self.body)

    def section(self, heading: str) -> str:
        match = re.search(rf"(?m)^## {re.escape(heading)}[ \t]*$", self.body)
        if match is None:
            return ""
        tail = self.body[match.end():]
        following = re.search(r"(?m)^#{1,2} ", tail)
        return (tail[:following.start()] if following else tail).strip()

    def relations(self) -> dict:
        return {key: sorted(targets(self.data, key)) for key in RELATIONS}

    def evidence(self) -> list[str]:
        return targets(self.data, "evidence")

    def set_evidence(self, links: list[str], titles: dict) -> None:
        """Rewrite the evidence list in the frontmatter and the body together."""
        self.lines = set_property(self.lines, "evidence", sequence_property(
            "evidence", [note_link(link) for link in links]))
        items = [f"- {note_link(link, titles[link])}" for link in links]
        block = "\n".join(["## Evidence", "", *items])
        match = re.search(r"(?m)^## Evidence[ \t]*$", self.body)
        if match is None:
            self.body = self.body.rstrip() + "\n\n" + block + "\n"
            return
        tail = self.body[match.end():]
        following = re.search(r"(?m)^#{1,2} ", tail)
        rest = tail[following.start():] if following else ""
        self.body = self.body[:match.start()] + block + ("\n\n" + rest if rest else "\n")


def concept_closure(root: Path, notes: list[Note]) -> dict:
    """Collect referenced concepts, then the concepts those concepts point at."""
    pending = [
        target for note in notes for key in REFERENCES
        for target in targets(note.data, key) if target.startswith("concepts/")
    ]
    resolved: dict[str, Note] = {}
    while pending:
        relative = pending.pop()
        if relative in resolved:
            continue
        if not safe(relative) or len(PurePosixPath(relative).parts) != 2:
            raise ImportFailure(f"Refusing an unsafe concept reference: {relative}")
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ImportFailure(f"The source references {relative} but does not publish it.")
        concept = Note(relative, path.read_bytes())
        if concept.data.get("kind") != "concept":
            raise ImportFailure(f"Expected a concept note: {relative}")
        resolved[relative] = concept
        pending.extend(
            target for key in RELATIONS for target in targets(concept.data, key)
            if target.startswith("concepts/")
        )
    return resolved


def owning_course(target: str) -> str | None:
    parts = PurePosixPath(target).parts
    return parts[1] if len(parts) > 2 and parts[0] == "courses" else None


def unsatisfied(relative: str, delivered: Note) -> ImportFailure:
    elsewhere = sorted({
        course for course in map(owning_course, delivered.evidence()) if course
    })
    hint = ("      Add one of these courses: " + ", ".join(elsewhere)) if elsewhere else \
           "      Its evidence points outside this repository."
    return ImportFailure(
        f"{relative} has no evidence in the vault after this import.\n{hint}")


class Titles(dict):
    """Alias evidence links with their note titles, wherever those notes live."""

    def __init__(self, vault: Path, known: dict):
        super().__init__(known)
        self.vault = vault

    def __missing__(self, relative: str):
        path = self.vault / relative
        title = None
        if path.is_file() and not path.is_symlink():
            try:
                note = Note(relative, path.read_bytes())
                title = note.data.get("title")
            except (NoteError, OSError, UnicodeError):
                title = None
        self[relative] = title
        return title


def reconcile(vault: Path, concepts: dict, keeps: set[str], policy: str,
              titles: dict) -> tuple[dict, list[dict]]:
    """Merge shared concepts additively; stop rather than silently redefining one."""
    writes, report = {}, []
    for relative, delivered in sorted(concepts.items()):
        kept = [link for link in delivered.evidence() if link in keeps]
        target = vault / relative
        if not target.is_file():
            if not kept:
                raise unsatisfied(relative, delivered)
            delivered.set_evidence(kept, titles)
            writes[relative] = delivered.rendered()
            report.append({"path": relative, "action": "added"})
            continue
        existing = Note.read(vault, relative)
        merged = list(dict.fromkeys([*existing.evidence(), *kept]))
        if not merged:
            raise unsatisfied(relative, delivered)
        differs = (
            [existing.data.get(key) for key in CANONICAL]
            != [delivered.data.get(key) for key in CANONICAL]
            or existing.relations() != delivered.relations()
            or existing.section("Definition") != delivered.section("Definition")
        )
        if differs and policy == "abort":
            raise ImportFailure(
                f"{relative} already exists in the vault with a different definition. "
                "Re-run with --on-concept-conflict keep to keep the vault's wording, "
                "or replace to take the course's. Evidence is merged either way."
            )
        chosen = delivered if differs and policy == "replace" else existing
        chosen.set_evidence(merged, titles)
        content = chosen.rendered()
        changed = content != target.read_bytes()
        if changed:
            writes[relative] = content
        report.append({
            "path": relative,
            "action": f"conflict-{policy}" if differs else "merged" if changed else "unchanged",
        })
    return writes, report


def load_imports(vault: Path) -> dict:
    path = vault / IMPORTS
    if not path.is_file():
        return {"schema": SCHEMA, "courses": []}
    data = read_json(path)
    if data.get("schema") != SCHEMA or not isinstance(data.get("courses"), list):
        raise ImportFailure(f"Unrecognized import record: {IMPORTS}")
    return data


def local_changes(vault: Path, prefix: str, recorded: dict) -> list[str]:
    """Name every course file the reader changed since it was imported."""
    changes = []
    base = vault / prefix
    present = set(walk(vault, base)) if base.is_dir() else set()
    for relative, expected in sorted(recorded.items()):
        path = vault / relative
        if not path.is_file():
            changes.append(f"{relative} (missing)")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            changes.append(f"{relative} (modified)")
    changes.extend(f"{relative} (added)" for relative in sorted(present - set(recorded)))
    return changes


def plan_course(staged: dict, vault: Path, course: str, records: dict, force: bool) -> dict:
    prefix = f"courses/{course}"
    files = course_files(staged["root"], course)
    entry = Note.read(staged["root"], f"{prefix}/course.md")
    previous = records.get(prefix)
    if previous is None and (vault / prefix).exists():
        raise ImportFailure(
            f"{prefix} already exists in the vault but was not imported by Clew. "
            "Move it aside before importing."
        )
    if previous and not force:
        changes = local_changes(vault, prefix, previous.get("files", {}))
        if changes:
            raise ImportFailure(
                f"{prefix} has local changes that re-import would overwrite:\n"
                + "\n".join(f"      {item}" for item in changes)
                + "\n      Re-apply them elsewhere, or pass --force to discard them."
            )
    return {
        "course": course, "prefix": prefix, "files": files,
        "notes": [Note.read(staged["root"], name) for name in files if name.endswith(".md")],
        "course_id": entry.data.get("id"),
        "removed": sorted(set((previous or {}).get("files", {})) - set(files)),
    }


def import_courses(source: str, courses: list[str], vault: Path, ref: str | None = None,
                   policy: str = "abort", force: bool = False,
                   dry_run: bool = False) -> dict:
    if not courses:
        raise ImportFailure("Name at least one course with --course.")
    if len(set(courses)) != len(courses):
        raise ImportFailure("Each course may be imported once per run.")
    workspace = Path(tempfile.mkdtemp(prefix="clew-import-"))
    try:
        staged = stage(source, ref, courses, workspace)
        records = {entry["course_path"]: entry for entry in load_imports(vault)["courses"]}
        plans = [plan_course(staged, vault, course, records, force) for course in courses]
        arriving = {name for plan in plans for name in plan["files"]}
        concepts = concept_closure(
            staged["root"], [note for plan in plans for note in plan["notes"]])
        keeps = {
            target for concept in concepts.values() for target in concept.evidence()
            if target in arriving or (vault / target).is_file()
        }
        titles = Titles(vault, {note.relative: note.data.get("title")
                                for plan in plans for note in plan["notes"]})
        concept_writes, concept_report = reconcile(vault, concepts, keeps, policy, titles)
        writes = {name: (staged["root"] / name).read_bytes()
                  for plan in plans for name in plan["files"]}
        writes.update(concept_writes)
        result = {
            "schema": "clew-import/v1",
            "source": staged["source"], "source_kind": staged["kind"],
            "ref": staged["ref"], "commit": staged["commit"], "dry_run": dry_run,
            "courses": [
                {"course_id": plan["course_id"], "course_path": plan["prefix"],
                 "files": len(plan["files"]), "removed": plan["removed"]}
                for plan in plans
            ],
            "concepts": concept_report,
            "written": sorted(writes),
        }
        if not dry_run:
            apply_writes(vault, writes, [name for plan in plans for name in plan["removed"]])
            record_imports(vault, staged, plans, concepts, writes)
        return result
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def apply_writes(vault: Path, writes: dict, removed: list[str]) -> None:
    for relative in sorted(writes):
        if PurePosixPath(relative).parts[0] in RESERVED:
            raise ImportFailure(f"Refusing to write a reserved path: {relative}")
        path = vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(path, writes[relative])
    for relative in removed:
        path = vault / relative
        if path.is_file() and not path.is_symlink():
            path.unlink()
        parent = path.parent
        while parent != vault and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


def record_imports(vault: Path, staged: dict, plans: list[dict], concepts: dict,
                   writes: dict) -> None:
    data = load_imports(vault)
    entries = {entry["course_path"]: entry for entry in data["courses"]}
    stamp = datetime.date.today().isoformat()
    for plan in plans:
        entries[plan["prefix"]] = {
            "course_id": plan["course_id"],
            "course_path": plan["prefix"],
            "source": staged["source"],
            "source_kind": staged["kind"],
            "ref": staged["ref"],
            "commit": staged["commit"],
            "imported_at": stamp,
            "files": {name: hashlib.sha256(writes[name]).hexdigest()
                      for name in plan["files"]},
            "concepts": sorted(concepts),
        }
    data["courses"] = [entries[key] for key in sorted(entries)]
    path = vault / IMPORTS
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def describe(result: dict) -> str:
    lines = [
        ("Would import" if result["dry_run"] else "Imported")
        + f" from {result['source']}"
        + (f" at {result['commit'][:12]}" if result["commit"] else "")
    ]
    for course in result["courses"]:
        removed = f", {len(course['removed'])} removed" if course["removed"] else ""
        lines.append(f"  {course['course_path']}: {course['files']} files{removed}")
    lines.extend(f"  {item['path']}: {item['action']}" for item in result["concepts"])
    lines.append("Run the Clew validator over each imported course before reading it.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True, help="Git URL or local content directory")
    parser.add_argument("--ref", help="Branch, tag or commit; defaults to the remote's HEAD")
    parser.add_argument("--course", action="append", default=[], metavar="KEY",
                        help="Course directory key; repeat to import several at once")
    parser.add_argument("--vault", help="Override the vault from .clew.local.json")
    parser.add_argument("--on-concept-conflict", choices=("abort", "keep", "replace"),
                        default="abort", help="How to handle a redefined shared concept")
    parser.add_argument("--force", action="store_true",
                        help="Discard local changes to previously imported course files")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    arguments = parser.parse_args(argv)
    try:
        result = import_courses(
            arguments.source, arguments.course, vault_path(arguments.vault), arguments.ref,
            arguments.on_concept_conflict, arguments.force, arguments.dry_run)
    except (NoteError, VaultError, OSError, UnicodeError, ValueError) as error:
        print(f"Clew: {error}", file=sys.stderr)
        return 1
    print(describe(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
