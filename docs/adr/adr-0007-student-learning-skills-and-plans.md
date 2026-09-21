---
title: "ADR-0007: Student learning skills and Markdown study plans"
status: "Proposed"
date: "2026-09-20"
authors: "Dominique Broeglin (human stakeholder); GitHub Copilot (draft)"
tags: ["architecture", "decision", "skills", "learning", "plans"]
supersedes: ""
superseded_by: ""
---

# ADR-0007: Student learning skills and Markdown study plans

## Status

**Proposed** | Accepted | Rejected | Superseded | Deprecated

Proposed on 2026-09-20 following the developer's request for a plan covering
study planning, synthesis, active recall and attempt repair. The developer
confirmed the minimal interactions documented below. That agreement and the
request to prepare for a later fleet run do not constitute ADR lifecycle
acceptance, implementation authorization, or permission to use a real vault.

Later on 2026-09-20 the developer separately requested "implement all 4 skills
in parallel". Implementation is recorded in REF-001; this record remains
Proposed because no lifecycle acceptance was requested.

## Context

Clew already provides bounded course reading, a minimal read-only course reader,
compact learner memory and explicitly activated tutor capture. It lacks focused
student workflows that turn course content into a study plan, concise revision
cards, recall practice and feedback on an actual attempt.

The developer requested study plans in `./Learning/Plans` within Obsidian, with
TODO checkboxes. This introduces a personal output location outside the pinned
learner-model contract's `model/` and `artifacts/` roots. The capture reporter
currently accepts persisted paths only under those two roots. Treating a plan
as another memory root would change a contract that must remain upstream-owned.

The developer values simplicity and maintainability, has a non-Git vault, and
approved chat-first instruction skills with no additional packages, plugins,
services, UI or tracking system. Checkbox state must not become a proxy for
demonstrated understanding.

## Decision

- **DEC-001**: Add four first-party skills named `study-plan`, `synthesise`,
  `active-recall` and `repair-attempt`. Follow the local first-party skill
  pattern while leaving APM-generated packages and immutable pins untouched.
  Reuse installed course-content, learner-model and Obsidian Markdown
  instructions rather than creating another framework or dependency.
- **DEC-002**: Keep the interaction in chat. Synthesis produces concise,
  source-linked cards in chat and saves them together in one `artifacts/`
  Markdown note only on request. Recall asks one unanswered question at a
  time. Repair starts from actual work, offers a focused hint and waits for a
  retry; explicit requests for full answers remain supported.
- **DEC-003**: Save requested study plans as ordinary Markdown at
  `<configured-external-vault>/Learning/Plans/`. This is a first-party work
  product location, not a change to the learner-model schema. Use actionable
  TODOs and course links, with dates only when requested. Do not add task IDs,
  a plan database, automatic schedules, progress scores or reminders.
- **DEC-004**: Students may edit plans in Obsidian. Tutor checkbox changes
  require an explicit request identifying the intended task; observed learning
  activity alone never changes a box. Preserve manual edits and completed tasks
  during unrelated revisions. A checked box does not establish mastery or
  authorize retrospective evidence capture.
- **DEC-005**: Keep plan persistence separate from memory recording. Ordinary
  file operations write plans with bounded access, ownership checks, collision
  handling, read-before-edit and read-back verification. Do not report plan
  paths through capture completion or duplicate plans into artifacts to make
  them fit. Genuine learner goals, decisions and attempts remain eligible for
  the existing tutor/learner-model workflow under its unchanged rules.
- **DEC-006**: The tutor remains the owner of activation, prompt disposition
  and capture completion. Skills do not start episodes or create competing
  writers. Course-only synthesis does not require memory reads; relevant
  history is recalled only when needed and authorized. Preserve original
  attempts and distinguish assistance from independent results.
- **DEC-007**: Introduce no new runtime, development, system or service
  dependencies, including transitive packages. Use existing tools and synthetic
  fixtures for evaluation. No course-reader or capture-extension changes are
  required by this design; an implementation finding that requires them must
  return for discussion.
- **DEC-008**: Target the agreed non-Git vault without creating Git metadata or
  modifying Git policy. Preserve existing `model/` and `artifacts/` safeguards.
  They do not cover `Learning/Plans/`; if a future plan destination is
  Git-managed, pause its write for an explicit privacy/tracking decision rather
  than claiming existing protection or silently adding ignore rules.

## Consequences

### Positive

- **POS-001**: Four focused workflows reuse current content and memory
  capabilities without additional infrastructure or UI.
- **POS-002**: Plans are readable and directly editable in Obsidian using
  standard Markdown checkboxes.
- **POS-003**: Separating work products from observed learning avoids inventing
  mastery, evidence or a second tracking system.
- **POS-004**: Disjoint first-party skill directories allow parallel
  implementation with a single coordinator for shared integration.

### Negative

- **NEG-001**: Instruction-based behavior requires conversational evaluation;
  static validation cannot prove source fidelity or effective tutoring.
- **NEG-002**: Ordinary file operations are non-transactional and cannot promise
  race-proof updates. Conflicts and partial writes require honest reporting.
- **NEG-003**: Plans add a documented output path outside existing memory roots;
  future Git-managed vault support needs a separate privacy decision.
- **NEG-004**: No dedicated flashcard UI, automatic reminders, automatic task
  completion or global progress overview is included.

## Alternatives Considered

### Put all personal outputs under artifacts

- **ALT-001**: **Description**: Store plans alongside cards and other work
  under the existing `artifacts/` root.
- **ALT-002**: **Rejection Reason**: This would not satisfy the developer's
  explicit `Learning/Plans/` requirement. Keep artifacts for requested saved
  cards and other existing work products instead.

### Add a plan/card plugin, canvas or scheduling service

- **ALT-003**: **Description**: Provide specialized controls, task metadata,
  automatic review dates and a stateful runtime.
- **ALT-004**: **Rejection Reason**: Adds unneeded UX, dependencies and upkeep
  when ordinary chat and Markdown deliver the agreed first experience.

### Extend the learner-model and capture schemas with plans

- **ALT-005**: **Description**: Add a plan target, plan recording requests and
  synchronized task state to the capture pipeline.
- **ALT-006**: **Rejection Reason**: Conflates generated work with evidence,
  expands an upstream-owned contract and creates coordination machinery that
  explicit file edits do not need.

### Use one large learning skill

- **ALT-007**: **Description**: Put planning, synthesis, recall and repair in a
  single instruction file.
- **ALT-008**: **Rejection Reason**: Distinct entry intents and evaluation cases
  are clearer in four small skills. Share existing grounding and memory
  contracts through references rather than building a new shared framework.

## Implementation Notes

- **IMP-001**: Follow the [implementation plan](../plans/student-learning-skills.md).
  Freeze common contracts and fixtures first; implement the four skill
  directories in parallel; integrate shared agent/docs/tests once afterward.
- **IMP-002**: No migration is proposed. Leave existing notes, imported teacher
  content, memory and artifacts where they are. Resolve only the configured
  external vault and selected task destinations.
- **IMP-003**: Use synthetic disposable vaults to test file boundaries,
  checkbox edits, collisions, answer withholding, faithful synthesis and
  evidence-grounded repair. Pair representative with-skill and baseline
  conversations and obtain human review of the resulting outputs.
- **IMP-004**: Update active repository guidance to explain the new plan output
  path without editing historical ADRs or the installed learner-model contract.
  Any newly discovered UX, dependency or storage requirement is a review gate,
  not autonomous fleet scope.
- **IMP-005**: Retain the current hosted-processing disclosure and bounded
  retrieval rules. Local notes are not a local-only inference guarantee; no
  new telemetry, external publication or real-learner evaluation is proposed.

## References

- **REF-001**: [Student learning skills implementation plan](../plans/student-learning-skills.md).
- **REF-002**: [ADR-0004: Compact learner memory and hosted processing](adr-0004-compact-learner-memory-and-hosted-processing.md).
- **REF-003**: [ADR-0005: Explicit tutor sessions and local evidence capture](adr-0005-explicit-tutor-sessions-and-local-evidence-capture.md).
- **REF-004**: [Learner-model guide](../LEARNER_MODEL.md).
- **REF-005**: [Course-content skill](../../.agents/skills/course-content/SKILL.md).
- **REF-006**: [Learner-model storage contract](../../.agents/skills/learner-model/references/learner-model-spec.md).
- **REF-007**: [Capture result path contract](../../.github/extensions/clew-tutor/recording.mjs).
- **REF-008**: [Existing first-party skill pattern](../../.agents/skills/ingestion/SKILL.md).
