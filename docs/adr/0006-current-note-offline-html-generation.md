# ADR-0006: Current-note offline HTML generation

- Status: Accepted
- Date: 2026-10-04

## Context

ADR-0001 separates faithful source preparation, optional learning aids and
repeatable publication. ADR-0008 defines document-internal learning units:
one PDF is one complete note but may contain several exercises and supplied
correction variants. ADR-0007 defines optional question-addressed help notes.

The desired output keeps expandable exercises, progressive hints, inline
supplied corrections, explanations and precise course excerpts. Publication
must use current edited content without a producer snapshot/hash approval
framework or an installed producer skill.

## Decision

Implement portable `clew-generate` for current whole-document notes only.
Consume `clew_schema: 1`, `type: document`, explicit roles, typed unit scopes,
native entry/question/answer anchors and relative relationship links.
Discover chapter folders through their `type: chapter` index or accept
explicit current-format Markdown files. Reject legacy exercise-per-note
inputs rather than maintaining a second parser or migrating user archives.

The agent reads selected current content and authors a small version-1 JSON
layout of scope, order and unresolved relationships. Python discovers/parses
structure, resolves references, renders Markdown, embeds assets and assembles
one offline HTML file. It does not decide semantic matches or generate prose.
Do not require `.clew/preparation.json`, baselines, hashes, Import/Enrich runtime
code or original Markdown. Never restore source text over human edits.

### Document-internal selection and ownership

Exercise identity is document ID plus native exercise-entry anchor. A whole
worksheet expands to its scoped exercise units, not a single sheet-sized
exercise. Partial question selections group by owner and preserve source order
and shared unit context. Whole worksheet views retain introductions, section
headings, inter-unit prose and final review warnings once in source order.
Scope comments are bookkeeping, not display content. Section IDs remain
private; section links use genuine headings.

Unit-entry selectors deliberately expand to the publication scope, while
native Obsidian block navigation still targets only the entry paragraph.
Preserve existing anchors in HTML without exposing generated entry scaffolding.
Heading/block/safe-line selections cannot silently bisect protected Markdown,
overlap, duplicate or misattribute source units.

Exact `Exercise` correction-unit and `Question` answer-callout footer links
define supplied associations. Linked answers must agree with their unit's
owning exercise. Canonical addresses include document identity; filenames,
printed numbering or matching local suffixes are not proof.

Correction panels contain that correction unit's non-answer context once and
only selected answers for the published question in source order. Variants
remain separate even within one document. Unmatched answers warn; explicit
choices may resolve missing matches but cannot contradict existing ownership.

Optional help notes supply existing anchored hints/explanations and any
human-authored methods. Explanations require their specific selected supplied
answer; hints can exist without an answer. Course links in aids register exact
selected course heading/block excerpts for the side panel, even when the full
reading view is suppressed. Missing content yields no empty controls.

### Scoped discovery and portable parsing

Use metadata, not role-folder names, for discovery. A selected chapter/index
expands to visible document/help notes; exclude hidden configuration, `.clew/`
and retained `sources/`. An established vault/course context permits bounded
chapter discovery, stopping at chapter roots and reporting inventory omissions.
Ask only about real ambiguity; do not require users to enumerate notes.

All note references resolve among selected inputs. Decode relative Markdown
paths/fragments and support existing wikilinks. Ignore structural lookalikes
inside code/math; preserve source comments' reading semantics and support
LF/CRLF/CR. Fail malformed scopes, duplicate identities/anchors, invalid nesting,
contradictory owners, unresolved targets, redirects and access errors explicitly.

### Offline output and HTML-first maintenance

Embed CSS, interaction code, supported raster figures and a pinned licensed
MathJax SVG runtime. No CDN, server or frontend build is needed. PDF links are
optional external provenance rebased from the output location.
Escape raw HTML; reject SVG/remote rendering resources, note transclusions,
Dataview and active/dynamic TeX rather than executing or silently discarding them.

Retain responsive light/dark styling, native controls and keyboard/mobile
behavior. Repeated view markup remains in native HTML `<template>` blocks
inside `assets/template.html`. JavaScript clones templates and consumes an
ordered worksheet stream; it does not construct repeated HTML strings or use
`createElement`. Preserve stable template IDs and `data-slot`, `data-action`,
`data-help` hooks. Missing templates/hooks fail explicitly.

Data mode (`--data`) compiles the same layout to JSON for a live reader such as
the canvas of ADR-0012, ignores `output`, makes source and PDF paths relative to
an optional `--base` directory and writes nothing else. It shares the parser,
selection and rendering rules, so both outputs present the same content.

Inspection and `--check` are read-only. Show selected scope, output, command
and warnings before publishing, without a hash ceremony. Refuse existing
output by default; explicitly requested `--overwrite` atomically replaces only
that derived HTML after successful rendering. Do not create output directories,
delete directories, modify sources or implement a ledger.

Bundle complete instructions, scripts, templates, dependencies, references,
licenses/provenance and workflow evaluations inside the skill. Keep executable
tests/fixtures in `tests/clew_generate/` per ADR-0003; browser checks are
development tooling, not a runtime dependency. Update all affected compatibility
claims and documentation together.

## Consequences

- Current Import-shaped documents publish with or without optional Enrich aids.
- Source file storage remains independent of learning-unit presentation.
- Publication accepts human edits and copied current notes without producer
  records or source-fidelity validation.
- Legacy input compatibility and migration, learning-content authorship and
  grading remain outside scope. The offline HTML stores no progress; activity
  capture belongs to the canvas reader (ADR-0012).
- Unsupported features or ambiguous relationships require explicit decisions.
- Offline assets increase HTML size; source PDFs remain external and their
  links can break after relocation without affecting reading.
- Structural checks cannot prove pedagogical or mathematical correctness;
  visible math failures and representative browser inspection complement them.
