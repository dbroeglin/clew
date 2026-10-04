"""Local path, hashing, and command-line utilities; no semantic decisions."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Callable

from pydantic import ValidationError


class IngestError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise IngestError(message)


def no_redirect(path: Path) -> Path:
    """Allow cloud placeholders, but never traverse name-surrogate reparse tags."""
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if not os.path.lexists(item):
            continue
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode), f"Redirected path: {item}")
        if getattr(info, "st_file_attributes", 0) & 0x400:
            tag = getattr(info, "st_reparse_tag", 0)
            require(bool(tag) and not tag & 0x20000000,
                    f"Redirected path or unavailable reparse tag: {item}")
    return path


def relative_path(value: str) -> PurePosixPath:
    win = PureWindowsPath(value)
    path = PurePosixPath(value)
    require(bool(value) and "\\" not in value and not win.drive
            and not win.is_absolute() and not path.is_absolute(),
            f"Expected a portable relative path: {value!r}")
    require(all(part not in {"", ".", ".."} for part in value.split("/")),
            f"Unsafe relative path: {value!r}")
    for part in path.parts:
        stem = part.split(".")[0].upper()
        require(not re.search(r'[<>:"|?*\x00-\x1f]', part)
                and not part.endswith((" ", "."))
                and stem not in {"CON", "PRN", "AUX", "NUL",
                                 *[f"COM{i}" for i in range(1, 10)],
                                 *[f"LPT{i}" for i in range(1, 10)]},
                f"Nonportable filename: {part!r}")
    return path


def contained(root: Path, reference: str, *, exists: bool = True) -> Path:
    root = no_redirect(root)
    target = no_redirect(root.joinpath(*relative_path(reference).parts))
    require(target.is_relative_to(root), f"Path escapes root: {reference}")
    if exists:
        require(target.is_file(), f"Missing file: {target}")
    return target


def sha256(path: Path) -> str:
    with no_redirect(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def read_json(path: Path) -> object:
    return json.loads(no_redirect(path).read_text(encoding="utf-8"))


def fingerprint(value: object) -> str:
    return hashlib.sha256(json_text(value).encode("utf-8")).hexdigest()


def write_new(path: Path, data: bytes) -> None:
    no_redirect(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    no_redirect(path)
    with path.open("xb") as stream:
        stream.write(data)


def command(action: Callable[[], object]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        result = action()
        sys.stdout.write(json_text(result))
        return 0
    except (IngestError, ValidationError, OSError, UnicodeError, ValueError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1
