---
title: "ADR-0001: Unified Clew content structure"
status: "Proposed"
date: "2026-09-19"
authors: "Dominique Broeglin"
tags: ["architecture", "decision", "content", "obsidian", "agent-skills"]
supersedes: ""
superseded_by: ""
---

# ADR-0001: Unified Clew content structure

## Status

**Proposed** | Accepted | Rejected | Superseded | Deprecated

Proposed on 2026-09-19 for human review in Clew. The source skill implementation
and its installation do not constitute formal acceptance of this ADR or
authorization to modify existing course, shared concept or learner data.

## Context

Humans may prefer original course PDFs, while agents working with Clew in the
GitHub Copilot App need small, complete Markdown sections that can be located
without repeatedly extracting PDFs or reading an entire course. A source may
be one whole-course PDF or several chapter PDFs; that packaging should not
change the course's logical structure.

Maintaining portable, hub-based and sectioned course formats introduces competing
rules for navigation, metadata and validation. Clew's objective is one content
structure for its Obsidian vault, not a general-purpose exporter. Related
concepts and prerequisites also need reusable definitions across courses,
without duplicating definitions or confusing curriculum content with evidence
about an individual learner.

The `course-content` skill should own this contract and its bounded reading and
validation behavior. Producer skills should target that contract rather than
define additional formats. Python helpers should use the consuming Clew
project's uv-managed dependencies and interpreter.

## Decision

Adopt one Clew content structure, identified by `schema: clew/v1`, for course,
chapter, section and shared concept notes.

```text
<vault>\
  courses\
    <course>\
      course.md
      chapters\
      sections\
      sources\
      assets\
      support\
        source-map.json
        verification.json
  concepts\
```

- **DEC-001**: Use a fixed vault layout and vault-relative links beginning with
  `courses/` or `concepts/`. The course directory is a stable lowercase
  kebab-case key. Notes have stable IDs, a kind, title and short retrieval
  summary in flat, Obsidian-friendly YAML frontmatter. Preserve identities when
  files are renamed, material is reordered or PDFs are repackaged.
- **DEC-002**: Keep the full transcription in semantically coherent section
  notes, normally around 400-1,200 words. Preserve assumptions, examples,
  exercises, supplied answers, editable mathematics and captioned figures.
  Chunk size is guidance, not permission to truncate or split an inseparable
  activity. Course and chapter notes are indexes, not duplicate transcriptions.
- **DEC-003**: Make course/chapter `children` lists the sole reading-order
  authority. Derive visible contents and reciprocal section `previous`/`next`
  links from that hierarchy, including chapter transitions. Use `course` and
  `parent` for upward navigation. Reading order is not a prerequisite graph
  or a personalized study plan.
- **DEC-004**: Put shared definitions in vault-level `concepts/` notes. Each
  owns a concise `## Definition` and has an `evidence` list displayed under
  `## Evidence`, linking to supporting course sections. Sections declare
  `teaches`; sections/concepts can declare prerequisites and related concepts;
  concepts can identify similar concepts. Relations need grounded or
  explicitly author-reviewed rationale. Reuse concepts by established meaning,
  not merely matching titles; changing a shared definition requires an explicit
  author decision.
- **DEC-005**: Preserve original PDF bytes and map section IDs to source spans
  in `source-map.json`, including hashes, physical pages, known printed labels
  and finer item/region mappings when needed. Generate `source_refs` and visible
  PDF-page links from that map. One large PDF, chapter PDFs or verified equivalent
  representations can support the same Markdown structure. Omit unauthorized
  originals without inventing links; retain visible citations and provenance.
- **DEC-006**: Read Markdown first and follow only relevant navigation,
  conceptual or evidence links. PDF inspection and support reports are for
  requested provenance, visual detail or unresolved transcription, not every
  lookup. Course work must not inspect or update learner memory or infer mastery
  from course content. Shared content concepts under `concepts/` are distinct
  from private learner-state objects under `model/concepts/`.
- **DEC-007**: Validate the selected course and its referenced shared concepts
  using the skill's executable validator. Structural errors always fail.
  Honest `needs-review`/`partial` transcriptions and unresolved page coverage
  produce warnings by default; strict mode makes them errors. Verification
  records bind the source map and section Markdown to actual hashes. Validation
  cannot independently prove visual fidelity, source correctness or legal rights.
- **DEC-008**: Run Python helpers through the consuming Clew project's uv
  environment. Add missing declared dependencies through project-scoped `uv add`,
  respecting its manifest, lockfile and authorization to change them. Do not
  create a skill-owned environment or bypass project constraints with global
  Python, pip or temporary dependency overlays.
- **DEC-009**: Support only this format in `course-content` during development.
  Do not retain compatibility readers, alternate exports or migration paths.
  Migration design is deferred. Align `digest` and other producers in separate
  follow-up work; their existing instructions are not a conforming implementation
  of this contract.

## Consequences

### Positive

- **POS-001**: Humans can inspect original PDF pages while agents retrieve
  bounded, complete Markdown sections with explicit navigation.
- **POS-002**: Source packaging is independent of learning structure; replacing
  chapter PDFs with equivalent whole-course material does not renumber sections
  or recreate conceptual identities.
- **POS-003**: Shared canonical definitions support cross-course connections
  without duplicated per-course definitions or learner-state assumptions.
- **POS-004**: A single contract, machine-readable schemas and executable
  validation give the future producer rewrite a precise target. Project uv
  centralizes Python dependency resolution.

### Negative

- **NEG-001**: Fixed vault-relative paths trade arbitrary bundle relocation for
  deterministic Obsidian navigation. A course also depends on referenced shared
  concept notes, not only files inside its own directory.
- **NEG-002**: Shared definitions require careful ownership and review because
  changes can affect several courses. Similar terminology does not automatically
  justify merging concepts.
- **NEG-003**: Derived navigation, source mappings and verification hashes must
  be reconciled after edits. Hashes and declared comparison records cannot replace
  actual source review or authorization to redistribute PDFs, text and figures.
- **NEG-004**: Removing other formats is a deliberate breaking change. Existing
  producer guidance and consumer references require coordinated follow-up;
  there is no automatic conversion path in this iteration.

## Alternatives Considered

### Keep several course profiles

- **ALT-001**: **Description**: Retain portable Markdown, the earlier hub/package
  format and an optional sectioned profile.
- **ALT-002**: **Rejection Reason**: Multiple authorities and producer modes
  conflict with the single Clew-plus-Obsidian objective.

### Use one complete Markdown file per chapter

- **ALT-003**: **Description**: Keep full chapter transcriptions as the primary
  Markdown reading units.
- **ALT-004**: **Rejection Reason**: Chapter length is not a reliable retrieval
  boundary. Small semantic sections provide more predictable bounded reads
  without making PDF pages the unit of content.

### Keep course-owned concepts or definitions in one selected course

- **ALT-005**: **Description**: Duplicate concept notes per course, or make each
  shared note point to one course section as its canonical definition.
- **ALT-006**: **Rejection Reason**: A shared concept should own its definition
  independently of a particular course, with supporting sections as evidence
  rather than as its storage location.

### Require verified content for every successful validation

- **ALT-007**: **Description**: Reject all partial or unreviewed transcriptions,
  even when their structure and limitations are correctly recorded.
- **ALT-008**: **Rejection Reason**: Development needs useful draft validation.
  Warnings preserve visibility; strict mode supplies the stronger readiness gate.

### Give the skill its own Python project

- **ALT-009**: **Description**: Resolve and run helper dependencies in a separate
  project/environment owned by the installed skill.
- **ALT-010**: **Rejection Reason**: Clew should control the runtime and dependency
  constraints through its own uv project rather than accumulating isolated
  helper environments.

## Implementation Notes

- **IMP-001**: The source implementation is `course-content` 3.0.0 in
  `francesco-kruk/clew-skills`, published at immutable revision
  `d4e0880642b0870857749978417cb9561487626a`. Its contract, navigation guidance,
  provenance reference, JSON schemas and `scripts/validate_clew.py` belong to
  that package. Pin the dependency in Clew's `apm.yml` and use `apm install`
  to regenerate `apm.lock.yaml` and deployed files, preserving the bundled MIT
  license. Enable `agent-skills` alongside `copilot` to honor the package's
  target declaration. Do not hand-edit deployed `.agents/skills/` files.
- **IMP-002**: Resolve the consuming Clew project root separately from the
  external vault. The gitignored `.clew.local.json` declares `version: 1` and an
  absolute `vault` path; course/note selection must be explicit. Use the
  project's uv configuration and Python 3.11 or newer for helpers. Clew has no
  `pyproject.toml` or `uv.lock` at proposal time; establish project uv
  configuration as an explicit integration change, not as a skill-local
  fallback. Add missing requirements only with authorization to edit the
  consuming manifest and lockfile.
- **IMP-003**: Invoke the validator through the consuming project:

  ```powershell
  uv run --project "<Clew project>" python "<installed course-content>\scripts\validate_clew.py" --vault "<vault>" --course mechanics --strict
  ```

  Omit `--strict` for draft validation. The helper emits one JSON report with
  errors, warnings and checked scope, and never repairs content or fetches URLs.
  PDF hashing is streamed; source page counts and review claims remain producer
  evidence, not independently rendered PDF checks.
- **IMP-004**: Validation follows explicitly referenced shared concepts without
  scanning the entire library. Cross-course note targets are checked only for
  their direct identity, schema and anchors, with a scoped warning; validate
  those courses separately. This does not authorize a reading agent to cross
  its established course scope without permission.
- **IMP-005**: Rewrite `digest` against this contract in follow-up work, then
  align other producers. Update Clew's course-metadata references, including
  the learner specification's older hub path and joins, without treating
  shared definitions as learner evidence or migrating private records.
- **IMP-006**: Maintain synthetic coverage for multi-PDF and whole-course
  representations, chunk navigation, shared definitions, prerequisite cycles,
  provenance/hashes, path confinement, warning/strict behavior and read-only
  operation. A structurally valid draft must retain visible limitations.
- **IMP-007**: Add this Proposed record and its index row together under
  `docs/adr/`. Check for numbering collisions with other proposed records
  before merging. Formal acceptance still requires explicit human review
  and a dated reference.

## References

- **REF-001**: [Clew ADR process and index](README.md) and
  [template](template.md). No earlier numbered ADR is superseded.
- **REF-002**: [Clew skill-management guidance](../../README.md#agent-skills),
  [APM manifest](../../apm.yml) and
  [learner-model boundary](../LEARNER_MODEL.md).
- **REF-003**: [Pinned course-content skill](https://github.com/francesco-kruk/clew-skills/blob/d4e0880642b0870857749978417cb9561487626a/skills/course-content/SKILL.md),
  [structure](https://github.com/francesco-kruk/clew-skills/blob/d4e0880642b0870857749978417cb9561487626a/skills/course-content/references/clew-structure.md),
  [provenance](https://github.com/francesco-kruk/clew-skills/blob/d4e0880642b0870857749978417cb9561487626a/skills/course-content/references/provenance.md)
  and [validation](https://github.com/francesco-kruk/clew-skills/blob/d4e0880642b0870857749978417cb9561487626a/skills/course-content/references/validation.md).
- **REF-004**: [Obsidian Properties](https://help.obsidian.md/properties),
  [internal links](https://help.obsidian.md/links) and
  [PDF embeds](https://help.obsidian.md/embeds).
- **REF-005**: [uv projects](https://docs.astral.sh/uv/guides/projects/) and
  [project dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/).
- **REF-006**: [francesco-kruk/clew-skills#7](https://github.com/francesco-kruk/clew-skills/pull/7),
  which published the unified course-content implementation. Its merge does not
  constitute acceptance of this ADR.
