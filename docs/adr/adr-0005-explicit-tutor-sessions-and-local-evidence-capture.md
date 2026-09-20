---
title: "ADR-0005: Explicit tutor sessions and local evidence capture"
status: "Accepted"
date: "2026-09-19"
authors: "Dominique Broeglin"
tags: ["architecture", "decision", "learner-model", "copilot", "capture", "privacy"]
supersedes: ""
superseded_by: ""
---

# ADR-0005: Explicit tutor sessions and local evidence capture

## Status

**Proposed** | **Accepted** | Rejected | Superseded | Deprecated

Proposed on 2026-09-19 following an exploratory discussion with Dominique
Broeglin. The requested outcome is documentation and an implementation plan,
not implementation or formal acceptance. Acceptance requires a separate,
explicit human decision recorded according to the [ADR process](README.md);
acceptance alone does not authorize implementation.

Accepted on 2026-09-20 by Dominique Broeglin (repository maintainer). The same
decision authorized implementation to begin with the synthetic-data spike
(plan P1); real-vault access remains a separate gate that this acceptance does
not grant (REF-008).

This record builds on the compact learner-model 3.0.0 contract merged in PR #4,
and on the direction proposed in
[ADR-0004](adr-0004-compact-learner-memory-and-hosted-processing.md), which
remains Proposed. It does not amend that contract, redefine
the memory format, or re-decide the hosted-processing boundary; it proposes only
the GitHub Copilot App integration layer that produces compact memory from
explicit learning sessions.

## Context

Clew needs to bring deliberate learner interactions from GitHub Copilot App
chat and canvas extensions into the learner's persistent memory. Chat supplies
rich conversational context; a canvas can supply precise exercise, attempt,
hint and proposal-response context. The same piece of work discussed across both
surfaces should be recorded in one place, not written twice.

[ADR-0004](adr-0004-compact-learner-memory-and-hosted-processing.md) already
settled what that memory is. The compact learner-model 3.0.0 contract keeps one
readable `model/learner.md` summary, meaningful dated notes under
`model/sessions/`, and optional `artifacts/`. Goals, confirmed preferences and
learning notes are optional Markdown headings, not typed schemas. Only
meaningful learning input, decisions or results justify a write; bare
continuation, recall and inspection are read-only. The contract permits bounded,
task-relevant learner context to be processed by hosted Copilot without a
per-workspace opt-in, and states plainly that skills are instructions, not a
transactional storage, access-control or network-audit backend.

What ADR-0004 does not address is the App surface itself. It does not say how an
interactive chat session and canvas extensions establish an explicit learning
boundary, how genuine learning activity becomes a compact memory update rather
than noise, how the same attempt seen through two surfaces is reconciled, or how
the runtime behaves when the agent simply forgets to record. Those are
integration questions, and answering them badly would either miss real evidence
or manufacture it.

The compact contract is delivered as the installed
[learner-model](../../.agents/skills/learner-model/references/learner-model-spec.md)
and course-content skills, pinned from `clew-skills` through APM. Those deployed
skills are generated artifacts; their canonical source lives in `clew-skills`,
and they must not be edited as first-party files in this repository. Any change
to the memory contract belongs upstream, not in an App adapter.

An earlier draft of this record targeted the preceding advanced, evidence-first
model - typed observations, misconceptions, numerical confidence, scheduling,
efficacy, provenance identifiers and a script-backed transactional writer. That
foundation was removed when ADR-0004 adopted the compact contract, so this
record is reframed onto the compact model and keeps only the App-integration
core.

## Decision

Use a thin Clew Tutor agent as the explicit learning entry point, with a shared
local App layer that admits, correlates and records deliberate chat and canvas
activity as compact learner memory through the installed skill's file
operations. The App layer adds activation, correlation and completion tracking;
it does not add a new memory format, storage schema or writer.

- **DEC-001**: Make selecting Clew Tutor for the main conversation the proposed
  start action, after an external vault is configured and the learner is known.
  Capture starts at that activation boundary, never by retrospectively importing
  the preceding chat. Invoking the tutor as a delegated subagent is not consent
  to record its parent conversation. If the host cannot establish an explicit
  activation reliably, stop and return an explicit start action for discussion
  rather than treating agent presence as consent.
- **DEC-002**: Keep learning-episode state in the local App layer, distinct from
  Copilot session identity and agent identity. Display capture status and a
  pause control. Switching away from the tutor or pausing stops recording new
  activity. Resolve resume, shutdown and already-pending work semantics before
  implementation; do not infer them from extension process lifetime. Missing or
  ambiguous activation state blocks capture. Status and control placement need
  UX agreement and must not be bolted onto the existing minimal course reader.
- **DEC-003**: Keep the tutor focused on tutoring, course context and proposing
  grounded takeaways. Reuse the installed course-content and learner-model
  skills rather than copying their contracts into the agent prompt. Offer narrow
  memory operations - the skill's conservative, meaning-gated file edits - rather
  than unrestricted learner-file editing. Prompt and tool choices supplement, but
  do not replace, the skill's own rules.
- **DEC-004**: Route chat takeaways and deliberate canvas actions through one
  shared capture path that writes compact memory. Instrument canvas submissions,
  hint requests, proposal responses and intentional artifact revisions
  explicitly. An agent-invoked canvas action is not automatically a learner
  action, and an open canvas is not an evidence producer.
- **DEC-005**: Produce compact learner-model 3.0.0 memory, not a typed graph.
  Capture updates the `model/learner.md` summary (goals, confirmed preferences,
  learning notes) and writes meaningful `model/sessions/YYYY-MM-DD-topic.md`
  notes with `-2`, `-3` collision suffixes, storing an original attempt once and
  linking it, with optional artifacts. Apply the contract's meaningful-write
  gating: only genuine learning input, decisions or results are recorded, while
  continuation, recall and inspection stay read-only and log nothing. Introduce
  no observations, identifiers, numerical scores, schedules, misconceptions or
  domain taxonomy; a single wrong answer is a dated note, not a diagnosis.
- **DEC-006**: Correlate chat and canvas references to the same work so that,
  where correlation succeeds, it is recorded in one authoritative location and
  linked rather than copied elsewhere; correlation is best effort, not an
  enforced guarantee. Keep genuinely distinct attempts distinct even when their
  answers match. Do not treat injected prompts, assistant text, quoted course
  content or tool output as learner input because it appears in the conversation.
- **DEC-007**: Keep authoritative memory in the learner's configured external
  vault, outside this repository clone, and rely on the ADR-0004 hosted-
  processing boundary for interpretation. Do not re-decide or re-gate that
  boundary, and do not add a per-workspace opt-in ceremony. Minimize transmitted
  context, never upload the whole vault, and disclose honestly that context
  already sent for hosted processing cannot be withdrawn or erased by local
  correction or deletion, and that no provider retention or deletion behavior is
  promised. Clew adds no remote authoritative store,
  automatic backup or cross-device sync.
- **DEC-008**: Respect the pinned-skill boundary. Memory is recorded only by the
  tutor agent following the installed learner-model skill's conservative
  instructions, exactly as delivered; the App layer orchestrates and observes
  rather than writing memory itself, and maintains no second set of write rules.
  It does not edit, fork or shadow the deployed skill, and any change to the
  memory contract goes
  through `clew-skills` and APM, not an App adapter. Completion and
  reconciliation behavior lives in the App layer, not in a modified skill.
- **DEC-009**: Track completion and fail honestly. Because the contract is
  instructions over conservative, non-atomic file edits, the App layer tracks
  whether a meaningful interaction was actually recorded, surfaces unrecorded or
  failed writes, and never claims success or a transactional rollback it cannot
  provide. On a partial write it reports exactly what persisted and stops,
  leaving the memory readable and the learner able to inspect and correct it
  directly.

## Consequences

### Positive

- **POS-001**: A named tutor makes the learning boundary understandable and
  separates using Clew from developing or discussing it.
- **POS-002**: One capture path keeps chat and canvas consistent and records
  work discussed on both surfaces once rather than twice.
- **POS-003**: Building on the pinned compact contract (proposed in ADR-0004,
  merged in PR #4) and the installed skill adds no competing memory format,
  storage schema, writer or inference runtime.
- **POS-004**: Local, portable Markdown memory preserves learner ownership and
  stays inspectable and correctable with ordinary tools.

### Negative

- **NEG-001**: Learners must deliberately enter tutor mode. Incidental learning
  elsewhere is not captured automatically.
- **NEG-002**: Hosted processing transmits selected learner content and cannot
  promise provider retention, deletion or a complete network audit. Local
  correction or deletion cannot recall context already sent to a host.
- **NEG-003**: Reliable App capture still requires lifecycle tracking,
  cross-surface correlation, completion detection and an inspectable "was this
  recorded?" signal - real implementation work beyond an agent profile.
- **NEG-004**: The installed SDK's agent and canvas surfaces include experimental
  APIs. Their behavior in the App, particularly around selection, resume and
  reload, must be established before being used as a capture boundary.
- **NEG-005**: Because the memory contract is instructions over conservative
  file edits, not an enforced backend, completeness and non-duplication rest on
  the App layer's discipline and the learner's ability to inspect and correct,
  not on a transactional guarantee. A crash or reload may leave a gap the learner
  sees rather than one the App recovers automatically.

## Alternatives Considered

### Ordinary chat with an explicit start/stop toggle

- **ALT-001**: **Description**: Keep the general-purpose agent and use a separate
  command or control to activate learning capture.
- **ALT-002**: **Rejection Reason**: A named tutor gives a clearer initial mental
  model and a focused instruction and tool surface. A separate explicit start
  control remains a fallback if reliable host activation cannot be established.

### Save only on request, or approve every write

- **ALT-003**: **Description**: Ask the learner to save each useful interaction,
  or present every candidate for approval before it is written.
- **ALT-004**: **Rejection Reason**: The requested behavior is automatic,
  meaning-gated capture within an explicitly started session. Per-write approval
  interrupts tutoring; inspection and correction remain available afterward.

### Revive the advanced evidence graph and a transactional writer

- **ALT-005**: **Description**: Keep the earlier draft's typed observations,
  misconceptions, confidence, scheduling, provenance identifiers and a
  script-backed transactional writer as the capture target.
- **ALT-006**: **Rejection Reason**: PR #4 pinned the compact contract and
  ADR-0004 rejected that advanced graph, and the repository implements no such
  inference, scheduling or transactional backend. Building the App layer against a removed
  foundation would reintroduce the very gaps ADR-0004 closed.

### Fork or edit the deployed skill to add capture rules

- **ALT-007**: **Description**: Add capture and correlation logic directly to the
  installed learner-model skill files in this repository.
- **ALT-008**: **Rejection Reason**: The deployed skills are generated,
  APM-pinned artifacts. Editing them creates multiple sources of truth and
  bypasses APM's immutable dependency, lockfile and license tracking. Capture
  logic belongs in the App layer or upstream in `clew-skills`.

## Implementation Notes

- **IMP-001**: Follow the separate
  [implementation plan](../plans/learner-evidence-capture.md). Review and
  acceptance of this proposal, authorization to implement, and authorization to
  use a particular learner vault are separate gates.
- **IMP-002**: First run an authorized, synthetic capability spike. The installed
  SDK exposes `session.rpc.agent.getCurrent()`, selection and deselection, and
  `subagent.selected` / `subagent.deselected` events. Check root-agent scope and
  the stable returned agent ID; an event name or current selection alone does not
  prove human activation. Verify restart and reload behavior instead of assuming
  delivery or replay guarantees.
- **IMP-003**: The installed extension API supports custom tools, session
  listeners and canvas providers. `createCanvas` exposes agent-callable actions;
  learner UI actions need their own instrumented path. Determine the supported
  App/SDK versions and a reliable capture and completion mechanism in the spike,
  before choosing production dependencies.
- **IMP-004**: Do not edit the APM-generated skills. Align this repository's
  README and agent instructions with the pinned contract rather than adding a
  second specification. Route any memory-contract change through `clew-skills`
  and APM, preserving pinned dependencies, the lockfile and license notices.
- **IMP-005**: Preserve the distinction between shared course concepts and
  private learner memory. ADR-0001 remains Proposed and is not accepted or
  superseded by this record. The merged, Proposed ADR-0002 remains the reader UX
  proposal: selecting a passage or staging a composer attachment is not learner
  input or memory-write authorization.
- **IMP-006**: Validate with synthetic fixtures before any real-vault rollout.
  Cover capture isolation, cross-surface correlation and non-duplication, missed
  recording and its recovery, meaningful-write gating, learner correction and
  data minimization. Do not depend on an end-of-session summary to make a note
  durable.
- **IMP-007**: The implementation plan targets compact memory outputs only -
  `model/learner.md`, dated `model/sessions/` notes and optional artifacts - and
  introduces no observation types, identifiers, scores or command catalogue. All
  memory is written by the tutor agent following the installed skill's
  conservative instructions; the App layer contributes activation, correlation
  and best-effort completion tracking, not a writer. The implementation adds no
  runtime or development dependency and no production writer.
- **IMP-008**: The P2-P6 implementation emits structured semantic recording
  requests and accepts explicit completion reports; it does not add a production
  file writer. A dependency-free reference recorder exists under the extension's
  test directory only, to prove the request contract against disposable
  synthetic compact-memory fixtures.
- **IMP-009**: The first canvas integration is intentionally headless and
  agent-callable. Attempt, hint, proposal-response and revision actions require
  an explicit learner-origin assertion plus source and attempt identities;
  agent invocation alone remains insufficient evidence. A learner-facing
  exercise iframe is deferred rather than silently approximated.
- **IMP-010**: Learner-control tools provide bounded inspection and prepare exact
  correction, stop-use and deletion scopes. Correction and stop-use are applied
  by the tutor agent through the installed skill. Deletion remains prepare-only
  until a separate explicit user confirmation authorizes a destructive action;
  the extension exposes no delete operation.

## References

- **REF-001**: [Clew ADR process](README.md) and
  [ADR template](template.md). No earlier numbered ADR is superseded.
- **REF-002**: [ADR-0004: Compact learner memory and hosted processing](adr-0004-compact-learner-memory-and-hosted-processing.md),
  the [learner-model contract pointer](../LEARNER_MODEL.md), the installed
  [learner-model 3.0.0 specification](../../.agents/skills/learner-model/references/learner-model-spec.md)
  and its
  [clarification gates](../../.agents/skills/learner-model/references/clarification-gates.md).
- **REF-003**: [Proposed ADR-0001](adr-0001-unified-clew-content-structure.md)
  and [repository skill guidance](../../README.md#agent-skills).
- **REF-004**: [GitHub custom-agent configuration](https://docs.github.com/en/copilot/reference/custom-agents-configuration),
  read on 2026-09-19, for agent profiles, invocation controls and tool selection.
- **REF-005**: [GitHub Copilot SDK](https://github.com/github/copilot-sdk).
  Installed SDK material inspected on 2026-09-19 through the extension authoring
  guide: `docs\agent-author.md`, `canvas.d.ts`, `types.d.ts`,
  `generated\rpc.d.ts` and `generated\session-events.d.ts`. These observations
  are not a supported-version or runtime-behavior guarantee.
- **REF-006**: Design discussion with Dominique Broeglin on 2026-09-19:
  Copilot App chat/canvas scope, local persistence with Copilot processing, and
  automatic capture within explicit learning sessions through a thin Clew Tutor
  entry point. This record was subsequently reframed onto the compact
  learner-model 3.0.0 contract adopted in ADR-0004. This is proposal context,
  not a formal acceptance record.
- **REF-007**: [Proposed ADR-0002](adr-0002-copilot-app-extension-ux.md) and
  [collaborative design instructions](../../AGENTS.md#discuss-before-implementing).
  This unmerged capture draft was renumbered to ADR-0005 after rebasing onto
  the PDF ingestion (ADR-0003) and compact learner memory (ADR-0004) work; no
  merged ADR was renumbered or superseded.
- **REF-008**: Acceptance decision recorded on 2026-09-20 with Dominique
  Broeglin, who accepted this record and authorized implementation to begin with
  the plan's synthetic-data spike, real-vault access excluded. This is the
  responsible-human approval required by the ADR process, not a merge or draft.
