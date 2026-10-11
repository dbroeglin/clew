"""Capture a baseline, review scratch drafts, or validate additive chapter aids."""
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
UNIT_OPEN = re.compile(r"%% clew:unit (section|exercise|correction) ([A-Za-z0-9-]+) %%")
UNIT_CLOSE = re.compile(r"%% /clew:unit ([A-Za-z0-9-]+) %%")
CALLOUT = re.compile(r"> \[!(question|reponse|hint|explanation)\][+-]?(?: (.*))?")
FRONTMATTER = re.compile(r"\A---(?:\r\n|\r|\n)(.*?)(?:\r\n|\r|\n)---(?:(?:\r\n|\r|\n)|$)", re.S)
RELATIONSHIP = re.compile(r"^\s*(?:>\s*)?\[(Exercise|Question)\]\(([^)\r\n]+)\)\s*$")


@dataclass
class Unit:
    kind: str
    identifier: str
    start: int
    end: int


@dataclass
class Block:
    kind: str
    label: str
    anchor: str
    lines: list[str]
    start: int
    end: int

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()

    @property
    def substantive_text(self) -> str:
        lines = [line for line in self.lines
                 if not RELATIONSHIP.fullmatch(line)
                 and not line.strip().startswith("[PDF p. ")]
        return "\n".join(lines).strip()


class Note:
    def __init__(self, path: Path, text: str, relative: str):
        self.path, self.text, self.relative = path, text, relative
        match = FRONTMATTER.match(text)
        require(match is not None, f"Missing or unclosed frontmatter: {relative}")
        self.header = text[:match.end()]
        self.body = text[match.end():]
        self.metadata = yaml.safe_load(match[1]) or {}
        require(isinstance(self.metadata, dict), f"Invalid frontmatter: {relative}")
        self.id = self.metadata.get("id")
        self.role = self.metadata.get("role", "")
        self.lines = self.body.splitlines()
        self.tokens = parser().parse(self.body)
        self.protected_lines = {
            line
            for token in self.tokens
            if token.type in {"fence", "code_block", "math_block"} and token.map
            for line in range(*token.map)
        }
        self.anchors: dict[str, list[int]] = {}
        for index, token in enumerate(self.tokens):
            if token.type != "paragraph_open" or token.level != 0 or not token.map:
                continue
            start = token.map[0]
            content = self.tokens[index + 1].content.rstrip()
            anchor = re.search(r"(?:^|\s)\^([A-Za-z0-9-]+)$", content)
            if anchor:
                self.anchors.setdefault(anchor[1], []).append(start)
        self.units = self._units()
        self.blocks = self._blocks()
        self.headings = [
            self.tokens[index + 1].content
            for index, token in enumerate(self.tokens)
            if token.type == "heading_open"
        ]

    def _units(self) -> list[Unit]:
        stack: list[Unit] = []
        units = []
        for index, line in enumerate(self.lines):
            if index in self.protected_lines:
                continue
            opening, closing = UNIT_OPEN.fullmatch(line), UNIT_CLOSE.fullmatch(line)
            if line.startswith(("%% clew:unit", "%% /clew:unit")):
                require(opening or closing,
                        f"Malformed source unit marker: {self.relative}, line {index + 1}")
            if opening:
                require(not stack or stack[-1].kind == "section",
                        f"Unsupported nested source unit: {self.relative}, line {index + 1}")
                require(not any(unit.identifier == opening[2] for unit in units + stack),
                        f"Duplicate source unit ID: {self.id}#{opening[2]}")
                stack.append(Unit(opening[1], opening[2], index, len(self.lines)))
            elif closing:
                require(stack and stack[-1].identifier == closing[1],
                        f"Mismatched source unit boundary: {self.relative}, line {index + 1}")
                unit = stack.pop()
                unit.end = index + 1
                if unit.kind in {"exercise", "correction"}:
                    require(unit.identifier in self.anchors and any(
                        unit.start < anchor < unit.end for anchor in self.anchors[unit.identifier]),
                        f"Missing {unit.kind} entry anchor: {self.id}#^{unit.identifier}")
                units.append(unit)
        require(not stack, f"Unclosed source unit in {self.relative}")
        return units

    def _blocks(self) -> list[Block]:
        blocks = []
        for token in self.tokens:
            if token.type != "blockquote_open" or token.level != 0 or not token.map:
                continue
            start, quote_end = token.map
            callout = CALLOUT.fullmatch(self.lines[start])
            if not callout:
                continue
            quoted = self.lines[start + 1:quote_end]
            require(all(line == ">" or line.startswith("> ") for line in quoted),
                    f"Callout needs explicit quote prefixes: {self.relative}, line {start + 1}")
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
            kind = "answer" if callout[1] == "reponse" else callout[1]
            blocks.append(Block(kind, callout[2] or "", anchor[1] if anchor else "",
                                [line[2:] if line.startswith("> ") else "" for line in quoted],
                                start, end))
        return blocks

    def unit_for(self, line: int, kind: str) -> Unit | None:
        matches = [unit for unit in self.units
                   if unit.kind == kind and unit.start < line < unit.end]
        return matches[0] if len(matches) == 1 else None

    def block(self, fragment: str, kind: str) -> Block:
        matches = [block for block in self.blocks
                   if fragment == "^" + block.anchor and block.anchor and block.kind == kind]
        require(len(matches) == 1, f"Expected anchored {kind}: {self.id}#{fragment}")
        return matches[0]

    def check_fragment(self, fragment: str) -> None:
        require(bool(fragment), f"Course reference needs a heading or block: {self.id}")
        if fragment.startswith("^"):
            require(len(self.anchors.get(fragment[1:], [])) == 1,
                    f"Missing or ambiguous course block: {self.id}#{fragment}")
        else:
            require(self.headings.count(fragment) == 1,
                    f"Missing or ambiguous course heading: {self.id}#{fragment}")


def inventory(root: Path) -> tuple[dict[str, bytes], list[str]]:
    root = local_path(root)
    require(root.is_dir(), f"Prepared chapter is missing: {root}")
    files: dict[str, bytes] = {}
    directories: list[str] = []

    def walk(directory: Path) -> None:
        for path in sorted(directory.iterdir()):
            relative = path.relative_to(root).as_posix()
            if path.name.startswith(".") and relative != ".clew" and not relative.startswith(".clew/"):
                continue
            path = local_path(path)
            if path.is_dir():
                directories.append(relative)
                walk(path)
            else:
                require(path.is_file(), f"Unsupported filesystem entry: {path}")
                files[relative] = path.read_bytes()

    walk(root)
    require("index.md" in files and ".clew/preparation.json" in files,
            f"Select one prepared Import chapter: {root}")
    return files, directories


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_chapter(root: Path, files: dict[str, bytes]) -> tuple[dict[str, Note], list[Note]]:
    try:
        preparation = json.loads(files[".clew/preparation.json"].decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise EnrichError(f"Invalid .clew/preparation.json: {error}") from error
    require(isinstance(preparation, dict)
            and type(preparation.get("schema_version")) is int
            and preparation.get("schema_version") == 1
            and preparation.get("status") == "complete",
            "Import preparation must be schema 1 and complete.")
    try:
        index_text = files["index.md"].decode("utf-8-sig")
        index_match = FRONTMATTER.match(index_text)
        index_metadata = yaml.safe_load(index_match[1]) if index_match else None
    except (UnicodeError, yaml.YAMLError) as error:
        raise EnrichError(f"Invalid chapter index: {error}") from error
    require(isinstance(index_metadata, dict) and index_metadata.get("type") == "chapter"
            and type(index_metadata.get("clew_schema")) is int
            and index_metadata.get("clew_schema") == 1, "Prepared chapter needs an Import index.")
    records = preparation.get("documents")
    require(isinstance(records, list) and bool(records), "Preparation record has no documents.")
    notes: list[Note] = []
    for relative, data in files.items():
        if (not relative.lower().endswith(".md") or relative == "index.md"
                or relative.startswith(".clew/") or relative.startswith("aides/")):
            continue
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError as error:
            raise EnrichError(f"Markdown must be UTF-8: {relative}") from error
        note = Note(root / Path(relative), text, relative)
        require(note.metadata.get("type") == "document"
                and type(note.metadata.get("clew_schema")) is int
                and note.metadata.get("clew_schema") == 1,
                f"Enrich accepts only Import document notes: {relative}")
        require(isinstance(note.id, str) and bool(note.id)
                and note.role in {"course", "exercise", "correction", "mixed", "unknown"},
                f"Invalid Import document identity/role: {relative}")
        notes.append(note)
    require(bool(notes), "Prepared chapter has no document notes.")
    expected = {(record.get("id"), record.get("path"), record.get("role"))
                for record in records if isinstance(record, dict)}
    actual = {(note.id, note.relative, note.role) for note in notes}
    require(len(expected) == len(records) and expected == actual,
            "Document notes differ from .clew/preparation.json.")
    aids = []
    for relative, data in files.items():
        if not relative.startswith("aides/") or not relative.lower().endswith(".md"):
            continue
        try:
            aid = Note(root / Path(relative), data.decode("utf-8-sig"), relative)
        except UnicodeError as error:
            raise EnrichError(f"Markdown must be UTF-8: {relative}") from error
        require(aid.metadata.get("type") == "help" and isinstance(aid.id, str) and bool(aid.id),
                f"Aid needs a unique id and type: help: {relative}")
        aids.append(aid)
    ids = [note.id for note in notes + aids]
    require(len(ids) == len(set(ids)), "Duplicate document/aid IDs.")
    for note in notes + aids:
        duplicates = sorted(anchor for anchor, lines in note.anchors.items() if len(lines) != 1)
        require(not duplicates, f"Duplicate anchors in {note.id}: {duplicates}")
    return {note.id: note for note in notes}, aids


def capture(root: Path, destination: Path) -> dict:
    root, destination = local_path(root), local_path(destination)
    require(not destination.is_relative_to(root), "Baseline must be outside the chapter.")
    require(destination.parent.is_dir(), f"Baseline parent does not exist: {destination.parent}")
    files, directories = inventory(root)
    read_chapter(root, files)
    baseline = {"schema_version": 2, "chapter": str(root),
                "files": {name: sha256(data) for name, data in files.items()},
                "directories": directories}
    encoded = json.dumps(baseline, ensure_ascii=False, indent=2)
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(encoded + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return {"status": "captured", "baseline": str(destination), "files": len(files),
            "excluded": ["hidden entries except .clew"]}


def resolve(notes: dict[str, Note], ref: str, origin: Note) -> tuple[Note, str]:
    require(isinstance(ref, str) and bool(ref), f"Missing reference in {origin.relative}")
    ref = ref.strip()
    if ref.startswith("[[") and ref.endswith("]]"):
        ref = ref[2:-2]
        ref = ref.split("|", 1)[0]
        name, _, fragment = ref.partition("#")
        matches = [note for note in notes.values()
                   if (not name and note is origin)
                   or name in {note.path.stem, note.path.name, note.relative,
                               str(Path(note.relative).with_suffix("")).replace("\\", "/")}]
    else:
        parsed = urlsplit(ref)
        require(not parsed.scheme and not parsed.netloc, f"External reference is not a local note: {ref}")
        name, fragment = unquote(parsed.path), unquote(parsed.fragment)
        relative = Path(os.path.abspath(origin.path.parent / name)) if name else origin.path
        matches = [note for note in notes.values()
                   if (not name and note is origin)
                   or note.path == relative]
    require(len(matches) == 1, f"Missing or ambiguous note reference in {origin.id}: {ref}")
    return matches[0], fragment


def link_references(text: str) -> list[tuple[str, str]]:
    links = []

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
        children = token.children or []
        for index, child in enumerate(children):
            if child.type == "enrich_wikilink":
                _, _, label = child.content.partition("|")
                links.append(("[[" + child.content + "]]", label))
            elif child.type == "link_open":
                url = urlsplit(child.attrGet("href") or "")
                if not url.scheme and not url.netloc and (
                        not url.path or url.path.lower().endswith(".md")):
                    label = []
                    for part in children[index + 1:]:
                        if part.type == "link_close":
                            break
                        label.append(part.content)
                    links.append((child.attrGet("href") or "", "".join(label)))
    return links


def links_in(text: str) -> list[str]:
    return [reference for reference, _ in link_references(text)]


def require_wikilink_label(reference: str, origin: Note) -> None:
    require(isinstance(reference, str) and reference.startswith("[[") and reference.endswith("]]"),
            f"New aid frontmatter needs a labeled wikilink: {origin.relative}")
    _, separator, label = reference[2:-2].partition("|")
    require(bool(separator) and bool(label.strip()),
            f"New aid link needs a display label: {origin.relative}: {reference}")


def check_display_math(block: Block, address: str) -> None:
    tokens = parser().parse(block.text)
    protected = {
        line for token in tokens if token.type in {"fence", "code_block"} and token.map
        for line in range(*token.map)
    }
    lines = block.text.splitlines()
    delimiters = [index for index, line in enumerate(lines)
                  if line.strip() == "$$" and index not in protected]
    require(len(delimiters) % 2 == 0, f"Unpaired display math delimiter: {address}")
    for opening, closing in zip(delimiters[::2], delimiters[1::2]):
        require((opening == 0 or not lines[opening - 1].strip())
                and (closing == len(lines) - 1 or not lines[closing + 1].strip()),
                f"Display math needs blank quoted lines before and after: {address}")


def relationship_links(note: Note, block: Block | Unit, label: str) -> list[str]:
    start, end = block.start, block.end
    matches = []
    for line in note.lines[start:end]:
        match = RELATIONSHIP.fullmatch(line)
        if match and match[1].casefold() == label.casefold():
            matches.append(match[2])
    return matches


def validate(root: Path, baseline_path: Path, *, drafts: dict[str, bytes] | None = None) -> dict:
    root, baseline_path = local_path(root), local_path(baseline_path)
    require(not baseline_path.is_relative_to(root), "Baseline must be outside the chapter.")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8-sig"))
    require(isinstance(baseline, dict) and set(baseline) == {
        "schema_version", "chapter", "files", "directories"
    } and type(baseline["schema_version"]) is int and baseline["schema_version"] == 2
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
    for name, expected_hash in previous.items():
        require(isinstance(expected_hash, str), f"Invalid baseline entry: {name}")
        require(sha256(current[name]) == expected_hash, f"Original file changed: {name}")
    added = sorted(set(current) - set(previous))
    require(all(name.startswith("aides/") and name.lower().endswith(".md") for name in added),
            f"Only new Markdown aid notes under aides/ are allowed: {added}")
    if drafts is not None:
        require(not added and not added_directories,
                "Review drafts against the unchanged pre-edit chapter, not persisted additions.")
        require(len({name.casefold() for name in drafts}) == len(drafts), "Duplicate draft destinations.")
        existing_paths = {name.casefold() for name in current}
        for relative, data in drafts.items():
            require(relative.startswith("aides/") and relative.lower().endswith(".md")
                    and Path(relative).parts == ("aides", Path(relative).name),
                    f"Invalid draft destination: {relative}")
            require(relative.casefold() not in existing_paths,
                    f"Draft would overwrite an existing file: {relative}")
            current[relative] = data
        added = sorted(drafts)
    notes, aids = read_chapter(root, current)
    new_aids = set(added)
    for aid in aids:
        if aid.relative in new_aids:
            require(type(aid.metadata.get("schema_version")) is int
                    and aid.metadata["schema_version"] == 1,
                    f"New aid needs schema_version: 1: {aid.relative}")

    questions: dict[tuple[str, str], tuple[Note, Block, Unit]] = {}
    answers: dict[tuple[str, str], tuple[Note, Block, Unit, tuple[str, str] | None]] = {}
    for note in notes.values():
        for block in note.blocks:
            if block.kind == "question":
                owner = note.unit_for(block.start, "exercise")
                require(note.role in {"exercise", "mixed"} and owner is not None and block.anchor
                        and bool(block.substantive_text),
                        f"Question must be anchored inside an exercise unit: {note.id}#{block.anchor}")
                questions[(note.id, "^" + block.anchor)] = (note, block, owner)
            elif block.kind == "answer":
                owner = note.unit_for(block.start, "correction")
                require(note.role in {"correction", "mixed"} and owner is not None and block.anchor
                        and bool(block.substantive_text),
                        f"Answer must be anchored inside a correction unit: {note.id}#{block.anchor}")
                links = relationship_links(note, block, "Question")
                require(len(links) <= 1, f"Answer has multiple question links: {note.id}#{block.anchor}")
                answer_key = (note.id, "^" + block.anchor)
                target_key = None
                if links:
                    target_note, fragment = resolve(notes, links[0], note)
                    target = target_note.block(fragment, "question")
                    target_unit = target_note.unit_for(target.start, "exercise")
                    require(target_unit is not None, f"Question has no exercise owner: {links[0]}")
                    target_key = (target_note.id, "^" + target.anchor)
                    answers[answer_key] = (note, block, owner, target_key)
                else:
                    answers[answer_key] = (note, block, owner, None)

    for note in notes.values():
        for unit in note.units:
            if unit.kind != "correction":
                continue
            links = relationship_links(note, unit, "Exercise")
            require(len(links) <= 1, f"Correction has multiple exercise links: {note.id}#{unit.identifier}")
            owners = set()
            if links:
                target_note, fragment = resolve(notes, links[0], note)
                matches = [candidate for candidate in target_note.units
                           if candidate.kind == "exercise" and fragment == "^" + candidate.identifier]
                require(target_note.role in {"exercise", "mixed"} and len(matches) == 1,
                        f"Correction association must target one whole exercise unit: {links[0]}")
                owners.add((target_note.id, matches[0].identifier))
            for _, _, answer_owner, question_key in answers.values():
                if answer_owner is not unit:
                    continue
                if question_key:
                    target_note = notes[question_key[0]]
                    question_data = questions.get((target_note.id, question_key[1]))
                    require(question_data is not None, f"Missing linked question: {question_key}")
                    owners.add((question_data[0].id, question_data[2].identifier))
            require(len(owners) <= 1,
                    f"Answers in correction unit disagree on exercise owner: {note.id}#{unit.identifier}")

    hints = explanations = 0
    aid_targets: dict[tuple[str, str], int] = {}
    new_question_keys = []
    aid_details = []
    for aid in aids:
        question_ref = aid.metadata.get("question")
        if aid.relative in new_aids:
            require_wikilink_label(question_ref, aid)
        question_note, question_fragment = resolve(notes, question_ref, aid)
        question = question_note.block(question_fragment, "question")
        question_unit = question_note.unit_for(question.start, "exercise")
        require(question_note.role == "exercise" and question_unit is not None,
                f"Aid targets a question outside an exercise: {aid.id}")
        question_key = (question_note.id, question_fragment)
        aid_targets[question_key] = aid_targets.get(question_key, 0) + 1
        if aid.relative in new_aids:
            new_question_keys.append(question_key)
        correction_ref = aid.metadata.get("correction")
        if correction_ref is not None:
            if aid.relative in new_aids:
                require_wikilink_label(correction_ref, aid)
            answer_note, answer_fragment = resolve(notes, correction_ref, aid)
            answer_note.block(answer_fragment, "answer")
            require(answers.get((answer_note.id, answer_fragment), (None, None, None, None))[3]
                    == question_key, f"Aid correction/question mismatch: {aid.id}")
        if aid.relative in new_aids:
            for reference, label in link_references(aid.body):
                require(bool(label.strip()), f"New aid link needs a display label: {aid.id}: {reference}")
                target, fragment = resolve(notes, reference, aid)
                if fragment or target.role == "course":
                    target.check_fragment(fragment)
        additions = [block for block in aid.blocks if block.kind in {"hint", "explanation"}]
        require(bool(additions), f"Aid needs hints or explanations: {aid.id}")
        course_links = []
        for block in additions:
            address = f"{aid.id}#^{block.anchor}"
            require(bool(block.anchor) and bool(block.text), f"Empty or unanchored aid: {address}")
            if aid.relative in new_aids:
                check_display_math(block, address)
            if block.kind == "explanation":
                require(correction_ref is not None,
                        f"Explanation needs a supplied correction: {address}")
                explanations += 1
            else:
                hints += 1
            course_refs = 0
            for ref in links_in(block.text):
                target, fragment = resolve(notes, ref, aid)
                if target.role == "course":
                    target.check_fragment(fragment)
                    course_refs += 1
                    course_links.append(ref)
                elif fragment.startswith("^"):
                    require(len(target.anchors.get(fragment[1:], [])) == 1,
                            f"Invalid aid link: {address} -> {ref}")
            require(course_refs > 0, f"Aid needs a precise course link: {address}")
        if aid.relative in new_aids:
            aid_details.append({
                "path": aid.relative, "sha256": sha256(current[aid.relative]),
                "question": question_ref, "question_address": f"{question_note.id}#{question_fragment}",
                "correction": correction_ref, "course_links": sorted(set(course_links)),
                "hints": sum(block.kind == "hint" for block in additions),
                "explanations": sum(block.kind == "explanation" for block in additions),
            })
    corrected = {target for _, _, _, target in answers.values() if target}
    for note_id, fragment in new_question_keys:
        require(aid_targets[(note_id, fragment)] == 1,
                f"Multiple aids target the same question: {note_id}#{fragment}")
    return {"status": "validated", "chapter": str(root), "new_aids": added,
            "documents": len(notes), "questions": len(questions), "supplied_answers": len(answers),
            "hints": hints, "explanations": explanations,
            "aid_details": aid_details,
            "new_hints": sum(row["hints"] for row in aid_details),
            "new_explanations": sum(row["explanations"] for row in aid_details),
            "new_aids_with_explanations": sum(row["explanations"] > 0 for row in aid_details),
            "new_hint_only_aids": sum(row["explanations"] == 0 for row in aid_details),
            "questions_without_aid": [f"{note}#{fragment}"
                                      for note, fragment in sorted(set(questions) - set(aid_targets))],
            "questions_without_correction": [f"{note}#{fragment}"
                                             for note, fragment in sorted(set(questions) - corrected)],
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
