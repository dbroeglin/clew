"""Shared temporary wheel fixtures from installed distributions, never published."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import re
import sys
import zipfile
from importlib.metadata import distribution
from pathlib import Path


def build_wheelhouse(directory: Path, requirements: str) -> None:
    """Retain installed runtime files/licenses and rebuild standard wheel RECORDs."""
    directory.mkdir()
    for line in requirements.splitlines():
        if not line or line[0].isspace() or line.startswith("#"):
            continue
        match = re.fullmatch(r"([\w.-]+)==([\w.+!-]+)", line)
        if match is None:
            raise ValueError(f"Unsupported fixture requirement: {line}")
        name, version = match.groups()
        installed = distribution(name)
        if installed.version != version:
            raise ValueError(f"Install the locked version of {name} before testing.")
        wheel_metadata = installed.read_text("WHEEL")
        if wheel_metadata is None or installed.files is None:
            raise ValueError(f"Missing installed wheel metadata: {name}")
        tags = [value.removeprefix("Tag: ") for value in wheel_metadata.splitlines()
                if value.startswith("Tag: ")]
        python_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
        tag = next((value for value in tags if value.startswith((python_tag, "py3"))), tags[0])
        archive_name = name.replace("-", "_") + "-" + version + "-" + tag + ".whl"
        site = Path(installed.locate_file("")).resolve()
        data: dict[str, bytes] = {}
        record_name = None
        for entry in installed.files:
            source = Path(installed.locate_file(entry)).resolve()
            if not source.is_relative_to(site):
                continue  # UV regenerates console entry points from wheel metadata.
            reference = source.relative_to(site).as_posix()
            if reference.endswith(".dist-info/RECORD"):
                record_name = reference
                continue
            if source.suffix == ".pyc" or source.name in {"INSTALLER", "REQUESTED", "direct_url.json"}:
                continue
            if not source.is_file():
                raise ValueError(f"Missing installed fixture file: {source}")
            data[reference] = source.read_bytes()
        if record_name is None:
            raise ValueError(f"Missing installed RECORD: {name}")
        record = io.StringIO(newline="")
        writer = csv.writer(record, lineterminator="\n")
        for reference, content in sorted(data.items()):
            digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode()
            writer.writerow([reference, "sha256=" + digest, len(content)])
        writer.writerow([record_name, "", ""])
        data[record_name] = record.getvalue().encode()
        with zipfile.ZipFile(directory / archive_name, "w", zipfile.ZIP_DEFLATED) as archive:
            for reference, content in sorted(data.items()):
                archive.writestr(reference, content)
