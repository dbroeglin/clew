"""Build small but genuinely valid clew/v1 content roots for the test suite."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


VALIDATOR = (
    Path(__file__).resolve().parents[1]
    / ".agents/skills/course-content/scripts/validate_clew.py"
)


def validator_available() -> bool:
    import importlib.util

    return VALIDATOR.is_file() and importlib.util.find_spec("jsonschema") is not None


def validate(root: Path, course: str, strict: bool = False) -> dict:
    """Run the Clew validator over one course and return its report."""
    import subprocess
    import sys

    command = [sys.executable, str(VALIDATOR), "--vault", str(root), "--course", course]
    if strict:
        command.append("--strict")
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if not result.stdout.strip():
        raise AssertionError(f"Validator produced no report: {result.stderr.strip()}")
    return json.loads(result.stdout)


def pdf(path: Path, pages: list[str]) -> Path:
    """Write a small multi-page PDF so page counts and hashes are genuine."""
    import pymupdf

    path.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    try:
        for text in pages:
            page = document.new_page()
            page.insert_text((72, 96), text, fontsize=12)
        document.save(path, deflate=True)
    finally:
        document.close()
    return path


def note(kind: str, identity: str, title: str, summary: str, body: str, **extra: str) -> str:
    lines = [
        "schema: clew/v1",
        f"id: {identity}",
        f"kind: {kind}",
        f'title: "{title}"',
        f'summary: "{summary}"',
    ]
    lines.extend(extra.values())
    front = "\n".join(lines)
    return f"---\n{front}\n---\n\n# {title}\n\n{body.strip()}\n"


def minimal_course(root: Path, course: str = "mechanics", course_id: str = "mechanics") -> Path:
    """One course, two chapters, three sections, two PDFs (one of them omitted)."""
    prefix = root / "courses" / course
    motion = pdf(prefix / "sources" / "motion.pdf", ["Speed and distance", "Worked example"])
    forces = ["courses/mechanics/sections/balanced-forces.md"]

    write(prefix / "course.md", note(
        "course", course_id, "Mechanics", "Motion and forces from first principles.",
        "An introductory mechanics course.",
        children=(
            "children:\n"
            '  - "[[courses/mechanics/chapters/motion]]"\n'
            '  - "[[courses/mechanics/chapters/forces]]"'
        ),
        source_refs="source_refs: []",
    ))
    for key, title, children in (
        ("motion", "Motion", ["average-speed", "acceleration"]),
        ("forces", "Forces", ["balanced-forces"]),
    ):
        write(prefix / "chapters" / f"{key}.md", note(
            "chapter", f"{course_id}.{key}", title, f"{title} in one dimension.",
            f"The {title.lower()} chapter.",
            course='course: "[[courses/mechanics/course]]"',
            parent='parent: "[[courses/mechanics/course]]"',
            children="children:\n" + "\n".join(
                f'  - "[[courses/mechanics/sections/{child}]]"' for child in children),
            source_refs="source_refs: []",
        ))
    for key, title, summary in (
        ("average-speed", "Average speed", "Distance over elapsed time."),
        ("acceleration", "Acceleration", "How quickly velocity changes."),
        ("balanced-forces", "Balanced forces", "Why steady motion needs no net force."),
    ):
        parent = "forces" if key == "balanced-forces" else "motion"
        write(prefix / "sections" / f"{key}.md", note(
            "section", f"{course_id}.{key}", title, summary, f"{summary} Explained plainly.",
            course='course: "[[courses/mechanics/course]]"',
            parent=f'parent: "[[courses/mechanics/chapters/{parent}]]"',
            previous="previous: null",
            next="next: null",
            source_refs="source_refs: []",
            fidelity="fidelity: partial",
        ))
    write(prefix / "support" / "source-map.json", json.dumps({
        "schema": "clew-source-map/v1",
        "course_id": course_id,
        "sources": [
            {
                "id": "motion-notes", "filename": "motion.pdf",
                "path": f"courses/{course}/sources/motion.pdf",
                "sha256": hashlib.sha256(motion.read_bytes()).hexdigest(),
                "page_count": 2, "citation": "Motion notes", "edition": None,
                "omission_reason": None,
            },
            {
                "id": "forces-handout", "filename": "forces.pdf", "path": None,
                "sha256": "0" * 64, "page_count": 1, "citation": "Forces handout",
                "edition": None, "omission_reason": "Redistribution is not permitted.",
            },
        ],
        "sections": [
            {"id": f"{course_id}.average-speed",
             "path": f"courses/{course}/sections/average-speed.md",
             "spans": [{"source_id": "motion-notes", "page_start": 1, "page_end": 1}]},
            {"id": f"{course_id}.acceleration",
             "path": f"courses/{course}/sections/acceleration.md",
             "spans": [{"source_id": "motion-notes", "page_start": 2, "page_end": 2}]},
            {"id": f"{course_id}.balanced-forces",
             "path": forces[0],
             "spans": [{"source_id": "forces-handout", "page_start": 1, "page_end": 1}]},
        ],
    }, indent=2) + "\n")
    write(prefix / "support" / "verification.json", json.dumps({
        "schema": "clew-verification/v1", "course_id": course_id,
        "sections": [], "pages": [],
    }, indent=2) + "\n")
    return root


def concept(root: Path, key: str, title: str, summary: str, definition: str,
            evidence: list[str], **relations: list[str]) -> Path:
    """Write a shared concept whose frontmatter refs are all visible in its body."""
    lines = [f"{name}:\n" + "\n".join(f'  - "[[{item[:-3]}]]"' for item in links)
             for name, links in relations.items() if links]
    body = [f"## Definition\n\n{definition}"]
    for name, links in relations.items():
        if links:
            body.append(f"## {name.title()}\n\n" + "\n".join(
                f"- [[{item[:-3]}]]" for item in links))
    body.append("## Evidence\n\n" + "\n".join(f"- [[{item[:-3]}]]" for item in evidence))
    return write(root / "concepts" / f"{key}.md", note(
        "concept", f"concept.{key}", title, summary, "\n\n".join(body),
        **{f"relation{index}": line for index, line in enumerate(lines)},
        evidence="evidence:\n" + "\n".join(f'  - "[[{item[:-3]}]]"' for item in evidence),
    ))


def course_tree(root: Path, course: str, title: str, summary: str,
                chapters: list[tuple], pages: list[str]) -> None:
    """Write one publishable course whose sections map onto a generated PDF."""
    prefix = root / "courses" / course
    source = pdf(prefix / "sources" / f"{course}.pdf", pages)
    write(prefix / "course.md", note(
        "course", f"course.{course}", title, summary,
        f"{summary} Work through the chapters in order.",
        children="children:\n" + "\n".join(
            f'  - "[[courses/{course}/chapters/{key}]]"' for key, _, _ in chapters),
        source_refs="source_refs: []",
    ))
    records, page = [], 0
    for key, chapter_title, sections in chapters:
        write(prefix / "chapters" / f"{key}.md", note(
            "chapter", f"course.{course}.{key}", chapter_title,
            f"{chapter_title} in brief.", f"The {chapter_title.lower()} chapter.",
            course=f'course: "[[courses/{course}/course]]"',
            parent=f'parent: "[[courses/{course}/course]]"',
            children="children:\n" + "\n".join(
                f'  - "[[courses/{course}/sections/{item[0]}]]"' for item in sections),
            source_refs="source_refs: []",
        ))
        for section_key, section_title, section_summary, links in sections:
            page += 1
            extras, visible = {}, []
            for relation, concepts in links.items():
                extras[relation] = f"{relation}:\n" + "\n".join(
                    f'  - "[[{item[:-3]}]]"' for item in concepts)
                visible.append(f"{relation.title()}: " + " · ".join(
                    f"[[{item[:-3]}]]" for item in concepts))
            write(prefix / "sections" / f"{section_key}.md", note(
                "section", f"course.{course}.{section_key}", section_title, section_summary,
                f"{section_summary}\n\n" + "\n".join(visible),
                course=f'course: "[[courses/{course}/course]]"',
                parent=f'parent: "[[courses/{course}/chapters/{key}]]"',
                previous="previous: null", next="next: null", **extras,
                source_refs="source_refs: []", fidelity="fidelity: partial",
            ))
            records.append({
                "id": f"course.{course}.{section_key}",
                "path": f"courses/{course}/sections/{section_key}.md",
                "spans": [{"source_id": f"{course}-notes", "page_start": page,
                           "page_end": page}],
            })
    write(prefix / "support" / "source-map.json", json.dumps({
        "schema": "clew-source-map/v1", "course_id": f"course.{course}",
        "sources": [{
            "id": f"{course}-notes", "filename": f"{course}.pdf",
            "path": f"courses/{course}/sources/{course}.pdf",
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "page_count": len(pages), "citation": f"{title} course notes",
            "edition": None, "omission_reason": None,
        }],
        "sections": records,
    }, indent=2) + "\n")
    write(prefix / "support" / "verification.json", json.dumps({
        "schema": "clew-verification/v1", "course_id": f"course.{course}",
        "sections": [], "pages": [],
    }, indent=2) + "\n")


RATIOS = "concepts/math-ratios.md"
SPEED = "concepts/physics-average-speed.md"
AVERAGE_SPEED = "courses/mechanics/sections/average-speed.md"
RATIOS_BASICS = "courses/proportional-reasoning/sections/ratios-basics.md"


def distribution_repo(root: Path) -> Path:
    """Two publishable courses that share one concept, as a producer would commit them."""
    course_tree(
        root, "mechanics", "Mechanics", "Describing motion before explaining it.",
        [("motion", "Motion", [
            ("average-speed", "Average speed", "Distance divided by elapsed time.",
             {"teaches": [SPEED], "prerequisites": [RATIOS]}),
            ("acceleration", "Acceleration", "How quickly velocity changes.",
             {"prerequisites": [SPEED]}),
        ]),
         ("forces", "Forces", [
             ("balanced-forces", "Balanced forces", "Steady motion needs no net force.", {}),
         ])],
        ["Speed and distance", "Change of velocity", "Balanced forces"],
    )
    course_tree(
        root, "proportional-reasoning", "Proportional reasoning",
        "Comparing quantities that scale together.",
        [("ratios", "Ratios", [
            ("ratios-basics", "Reading a ratio", "Two quantities compared by division.",
             {"teaches": [RATIOS]}),
        ])],
        ["Ratios and proportion"],
    )
    concept(root, "math-ratios", "Ratio",
            "A comparison of two quantities by division.",
            "A ratio compares two quantities by division, so $a : b$ is the number "
            "$a / b$ and is unchanged when both quantities scale together.",
            [AVERAGE_SPEED, RATIOS_BASICS], related=[SPEED])
    concept(root, "physics-average-speed", "Average speed",
            "Total distance divided by total elapsed time.",
            "Average speed is the ratio $\\bar v = \\Delta s / \\Delta t$ of the "
            "distance covered to the time taken, ignoring how the speed varied.",
            [AVERAGE_SPEED], prerequisites=[RATIOS])
    return root
