---
title: "ADR-0006: Git-based course distribution and import"
status: "Proposed"
date: "2026-09-20"
authors: "Dominique Broeglin (maintainer)"
tags: ["architecture", "decision", "course-content", "distribution", "ingestion"]
supersedes: ""
superseded_by: ""
---

# ADR-0006: Git-based course distribution and import

## Status

**Proposed** | Accepted | Rejected | Superseded | Deprecated

Proposed on 2026-09-20. Acceptance is a separate human decision and is not
implied by merging this record or by any implementation that accompanies it.

## Context

Producing a course is expensive and non-deterministic. `scripts/digest_pdf.py`
sends every requested page to Azure Document Intelligence and a vision model,
and an agent then maps the resulting digest into `clew/v1` notes. Today that
whole pipeline runs once per reader, because nothing describes how a finished
course travels from the person who produced it to the people who read it.

The repository stops at both ends of the gap. [ADR-0003](adr-0003-pdf-digestion.md)
deliberately ends at an intermediate `document.md`, and
[ADR-0001](adr-0001-unified-clew-content-structure.md) defines the course
structure but assumes the course already exists inside an authorized vault.
`.clew.local.json` records where that vault is; nothing fetches, places, updates
or records a course in it.

Four properties of `clew/v1` constrain any answer:

- The validator's fixed layout rejects unknown files inside a course directory,
  and `support/` admits only `source-map.json` and `verification.json`. Import
  bookkeeping cannot live inside the course it describes.
- Shared concepts are vault-level and collectively owned. Adding a course is not
  permission to redefine a concept another course depends on.
- A concept requires a nonempty `evidence` list of links that resolve. A concept
  grounded only in a course the reader does not have is a broken note, and
  dropping the links leaves an invalid one.
- Section IDs, navigation and provenance are derived artifacts whose correctness
  the validator checks: hashes, `previous`/`next` chains, `source_refs` and
  `## Contents` lists. A language model cannot compute SHA-256 and is unreliable
  at the rest, so producing them by hand wastes exactly the tokens this decision
  is meant to save.

The same person may occupy either role. A learner working alone from a teacher's
PDF is a producer for their own repository; the roles differ by permission, not
by tooling.

## Decision

Publish a course as ordinary files in a git repository whose root is shaped like
a vault: `courses/<course-id>/…` beside one shared `concepts/` directory. The
producer validates the repository by pointing the existing validator's `--vault`
at its root. No bundle format, archive, manifest or registry is introduced.

Import is a deterministic Python script bundled with a new first-party
`clew-import` skill. It stages the requested courses with a shallow, blobless,
sparse `git` checkout, or reads a local directory, then copies one or more
courses plus the shared concepts those courses reference. A plain copy is
insufficient, so the script also reconciles concepts and records provenance.

Concept reconciliation is additive by default. When an incoming concept matches
the vault's copy apart from its `evidence`, the two lists are merged so both
courses' sections are cited. When the canonical definition, title, summary or
relationship links differ, the import stops and reports the conflict; it
proceeds only with an explicit `--on-concept-conflict keep|replace`. When a
referenced concept's evidence resolves entirely into courses the reader is not
importing, the import stops and names the courses that would satisfy it.

Provenance lives in a vault-level `.clew/imports.json`, outside every course
directory. It records the source, ref, resolved commit and the hash of each
imported course file. Re-import replaces files that are untouched since the last
import and refuses, with a list, when a file was modified locally, unless
`--force` is given. Shared concept notes are merged rather than hash-guarded,
because another course may legitimately have added evidence to them.

Production gains a deterministic helper, `scripts/clew_finalize.py`, which
regenerates only what is mechanically derivable from the authored sections and
the source map: navigation chains, `source_refs`, `## Contents` lists, source
hashes and page counts, and the verification record's hashes and page coverage.
It preserves author-owned `fidelity`, `checks`, `limitations` and prose, never
promotes a section to `verified`, and offers `--check` so a commit can be gated.

The producer role is a Copilot custom agent, `.github/agents/course-creator.md`,
composing the existing `ingestion` and `course-content` skills, the finalize
helper and the validator, and owning the git publishing steps. Both scripts
reuse `src/vault/storage.py` for vault resolution, symlink refusal and atomic
writes rather than duplicating them, and neither adds a module under `src/`.

## Consequences

### Positive

- **POS-001**: A course is converted once. Readers pay a deterministic file copy
  instead of repeating Document Intelligence and vision-model requests.
- **POS-002**: The distribution format is the content format. There is no second
  schema to keep in step with `clew/v1`, and the existing validator checks a
  repository directly.
- **POS-003**: Corrections propagate. A producer fixes a section, and readers
  re-import at a recorded commit rather than rebuilding from the PDF.
- **POS-004**: Shared concepts accumulate evidence across courses instead of
  being duplicated or silently overwritten.
- **POS-005**: Moving hashes and derived navigation into a deterministic helper
  removes the most error-prone and token-expensive part of authoring.

### Negative

- **NEG-001**: Cross-course concept dependencies can make a single-course import
  fail until the reader also imports the grounding course. The report explains
  the remedy, but the first attempt still stops.
- **NEG-002**: Local edits to imported course files conflict with updates. The
  reader must re-apply them or pass `--force` and lose them; the design offers no
  merge.
- **NEG-003**: Provenance in `.clew/imports.json` is a new vault-level artifact
  that must stay consistent with the course files beside it.
- **NEG-004**: `git` becomes a runtime requirement for importing, and private
  repositories depend on credentials the script never manages.
- **NEG-005**: Neither script can establish legal rights. A repository can still
  distribute material its producer was not permitted to share.

## Alternatives Considered

### Self-contained course bundles with a manifest

- **ALT-001**: **Description**: Give each course directory a `clew-course.json`
  manifest listing its files, hashes and concept dependencies, and distribute or
  archive that directory independently of any vault shape.
- **ALT-002**: **Rejection Reason**: The validator rejects unknown files inside
  a course, so the manifest would have to live outside the thing it describes
  anyway. It also introduces a second schema beside `source-map.json` and
  `verification.json` for information those records already carry.

### One mini-vault per course in the repository

- **ALT-003**: **Description**: Publish `<course-id>/courses/<id>/` beside
  `<course-id>/concepts/`, so each course ships its own private concept copies.
- **ALT-004**: **Rejection Reason**: Duplicated concept notes contradict the
  shared canonical definition `clew/v1` requires, and repeated import would
  scatter competing definitions of the same concept across one vault.

### Always overwrite concepts on import

- **ALT-005**: **Description**: Treat the incoming repository as authoritative
  and replace any colliding concept note.
- **ALT-006**: **Rejection Reason**: Adding a course is not permission to
  redefine a shared concept, and a silent overwrite would rewrite the
  definition another already-imported course depends on.

### Auto-import the dependency closure

- **ALT-007**: **Description**: When a concept's evidence points into other
  courses, fetch those courses too, transitively, and report what was added.
- **ALT-008**: **Rejection Reason**: A reader asking for one course would
  receive unrequested material whose size depends on the producer's concept
  graph. Naming the missing courses keeps the choice with the reader.

### Distribute through a package registry or hosted service

- **ALT-009**: **Description**: Publish courses as versioned packages to an
  index, with a client that resolves and installs them.
- **ALT-010**: **Rejection Reason**: Disproportionate for Markdown and PDFs that
  git already versions, and it would add hosting, authentication and release
  machinery the project does not need to prove the workflow.

## Implementation Notes

- **IMP-001**: Import stages into a temporary directory, applies the validator's
  fixed-layout whitelist to the staged content, and refuses symlinks, reparse
  points and paths escaping the course directory, so an import cannot place
  arbitrary files in a vault.
- **IMP-002**: Writes are confined to `courses/<id>/`, `concepts/` and `.clew/`.
  Nothing touches the reserved `model/` or `artifacts/` paths, `.clew.local.json`,
  or any learner record.
- **IMP-003**: The destination vault resolves through `vault_path()`, so
  `--vault` is an override rather than a required argument. Content roots, being
  legitimately inside the clone for the bundled example, are validated separately
  from the learner-vault rule that forbids in-clone paths.
- **IMP-004**: Concept merging reads frontmatter with PyYAML for comparison but
  writes surgical line edits, so key order, quoting and formatting survive. The
  `## Evidence` body section is updated together with the frontmatter list.
- **IMP-005**: The import script performs its own structural checks and does not
  require the APM-managed validator to be installed; the skill directs the agent
  to run `validate_clew.py` on the result.
- **IMP-006**: `clew_finalize.py` regenerates derived artifacts only. Author
  `fidelity`, `checks` and `limitations` are preserved, and `--check` reports
  drift without writing.
- **IMP-007**: Tests use synthetic repositories, vaults and generated PDFs. No
  real learner record or third-party course material enters the test suite.
- **IMP-008**: The bundled `examples/reader-vault` becomes a valid `clew/v1`
  vault with two courses sharing a concept, so the merge path, the reader and
  strict validation all have a genuine fixture.

## References

- **REF-001**: [ADR-0001: Unified Clew content structure](adr-0001-unified-clew-content-structure.md).
- **REF-002**: [ADR-0003: Standalone Azure-assisted PDF digestion](adr-0003-pdf-digestion.md).
- **REF-003**: [ADR-0004: Compact learner memory and hosted processing](adr-0004-compact-learner-memory-and-hosted-processing.md).
- **REF-004**: [Course distribution contract](../COURSE_DISTRIBUTION.md).
- **REF-005**: [Clew course structure](../../.agents/skills/course-content/references/clew-structure.md).
- **REF-006**: [Clew PDF provenance](../../.agents/skills/course-content/references/provenance.md).
- **REF-007**: [Copilot CLI custom agents reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference).
- **REF-008**: [Git sparse-checkout documentation](https://git-scm.com/docs/git-sparse-checkout).
