# Working in Clew

## Discuss before implementing

Work through the design with the human developer rather than filling gaps with
an autonomous implementation. Permission to build a feature is not blanket
approval of its UX, constraints, or dependencies.

1. Ask focused questions, one at a time, to understand the intended user journey
   and the smallest useful experience. Distinguish feedback about visible UX
   from feedback about implementation complexity.
2. Research a few viable options before proposing a solution. Use the existing
   code and authoritative documentation to check feasibility. Include reuse or
   no-new-dependency options where viable; explain trade-offs and recommend an
   option rather than asking the developer to choose without context.
3. Discuss **all UX choices, constraints, and every new dependency, in any form**,
   and wait for explicit agreement before adopting them. This includes runtime
   libraries, development/build/test tools, system binaries, vendored code or
   assets, services, integrations, and agent skills. Disclose the dependency
   footprint, including transitive packages and resulting constraints; approval
   covers that disclosed proposal together, not a separate vote on each nested
   package. An undisclosed expansion requires another discussion.
4. Summarize the agreed interaction, what is in and out of scope, and unresolved
   decisions before implementation. Record decisions in the relevant design
   document or ADR. Proceed only within the agreed scope; routine code details
   may be chosen autonomously only when they do not change the agreed UX,
   constraints, or dependency footprint.

Keep the visible experience minimal. Do not add controls, metadata, dialogs,
confirmation steps, or convenience behaviors merely because they are possible.
Propose additions in terms of the user journey they serve. Simplifying the UI
does not authorize removing implementation safeguards.

Check host capabilities before committing to an interaction. If the intended
UX is unsupported or unverified, explain the gap and discuss options. Honor a
decision to defer; do not silently substitute a different workflow, invent an
API, add a workaround, or introduce another dependency.

A working prototype does not retroactively approve its choices. Keep unreviewed
choices explicitly provisional, and separate UX requirements from implementation
mechanisms in ADRs. When the developer pauses implementation for discussion,
pause your work and direct delegated agents to pause too; do not keep polishing
or expanding the implementation while decisions are pending.

## Architecture decisions

Before architectural changes, read the [ADR process and index](docs/adr/README.md),
applicable records, and relevant specifications such as the
[learner model](docs/LEARNER_MODEL.md).

For significant architectural decisions, use the APM-managed
[create-architectural-decision-record skill](.agents/skills/create-architectural-decision-record/SKILL.md)
and [ADR template](docs/adr/template.md). Ask for missing context, options,
rationale, or stakeholders rather than inventing them. New records start
Proposed; acceptance and other lifecycle changes require explicit human approval.
Acceptance is not authorization to implement. Keep the index and supersession
links consistent, and preserve historical records.

## Skill dependencies

Do not edit generated files under `.agents/skills/`. Manage dependency changes
through `apm.yml` and APM, preserving pinned versions, the lockfile, and license
notices. Keep Clew-specific guidance outside the generated skills.
