"""Current-note inspection and explicit selection, independent of Ingest."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin


class GenerateError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GenerateError(message)


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
    return MarkdownIt("commonmark", {"html": False}).enable("table").use(dollarmath_plugin)


@dataclass
class Part:
    kind: str
    text: str
    label: str = ""
    block: str = ""
    fields: str = ""

    def display(self) -> str:
        if self.label and self.kind in {"note", "warning", "tip", "method", "hint"}:
            return self.label + "\n\n" + self.text
        return self.text


@dataclass
class Note:
    path: Path
    text: str
    metadata: dict
    body: str
    parts: list[Part] = field(default_factory=list)
    blocks: dict[str, Part] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return str(self.metadata.get("id", self.path.stem))

    @property
    def title(self) -> str:
        return str(self.metadata.get("title", self.path.stem))

    def select(self, fragment: str = "") -> str:
        return "\n\n".join(part.display() for part in self.select_parts(fragment)
                          if part.text.strip())

    def select_parts(self, fragment: str = "") -> list[Part]:
        if not fragment:
            return self.parts
        if fragment.startswith("^"):
            require(fragment[1:] in self.blocks, f"Missing block: {self.id}#{fragment}")
            return [self.blocks[fragment[1:]]]
        match = re.fullmatch(r"L([1-9]\d*)-L([1-9]\d*)", fragment)
        if match:
            start, end = map(int, match.groups())
            lines = self.text.splitlines(keepends=True)
            require(1 <= start <= end <= len(lines), f"Invalid line range: {self.id}#{fragment}")
            header_lines = len(self.text[:len(self.text) - len(self.body)].splitlines())
            require(start > header_lines, "Select note content, not frontmatter.")
            protected = set()
            for token in parser().parse(self.text):
                if token.map and token.type not in {"ordered_list_open", "bullet_list_open"}:
                    protected.update(range(token.map[0] + 1, token.map[1]))
            require(start - 1 not in protected and end not in protected,
                    f"Range bisects Markdown: {self.id}#{fragment}")
            selected = "".join(lines[start - 1:end])
            require(not selected.startswith("---"), "Select note content, not frontmatter.")
            return split_parts(selected)
        tokens = parser().parse(self.body)
        matches = []
        for index, token in enumerate(tokens):
            if token.type == "heading_open" and tokens[index + 1].content == fragment:
                matches.append((index, token))
        require(len(matches) == 1, f"Missing or ambiguous heading: {self.id}#{fragment}")
        index, token = matches[0]
        start = token.map[0]
        end = len(self.body.splitlines())
        for following in tokens[index + 1:]:
            if following.type == "heading_open" and int(following.tag[1:]) <= int(token.tag[1:]):
                end = following.map[0]
                break
        return split_parts("\n".join(self.body.splitlines()[start:end]))


def split_parts(body: str) -> list[Part]:
    # Only exact Ingest structural markers and known field lines are removed.
    lines = body.splitlines()
    parts: list[Part] = []
    plain: list[str] = []

    def flush() -> None:
        if plain:
            parts.append(Part("text", "\n".join(plain).strip()))
            plain.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        if re.fullmatch(r"<!-- /?clew-part:\d+ -->", line):
            index += 1
            continue
        if re.match(r"^\s*(`{3,}|~{3,})", line):
            fence = re.match(r"^\s*(`{3,}|~{3,})", line).group(1)
            plain.append(line)
            index += 1
            while index < len(lines):
                plain.append(lines[index])
                closing = re.fullmatch(r"\s*" + re.escape(fence[0]) + r"{" + str(len(fence)) + r",}\s*", lines[index])
                index += 1
                if closing:
                    break
            continue
        callout = re.match(r"^> \[!(question|reponse|method|hint|note|warning|tip)\][+-]?(?: (.*))?$", line)
        if callout:
            flush()
            quoted = []
            index += 1
            while index < len(lines) and (lines[index] == ">" or lines[index].startswith("> ")):
                quoted.append(lines[index][2:] if lines[index].startswith("> ") else "")
                index += 1
            fields = ""
            if quoted and re.match(r"^\[(src|question|needs)::", quoted[0]):
                fields = quoted.pop(0)
            while index < len(lines) and not lines[index].strip():
                index += 1
            anchor = ""
            if index < len(lines) and re.fullmatch(r"\^[A-Za-z0-9-]+", lines[index]):
                anchor = lines[index][1:]
                index += 1
            parts.append(Part(callout[1], "\n".join(quoted).strip(),
                              callout[2] or "", anchor, fields))
            continue
        anchor = re.fullmatch(r"\^([A-Za-z0-9-]+)", line)
        if anchor:
            if plain:
                plain_text = "\n".join(plain)
                tokens = parser().parse(plain_text)
                starts = [token.map[0] for token in tokens
                          if token.map and token.level == 0]
                if starts:
                    start = starts[-1]
                    if start:
                        parts.append(Part("text", "\n".join(plain[:start]).strip()))
                        plain[:] = plain[start:]
                flush()
            require(bool(parts) and not parts[-1].block, "Block anchor has no unique content.")
            parts[-1].block = anchor[1]
        else:
            plain.append(line)
        index += 1
    flush()
    return parts


def read_note(path: Path) -> Note:
    path = local_path(path)
    require(path.is_file() and path.suffix.lower() == ".md", f"Expected Markdown note: {path}")
    text = path.read_text(encoding="utf-8-sig")
    body = text
    metadata = {}
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if match:
        metadata = yaml.safe_load(match[1]) or {}
        require(isinstance(metadata, dict), f"Frontmatter must be an object: {path}")
        for key in ("id", "title", "type", "question"):
            if key in metadata:
                require(isinstance(metadata[key], str) and bool(metadata[key]),
                        f"Frontmatter {key} must be a nonempty string: {path}")
        body = text[match.end():]
    parts = split_parts(body)
    blocks = {}
    for part in parts:
        if part.block:
            require(part.block not in blocks, f"Duplicate block: {path}#^{part.block}")
            blocks[part.block] = part
    return Note(path, text, metadata, body, parts, blocks)


class Library:
    def __init__(self, paths: list[Path]):
        require(bool(paths), "Select at least one note.")
        self.notes = [read_note(path) for path in paths]
        require(len({note.path for note in self.notes}) == len(self.notes), "Duplicate selected note.")

    def resolve(self, ref: str, origin: Note | None = None) -> tuple[Note, str]:
        require(isinstance(ref, str) and bool(ref), "Expected nonempty note reference.")
        if ref.startswith("[[") and ref.endswith("]]"):
            ref = ref[2:-2].split("|", 1)[0]
        name, _, fragment = ref.partition("#")
        if not name and origin:
            return origin, fragment
        matches = []
        for note in self.notes:
            if name in {note.id, note.path.stem, note.path.name, str(note.path),
                        note.path.as_posix()}:
                matches.append(note)
            elif origin and local_path(origin.path.parent / name) == note.path:
                matches.append(note)
        require(len(matches) == 1, f"Missing or ambiguous selected note: {ref}")
        return matches[0], fragment

    def select(self, ref: str, origin: Note | None = None) -> tuple[Note, str]:
        note, fragment = self.resolve(ref, origin)
        return note, note.select(fragment)

    def inventory(self) -> list[dict]:
        return [{"path": str(note.path), "id": note.id, "title": note.title,
                 "type": note.metadata.get("type"), "lines": len(note.text.splitlines()),
                 "blocks": [{"ref": f"{note.id}#^{part.block}", "kind": part.kind,
                             "label": part.label, "relationships": part.fields}
                            for part in note.parts if part.block],
                 "headings": [token.content for token in parser().parse(note.body)
                              if token.type == "inline" and token.map and
                              note.body.splitlines()[token.map[0]].lstrip().startswith("#")]}
                for note in self.notes]


def command(operation) -> int:
    import sys
    try:
        print(json.dumps(operation(), ensure_ascii=False, indent=2))
        return 0
    except (GenerateError, OSError, ValueError, yaml.YAMLError) as error:
        print(f"Generate error: {error}", file=sys.stderr)
        return 1
