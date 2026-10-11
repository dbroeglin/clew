"""Version-bound checkpoints and immutable paid-response evidence."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import stat
import sys
import time
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path, PureWindowsPath
from typing import Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field

LOG = logging.getLogger("ingestion")
CHECKPOINT = "checkpoint.json"
LOCK = ".digest.lock"
PROGRESS_RETRY_DELAYS = (0.1, 0.2, 0.4, 0.8, 1.6)


class DigestionError(Exception):
    """An extraction cannot safely be published."""


class CheckpointError(DigestionError):
    """A checkpoint cannot safely be resumed."""


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PaidCall(StrictRecord):
    key: str
    kind: str
    request_sha256: str
    response: str
    status: Literal["pending", "received", "usable", "rejected"] = "pending"


class CheckpointRecord(StrictRecord):
    schema_version: Literal[1] = 1
    binding: dict[str, object]
    files: dict[str, str] = Field(default_factory=dict)
    calls: list[PaidCall] = Field(default_factory=list)
    analysis_attempted: bool = False
    operation_id: str | None = None
    complete: bool = False
    writing: dict[str, str] = Field(default_factory=dict)
    incomplete_temporary_files: list[str] = Field(default_factory=list)


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def runtime_fingerprint() -> str:
    scripts = Path(__file__).parent
    return fingerprint({
        "python": list(sys.version_info[:3]),
        "scripts": {
            name: fingerprint((scripts / name).read_text(encoding="utf-8")) for name in
            ("digest_pdf.py", "digestion_checkpoint.py", "math_render.py", "check_math.cjs")
        },
        "dependencies": {
            name: version(name) for name in (
                "azure-ai-documentintelligence", "azure-core", "azure-identity", "openai",
                "pymupdf", "pillow", "pydantic", "markdown-it-py", "mdit-py-plugins",
            )
        },
    })


def raise_walk_error(error: OSError) -> None:
    raise error


def replace_progress(pending: Path, target: Path) -> None:
    for attempt in range(len(PROGRESS_RETRY_DELAYS) + 1):
        try:
            pending.replace(target)
        except OSError as error:
            if getattr(error, "winerror", None) not in (5, 32, 33) or attempt == len(PROGRESS_RETRY_DELAYS):
                raise
            delay = PROGRESS_RETRY_DELAYS[attempt]
            LOG.warning(
                "Could not replace %s (WinError %s); local retry %s/%s in %.1f seconds.",
                target, error.winerror, attempt + 1, len(PROGRESS_RETRY_DELAYS), delay,
            )
            time.sleep(delay)
        else:
            return


def redirected(path: Path) -> bool:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        return True
    if not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        return False
    tag = getattr(info, "st_reparse_tag", 0)
    return tag == 0 or bool(tag & 0x20000000)


def safe_path(root: Path, reference: str) -> Path:
    relative, windows = Path(reference), PureWindowsPath(reference)
    if (
        not reference or relative.is_absolute() or windows.drive
        or ".." in relative.parts or ".." in windows.parts
    ):
        raise CheckpointError("Checkpoint artifact escapes the output directory.")
    path = root / relative
    for part in (path, *path.parents):
        if os.path.lexists(part) and redirected(part):
            raise CheckpointError(f"Resume path redirects or has an unknown reparse tag: {part}")
        if part == root:
            break
    if not path.resolve().is_relative_to(root.resolve()):
        raise CheckpointError("Checkpoint artifact escapes the output directory.")
    return path


@contextmanager
def output_lock(output: Path, *, inspect: bool = False) -> Iterator[None]:
    path = safe_path(output, LOCK)
    if inspect and not path.exists():
        raise CheckpointError("No output lock identifies this resumable run.")
    with path.open("rb" if inspect else "a+b") as stream:
        if not inspect and path.stat().st_size == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise CheckpointError("Another process is using this digest; do not resume it.") from error
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise CheckpointError("Another process is using this digest; do not resume it.") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@dataclass
class SavedResponse:
    status: str
    output_text: str
    usage: object
    model: object


def saved_response(data: Mapping[str, object]) -> SavedResponse:
    status = data.get("status")
    if not isinstance(status, str):
        raise CheckpointError("Saved response has no valid status.")
    text = data.get("output_text")
    if not isinstance(text, str):
        parts: list[str] = []
        output = data.get("output")
        if not isinstance(output, list):
            raise CheckpointError("Saved response has no output.")
        for message in output:
            if not isinstance(message, dict) or message.get("type") != "message":
                continue
            content = message.get("content")
            if not isinstance(content, list):
                raise CheckpointError("Saved response has malformed message content.")
            for item in content:
                if isinstance(item, dict) and item.get("type") == "output_text":
                    value = item.get("text")
                    if not isinstance(value, str):
                        raise CheckpointError("Saved response has malformed output text.")
                    parts.append(value)
        text = "".join(parts)
    return SavedResponse(status, text, data.get("usage"), data.get("model"))


class DigestionCheckpoint:
    def __init__(self, output: Path, record: CheckpointRecord):
        self.output = output
        self.record = record

    @classmethod
    def create(cls, output: Path, binding: dict[str, object]) -> DigestionCheckpoint:
        checkpoint = cls(output, CheckpointRecord(binding=binding))
        checkpoint.save()
        return checkpoint

    @classmethod
    def load(cls, output: Path, binding: dict[str, object]) -> DigestionCheckpoint:
        path = safe_path(output, CHECKPOINT)
        if not path.is_file():
            raise CheckpointError(
                "No resumable checkpoint: only runs started by a checkpoint-enabled converter "
                "can use --resume. Preserve this output."
            )
        checkpoint = cls(output, CheckpointRecord.model_validate_json(path.read_bytes()))
        if checkpoint.record.binding != binding:
            raise CheckpointError(
                "Resume refused: source, page scope, options, Azure configuration, or "
                "converter/dependency version changed. Use the original settings and version."
            )
        if len(checkpoint.record.writing) > 1:
            raise CheckpointError("Checkpoint contains conflicting pending writes.")
        for reference, digest in checkpoint.record.writing.items():
            target = safe_path(output, reference)
            pending_file = safe_path(output, reference + ".tmp")
            previous = checkpoint.record.files.get(reference)
            if target.is_file() and sha256(target) == digest:
                continue
            if pending_file.is_file() and sha256(pending_file) == digest:
                if target.exists() and (previous is None or sha256(target) != previous):
                    raise CheckpointError(f"Pending artifact was changed: {target}")
                continue
            if target.exists() and (previous is None or sha256(target) != previous):
                raise CheckpointError(f"Pending artifact was changed: {target}")
        for reference, digest in checkpoint.record.files.items():
            artifact = safe_path(output, reference)
            staged = checkpoint.record.writing.get(reference)
            if (
                not artifact.is_file()
                or sha256(artifact) not in {digest, staged}
            ):
                raise CheckpointError(f"Resume artifact is missing or changed: {artifact}")
        pending = {call.response for call in checkpoint.record.calls if call.status == "pending"}
        allowed = {
            CHECKPOINT, LOCK, "run.json", "run.json.tmp", CHECKPOINT + ".tmp",
            *checkpoint.record.incomplete_temporary_files,
            *checkpoint.record.writing,
            *(reference + ".tmp" for reference in checkpoint.record.writing),
        }
        for directory, directories, filenames in os.walk(
            output, followlinks=False, onerror=raise_walk_error,
        ):
            parent = Path(directory)
            for name in directories:
                if redirected(parent / name):
                    raise CheckpointError(f"Resume directory redirects: {parent / name}")
            for name in filenames:
                file = parent / name
                reference = file.relative_to(output).as_posix()
                safe_path(output, reference)
                if reference not in checkpoint.record.files and reference not in allowed | pending:
                    if reference.endswith(".tmp") and reference[:-4] in checkpoint.record.files:
                        continue
                    raise CheckpointError(f"Unexpected file in digest; preserve and inspect it: {file}")
        for call in checkpoint.record.calls:
            safe_path(output, call.response)
            if call.status != "pending" and call.response not in checkpoint.record.files:
                raise CheckpointError("Paid response is not committed in the checkpoint.")
        for reference in checkpoint.record.incomplete_temporary_files:
            if not reference.endswith(".tmp"):
                raise CheckpointError("Checkpoint has an invalid incomplete temporary-file reference.")
            safe_path(output, reference)
        if checkpoint.record.complete and "manifest.json" not in checkpoint.record.files:
            raise CheckpointError("Completed checkpoint has no committed completion manifest.")
        return checkpoint

    def save(self) -> None:
        path = safe_path(self.output, CHECKPOINT)
        pending = safe_path(self.output, CHECKPOINT + ".tmp")
        pending.write_bytes((self.record.model_dump_json(indent=2) + "\n").encode("utf-8"))
        replace_progress(pending, path)

    def recover_write(self) -> None:
        for reference, digest in list(self.record.writing.items()):
            target = safe_path(self.output, reference)
            pending = safe_path(self.output, reference + ".tmp")
            if target.is_file() and sha256(target) == digest:
                self.record.files[reference] = digest
            elif pending.is_file() and sha256(pending) == digest:
                pending.replace(target)
                self.record.files[reference] = digest
            else:
                LOG.warning("Interrupted local write will be regenerated: %s", target)
                if pending.exists():
                    reference = reference + ".tmp"
                    if reference not in self.record.incomplete_temporary_files:
                        self.record.incomplete_temporary_files.append(reference)
            self.record.writing.clear()
            self.save()
        for call in self.record.calls:
            if call.status == "pending" and call.response in self.record.files:
                call.status = "received"
                self.save()

    def prepare_write(self, path: Path, digest: str) -> tuple[Path, Path, str]:
        reference = path.relative_to(self.output).as_posix()
        target = safe_path(self.output, reference)
        if target.exists():
            expected = self.record.files.get(reference)
            actual = sha256(target)
            if expected is None and actual != digest:
                raise CheckpointError(f"Refusing to overwrite an uncommitted artifact: {target}")
            if expected is not None and actual != expected:
                raise CheckpointError(f"Artifact changed during this run: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        pending = safe_path(self.output, reference + ".tmp")
        self.record.writing = {reference: digest}
        self.save()
        return target, pending, reference

    def finish_write(self, target: Path, pending: Path, reference: str, digest: str) -> None:
        if sha256(pending) != digest:
            raise CheckpointError("The copied artifact does not match its source hash; import stopped.")
        pending.replace(target)
        self.record.files[reference] = digest
        temporary = reference + ".tmp"
        if temporary in self.record.incomplete_temporary_files:
            self.record.incomplete_temporary_files.remove(temporary)
        self.record.writing.clear()
        self.save()

    def write(self, path: Path, data: bytes) -> None:
        digest = hashlib.sha256(data).hexdigest()
        reference = path.relative_to(self.output).as_posix()
        if self.record.files.get(reference) == digest and sha256(safe_path(self.output, reference)) == digest:
            return
        target, pending, reference = self.prepare_write(path, digest)
        pending.write_bytes(data)
        self.finish_write(target, pending, reference, digest)

    def copy(self, source: Path, destination: Path) -> None:
        digest = sha256(source)
        if source.is_relative_to(self.output):
            expected = self.record.files.get(source.relative_to(self.output).as_posix())
            if expected is None or digest != expected:
                raise CheckpointError(f"Source artifact changed during this run: {source}")
        reference = destination.relative_to(self.output).as_posix()
        if self.record.files.get(reference) == digest and sha256(safe_path(self.output, reference)) == digest:
            return
        target, pending, reference = self.prepare_write(destination, digest)
        shutil.copyfile(source, pending)
        self.finish_write(target, pending, reference, digest)

    def write_json(self, path: Path, value: object) -> None:
        self.write(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    def cached_call(self, key: str, request: object) -> PaidCall | None:
        digest = fingerprint(request)
        for call in reversed(self.record.calls):
            if call.key != key:
                continue
            if call.request_sha256 != digest:
                raise CheckpointError(f"Resume request changed for {key}; no cloud call was repeated.")
            if call.status in {"received", "usable"}:
                return call
            return None
        return None

    def begin_call(self, key: str, kind: str, request: object) -> PaidCall:
        call = PaidCall(
            key=key, kind=kind, request_sha256=fingerprint(request),
            response=f"raw/checkpoints/response-{len(self.record.calls) + 1:06d}.json",
        )
        self.record.calls.append(call)
        self.save()
        return call

    def response_data(self, call: PaidCall) -> dict[str, object]:
        value = json.loads(self.read(self.output / call.response))
        if not isinstance(value, dict):
            raise CheckpointError("Saved paid response is not a JSON object.")
        return value

    def read(self, path: Path) -> bytes:
        reference = path.relative_to(self.output).as_posix()
        data = safe_path(self.output, reference).read_bytes()
        if hashlib.sha256(data).hexdigest() != self.record.files.get(reference):
            raise CheckpointError(f"Artifact changed during this run: {path}")
        return data

    def usage(self) -> Iterator[tuple[str, SavedResponse]]:
        for call in self.record.calls:
            if call.status != "pending":
                yield call.kind, saved_response(self.response_data(call))

    def summary(self) -> dict[str, object]:
        if (
            self.record.analysis_attempted and not self.record.operation_id
            and "raw/document-intelligence.json" not in self.record.files
        ):
            raise CheckpointError(
                "DI submission outcome is unknown: no operation ID was committed. "
                "Resume cannot safely resubmit the PDF; inspect the original failure."
            )
        if self.record.operation_id is not None and not self.record.operation_id.strip():
            raise CheckpointError("Checkpoint contains an invalid DI operation ID.")
        return {
            "checkpoint_sha256": sha256(self.output / CHECKPOINT),
            "completed_model_requests": sum(call.status == "usable" for call in self.record.calls),
            "completed_page_model_requests": sum(
                call.status == "usable" and call.kind in {"page_transcription", "page_review"}
                for call in self.record.calls
            ),
            "received_page_model_requests": sum(
                call.status == "received" and call.kind in {"page_transcription", "page_review"}
                for call in self.record.calls
            ),
            "failed_model_responses": sum(call.status == "rejected" for call in self.record.calls),
            "uncertain_model_requests": sum(call.status == "pending" for call in self.record.calls),
            "document_intelligence": (
                "reuse_saved_layout" if "raw/document-intelligence.json" in self.record.files
                else "poll_existing_operation" if self.record.operation_id else "submit"
            ),
            "complete": self.record.complete,
        }
