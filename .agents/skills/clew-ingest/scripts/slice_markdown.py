"""Print an exact, safely bounded Markdown line range; never write files."""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from ingest_io import IngestError, no_redirect, require
from markdown_source import MarkdownSource


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("markdown", type=Path)
    cli.add_argument("--start", type=int, required=True)
    cli.add_argument("--end", type=int, required=True)
    cli.add_argument("--sha256", required=True, help="Expected Markdown file hash")
    args = cli.parse_args()
    try:
        data = no_redirect(args.markdown).read_bytes()
        require(hashlib.sha256(data).hexdigest() == args.sha256, "Markdown changed since inspection.")
        text = data.decode("utf-8")
        sys.stdout.write(MarkdownSource(text).select(args.start, args.end))
        return 0
    except (IngestError, OSError, UnicodeError, ValueError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
