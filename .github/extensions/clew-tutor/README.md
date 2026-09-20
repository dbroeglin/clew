# Clew Tutor capture (ADR-0005, plan P1-P6)

This project extension implements the local orchestration side of
[ADR-0005](../../../docs/adr/adr-0005-explicit-tutor-sessions-and-local-evidence-capture.md)
and its [implementation plan](../../../docs/plans/learner-evidence-capture.md).
It has been exercised with synthetic vaults only. A real learner vault remains
a separate authorization and rollout decision.

## Boundary

The shipped extension never writes learner memory. It:

- binds an explicitly selected Clew Tutor session to one learner and vault;
- adds a bounded prompt-disposition obligation to each active learner turn;
- gates meaningful activity, correlates chat and canvas references, and emits
  semantic recording requests;
- receives honest `recorded`, `partial` or `failed` reports after the tutor
  agent applies the pinned learner-model skill;
- reads bounded memory files for inspection and prepares exact correction,
  stop-use and deletion scopes.

The tutor agent remains the writer. `test/reference-recorder.mjs` is a
test-only reference implementation that materializes requests in disposable
synthetic vaults; it is never registered with the App and is not a production
writer.

## Runtime flow

1. The learner selects the **Clew Tutor** custom agent. Model-driven invocation
   is disabled.
2. The agent calls `clew_tutor_bind_session` with the explicit learner and
   configured external vault.
3. While capture is active, `onUserPromptSubmitted` allocates a bounded,
   in-memory prompt ID but stores no prompt text. Before stopping, the agent
   classifies that prompt with `clew_tutor_dispose_prompt`.
4. Read-only activity produces no request. Meaningful activity produces one
   semantic request targeting the summary, a dated session or an artifact.
5. The agent applies the request through the learner-model skill, then calls
   `clew_tutor_report_recording` with the exact persisted paths or an honest
   partial/failed result.
6. `clew_tutor_capture_status` combines request/result state with a best-effort
   read of the compact memory.

Switching away pauses admission. Reload or explicit end starts inactive, clears
all pending state and requires the learner to reselect Clew Tutor before binding
again: there is deliberately no durable inbox or exactly-once guarantee.

## Headless canvas actions

`clew-tutor-capture` registers agent-callable actions for:

- `submit_attempt`
- `request_hint`
- `respond_to_proposal`
- `revise_attempt`

There is no learner-facing exercise iframe in this phase. Every action requires
an explicit source interaction, attempt identity and `learnerOrigin: true`.
Agent invocation alone is not accepted as proof of learner origin. Chat and
canvas events sharing an attempt ID become one recording request where
best-effort correlation succeeds.

## Learner controls

- `clew_tutor_memory_inspect` reads one `model/` or `artifacts/` file, capped at
  16 KiB.
- `clew_tutor_prepare_memory_change` resolves one exact correction or stop-use
  replacement without writing it.
- `clew_tutor_prepare_deletion` reports an exact file or passage and affected
  compact-memory references. It performs no deletion and requires separate
  explicit confirmation before any destructive action.

These tools do not create a tombstone engine, overlay or alternate memory
format.

## Validation

Run from this directory:

```powershell
npm test
npm run check
```

The dependency-free Node suite covers summary/session/artifact requests,
read-only gating, partial failures, automatic prompt disposition, origin-gated
canvas capture, cross-surface correlation, bounded inspection, prepare-only
deletion, reload gaps, prompt bounds and concurrent-session isolation.

The project extension also reloads successfully against the host-provided SDK;
its eight tools and nine headless canvas actions are discoverable. Live
selection/binding against a real learner vault has not been authorized or
tested.

## Remaining limits

- The custom-agent profile and prompt discipline are not a filesystem sandbox;
  generic agent tools cannot be proven unable to bypass this orchestration.
- Completion inspection is intentionally heuristic and best effort.
- Prompt and request state is memory-only and is lost on process termination,
  reload or session replacement.
- The canvas API and agent-selection RPC are experimental host surfaces.
- No visible learner practice UI, real-vault rollout, remote store, passive
  telemetry, backup or cross-device sync is included.
