"""Discover selected Ingest chapters or inspect current notes, without writing."""
import argparse
from pathlib import Path

from notes import Library, command, list_chapters


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("notes", type=Path, nargs="+")
    cli.add_argument("--list-chapters", action="store_true",
                     help="List chapter roots within the supplied vault/container, without selecting them.")
    args = cli.parse_args()
    def inspect() -> dict:
        if args.list_chapters:
            return {"containers": [list_chapters(root) for root in args.notes]}
        library = Library(args.notes)
        return {"chapters": library.chapters, "notes": library.inventory()}

    return command(inspect)


if __name__ == "__main__":
    raise SystemExit(main())
