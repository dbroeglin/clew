"""Check an agent-selected vault location without classifying course material."""
from __future__ import annotations

import os
from pathlib import Path

from document_formats import Plan
from document_io import contained, no_redirect, relative_path, require

RESERVED = {".obsidian", ".git", ".github", ".agents"}


def placement_parent(plan: Plan) -> Path:
    vault = Path(plan.placement.vault)
    require(vault.is_absolute(), "Vault root must be absolute.")
    vault = no_redirect(vault)
    require(vault.is_dir(), f"Vault root is missing: {vault}")
    require(not any(part.casefold() in RESERVED for part in vault.parts),
            "Vault root must not be inside a configuration directory.")
    parent = relative_path(plan.placement.parent)
    require(not any(part.startswith(".") for part in parent.parts),
            "Placement must not target a hidden/configuration directory.")
    selected = contained(vault, parent.as_posix(), exists=False)
    ancestor = selected
    while ancestor.is_relative_to(vault):
        legacy = no_redirect(ancestor / "ingest.json")
        marker = no_redirect(ancestor / ".clew")
        require(not os.path.lexists(marker) and not os.path.lexists(legacy),
                f"Placement is inside an existing or unrecognized owned root: {ancestor}. "
                "Choose a sibling learning-material container.")
        if ancestor == vault:
            break
        ancestor = ancestor.parent
    return selected


def missing_parents(plan: Plan) -> list[Path]:
    parent = placement_parent(plan)
    vault = no_redirect(Path(plan.placement.vault))
    missing = []
    while parent != vault:
        no_redirect(parent)
        if os.path.lexists(parent):
            require(parent.is_dir(), f"Placement parent is not a directory: {parent}")
            break
        missing.append(parent)
        parent = parent.parent
    require(not missing or plan.placement.create_parent,
            "Placement parent is missing; approve create_parent or choose an existing parent.")
    return list(reversed(missing))
