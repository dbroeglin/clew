# Agent guidance

## Architecture decisions

Before proposing or changing architecture, consult the [ADR index](docs/adr/README.md).
Read only the records relevant to the task; the index is the discovery entry point,
not a requirement to load every ADR.

When adding or revising a decision, follow
[ADR-0000](docs/adr/0000-record-architecture-decisions.md) and update the index in
the same change.

## Autonomous skills

Treat every first-party skill directory as a portable artifact. Follow
[ADR-0003](docs/adr/0003-autonomous-portable-skills.md): keep complete operating
instructions, executable assets, direct dependency declarations, configuration
templates, tests/evals, licenses, and provenance inside the skill as applicable.

Do not make a skill depend on repository ADRs, READMEs, tests, configuration
templates, dependency manifests, or undocumented directory conventions. If a
runtime rule is derived from an ADR, state the complete operational rule in the
skill; an ADR reference is not an instruction. Dependencies on another skill,
platform capability, external service, or host integration must be explicit.

## Documentation integrity

For every task and pull request, assess documentation impact before considering
the work complete. Update all affected public documentation, contributor
guidance, skill instructions, examples, commands, and ADR index/status links in
the same change.

Verify that documentation is coherent with the implementation and with other
documentation, complete for its intended reader, and factually correct. Remove
or correct stale paths, commands, capabilities, and claims. If no documentation
change is needed, explicitly verify that the task did not invalidate existing
documentation. Treat documentation defects as task defects, not optional
follow-up work. See ADR-0003 for the full rationale and contract.
