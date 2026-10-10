"""Read-only, bounded vault layout inventory for agent placement decisions."""
from __future__ import annotations

import argparse
from pathlib import Path

from document_io import command, contained, no_redirect, require


def inspect(vault: Path, *, within: str | None = None, depth: int = 4,
            max_directories: int = 128, samples: int = 3) -> dict:
    vault = no_redirect(vault)
    require(vault.is_dir(), f"Vault directory is missing: {vault}")
    require(depth >= 0 and max_directories >= 1 and samples >= 1, "Invalid inventory limits.")
    scope = contained(vault, within, exists=False) if within else vault
    require(scope.is_dir(), f"Inventory scope is missing: {scope}")
    require(not any(part.startswith(".") for part in scope.relative_to(vault).parts),
            "Inventory scope must not be a hidden/configuration directory.")
    marker = no_redirect(vault / ".obsidian")
    directories: list[dict] = []
    omitted: list[dict] = []

    def reference(path: Path) -> str:
        return path.relative_to(vault).as_posix()

    def visit(path: Path, level: int) -> None:
        if len(directories) >= max_directories:
            omitted.append({"path": reference(path), "reason": "directory limit"})
            return
        children = sorted(path.iterdir(), key=lambda item: (item.name.casefold(), item.name))
        folders, notes = [], []
        for child in children:
            if child.name.startswith("."):
                omitted.append({"path": reference(child), "reason": "hidden/configuration entry"})
                continue
            no_redirect(child)
            if child.is_dir():
                folders.append(child)
            elif child.is_file() and child.suffix.lower() == ".md":
                notes.append(reference(child))
        legacy = any(child.name.casefold() == "ingest.json" for child in children)
        prepared = no_redirect(path / ".clew" / "preparation.json").is_file()
        directories.append({"path": reference(path), "markdown_count": len(notes),
                            "has_owned_root": legacy or prepared,
                            "markdown_samples": notes[:samples]})
        if legacy or prepared:
            omitted.extend({"path": reference(child), "reason": "owned document root"}
                           for child in folders)
            return
        for child in folders:
            if level == depth:
                omitted.append({"path": reference(child), "reason": "depth limit"})
            else:
                visit(child, level + 1)

    visit(scope, 0)
    return {"schema_version": 1, "vault": str(vault), "scope": reference(scope),
            "obsidian_marker": marker.is_dir(), "directories": directories,
            "omitted": omitted, "requires_agent_review": True}


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("vault", type=Path)
    cli.add_argument("--within", help="Relative visible directory for focused inspection")
    cli.add_argument("--depth", type=int, default=4)
    cli.add_argument("--max-directories", type=int, default=128)
    cli.add_argument("--samples", type=int, default=3)
    args = cli.parse_args()
    return command(lambda: inspect(args.vault, within=args.within, depth=args.depth,
                                   max_directories=args.max_directories, samples=args.samples))


if __name__ == "__main__":
    raise SystemExit(main())
