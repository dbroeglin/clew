---
title: "ADR-0004: Compact learner memory and hosted processing"
status: "Proposed"
date: "2026-09-19"
authors: "Francesco Kruk (originating maintainer)"
tags: ["architecture", "decision", "learner-model", "privacy", "skills"]
supersedes: ""
superseded_by: ""
---

# ADR-0004: Compact learner memory and hosted processing

## Status

**Proposed** | Accepted | Rejected | Superseded | Deprecated

Proposed on 2026-09-19 from Francesco Kruk's learner-model 3.0.0 redesign and
incorporated into this repository at the integrating maintainer's direction.
The implementation request does not constitute lifecycle acceptance.

## Context

Clew needs useful learner continuity without requiring an unimplemented graph
of concepts, misconceptions, preferences, goals, provenance events, numerical
confidence, efficacy, decay, and review schedules. The preceding specification
described that advanced model in detail, but supplied neither its storage engine
nor complete update algorithms. Several writes therefore depended on unresolved
schema, posterior, tombstone, scheduling, and efficacy rules.

Learner records are stored in a local external vault, but ordinary use occurs
through hosted GitHub Copilot. Local file storage does not create a local-only
inference boundary: task-relevant file contents returned to the agent can enter
hosted model context. The runtime must disclose that boundary honestly while
limiting retrieval and prohibiting bulk or unrelated access.

Reusable course-reading and learner-memory skills need one immutable source of
truth. Generated deployments in this repository must not be edited as if they
were source packages.

## Decision

Adopt Francesco Kruk's learner-model 3.0.0 compact learning-memory contract.
Keep one active `model/learner.md` summary, identified by exactly one
`<!-- clew-learning-memory: v1 -->` marker, plus meaningful dated notes under
`model/sessions/` and optional useful work under `artifacts/`. Store an original
attempt once and link to it. Goals, confirmed preferences, and learning notes
are readable optional sections rather than typed record schemas.

Only meaningful learning input, decisions, or results justify a memory update.
Bare continuation, recall, and inspection are read-only. Do not infer mastery,
diagnosed misconceptions, standing preferences, numerical confidence or
efficacy, automatic schedules, domain taxonomy, or successful outcomes.

Resolve an explicitly configured existing vault outside the repository clone.
Configuration records only its canonical location, does not create a vault or
learner records, and does not establish ownership of existing `model` or
`artifacts` paths. Unknown and earlier learner-model formats require an explicit
migration decision; they are never silently converted.

Permit bounded, task-relevant learner context to be processed by hosted Copilot
without an additional per-workspace opt-in ceremony. Disclose that local storage
is not local-only inference. Never bulk-upload the vault, collect passive
telemetry, access unrelated learners, publish records, grant institutional
access, or promise provider retention, deletion, training, encryption, or a
complete network audit. Local correction or deletion cannot erase context
already sent to a host.

Consume the matching `learner-model` and `course-content` packages from
`francesco-kruk/clew-skills` revision
`d4e0880642b0870857749978417cb9561487626a` through APM 0.28.0. The deployed
skills and their contracts are generated artifacts; their canonical sources
remain in `clew-skills`.

## Consequences

### Positive

- **POS-001**: The supported model is small enough to operate transparently
  with ordinary Markdown and conservative file tools.
- **POS-002**: Meaningful-write gating avoids manufacturing evidence or noisy
  sessions from configuration, recall, or generated practice.
- **POS-003**: Hosted-processing disclosure accurately describes the runtime
  boundary while bounded retrieval limits unnecessary exposure.
- **POS-004**: Immutable APM pins keep course reading and learner memory on a
  matching release and eliminate competing maintained copies.

### Negative

- **NEG-001**: The compact model does not provide typed graph queries,
  numerical mastery estimates, automatic scheduling, or measured adaptation
  efficacy.
- **NEG-002**: Relevant private content can leave the machine during hosted
  use, and local deletion cannot recall previously transmitted context.
- **NEG-003**: Existing advanced or unfamiliar models require an explicit
  migration decision before writes.
- **NEG-004**: Skills remain instructions rather than a transactional storage,
  access-control, or network-audit backend.

## Alternatives Considered

### Retain the advanced learner graph

- **ALT-001**: **Description**: Keep domain-indexed concepts, misconceptions,
  preferences, goals, JSONL provenance, confidence, efficacy, and schedules as
  the active runtime contract.
- **ALT-002**: **Rejection Reason**: The repository does not implement the
  required inference, scheduling, tombstone, or transactional machinery, so
  many ordinary writes remain blocked or invite invented policy.

### Require local-only processing

- **ALT-003**: **Description**: Prevent a hosted agent from reading private
  learner records and send only serialized adaptation decisions.
- **ALT-004**: **Rejection Reason**: No local inference and redaction backend
  exists, and the rule would prevent the requested hosted Copilot workflow.

### Copy generated skills into this repository as first-party sources

- **ALT-005**: **Description**: Continue editing deployed skill files and the
  repository specification independently.
- **ALT-006**: **Rejection Reason**: Multiple sources of truth drift and bypass
  APM's immutable dependency, lockfile, and license tracking.

## Implementation Notes

- **IMP-001**: Configure an absolute existing external vault with
  `python -m src.vault.cli configure --vault PATH`; keep `.clew.local.json`
  ignored and provide a read-only `status` command.
- **IMP-002**: Configuration must not read course or learner-file contents,
  initialize Git, create learner records, or silently adopt reserved paths.
  Add private-path ignore rules only after checking for already tracked content.
- **IMP-003**: Replace the advanced repository specification with a pointer to
  the pinned package contract, and update README and agent instructions so no
  active documentation promises unsupported graph behavior.
- **IMP-004**: Restore generated skill files through APM rather than manual
  edits. Preserve both `copilot` and `agent-skills` targets, immutable pins,
  lockfile hashes, line endings, and bundled licenses.
- **IMP-005**: Validate configuration and documentation with synthetic data
  only. Do not use real learner records in tests or external evaluation.

## References

- **REF-001**: [Francesco Kruk's integration commit](https://github.com/francesco-kruk/clew/commit/df92d5c7acae8852fa08d926e0a12c163102e7d3).
- **REF-002**: [Original local learner-storage ADR](https://github.com/francesco-kruk/clew/blob/df92d5c7acae8852fa08d926e0a12c163102e7d3/docs/adr/adr-0003-local-learner-storage-and-hosted-copilot-processing.md).
- **REF-003**: [Original learner-continuity ADR](https://github.com/francesco-kruk/clew/blob/df92d5c7acae8852fa08d926e0a12c163102e7d3/docs/adr/adr-0005-evidence-first-learner-continuity.md).
- **REF-004**: [Pinned learner-model source](https://github.com/francesco-kruk/clew-skills/tree/d4e0880642b0870857749978417cb9561487626a/skills/learner-model).
- **REF-005**: [Illustrated learner-model guide](../LEARNER_MODEL.md).
