# ADR-0004: Faithful multi-bundle ingest

- Status: Accepted
- Date: 2026-10-04

## Context

ADR-0001 separates conversion, faithful organization, enrichment, and publication.
The first Ingest iteration must prepare readable course material from existing
PDF Import bundles, without implementing HTML generation or learning enrichment.
The user approved this scope and the following decisions before implementation.

A course, exercise sheet, and correction can be separate bundles or combined in
one document. Some sources have no exercises or corrections. Source layout alone
does not determine useful note boundaries or question dependencies. The proposed
PT Tutor Vault Schema is design input, not a mandatory full schema.

ADR-0003 requires portable operating assets. Its requirement to bundle script
tests conflicts with the user's decision to keep those tests in the repository,
outside skills. Runtime portability and development test ownership are distinct.

## Decision

Implement `clew-ingest` as a portable skill consuming explicitly selected
schema-version-3 Import bundles. It does not convert PDFs, call cloud services,
generate learning material, or render HTML.

The agent chooses coherent note boundaries, meaningful names, ordering,
question/answer matches, and relationships evidenced by source passages. A
versioned JSON plan records those decisions and exact source selectors. Each run
requires explicit user approval of that concrete plan before writing. Narrow
Python tools inspect bundles, slice Markdown, check/materialize plans, and
validate persisted outputs; they do not make semantic decisions.

Contextual placement is also an agent responsibility. Inspect the user-identified
vault's visible layout and representative notes, match supplied material to
existing subject/level conventions, and propose an exact parent and new chapter
destination with rationale. Obtain placement confirmation; ask when ambiguous,
and never silently use the vault root. Do not impose a fixed taxonomy. A bounded,
read-only inventory helper exposes paths and omissions, not semantic decisions.
Required plan placement records the vault, relative parent, rationale, and any
explicitly approved missing-container creation. Final concrete-plan approval
remains a separate writing gate.

Use course/section notes, exercise/question blocks, and correction/answer blocks.
Defer competency notes, inferred prerequisite graphs, misconceptions, rubrics,
and the full proposed taxonomy. Preserve ambiguous content, omit uncertain
relationships, and report review issues. Missing exercises/corrections belong to
Enrich, not Ingest.

Create one previously nonexistent output directory:

```text
<ingest>/
  index.md
  courses/        course and section notes with meaningful names
  exercices/     exercise notes
  corriges/      correction notes
  sources/
    <source-id>/
      <original-name>.pdf
      document.md
      figures/   referenced figures
  ingest.json    plan, source mapping, fingerprints, review and ownership records
```

Use separate stable source IDs even when source filenames collide. Keep every
created file under the ingest root, with no external symlink or cross-ingest
ownership. Removing that directory removes the entire ingest. Do not automatically
delete, merge, overwrite, or update outputs. Preserve failed partial outputs and
report them explicitly.

Approved missing parent containers may be created as shared vault organization.
They hold no chapter-owned files outside the new root and may remain after
removal; never automatically delete them. Do not nest an ingest inside another
ingest's owned subtree.

Manual testing refined the retained layout: put the PDF directly beside its
Markdown rather than repeating Import's internal `source/` directory. Keep
Import-relative references in snapshot provenance, but map note references,
copies, and ownership records to the flattened path. Generated provenance links
use separate `#page=N` PDF links for each original page, not printed labels or
selected-page positions; source-authored links remain faithful. Index PDF links
target the first imported page. The output schema is version 3; plans use version
2 with required placement, while note schemas remain version 1. Approval hashes
bind the output version and full plan. Reject earlier version-1/2 outputs and
version-1 plans explicitly without automatic migration, and require confirmed
placement and a freshly approved ingest in a new destination.
Import's own directory layout is unchanged.

Copy only PDFs, imported Markdown, and referenced figures. Preserve relevant
manifest metadata in ingest provenance, but do not present the subset as a
complete Import bundle. External bundles, including raw evidence and logs, remain
unchanged. This partially supersedes ADR-0002's requirement to preserve the entire
bundle when placing it in the vault; Import's own bundle contract is unchanged.

Validate exact content coverage, safe Markdown boundaries, fidelity apart from
documented wrappers/link rewrites, source hashes, assets, IDs, ordering, and
relationships. Approval is invalidated by changed source fingerprints, plan, or
destination. Renderers can later consume the notes without Obsidian plugins or
external original-bundle locations.

### Script tests belong to the repository

Keep executable Python tests and fixtures outside every skill directory:
`tests/clew_ingest/` and `tests/clew_import/`. Workflow evaluations may remain
inside the skill. Update development commands accordingly.

This partially supersedes ADR-0003's script-test bundling requirement. Skills
still own complete runtime instructions, assets, dependencies, configuration,
licenses, and provenance. A copied skill does not need repository tests or ADRs
to operate; the repository verifies portability through its external test suite.

## Consequences

- Source content remains distinguishable from future enrichment.
- The agent's intelligence is inspectable in a concrete approved plan.
- Repeatable mechanical execution does not require a second embedded model.
- Contextual placement requires reading vault conventions and user confirmation,
  not a hardcoded subject/level classifier.
- One output root makes ownership and removal straightforward.
- Source-evidenced relationships may be sparse; missing links remain review
  findings instead of guesses.
- Retained subsets are smaller than complete bundles but cannot reproduce
  conversion diagnostics; the original bundles preserve those.
- Portable skills omit development script tests; maintainers use this repository
  to run them. Workflow evals and runtime format references remain distributable.
- HTML, incremental updates, cross-ingest linking, cleanup automation, and Enrich
  remain future work. ADR-0001's stage boundaries are not superseded.
