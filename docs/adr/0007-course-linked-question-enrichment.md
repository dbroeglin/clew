# ADR-0007: Course-linked question enrichment

- Status: Accepted
- Date: 2026-10-04

> Later refinement: [ADR-0008](0008-exercise-unit-pipeline-contract.md)
> fixes source exercise/correction units and checks supplied-answer ownership.
> Question-scoped help notes remain auxiliary additions, not source units.

## Context

[ADR-0001](0001-document-processing-pipeline.md) separates faithful Ingest,
optional Enrich, and repeatable Generate.
[ADR-0006](0006-current-note-offline-html-generation.md) already publishes
optional question-addressed help notes, but does not define an Enrich
implementation or supplied-answer explanations. This record implements that
first enrichment scope and refines Generate without superseding either stage
boundary.

The first Enrich increment should be deliberately small: question-specific
hints and explanations of supplied answers, both linked to existing course
passages. Real current-note worksheets can have ordinary exercise headings,
numbered lists, shared instructions, and multiline mathematics in long notes.
Line-range mappings were considered, then rejected in favor of stable anchors.

## Decision

Add portable `clew-enrich`. The host agent reads current selected notes, chooses
boundaries and course/answer mappings, previews the concrete edits, obtains
approval, and authors them using normal file-editing tools. No enrichment
writer, embedded model, external service, or approval-hash framework is added.

Reuse existing question/answer anchors. When absent, add structural
`question`/`reponse` callouts, stable anchors, and explicit answer `question::`
links while preserving supplied text. Keep teaching additions in separate
`aides/` notes with `type: help`, question links, and supplied-answer links for
explanations. Ordered anchored `hint` and `explanation` callouts contain precise
course heading/block links. Missing answers remain missing.

A local validator captures a pre-edit baseline in host scratch storage outside
the chapter and repository, then checks the persisted result. Compare supplied
content after removing only documented structural wrappers/fields/separators;
retain formulas, source blank lines, indentation, numbering, and shared context.
Check file/directory inventory, immutable files, unique IDs/anchors, answer/question
agreement, and precise course targets. Existing aid files are immutable in this
additive increment. The baseline is local comparison evidence, not a permission
token, publishing artifact, revision ledger, or attestation.

The validator is self-contained and has its own direct runtime dependencies.
Enrich does not require Import, Ingest, or Generate to be installed. Pedagogical
correctness still requires agent review; ambiguous matches or inconsistent
supplied mathematics require a user decision, not silent repair.

Extend Generate's existing convention to explanations matched to selected
supplied answers. Hints and explanations use its side panel; supplied corrections
remain inline. Course links authored in aids open the exact referenced passage
in the side panel, even when the course is also selected for reading.
Keep HTML-first templates, offline publication, and source-note immutability
during Generate. No guided steps or new navigation framework.

Keep tests outside skills. Use a compact independently authored English chapter
with ordinary baseline notes and an enriched overlay. Private material is not
copied into fixtures. Update the affected skill contracts and documentation.

## Consequences

- Stable links survive unrelated line insertions without a mapping ledger.
- Enrich changes source-note structure, not supplied teaching content; generated
  prose remains separate and identifiable.
- Ingest's exact-snapshot validator intentionally reports later edits/new aids.
  Do not change it or rewrite `ingest.json` to hide the new stage.
- Generate still reads current notes without earlier-stage validation or hashes.
- Existing human aids are preserved. Aid revisions, broader enrichment,
  generated answers/exercises, and revision history remain future decisions.
