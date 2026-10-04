# ADR-0006: Current-note offline HTML generation

- Status: Accepted
- Date: 2026-10-04

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
