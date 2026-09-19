---
title: "ADR-0001: Copilot App extensions for a bidirectional learner UX"
status: "Proposed"
date: "2026-09-19"
authors: "Clew maintainers"
tags: ["architecture", "decision", "ux", "copilot", "extensions"]
supersedes: ""
superseded_by: ""
---

# ADR-0001: Copilot App extensions for a bidirectional learner UX

## Status

**Proposed** | Accepted | Rejected | Superseded | Deprecated

The initial reader implementation was separately requested for evaluation.
Its presence does not constitute acceptance of this decision or approval of its
UX, constraints, or dependencies. The reader UX was refined in discussion on
2026-09-19. Implementation of the refined UX was subsequently authorized,
separately from acceptance of this ADR.

## Context

Clew's learner and agent need to work with the same course material in a shared
visual surface. A chat transcript alone is not a suitable reading or navigation
interface. The learner must be able to initiate an interaction with the current
session from that surface, and the session must be able to control the surface.
Neither direction can depend on copying content manually between applications.

The first surface is a Markdown reader for a chosen course in the current
vault. Navigation comes from top-level YAML `previous` and `next` properties,
containing paths or wikilinks, rather than inferred file order. Course
mathematics must render with KaTeX.

The prototype added too many visible behaviors and controls. The agreed
direction is a reading-first surface, with discussion initiated from a selected
passage and completed in the existing chat composer. The concern is UX
complexity, not a request to remove implementation safeguards.

The [learner model specification](../LEARNER_MODEL.md) keeps course metadata
separate from private, domain-indexed learner records. It excludes passive
telemetry and restricts transmission to resolved adaptation decisions and
grounded course excerpts. Building a bidirectional interface must not turn page
navigation into learning evidence or make the private model available to a
hosted session.

## Decision

Use project-scoped GitHub Copilot App canvas extensions as Clew's learner-facing
UX layer. Keep the learner and agent in the same session, use the supported
Copilot SDK rather than modifying the host application, and make both directions
of communication explicit.

This records the architectural direction and agreed UX, not blanket approval of
the prototype's mechanisms. Follow the
[collaborative design instructions](../../AGENTS.md#discuss-before-implementing)
before choosing implementation constraints or adding dependencies.

- **DEC-001**: **Reader baseline:** show the course title, rendered content,
  Previous/Next navigation, and a collapsible contents list of the current
  page's headings. Contents starts collapsed and retains the learner's toggle
  choice while navigating in that panel. Other
  persistent controls, status metadata, or behaviors require discussion before
  being added; they are not implied by the bidirectional requirement.
- **DEC-002**: **Session to extension:** the session can open and navigate the
  reader through the supported extension API. Session-driven changes must be
  reflected in the reading surface. Agent-facing capabilities do not each
  require a corresponding permanent control in the reader.
- **DEC-003**: **Reader to session:** selecting a passage offers a contextual
  **Ask in chat** action. That action should prepare the passage in the current
  chat composer as an attachment chip, a form explicitly agreed with the
  developer. The learner writes a question and chooses when to send it. Preserve
  the complete selection without silently truncating it or applying the
  prototype's 12,000-character excerpt cap; report host-imposed rejections.
  Include a source reference consisting of the full file path and the heading
  where the selection starts, when available. This is excerpt metadata, not an
  attachment of the entire file, and does not change the learner's instruction.
  Selecting text or invoking this action must not automatically send a message.
- **DEC-004**: **Capability gate:** composer handoff must use a supported host
  mechanism. If that mechanism is unavailable, defer this interaction. Do not
  substitute direct sending, a question field in the reader, a separate preview
  dialog, or a custom host bridge without another discussion and agreement.
- **DEC-005**: The first surface reads the chosen course's Markdown, including
  KaTeX mathematics, and follows the authored `previous` and `next` properties.
  Rendering integration, detailed link-resolution rules, and operational limits
  are implementation proposals to review, not additional UX decisions implied
  by this requirement.
- **DEC-006**: Preserve the learner-model specification's existing privacy and
  ownership boundaries. Course reading and navigation must not become passive
  learning evidence. Course content remains separate from private learner
  records; a connection to the session does not grant permission to transmit or
  update the learner model.
- **DEC-007**: Research a few viable options and present trade-offs and a
  recommendation before introducing a dependency or constraint. The human
  developer approves the proposal together with its disclosed dependency
  footprint, including transitive packages. Neither a working prototype nor
  permission to implement the feature approves unreviewed adjacent choices.

## Consequences

### Positive

- **POS-001**: The learner gets a focused reading surface rather than a second
  application toolbar competing with the course material.
- **POS-002**: The selected passage grounds the learner's own question. The chat
  composer remains the place to author and send messages, without an extra
  explanation workflow inside the reader.
- **POS-003**: Existing Markdown courses and their authored navigation remain
  usable without conversion into an application-specific database. KaTeX
  supports mathematical course content.
- **POS-004**: Explicit discussion gates keep requirements separate from
  convenient prototype choices and preserve the learner-model boundary.

### Negative

- **NEG-001**: The interactive UX depends on GitHub Copilot App's canvas
  capability and the bundled SDK. The canvas API is experimental, so SDK
  compatibility and restart/rehydration behavior require verification on
  supported App versions.
- **NEG-002**: Composer staging requires a host that supports extension context
  attachments. On an unsupported host the action remains unavailable rather
  than being replaced by another UX. Large selections may be rejected by the
  host; the reader must report this rather than silently shortening them.
- **NEG-003**: A deliberately small reader will not expose every available
  capability as a visible control. Additional workflows need separate
  discussion rather than accumulating in the initial interface.
- **NEG-004**: The prototype's technical choices still need review independently
  of this UX refinement. Implementing an agreed interaction does not approve
  the rest of the prototype's constraints or dependencies.

## Alternatives Considered

### Chat-only UX

- **ALT-001**: **Description**: Render course material and navigation prompts
  directly in the conversation.
- **ALT-002**: **Rejection Reason**: Chat is appropriate for explanations but
  does not provide a stable course-reading surface that the learner and agent
  can navigate together.

### Obsidian plugin as the primary UX

- **ALT-003**: **Description**: Implement Clew's reading and interaction surfaces
  within an Obsidian plugin.
- **ALT-004**: **Rejection Reason**: Native vault integration would be useful,
  but the primary learner surface would be outside the Copilot session and
  require a separate session bridge. The proposal prioritizes co-location with
  the agent while preserving the vault's Markdown sources.

### Standalone web application

- **ALT-005**: **Description**: Build an independent browser application with its
  own session integration and course-reading UI.
- **ALT-006**: **Rejection Reason**: This offers host independence but adds
  application hosting, session routing, and lifecycle responsibilities before
  proving the shared learner-agent UX. An extension uses the existing session
  and App surface instead.

### Permanent page-explanation controls

- **ALT-007**: **Description**: Keep the prototype's persistent **Explain this
  page** action, separate excerpt-preview dialog, and direct message submission
  from the reader.
- **ALT-008**: **Rejection Reason**: This adds visible behaviors the learner did
  not request. The agreed alternative is a contextual selected-passage handoff
  to the existing composer, with the learner authoring and sending the question.

## Implementation Notes

- **IMP-001**: The documented
  `session.rpc.extensions.sendAttachmentsToMessage` API stages attachments in
  the next user-message composer. `ExtensionContextPushInput` takes a title and
  JSON payload; `SendAttachmentsToMessageParams.instanceId` binds provenance to
  the extension's canvas. Use it for the selected passage, its canonical file
  path, and a heading verified against the current note. Do not invent exact
  source-line coordinates for a rendered selection. `CopilotSession.send`
  submits a message and is not a substitute.
- **IMP-002**: Refine the existing
  [reader extension](../../.github/extensions/clew-course-reader/README.md),
  removing the previous whole-page explanation and direct-send flow. Reuse
  existing dependencies; this UX change introduces no new dependency.
- **IMP-003**: Treat the prototype's package selection, math-rendering
  integration, persistence, synchronization, and operating limits as unreviewed
  implementation choices. Present researched options and their constraints
  before adopting them as requirements. Do not convert these mechanisms into
  extra visible controls by default.
- **IMP-004**: Keep approved dependencies pinned with their lockfiles and license
  notices. APM continues to manage agent skills; no generated skill changes are
  needed for this document. Approval of a named technology does not approve an
  undisclosed integration package or development-tool dependency.
- **IMP-005**: When implementation is authorized, verify the agreed reading and
  navigation flow, KaTeX rendering, and the supported composer handoff without
  automatic sending. Use synthetic course material, preserve existing safety
  and privacy guarantees, and report deferred capabilities plainly.

## References

- **REF-001**: [Clew's purpose and shared canvas](../../README.md).
- **REF-002**: [Learner model specification](../LEARNER_MODEL.md), especially
  sections 2, 4, 8, 9, and 10.
- **REF-003**: [ADR process](README.md). This is the first record; it supersedes
  no earlier ADR.
- **REF-004**: [Current prototype usage and contract](../../.github/extensions/clew-course-reader/README.md);
  this describes the implementation, not approval of its UX.
- **REF-005**: The installed Copilot SDK's `docs/extensions.md`,
  `docs/agent-author.md`, `canvas.d.ts`, `types.d.ts`, and `generated/rpc.d.ts`,
  located through `extensions_manage` with operation `guide`. These define the
  runtime APIs used here; consult the SDK bundled with the running App.
- **REF-006**: [KaTeX options and trust boundary](https://katex.org/docs/options).
- **REF-007**: [Collaboration and approval instructions](../../AGENTS.md#discuss-before-implementing).
