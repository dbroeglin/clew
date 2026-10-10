"""Local preparation utilities; no cloud clients or content generation."""
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
import yaml


class DocumentError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DocumentError(message)


def no_redirect(path: Path) -> Path:
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
    require(isinstance(value, str), f"Expected a relative path string: {value!r}")
    path, windows = PurePosixPath(value), PureWindowsPath(value)
    require(bool(value) and "\\" not in value and not path.is_absolute()
            and not windows.drive and not windows.is_absolute(),
            f"Expected a portable relative path: {value!r}")
    require(all(part not in {"", ".", ".."} for part in value.split("/")),
            f"Unsafe relative path: {value!r}")
    for part in path.parts:
        require(not re.search(r'[<>:"|?*\x00-\x1f#^]', part)
                and not part.endswith((" ", "."))
                and part.split(".")[0].upper() not in {
                    "CON", "PRN", "AUX", "NUL",
                    *[f"COM{i}" for i in range(1, 10)],
                    *[f"LPT{i}" for i in range(1, 10)],
                }, f"Nonportable filename: {part!r}")
    return path


def contained(root: Path, reference: str, *, exists: bool = True) -> Path:
    root = no_redirect(root)
    target = no_redirect(root.joinpath(*relative_path(reference).parts))
    require(target.is_relative_to(root), f"Path escapes root: {reference}")
    if exists:
        require(target.is_file(), f"Missing file: {target}")
    return target


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    with no_redirect(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def fingerprint(value: object) -> str:
    return digest(json_text(value).encode("utf-8"))


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> object:
    return json.loads(no_redirect(path).read_bytes(), object_pairs_hook=unique_object)


class UniqueLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        self.flatten_mapping(node)
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            require(isinstance(key, str), "YAML property names must be strings.")
            require(key not in result, f"Duplicate YAML property: {key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def yaml_object(text: str) -> dict:
    result = yaml.load(text, Loader=UniqueLoader)
    require(isinstance(result, dict), "Frontmatter must be a YAML object.")
    return result


def write_new(path: Path, data: bytes) -> None:
    path = no_redirect(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    no_redirect(path)
    with path.open("xb") as stream:
        stream.write(data)


def command(action: Callable[[], dict]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        report = action()
        sys.stdout.write(json_text(report))
        return 1 if report.get("status") == "invalid" else (
            2 if report.get("status") == "needs_review" else 0)
    except (DocumentError, ValidationError, OSError, UnicodeError, ValueError,
            yaml.YAMLError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1
