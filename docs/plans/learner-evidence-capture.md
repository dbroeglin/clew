# Learner evidence capture implementation plan

**Status:** Architecture accepted (ADR-0005, 2026-09-20); implementation in progress - P1 synthetic-data spike complete, P2-P6 pending.
**Human stakeholder:** Dominique Broeglin.
**Architecture:** [Accepted ADR-0005](../adr/adr-0005-explicit-tutor-sessions-and-local-evidence-capture.md).

ADR-0005 is accepted and implementation has begun with the synthetic-data
spike (P1). Building the runnable feature beyond that spike, and permission to
use a particular learner vault, remain separate decisions. The work so far
changes neither the pinned learner-model contract nor any private learner
records, and the spike processes synthetic data only.

This plan builds on the compact learner-model 3.0.0 contract merged in PR #4 and
proposed in
[ADR-0004](../adr/adr-0004-compact-learner-memory-and-hosted-processing.md),
which remains Proposed. It
targets only the GitHub Copilot App integration that turns explicit learning
sessions into compact memory; it does not redefine the memory format, add a
storage engine, or re-decide the hosted-processing boundary.

Key sections: [capturable activity](#capturable-activity),
[recording through the installed skill](#recording-through-the-installed-skill),
[delivery sequence](#delivery-sequence) and
[acceptance scenarios](#acceptance-scenarios).

## Intended outcome

Learners explicitly enter a Clew Tutor session and then learn through chat and a
tutor-owned canvas without having to request that each interaction be saved.
Both surfaces feed one local App capture layer. Copilot interprets relevant
context; the tutor agent, following the installed learner-model skill, performs
the meaning-gated Markdown edits, while local code correlates the same work
across surfaces and observes whether it was recorded. The App layer orchestrates
and observes; it is not itself a writer.

The recorded memory is exactly what the compact contract defines: one readable
`model/learner.md` summary, meaningful dated `model/sessions/YYYY-MM-DD-topic.md`
notes, and optional `artifacts/`. The App layer adds no observation types,
identifiers, numerical scores, schedules or domain taxonomy, and it introduces
no new writer - every write goes through the installed skill, which is pinned
from `clew-skills` and must not be edited here.

The authoritative memory stays in the learner's configured external vault.
Bounded, task-relevant context may be processed by GitHub Copilot under the
ADR-0004 boundary, without a per-workspace opt-in and without claiming zero
remote retention. Automatic backups, cross-device sync, passive telemetry and
capture from unrelated conversations remain outside this work.

The first complete integration should demonstrate both capture paths writing
correct compact memory, recording the same work once, and supporting learner
inspection and correction. Because the contract is instructions over
conservative, non-atomic file edits, completeness rests on the App layer's
discipline and the learner's ability to inspect and correct, not on a
transactional guarantee.

## Current baseline

- The repository contains the compact learner-model and course-content skills,
  pinned from `clew-skills` through APM, plus a read-only course-reader
  extension. It has no App capture layer.
- The learner-model 3.0.0 contract is delivered as the installed
  [specification](../../.agents/skills/learner-model/references/learner-model-spec.md),
  [clarification gates](../../.agents/skills/learner-model/references/clarification-gates.md)
  and [operational skill](../../.agents/skills/learner-model/SKILL.md). It is a
  set of agent instructions over conservative file tools, not a transactional
  storage, access-control or network-audit backend.
- [docs/LEARNER_MODEL.md](../LEARNER_MODEL.md) is now a pointer to that pinned
  contract; the earlier advanced, evidence-first specification and its numbered
  sections no longer apply.
- A vault configuration tool exists at `src/vault` (`python -m src.vault.cli
  configure --vault PATH` and `status`). It only remembers an existing external
  vault's location and protects reserved `model`/`artifacts` paths; it never
  reads or creates learner memory.
- The installed SDK exposes agent selection state/events, extension tools,
  session events and canvas provider APIs. App behavior, version support and
  reliable replay have not been demonstrated.
- ADR-0001 is still Proposed. Installing its skill is not architectural
  acceptance.
- [ADR-0002](../adr/adr-0002-copilot-app-extension-ux.md) is also Proposed.
  Preserve the existing reader's minimal UX and read-only course boundary.
  Selecting a passage and staging an Ask in chat attachment are not learner
  input or permission to write memory. This plan does not add recording controls
  to the course reader.

## Contract and approval gates

Resolve these before implementing their dependent behavior. A missing decision
must not cause meaningful learner activity to be silently dropped, but must
prevent an unsupported or ambiguous write. Record resolutions in the App layer's
own documentation or a further ADR where the decision is architectural; the
memory contract itself is changed only upstream in `clew-skills`.

| Gate | Required decision | Blocks |
| --- | --- | --- |
| G0a - Architectural disposition | Explicit, dated human acceptance or rejection of ADR-0005 through the ADR process. Produced by the P0 review, not a precondition of it. | Committing to the App-integration architecture and unblocking G0b. |
| G0b - Implementation authorization | A separate implementation/spike request, with real-vault access separately scoped. | Implementation and private-data rollout. |
| G1 - Processing and disclosure | App-specific context minimization and one-time honest disclosure within the ADR-0004 boundary: what bounded context a capture step may send, and the wording of the disclosure. No per-workspace opt-in and no network-audit claim are introduced. | Sending any learner context for hosted interpretation. |
| G2 - Capture contract | What chat or canvas activity is a meaningful write versus read-only; how the summary versus a dated session is chosen; cross-surface correlation so the same work is recorded in one place where correlation succeeds; and what is never learner input. | A shared, testable capture contract. |
| G3 - Episode lifecycle | What proves human activation; start, pause, resume and end; treatment of already-recorded and pending work after pause, reload or restart; binding to the learner, configured vault and source context; and an explicit ownership/migration decision for an existing nonempty `model/` before any capture write. | Reliable automatic capture. |
| G4 - Completion and honest failure | How the App detects that a meaningful interaction was not recorded or a write failed; how a non-atomic partial write is reported; and the inspectable "was this recorded" signal. | A claim that capture reliably persists eligible activity. |
| G5 - App dependencies and packaging | The extension entry surface, supported App/SDK versions, and any added runtime or development dependency with its transitive footprint, agreed under AGENTS.md. | Adding execution or spike dependencies. |

For G1, follow the ADR-0004 boundary as merged in PR #4; do not restate or re-gate it
here. The App layer's job is to minimize what a given step sends and to disclose
honestly, not to add a second processing policy.

For G2 and G4, use the installed
[clarification gates](../../.agents/skills/learner-model/references/clarification-gates.md)
and the contract's meaningful-write rules as the starting point. Do not
reintroduce observation types, scores, schedules or a tombstone engine to make a
capture case fit; the compact contract does not support them.

## Capturable activity

Capture writes only the compact memory the contract defines, and only for
genuine learning activity. A path, a bare "continue", recall and inspection are
never writes. The table maps eligible activity to the memory it updates through
the installed skill.

| Learning activity | Deliberate meaning and necessary context | Compact memory it updates |
| --- | --- | --- |
| Stated goal | The learner states a learning goal in their own words. | The summary's Goals, citing the learner's actual statement date; no session required. |
| Confirmed preference | The learner confirms a working condition with explicit future scope, not a one-off request. | The summary's Confirmed preferences, dated; a current-only request shapes the reply but is not recorded. |
| Learning takeaway | An evidence-grounded takeaway from actual work, with its uncertainty. | The summary's Learning notes, linking the dated session that supports it. |
| Attempt and outcome | A real attempt with the learner's answer, any help or feedback actually used, and the actual outcome. | A dated `model/sessions/` note; the original attempt is stored once and linked, not copied across files. |
| Supplied work | Substantial work the learner supplies and it is worth retaining. | An `artifacts/` entry, linked from the session; trivial conversation is not saved as an artifact. |
| Correction or stop-use | The learner corrects a recorded statement or stops using a preference, with scope. | A direct, dated edit to the affected summary item or note; no separate event, ID or overlay. |

### Inputs that are not learner memory

- Assistant answers, generated exercises, injected prompts, quoted course
  content and tool output are context, not the learner's input, even when
  delivered through a user-message-shaped event.
- Agent-invoked canvas actions, view changes and passive editor activity are not
  learner actions; an open canvas is not an evidence producer.
- Bare continuation, recall and inspection make no writes to `model/` or
  `artifacts/`, create no session, and do not touch timestamps.
- Configuration and status operations neither read nor create memory; a
  path-only exchange asks for the learner's goal.

## Recording through the installed skill

- Record memory only by having the tutor agent follow the installed
  learner-model skill's conservative, meaning-gated instructions, exactly as
  delivered. The App layer orchestrates and observes rather than writing memory
  itself; it maintains no second set of write rules and no separate writer, and
  it never edits, forks or shadows the deployed skill. Any change to the memory
  contract goes through `clew-skills` and APM, not an App adapter.
- Apply the contract's meaningful-write gating. Only genuine learning input,
  decisions or results are written; continuation, recall and inspection stay
  read-only.
- Before the first capture write to an existing `model/`, resolve the contract's
  ownership/migration decision. An existing nonempty `model/` without the
  recognized summary, or an unknown or advanced marker, blocks capture writes -
  not course reading - until the learner decides; nothing is silently overwritten
  or migrated.
- Correlate chat and canvas references to the same work so that, where
  correlation succeeds, it is recorded in one authoritative location and linked
  rather than copied elsewhere; correlation is best effort, not an enforced
  guarantee. Keep genuinely distinct attempts distinct even when their answers
  match.
- Track completion on a best-effort basis. Within an active session, surface
  meaningful interactions that were not recorded, and never claim success or a
  transactional rollback the file tools cannot provide. On a partial write,
  report exactly what persisted and stop. Because the App adds no durable backlog
  or writer, a crash, compaction or reload may leave a gap; the readable memory
  and learner inspection are the backstop, not automatic exactly-once recovery.
- Keep hosted processing within the ADR-0004 boundary: send only bounded relevant
  context, never the whole vault, disclose once, and add no opt-in ceremony.
- Keep learner memory out of this repository; it lives only in the configured
  external vault.

The App layer therefore contributes activation, correlation and completion
tracking. It does not advertise an update as supported until that path is
exercised against the installed skill with synthetic fixtures and documented.

## Proposed responsibilities

| Component | Owns | Does not own |
| --- | --- | --- |
| Clew Tutor profile | Tutoring behavior, relevant skill use, grounded course context and proposed takeaways. | Unrestricted memory-file editing or proof that a write succeeded. |
| Episode controller | Authorized learner/vault binding, activation state, source boundaries and visible status. | Inferring consent from arbitrary text or a delegated agent invocation. |
| Chat adapter | Eligible chat takeaways and decisions with their human origin and context. | Treating every `user.message` event as learner input. |
| Canvas adapter | Explicit submissions, hints, proposal responses and intentional revisions with attempt identity. | Treating agent actions, view changes or keystrokes as learning activity. |
| App capture layer | Meaningful-write gating, cross-surface correlation and non-duplication, completion tracking and honest failure reporting. | A new memory format, storage schema, writer or second rule set. |
| Installed learner-model skill (pinned) | The meaning-gated file-editing instructions and the memory contract itself. | Being edited in this repository; it changes only through `clew-skills` and APM. |
| Vault configuration tool (`src/vault`) | Locating the external vault, reserved-path protection and read-only status. | Reading learner content or creating memory. |
| Copilot inference path | Interpretation of the minimum relevant context. | Unbounded vault access or independent authority to write memory. |

These are responsibility boundaries, not a requirement for separate processes or
packages. The extension entry point is constrained by the SDK to its supported
entry surface; the packaging and any test runner remain choices for the
authorized spike and G5 review. Use already approved tooling; discuss any added
runtime or development dependency first, including its transitive footprint.

## Delivery sequence

### P0 - Review the architecture and close the capture contracts

**Dependencies:** Stakeholder availability to record the G0a disposition and the
G1-G5 decisions; not blocked by the G0b implementation authorization, which P0
does not perform.

- Review ADR-0005 against the compact contract through the repository ADR
  process. Keep it Proposed until an explicit, dated human acceptance or
  rejection is recorded. Recheck numbering against other proposed records before
  merging.
- Agree the meaningful-write mapping: which chat and canvas activity updates the
  summary, which writes a dated session, and what stays read-only.
- Agree cross-surface correlation and non-duplication, activation proof, and the
  completion signal for an omitted or failed write.
- Confirm the App layer writes only through the installed skill's file
  operations and edits no deployed skill file.

**Exit:** The capture contracts are reviewable and consistent with the compact
model, with unresolved questions recorded as gates rather than adapter guesses.

### P1 - Prove the host integration with synthetic data

**Dependencies:** Separate spike authorization under G0b; proposed G3 and G4.

- Establish, with synthetic data only, how activation, selection, pause, resume,
  restart and reload actually behave, and whether a canvas provider can deliver
  the learner actions the capture contract needs.
- Prove a completion mechanism: how the App detects that a meaningful
  interaction was not recorded, without inventing a record.
- Record the actual observed capability and its limits; do not assume delivery
  or replay guarantees.

**Exit:** Synthetic capability evidence exists for activation, capture and
completion, with no private-data readiness claim.

### P2 - Implement the App capture layer over the installed skill

**Dependencies:** P1; resolved G1, G2 and G4.

- Implement meaningful-write gating, cross-surface correlation and completion
  tracking that record compact memory through the installed skill's file
  operations. Add no writer, scripts or second rule set.
- Ensure the same work seen through chat and canvas is written once, in one
  authoritative location, and linked elsewhere; keep distinct attempts distinct.
- Return a clear result distinguishing what was recorded, what was read-only, and
  any partial or failed write, reporting exactly what persisted and stopping.

**Exit:** Synthetic chat and canvas activity becomes correct compact memory,
recorded in one authoritative location where correlation succeeds, with omissions
and partial writes surfaced rather than hidden. This is the capture milestone,
not a completed tutoring experience.

### P3 - Add Clew Tutor and automatic chat capture

**Dependencies:** P2; resolved G1 and G3; aligned agent instructions.

- Add a thin custom-agent profile in the standard discovery location. Reuse the
  course-content and learner-model skills. Prefer a narrow capture path through
  prompt and tool discipline, and treat App mediation as observation, not
  enforcement: the profile is not a filesystem sandbox, and generic file tools
  cannot be proven unable to bypass the capture path.
- Start capture at an established human activation after learner/vault setup.
  Show active and paused state; do not import earlier chat history. Use backend
  state checks on every admission, not just prompt wording.
- Distinguish learner statements, goals, corrections and demonstrated outcomes
  from questions, hypothetical examples, quoted course content, assistant claims
  and system or agent injections.
- Implement the best-effort completion mechanism proven in P1. Within an active
  session, keep meaningful interactions that were not recorded visible so the
  learner can complete them. Because the App adds no durable backlog or writer, a
  crash, compaction or reload may leave a gap the learner sees rather than one the
  App recovers exactly once.

**Exit:** An explicitly started tutor chat records eligible activity as compact
memory, ignores non-learner input, and, within an active session, surfaces an
unrecorded meaningful interaction for completion rather than dropping it
silently.

### P4 - Connect one end-to-end learning canvas

**Dependencies:** P3; agreed canvas capture contract.

- Instrument one tutor-owned canvas so explicit submissions, hints, proposal
  responses and intentional revisions are captured with attempt identity, while
  agent-driven actions and passive activity are not.
- Preserve correlation when the learner discusses a canvas answer in chat: the
  discussion can add a takeaway or a correction without creating a second
  recording of the same attempt.
- Show pending, recorded and failed states in the canvas. A model timeout,
  closed window or repeated click must not produce a false success or a duplicate
  session note.

**Exit:** One exercise moves between canvas and chat and is recorded in a single
dated session (with an optional artifact); genuine revisions remain
distinguishable, and pause and retry match the chat path.

### P5 - Expose learner control over the memory

**Dependencies:** P3-P4; resolved G2 correction rules.

- Provide inspection from a summary item to its supporting session and back,
  including why something was or was not recorded, in the learner's language.
- Implement correction, stop-use and scoped local deletion as the contract
  defines them: direct dated edits to the summary or note, marking a preference
  inactive, and deleting only a confirmed local scope while repairing affected
  links. Use the installed skill's conservative edits; add no tombstone engine,
  suppression file or overlay.
- State the scope of forgetting honestly: a dated stop-use instruction is
  honored on later recall and not re-inferred, but neither local edits nor
  deletion can erase context already processed by a host.

**Exit:** The learner can inspect, correct, stop-use and delete within the
compact contract, and unsupported requests are explained rather than faked.

### P6 - Harden and prepare an explicitly authorized rollout

**Dependencies:** P5 and the acceptance scenarios below.

- Exercise lifecycle races, process termination, concurrent sessions, reload,
  unavailable inference, omitted recording and partial writes with synthetic
  fixtures.
- Confirm parity between the chat and canvas paths and the installed skill's
  direct operations against the same fixtures.
- Verify that context sent for hosted interpretation contains only bounded
  approved data, and that capture status, unrecorded backlog and failures are
  visible without becoming a full transcript archive.
- Keep real-vault authorization a separate, explicit gate; synthetic validation
  is not permission to process real learner records.

**Exit:** The integration behaves safely under faults and is ready for a
separately authorized real-vault rollout.

## Acceptance scenarios

| Scenario | Required result |
| --- | --- |
| Developing Clew or using another agent | No capture and no learner-memory retrieval for capture. |
| Explicit tutor activation in an existing chat | Capture begins at the approved boundary, with a known learner and configured vault; earlier messages are not imported. |
| Existing nonempty `model/` without the recognized summary (old, advanced or unknown marker) | Capture writes are blocked pending an explicit ownership/migration decision; course reading is unaffected; nothing is silently overwritten or migrated. |
| Tutor invoked as a delegated subagent | No automatic activation of capture for the parent conversation. |
| Pause, switch away, resume, reload or restart | New capture follows the defined episode state; unrecorded work stays visible for completion within a session rather than being silently lost, though it is not auto-recovered exactly once across a crash or reload. |
| Injection, assistant answer or agent-driven canvas edit | Not recorded as learner memory, even when delivered through a user-message-shaped event. |
| Tool-mediated learner confirmation | Captured with its actual proposal context and human origin, not assumed to be a normal chat message. |
| Same work across canvas and chat, or delivered twice | Recorded in one authoritative location where correlation succeeds; new revisions and genuinely distinct attempts remain distinct; correlation is best effort. |
| Meaningful interaction not recorded, or invalid capture output | Surfaced as unrecorded so it can be completed within the session; no fabricated note or invented outcome; cross-crash recovery is not guaranteed. |
| Copilot unavailable | No claim that interpretation occurred; permitted local recording remains pending with its actual capability recorded. |
| Partial or non-atomic write | Reports exactly what persisted and stops; the memory stays readable and correctable; no false success or transactional-rollback claim. |
| Bare recall, continuation or inspection | No writes to `model/` or `artifacts/`, no new session and no timestamp change. |
| Configuration, status or a path-only exchange | No memory read or creation; the learner is asked for their goal. |
| Correction or stop-use request | A direct dated edit to the affected summary item or note; later recall honors it and does not re-infer the old value. |
| Scoped local deletion | Only the confirmed local files or passages are deleted and affected links repaired; unrelated and shared work is preserved; hosted copies are acknowledged, not claimed erased. |
| Hosted-processing context | Only bounded relevant context is sent, never the whole vault, disclosed once; no zero-retention claim. |
| Editing or forking the deployed skill | Not done; capture uses the installed operations, and contract changes go through `clew-skills` and APM. |
| Missing configuration, consent or SDK capability | Explicitly blocked operation, not a guessed policy or a silent always-on fallback. |

## Reviewable delivery milestones

| Milestone | Deliverable | Completion boundary |
| --- | --- | --- |
| M1 | Approved capture contracts and synthetic host capability evidence. | P0-P1; no private-data readiness claim. |
| M2 | An App capture layer recording inspectable compact memory through the installed skill, with omissions and partial writes surfaced. | P2; no claim of a completed tutoring experience. |
| M3 | Tutor chat and one canvas sharing the capture path and recording shared work once. | P3-P4; non-learner input is ignored and nothing is silently lost. |
| M4 | Learner inspection, correction and stop-use, plus rollout guidance. | P5-P6; explicit real-vault authorization is still required. |

## References

- [Accepted ADR-0005](../adr/adr-0005-explicit-tutor-sessions-and-local-evidence-capture.md)
  records the rationale and alternatives; this document records sequencing.
- [Proposed ADR-0004](../adr/adr-0004-compact-learner-memory-and-hosted-processing.md)
  and the [learner-model contract pointer](../LEARNER_MODEL.md) define the
  compact memory and hosted-processing boundary this plan builds on (merged in
  PR #4; ADR-0004 remains Proposed).
- The installed
  [learner-model 3.0.0 specification](../../.agents/skills/learner-model/references/learner-model-spec.md),
  [clarification gates](../../.agents/skills/learner-model/references/clarification-gates.md)
  and [operational skill](../../.agents/skills/learner-model/SKILL.md) define the
  memory format, meaningful-write gating and file-tool boundaries.
- The [vault configuration tool](../../src/vault/cli.py) locates the external
  vault and protects reserved paths without reading learner content.
- [Proposed ADR-0001](../adr/adr-0001-unified-clew-content-structure.md) and
  [skill management](../../README.md#agent-skills) govern content boundaries and
  APM-pinned dependency handling.
- [Proposed ADR-0002](../adr/adr-0002-copilot-app-extension-ux.md) and
  [collaborative design instructions](../../AGENTS.md#discuss-before-implementing)
  preserve the reader UX and require agreement on new interactions and
  dependency footprints.
- [GitHub custom-agent configuration](https://docs.github.com/en/copilot/reference/custom-agents-configuration)
  and [Copilot SDK](https://github.com/github/copilot-sdk) provide host references;
  the installed SDK evidence and its limitations are recorded in ADR-0005.
