"""Inspect only explicitly selected Markdown files, without writing."""
import argparse
from pathlib import Path

from notes import Library, command


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("notes", type=Path, nargs="+")
    args = cli.parse_args()
    return command(lambda: {"notes": Library(args.notes).inventory()})


if __name__ == "__main__":
    raise SystemExit(main())
