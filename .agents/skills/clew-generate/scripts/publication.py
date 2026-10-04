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
                {"corrections", "method", "hints", "courses"}, f"Invalid question options: {ref}")
        canonical_overrides[key] = options
    consumed = set()
    question_data = []
    exercise_data = []
    excerpts: dict[str, dict] = {}
    published = set()

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

    for exercise_ref in exercises:
        note, fragment = library.resolve(exercise_ref)
        exercise_key = (str(note.path), fragment)
        require(exercise_key not in published, f"Duplicate exercise selection: {exercise_ref}")
        published.add(exercise_key)
        parts = None
        if fragment:
            questions = [(fragment, note.select(fragment), "")]
            context = ""
        else:
            question_parts = [part for part in note.parts if part.kind == "question"]
            if question_parts:
                require(all(part.block for part in question_parts),
                        f"Question callouts need block anchors: {note.id}")
                questions = [("^" + part.block, part.text, part.label) for part in question_parts]
                context = ""
                parts = note.parts
            else:
                # An unnumbered exercise is one question, never duplicated as context.
                questions = [("", note.select(), "")]
                context = ""
        question_ids = []
        for question_fragment, text, label in questions:
            key = (str(note.path), question_fragment)
            options = canonical_overrides.get(key, {})
            if key in canonical_overrides:
                consumed.add(key)
            address = note.id + ("#" + question_fragment if question_fragment else "")
            auto_answers = []
            for answer_note in library.notes:
                for part in answer_note.parts:
                    if part.kind != "reponse" or not part.block:
                        continue
                    for target in re.findall(r"\[question::\s*(\[\[.*?\]\])\]", part.fields):
                        target_note, target_fragment = library.resolve(target, answer_note)
                        if (str(target_note.path), target_fragment) == key:
                            auto_answers.append(f"{answer_note.id}#^{part.block}")
            answer_refs = refs(options.get("corrections", auto_answers), "corrections")
            method = options.get("method")
            require(method is None or (isinstance(method, str) and bool(method)),
                    f"Invalid method: {address}")
            hint_refs = refs(options.get("hints", []), "hints")
            course_refs = refs(options.get("courses", note.metadata.get("courses", [])), "question courses")
            # Separate aid notes can be authored by humans or a future Enrich.
            aid_notes = []
            for aid in library.notes:
                target = aid.metadata.get("question")
                if aid.metadata.get("type") == "help" and isinstance(target, str):
                    target_note, target_fragment = library.resolve(target, aid)
                    if (str(target_note.path), target_fragment) == key:
                        aid_notes.append(aid)
            auto_methods = []
            auto_hints = []
            for aid in aid_notes:
                for part in aid.parts:
                    if part.kind in {"method", "hint"}:
                        require(bool(part.block), f"Aid needs a block anchor: {aid.id}")
                        (auto_methods if part.kind == "method" else auto_hints).append(
                            f"{aid.id}#^{part.block}")
            require("method" in options or len(auto_methods) <= 1,
                    f"Multiple methods require an explicit selection: {address}")
            method = method if "method" in options else (auto_methods[0] if auto_methods else None)
            hint_refs = hint_refs if "hints" in options else auto_hints
            identifier = f"question-{len(question_data) + 1}"
            question_ids.append(identifier)
            question_data.append({
                "id": identifier, "label": label or "Question",
                "html": render(text, note, question_fragment),
                "method": content(method, note) if method else "",
                "hints": [content(ref, note) for ref in hint_refs],
                "corrections": [content(ref, note) for ref in answer_refs],
                "courses": [course(ref, note) for ref in course_refs],
                "address": address,
            })
        segments = []
        if parts is not None:
            identifiers = iter(question_ids)
            for part in parts:
                if part.kind == "question":
                    segments.append({"question": next(identifiers)})
                elif part.text.strip():
                    segments.append({"html": render(part.display(), note)})
        else:
            segments = [{"question": identifier} for identifier in question_ids]
        exercise_data.append({"title": note.title, "context": render(context, note),
                              "questions": question_ids, "segments": segments})
    require(consumed == set(canonical_overrides),
            f"Overrides refer to unpublished questions: {sorted(set(canonical_overrides) - consumed)}")
    reading = [course(ref) for ref in courses]
    return {"title": layout["title"], "exercises": exercise_data,
            "questions": question_data, "courses": list(excerpts.values()),
            "reading": reading}
