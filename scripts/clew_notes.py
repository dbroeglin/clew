"""Read and surgically edit Clew note frontmatter without reformatting it.

Clew notes are authored by hand, so a round trip through a YAML dumper would
reorder keys and restyle quoting. These helpers parse properties for inspection
but rewrite only the lines they must change.
"""

from __future__ import annotations

from pathlib import PurePosixPath
import re

try:
    import yaml
except ImportError as error:  # pragma: no cover - the project pins PyYAML
    raise SystemExit(
        "Clew: PyYAML is required; run this through the project's uv environment."
    ) from error


PROPERTY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:")
ORDER = (
    "schema", "id", "kind", "title", "summary", "aliases", "tags", "cssclasses",
    "domains", "primary_domains", "prerequisite_domains",
    "course", "parent", "children", "previous", "next",
    "teaches", "prerequisites", "similar", "related", "evidence",
    "source_refs", "fidelity",
)
RELATIONS = ("teaches", "prerequisites", "similar", "related", "evidence")


class NoteError(Exception):
    """An actionable problem with a Clew note."""


def split_note(raw: bytes, name: str) -> tuple[list[str], str]:
    """Return the frontmatter lines and the body of one note."""
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---\n"):
        raise NoteError(f"Missing Clew YAML frontmatter: {name}")
    end = re.search(r"(?m)^---[ \t]*$", text[4:])
    if not end:
        raise NoteError(f"Unclosed YAML frontmatter: {name}")
    return text[4:4 + end.start()].split("\n")[:-1], text[4 + end.end():].lstrip("\n")


def join_note(lines: list[str], body: str) -> bytes:
    front = "\n".join(lines)
    return f"---\n{front}\n---\n\n{body.rstrip()}\n".encode("utf-8")


def properties(lines: list[str], name: str) -> dict:
    try:
        data = yaml.safe_load("\n".join(lines))
    except yaml.YAMLError as error:
        raise NoteError(f"Invalid YAML frontmatter in {name}: {error}") from error
    if not isinstance(data, dict):
        raise NoteError(f"Expected flat YAML properties: {name}")
    return data


def set_property(lines: list[str], key: str, rendered: list[str]) -> list[str]:
    """Replace one property in place, or insert it in the conventional order."""
    start = next((index for index, line in enumerate(lines) if line.startswith(f"{key}:")), None)
    if start is not None:
        end = start + 1
        while end < len(lines) and not PROPERTY.match(lines[end]):
            end += 1
        return lines[:start] + rendered + lines[end:]
    rank = ORDER.index(key) if key in ORDER else len(ORDER)
    for index, line in enumerate(lines):
        match = PROPERTY.match(line)
        name = line[:match.end() - 1] if match else None
        if name in ORDER and ORDER.index(name) > rank:
            return lines[:index] + rendered + lines[index:]
    return lines + rendered


def scalar(key: str, link: str | None) -> list[str]:
    return [f'{key}: "{link}"' if link else f"{key}: null"]


def sequence_property(key: str, links: list[str]) -> list[str]:
    if not links:
        return [f"{key}: []"]
    return [f"{key}:"] + [f'  - "{link}"' for link in links]


def target_path(value: str) -> str:
    """Normalize a wikilink or bare reference to a vault-relative file path."""
    inner = value.strip()
    if inner.startswith("[[") and inner.endswith("]]"):
        inner = inner[2:-2]
    inner = inner.replace("\\|", "|").split("|", 1)[0].split("#", 1)[0].strip()
    return inner if PurePosixPath(inner).suffix else f"{inner}.md"


def targets(data: dict, key: str) -> list[str]:
    """Return the note paths one reference property points at."""
    value = data.get(key)
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    return [target_path(item) for item in items if isinstance(item, str) and item.strip()]


def note_link(path: str, alias: str | None = None) -> str:
    target = path[:-3] if path.endswith(".md") else path
    return f"[[{target}|{alias}]]" if alias else f"[[{target}]]"


def page_link(path: str, page: int) -> str:
    return f"[[{path}#page={page}|{PurePosixPath(path).name}, page {page}]]"
