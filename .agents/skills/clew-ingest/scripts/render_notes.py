"""Deterministic structural wrapping; source prose is never rewritten."""
from __future__ import annotations

import json
import posixpath
from urllib.parse import quote

from bundle_sources import Bundle
from formats import Note, Plan
from markdown_source import source_lines
from plan_checks import note_path


def frontmatter(values: dict) -> str:
    return "---\n" + "".join(f"{key}: {json.dumps(value, ensure_ascii=False)}\n"
                             for key, value in values.items()) + "---\n\n"


def target_link(address: str) -> str:
    return f"[[{address}]]"


def pdf_page_uri(source: str, bundle: Bundle, page: int, directory: str = "") -> str:
    path = posixpath.relpath(f"sources/{source}/{bundle.metadata['source']['name']}", directory)
    return quote(path, safe="/") + f"#page={page}"


def sources_for(note: Note, bundles: dict[str, Bundle]) -> list[dict]:
    return [{"id": part.source,
             "file": f"sources/{part.source}/{bundles[part.source].metadata['source']['name']}",
             "pages": bundles[part.source].markdown.pages(part.start, part.end),
             "lines": [part.start, part.end]}
            for part in note.parts]


def render_note(note: Note, plan: Plan, bundles: dict[str, Bundle]) -> bytes:
    outgoing = [edge for edge in plan.relationships if edge.origin == note.id]
    values = {"schema_version": 1, "id": note.id, "type": note.type,
              "title": note.title, "title_origin": note.title_origin,
              "order": note.order, "status": "draft", "sources": sources_for(note, bundles)}
    for rel, key in (("course", "courses"), ("correction", "exercises")):
        links = [target_link(edge.target) for edge in outgoing if edge.rel == rel]
        if links:
            values[key] = links
    if note.type == "exercise":
        values["corrections"] = [target_link(edge.origin) for edge in plan.relationships
                                if edge.rel == "correction" and edge.target == note.id]
    body = []
    for index, part in enumerate(note.parts):
        bundle = bundles[part.source]
        replacements = {path: quote(posixpath.relpath(
            f"sources/{part.source}/{bundle.retained_path(path)}",
            posixpath.dirname(note_path(note))), safe="/")
                        for path in bundle.files}
        content = bundle.markdown.rewrite(part.start, part.end, replacements)
        if part.role == "text":
            segment = content
        else:
            fields = [f"[src:: {part.source}; pages "
                      f"{','.join(map(str, bundle.markdown.pages(part.start, part.end)))}]"]
            address = f"{note.id}#^{part.id}"
            for edge in plan.relationships:
                if edge.origin == address:
                    fields.append(f"[{edge.rel}:: {target_link(edge.target)}]")
            callout = "question" if part.role == "question" else "reponse"
            header = f"> [!{callout}]"
            if part.label:
                header += " " + part.label
            quoted = "".join("> " + line for line in source_lines(content))
            if quoted and not quoted.endswith(("\n", "\r")):
                quoted += "\n"
            segment = header + "\n> " + " ".join(fields) + "\n" + quoted + f"\n^{part.id}\n"
        if segment and not segment.endswith(("\n", "\r")):
            segment += "\n"
        body.append(f"<!-- clew-part:{index} -->\n" + segment
                    + f"<!-- /clew-part:{index} -->\n")
    children = [edge.origin for edge in plan.relationships
                if edge.rel == "course" and edge.target == note.id]
    if children:
        ranks = {item.id: item.order for item in plan.notes}
        body.append("\n\n" + "\n".join(f"- {target_link(child)}"
                                     for child in sorted(children, key=lambda child: ranks[child])) + "\n")
    if note.parts:
        pages_by_source: dict[str, set[int]] = {}
        for part in note.parts:
            pages_by_source.setdefault(part.source, set()).update(
                bundles[part.source].markdown.pages(part.start, part.end))
        references = []
        for source, pages in pages_by_source.items():
            links = []
            for page in sorted(pages):
                uri = pdf_page_uri(source, bundles[source], page, posixpath.dirname(note_path(note)))
                links.append(f"[page {page}]({uri})")
            if links:
                references.append(f"- {source}: " + ", ".join(links))
        body.append("\n\n## Sources\n\n" + "\n".join(references) + "\n")
    return (frontmatter(values) + "\n\n".join(body)).encode("utf-8")


def render_index(plan: Plan, issues: list[dict], bundles: dict[str, Bundle]) -> bytes:
    content = frontmatter({"schema_version": 1, "id": plan.ingest_id, "type": "ingest",
                           "title": plan.title, "status": "draft"})
    content += "# " + plan.title + "\n\n"
    for label, types in (("Cours", {"course", "section"}),
                         ("Exercices", {"exercise"}), ("Corrections", {"correction"})):
        notes = sorted((note for note in plan.notes if note.type in types),
                       key=lambda note: (note.order, note.id))
        if notes:
            content += "## " + label + "\n\n"
            content += "".join(f"- [[{note.id}|{note.title}]]\n" for note in notes) + "\n"
    content += "## Sources\n\n"
    for source in plan.sources:
        bundle = bundles[source.id]
        page = bundle.metadata["pages"][0]
        pdf = pdf_page_uri(source.id, bundle, page)
        content += f"- `{source.id}`: [PDF, page {page}]({pdf}) / [Markdown](sources/{source.id}/document.md)\n"
    if issues:
        content += "\n## Review\n\n"
        content += "".join(f"- **{issue['code']}**: {issue['message']}\n" for issue in issues)
    return content.encode("utf-8")
