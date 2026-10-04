# ADR-0000: Record architecture decisions

- Status: Accepted
- Date: 2026-10-04

## Context

Clew needs a durable record of significant architecture decisions, their
constraints, and their rationale. Code and commit history alone do not reliably
explain why an approach was chosen or which alternatives were considered.

AI agents also need to discover relevant decisions without loading the entire
decision history into their context. Guidance should use progressive disclosure:
a short entry point, a scannable index, and detailed records opened as needed.

## Decision

We use architecture decision records (ADRs) for significant decisions affecting
the system's structure, dependencies, interfaces, data, or quality attributes.
Routine implementation details do not require an ADR.

Store ADRs as version-controlled Markdown files in `docs/adr/`. Use a
four-digit, sequential identifier and a descriptive kebab-case filename:
`0000-record-architecture-decisions.md`, followed by `0001-<decision-title>.md`.
Identifiers are stable and must not be reused.

Use the lightweight Context / Decision / Consequences format demonstrated by
this record. Each ADR includes its identifier and title, status, and date.
The context describes the problem, constraints, and relevant alternatives; the
decision records the chosen approach; the consequences capture benefits,
tradeoffs, and follow-up obligations.

Maintain `docs/adr/README.md` as the ADR index. A README in the ADR directory is a
conventional Markdown entry point, browsable directly in GitHub without extra
tooling. List every ADR in ascending numeric order with its identifier, linked
title, status, and a short summary. Update the index in the same change as a new
ADR or a status transition.

Use this discovery path for progressive disclosure:

1. Root `AGENTS.md` points AI agents to the index and tells them to read only
   relevant records.
2. The index exposes enough metadata to select relevant decisions.
3. Individual ADRs provide the detailed context, rationale, and consequences.

New ADRs start as Proposed and become Accepted when agreed upon, or Rejected if
not adopted. Keep accepted decisions as historical records rather than rewriting
their rationale to reflect a different choice. If a decision changes, add a new
ADR, mark the old one Superseded, and link both records to each other and from the
index. Use Deprecated when a decision no longer applies and has no replacement.
Clarifications and factual corrections may be made to existing records without
changing their original intent.

## Consequences

Decisions and their rationale stay close to the code and can be reviewed in the
same workflow. Contributors and AI agents can find applicable constraints
quickly while keeping initial guidance and context usage small.

The index is maintained manually, so every ADR addition or status change carries
an explicit obligation to keep it accurate. This avoids introducing generation
tooling while the decision history is small.
