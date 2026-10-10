"""Inspect explicitly selected converted documents without writing anything."""
from __future__ import annotations

import argparse
from pathlib import Path

from bundle_sources import load_bundle
from document_io import command, require


def inspect(paths: list[Path]) -> dict:
    bundles = [load_bundle(path) for path in paths]
    require(len({str(bundle.root).casefold() for bundle in bundles}) == len(bundles),
            "The same conversion bundle was selected twice.")
    return {"schema_version": 1, "status": "needs_review" if any(
        bundle.manifest["status"] == "needs_review" for bundle in bundles) else "inspected",
        "bundles": [bundle.inventory() for bundle in bundles], "requires_agent_review": True}


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("bundles", nargs="+", type=Path)
    args = cli.parse_args()
    return command(lambda: inspect(args.bundles))


if __name__ == "__main__":
    raise SystemExit(main())
