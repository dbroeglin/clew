# ADR-0007: Course-linked question enrichment

- Status: Accepted
- Date: 2026-10-04

## Context

[ADR-0001](0001-document-processing-pipeline.md) separates faithful Import,
optional Enrich, and repeatable Generate. [ADR-0008](0008-exercise-unit-pipeline-contract.md)
defines the stable document-internal exercise/correction units and question/
answer anchors produced by Import. Enrich needs to preserve those complete
source documents while adding optional learning aids.

The first Enrich scope remains deliberately small: question-specific hints and
explanations of supplied answers, both linked to existing course passages.
Real worksheets contain shared context, ordinary lists, and multiline
mathematics; stable imported anchors and source-unit ownership are safer than
line-range mappings or regenerated boundaries.

## Decision

`clew-enrich` consumes only a completed Import whole-document chapter:
`type: chapter` index, `type: document` notes, and `.clew/preparation.json` with
`status: complete`. It follows each note's explicit role, document ID, source
unit comments, native exercise/correction entry anchors, and question/answer
anchors. It does not consume or migrate the legacy exercise-per-note layout.

The host agent reads selected current notes, decides semantic question/answer
and course matches, previews concrete changes, obtains approval, and writes
separate `aides/` notes with `type: help`. Hints and explanations are anchored
callouts; each contains a precise existing course heading/block link. Aid
frontmatter links to the imported question and, for an explanation, its
specific supplied answer. Import's `Exercise` and `Question` relationship
footers and enclosing unit scopes define ownership. Missing answers remain
missing. Enrich never changes imported documents, the index, preparation
record, retained sources, or existing aids.

A local validator captures a versioned file-hash and inventory baseline in
host scratch storage outside the chapter and repository, then checks persisted
additions. Only new Markdown under `aides/` is permitted. It verifies the
completed preparation identity, unchanged existing files, unique IDs/anchors,
unit ownership, answer/question agreement, and precise local course references.
The validator does not write notes or decide semantic matches. Pedagogical
correctness remains the agent's responsibility; ambiguous matches or
inconsistent supplied mathematics require a user decision, not silent repair.
Existing aid notes are immutable in this additive increment; do not recapture a
baseline to hide edits.

The validator is self-contained with its own direct runtime dependencies. It
requires a prepared Import artifact, not Import runtime code or installation.
No external learning sources, embedded model, cloud service, or repository
specific runtime knowledge is required.

Generate remains a legacy exercise-per-note consumer. It does not consume
prepared-document Enrich aids, and this decision does not claim new-format HTML
publication or end-to-end compatibility. Existing legacy archives are not
migrated.

Keep tests outside skills in `tests/clew_enrich/`, with independently authored
synthetic prepared-document fixtures. Update all affected portable contracts,
examples, project documentation, compatibility claims, and the ADR index.

## Consequences

- Stable document and block addresses support aids without splitting or editing
  the imported source documents.
- Generated learning prose remains separate and distinguishable from supplied
  course/exercise/correction content.
- Import preparation evidence is retained unchanged and local baselines remain
  comparison evidence, not permission tokens or revision history.
- Generate continues to publish only its legacy input contract until separately
  refactored; legacy archives are not migrated.
- Existing human aids are preserved. Aid revisions, broader enrichment,
  generated answers/exercises, and revision history remain outside this scope.
