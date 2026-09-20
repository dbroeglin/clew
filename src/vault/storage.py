"""Save an existing vault location without opening course or learner files."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".clew.local.json"
PRIVATE = ("model", "artifacts")


class VaultError(Exception):
    """An actionable vault configuration failure."""


def plain_path(path: Path) -> Path:
    """Check existing ancestors without following symlinks or Windows junctions."""
    path = Path(os.path.abspath(path))
    for ancestor in reversed((path, *path.parents)):
        try:
            info = ancestor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise VaultError(f"Symlink/reparse path is not allowed: {ancestor}")
    return path


def read_json(path: Path) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise VaultError(f"Duplicate JSON key {key!r} in {path}")
            result[key] = value
        return result

    plain_path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (OSError, ValueError) as exc:
        raise VaultError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VaultError(f"Expected a JSON object: {path}")
    return value


def atomic_write(path: Path, content: bytes) -> None:
    plain_path(path)
    descriptor, name = tempfile.mkstemp(prefix=".clew-write-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def vault_path(explicit: str | Path | None = None) -> Path:
    if explicit is None:
        plain_path(CONFIG)
        if not CONFIG.exists():
            raise VaultError(
                "Configure an existing external vault first: "
                "python -m src.vault.cli configure --vault PATH"
            )
        configuration = read_json(CONFIG)
        explicit = configuration.get("vault")
        if (
            set(configuration) != {"version", "vault"}
            or type(configuration["version"]) is not int
            or configuration["version"] != 1
            or not isinstance(explicit, str)
        ):
            raise VaultError(f"Invalid configuration: {CONFIG}; run configure --vault PATH")
    path = Path(explicit)
    if not path.is_absolute():
        raise VaultError("The vault must be an explicit absolute path.")
    path = plain_path(path).resolve()
    root = ROOT.resolve()
    if path == root or root in path.parents or path in root.parents:
        raise VaultError("The vault must be outside this clone and cannot contain it.")
    if not path.exists():
        raise VaultError(f"Vault does not exist: {path}. Create it yourself, then configure its path.")
    if not path.is_dir():
        raise VaultError(f"Vault is not a directory: {path}")
    return path


def protect_private_paths(vault: Path, *, write_ignore: bool = False) -> dict:
    """Inspect Git's index only, never learner files or their content."""
    vault = plain_path(vault).resolve()
    environment = {**os.environ, "LC_ALL": "C"}
    try:
        result = subprocess.run(
            ["git", "-C", str(vault), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            env=environment,
        )
    except FileNotFoundError as exc:
        raise VaultError(
            "Git is required to check for already-tracked private vault paths. "
            "Install Git and retry."
        ) from exc
    if result.returncode:
        if "not a git repository" in result.stderr.lower():
            return {"version_controlled": False, "ignore_rules_missing": []}
        raise VaultError(f"Cannot determine vault Git status: {result.stderr.strip()}")
    git_root = Path(result.stdout.strip()).resolve()
    try:
        relative = vault.relative_to(git_root).as_posix()
    except ValueError as exc:
        raise VaultError(
            "Git reports a worktree outside the selected vault's ancestors; "
            "review its Git configuration."
        ) from exc
    prefix = "" if relative == "." else relative + "/"
    paths = [":(icase,literal)" + prefix + name for name in PRIVATE]
    tracked = subprocess.run(
        ["git", "-C", str(git_root), "ls-files", "-z", "--", *paths],
        capture_output=True,
        check=False,
        env=environment,
    )
    if tracked.returncode:
        raise VaultError("Cannot inspect the vault Git index; private-data protection was not applied.")
    if tracked.stdout:
        raise VaultError(
            "Private vault paths are already tracked by Git. Stop tracking model/, artifacts/, "
            "explicitly and review repository history before continuing. "
            "Ignore rules do not untrack data, erase history, or encrypt files."
        )
    ignore = plain_path(vault / ".gitignore")
    existing = ignore.read_bytes() if ignore.exists() else b""
    rules = [f"/{name}/" for name in PRIVATE]
    lines = existing.decode("utf-8").splitlines()
    ignored = subprocess.run(
        ["git", "-C", str(vault), "check-ignore", "--no-index", "--stdin", "-z"],
        input=b"model/\0artifacts/\0",
        capture_output=True,
        check=False,
        env=environment,
    )
    if ignored.returncode not in (0, 1):
        raise VaultError("Cannot verify vault ignore rules; no private-data protection was claimed.")
    matches = ignored.stdout.decode("utf-8").split("\0")
    missing = [rule for rule in rules if rule not in lines or rule[1:] not in matches]
    if missing and write_ignore:
        separator = b"\n" if existing and not existing.endswith(b"\n") else b""
        additions = "# Clew private local state (not encryption)\n" + "\n".join(missing) + "\n"
        atomic_write(ignore, existing + separator + additions.encode("utf-8"))
        missing = []
    return {"version_controlled": True, "ignore_rules_missing": missing}


def describe(vault: Path, git: dict) -> dict:
    existing = sorted(entry.name for entry in vault.iterdir() if entry.name.casefold() in PRIVATE)
    warnings = []
    if existing:
        warnings.append(
            "Reserved model/artifacts paths already exist. Their contents and ownership were not "
            "inspected. Ask before writing if they are not confirmed Clew learner records and "
            "personal work."
        )
    if git["ignore_rules_missing"]:
        warnings.append(
            "Private-path ignore rules are missing; run configure again before storing learner records."
        )
    return {
        "status": "configured",
        "vault": str(vault),
        "existing_private_paths": existing,
        "warnings": warnings,
        "git": git,
    }


def configure(explicit: str | Path) -> dict:
    vault = vault_path(explicit)
    plain_path(CONFIG)
    configuration = {"version": 1, "vault": str(vault)}
    encoded = (json.dumps(configuration, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    previous = CONFIG.read_bytes() if CONFIG.exists() else None
    report = describe(vault, protect_private_paths(vault, write_ignore=True))
    if previous != encoded:
        atomic_write(CONFIG, encoded)
    return report


def status() -> dict:
    vault = vault_path()
    return describe(vault, protect_private_paths(vault))
