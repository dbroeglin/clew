# ADR-0004: Faithful whole-document preparation

- Status: Accepted
- Date: 2026-10-04

## Context

Splitting converted Markdown creates coverage, context and matching risks.
An LLM should choose changes, not regenerate supplied Markdown.

## Decision

Local step B of `clew-import` accepts selected completed conversion bundles.
Keep one complete editable note per PDF, including mixed roles, with unchanged
source order, prose, formulas, numbering, figures and shared context.
Use `markdown-it-py` CommonMark/table/dollar-math rules for safe source locations.

The agent selects fingerprint-bound blocks, unit/callout roles and
evidence-backed matches in a strict version-1 plan. Python applies a closed
operation set to original source slices: unit scopes, exercise/correction entry anchors, callout
wrapping, block anchors and heading levels, plus generated metadata, page
links, required destination-only remaps and review warnings. PDF provenance is
one compact starting-page link per section entry or exercise/correction/callout
footer, after generated relationship links, with unit entry anchors kept at
the beginning. Sections navigate by existing headings, without generated block
IDs. Do not generate covered-page lists or page-break links. Unit/review
bookkeeping uses Obsidian `%%` comments. Only this generated format is supported;
no compatibility adapter or automatic archive migration is added.
No generic replacement, formatter, OCR repair or source-note splitting.

Choose a new chapter under an evidence-supported non-root vault parent.
One local approval includes placement, parent creation, names, diffs,
operations, matches and warnings. Cloud approval is separate.

Folders are `Course-<basename>`, `Exercise-<basename>`,
`Correction-<basename>`, or basename for unknown/mixed material. Each has its
complete note, adjacent original PDF and referenced figures. Private `.clew/`
contains immutable Markdown baselines and `preparation.json`; `index.md` gives
navigation. Explicit names resolve collisions. Everything is owned by one root.
Raw diagnostics stay in unchanged external bundles; no secrets are copied.

Pedantic validation aggregates current structure/link findings, checks native
anchor scope, typed unit ownership, local paths/fragments/assets and actual PDF
pages. Initial preparation additionally requires exact independent reversal of
recorded edits and preservation of math/code/table structure. Default current
validation accepts manual edits; fidelity mode detects initial-snapshot changes.
Neither mode rewrites notes or baselines. External URLs are not fetched.

Uncertain supplied matches and suspicious valid structure are review findings,
with warning callouts in a final document appendix identifying their anchor or
original source line, and an index summary after navigation.
Broken links, malformed anchors/ownership and unsafe edits are hard errors.
No review reason waives errors.

Persisted fidelity must pass before marking complete. Failures preserve the
partial root; no overwrite, merge, cleanup or automatic retry. Relative links
keep complete chapters movable without external bundles.
Local exits are 0 clean, 2 review-only, 1 errors.

## Consequences

Full documents remain editable and traceable. Semantic decisions remain the
agent's responsibility, but mechanical preservation is enforced locally.
Enrich/Generate new-format consumption and archive migration are deferred.
