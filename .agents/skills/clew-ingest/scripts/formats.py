"""Versioned agent plan and output records."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Slug = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
OUTPUT_VERSION = 3


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if isinstance(value, dict) and "schema_version" in value and type(value["schema_version"]) is not int:
            raise ValueError("Schema version must be an integer, not a boolean or string.")
        return value


class Source(Record):
    id: Slug
    bundle: str
    fingerprint: Digest


class Span(Record):
    source: Slug
    start: int = Field(ge=1)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered(self) -> Span:
        if self.end < self.start:
            raise ValueError("Source range end precedes start.")
        return self


class Part(Span):
    role: Literal["text", "question", "answer"] = "text"
    id: Slug | None = None
    label: str | None = None

    @model_validator(mode="after")
    def addressed(self) -> Part:
        if self.role == "text" and (self.id is not None or self.label is not None):
            raise ValueError("Plain text has no block ID or structural label.")
        if self.role != "text" and self.id is None:
            raise ValueError("Questions and answers require block IDs.")
        return self


class Note(Record):
    id: Slug
    type: Literal["course", "section", "exercise", "correction"]
    title: str = Field(min_length=1)
    title_origin: Literal["source", "agent"]
    order: int = Field(ge=1)
    parts: list[Part]


class Edge(Record):
    rel: Literal["course", "correction", "question", "needs"]
    origin: str
    target: str
    evidence: list[Span] = Field(min_length=1)


class Issue(Record):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    note: Slug | None = None


class Placement(Record):
    vault: str
    parent: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    create_parent: bool = False


class Plan(Record):
    schema_version: Literal[2]
    ingest_id: Slug
    title: str = Field(min_length=1)
    destination: str
    placement: Placement
    sources: list[Source] = Field(min_length=1)
    notes: list[Note] = Field(min_length=1)
    relationships: list[Edge]
    issues: list[Issue]


class ImportedSource(Record):
    name: str
    path: str
    sha256: Digest
    page_count: int = Field(ge=1)


class RetainedMetadata(Record):
    status: Literal["extracted", "needs_review"]
    source: ImportedSource
    pages: list[int] = Field(min_length=1)
    issues: list[object]


class Snapshot(Record):
    metadata: RetainedMetadata
    files: dict[str, Digest]
    fingerprint: Digest


class IngestRecord(Record):
    schema_version: Literal[3]
    status: Literal["writing", "complete"]
    plan: Plan
    plan_sha256: Digest
    sources: dict[Slug, Snapshot]
    issues: list[Issue]
    files: dict[str, Digest]
