# ADR-0003: Autonomous, portable skills

- Status: Accepted; script-test ownership partially superseded by ADR-0004; refined by ADR-0011
- Date: 2026-10-04

> **Supersession note:** [ADR-0004](0004-faithful-multi-bundle-ingest.md)
> places executable script tests and fixtures outside skill directories, in
> repository-owned suites. Workflow evaluations may remain bundled. Runtime
> portability and the remaining rules in this record are unchanged.
> **Refinement:** [ADR-0011](0011-npm-workspace-and-offline-import-mathjax.md)
> extends skill-owned dependency declarations and host-owned resolution to an
> npm workspace for Import's local MathJax checker, with root installation and
> a standalone Node dependency contract.

## Context

Clew is intended to produce agent skills that can be copied into another
compatible agent environment and remain understandable, installable, testable,
and usable there. A skill is a distributable artifact, not merely an entry point
into the Clew repository.

The first PDF Import skill contains its executable and detailed workflow, but it
also refers to repository ADRs for its purpose and relies on repository-root
dependency, configuration, and test files. Those references work inside Clew but
make the copied skill incomplete. ADRs record why Clew made a decision; they must
not be required operating instructions for an exported skill.

At the same time, creating one virtual environment per skill is wasteful when
several skills are developed or used together in Clew. We want skills to own
their dependencies without giving up a shared development environment and lock.

Repository documentation is also part of the product. As skills and architecture
evolve, tasks and pull requests must not leave README files, skill instructions,
ADRs, examples, or commands contradictory, incomplete, or factually stale.

## Decision

### The skill directory is the portable artifact

Each first-party skill must contain everything specific to understanding,
installing, operating, maintaining, and validating that skill. As applicable,
this includes:

- Complete behavioral and safety instructions in `SKILL.md`.
- Executable code and other runtime assets.
- Direct dependency declarations and supported runtime versions.
- Configuration templates that contain no credentials.
- Workflow evaluations, licenses, and provenance. The original decision also
  bundled script tests and fixtures; that clause is superseded by ADR-0004,
  which places them in repository-owned `tests/<skill_name>/` suites.
- Commands that work when the skill is hosted by Clew and enough information to
  adapt or run them when the skill directory is copied elsewhere.

A skill may depend on platform capabilities, external services, or another skill
when those dependencies are explicit in the skill artifact. It must state what
is required, why it is required, and how absence or failure is reported. It must
not silently rely on repository-specific files, conventions, source history, or
knowledge from documentation outside its directory.

Repository documentation may link to a skill, but the skill must not require the
reader or agent to open Clew's README, ADRs, or contributor guidance to operate
correctly. If an ADR contains a constraint needed at runtime, copy the resulting
rule into the skill in operational language. Keep the rationale in the ADR.
Avoid duplicating rationale or using an ADR reference as a substitute for an
instruction.

Cross-skill dependencies are allowed only when they are deliberate and explicit.
The dependent skill must identify the other skill and the contract it consumes.
Shared implementation that is not an explicit skill dependency must be packaged
as a declared runtime dependency or included in the skill.

### Skills own dependency declarations; hosts own resolution

Every skill with Python dependencies is a UV project with its own
`pyproject.toml`. It declares its direct dependencies and Python compatibility
inside the skill directory.

Clew is a UV workspace whose members are the skill projects. The workspace root
owns the shared `uv.lock` and `.venv`, and `uv sync --all-packages --locked`
installs all member dependencies into that single environment. Commands select
the relevant workspace package when needed.

When a skill is copied outside Clew, its own `pyproject.toml` remains sufficient
for UV to resolve and install a local environment. The host may create its own
lockfile. Therefore:

- The skill owns dependency intent and compatible version constraints.
- The host owns the exact combined resolution, lockfile, and environment.
- A host must fail visibly on incompatible skill constraints; it must not remove,
  weaken, or override a skill's constraints silently.
- A skill must not edit an importing host's dependency declaration or lockfile
  during normal operation. Installation or synchronization is a separate,
  visible step that follows the host's approval rules.

This gives Clew one efficient environment while preserving enough metadata for a
skill to install its dependencies independently.

### Host integration must remain explicit

A host may provide shared facilities such as a workspace lock, virtual
environment, credentials file location, agent runtime, or platform tools. The
skill must detect or be told about that integration and describe it explicitly.
It must also retain a standalone path that does not assume Clew's directory
layout.

Host-owned secrets and local configuration are not bundled into a skill.
Configuration examples and validation rules are bundled; real values remain
local and untracked.

### Documentation integrity is a completion criterion

Every task and pull request must assess its documentation impact. Before the work
is considered complete:

1. Update all affected instructions, examples, READMEs, ADR indexes, ADR status
   links, and skill documentation in the same change.
2. Check that public repository documentation, contributor guidance, skill
   instructions, code behavior, and tests describe one coherent system.
3. Remove or correct stale commands, paths, capabilities, dependencies, and
   claims. Do not preserve known mistakes merely because they predate the task.
4. If no documentation changes are needed, verify that the implementation does
   not invalidate existing documentation.

Reviews must treat contradictory, incomplete, or incorrect documentation as a
defect, not optional follow-up work. Historical ADR rationale remains historical,
but add a new ADR or an explicit supersession note when a later decision changes
the operative architecture.

This ADR supersedes the repository-root dependency ownership, configuration
template ownership, and root test-location decisions in
[ADR-0002](0002-pdf-import-skill-and-project-runtime.md). ADR-0002's PDF Import
behavior, safety gates, artifact contract, and pinned implementation provenance
remain accepted; [ADR-0005](0005-conservative-import-and-latex-leakage-review.md)
later permits prompt and review-check changes to that baseline.

## Consequences

- A copied skill is a meaningful artifact rather than a repository-dependent
  fragment.
- Runtime rules may appear both in an ADR and in a skill, but with distinct
  purposes: rationale in the ADR and complete operational instructions in the
  skill.
- Skill directories include their runtime validation assets and workflow
  evaluations; executable script tests and fixtures remain outside them per
  ADR-0004.
- Clew retains one lockfile and virtual environment for efficient development,
  while standalone hosts may resolve a different compatible lock.
- Adding a skill requires workspace integration and combined dependency
  resolution; incompatible constraints are surfaced centrally.
- Documentation work becomes part of every change's definition of done, adding
  review effort but reducing drift and misleading examples.
