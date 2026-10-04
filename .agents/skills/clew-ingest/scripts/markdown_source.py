"""Lossless line selection with parser-defined protected Markdown boundaries."""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin

from ingest_io import relative_path, require

PAGE = re.compile(r"<!-- page: ([1-9][0-9]*) -->")


def source_lines(text: str) -> list[str]:
    return re.findall(r"[^\r\n]*(?:\r\n|\r|\n|$)", text)[:-1]


@dataclass(frozen=True)
class Link:
    start: int
    end: int
    path: str


def parser() -> MarkdownIt:
    return MarkdownIt("commonmark", {"store_labels": True}).enable("table").use(dollarmath_plugin)


class MarkdownSource:
    def __init__(self, text: str) -> None:
        self.text = text
        self.lines = source_lines(text)
        require(bool(self.lines), "Empty imported Markdown.")
        environment: dict = {}
        self.tokens = parser().parse(text, environment)
        self.definitions = environment.get("references", {})
        self.reference_uses: list[tuple[int, int, str]] = []
        self.markers: dict[int, int] = {}
        protected: set[int] = set()
        for token in self.tokens:
            if token.map is None:
                continue
            start, end = token.map
            if token.type == "html_block" and end == start + 1:
                match = PAGE.fullmatch(self.lines[start].strip())
                if match:
                    self.markers[start] = int(match[1])
            if token.type not in {"ordered_list_open", "bullet_list_open"}:
                protected.update(range(start + 1, end))
            for child in token.children or []:
                if child.meta.get("label"):
                    self.reference_uses.append((start + 1, end, child.meta["label"]))
        for definition in self.definitions.values():
            start, end = definition["map"]
            protected.update(range(start + 1, end))
        self.boundaries = sorted(set(range(len(self.lines) + 1)) - protected)
        self.links = self._links()

    def select(self, start: int, end: int, *, display: bool = False) -> str:
        require(1 <= start <= end <= len(self.lines), "Source range is out of bounds.")
        require(start - 1 in self.boundaries and end in self.boundaries,
                f"Range {start}-{end} bisects a protected Markdown construct.")
        return "".join(line for index, line in enumerate(self.lines[start - 1:end], start - 1)
                       if not display or index not in self.markers)

    def pages(self, start: int, end: int) -> list[int]:
        pages: set[int] = set()
        current = None
        for index in range(end):
            if index in self.markers:
                current = self.markers[index]
            if index >= start - 1 and current is not None:
                pages.add(current)
        return sorted(pages)

    def _links(self) -> list[Link]:
        """Locate local destinations, refusing syntax we cannot rewrite losslessly."""
        destinations: set[str] = set()
        for token in self.tokens:
            for child in token.children or []:
                if child.type in {"image", "link_open"}:
                    url = child.attrGet("src" if child.type == "image" else "href")
                    if url and not urlsplit(url).scheme and not url.startswith(("#", "//")):
                        destinations.add(url)
        links: list[Link] = []
        protected_lines: set[int] = set()
        for token in self.tokens:
            if token.type in {"fence", "code_block", "math_block", "html_block"} and token.map:
                protected_lines.update(range(*token.map))
        offset = 0
        for line_index, line in enumerate(self.lines):
            if line_index not in protected_lines:
                # Inline destinations (with optional titles), and reference definitions.
                patterns = (
                    r"\]\(\s*(?P<url><[^>\n]+>|[^\s()]+)(?:\s+['\"].*?['\"])?\s*\)",
                    r"^\s{0,3}\[[^\]\n]+\]:\s*(?P<url><[^>\n]+>|[^\s]+)",
                )
                code_ranges = [(m.start(), m.end()) for m in re.finditer(r"(`+).*?\1", line)]
                for pattern in patterns:
                    for match in re.finditer(pattern, line):
                        raw = match.group("url")
                        url = raw[1:-1] if raw.startswith("<") else raw
                        # Markdown-it percent-encodes destinations.
                        if not any(unquote(url) == unquote(item) for item in destinations):
                            continue
                        if any(a <= match.start() < b for a, b in code_ranges):
                            continue
                        parsed = urlsplit(url)
                        require(not parsed.query and not parsed.fragment,
                                f"Unsupported local destination suffix: {url}")
                        reference = unquote(parsed.path)
                        relative_path(reference)
                        start, end = match.span("url")
                        if raw.startswith("<"):
                            start, end = start + 1, end - 1
                        links.append(Link(offset + start, offset + end, reference))
            offset += len(line)
        located = {link.path for link in links}
        require(all(unquote(item) in located for item in destinations),
                "A local Markdown link cannot be rewritten safely; resolve its syntax before ingest.")
        return links

    def rewrite(self, start: int, end: int, replacements: dict[str, str]) -> str:
        text = self.select(start, end)
        offset = sum(len(line) for line in self.lines[:start - 1])
        edits: list[tuple[int, int, str]] = []
        for link in self.links:
            if offset <= link.start and link.end <= offset + len(text):
                require(link.path in replacements, f"No asset mapping for {link.path}")
                edits.append((link.start - offset, link.end - offset, replacements[link.path]))
        position = 0
        for index, line in enumerate(self.lines[start - 1:end], start - 1):
            if index in self.markers:
                edits.append((position, position + len(line), ""))
            position += len(line)
        for a, b, replacement in sorted(edits, reverse=True):
            text = text[:a] + replacement + text[b:]
        return text
