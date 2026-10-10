# ADR-0003: Autonomous, portable skills

- Status: Accepted
- Date: 2026-10-04

## Context

A copied skill must operate without repository-specific runtime knowledge.
Shared development environments should not undermine that portability.

## Decision

Each skill owns complete instructions, scripts/assets, direct dependencies,
configuration templates, workflow evals, licenses and provenance. Runtime
rules must be stated in the skill, not delegated to repository ADRs/READMEs.
Explicit external services/platform integrations are allowed.
No undeclared sibling runtime imports.

Executable script tests and fixtures belong outside skills in
`tests/<skill_name>/`; they are development assets, not runtime dependencies.
Workflow evals may remain skill-owned.

Skills own dependency intent; hosts own resolution, locks, environments and
secrets. Clew uses shared UV resolution and an npm workspace for Import's
MathJax dependency. Standalone copies resolve from their own manifests.
Setup is separate and visible; routine inspection never installs packages or
edits host manifests/locks. Fail incompatibilities explicitly.

Keep the README focused on end-user skill calls. Put setup, contracts, direct
commands and limits in `docs/skills.md`, while keeping portable instructions
complete. Every change updates affected docs, examples, guidance and ADR index
in the same change. Revise ADRs in place; Git preserves prior decisions.

## Consequences

Portable artifacts remain self-contained, while development shares efficient
resolution and external tests. Documentation defects are completion defects.
