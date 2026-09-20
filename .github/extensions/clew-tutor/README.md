# Clew Tutor capture — synthetic-data spike (ADR-0005, plan P1)

This is the plan **P1** synthetic-data spike for the App integration described in
[ADR-0005](../../../docs/adr/adr-0005-explicit-tutor-sessions-and-local-evidence-capture.md)
and its [implementation plan](../../../docs/plans/learner-evidence-capture.md). It
proves the capture contract's logic on synthetic vaults and stakes out the SDK
adapter. It is **not** wired to a real vault and processes no real learner data.

## What this establishes (validated with `node --test`)

The pure-logic capture core, exercised over synthetic events and throwaway temp
vaults:

- **Episode lifecycle** (`episode.mjs`): capture begins only on an explicit human
  activation with a known learner and vault; pause/resume/end behave; a reload
  starts inactive and never auto-resumes from process lifetime.
- **Meaningful-write gating** (`gating.mjs`): only genuine learner activity is a
  write; assistant, agent, system and injected input, and recall/inspection/
  configuration, are read-only; a preference needs explicit future scope.
- **Cross-surface correlation** (`correlation.mjs`): the same work seen in chat
  and canvas becomes one candidate, distinct attempts stay distinct, and
  re-delivery is idempotent — best effort, not an enforced guarantee.
- **Ownership/migration preflight** (`vault.mjs`, read-only): an existing model
  without the recognized compact summary blocks capture writes until resolved;
  course reading is never gated.
- **Completion observation** (`completion.mjs`): an unrecorded candidate is
  surfaced and clears once the agent records it. No durable backlog is kept, so
  exactly-once recovery across a crash or reload is not guaranteed.

Run: `node --test` (or `node --check ...` via `npm run check`). No dependencies
beyond Node's built-ins.

## Boundary invariants held by this spike

- The App layer **orchestrates and observes**; it never writes learner memory.
  The tutor agent performs edits through the pinned learner-model skill. Every
  vault touch here is read-only, plus temp-dir writes in tests.
- No new runtime or development dependencies (Node built-ins only).
- The deployed, APM-pinned skills are not edited.

## What still needs the live App (honest limits, ADR-0005 NEG-004)

The SDK is host-provided and not runnable here, so `extension.mjs` is
syntax-checked only and documents assumptions to validate against the live App:

- Activation via the selected root agent: `session.rpc.agent.getCurrent()`, an
  `isRoot`/root-scope signal, and `subagent.selected` / `subagent.deselected`
  delivery and subscription.
- How the learner and explicit vault path are supplied to the extension.
- The learner-facing canvas UI action path (submissions, hints) distinct from
  agent-callable actions, and the reliable delivery/replay of chat events.
- Whether the agent profile's tool grant can be narrowed to the capture actions.
