"""Resolve document-internal publication units without semantic inference."""
from __future__ import annotations

import json
from pathlib import Path

from notes import Library, Note, Part, Unit, local_path, note_links, require


def load_layout(path: Path) -> tuple[dict, Library]:
    path = local_path(path)
    layout = json.loads(path.read_text(encoding="utf-8-sig"))
    require(isinstance(layout, dict), "Layout must be an object.")
    require(not set(layout) - {"schema_version", "title", "output", "notes",
                              "courses", "exercises", "questions"}, "Unknown layout key.")
    require(type(layout.get("schema_version")) is int and layout["schema_version"] == 1,
            "Expected layout schema_version 1.")
    for key in ("title", "output"):
        require(isinstance(layout.get(key), str) and bool(layout[key].strip()), f"Missing {key}.")
    paths = layout.get("notes")
    require(isinstance(paths, list) and all(isinstance(p, str) and p for p in paths),
            "notes must be an array of paths.")
    library = Library([path.parent / name for name in paths])
    output = local_path(path.parent / layout["output"])
    require(output.suffix.lower() == ".html", "Output must be an .html file.")
    require(output not in {note.path for note in library.notes} and output != path,
            "Output cannot replace an input.")
    require(output.parent.is_dir(), f"Output parent does not exist: {output.parent}")
    layout["output"] = str(output)
    return layout, library


def refs(value, label: str) -> list[str]:
    require(isinstance(value, list) and all(isinstance(ref, str) and ref for ref in value),
            f"{label} must be an array of references.")
    require(len(set(value)) == len(value), f"Duplicate {label} reference.")
    return value


def compile_layout(layout: dict, library: Library, render) -> dict:
    for note in library.notes:
        for part in note.parts:
            if part.kind == "warning" and part.label == "Clew review":
                render.warn(f"Review required in {note.id}: {part.text.splitlines()[0]}")

    def resolve(ref: str, origin: Note | None = None) -> tuple[Note, str]:
        return library.resolve(ref, origin)

    def key(note: Note, fragment: str) -> tuple[str, str]:
        return note.id, fragment

    def address(note: Note, unit: Unit) -> str:
        return note.id + "#^" + unit.id

    def selected_span(note: Note, fragment: str, kind: str) -> tuple[int, int]:
        matches = [unit for unit in note.units
                   if unit.kind == kind and fragment == "^" + unit.id]
        if matches:
            return matches[0].start, matches[0].end
        return note.selection_span(fragment)

    overrides = layout.get("questions", {})
    require(isinstance(overrides, dict), "questions must map references to options.")
    canonical = {}
    for ref, options in overrides.items():
        note, fragment = resolve(ref)
        require(fragment.startswith("^") and fragment[1:] in note.blocks
                and note.blocks[fragment[1:]].kind == "question",
                f"Override requires an anchored question: {ref}")
        require(key(note, fragment) not in canonical, f"Duplicate question override: {ref}")
        require(isinstance(options, dict) and not set(options) -
                {"corrections", "method", "hints", "explanations", "courses"},
                f"Invalid question options: {ref}")
        canonical[key(note, fragment)] = options

    course_refs = refs(layout.get("courses", [
        note.id for note in library.notes if note.role == "course"
    ]), "courses")
    exercise_refs = refs(layout.get("exercises", [
        note.id for note in library.notes if note.role in {"exercise", "mixed"}
        and any(unit.kind == "exercise" for unit in note.units)
    ]), "exercises")
    require(bool(course_refs or exercise_refs), "Select courses or exercise units in the layout.")
    selections = {}
    groups = {}
    whole_documents = set()
    for ref in exercise_refs:
        note, fragment = resolve(ref)
        require(note.role in {"exercise", "mixed"}, f"Exercise selection targets a non-exercise: {ref}")
        start, end = selected_span(note, fragment, "exercise")
        previous = selections.setdefault(note.id, [])
        require(all(end <= a or b <= start for a, b in previous),
                f"Duplicate/overlapping exercise selection: {ref}")
        previous.append((start, end))
        candidates = []
        for unit in note.units:
            if unit.kind == "exercise" and unit.start < end and start < unit.end:
                parts = note.span_parts(max(start, unit.start), min(end, unit.end))
                if parts:
                    candidates.append((unit, parts))
        require(bool(candidates), f"Selection is outside exercise units: {ref}")
        if not fragment:
            whole_documents.add(note.id)
        for unit, parts in candidates:
            entry = groups.setdefault(address(note, unit), (note, unit, []))
            entry[2].extend(parts)
    document_anchors = {note.id: render.target(note, "") for note in library.notes
                        if note.id in whole_documents}

    questions = {(note.id, "^" + part.block): (note, part, note.owner(part, "exercise"))
                 for note in library.notes for part in note.parts if part.kind == "question"}
    answer_targets = {}
    matched_answers = {}
    correction_owners = {}
    for note in library.notes:
        for unit in note.units:
            if unit.kind != "correction":
                continue
            unit_parts = note.span_parts(unit.start, unit.end)
            links = note_links("\n\n".join(part.display() for part in unit_parts
                                         if part.kind != "reponse"), label="Exercise")
            require(len(links) <= 1, f"Correction unit has multiple exercise links: {address(note, unit)}")
            owners = set()
            if links:
                target, fragment = resolve(links[0], note)
                require(target.role in {"exercise", "mixed"}, "Correction needs an exercise document.")
                owners.add(address(target, target.unit(fragment, "exercise")))
            for part in unit_parts:
                if part.kind != "reponse":
                    continue
                links = note_links(part.text, label="Question")
                require(len(links) <= 1, f"Answer has multiple question links: {note.id}#^{part.block}")
                answer_key = key(note, "^" + part.block)
                answer_targets[answer_key] = None
                if not links:
                    render.warn(f"Unmatched supplied answer: {note.id}#^{part.block}")
                    continue
                target, fragment = resolve(links[0], note)
                target_key = key(target, fragment)
                require(target_key in questions, f"Answer needs an anchored exercise question: {links[0]}")
                owners.add(address(target, questions[target_key][2]))
                answer_targets[answer_key] = target_key
                matched_answers.setdefault(target_key, []).append(f"{note.id}#^{part.block}")
            require(len(owners) <= 1,
                    f"Answers disagree with correction exercise owner: {address(note, unit)}")
            correction_owners[address(note, unit)] = next(iter(owners), None)

    excerpts = {}

    def course(ref: str, origin: Note | None = None) -> str:
        note, fragment = resolve(ref, origin)
        require(note.role in {"course", "mixed"}, f"Course selection needs a course document: {ref}")
        excerpt_key = key(note, fragment)
        if excerpt_key not in excerpts:
            title = fragment.lstrip("^") or note.title
            if fragment.startswith("^") and fragment[1:] in note.blocks:
                title = note.blocks[fragment[1:]].label or title
            excerpts[excerpt_key] = {"id": f"course-{len(excerpts) + 1}",
                                     "title": title,
                                     "html": render(note.select(fragment), note, fragment)}
        return excerpts[excerpt_key]["id"]

    def content(ref: str, origin: Note) -> str:
        note, fragment = resolve(ref, origin)
        return render(note.select(fragment), note, fragment)

    def correction_panels(references: list[str], origin: Note, owner: Unit,
                          question_key: tuple[str, str]) -> tuple[list[str], set[tuple[str, str]]]:
        panels = {}
        selected_answers = set()
        for ref in references:
            note, fragment = resolve(ref, origin)
            start, end = selected_span(note, fragment, "correction")
            parts = note.span_parts(start, end)
            answers = [part for part in parts if part.kind == "reponse"]
            require(bool(answers), f"Empty correction selection or no supplied answers: {ref}")
            units = {note.owner(part, "correction").id for part in answers}
            require(len(units) == 1, f"Select one correction unit or answer, not a whole multi-unit document: {ref}")
            unit = note.unit("^" + next(iter(units)), "correction")
            unit_address = address(note, unit)
            declared_owner = correction_owners[unit_address]
            require(declared_owner is None or declared_owner == address(origin, owner),
                    f"Correction selection belongs to another exercise: {ref}")
            correction_owners[unit_address] = address(origin, owner)
            block_selection = fragment.startswith("^") and fragment[1:] in note.blocks \
                and note.blocks[fragment[1:]].kind == "reponse"
            kept = []
            for part in answers:
                answer_key = key(note, "^" + part.block)
                target = answer_targets[answer_key]
                if target is not None and target != question_key:
                    require(not block_selection, f"Correction/question mismatch: {ref}")
                    continue
                answer_targets[answer_key] = question_key
                kept.append(part)
                selected_answers.add(answer_key)
            require(bool(kept), f"Correction/question mismatch: {ref}")
            panel = panels.setdefault(unit_address, (note, unit, []))
            panel[2].extend(kept)
        result = []
        for note, unit, selected in panels.values():
            context = [part for part in note.span_parts(unit.start, unit.end)
                       if part.kind != "reponse"]
            parts = {(part.start, part.end): part for part in context + selected}
            markup = render.target(note, "^" + unit.id)
            markup += "\n".join(render(part.display(), note, "^" + part.block if part.block else "")
                                for part in sorted(parts.values(), key=lambda part: part.start))
            result.append(markup)
        return result, selected_answers

    question_data, exercise_data = [], []
    consumed = set()
    for note, unit, selected in groups.values():
        selected_questions = {part.block for part in selected if part.kind == "question"}
        parts = [part for part in note.span_parts(unit.start, unit.end)
                 if part.kind != "question" or part.block in selected_questions]
        question_ids = []
        segments = []
        for part in parts:
            if part.kind != "question":
                markup = render(part.display(), note, "^" + part.block if part.block else "")
                if markup:
                    segments.append({"html": markup})
                continue
            question_key = key(note, "^" + part.block)
            options = canonical.get(question_key, {})
            if question_key in canonical:
                consumed.add(question_key)
            answer_refs = refs(options.get("corrections", matched_answers.get(question_key, [])),
                               "corrections")
            corrections, selected_answers = correction_panels(answer_refs, note, unit, question_key)
            auto = {"method": [], "hints": [], "explanations": []}
            for aid in library.notes:
                if aid.metadata["type"] != "help":
                    continue
                aid_note, aid_fragment = resolve(aid.metadata.get("question"), aid)
                require(key(aid_note, aid_fragment) in questions,
                        f"Aid requires an anchored question: {aid.id}")
                if key(aid_note, aid_fragment) != question_key:
                    continue
                answer_key = None
                if "correction" in aid.metadata:
                    answer_note, answer_fragment = resolve(aid.metadata["correction"], aid)
                    answer_key = key(answer_note, answer_fragment)
                    require(answer_key in answer_targets and
                            answer_targets[answer_key] == question_key,
                            f"Aid correction/question mismatch: {aid.id}")
                for aid_part in aid.parts:
                    if aid_part.kind not in {"method", "hint", "explanation"}:
                        continue
                    require(bool(aid_part.block) and bool(aid_part.text),
                            f"Aid needs content and a block anchor: {aid.id}")
                    category = {"method": "method", "hint": "hints",
                                "explanation": "explanations"}[aid_part.kind]
                    if category == "explanations":
                        require(answer_key is not None, f"Explanation needs a supplied correction: {aid.id}")
                        if answer_key not in selected_answers:
                            continue
                    auto[category].append(f"{aid.id}#^{aid_part.block}")
            require("method" in options or len(auto["method"]) <= 1,
                    f"Multiple methods require an explicit selection: {note.id}#^{part.block}")
            method = options.get("method", auto["method"][0] if auto["method"] else None)
            require(method is None or isinstance(method, str) and bool(method), "Invalid method selector.")
            hints = refs(options.get("hints", auto["hints"]), "hints")
            explanations = refs(options.get("explanations", auto["explanations"]), "explanations")
            require(not explanations or bool(corrections),
                    f"Explanations require a selected supplied correction: {note.id}#^{part.block}")
            for ref in ([method] if method else []) + hints + explanations:
                aid, fragment = resolve(ref, note)
                if aid.metadata["type"] == "help":
                    target, target_fragment = resolve(aid.metadata.get("question"), aid)
                    require(key(target, target_fragment) == question_key,
                            f"Aid targets another question: {ref}")
                    if ref in explanations:
                        target, target_fragment = resolve(aid.metadata.get("correction"), aid)
                        require(key(target, target_fragment) in selected_answers,
                                f"Explanation targets an unselected correction: {ref}")
            identifier = f"question-{len(question_data) + 1}"
            question_ids.append(identifier)
            question_data.append({"id": identifier, "label": part.label or "Question",
                                  "html": render(part.text, note, "^" + part.block),
                                  "method": content(method, note) if method else "",
                                  "hints": [content(ref, note) for ref in hints],
                                  "explanations": [content(ref, note) for ref in explanations],
                                  "corrections": corrections,
                                  "courses": [course(ref, note) for ref in
                                              refs(options.get("courses", []), "question courses")],
                                  "address": f"{note.id}#^{part.block}"})
            segments.append({"question": identifier})
        if not question_ids:
            render.warn(f"Exercise has no selected anchored questions: {address(note, unit)}")
        exercise_data.append({"title": unit.title, "address": address(note, unit), "context": "",
                              "questions": question_ids, "segments": segments})
    require(consumed == set(canonical), "Overrides refer to unpublished questions.")

    worksheet = []
    emitted_groups = set()
    for note, unit, _ in groups.values():
        if note.id not in whole_documents:
            worksheet.append({"exercise": address(note, unit)})
            emitted_groups.add(address(note, unit))
            continue
        if address(note, unit) in emitted_groups:
            continue
        worksheet.append({"html": document_anchors[note.id]})
        exercise_units = {candidate.start: candidate for candidate in note.units
                          if candidate.kind == "exercise"}
        events = [(part.start, part) for part in note.parts
                  if not any(candidate.kind != "section"
                             and candidate.start < part.start < candidate.end
                             for candidate in note.units)]
        events.extend(exercise_units.items())
        for _, item in sorted(events, key=lambda event: event[0]):
            if isinstance(item, Unit):
                worksheet.append({"exercise": address(note, item)})
                emitted_groups.add(address(note, item))
            else:
                worksheet.append({"html": render(item.display(), note,
                                                 "^" + item.block if item.block else "")})
    reading = [course(ref) for ref in course_refs]
    course_links = {}
    while len(course_links) < len(render.course_links):
        for anchor, (note, fragment) in list(render.course_links.items()):
            if anchor not in course_links:
                require(bool(fragment), f"Aid course link needs a precise passage: {note.id}")
                course_links[anchor] = course(note.id + "#" + fragment)
    return {"title": layout["title"], "exercises": exercise_data, "worksheet": worksheet,
            "questions": question_data, "courses": list(excerpts.values()),
            "reading": reading, "course_links": course_links}
