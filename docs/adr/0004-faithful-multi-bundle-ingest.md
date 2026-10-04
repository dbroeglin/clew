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
    <source-id>/  retained PDF, unchanged imported Markdown, referenced figures
  ingest.json    plan, source mapping, fingerprints, review and ownership records
```

Use separate stable source IDs even when source filenames collide. Keep every
created file under the ingest root, with no external symlink or cross-ingest
ownership. Removing that directory removes the entire ingest. Do not automatically
delete, merge, overwrite, or update outputs. Preserve failed partial outputs and
report them explicitly.

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
- One output root makes ownership and removal straightforward.
- Source-evidenced relationships may be sparse; missing links remain review
  findings instead of guesses.
- Retained subsets are smaller than complete bundles but cannot reproduce
  conversion diagnostics; the original bundles preserve those.
- Portable skills omit development script tests; maintainers use this repository
  to run them. Workflow evals and runtime format references remain distributable.
- HTML, incremental updates, cross-ingest linking, cleanup automation, and Enrich
  remain future work. ADR-0001's stage boundaries are not superseded.
