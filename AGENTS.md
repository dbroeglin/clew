# Agent guidance

## Architecture decisions

Before proposing or changing architecture, consult the [ADR index](docs/adr/README.md).
Read only the records relevant to the task; the index is the discovery entry point,
not a requirement to load every ADR.

When adding or revising a decision, follow
[ADR-0000](docs/adr/0000-record-architecture-decisions.md) and update the index in
the same change. Revise existing relevant records in place to describe the
current coherent design; use Git history for prior states rather than adding
supersession chains for revisions.

## Autonomous skills

Treat every first-party skill directory as a portable artifact. Follow
[ADR-0003](docs/adr/0003-autonomous-portable-skills.md): keep complete operating
instructions, executable assets, direct dependency declarations, configuration
templates, workflow evals, licenses, and provenance inside the skill as applicable.

Keep executable script tests and fixtures **outside skill directories**, under
repository-owned `tests/<skill_name>/` suites, as specified by
[ADR-0003](docs/adr/0003-autonomous-portable-skills.md). Test location is a
development concern, not a runtime dependency. Workflow evaluations may remain
inside the skill. Do not bundle script tests to make a skill portable.

Do not make a skill depend on repository ADRs, READMEs, tests, configuration
templates, dependency manifests, or undocumented directory conventions. If a
runtime rule is derived from an ADR, state the complete operational rule in the
skill; an ADR reference is not an instruction. Dependencies on another skill,
platform capability, external service, or host integration must be explicit.

## Documentation integrity

Keep the root README focused on the end-user workflow and calling skills.
Put runtime setup, artifact contracts, direct script commands, limitations, and
development checks in [the skills reference](docs/skills.md). Portable skills
must still contain their complete operating instructions; the reference is not
a runtime dependency.

Write and test code portably across Windows, macOS, and Linux. In particular,
do not assume a platform-specific newline: preserve or explicitly handle
supported `\n`, `\r\n`, and `\r` line endings, and derive generated text's
newline from its source when preserving document formatting. Use platform-
independent path APIs rather than hard-coded separators.

## Validation before proposing a pull request

For changes to Clew-owned code and first-party skills, identify the affected
test suites and run their focused checks before proposing that the work is ready
for a pull request. Run the applicable full suite as well when it is practical;
report any suite that remains blocked or unrun. Do not propose a pull request
while an applicable check is failing or blocked without clearly stating the
reason and the remaining validation.

When a required test dependency is missing, inspect the owning project's
manifest and lockfile, then install or restore the declared dependencies using
the documented locked setup before rerunning the check. Do not update manifests
or lockfiles just to make a test command work. This validation gate applies to
Clew-owned code and first-party skills only; exclude skills imported or managed
through APM unless the task specifically changes Clew's APM integration.

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
