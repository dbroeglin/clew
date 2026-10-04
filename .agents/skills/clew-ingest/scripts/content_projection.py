"""Independently unwrap persisted source segments and reverse local-link edits."""
from __future__ import annotations

import posixpath
from urllib.parse import quote

from bundle_sources import Bundle
from formats import Note
from ingest_io import require
from markdown_source import source_lines
from plan_checks import note_path


def verify_projection(text: str, note: Note, bundles: dict[str, Bundle]) -> None:
    cursor = 0
    for index, part in enumerate(note.parts):
        opening = f"<!-- clew-part:{index} -->\n"
        closing = f"<!-- /clew-part:{index} -->\n"
        require(text.count(opening) == text.count(closing) == 1,
                f"Missing/duplicated source segment marker: {note.id}/{index}")
        start = text.find(opening, cursor) + len(opening)
        end = text.find(closing, start)
        require(start >= cursor + len(opening) and end >= start, "Reordered segment markers.")
        actual = text[start:end]
        cursor = end + len(closing)
        document = bundles[part.source].markdown
        expected = document.select(part.start, part.end, display=True)
        if part.role != "text":
            _, separator, remainder = actual.partition("\n")
            require(bool(separator), "Missing callout header.")
            _, separator, remainder = remainder.partition("\n")
            require(bool(separator), "Missing callout fields.")
            footer = f"\n^{part.id}\n"
            require(remainder.endswith(footer), "Missing block anchor.")
            quoted = remainder[:-len(footer)]
            lines = source_lines(quoted)
            require(all(line.startswith("> ") for line in lines), "Invalid source callout quoting.")
            actual = "".join(line[2:] for line in lines)
        if expected and not expected.endswith(("\n", "\r")):
            require(actual.endswith("\n"), "Missing structural final separator.")
            actual = actual[:-1]
        offset = sum(len(line) for line in document.lines[:part.start - 1])
        raw_length = len(document.select(part.start, part.end))
        for link in document.links:
            if offset <= link.start and link.end <= offset + raw_length:
                removed = 0
                position = offset
                for line_index in range(part.start - 1, part.end):
                    line = document.lines[line_index]
                    if line_index in document.markers and position < link.start:
                        removed += len(line)
                    position += len(line)
                position = link.start - offset - removed
                replacement = quote(posixpath.relpath(
                    f"sources/{part.source}/{bundles[part.source].retained_path(link.path)}",
                    posixpath.dirname(note_path(note))), safe="/")
                require(actual[position:position + len(replacement)] == replacement,
                        "Source projection fidelity differs at a rewritten destination.")
                original = document.text[link.start:link.end]
                actual = actual[:position] + original + actual[position + len(replacement):]
        require(actual == expected, f"Source projection fidelity differs: {note.id}/{index}")
