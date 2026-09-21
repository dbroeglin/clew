# Student learning skills implementation plan

**Status:** Four skills and integration implemented on 2026-09-20; representative
synthetic evaluation complete, human review and real-vault rollout pending.
**Human stakeholder:** Dominique Broeglin.
**Architecture:** [Proposed ADR-0007](../adr/adr-0007-student-learning-skills-and-plans.md).
**Decision date:** 2026-09-20.

Build four small first-party skills: `study-plan`, `synthesise`,
`active-recall`, and `repair-attempt`. The developer explicitly requested
parallel implementation after reviewing this plan. That request does not
authorize access to a real learner vault or change ADR-0007's Proposed status.

## Agreed experience and boundaries

The developer confirmed these choices during planning:

- Keep v1 simple: four instruction-based skills, chat interaction, ordinary
  Markdown, and no new packages, plugins, services, UI, or tracking backend.
- Save study plans under `Learning/Plans/` relative to the configured external
  Obsidian vault, never relative to the repository or the Obsidian application.
- Use ordinary TODO checkboxes. The student can edit them in Obsidian; the
  tutor may change them only on an explicit request identifying the task.
  Observing completion does not automatically check a box.
- Include course source links in plans. Add dates only when requested; do not
  introduce automatic review schedules or reminders.
- Show synthesis cards in chat. Save one Markdown note under `artifacts/`
  only when requested, rather than creating a file per card.
- Run recall and repair one step at a time in chat. Reuse existing tutor
  capture for meaningful learner activity, not a second recording system.
- The developer's vault is not a Git repository. Do not initialize Git or
  change Git setup as part of this feature.

The new skills themselves are the approved first-party additions. Reuse the
already installed `course-content`, `learner-model`, and `obsidian-markdown`
skills, existing file tools, and current validation tools. No additional direct
or transitive dependency is proposed.

## Existing foundations and implementation constraints

| Existing surface | Reuse |
| --- | --- |
| `course-content` 3.0.0 | Bounded section reads, canonical definitions, source links, exercise identifiers, and fidelity limitations. |
| `learner-model` 3.0.0 | Meaningful goals, attempts, assistance and observed outcomes, plus optional artifacts. |
| `.github/agents/clew-tutor.md` | Explicit learning-session activation and memory recording orchestration. |
| `.github/extensions/clew-tutor/` | Existing capture and completion reporting; no new recording categories. |
| `src/vault/` | Explicit external-vault configuration and existing path/Git safeguards; no new storage service. |
| Local `ingestion` and `clew-import` skills | First-party skill placement under `.agents/skills/`, distinct from APM-generated dependencies. |
| `tests/` and existing skill eval files | Standard-library test patterns and prompt/expected-output/assertion evaluation format. |

Do not modify generated skill directories, APM pins, lockfiles, licenses, or
notices. New first-party skill directories are source, not edits to deployed
upstream packages. Do not add a new Python runtime module, a general workflow
framework, or a shared skill dependency merely to avoid a few instruction lines.
Reference existing contracts rather than copying them into four competing
versions.

The course reader is read-only and course-scoped. It is not a viewer for
`Learning/Plans/` or `artifacts/`. Chat and ordinary Obsidian notes are sufficient
for v1; no reader changes or live App capability assumption is needed.

## Storage and evidence contract

### Study plans are work products, not learner memory

`Learning/Plans/` is a narrowly scoped, first-party output location. It is not
a new learner-model root, course format, evidence store, or automatic scheduler.
Do not move existing artifacts or memory there.

The study-plan skill directly creates or edits the requested plan through
ordinary conservative file operations. It must not pass a plan path as a
`persistedPaths` value to the capture reporter: the current reporter accepts
only `model/` and `artifacts/`. A meaningful learner goal or decision can
separately be recorded by the existing tutor workflow under its existing
contract. Do not duplicate the plan into `artifacts/` to satisfy capture.

Checking a box means that the activity was marked complete. It does not prove
understanding, an independent successful attempt, or mastery. A manually
checked box is not permission to manufacture or retroactively capture learning
evidence.

### Conservative writes

Resolve the configured vault and exact selected course/plan first. Scope reads
to necessary content; do not scan all plans, memory, or the vault. Create
`Learning/Plans/` only when saving the requested plan, not during configure,
status, inspection, or a bare continuation.

Use a short readable course/topic filename. Check for collisions before
creating it; use a numeric suffix for a distinct new plan rather than
overwriting. Updating an existing plan requires identifying that plan. Preserve
student prose and completed boxes unless the requested edit explicitly changes
them. No automatic archival, cleanup, renaming, or deletion.

Inspect existing destination paths before writing; stop on ambiguous ownership,
unsafe aliases, a conflicting file/directory, or unexpected concurrent changes.
Re-read immediately before an edit and verify the saved result and links.
Ordinary file edits are not a transactional writer; report partial persistence
accurately. No automatic rollback or success-shaped fallback.

The non-Git vault is the agreed rollout case. Existing configuration safeguards
for `model/` and `artifacts/` remain unchanged. `Learning/Plans/` is not currently
covered by those Git ignore rules. If a future target vault is Git-managed,
pause before persisting a plan and discuss plan privacy/tracking explicitly;
do not silently claim protection, change ignore rules, or weaken existing
checks. Supporting that case is a separate decision, not fleet scope.

### Memory ownership

The tutor owns activation, prompt disposition and recording completion. The
four skills must not bind a capture episode, impersonate learner input, or
perform a second recording pass. Outside an explicitly active tutor episode,
do not silently activate automatic capture.

Course-only synthesis and fresh planning do not require learner-memory reads.
For requests grounded in prior difficulties, recall only relevant authorized
memory through the installed skill. Read-only recall, an unanswered question,
a generated card, and a proposed solution are not evidence of learning.

## Skill specifications

### 1. `study-plan`

**Entry requests:** "Plan my learning for this chapter", "Help me revise this
course", or "Update this plan's task as complete". Do not trigger for software
project planning.

**Flow:**

1. Establish the selected course/scope and the student's goal. Use already
   supplied constraints; ask one focused question only when necessary. A
   deadline, time budget, or history is not mandatory.
2. Read indexes to select content, then enough relevant sections to ground the
   activities. Preserve source order and declared prerequisites unless the
   requested revision focus justifies a different proposed order.
3. Create a short actionable sequence mixing reading, synthesis, recall and
   attempts as appropriate. Tasks should say what to do, not just "master X".
   They can suggest the other skills without invoking all of them immediately.
4. Save the requested plan to `Learning/Plans/` with unchecked TODOs and source
   links. Do not add a second confirmation ceremony for an already clear save
   request. A request only to discuss a possible plan stays in chat.
5. On explicit completion/update requests, patch only the selected task or
   scope. Asking to show or continue a plan makes no write by itself.

**Minimal illustrative shape** (actual links must resolve in the selected
course; no IDs, database properties, or progress percentages):

```markdown
# Mechanics: understanding forces

Goal: explain the force model and use it in a practice problem.

- [ ] Read [[courses/mechanics/sections/forces#Force model|the force model]].
- [ ] Make a synthesis card for that section.
- [ ] Answer a recall question about the model's assumptions.
- [ ] Attempt the linked course exercise, then discuss any unclear step.
```

**Acceptance:** correct vault-relative destination, actionable source-grounded
tasks, explicit-only checkbox edits, preserved manual work, collision handling,
and no dates unless requested.

### 2. `synthesise`

**Entry requests:** "Make revision cards", "Summarise this section for studying",
or "Make a fiche de synthese". This means concise study notes, not a flashcard
application or a quiz.

**Flow:** read the selected section and necessary linked definitions; produce
a small set of cards in chat, scaled to the requested scope. Each card includes
the central idea, essential definitions/formulas, relevant conditions, a compact
example or trap where useful, a source citation, and a self-check question.
Do not force empty fields where they add nothing.

Preserve notation and important exceptions. Distinguish illustrative generated
examples from source examples. Carry fidelity/missing-source limitations
forward instead of presenting a compressed statement as authoritative.

If the student requests saving, retain the cards together in one readable
Markdown artifact using the installed artifact/Obsidian instructions. Do not
save by default, rewrite teacher notes, or interpret card generation as progress.
Leave a self-check answer for a subsequent request or recall interaction.

**Acceptance:** concise but accurate cards with source links, no dropped
conditions, no unrequested files, and a single artifact on a save request.

### 3. `active-recall`

**Entry requests:** "Quiz me", "Test my recall", or "Ask me about this section".
Do not route a request for a direct explanation into a forced quiz.

**Flow:** choose one grounded question, ask it without the answer, and wait.
After an attempt, give specific feedback and allow a retry or next question.
Use definitions, explanations, contrasts, and small applications as appropriate.
Distinguish teacher answers from independently derived feedback.

Offer hints when requested without treating an assisted answer as independent
performance. Respect requests to reveal an answer, skip, or stop; answer-seeking
does not need an extra consent step. Keep session state conversational, not in
a new queue or database. Save a practice artifact only if explicitly requested.

**Acceptance:** one unanswered question at a time, no premature solution,
source-grounded feedback, honest uncertainty, and no automatic plan-checkbox
updates or numerical mastery scores.

### 4. `repair-attempt`

**Entry requests:** "Where did my solution go wrong?", "Help me fix this answer",
or "Explain the feedback on my attempt". Distinguish this from correcting
stored learner memory or rewriting the authoritative course.

**Flow:** obtain the problem and actual attempt; inspect the relevant source.
Identify the earliest unsupported step that can be established, explain the
local issue, give a small hint, and wait for a retry. Ask about missing working
instead of inventing reasoning. If the attempt is correct, say so.

Provide a full solution when requested. After a correction, offer a nearby
check rather than asserting the problem is permanently fixed. Verify any
generated check and its solution as far as available sources permit; report
unresolved ambiguity rather than invent a reliable-looking exercise.

**Acceptance:** preserve the original attempt, distinguish help from independent
success, do not diagnose a misconception from one error, and do not record a
successful repair before an actual retry demonstrates it.

## Fleet delivery sequence and file ownership

P0-P5 are complete. P1-P4 were implemented in parallel in disjoint directories.
P6's representative synthetic checks are complete; human review and broader
behavioral coverage remain as described below. This document does not authorize
expanding the UX or dependencies.

| Phase | Owner and deliverables | Dependency |
| --- | --- | --- |
| P0 - Freeze scope and fixtures | Coordinator confirms implementation authorization and ADR disposition; prepares one small synthetic course and disposable-vault fixture shared by evaluations. Freeze common contracts from this plan. | Human review of this plan. |
| P1 - Study planning | One worker owns `.agents/skills/study-plan/`: `SKILL.md`, a small plan template if useful, and `evals/evals.json`. | P0 |
| P2 - Synthesis | One worker owns `.agents/skills/synthesise/`: `SKILL.md`, a compact card template if useful, and `evals/evals.json`. | P0 |
| P3 - Recall | One worker owns `.agents/skills/active-recall/`: `SKILL.md` and `evals/evals.json`. | P0 |
| P4 - Attempt repair | One worker owns `.agents/skills/repair-attempt/`: `SKILL.md` and `evals/evals.json`. | P0 |
| P5 - Integration | Coordinator alone updates the tutor's brief routing guidance, README skill documentation, AGENTS storage guidance, learner-model guide boundary explanation, and shared tests. | P1-P4 |
| P6 - Evaluation and handoff | Coordinator runs cross-skill scenarios, reports behavioral evidence and limits, and presents representative outputs for human review. | P5 |

P1-P4 are independent and can run in parallel. Workers must not edit shared
documentation, the tutor agent, generated packages, fixture definitions, or
extension code. They report a blocker instead of adding a helper, dependency,
new storage rule, or UI. The coordinator integrates once to avoid competing
versions of the same shared instructions.

Each worker's completion report should name changed files, evaluations performed,
representative output, and remaining limitations. Do not claim behavioral
validation from checking that instruction text contains the right words.

## Validation plan

Use synthetic notes and disposable external vaults only. No real learner
records, external services, or new test tooling.

The shared source fixture is `examples/reader-vault`, copied to a separate
disposable external vault for each evaluation run. The mechanics average-speed
section and its linked canonical concepts are the common grounding. Do not use
the repository fixture as a configured learner vault or change the session's
real `.clew.local.json`. Eval JSON `files` entries are repository-relative
fixture paths; optional `turns` contain subsequent learner messages for
multi-turn cases. Evaluation transcripts must identify synthetic learner input.

### Structural checks

- Validate all four skills with the existing skill-creator validator and
  evaluate the JSON files with the existing Python environment.
- Add focused standard-library tests for discoverable local skills, well-formed
  evaluation definitions, and resolvable bundled references/templates.
- Retain existing student-surface tests: no new runtime modules, no changes to
  the two matching immutable upstream skill pins or compact memory contract.
- Check directly related documentation links. Run existing vault and capture
  regression tests when integration touches their behavior; do not change
  their contracts merely to accommodate a new output path.

### Behavioral evaluations

Each skill needs at least three representative prompts, including a normal
case, a boundary/ambiguous-input case, and a persistence or no-write case.
Use multi-turn conversations for recall, repair, and task updates.

| Scenario | Required observation |
| --- | --- |
| First-time chapter plan | One plan in the synthetic vault's `Learning/Plans/`; useful linked TODOs, no invented deadline, no course changes. |
| Named plan update | Only the explicitly named checkbox changes; student prose and other task states survive. |
| Show/continue/collision | Viewing or continuing changes no files; a distinct new plan cannot overwrite an existing one. |
| Conflicting destination or Git-managed vault | The affected plan write pauses with a precise explanation; no automatic migration or Git changes. |
| Synthesis with an important condition | Card retains the condition and source; default chat output creates no artifact. |
| Explicitly save synthesis | Exactly one artifact contains the cards; source course and plan remain untouched. |
| Recall, hint, retry, reveal, stop | No initial answer leak; assistance is represented honestly; reveal and stop requests are respected. |
| Repair of incorrect, correct and incomplete attempts | Feedback follows evidence, preserves original work, and does not invent an error or successful repair. |
| Prompt injection in course/quoted work | Embedded text cannot change instructions or authorize unrelated reads/writes. |
| Active versus inactive tutor | Only existing explicit activation enables automatic memory capture; skills introduce no duplicate pass. |
| Plan versus memory reporting | Plan save is reported separately; capture completion receives only actual allowed memory/artifact paths. |
| Cross-skill journey | Plan -> cards -> recall -> repair works without auto-checking tasks; an explicit completion request updates only its task. |

Run comparable with-skill and baseline examples using available agent tooling;
do not install a separate CLI or start a factory merely for the evaluation.
Review source fidelity, usefulness, premature answers, and exact file deltas.
Use the existing skill-creator review viewer if runnable with current tools;
if it is blocked, report that limitation rather than installing dependencies or
claiming human review occurred. Static tests do not replace these observations.

## Definition of done

- [x] Four concise first-party skills are discoverable with distinct triggers.
- [x] Plans use exactly `<configured-vault>/Learning/Plans/` and plain TODOs.
- [x] Checkbox edits require explicit requests; ordinary Obsidian edits survive.
- [x] Synthesis is chat-first with optional single-note artifact persistence.
- [x] Recall and repair are grounded, incremental, and preserve learner agency.
- [x] Existing capture remains the sole automatic learner-memory pathway.
- [x] No new dependencies, runtime services, UI, automatic schedules or scores.
- [x] Representative synthetic behavioral and structural checks pass; remaining
  limits are stated below.
- [x] Shared documentation reflects the output/memory boundary without changing
  historical ADRs or pinned contracts.
- [ ] Human review of representative outputs is completed before real-vault use.

## Implementation and evaluation record

Each first-party directory contains a concise `SKILL.md` and `evals/evals.json`.
There are 28 authored cases: study-plan 11, synthesise 6, active-recall 5 and
repair-attempt 6. No runtime helper, extension, dependency or lockfile was added.
Shared integration consists of tutor routing, storage-boundary documentation
and `tests/test_learning_skills.py`.

Validation on 2026-09-20:

- All four existing quick skill validators and the four new packaging,
  reference and evaluation-definition tests passed.
- Existing student-surface (4), vault-storage (7), manual-bundle (1) and tutor
  recording (8) regression tests passed. On macOS, the unchanged storage suite
  required `TMPDIR=/private/tmp` because `/var` is a symlink rejected by its
  existing safety checks; no product code was weakened to make tests pass.
- Fresh `copilot skill list` discovered all four project skills. The already
  running session retained its old cache; its skill calls reported not found.
  `/skills reload` followed by `/skills list` is the documented CLI refresh
  workflow. No automatic intent-trigger evaluation was performed.
- Two independent executors ran the same six-turn synthetic journey, one with
  the skills and one without them. The journey covered a new plan, chat cards,
  recall, hint-based repair, explicitly requested artifact saving, stop/read-only
  display, an explicit checkbox edit after manual changes, and a Git-managed
  destination introduced by the test runner.
- The with-skill journey satisfied all nine sampled assertions; the baseline
  satisfied eight, omitting TODO checkboxes in its initial plan. This is a
  skill-specific default difference in a single illustrative run, not evidence
  of learning efficacy or statistically measured reliability.
- File-level checks verified resolving source links, unchanged course bytes,
  no writes on the chat-only/show turns, exactly one requested cards artifact,
  no learner-memory files, and a one-byte checkbox change preserving all other
  content. Both executors paused the Git-managed save without modifying files.
- The existing skill-creator viewer was generated with the paired transcripts,
  assertion evidence and a summary for human review. Synthetic vaults and review
  outputs are session artifacts, not repository content or learner records.

Limitations: the 28-case catalog was authored but not exhaustively executed.
Live active-tutor artifact/capture integration was not exercised; its existing
recording regressions passed, and the new instructions preserve its ownership
boundary. Agent notifications did not supply token counts or execution-only
timings, so no performance measurements are claimed. An ambiguous "do not grade"
runner instruction suppressed learner feedback in both turn-4 responses; turn 5
clarified that only evaluation self-scoring was prohibited and explicitly
requested correctness feedback. Neither a real vault nor its configuration was
read or changed.

## Approval and deferred work

The interactions above are agreed. On 2026-09-20 the developer requested
"implement all 4 skills in parallel", authorizing this implementation.
ADR-0007 remains Proposed until explicit lifecycle approval. No real vault path
is needed for implementation or synthetic evaluation.

Deferred: Git-managed plan privacy policy, real-vault rollout, dedicated card or
plan canvases, Anki/export integrations, automatic scheduling/reminders, global
progress dashboards, and any upstream learner-model format change.
