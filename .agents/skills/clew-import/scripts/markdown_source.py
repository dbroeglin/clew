"""Read-only Markdown structure and source locations, never reserialization."""
from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_right
import re
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.common.utils import normalizeReference
from markdown_it.rules_inline.image import image
from markdown_it.rules_inline.link import link
from markdown_it.rules_inline.backticks import backtick
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.dollarmath.index import math_inline_dollar

from document_io import require

PAGE = re.compile(r"<!-- page: ([1-9][0-9]*) -->")
ANCHOR = re.compile(r"\^([A-Za-z0-9-]+)")
CALLOUT = re.compile(r"^ {0,3}>[ \t]*\[!([A-Za-z0-9-]+)\]([+-]?)(?:[ \t]+(.*))?$")
COURSE_LABELS = {
    "definition": r"d(?:e|é)finition",
    "theorem": r"th(?:e|é)or(?:e|è)me|theorem",
    "property": r"propri(?:e|é)t(?:e|é)|property",
    "lemma": r"lemme|lemma",
    "proposition": r"proposition",
    "corollary": r"corollaire|corollary",
    "example": r"exemple|example",
    "remark": r"remarque|remark",
    "proof": r"d(?:e|é)monstration|preuve|proof",
}


def source_lines(text: str) -> list[str]:
    return re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text)[:-1]


def label_kind(label: str) -> str:
    label = re.sub(r"^[0-9]+(?:\.[0-9]+)*[.)]?\s+", "", label)
    if re.match(r"^(?:correction|solution|corrig(?:e|é))\b", label, re.I):
        return "correction"
    if re.match(r"^(?:exercice|exercise|problem|probl(?:e|è)me)\b", label, re.I):
        return "exercise"
    if re.match(r"^(?:question|answer|r(?:e|é)ponse)\b", label, re.I):
        return "question" if re.match(r"^question", label, re.I) else "answer"
    for kind, pattern in COURSE_LABELS.items():
        if re.match(rf"^(?:{pattern})\b", label, re.I):
            return kind
    return "section"


def _capture(rule, token_type: str):
    def capture(state, silent):
        start, count = state.pos, len(state.tokens)
        opening = start + (1 if token_type == "image" else 0)
        label_end = -1
        if ((token_type == "image" and state.src.startswith("![", start))
                or (token_type == "link_open" and state.src.startswith("[", start))):
            label_end = state.md.helpers.parseLinkLabel(state, opening, token_type != "image")
        if not rule(state, silent):
            return False
        if silent:
            return True
        token = next((item for item in state.tokens[count:] if item.type == token_type), None)
        if token is None:
            return True
        token.meta["source_span"] = (start, state.pos)
        if label_end >= 0 and state.src[label_end + 1:label_end + 2] == "(":
            pos = label_end + 2
            while pos < len(state.src) and state.src[pos] in " \t\n":
                pos += 1
            result = state.md.helpers.parseLinkDestination(state.src, pos, len(state.src))
            if result.ok:
                end = result.pos
                if state.src[pos:pos + 1] == "<":
                    pos, end = pos + 1, end - 1
                token.meta["destination_span"] = (pos, end)
        return True
    return capture


def _wikilink(state, silent):
    start = state.pos
    embedded = state.src.startswith("![[", start)
    opening = start + (1 if embedded else 0)
    if not state.src.startswith("[[", opening):
        return False
    end = state.src.find("]]", opening + 2)
    if end < 0 or "\n" in state.src[opening:end]:
        return False
    target, _, label = state.src[opening + 2:end].partition("|")
    if not target.strip():
        return False
    if not silent:
        token = state.push("wikilink", "", 0)
        token.attrs = {"href": target.strip()}
        token.content = label or target
        token.meta = {"source_span": (start, end + 2), "embedded": embedded,
                      "destination_span": (opening + 2, opening + 2 + len(target))}
    state.pos = end + 2
    return True


def _unresolved_reference(state, silent):
    start = state.pos
    opening = start + (1 if state.src.startswith("![", start) else 0)
    if state.src[opening:opening + 1] != "[":
        return False
    label_end = state.md.helpers.parseLinkLabel(state, opening, False)
    if label_end < 0 or state.src[label_end + 1:label_end + 2] != "[":
        return False
    end = state.md.helpers.parseLinkLabel(state, label_end + 1, False)
    if end < 0:
        return False
    label = state.src[label_end + 2:end] or state.src[opening + 1:label_end]
    if not silent:
        token = state.push("unresolved_reference", "", 0)
        token.content = label
        token.meta = {"source_span": (start, end + 1)}
    state.pos = end + 1
    return True


def _clew_comment(state, start_line, end_line, silent):
    if state.sCount[start_line] - state.blkIndent >= 4:
        return False
    start = state.bMarks[start_line] + state.tShift[start_line]
    end = state.eMarks[start_line]
    raw = state.src[start:end]
    if not raw.startswith(("%% clew:", "%% /clew:")):
        return False
    if silent:
        return True
    token = state.push("clew_comment", "", 0)
    token.block = True
    token.content = raw
    token.map = [start_line, start_line + 1]
    state.line = start_line + 1
    return True


def parser() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"store_labels": True, "inline_definitions": True})
    md.enable("table").use(dollarmath_plugin)
    md.block.ruler.before("html_block", "clew_comment", _clew_comment,
                          {"alt": ["paragraph", "reference", "blockquote"]})
    # Inspection must expose unsafe destinations so the validator can reject them.
    md.validateLink = lambda _url: True
    md.inline.ruler.at("link", _capture(link, "link_open"))
    md.inline.ruler.at("image", _capture(image, "image"))
    md.inline.ruler.at("backticks", _capture(backtick, "code_inline"))
    md.inline.ruler.at("math_inline", _capture(math_inline_dollar(), "math_inline"))
    md.inline.ruler.before("link", "wikilink", _wikilink)
    md.inline.ruler.after("image", "unresolved_reference", _unresolved_reference)
    return md


@dataclass(frozen=True)
class Block:
    id: str
    start: int
    end: int
    kind: str
    level: int = 0
    label: str = ""


@dataclass(frozen=True)
class Link:
    target: str
    line: int
    kind: str = "markdown"
    image: bool = False
    start: int | None = None
    end: int | None = None
    destination_start: int | None = None
    destination_end: int | None = None
    reference: str | None = None


class MarkdownSource:
    def __init__(self, text: str) -> None:
        self.text = text
        self.lines = source_lines(text)
        self.offsets = [0]
        for line in self.lines:
            self.offsets.append(self.offsets[-1] + len(line))
        self.environment: dict = {}
        self.tokens = parser().parse(text, self.environment)
        self.definitions = self.environment.get("references", {})
        self.markers: dict[int, int] = {}
        protected: set[int] = set()
        blocks: list[Block] = []
        self.headings: list[dict] = []
        for index, token in enumerate(self.tokens):
            if token.map is None:
                continue
            start, end = token.map
            if token.type == "html_block" and end == start + 1:
                match = PAGE.fullmatch(self.lines[start].strip())
                if match:
                    self.markers[start] = int(match[1])
            if token.type not in {"ordered_list_open", "bullet_list_open"}:
                protected.update(range(start + 1, end))
            if token.type == "heading_open":
                inline = self.tokens[index + 1]
                content = inline.content
                display = "".join(child.content for child in inline.children or []
                                  if child.type not in {"html_inline"})
                self.headings.append({"start": start, "end": end, "level": int(token.tag[1:]),
                                      "label": content, "text": display, "kind": label_kind(display)})
            if token.level == 0 and token.type in {
                "heading_open", "paragraph_open", "blockquote_open", "table_open",
                "ordered_list_open", "bullet_list_open", "fence", "code_block",
                "math_block", "math_block_label", "html_block", "clew_comment", "hr", "definition",
            } or token.type == "list_item_open" and token.level == 1:
                kind = {"heading_open": "heading", "paragraph_open": "paragraph",
                        "blockquote_open": "quote", "table_open": "table",
                        "list_item_open": "item", "ordered_list_open": "list",
                        "bullet_list_open": "list", "definition": "reference"}.get(
                            token.type, token.type)
                label = self.tokens[index + 1].content if kind == "heading" else token.info
                blocks.append(Block("", start, end, kind, token.level, label))
        for definition in self.definitions.values():
            protected.update(range(definition["map"][0] + 1, definition["map"][1]))
        self.boundaries = set(range(len(self.lines) + 1)) - protected
        self.blocks = {f"b-{index}": Block(f"b-{index}", block.start, block.end,
                                          block.kind, block.level, block.label)
                       for index, block in enumerate(blocks, 1)
                       if block.start in self.boundaries and block.end in self.boundaries}
        self.protected_inline: list[tuple[int, int]] = []
        self.links, self.unresolved_references = self._links()

    def select(self, start: str, end: str) -> tuple[int, int]:
        require(start in self.blocks and end in self.blocks,
                f"Unknown or unsafe block selector: {start}/{end}")
        first, last = self.blocks[start], self.blocks[end]
        require(first.start <= last.start and first.end <= last.end,
                f"Reversed block selection: {start}/{end}")
        return first.start, last.end

    def span(self, start: str, end: str) -> tuple[int, int]:
        a, b = self.select(start, end)
        return self.offsets[a], self.offsets[b]

    def pages(self, start: int, end: int) -> list[int]:
        result: set[int] = set()
        current = None
        for index in range(end):
            if index in self.markers:
                current = self.markers[index]
            if index >= start and current is not None:
                result.add(current)
        return sorted(result)

    def inventory(self) -> dict:
        anchors = []
        for index, token in enumerate(self.tokens):
            if token.type == "paragraph_open" and token.map:
                match = re.search(r"(?:^|\s)\^([A-Za-z0-9-]+)$", self.tokens[index + 1].content.rstrip())
                if match:
                    anchors.append({"id": match[1], "line": token.map[0] + 1, "top_level": token.level == 0})
        return {
            "line_count": len(self.lines),
            "blocks": [{"id": block.id, "kind": block.kind, "start": block.start + 1,
                        "end": block.end, "label": block.label,
                        "pages": self.pages(block.start, block.end)}
                       for block in self.blocks.values()],
            "outline": [{**heading, "start": heading["start"] + 1,
                         "safe": heading["start"] in self.boundaries
                         and heading["end"] in self.boundaries}
                        for heading in self.headings],
            "page_markers": [{"line": line + 1, "page": page}
                             for line, page in self.markers.items()],
            "existing_anchors": anchors,
            "local_references": sorted({item.target for item in self.links
                                        if not urlsplit(item.target).scheme}),
        }

    def _inline_positions(self, content: str, start: int, end: int,
                          cursor: int = 0) -> list[int] | None:
        positions = []
        source_line = start
        for fragment in content.split("\n"):
            found = False
            while source_line < end:
                raw = self.lines[source_line].rstrip("\r\n")
                position = raw.find(fragment, cursor)
                if position >= 0:
                    positions.extend(self.offsets[source_line] + position + index
                                     for index in range(len(fragment)))
                    found = True
                    break
                source_line += 1
                cursor = 0
            if not found:
                return None
            positions.append(self.offsets[source_line] + len(raw))
            source_line += 1
            cursor = 0
        return positions[:-1]

    @staticmethod
    def _mapped(span: tuple[int, int] | None, positions: list[int] | None):
        if span is None or positions is None or not 0 <= span[0] < span[1] <= len(positions):
            return None, None
        return positions[span[0]], positions[span[1] - 1] + 1

    def _links(self) -> tuple[list[Link], list[tuple[int, str]]]:
        links, unresolved = [], []
        row_map, row_cursor = None, 0
        md = parser()
        for token in self.tokens:
            if token.type == "tr_open":
                row_map, row_cursor = token.map, 0
            if token.type == "definition" and token.map:
                start, end = token.map
                raw = "".join(self.lines[start:end]).replace("\r\n", "\n").replace("\r", "\n")
                match = re.match(r" {0,3}\[(?:\\.|[^\]\n])+\]:\s*", raw)
                a = b = None
                if match:
                    result = md.helpers.parseLinkDestination(raw, match.end(), len(raw))
                    if result.ok:
                        pos, stop = match.end(), result.pos
                        if raw[pos:pos + 1] == "<":
                            pos, stop = pos + 1, stop - 1
                        positions = self._inline_positions(raw.rstrip("\n"), start, end)
                        a, b = self._mapped((pos, stop), positions)
                links.append(Link(token.meta["url"], start + 1, "definition",
                                  destination_start=a, destination_end=b,
                                  reference=token.meta["id"]))
                continue
            if token.type != "inline":
                continue
            mapping = token.map or row_map
            if mapping is None:
                continue
            start, end = mapping
            positions = self._inline_positions(token.content, start, end,
                                               row_cursor if token.map is None else 0)
            if token.map is None and positions:
                row_cursor = positions[-1] - self.offsets[start] + 1
            for child in token.children or []:
                if child.type in {"code_inline", "math_inline", "image"}:
                    a, b = self._mapped(child.meta.get("source_span"), positions)
                    if a is not None:
                        self.protected_inline.append((a, b))
                if child.type == "unresolved_reference":
                    unresolved.append((start + 1, normalizeReference(child.content)))
                    continue
                if child.type not in {"image", "link_open", "wikilink"}:
                    continue
                a, b = self._mapped(child.meta.get("source_span"), positions)
                da, db = self._mapped(child.meta.get("destination_span"), positions)
                links.append(Link(
                    str(child.attrGet("src" if child.type == "image" else "href")),
                    start + 1 if a is None else bisect_right(self.offsets, a),
                    "wiki" if child.type == "wikilink" else "markdown",
                    child.type == "image" or bool(child.meta.get("embedded")),
                    a, b, da, db, child.meta.get("label")))
        return links, unresolved
