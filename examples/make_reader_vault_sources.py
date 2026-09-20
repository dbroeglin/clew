"""Generate the synthetic source PDFs and source maps for the example vault.

The example vault ships the sources its sections are extracted from, so a reader
can follow a page link and land on the passage a section was written from. Real
courses digest a publisher's PDF; this one renders its own authored prose, which
keeps the example self-contained and legally redistributable.

Output is byte-for-byte reproducible: fonts are the base-14 set, timestamps are
pinned, and the trailer identifier is rewritten to a constant so that rerunning
the script leaves ``sha256`` in ``support/source-map.json`` untouched.

Run it from the repository root::

    uv run examples/make_reader_vault_sources.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pymupdf
import yaml

VAULT = Path(__file__).resolve().parent / "reader-vault"
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
LINK = re.compile(r"\[\[([^\[\]|]+)\|([^\[\]]+)\]\]|\[\[([^\[\]]+)\]\]")
FENCE = re.compile(r"^```[a-z]*$")
NAV_START = "<!-- clew:nav -->"
NAV_END = "<!-- /clew:nav -->"
IDENTIFIER = re.compile(rb"/ID\s*\[\s*<[0-9A-Fa-f]+>\s*<[0-9A-Fa-f]+>\s*\]")
STAMP = "D:20240101000000Z"
TITLE_FONT = "hebo"
BODY_FONT = "helv"
SIZE = 10.5
LEADING = 14.0
PAGE = pymupdf.paper_rect("a4")
BODY = pymupdf.Rect(72, 96, PAGE.x1 - 72, PAGE.y1 - 72)


def load(path: Path) -> tuple[dict, str]:
    """Return the frontmatter mapping and body of a note."""
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER.match(text)
    if match is None:
        raise SystemExit(f"{path}: missing frontmatter")
    return yaml.safe_load(match.group(1)) or {}, text[match.end():]


def target(link: str) -> Path:
    """Resolve a quoted wikilink from frontmatter to the note it names."""
    path = VAULT / link.strip().removeprefix("[[").removesuffix("]]")
    return path if path.suffix else path.with_suffix(".md")


def prose(body: str) -> list[str]:
    """Flatten a section body into the blocks a source page would carry.

    Each block is a paragraph, a subheading or a single line of mathematics.
    Wikilinks keep their visible text, markup is dropped, and the level-one
    heading is discarded because the rendered page already carries the title.
    The navigation block is skipped entirely: ``clew_finalize.py`` generates it
    from the frontmatter, so rendering it would put page references onto the
    very pages they number.
    """
    blocks: list[str] = []
    paragraph: list[str] = []
    skipping = verbatim = False

    def flush() -> None:
        if paragraph:
            blocks.append(" ".join(paragraph))
            paragraph.clear()

    for line in body.splitlines():
        stripped = line.strip()
        if stripped == NAV_START:
            skipping = True
        elif stripped == NAV_END:
            skipping = False
        elif skipping:
            continue
        elif FENCE.match(stripped):
            flush()
            verbatim = not verbatim
        elif not stripped:
            flush()
        elif stripped == "$$":
            flush()
        elif stripped.startswith("# "):
            flush()
        else:
            text = clean(stripped)
            if verbatim or stripped.startswith("#"):
                flush()
                blocks.append(text)
            else:
                paragraph.append(text)
    flush()
    return blocks


def clean(line: str) -> str:
    """Reduce one Markdown line to the text a printed page would show."""
    line = re.sub(r"^#+\s*", "", line)
    line = re.sub(r"^>\s*", "", line)
    line = LINK.sub(lambda match: match.group(2) or match.group(3), line)
    return line.replace("**", "").replace("$", "")


def wrap(blocks: list[str]) -> list[str]:
    """Break blocks into rendered lines that fit the body column.

    Wrapping is measured rather than estimated so that pagination is decided
    here, not by the renderer, and a section's page span is known before the
    page is drawn.
    """
    lines: list[str] = []
    for block in blocks:
        if lines:
            lines.append("")
        current = ""
        for word in block.split():
            candidate = f"{current} {word}".strip()
            if current and pymupdf.get_text_length(candidate, BODY_FONT, SIZE) > BODY.width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


def paginate(blocks: list[str]) -> list[list[str]]:
    """Split one section's prose into the lines drawn on each of its pages."""
    lines = wrap(blocks)
    capacity = int(BODY.height // LEADING)
    return [lines[at:at + capacity] for at in range(0, len(lines), capacity)] or [[]]


def render(sources: list[tuple[str, list[list[str]]]]) -> bytes:
    """Render titled prose pages to reproducible PDF bytes."""
    doc = pymupdf.open()
    for title, pages in sources:
        for number, lines in enumerate(pages, start=1):
            page = doc.new_page(width=PAGE.x1, height=PAGE.y1)
            heading = title if number == 1 else f"{title} (continued)"
            page.insert_text((BODY.x0, 72), heading, fontname=TITLE_FONT, fontsize=13)
            for index, line in enumerate(lines):
                if line:
                    point = (BODY.x0, BODY.y0 + LEADING * (index + 1))
                    page.insert_text(point, line, fontname=BODY_FONT, fontsize=SIZE)
    doc.set_metadata({
        "title": "Clew example course notes", "author": "Clew",
        "creationDate": STAMP, "modDate": STAMP,
    })
    raw = doc.tobytes(deflate=True)
    doc.close()
    return IDENTIFIER.sub(b"/ID[<" + b"0" * 32 + b"><" + b"0" * 32 + b">]", raw)


def sections(course: Path) -> list[Path]:
    """Return the course's sections in authored order."""
    entry, _ = load(course / "course.md")
    found: list[Path] = []
    for chapter in entry["children"]:
        meta, _ = load(target(chapter))
        found.extend(target(child) for child in meta["children"])
    return found


def build(course: Path) -> None:
    """Write one course's source PDF and the source map that indexes it."""
    layout, records = [], []
    for path in sections(course):
        meta, body = load(path)
        pages = paginate(prose(body))
        first = sum(len(each) for _, each in layout) + 1
        layout.append((meta["title"], pages))
        records.append((path, meta["id"], first, first + len(pages) - 1))
    data = render(layout)
    name = f"{course.name}-notes"
    source = course / "sources" / f"{name}.pdf"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(data)
    relative = source.relative_to(VAULT).as_posix()
    course_id = load(course / "course.md")[0]["id"]
    total = sum(len(pages) for _, pages in layout)
    write(course / "support" / "source-map.json", {
        "schema": "clew-source-map/v1",
        "course_id": course_id,
        "sources": [{
            "id": name,
            "filename": source.name,
            "path": relative,
            "sha256": hashlib.sha256(data).hexdigest(),
            "page_count": total,
            "citation": f"Clew example notes for {course.name}",
            "edition": None,
            "omission_reason": None,
        }],
        "sections": [
            {
                "id": identity,
                "path": path.relative_to(VAULT).as_posix(),
                "spans": [{"source_id": name, "page_start": start, "page_end": end}],
            }
            for path, identity, start, end in records
        ],
    })
    seed(course, course_id,
         {identity: check(name, start, end) for _, identity, start, end in records})
    print(f"{relative}: {total} page(s) for {len(records)} section(s)")


def seed(course: Path, course_id: str, checks: dict[str, str]) -> None:
    """Record each section's verification check without discarding finalize's work.

    Only the check text belongs to this script; the hashes and page coverage in
    the same file are ``clew_finalize.py``'s, so rerunning the generator must
    leave them alone or the two would overwrite each other indefinitely.
    """
    path = course / "support" / "verification.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    report.setdefault("schema", "clew-verification/v1")
    report["course_id"] = course_id
    kept = [record for record in report.get("sections", []) if record["id"] in checks]
    known = {record["id"] for record in kept}
    kept.extend({"id": identity} for identity in checks if identity not in known)
    for record in kept:
        record["checks"] = [checks[record["id"]]]
        record["limitations"] = []
    report["sections"] = kept
    report.setdefault("pages", [])
    write(path, report)


def check(source: str, start: int, end: int) -> str:
    """Describe the comparison that justifies this example's verified fidelity.

    The example inverts the usual direction: its pages are rendered from the
    notes rather than the notes being extracted from a publisher's pages, so
    the two agree by construction and the claim is exact rather than assessed.
    """
    span = f"page {start}" if start == end else f"pages {start}-{end}"
    return (f"{span.capitalize()} of {source} was rendered from this section's own prose by "
            "examples/make_reader_vault_sources.py, so every sentence, figure and formula on "
            "the page is the section's text with Markdown and KaTeX markup removed.")


def write(path: Path, payload: dict) -> None:
    """Write JSON with the trailing newline the repository's files carry."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    for course in sorted((VAULT / "courses").iterdir()):
        if course.is_dir():
            build(course)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
