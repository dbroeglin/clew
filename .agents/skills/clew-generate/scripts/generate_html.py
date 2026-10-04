"""Check or publish current selected Obsidian notes as one offline HTML file."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

from notes import command, local_path, require
from publication import compile_layout, load_layout
from render_html import Renderer, assemble


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
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=output.parent, suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(page)
                stream.flush()
                os.fsync(stream.fileno())
            local_path(output)
            if overwrite:
                os.replace(temporary, output)
            else:
                # A hard link atomically refuses a concurrently created destination.
                os.link(temporary, output)
            report["bytes"] = output.stat().st_size
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    return report


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("layout", type=Path)
    cli.add_argument("--check", action="store_true")
    cli.add_argument("--overwrite", action="store_true")
    args = cli.parse_args()
    return command(lambda: generate(args.layout, check=args.check, overwrite=args.overwrite))


if __name__ == "__main__":
    raise SystemExit(main())
