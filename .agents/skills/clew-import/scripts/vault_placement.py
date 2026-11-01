"""Check an agent-selected vault location without classifying course material."""
from __future__ import annotations

import os
from pathlib import Path

from document_formats import Plan
from document_io import contained, no_redirect, relative_path, require

RESERVED = {".obsidian", ".git", ".github", ".agents"}


def placement_parent(plan: Plan) -> Path:
    return parent_in_vault(plan.placement.vault, plan.placement.parent)


def missing_parents(plan: Plan) -> list[Path]:
    return missing_parents_in_vault(plan.placement.vault, plan.placement.parent,
                                    plan.placement.create_parent)


def parent_in_vault(vault_root: str, parent_reference: str) -> Path:
    vault = Path(vault_root)
    require(vault.is_absolute(), "Vault root must be absolute.")
    vault = no_redirect(vault)
    require(vault.is_dir(), f"Vault root is missing: {vault}")
    require(not any(part.casefold() in RESERVED for part in vault.parts),
            "Vault root must not be inside a configuration directory.")
    parent = relative_path(parent_reference)
    require(not any(part.startswith(".") for part in parent.parts),
            "Placement must not target a hidden/configuration directory.")
    selected = contained(vault, parent.as_posix(), exists=False)
    ancestor = selected
    while ancestor.is_relative_to(vault):
        legacy = no_redirect(ancestor / "ingest.json")
        private = no_redirect(ancestor / ".clew")
        if os.path.lexists(private):
            require(private.is_dir(), f"Private metadata path is not a directory: {private}")
        marker = no_redirect(private / "preparation.json")
        baselines = no_redirect(private / "baselines")
        require(not any(os.path.lexists(path) for path in (marker, baselines, legacy)),
                f"Placement is inside an existing or unrecognized owned root: {ancestor}. "
                "Choose a sibling learning-material container.")
        if ancestor == vault:
            break
        ancestor = ancestor.parent
    return selected


def missing_parents_in_vault(vault_root: str, parent_reference: str, create_parent: bool) -> list[Path]:
    parent = parent_in_vault(vault_root, parent_reference)
    vault = no_redirect(Path(vault_root))
    missing = []
    while parent != vault:
        no_redirect(parent)
        if os.path.lexists(parent):
            require(parent.is_dir(), f"Placement parent is not a directory: {parent}")
            break
        missing.append(parent)
        parent = parent.parent
    require(not missing or create_parent,
            "Placement parent is missing; approve create_parent or choose an existing parent.")
    return list(reversed(missing))
