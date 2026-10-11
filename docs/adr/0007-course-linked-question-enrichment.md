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
and course matches, drafts in scratch, reviews exact prose, obtains approval,
and writes separate `aides/` notes with `type: help`. Hints and explanations are anchored
callouts; each contains a precise existing course heading/block link. Aid
frontmatter links to the imported question and, for an explanation, its
specific supplied answer. Import's `Exercise` and `Question` relationship
footers and enclosing unit scopes define ownership. Document IDs are internal
identity keys, not navigational targets. Wikilinks use actual unique filenames or
chapter-relative note paths; Markdown links use origin-relative paths. New aids
have readable labels on question/correction wikilinks and local body links.
Existing aids are not rewritten to satisfy new label requirements. Missing
answers remain missing. Enrich never changes imported documents, the index, preparation
record, retained sources, or existing aids.

A local validator captures a versioned file-hash and inventory baseline in
host scratch storage outside the chapter and repository, then checks persisted
additions. Only new Markdown under `aides/` is permitted. It verifies the
completed preparation identity, unchanged existing files, unique IDs/anchors,
unit ownership, answer/question agreement, and precise local course references.
The validator does not write notes or decide semantic matches. A bundled
scratch reviewer reuses its checks on an in-memory overlay, then emits exact
proposal text and a hash manifest outside the chapter. It refuses overwrites
and duplicate new question targets.
Failed scratch checks require draft repair and a new proposal attempt before
approval; unavailable checks leave a proposal unvalidated and block persistence.
After explicit approval, the host copies only approved bytes; the reviewer
verifies the original baseline, recorded manifest hash, unchanged preview and
exact persisted file set/bytes. Only the required `aides/` directory may be
new; unrelated empty directories are rejected too. Hashes are integrity
evidence, never authorization.

Large selections may use bounded independent workers for disjoint scratch
batches. Consolidation, complete question coverage and semantic review remain
the host's responsibility. Hints follow distinct reasoning decisions without
fixed counts. Explanations unpack supplied computations, domains, hypotheses
and omitted transitions, citing relevant course concepts at use.
Each individual hint/explanation has its own precise course reference, not just
shared mappings or another callout's citation. Elementary transitions stay
inside the course-supported reasoning they develop, rather than unsupported
standalone callouts or artificially cited ones. The cited block/section must
actually contain the supporting content; resolving an anchor on a title is
not enough.

Pedagogical correctness remains the agent's responsibility; ambiguous matches or
genuinely inconsistent supplied mathematics require a user decision, not silent
repair. Supported omitted eventual ranks or uniform bounds may be explained
without declaring a compressed valid proof false. Under an explicit user
hints-only policy, flag genuine contradictions/missing support and omit the
correction link and explanation. List questions with no supported aid.
Existing aid notes are immutable in this additive increment; do not recapture a
baseline to hide edits.

The validator is self-contained with its own direct runtime dependencies. It
requires a prepared Import artifact, not Import runtime code or installation.
No external learning sources, embedded model, cloud service, or repository
specific runtime knowledge is required.
Optional read-only Obsidian checks may confirm real navigation, but are not a
runtime dependency or a substitute for mathematical review. Callout folding and
portable newlines are supported; display math is separated from prose so real
course links remain parsed outside math/code.

Generate consumes current document-internal units and these aids under
ADR-0006. It requires neither this validator nor its comparison baseline:
supplied answers reveal inline, while hints/explanations and precise course
links use the side panel. Existing legacy archives are not supported or migrated.

Keep tests outside skills in `tests/clew_enrich/`, with independently authored
synthetic prepared-document fixtures. Update all affected portable contracts,
examples, project documentation, compatibility claims, and the ADR index.

## Consequences

- Stable document and block addresses support aids without splitting or editing
  the imported source documents.
- Generated learning prose remains separate and distinguishable from supplied
  course/exercise/correction content.
- Scratch checks and approved-byte verification make exact-prose review
  reproducible without granting edit permissions or generating learning prose.
- Import preparation evidence is retained unchanged and local baselines remain
  comparison evidence, not permission tokens or revision history.
- Generate can publish current units with or without these optional aids;
  legacy archives are not migrated.
- Existing human aids are preserved. Aid revisions, broader enrichment,
  generated answers/exercises, and revision history remain outside this scope.
