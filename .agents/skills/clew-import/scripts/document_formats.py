"""The closed, versioned whole-document preparation contract."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Slug = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")]
AnchorId = Annotated[str, Field(pattern=r"^[A-Za-z0-9-]+$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
BlockId = Annotated[str, Field(pattern=r"^b-[1-9][0-9]*$")]
Role = Literal["course", "exercise", "correction", "mixed", "unknown"]
CalloutKind = Literal[
    "definition", "theorem", "property", "lemma", "proposition", "corollary",
    "example", "remark", "proof", "question", "answer",
]
UNIT_KINDS = {"section", "exercise", "correction"}
CALLOUT_KINDS = {
    "definition", "theorem", "property", "lemma", "proposition", "corollary",
    "example", "remark", "proof", "question", "answer",
}


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="before")
    @classmethod
    def integer_schema(cls, value: object) -> object:
        if isinstance(value, dict):
            for key in ("schema_version", "clew_schema"):
                if key in value and type(value[key]) is not int:
                    raise ValueError("Schema versions must be integers, not booleans or strings.")
        return value


class Address(Record):
    document: Slug
    anchor: AnchorId


class Evidence(Record):
    document: Slug
    start: BlockId
    end: BlockId


class Match(Record):
    target: Address
    evidence: list[Evidence] = Field(min_length=1)


class Selection(Record):
    start: BlockId
    end: BlockId


class Unit(Selection):
    op: Literal["unit"]
    kind: Literal["section", "exercise", "correction"]
    id: AnchorId
    exercise: Match | None = None

    @model_validator(mode="after")
    def relationship_kind(self) -> Unit:
        if self.exercise is not None and self.kind != "correction":
            raise ValueError("Only correction units declare an exercise match.")
        return self


class Callout(Selection):
    op: Literal["callout"]
    kind: CalloutKind
    id: AnchorId
    owner: AnchorId | None = None
    question: Match | None = None

    @model_validator(mode="after")
    def ownership(self) -> Callout:
        if (self.kind in {"question", "answer"}) != (self.owner is not None):
            raise ValueError("Questions/answers require an owner; course callouts have no owner.")
        if self.question is not None and self.kind != "answer":
            raise ValueError("Only supplied answers declare a question match.")
        return self


class Anchor(Record):
    op: Literal["anchor"]
    block: BlockId
    id: AnchorId


class Heading(Record):
    op: Literal["heading"]
    block: BlockId
    level: int = Field(ge=1, le=6)


Operation = Annotated[Unit | Callout | Anchor | Heading, Field(discriminator="op")]


class Review(Record):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    block: BlockId | None = None

    @model_validator(mode="after")
    def visible_text(self) -> Review:
        if not self.message.strip() or any(ord(char) < 32 for char in self.code + self.message):
            raise ValueError("Review messages must be nonempty, single-line, printable text.")
        return self


class Document(Record):
    id: Slug
    bundle: str
    fingerprint: Digest
    role: Role = "unknown"
    folder: str | None = None
    operations: list[Operation] = Field(default_factory=list)
    reviews: list[Review] = Field(default_factory=list)


class Placement(Record):
    vault: str
    parent: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    create_parent: bool = False


class Plan(Record):
    schema_version: Literal[1]
    id: Slug
    title: str = Field(min_length=1)
    destination: str
    placement: Placement
    documents: list[Document] = Field(min_length=1)

    @model_validator(mode="after")
    def title_line(self) -> Plan:
        if not self.title.strip() or any(ord(char) < 32 for char in self.title):
            raise ValueError("Chapter title must be nonempty, single-line, printable text.")
        return self


class Finding(Record):
    code: str
    severity: Literal["error", "review"]
    path: str
    line: int = Field(ge=1)
    end_line: int | None = Field(default=None, ge=1)
    message: str
    anchor: str | None = None
    target: str | None = None


class Change(Record):
    kind: Literal[
        "insert", "quote-prefix", "heading-prefix", "heading-suffix",
        "page-marker", "link-destination", "callout-spacing",
    ]
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    output_start: int = Field(ge=0)
    output_end: int = Field(ge=0)
    before_sha256: Digest
    after: str


class PreparedSource(Record):
    id: Slug
    path: str
    role: Role
    pdf: str
    page_count: int = Field(ge=1)
    pages: list[int] = Field(min_length=1)
    baseline: str
    baseline_sha256: Digest
    retained_files: dict[str, Digest]
    changes: list[Change]
    prepared_sha256: Digest


class PreparationRecord(Record):
    schema_version: Literal[1]
    status: Literal["writing", "complete"]
    plan: Plan
    plan_sha256: Digest
    documents: list[PreparedSource] = Field(min_length=1)
    findings: list[Finding]
    index_sha256: Digest
