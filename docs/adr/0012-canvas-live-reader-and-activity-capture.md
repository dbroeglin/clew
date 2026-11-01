# ADR-0012: Canvas live reader, activity capture and tutor bridge

- Status: Accepted
- Date: 2026-11-01

## Context

ADR-0006 publishes current notes as one offline HTML file without progress
storage. Students also need to browse the same material inside a GitHub
Copilot App canvas, with a complete record of what they did and a tutor agent
that knows their progress without receiving answers to repeat.

A canvas is a project extension (`.github/extensions/<name>/extension.mjs`)
running in its own Node process that speaks JSON-RPC over stdio. Its view is a
sandboxed iframe on a URL the extension serves; there is no message bridge from
the page to the agent. The extension can register agent-callable canvas
actions, add hidden context with `onUserPromptSubmitted`, send prompts into
the session and veto tool calls with `onPreToolUse`. The session's own
`events.jsonl` records only what reaches the conversation. The port of the
extension's local server changes when the extension restarts, and an idle
session can stop the extension while the canvas stays open.

## Decision

### Live reader

Implement the project extension `clew-canvas` with one canvas, opened with the
path of a version-1 Generate layout stored in the vault at
`Activity/Layouts/<publication>.json`. The extension compiles the layout with
Generate's data mode, which writes the compiled publication as JSON (no HTML,
`output` ignored, paths relative to the vault), and serves a French reader
with the same views as the offline HTML. It watches the selected notes and the
layout and recompiles after edits, preserving the open exercise, revealed hints
and correction state; a failed recompile keeps the last good content visible
as stale. Offline HTML publication is unchanged.

The extension serves the page, data and vault PDFs on `127.0.0.1` with a
per-session token, a strict content security policy and no network
resources. It persists its port and open instances in the session workspace so
a restarted extension reattaches to an open canvas; the page buffers actions
while the server is away and delivers them later.

### Activity record

Record the complete learning record in the vault, outside the course
folders, in `Activity/<YYYY-MM-DD>-<publication>-<session8>/`:

- `activity.jsonl`: one versioned event per line, with a header linking the
  layout, vault-relative source notes and the Copilot session. Events are
  semantic student actions (exercise started, method shown, hint revealed,
  correction shown or hidden, explanation, course passage and PDF opened,
  tutor requested), plus canvas lifecycle and content changes.
- `summary.md`: a deterministic French summary regenerated from the events,
  with no model call.
- `.clew-activity/`: the layout snapshot and replayable state.

Clicks only are captured, not scrolling or focus. Time per exercise is derived
from gaps between events, each gap capped at ten minutes. The session's
`events.jsonl` receives only what the tutor sees.

### Tutor bridge

Bring activity to the agent through two triggers only: a digest of the actions
since the previous message, added as hidden context on the next user prompt,
and a per-question "Demander au tuteur" button that sends the fixed visible
prompt "I need help with this question" with hidden question context. There is
no free-text box and no rule-based intervention.

The agent has two canvas actions: `get_state` reads progress, statements and
available aids without their contents, and `show` scrolls to and highlights a
question, exercise or course passage. Neither reveals hints, methods or
corrections, and neither is recorded as a student action.

The `clew-tutor` custom agent writes the layout, opens the canvas and tutors
in French: one guiding question at a time, never answers, hint contents or
corrections, within the publication's material. While it is active the
extension denies file-tool writes in the vault except layouts. Shell commands
are not inspected; the agent's instructions forbid vault writes through them.

## Consequences

- Students browse and are tutored in the Copilot App while the vault keeps a
  durable, human-readable record independent of session retention.
- The extension requires the Copilot App, Node, Python, UV and a synchronized
  Clew workspace; it is not a portable skill and stays repository-owned.
- Session transcripts contain digests and help requests, not the full record.
- The guard is defense in depth, not a sandbox: shell writes rely on agent
  instructions.
- Behaviour inside the app's webview (link handling, theme injection,
  extension lifetime) can change with the host and needs in-app checks;
  repository tests use a local browser and a simulated session.
