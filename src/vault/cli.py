"""Remember the student's existing external vault once, or inspect its location."""

from __future__ import annotations

import argparse
import json
import sys

from .storage import VaultError, configure, status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("configure", help="Remember an existing external vault")
    setup.add_argument("--vault", required=True, help="Absolute path to a vault you already created")
    commands.add_parser("status", help="Read configuration without changing any files")
    arguments = parser.parse_args(argv)
    try:
        result = configure(arguments.vault) if arguments.command == "configure" else status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (VaultError, OSError, UnicodeError, ValueError) as exc:
        print(f"Clew: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
