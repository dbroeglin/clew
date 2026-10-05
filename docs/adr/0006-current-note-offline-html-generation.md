# ADR-0006: Current-note offline HTML generation

- Status: Accepted
- Date: 2026-10-04

> Later refinement: [ADR-0007](0007-course-linked-question-enrichment.md)
> defines the first Enrich implementation and extends this publication
> convention to supplied-answer explanations and aid-to-course panel links.
> [ADR-0008](0008-exercise-unit-pipeline-contract.md) groups question selections
> by owning exercise and separates note granularity from HTML presentation.

## Context

ADR-0001 separates optional learning enrichment from repeatable publication.
Import and faithful Ingest exist, but Enrich does not. A separately authored
HTML mock demonstrates expandable exercises, question methods and progressive
hints, inline supplied corrections, and contextual course excerpts.

The user selected an agent-directed skill with deterministic Python, current
Obsidian input, one offline HTML output, optional preexisting enrichment, and
the mock's visible interactions. They explicitly rejected an Ingest-style
hash/approval/provenance framework for Generate.

## Decision

Implement portable `clew-generate`. The agent reads selected current notes and
authors a small versioned JSON layout recording selected files, role/order
choices, and unresolved relationships. Reuse existing note links whenever
possible. Python inspects structure, resolves explicit selectors, renders
Markdown, embeds assets, and assembles a fixed HTML template. It does not make
semantic or pedagogical decisions.

Accept current Ingest-shaped notes and a documented subset of ordinary Obsidian
Markdown without requiring `ingest.json`, byte identity, a producer installation,
or a fixed vault hierarchy. Never restore imported text over human edits.
References use existing note/block/heading addresses or parser-safe explicit
line ranges. Ambiguous/unpublished targets are explicit errors.

Optional separate help notes can contain question-addressed method/hint
callouts. Missing aids or corrections are valid; omit unavailable controls.
Generate never writes teaching content or implements Enrich. Guided-step tabs,
grading, progress persistence, and analytics are outside the first release.

Produce one static file with embedded CSS, interaction code, supported raster
figures, and a pinned licensed MathJax SVG runtime. No CDN or runtime service is
required. PDF references remain optional external provenance links, rebased
from the output location. HTML remains derived; notes are the content store.

Use fixed responsive two-column layout and light/dark theme tokens, preserving
the mock's interactions rather than copying its green/serif appearance.
Render Markdown in Python and limit browser JavaScript to interactions and math.
Escape raw HTML, reject unsafe executable resources, and report unsupported
constructs rather than evaluating plugins or silently discarding content.

Inspection and `--check` are read-only. The agent shows scope, choices, path,
warnings, and command before publication without requiring a hash ceremony.
Do not modify source notes. Refuse an existing output by default; narrowly
requested `--overwrite` replaces only the specified derived HTML atomically.
Do not create output directories, clean up directories, or implement a ledger.

Bundle complete instructions, scripts, templates, licenses, dependencies,
format references, and workflow evaluations in the skill. Keep executable
tests outside it, under `tests/clew_generate`, per ADR-0004. Browser checks are
development tooling, not a standalone runtime requirement.

### HTML-first template maintenance

Keep repeated course/exercise/question views, optional controls, hint panels,
corrections, content containers, and course links in native HTML `<template>`
blocks inside `assets/template.html`. This refines the fixed-template decision:
the file owns the actual view markup, not just the outer page shell.

JavaScript clones these blocks, fills text and Python-rendered content, removes
unavailable controls, and attaches interaction behavior. Do not construct view
markup with JavaScript HTML strings or `createElement` calls. CSS remains in
`assets/style.css`; Python embeds the assets without a frontend build step.

Use stable template IDs and `data-slot`, `data-action`, and `data-help` hooks
as the markup/behavior contract rather than styling classes or incidental
nesting. Layout, static labels, and classes can be edited in HTML without
rewriting behavior, provided those hooks and native control semantics remain.
Missing required templates/hooks fail explicitly, not through a silent fallback.
Browser checks must exercise edited template structure as well as the existing
offline learning interactions.

### Topology-led chapter discovery

When the user supplies a course/chapter context, do not require a hand-authored
list of its constituent notes. A selected chapter directory or Ingest `index.md`
expands to current learning notes under `courses/`, `exercices/`, and `corriges/`,
plus optional help notes. Reuse note metadata for role, reading order,
course/section membership, and answer/question matches. Directory roles supply
structural defaults only; they do not infer pedagogical relationships.

When only a vault/material container and course name are established, bounded
read-only discovery lists chapter paths and titles. The skill selects the unique
matching chapter from user context; ask only about genuine ambiguity.
Do not publish an entire vault or scan unrelated machine locations.
Exclude hidden configuration and retained `sources/`; stop discovery at chapter
roots and report inventory-limit omissions.

This uses Ingest's known topology without requiring its implementation,
validating its record, or comparing hashes. Explicit current-note paths remain
supported for other layouts. Missing roles, including corrections, are valid;
unresolved semantic relationships still require explicit agent decisions.

## Consequences

- A current course can be published without rerunning any previous stage.
- Agent decisions remain explicit without a large plan/approval system.
- Enrich can adopt a minimal aid convention later; Generate works without it.
- Unsupported Obsidian features require an explicit selection/content decision.
- The offline runtime increases HTML size; selected content/figures only are
  embedded rather than entire imported sources.
- Source PDF links can break when the HTML moves, without affecting reading.
- Mathematical correctness is not mechanically proven; browser errors and
  representative inspection complement static selection checks.
- Ingest's existing immutable-output validator is unchanged and intentionally
  not used by Generate. Future Enrich ownership/revision semantics remain open.
- HTML-first view markup is maintainable without a framework; changes to
  behavioral hooks or native controls require coordinated JavaScript updates.
- Normal Ingest chapters can be selected by folder/index rather than by note
  enumeration, while bounded discovery keeps publication scoped to one course.
