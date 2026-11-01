"""Inspect current whole-document notes without producer records or snapshots."""
from __future__ import annotations

import functools
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

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


def normalized_heading_reference(value: str) -> str:
    value = re.sub(r"(?<!\\)\\\\([A-Za-z]+)", r"\\\1", value)
    return re.sub(r"(?<!\\)(\*{1,3}|_{1,3})(.+?)\1", r"\2", value)


@functools.lru_cache(maxsize=256)
def protected_lines(body: str) -> frozenset[int]:
    return frozenset(line for token in parser().parse(body)
                     if token.type in {"fence", "code_block", "math_block"} and token.map
                     for line in range(*token.map))


@functools.lru_cache(maxsize=64)
def heading_tokens(body: str) -> tuple[tuple[int, str, int], ...]:
    """Return (level, content, first line) for each heading, with comments hidden."""
    tokens = parser().parse(hide_comments(body))
    return tuple((int(token.tag[1:]), tokens[index + 1].content, token.map[0])
                 for index, token in enumerate(tokens) if token.type == "heading_open")


# Notes are immutable once read; repeated selections and links re-scan the same text.
@functools.lru_cache(maxsize=1024)
def hide_comments(body: str) -> str:
    protected = protected_lines(body)
    offsets = [0]
    for line in body.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    spans = [(offsets[line], offsets[line + 1]) for line in protected]
    spans.extend(match.span() for match in re.finditer(
        r"(`+)[^\n]*?\1|(?<!\\)\$[^\n$]+\$", body))

    def mask(match: re.Match) -> str:
        if any(start <= match.start() < end for start, end in spans):
            return match[0]
        return re.sub(r"[^\n]", " ", match[0])

    return re.sub(r"%%.*?%%", mask, body, flags=re.S)


@dataclass
class Part:
    kind: str
    text: str
    label: str = ""
    block: str = ""
    start: int = 0
    end: int = 0

    def display(self) -> str:
        return (self.label + "\n\n" if self.label else "") + self.text


@dataclass
class Unit:
    kind: str
    id: str
    start: int
    end: int
    title: str = ""


UNIT_OPEN = re.compile(r"%% clew:unit (section|exercise|correction) ([A-Za-z0-9-]+) %%")
UNIT_CLOSE = re.compile(r"%% /clew:unit ([A-Za-z0-9-]+) %%")
CALLOUT_KINDS = {
    "question", "reponse", "method", "hint", "explanation", "note", "warning", "tip",
    "definition", "theorem", "property", "lemma", "proposition", "corollary",
    "example", "remark", "proof",
}


def split_parts(body: str) -> list[Part]:
    lines = hide_comments(body).splitlines()
    parts: list[Part] = []
    for token in parser().parse("\n".join(lines)):
        if token.level != 0 or not token.map or token.type == "inline":
            continue
        start, end = token.map
        text = "\n".join(lines[start:end]).strip()
        if not text:
            continue
        callout = re.fullmatch(r"> \[!([A-Za-z-]+)\][+-]?(?: (.*))?", lines[start])
        if token.type == "blockquote_open" and callout and callout[1] in CALLOUT_KINDS:
            quoted = lines[start + 1:end]
            require(all(line == ">" or line.startswith("> ") for line in quoted),
                    f"Callout needs explicit quote prefixes at body line {start + 1}.")
            parts.append(Part(callout[1], "\n".join(
                line[2:] if line.startswith("> ") else "" for line in quoted).strip(),
                callout[2] or "", start=start, end=end))
        elif token.type == "paragraph_open":
            anchor = re.search(r"(?:^|\s)\^([A-Za-z0-9-]+)$", text)
            if anchor and not text[:anchor.start()].strip():
                require(bool(parts) and not parts[-1].block, "Block anchor has no unique content.")
                parts[-1].block = anchor[1]
                parts[-1].end = end
            else:
                parts.append(Part("text", text[:anchor.start()].rstrip() if anchor else text,
                                  block=anchor[1] if anchor else "", start=start, end=end))
        else:
            parts.append(Part("text", text, start=start, end=end))
    return parts


@dataclass
class Note:
    path: Path
    text: str
    metadata: dict
    body: str
    parts: list[Part] = field(default_factory=list)
    blocks: dict[str, Part] = field(default_factory=dict)
    units: list[Unit] = field(default_factory=list)
    spans: dict[str, tuple[int, int]] = field(default_factory=dict, repr=False, compare=False)

    @property
    def id(self) -> str:
        return self.metadata["id"]

    @property
    def title(self) -> str:
        return self.metadata.get("title", self.path.stem)

    @property
    def role(self) -> str:
        return self.metadata.get("role", "")

    def owner(self, part: Part, kind: str) -> Unit:
        matches = [unit for unit in self.units if unit.kind == kind
                   and unit.start < part.start and part.end <= unit.end - 1]
        require(len(matches) == 1, f"Expected one {kind} owner: {self.id}#^{part.block}")
        return matches[0]

    def unit(self, fragment: str, kind: str) -> Unit:
        matches = [unit for unit in self.units
                   if unit.kind == kind and fragment == "^" + unit.id]
        require(len(matches) == 1, f"Expected {kind} entry: {self.id}#{fragment}")
        return matches[0]

    def span_parts(self, start: int, end: int) -> list[Part]:
        selected = [part for part in self.parts if part.start < end and start < part.end]
        require(all(start <= part.start and part.end <= end for part in selected),
                f"Selection bisects content: {self.id}, body lines {start + 1}-{end}")
        return selected

    def select_parts(self, fragment: str = "") -> list[Part]:
        return self.span_parts(*self.selection_span(fragment))

    def select(self, fragment: str = "") -> str:
        return "\n\n".join(part.display() for part in self.select_parts(fragment)
                          if part.text.strip())

    def selection_span(self, fragment: str = "") -> tuple[int, int]:
        if fragment not in self.spans:
            self.spans[fragment] = self.uncached_selection_span(fragment)
        return self.spans[fragment]

    def uncached_selection_span(self, fragment: str = "") -> tuple[int, int]:
        if not fragment:
            return 0, len(self.body.splitlines())
        if fragment.startswith("^"):
            require(fragment[1:] in self.blocks, f"Missing block: {self.id}#{fragment}")
            part = self.blocks[fragment[1:]]
            return part.start, part.end
        match = re.fullmatch(r"L([1-9]\d*)-L([1-9]\d*)", fragment)
        if match:
            first, last = map(int, match.groups())
            header = len(self.text.splitlines()) - len(self.body.splitlines())
            start, end = first - 1 - header, last - header
            require(0 <= start < end <= len(self.body.splitlines()),
                    f"Invalid line range or frontmatter selection: {self.id}#{fragment}")
            self.span_parts(start, end)
            return start, end
        headings = heading_tokens(self.body)
        matches = [index for index, (_, content, _) in enumerate(headings) if content == fragment]
        if not matches:
            matches = [index for index, (_, content, _) in enumerate(headings)
                       if normalized_heading_reference(content)
                       == normalized_heading_reference(fragment)]
        require(len(matches) == 1, f"Missing or ambiguous heading: {self.id}#{fragment}")
        index = matches[0]
        level, _, start = headings[index]
        end = len(self.body.splitlines())
        for other_level, _, line in headings[index + 1:]:
            if other_level <= level:
                end = line
                break
        return start, end


def read_note(path: Path) -> Note:
    path = local_path(path)
    require(path.is_file() and path.suffix.lower() == ".md", f"Expected Markdown note: {path}")
    text = path.read_text(encoding="utf-8-sig")
    match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
    require(match is not None, f"Current notes require frontmatter; legacy input unsupported: {path}")
    metadata = yaml.safe_load(match[1])
    require(isinstance(metadata, dict), f"Frontmatter must be an object: {path}")
    require(metadata.get("type") in {"document", "chapter", "help"},
            f"Legacy input unsupported; select current document/help notes: {path}")
    if metadata["type"] in {"document", "chapter"}:
        require(type(metadata.get("clew_schema")) is int and metadata["clew_schema"] == 1,
                f"Expected clew_schema: 1: {path}")
    if metadata["type"] == "document":
        require(metadata.get("role") in {"course", "exercise", "correction", "mixed", "unknown"},
                f"Invalid document role: {path}")
    for key in ("id", "title", "question", "correction"):
        if key == "id" or key in metadata:
            require(isinstance(metadata.get(key), str) and bool(metadata[key].strip()),
                    f"Frontmatter {key} must be a nonempty string: {path}")
    body = text[match.end():]
    note = Note(path, text, metadata, body, split_parts(body))
    for part in note.parts:
        if part.block:
            require(part.block not in note.blocks, f"Duplicate block: {path}#^{part.block}")
            note.blocks[part.block] = part
    stack: list[Unit] = []
    protected = protected_lines(body)
    lines = body.splitlines()
    tokens = parser().parse(hide_comments(body))
    headings = [(token.map[0], tokens[index + 1].content)
                for index, token in enumerate(tokens) if token.type == "heading_open"]
    for index, line in enumerate(lines):
        if index in protected:
            continue
        opening, closing = UNIT_OPEN.fullmatch(line), UNIT_CLOSE.fullmatch(line)
        if line.startswith(("%% clew:unit", "%% /clew:unit")):
            require(bool(opening or closing), f"Malformed unit marker: {path}, line {index + 1}")
        if opening:
            require(not stack or stack[-1].kind == "section", f"Invalid nested unit: {path}")
            require(not any(unit.id == opening[2] for unit in stack + note.units),
                    f"Duplicate unit ID: {note.id}#{opening[2]}")
            stack.append(Unit(opening[1], opening[2], index, len(lines)))
        elif closing:
            require(bool(stack) and stack[-1].id == closing[1],
                    f"Mismatched unit boundary: {path}, line {index + 1}")
            unit = stack.pop()
            unit.end = index + 1
            if unit.kind != "section":
                entry = note.blocks.get(unit.id)
                require(entry is not None and unit.start < entry.start
                        and entry.end <= unit.end - 1,
                        f"Missing {unit.kind} entry anchor: {note.id}#^{unit.id}")
                require(entry.kind not in {"question", "reponse"},
                        f"Unit entry cannot also be a question or answer: {note.id}#^{unit.id}")
                if entry.kind == "text" and entry.text == unit.kind.title():
                    entry.text = ""
            titles = [title for line, title in headings if unit.start < line < unit.end]
            unit.title = titles[0] if titles else unit.kind.title()
            note.units.append(unit)
    require(not stack, f"Unclosed unit: {path}")
    note.units.sort(key=lambda unit: unit.start)
    for part in note.parts:
        if part.kind in {"question", "reponse"}:
            kind = "exercise" if part.kind == "question" else "correction"
            require(note.role in {kind, "mixed"} and bool(part.block) and bool(part.text),
                    f"Expected anchored {kind} callout in a document: {note.id}")
            note.owner(part, kind)
    return note


def note_links(text: str, *, label: str | None = None) -> list[str]:
    md = parser()

    def wikilink(state, silent: bool) -> bool:
        match = re.match(r"\[\[([^\]\n]+)\]\]", state.src[state.pos:])
        if not match:
            return False
        if not silent:
            token = state.push("note_wikilink", "", 0)
            token.content = match[1]
        state.pos += len(match[0])
        return True

    md.inline.ruler.before("link", "note_wikilink", wikilink)
    links = []
    for token in md.parse(text):
        children = token.children or []
        for index, child in enumerate(children):
            if child.type == "note_wikilink" and label is None:
                links.append("[[" + child.content + "]]")
            elif child.type == "link_open":
                following = children[index + 1:index + 3]
                if label is None or (len(following) == 2 and following[0].type == "text"
                                     and following[0].content == label
                                     and following[1].type == "link_close"):
                    links.append(child.attrGet("href") or "")
    return links


def chapter_directory(root: Path) -> bool:
    index = local_path(root / "index.md")
    if not root.is_dir() or not index.is_file():
        return False
    text = index.read_text(encoding="utf-8-sig")
    match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", text, re.S)
    metadata = yaml.safe_load(match[1]) if match else {}
    return isinstance(metadata, dict) and metadata.get("type") == "chapter"


def discover_chapter(root: Path) -> tuple[list[Note], dict]:
    root = local_path(root)
    require(chapter_directory(root), f"Expected current chapter index: {root}")
    found = []
    omitted = []

    def walk(directory: Path) -> None:
        for entry in sorted(directory.iterdir(), key=lambda item: (item.name.casefold(), item.name)):
            if entry.name.startswith(".") or entry.name == "sources":
                continue
            entry = local_path(entry)
            if entry.is_dir():
                walk(entry)
            elif entry.suffix.lower() == ".md":
                if entry != root / "index.md":
                    found.append(read_note(entry))
            elif entry.suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                omitted.append(entry.relative_to(root).as_posix())

    walk(root)
    require(bool(found), f"No current document/help notes in chapter: {root}")
    return found, {"root": str(root), "title": read_note(root / "index.md").title,
                   "notes": len(found), "omitted": omitted,
                   "excluded": ["sources/", "index.md", "hidden entries (including .clew/)"]}


def list_chapters(root: Path, *, depth: int = 8, limit: int = 512) -> dict:
    root = local_path(root)
    require(root.is_dir(), f"Expected vault or material container: {root}")
    chapters, omitted = [], []
    visited = 0

    def walk(directory: Path, level: int) -> None:
        nonlocal visited
        if visited >= limit or level > depth:
            omitted.append(str(directory))
            return
        visited += 1
        if chapter_directory(directory):
            chapters.append({"root": str(directory), "title": read_note(directory / "index.md").title})
            return
        for entry in sorted(directory.iterdir(), key=lambda item: (item.name.casefold(), item.name)):
            if not entry.name.startswith(".") and entry.name != "sources":
                entry = local_path(entry)
                if entry.is_dir():
                    walk(entry, level + 1)

    walk(root, 0)
    return {"root": str(root), "chapters": chapters, "omitted": omitted,
            "excluded": ["sources/", "hidden entries"]}


class Library:
    def __init__(self, paths: list[Path]):
        require(bool(paths), "Select at least one note.")
        self.notes: list[Note] = []
        self.chapters: list[dict] = []
        seen = set()
        roots = set()
        for path in paths:
            path = local_path(path)
            index = not path.is_dir() and path.name.lower() == "index.md"
            if path.is_dir() or (index and read_note(path).metadata["type"] == "chapter"):
                root = path if path.is_dir() else path.parent
                require(chapter_directory(root),
                        f"Not a current chapter: {root}. Use --list-chapters on the vault first.")
                if root in roots:
                    continue
                roots.add(root)
                notes, report = discover_chapter(root)
                self.chapters.append(report)
            else:
                notes = [read_note(path)]
            for note in notes:
                require(note.metadata["type"] != "chapter", "Select a chapter by its index.md.")
                if note.path not in seen:
                    seen.add(note.path)
                    self.notes.append(note)
        require(len({note.id for note in self.notes}) == len(self.notes),
                "Duplicate learning-note IDs.")

    def resolve(self, ref: str, origin: Note | None = None) -> tuple[Note, str]:
        require(isinstance(ref, str) and bool(ref), "Expected nonempty note reference.")
        if ref.startswith("[[") and ref.endswith("]]"):
            ref = ref[2:-2].split("|", 1)[0]
        parsed = urlsplit(ref)
        # Layout selectors can use absolute Windows paths, unlike content URLs.
        absolute = bool(re.match(r"^[A-Za-z]:[\\/]", ref))
        require(absolute or (not parsed.scheme and not parsed.netloc),
                f"Expected local note reference: {ref}")
        if absolute:
            name, _, fragment = ref.partition("#")
        else:
            name, fragment = unquote(parsed.path), unquote(parsed.fragment)
        relative = Path(os.path.abspath(origin.path.parent / name)) if origin and name else None
        local_matches = [note for note in self.notes if note.path == relative]
        if local_matches:
            return local_matches[0], fragment
        matches = [note for note in self.notes if
                   (not name and origin is note)
                   or name in {note.id, note.path.stem, note.path.name, str(note.path),
                               note.path.as_posix()}]
        require(len(matches) == 1, f"Missing or ambiguous selected note: {ref}")
        return matches[0], fragment

    def inventory(self) -> list[dict]:
        return [{"path": str(note.path), "id": note.id, "title": note.title,
                 "type": note.metadata["type"], "role": note.role,
                 "lines": len(note.text.splitlines()),
                 "relationships": {key: note.metadata[key] for key in ("question", "correction")
                                   if key in note.metadata},
                 "units": [{"kind": unit.kind, "id": unit.id, "title": unit.title,
                            "ref": f"{note.id}#^{unit.id}" if unit.kind != "section" else None}
                           for unit in note.units],
                 "blocks": [{"ref": f"{note.id}#^{part.block}", "kind": part.kind,
                             "label": part.label,
                             "owner": note.owner(part, "exercise" if part.kind == "question"
                                                else "correction").id
                             if part.kind in {"question", "reponse"} else None}
                            for part in note.parts if part.block],
                 "headings": [tokens[index + 1].content for tokens in
                              [parser().parse(hide_comments(note.body))]
                              for index, token in enumerate(tokens) if token.type == "heading_open"]}
                for note in self.notes]


def command(operation) -> int:
    import sys
    try:
        print(json.dumps(operation(), ensure_ascii=False, indent=2))
        return 0
    except (GenerateError, OSError, ValueError, yaml.YAMLError) as error:
        print(f"Generate error: {error}", file=sys.stderr)
        return 1
