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

Enrich and Generate remain separate skills. Their current implementations
consume legacy exercise-per-note content; support for the new document-internal
units is deferred. Do not claim new-format end-to-end publication works yet.
Current notes are authoritative for learning/editing; HTML remains derived.
Retain immutable conversion evidence and preparation baselines.

PDF is the only implemented conversion input. No preparation OCR repairs,
generated exercises/answers, inferred prerequisites or migration of archives.
Detailed conversion rules are in ADR-0002/0005/0009/0010/0011;
preparation in ADR-0004 and unit identities in ADR-0008.

## Consequences

Users invoke one import skill without forcing a reconversion. Source storage
is independent of learning-unit presentation. Consumer refactors can follow
without changing or splitting archived source documents.
