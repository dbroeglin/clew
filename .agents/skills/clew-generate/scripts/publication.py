"""Resolve the minimal publication layout without semantic inference."""
from __future__ import annotations

import json
import re
from pathlib import Path

from notes import Library, Note, local_path, require


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
    layout["output"] = str(local_path(path.parent / layout["output"]))
    output = Path(layout["output"])
    require(output.suffix.lower() == ".html", "Output must be an .html file.")
    require(output not in {note.path for note in library.notes} and output != path,
            "Output cannot replace an input.")
    require(output.parent.is_dir(), f"Output parent does not exist: {output.parent}")
    return layout, library


def refs(value, label: str) -> list[str]:
    require(isinstance(value, list) and all(isinstance(ref, str) and ref for ref in value),
            f"{label} must be an array of references.")
    require(len(set(value)) == len(value), f"Duplicate {label} reference.")
    return value


def compile_layout(layout: dict, library: Library, render) -> dict:
    require(len({note.id for note in library.notes}) == len(library.notes),
            "Duplicate learning-note IDs.")
    overrides = layout.get("questions", {})
    require(isinstance(overrides, dict), "questions must map references to options.")
    courses = refs(layout.get("courses", [
        note.id for note in library.notes if note.metadata.get("type") in {"course", "section"}
    ]), "courses")
    exercises = refs(layout.get("exercises", [
        note.id for note in library.notes if note.metadata.get("type") == "exercise"
    ]), "exercises")
    require(bool(courses or exercises), "Select courses or exercises in the layout.")
    canonical_overrides = {}
    for ref, options in overrides.items():
        note, fragment = library.resolve(ref)
        key = (str(note.path), fragment)
        require(key not in canonical_overrides, f"Duplicate question override: {ref}")
        require(isinstance(options, dict) and not set(options) -
                {"corrections", "method", "hints", "explanations", "courses"}, f"Invalid question options: {ref}")
        canonical_overrides[key] = options
    consumed = set()
    question_data = []
    exercise_data = []
    excerpts: dict[str, dict] = {}
    units = {}
    for ref in exercises:
        note, fragment = library.resolve(ref)
        require(note.metadata.get("type") in {None, "exercise"},
                f"Exercise selection targets a non-exercise: {ref}")
        start, end = note.selection_span(fragment)
        selections = units.setdefault(note.id, (note, []))[1]
        require(all(end <= previous_start or previous_end <= start
                    for previous_start, previous_end, _, _ in selections),
                f"Duplicate/overlapping exercise selection: {ref}")
        selections.append((start, end, fragment, note.select_parts(fragment)))

    answer_targets = {}
    matched_answers = {}
    correction_owners = {}
    for note in library.notes if units else []:
        answers = [part for part in note.parts if part.kind == "reponse"]
        if note.metadata.get("type") != "correction" and not answers:
            continue
        require(note.metadata.get("type") in {None, "correction"},
                f"Supplied answers need a correction note: {note.id}")
        owners = set()
        for ref in refs(note.metadata.get("exercises", []), "correction exercises"):
            target, fragment = library.resolve(ref, note)
            require(target.metadata.get("type") in {None, "exercise"} and not fragment,
                    f"Correction association needs a whole exercise note: {note.id} -> {ref}")
            owners.add(target.id)
        require(len(owners) <= 1, f"Correction unit has multiple exercises: {note.id}")
        for part in answers:
            links = re.findall(r"\[question::\s*(\[\[.*?\]\])\]", part.fields)
            require(len(links) <= 1, f"Answer has multiple question links: {note.id}#^{part.block}")
            if not links:
                render.warn(f"Unmatched supplied answer: {note.id}#^{part.block or '(no anchor)'}")
                continue
            require(bool(part.block), f"Supplied answer needs a block anchor: {note.id}")
            target, fragment = library.resolve(links[0], note)
            require(target.metadata.get("type") in {None, "exercise"}
                    and fragment.startswith("^") and fragment[1:] in target.blocks
                    and target.blocks[fragment[1:]].kind in {"question", "text"},
                    f"Answer needs an anchored exercise question: {note.id}#^{part.block}")
            require(not owners or target.id in owners,
                    f"Answer targets a different exercise than its correction unit: "
                    f"{note.id}#^{part.block} -> {target.id}")
            owners.add(target.id)
            key = (str(target.path), fragment)
            answer_targets[str(note.path), "^" + part.block] = key
            matched_answers.setdefault(key, []).append(f"{note.id}#^{part.block}")
        correction_owners[str(note.path)] = next(iter(owners), None)

    def course(ref: str, origin: Note | None = None) -> str:
        note, fragment = library.resolve(ref, origin)
        key = str(note.path) + "#" + fragment
        if key not in excerpts:
            identifier = f"course-{len(excerpts) + 1}"
            excerpts[key] = {"id": identifier, "title": fragment or note.title,
                             "html": render(note.select(fragment), note, fragment)}
        return excerpts[key]["id"]

    def content(ref: str, origin: Note) -> str:
        note, fragment = library.resolve(ref, origin)
        return render(note.select(fragment), note, fragment)

    def correction_panels(references: list[str], origin: Note, question_key: tuple) -> list[str]:
        selected = {}
        for ref in references:
            note, fragment = library.resolve(ref, origin)
            parts = note.select_parts(fragment)
            require(any(part.text.strip() for part in parts), f"Empty correction selection: {ref}")
            path = str(note.path)
            if path in correction_owners:
                owner = correction_owners[path]
                require(owner is None or owner == origin.id,
                        f"Correction selection belongs to another exercise: {ref}")
                correction_owners[path] = origin.id
                targets = {answer_targets[path, "^" + part.block] for part in parts
                           if (path, "^" + part.block) in answer_targets}
                require(not targets or question_key in targets,
                        f"Correction/question mismatch: {ref}")
            entry = selected.setdefault(path, {"note": note, "parts": [], "context": False})
            entry["parts"].extend(parts)
            if fragment.startswith("^") and any(part.kind == "reponse" for part in parts):
                entry["context"] = True
        panels = []
        for entry in selected.values():
            note, parts = entry["note"], entry["parts"]
            if entry["context"]:
                context = [part for part in note.parts if part.kind != "reponse"]
                parts = [part for part in parts if not any(
                    other.start <= part.start and part.end <= other.end for other in context)]
                parts.extend(context)
            unique = {(part.start, part.end, part.block): part for part in parts}
            panels.append("\n".join(
                render(part.display(), note, "^" + part.block if part.block else "")
                for part in sorted(unique.values(), key=lambda part: part.start) if part.text.strip()))
        return panels

    for note, selections in units.values():
        selections.sort(key=lambda selection: selection[0])
        parts = None
        selected_parts = [part for _, _, _, selection in selections for part in selection]
        if any(part.kind == "question" for part in note.parts):
            question_parts = [part for part in selected_parts if part.kind == "question"]
            require(bool(question_parts), f"Exercise selection contains no questions: {note.id}")
            require(all(part.block and part.text.strip() for part in question_parts),
                    f"Question callouts need block anchors and content: {note.id}")
            questions = [("^" + part.block, part.text, part.label) for part in question_parts]
            parts = selected_parts
        else:
            # Explicit unnumbered selections remain questions, not duplicated context.
            questions = [(fragment, note.select(fragment), "") for _, _, fragment, _ in selections]
        question_ids = []
        unit_anchor = render.target(note, "")
        for question_fragment, text, label in questions:
            require(bool(text.strip()), f"Empty question selection: {note.id}#{question_fragment}")
            key = (str(note.path), question_fragment)
            options = canonical_overrides.get(key, {})
            if key in canonical_overrides:
                consumed.add(key)
            address = note.id + ("#" + question_fragment if question_fragment else "")
            auto_answers = matched_answers.get(key, [])
            answer_refs = refs(options.get("corrections", auto_answers), "corrections")
            method = options.get("method")
            require(method is None or (isinstance(method, str) and bool(method)),
                    f"Invalid method: {address}")
            hint_refs = refs(options.get("hints", []), "hints")
            explanation_refs = refs(options.get("explanations", []), "explanations")
            course_refs = refs(options.get("courses", note.metadata.get("courses", [])), "question courses")
            # Separate aid notes are additions, never supplied corrections.
            aid_notes = []
            for aid in library.notes:
                target = aid.metadata.get("question")
                if aid.metadata.get("type") == "help" and isinstance(target, str):
                    target_note, target_fragment = library.resolve(target, aid)
                    if (str(target_note.path), target_fragment) == key:
                        aid_notes.append(aid)
            auto_methods = []
            auto_hints = []
            auto_explanations = []
            selected_answers = set()
            for ref in answer_refs:
                target, fragment = library.resolve(ref, note)
                selected_answers.add((str(target.path), fragment))
                selected_answers.update((str(target.path), "^" + part.block)
                                        for part in target.select_parts(fragment)
                                        if part.kind == "reponse" and part.block)
            supplied_answers = {(str(target.path), fragment) for target, fragment in
                                (library.resolve(ref, note) for ref in auto_answers)}
            for aid in aid_notes:
                for part in aid.parts:
                    if part.kind in {"method", "hint", "explanation"}:
                        require(bool(part.block), f"Aid needs a block anchor: {aid.id}")
                        ref = f"{aid.id}#^{part.block}"
                        if part.kind == "explanation":
                            correction = aid.metadata.get("correction")
                            require(isinstance(correction, str),
                                    f"Explanation needs a supplied correction: {ref}")
                            target, fragment = library.resolve(correction, aid)
                            answer_key = (str(target.path), fragment)
                            require(answer_key in supplied_answers,
                                    f"Explanation correction/question mismatch: {ref}")
                            if answer_key in selected_answers:
                                auto_explanations.append(ref)
                        else:
                            (auto_methods if part.kind == "method" else auto_hints).append(ref)
            require("method" in options or len(auto_methods) <= 1,
                    f"Multiple methods require an explicit selection: {address}")
            method = method if "method" in options else (auto_methods[0] if auto_methods else None)
            hint_refs = hint_refs if "hints" in options else auto_hints
            explanation_refs = explanation_refs if "explanations" in options else auto_explanations
            require(not explanation_refs or bool(answer_refs),
                    f"Explanations require a selected supplied correction: {address}")
            for ref in explanation_refs:
                aid, fragment = library.resolve(ref, note)
                if aid.metadata.get("type") == "help" and any(
                        part.kind == "explanation" for part in aid.select_parts(fragment)):
                    aid_question, aid_fragment = library.resolve(aid.metadata.get("question"), aid)
                    require((str(aid_question.path), aid_fragment) == key,
                            f"Explanation targets another question: {ref}")
                    target, target_fragment = library.resolve(aid.metadata.get("correction"), aid)
                    require((str(target.path), target_fragment) in selected_answers,
                            f"Explanation targets an unselected correction: {ref}")
            identifier = f"question-{len(question_data) + 1}"
            question_ids.append(identifier)
            question_data.append({
                "id": identifier, "label": label or "Question",
                "html": unit_anchor + render(text, note, question_fragment),
                "method": content(method, note) if method else "",
                "hints": [content(ref, note) for ref in hint_refs],
                "explanations": [content(ref, note) for ref in explanation_refs],
                "corrections": correction_panels(answer_refs, note, key),
                "courses": [course(ref, note) for ref in course_refs],
                "address": address,
            })
            unit_anchor = ""
        segments = []
        if parts is not None:
            identifiers = iter(question_ids)
            for part in parts:
                if part.kind == "question":
                    segments.append({"question": next(identifiers)})
                elif part.text.strip():
                    segments.append({"html": render(part.display(), note,
                                                    "^" + part.block if part.block else "")})
        else:
            segments = [{"question": identifier} for identifier in question_ids]
        exercise_data.append({"title": note.title, "address": note.id, "context": "",
                              "questions": question_ids, "segments": segments})
    require(consumed == set(canonical_overrides),
            f"Overrides refer to unpublished questions: {sorted(set(canonical_overrides) - consumed)}")
    reading = [course(ref) for ref in courses]
    course_links = {}
    while len(course_links) < len(render.course_links):
        for anchor, (target, fragment) in list(render.course_links.items()):
            if anchor not in course_links:
                course_links[anchor] = course(target.id + ("#" + fragment if fragment else ""))
    return {"title": layout["title"], "exercises": exercise_data,
            "questions": question_data, "courses": list(excerpts.values()),
            "reading": reading, "course_links": course_links}
