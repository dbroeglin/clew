"""Check or publish current selected Obsidian notes as offline HTML or live-reader data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

from notes import command, local_path, require
from publication import compile_layout, load_layout
from render_html import Renderer, assemble


def write_atomically(output: Path, text: str, *, replace: bool) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=output.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        local_path(output)
        if replace:
            os.replace(temporary, output)
        else:
            # A hard link atomically refuses a concurrently created destination.
            os.link(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def generate(path: Path, *, check: bool = False, overwrite: bool = False) -> dict:
    layout, library = load_layout(path)
    output = Path(layout["output"])
    require(not output.exists() or (overwrite and output.is_file()),
            f"Output exists; use a new path or explicitly approve --overwrite: {output}")
    renderer = Renderer(library, output)
    data = compile_layout(layout, library, renderer)
    renderer.validate_links()
    page = assemble(data)
    report = {"status": "checked" if check else "generated", "output": str(output),
              "exercises": len(data["exercises"]), "questions": len(data["questions"]),
              "course_views": len(data["courses"]), "warnings": renderer.warnings}
    if not check:
        write_atomically(output, page, replace=overwrite)
        report["bytes"] = output.stat().st_size
    return report


def relative(path: Path, base: Path) -> str:
    try:
        return os.path.relpath(path, base).replace("\\", "/")
    except ValueError:
        return path.as_uri()


def compile_data(path: Path, target: Path, *, base: Path | None = None) -> dict:
    """Write the compiled publication as JSON for a live reader such as a canvas.

    Source PDF links and ``sources`` paths are relative to ``base`` (default: the
    layout directory). The layout ``output`` is ignored and nothing else is written.
    """
    layout, library = load_layout(path, data=True)
    target = local_path(target)
    require(target.suffix.lower() == ".json", "Data output must be a .json file.")
    require(target not in {note.path for note in library.notes} and target != local_path(path),
            "Data output cannot replace an input.")
    require(target.parent.is_dir(), f"Data output parent does not exist: {target.parent}")
    base = local_path(base if base is not None else Path(path).parent)
    require(base.is_dir(), f"Base directory does not exist: {base}")
    # The renderer resolves PDF links relative to its output's parent directory.
    renderer = Renderer(library, base / "publication.html")
    data = compile_layout(layout, library, renderer)
    renderer.validate_links()
    data["sources"] = [{"id": note.id, "title": note.title, "type": note.metadata.get("type", ""),
                        "role": note.role, "path": relative(note.path, base),
                        "sha256": hashlib.sha256(note.text.encode("utf-8")).hexdigest()}
                       for note in library.notes]
    data["warnings"] = renderer.warnings
    write_atomically(target, json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                     replace=True)
    return {"status": "data", "output": str(target),
            "exercises": len(data["exercises"]), "questions": len(data["questions"]),
            "course_views": len(data["courses"]), "warnings": renderer.warnings}


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("layout", type=Path)
    mode = cli.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--data", type=Path, metavar="JSON",
                      help="write compiled publication data for a live reader instead of HTML")
    cli.add_argument("--overwrite", action="store_true")
    cli.add_argument("--base", type=Path, help="directory that data-mode paths are relative to")
    args = cli.parse_args()
    if args.base is not None and args.data is None:
        cli.error("--base requires --data")
    if args.data is not None:
        return command(lambda: compile_data(args.layout, args.data, base=args.base))
    return command(lambda: generate(args.layout, check=args.check, overwrite=args.overwrite))


if __name__ == "__main__":
    raise SystemExit(main())
