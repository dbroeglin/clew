# ADR-0001: Document processing pipeline

- Status: Accepted
- Date: 2026-10-04

## Context

Clew needs faithful editable source documents, optional distinguishable learning
aids and repeatable publication. File splitting introduces fragile source
coverage and matching decisions.

## Decision

Use one portable `clew-import` skill with two resumable steps:
PDF conversion into retained bundles, then deterministic whole-document
Obsidian preparation. Keep one complete note per PDF beside its PDF and figures.
Preparation adds structure/anchors/links without regenerating source text.
Conversion and local preparation have separate concrete approvals.

Enrich and Generate remain separate skills with different input contracts.
Enrich optionally consumes completed whole-document chapters, using
document-internal exercise/correction units and stable question/answer anchors;
it writes new help notes without changing imported documents. Generate remains
a legacy exercise-per-note consumer. Do not claim whole-document HTML
publication or end-to-end new-format output works yet. Current notes are
authoritative for learning/editing; HTML remains derived. Retain immutable
conversion evidence and preparation baselines.

PDF is the only implemented conversion input. No preparation OCR repairs,
generated exercises/answers, inferred prerequisites or migration of archives.
Detailed conversion rules are in ADR-0002/0005/0009/0010/0011;
preparation in ADR-0004 and unit identities in ADR-0008.

## Consequences

Users invoke one import skill without forcing a reconversion. Source storage
is independent of learning-unit presentation. Enrich can use prepared unit
anchors without changing or splitting source documents; Generate's document
consumer and archive migration remain separate future work.
