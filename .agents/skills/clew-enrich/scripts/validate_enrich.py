"""Capture a local baseline or check anchored enrichment without writing notes."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
import yaml


class EnrichError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EnrichError(message)


def local_path(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    for item in [*reversed(path.parents), path]:
        if not item.exists() and not item.is_symlink():
            continue
        info = item.lstat()
        tag = getattr(info, "st_reparse_tag", 0)
        require(not item.is_symlink() and not tag & 0x20000000,
                f"Redirected path is unsupported: {item}")
        if getattr(info, "st_file_attributes", 0) & 0x400:
            require(bool(tag), f"Unknown reparse point: {item}")
    return path


def parser() -> MarkdownIt:
    return MarkdownIt("commonmark").enable("table").use(dollarmath_plugin)


ANCHOR = re.compile(r"\^([A-Za-z0-9-]+)")
QUESTION_FIELD = re.compile(r"\[question::\s*(\[\[.*?\]\])\]")
ROLES = {"courses": "course", "exercices": "exercise", "corriges": "correction", "aides": "help"}


@dataclass
class Block:
    kind: str
    label: str
    anchor: str
    lines: list[str]
    start: int
    end: int

    @property
    def fields(self) -> str:
        if self.lines and re.match(r"^\[(src|question|needs)::", self.lines[0]):
            return self.lines[0]
        return ""

    @property
    def text(self) -> str:
        return "\n".join(self.lines[1:] if self.fields else self.lines).strip()


class Note:
    def __init__(self, path: Path, text: str, role: str):
        self.path = path
        self.text = text
        self.header = ""
        self.body = text
        self.metadata = {}
        match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
        if match:
            self.header = text[:match.end()]
            self.body = text[match.end():]
            self.metadata = yaml.safe_load(match[1]) or {}
        require(isinstance(self.metadata, dict), f"Invalid frontmatter: {path}")
        self.id = self.metadata.get("id", path.stem)
        self.role = self.metadata.get("type", role)
        require(isinstance(self.id, str) and bool(self.id), f"Invalid note ID: {path}")
        self.lines = self.body.splitlines()
        self.tokens = parser().parse(self.body)
        self.anchors: set[str] = set()
        self.anchor_lines: set[int] = set()
        for token in self.tokens:
            if token.type == "paragraph_open" and token.level == 0 and token.map:
                start, end = token.map
                anchor = ANCHOR.fullmatch(self.lines[start]) if end == start + 1 else None
                if anchor:
                    require(anchor[1] not in self.anchors, f"Duplicate anchor: {self.id}#^{anchor[1]}")
                    self.anchors.add(anchor[1])
                    self.anchor_lines.add(start)
        self.blocks = []
        for token in self.tokens:
            if token.type != "blockquote_open" or token.level != 0 or not token.map:
                continue
            start, quote_end = token.map
            callout = re.fullmatch(
                r"> \[!(question|reponse|hint|explanation|method)\](?: (.*))?",
                self.lines[start])
            if not callout:
                continue
            quoted = self.lines[start + 1:quote_end]
            require(all(line == ">" or line.startswith("> ") for line in quoted),
                    f"Callout needs explicit quote prefixes: {path}, body line {start + 1}")
            end = quote_end
            while end < len(self.lines) and not self.lines[end]:
                end += 1
            anchor = ANCHOR.fullmatch(self.lines[end]) if end < len(self.lines) else None
            if anchor:
                end += 1
                if end < len(self.lines) and not self.lines[end]:
                    end += 1
            else:
                end = quote_end
            self.blocks.append(Block(callout[1], callout[2] or "", anchor[1] if anchor else "",
                                     [line[2:] if line.startswith("> ") else "" for line in quoted],
                                     start, end))

    def block(self, fragment: str, kind: str) -> Block:
        matches = [block for block in self.blocks
                   if fragment == "^" + block.anchor and block.anchor and block.kind == kind]
        require(len(matches) == 1, f"Expected anchored {kind}: {self.id}#{fragment}")
        return matches[0]

    def check_fragment(self, fragment: str) -> None:
        require(bool(fragment), f"Course reference needs a heading or block: {self.id}")
        if fragment.startswith("^"):
            require(fragment[1:] in self.anchors, f"Missing course block: {self.id}#{fragment}")
        else:
            matches = [self.tokens[index + 1].content for index, token in enumerate(self.tokens)
                       if token.type == "heading_open" and self.tokens[index + 1].content == fragment]
            require(len(matches) == 1, f"Missing or ambiguous course heading: {self.id}#{fragment}")

    def projection(self) -> list[str]:
        result = []
        position = 0

        def outside(start: int, end: int) -> list[str]:
            removed = set()
            for anchor in self.anchor_lines & set(range(start, end)):
                removed.add(anchor)
                for neighbor in (anchor - 1, anchor + 1):
                    if start <= neighbor < end and not self.lines[neighbor]:
                        removed.add(neighbor)
            return [self.lines[index] for index in range(start, end) if index not in removed]

        for block in self.blocks:
            if block.kind not in {"question", "reponse"}:
                continue
            result.extend(outside(position, block.start))
            content = list(block.lines)
            if block.fields:
                field = QUESTION_FIELD.sub("", content[0]).rstrip()
                content[:1] = [field] if field else []
            result.extend(content)
            position = block.end
        result.extend(outside(position, len(self.lines)))
        return result


def inventory(root: Path) -> tuple[dict[str, bytes], list[str]]:
    root = local_path(root)
    require(root.is_dir() and any((root / role).is_dir() for role in ROLES if role != "aides"),
            f"Select one chapter with learning-note directories: {root}")
    files = {}
    directories = []

    def walk(directory: Path) -> None:
        for path in sorted(directory.iterdir()):
            if path.name.startswith("."):
                continue
            path = local_path(path)
            if path.is_dir():
                directories.append(path.relative_to(root).as_posix())
                walk(path)
            else:
                require(path.is_file(), f"Unsupported filesystem entry: {path}")
                files[path.relative_to(root).as_posix()] = path.read_bytes()

    walk(root)
    return files, directories


def role_of(name: str) -> str | None:
    path = Path(name)
    return ROLES.get(path.parts[0]) if len(path.parts) > 1 and path.suffix.lower() == ".md" else None


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture(root: Path, destination: Path) -> dict:
    root, destination = local_path(root), local_path(destination)
    require(not destination.is_relative_to(root), "Baseline must be outside the chapter.")
    require(destination.parent.is_dir(), f"Baseline parent does not exist: {destination.parent}")
    files, directories = inventory(root)
    records = {}
    for name, data in files.items():
        record = {"sha256": digest(data)}
        if role_of(name) in {"exercise", "correction"}:
            text = data.decode("utf-8-sig")
            Note(root / name, text, role_of(name))
            record["text"] = text
        records[name] = record
    baseline = {"schema_version": 1, "chapter": str(root), "files": records, "directories": directories}
    encoded = json.dumps(baseline, ensure_ascii=False, indent=2)
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {"status": "captured", "baseline": str(destination), "files": len(files),
            "excluded": ["hidden entries"]}


def resolve(notes: list[Note], ref: str, origin: Note) -> tuple[Note, str]:
    require(isinstance(ref, str) and bool(ref), f"Missing reference in {origin.path}")
    if ref.startswith("[[") and ref.endswith("]]"):
        ref = ref[2:-2]
    ref = ref.split("|", 1)[0]
    name, _, fragment = ref.partition("#")
    relative = Path(os.path.abspath(origin.path.parent / name))
    matches = [note for note in notes if
               (not name and note is origin) or
               name in {note.id, note.path.stem, note.path.name, str(note.path), note.path.as_posix()} or
               (bool(name) and relative == note.path)]
    require(len(matches) == 1, f"Missing or ambiguous note reference in {origin.id}: {ref}")
    return matches[0], fragment


def references(text: str) -> list[str]:
    refs = []

    def wikilink(state, silent: bool) -> bool:
        match = re.match(r"\[\[([^\]\n]+)\]\]", state.src[state.pos:])
        if not match:
            return False
        if not silent:
            token = state.push("enrich_wikilink", "", 0)
            token.content = match[1]
        state.pos += len(match[0])
        return True

    md = parser()
    md.inline.ruler.before("link", "enrich_wikilink", wikilink)
    for token in md.parse(text):
        for child in token.children or []:
            if child.type == "enrich_wikilink":
                refs.append(child.content)
            elif child.type == "link_open":
                url = urlsplit(child.attrGet("href") or "")
                if not url.scheme and not url.netloc and (not url.path or url.path.lower().endswith(".md")):
                    refs.append(unquote(url.path) + ("#" + unquote(url.fragment) if url.fragment else ""))
    return refs


def validate(root: Path, baseline_path: Path) -> dict:
    root = local_path(root)
    baseline_path = local_path(baseline_path)
    require(not baseline_path.is_relative_to(root), "Baseline must be outside the chapter.")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    require(isinstance(baseline, dict) and set(baseline) == {"schema_version", "chapter", "files", "directories"}
            and type(baseline["schema_version"]) is int and baseline["schema_version"] == 1
            and baseline["chapter"] == str(root), "Invalid baseline or different chapter.")
    previous = baseline["files"]
    require(isinstance(previous, dict) and bool(previous), "Baseline needs a file inventory.")
    current, directories = inventory(root)
    previous_directories = baseline["directories"]
    require(isinstance(previous_directories, list)
            and all(isinstance(name, str) for name in previous_directories),
            "Invalid baseline directory inventory.")
    require(not set(previous_directories) - set(directories), "Original directories removed.")
    added_directories = sorted(set(directories) - set(previous_directories))
    require(all(name == "aides" or name.startswith("aides/") for name in added_directories),
            f"Only new aid directories are allowed: {added_directories}")
    require(not set(previous) - set(current), f"Original files removed: {sorted(set(previous) - set(current))}")
    for name, record in previous.items():
        require(isinstance(record, dict) and set(record) <= {"sha256", "text"}
                and isinstance(record.get("sha256"), str), f"Invalid baseline entry: {name}")
        data = current[name]
        if digest(data) == record["sha256"]:
            continue
        role = role_of(name)
        require(role in {"exercise", "correction"} and isinstance(record.get("text"), str),
                f"Untouched file changed: {name}")
        old = Note(root / name, record["text"], role)
        new = Note(root / name, data.decode("utf-8-sig"), role)
        require(old.header == new.header, f"Original frontmatter changed: {name}")
        require(old.anchors <= new.anchors, f"Existing anchors removed: {name}")
        require(old.projection() == new.projection(),
                f"Supplied text/formatting changed: {name}; preserve quoted source blank lines too.")
        for block in old.blocks:
            if block.anchor:
                matching = [item for item in new.blocks if item.anchor == block.anchor]
                require(len(matching) == 1 and matching[0].kind == block.kind
                        and matching[0].label == block.label,
                        f"Existing block changed: {name}#^{block.anchor}")
                old_links = QUESTION_FIELD.findall(block.fields)
                require(not old_links or old_links == QUESTION_FIELD.findall(matching[0].fields),
                        f"Existing answer/question link changed: {name}#^{block.anchor}")
            elif block.kind in {"question", "reponse"}:
                require(any(item.kind == block.kind and item.label == block.label
                            and item.text == block.text for item in new.blocks),
                        f"Existing unanchored callout changed: {name}, {block.label}")
    added = sorted(set(current) - set(previous))
    require(all(role_of(name) == "help" for name in added),
            f"Only new Markdown aid notes under aides/ are allowed: {added}")
    notes = [Note(root / name, data.decode("utf-8-sig"), role_of(name))
             for name, data in current.items() if role_of(name)]
    for note in notes:
        if note.path.relative_to(root).as_posix() in added:
            require(note.role == "help", f"New aid note needs type: help: {note.path}")
    ids = [note.id for note in notes]
    require(len(ids) == len(set(ids)), "Duplicate learning-note IDs.")
    questions = set()
    answers = {}
    for note in notes:
        for block in note.blocks:
            if block.kind not in {"question", "reponse"}:
                continue
            expected = "exercise" if block.kind == "question" else "correction"
            require(note.role == expected and bool(block.anchor) and bool(block.text),
                    f"Invalid {block.kind} block in {note.id}: {block.anchor or '(no anchor)'}")
            key = (note.id, "^" + block.anchor)
            if block.kind == "question":
                questions.add(key)
            else:
                links = QUESTION_FIELD.findall(block.fields)
                require(len(links) == 1, f"Answer needs one question link: {note.id}#^{block.anchor}")
                question_note, fragment = resolve(notes, links[0], note)
                require(question_note.role == "exercise", f"Answer targets a non-exercise: {links[0]}")
                question_note.block(fragment, "question")
                answers[key] = (question_note.id, fragment)
    hints = explanations = 0
    for aid in notes:
        if aid.role != "help":
            continue
        question_note, question_fragment = resolve(notes, aid.metadata.get("question"), aid)
        require(question_note.role == "exercise", f"Aid targets a non-exercise: {aid.id}")
        question_note.block(question_fragment, "question")
        question_key = (question_note.id, question_fragment)
        correction = aid.metadata.get("correction")
        if correction is not None:
            answer_note, answer_fragment = resolve(notes, correction, aid)
            require(answers.get((answer_note.id, answer_fragment)) == question_key,
                    f"Aid correction/question mismatch: {aid.id}")
        additions = [block for block in aid.blocks if block.kind in {"hint", "explanation"}]
        require(bool(additions), f"Aid needs hints or explanations: {aid.id}")
        for block in additions:
            address = f"{aid.id}#^{block.anchor}"
            require(bool(block.anchor) and bool(block.text), f"Empty or unanchored aid: {address}")
            if block.kind == "explanation":
                require(correction is not None, f"Explanation needs a supplied correction: {address}")
                explanations += 1
            else:
                hints += 1
            course_refs = 0
            for ref in references(block.text):
                target, fragment = resolve(notes, ref, aid)
                if target.role in {"course", "section"}:
                    target.check_fragment(fragment)
                    course_refs += 1
                elif fragment:
                    require(fragment.startswith("^") and fragment[1:] in target.anchors,
                            f"Invalid aid link: {address} -> {ref}")
            require(course_refs > 0, f"Aid needs a precise course link: {address}")
    corrected = set(answers.values())
    return {"status": "validated", "chapter": str(root), "new_aids": added,
            "questions": len(questions), "supplied_answers": len(answers),
            "hints": hints, "explanations": explanations,
            "questions_without_correction": [f"{note}#{fragment}"
                                             for note, fragment in sorted(questions - corrected)],
            "limitations": ["Structural preservation and references checked; pedagogical correctness needs agent review."]}


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("chapter", type=Path)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture", type=Path, metavar="BASELINE",
                      help="Save a new baseline outside the chapter before editing.")
    mode.add_argument("--before", type=Path, metavar="BASELINE",
                      help="Validate current notes against the pre-edit baseline.")
    args = cli.parse_args()
    try:
        result = capture(args.chapter, args.capture) if args.capture else validate(args.chapter, args.before)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (EnrichError, OSError, ValueError, yaml.YAMLError) as error:
        print(f"Enrich error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
