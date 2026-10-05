"""Mechanical plan validation: coverage, identity, ordering, and typed links."""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

from bundle_sources import Bundle, load_bundle
from formats import OUTPUT_VERSION, Note, Plan
from ingest_io import fingerprint, no_redirect, read_json, relative_path, require
from vault_placement import missing_parents, placement_parent

FOLDERS = {"course": "courses", "section": "courses",
           "exercise": "exercices", "correction": "corriges"}


def note_path(note: Note) -> str:
    return f"{FOLDERS[note.type]}/{note.id}.md"


def read_plan(path: Path) -> Plan:
    return Plan.model_validate(read_json(path))


def plan_hash(plan: Plan) -> str:
    return fingerprint({"output_version": OUTPUT_VERSION, "plan": plan.model_dump()})


def inspect_plan(plan: Plan) -> dict[str, Bundle]:
    bundles = {}
    for source in plan.sources:
        require(Path(source.bundle).is_absolute(), "Bundle paths must be absolute.")
        require(source.id not in bundles, f"Duplicate source ID: {source.id}")
        bundle = load_bundle(Path(source.bundle))
        require(bundle.fingerprint == source.fingerprint, f"Source changed: {source.id}")
        bundles[source.id] = bundle
    require(len({str(bundle.root).casefold() for bundle in bundles.values()}) == len(bundles),
            "The same bundle was selected twice.")
    return bundles


def check_destination(plan: Plan, bundles: dict[str, Bundle]) -> Path:
    path = Path(plan.destination)
    require(path.is_absolute(), "Destination must be absolute.")
    path = no_redirect(path)
    require(not os.path.lexists(path), f"Destination already exists: {path}")
    relative_path(path.name)
    require(not path.name.startswith("."), "Chapter destination must not be a hidden/configuration directory.")
    require(path.parent == placement_parent(plan),
            "Destination must be a chapter directly under the confirmed vault parent, not the vault root.")
    missing_parents(plan)
    require(all(not path.is_relative_to(bundle.root) for bundle in bundles.values()),
            "Destination must not be inside an input bundle.")
    return path


def check_plan(plan: Plan, bundles: dict[str, Bundle]) -> list[dict]:
    require(set(bundles) == {source.id for source in plan.sources},
            "Sources do not match the plan.")
    notes = {note.id: note for note in plan.notes}
    require(len(notes) == len(plan.notes), "Duplicate note IDs.")
    coverage: dict[str, list[tuple[int, int]]] = defaultdict(list)
    blocks = {}
    issues = [issue.model_dump(exclude_none=True) for issue in plan.issues]
    for source in plan.sources:
        require(bundles[source.id].fingerprint == source.fingerprint,
                f"Source fingerprint differs: {source.id}")
        relative_path(f"sources/{source.id}/document.md")
        for item in bundles[source.id].metadata["issues"]:
            issues.append({"code": "import-review", "message": source.id + ": "
                           + json.dumps(item, ensure_ascii=False, sort_keys=True)})
        if bundles[source.id].metadata["status"] == "needs_review":
            issues.append({"code": "import-status", "message": f"{source.id}: needs_review"})
        external = []
        for token in bundles[source.id].markdown.tokens:
            for child in token.children or []:
                if child.type in {"image", "link_open"}:
                    url = child.attrGet("src" if child.type == "image" else "href") or ""
                    if url.startswith(("http:", "https:", "//", "#")):
                        external.append(url)
        if external:
            issues.append({"code": "external-reference",
                           "message": f"{source.id}: preserved external/fragment links: {sorted(set(external))}"})
    for note in plan.notes:
        require(note.id.startswith(plan.ingest_id + "-"), f"Note ID needs ingest namespace: {note.id}")
        relative_path(note_path(note))
        require("\n" not in note.title and "\r" not in note.title, "Titles must be single-line.")
        previous: dict[str, int] = {}
        for index, part in enumerate(note.parts):
            require(part.source in bundles, f"Unknown source: {part.source}")
            document = bundles[part.source].markdown
            document.select(part.start, part.end)
            require(not any(marker in document.select(part.start, part.end)
                            for marker in ("<!-- clew-part:", "<!-- /clew-part:")),
                    "Source contains a reserved structural marker; review before ingestion.")
            require(part.start > previous.get(part.source, 0), f"Reordered content in {note.id}")
            previous[part.source] = part.end
            coverage[part.source].append((part.start, part.end))
            require(part.role == "text" or
                    (part.role == "question" and note.type == "exercise") or
                    (part.role == "answer" and note.type == "correction"),
                    f"Invalid {part.role} block in {note.type} note.")
            if part.id:
                require(bool(document.select(part.start, part.end, display=True).strip()),
                        "Question/answer blocks must contain source content.")
                prefix = "q-" if part.role == "question" else "r-"
                require(part.id.startswith(prefix), f"Block ID must start with {prefix}")
                address = f"{note.id}#^{part.id}"
                require(address not in blocks, f"Duplicate block: {address}")
                require(part.label is None or ("\n" not in part.label and "\r" not in part.label),
                        "Block labels must be single-line.")
                blocks[address] = (note, part, index)
        require(note.parts or note.type == "course", f"Empty source note: {note.id}")
    for source, bundle in bundles.items():
        next_line = 1
        for start, end in sorted(coverage[source]):
            require(start == next_line, f"Dropped/duplicated source lines in {source} at {next_line}")
            next_line = end + 1
        require(next_line == len(bundle.markdown.lines) + 1, f"Incomplete coverage: {source}")
    reference_contexts: dict[tuple[str, str], str] = {}
    for source, bundle in bundles.items():
        def context(start, end):
            for note in plan.notes:
                for index, part in enumerate(note.parts):
                    if part.source == source and part.start <= start <= end <= part.end:
                        return (note.id, index if part.role != "text" else -1)
            return None

        for start, end, label in bundle.markdown.reference_uses:
            definition = bundle.markdown.definitions[label]
            a, b = definition["map"]
            require(context(start, end) == context(a + 1, b)
                    and context(start, end) is not None,
                    f"Reference [{label}] crosses note/callout scope in {source}; keep its definition with its usage.")
        for label, definition in bundle.markdown.definitions.items():
            start, end = definition["map"]
            owner = context(start + 1, end)
            require(owner is not None, "Reference definition was split across parts.")
            key = (owner[0], label)
            # Definitions from different source namespaces cannot shadow each other.
            require(key not in reference_contexts or reference_contexts[key] == source,
                    f"Reference label [{label}] collides between sources in {owner[0]}.")
            reference_contexts[key] = source
    course_parent: dict[str, str] = {}
    correction_parent: dict[str, str] = {}
    answers: dict[str, str] = {}
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in plan.relationships:
        key = (edge.rel, edge.origin, edge.target)
        require(key not in seen_edges, f"Duplicate relationship: {key}")
        seen_edges.add(key)
        for evidence in edge.evidence:
            require(evidence.source in bundles, "Unknown evidence source.")
            require(bool(bundles[evidence.source].markdown.select(
                evidence.start, evidence.end, display=True).strip()), "Empty relationship evidence.")
        if edge.rel in {"course", "correction"}:
            require(edge.origin in notes and edge.target in notes, "Unknown relationship note.")
            origin, target = notes[edge.origin], notes[edge.target]
            if edge.rel == "course":
                require(origin.type in {"section", "exercise"} and target.type == "course",
                        "Course relationship has wrong note types.")
                if origin.type == "section":
                    require(origin.id not in course_parent, "Section has multiple parent courses.")
                    course_parent[origin.id] = target.id
            else:
                require(origin.type == "correction" and target.type == "exercise",
                        "Correction relationship has wrong note types.")
                require(origin.id not in correction_parent, "Correction has multiple exercises.")
                correction_parent[origin.id] = target.id
        else:
            require(edge.origin in blocks and edge.target in blocks, "Unknown relationship block.")
            origin_note, origin_part, origin_index = blocks[edge.origin]
            target_note, target_part, target_index = blocks[edge.target]
            if edge.rel == "question":
                require(origin_part.role == "answer" and target_part.role == "question",
                        "Answer must point to a question.")
                require(edge.origin not in answers, "Answer has multiple question targets.")
                answers[edge.origin] = edge.target
            else:
                require(origin_part.role == target_part.role == "question"
                        and origin_note.id == target_note.id and target_index < origin_index,
                        "Question needs must target an earlier question in the same exercise.")
    for answer, question in answers.items():
        require(correction_parent.get(blocks[answer][0].id) == blocks[question][0].id,
                "Answer target does not match correction's exercise.")
    # Earlier-question-only links already imply an acyclic dependency graph.
    orders: set[tuple[str, str, int]] = set()
    for note in plan.notes:
        if note.type == "section":
            require(note.id in course_parent, f"Section has no parent course: {note.id}")
        scope = course_parent.get(note.id, "")
        order_key = (note.type, scope, note.order)
        require(order_key not in orders, f"Duplicate order in {note.type}/{scope}: {note.order}")
        orders.add(order_key)
    section_ranges: dict[tuple[str, str], int] = {}
    for note in sorted(plan.notes, key=lambda note: note.order):
        if note.type == "section":
            for part in note.parts:
                key = (course_parent[note.id], part.source)
                require(part.start > section_ranges.get(key, 0), "Sections reverse source reading order.")
                section_ranges[key] = part.end
    targeted = set(answers.values())
    for address, (note, part, _) in blocks.items():
        if part.role == "question" and address not in targeted:
            issues.append({"code": "missing-answer", "note": note.id, "message": address})
        if part.role == "answer" and address not in answers:
            issues.append({"code": "unmatched-answer", "note": note.id, "message": address})
    for note in plan.notes:
        if note.type == "correction" and note.id not in correction_parent:
            issues.append({"code": "unmatched-correction", "note": note.id, "message": note.id})
    for issue in issues:
        if issue.get("note"):
            require(issue["note"] in notes, "Review issue refers to an unknown note.")
    review_structure(plan, bundles)
    return issues


def review_structure(plan: Plan, bundles: dict[str, Bundle]) -> dict:
    exceptions = {}
    for issue in plan.issues:
        if issue.code.startswith("structure-"):
            key = (issue.note, issue.code)
            require(key not in exceptions, f"Duplicate structure exception: {key}")
            require(issue.note is not None and bool(issue.message.strip()),
                    "Structure exceptions need a note and source-specific reasoning.")
            exceptions[key] = issue
    used = set()
    reviews = []
    units = []
    note_units: dict[str, list[dict]] = defaultdict(list)

    def owner(source: str, line: int) -> Note:
        return next(note for note in plan.notes for part in note.parts
                    if part.source == source and part.start <= line <= part.end)

    def explain(note: Note, code: str, message: str, evidence: dict) -> None:
        key = (note.id, code)
        require(key in exceptions,
                f"{message} Add a source-specific issue with note '{note.id}' and code '{code}'.")
        used.add(key)
        reviews.append({"note": note.id, "code": code,
                        "message": exceptions[key].message, **evidence})

    for note in plan.notes:
        role = {"exercise": "question", "correction": "answer"}.get(note.type)
        if role:
            require(any(part.role == role for part in note.parts),
                    f"{note.type.capitalize()} note needs anchored {role} parts: {note.id}")
    for source, bundle in bundles.items():
        rows = bundle.markdown.outline
        candidates = []
        for row in rows:
            if row["kind"] not in {"exercise", "correction"}:
                continue
            note = owner(source, row["start"])
            code = f"structure-candidate:{source}:{row['start']}"
            if (note.id, code) in exceptions:
                explain(note, code, "", {"source": source, "candidate": row})
            else:
                candidates.append(row)
        for index, row in enumerate(candidates):
            start = row["start"]
            end = candidates[index + 1]["start"] - 1 if index + 1 < len(candidates) else len(bundle.markdown.lines)
            note = owner(source, start)
            require(note.type in {"exercise", "correction"}
                    and (row["kind"] != "correction" or note.type == "correction"),
                    f"Exercise/correction candidate {source}:{start} is in {note.type} note "
                    f"{note.id}; structure the unit, or use 'structure-candidate:{source}:{start}' for this note "
                    "only if source review establishes a misleading candidate.")
            role = "question" if note.type == "exercise" else "answer"
            # Shared introductions may belong to the following unit; only structural
            # children and the heading establish ownership of this candidate.
            owners = {note.id} | {other.id for other in plan.notes if other.type == note.type
                                  for part in other.parts if part.source == source and part.role == role
                                  and part.start <= end and start <= part.end}
            require(len(owners) == 1,
                    f"Exercise/correction unit {source}:{start}-{end} is split between notes: "
                    f"{sorted(owners)}")
            unit = {"source": source, "start": start, "end": end, "label": row["label"],
                    "note": note.id, "type": note.type,
                    "safe_start": start - 1 in bundle.markdown.boundaries,
                    "safe_end": end in bundle.markdown.boundaries}
            units.append(unit)
            note_units[note.id].append(unit)
            require(len(note_units[note.id]) == 1,
                    f"Note {note.id} aggregates independent exercise/correction units: "
                    f"{[(item['source'], item['start']) for item in note_units[note.id]]}. "
                    + ("A candidate boundary is parser-unsafe; stop for a source-specific decision."
                       if any(not item["safe_start"] or not item["safe_end"]
                              for item in note_units[note.id]) else "Use one note per unit."))
        course_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        item_groups: dict[int, list[dict]] = defaultdict(list)
        for row in rows:
            note = owner(source, row["start"])
            if row["kind"] == "heading" and note.type in {"course", "section"}:
                family = (".".join(map(str, row["number"][:-1])) or "root") if row["number"] else (
                    f"heading-{row['parent'] or 'root'}-{row['level']}")
                course_groups[note.id, family].append(row)
            if row["kind"] == "item" and row["level"] == 1:
                item_groups[row["parent"]].append(row)
        for (note_id, family), peers in course_groups.items():
            if len(peers) > 1:
                note = next(note for note in plan.notes if note.id == note_id)
                explain(note, f"structure-course-group:{source}:{family}",
                        f"Course note {note.id} groups peer topics in {source}.",
                        {"source": source, "candidates": peers})
        for parent, items in item_groups.items():
            owners = {owner(source, row["start"]).id for row in items
                      if owner(source, row["start"]).type in {"exercise", "correction"}}
            covered = any(unit["source"] == source and unit["start"] <= parent <= unit["end"]
                          for unit in units)
            if len(owners) > 1 and not covered:
                explain(owner(source, parent), f"structure-candidate:{source}:{parent}",
                        f"Unheaded source list {source}:{parent} crosses exercise/correction notes.",
                        {"source": source, "candidates": items, "owners": sorted(owners)})
        for note in plan.notes:
            if note.type not in {"exercise", "correction"}:
                continue
            for part in note.parts:
                if part.source != source:
                    continue
                internal = [row for row in rows if part.start <= row["start"] <= row["end"] <= part.end
                            and (row["kind"] == "question"
                                 or (row["kind"] == "heading" and row["number"])
                                 or (row["kind"] == "item" and row["level"] == 1
                                     and len(item_groups[row["parent"]]) > 1))]
                groups = defaultdict(list)
                for row in internal:
                    key = (row["kind"], row["parent"] if row["kind"] == "item"
                           else tuple(row["number"][:-1]) if row["kind"] == "heading" else ())
                    groups[key].append(row)
                if internal and (part.role == "text" or any(len(group) > 1 for group in groups.values())):
                    explain(note, f"structure-block-group:{source}:{part.start}",
                            f"Internal question/answer candidates need review in {note.id} "
                            f"at {source}:{part.start}-{part.end}.",
                            {"source": source, "start": part.start, "end": part.end,
                             "role": part.role, "candidates": internal})
    require(used == set(exceptions),
            f"Unknown, unscoped, or unused structure exceptions: {sorted(set(exceptions) - used)}")
    return {
        "requires_agent_review": True, "units": units, "exceptions": reviews,
        "notes": [{"id": note.id, "type": note.type,
                   "parts": [part.model_dump(exclude_none=True) for part in note.parts],
                   "question_count": sum(part.role == "question" for part in note.parts),
                   "answer_count": sum(part.role == "answer" for part in note.parts),
                   "questions": [f"{note.id}#^{part.id}" for part in note.parts if part.role == "question"],
                   "answers": [f"{note.id}#^{part.id}" for part in note.parts if part.role == "answer"]}
                  for note in plan.notes],
        "relationships": [edge.model_dump() for edge in plan.relationships],
    }


def output_paths(plan: Plan, bundles: dict[str, Bundle]) -> list[str]:
    paths = ["index.md", "ingest.json", *[note_path(note) for note in plan.notes]]
    for source, bundle in bundles.items():
        paths.extend(f"sources/{source}/{bundle.retained_path(path)}" for path in bundle.files)
    require(len({path.casefold() for path in paths}) == len(paths), "Output filename collision.")
    for path in paths:
        relative_path(path)
    return sorted(paths)
