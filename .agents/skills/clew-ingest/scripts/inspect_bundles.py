"""Inspect explicitly selected Import bundles without writing or making decisions."""
from __future__ import annotations

import argparse
from pathlib import Path

from bundle_sources import load_bundle
from ingest_io import command, require


def inspect(paths: list[Path]) -> dict:
    bundles = [load_bundle(path) for path in paths]
    require(len({str(bundle.root).casefold() for bundle in bundles}) == len(bundles),
            "The same bundle was selected twice.")
    return {"schema_version": 1, "bundles": [bundle.inventory() for bundle in bundles]}


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("bundles", nargs="+", type=Path)
    args = cli.parse_args()
    return command(lambda: inspect(args.bundles))


if __name__ == "__main__":
    raise SystemExit(main())
