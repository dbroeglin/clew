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
applicable records, and the [learner-model contract](docs/LEARNER_MODEL.md).

For significant decisions, use the APM-managed
[ADR skill](.agents/skills/create-architectural-decision-record/SKILL.md) and
[template](docs/adr/template.md). New records start Proposed; lifecycle changes
require explicit human approval. Keep the index and relationship links
consistent, and preserve historical records.

## Locate the selected vault

The learner creates an external vault outside this clone. Courses follow the
installed `course-content` 3.0.0 `clew/v1` contract under `courses/`; learner
memory and personal work use the separate reserved `model` and `artifacts`
roots.

Study plans have one separate first-party output location:
`<configured-vault>/Learning/Plans/`. These are ordinary Markdown work products,
not a new learner-memory root. Use `study-plan` to create requested plans or
make explicitly requested checkbox edits; preserve the student's manual work.
Showing or continuing a plan does not write it, and completing an exercise does
not automatically check a task. Do not route plan paths through tutor memory
capture or copy plans into `artifacts/` to satisfy that capture contract.
Create the plans directory only for an authorized save, never during setup.
The initial plan workflow targets non-Git vaults. Existing private-path Git
rules do not protect `Learning/Plans/`; pause plan writes in a Git-managed vault
for a specific privacy/tracking decision rather than changing Git policy.

Configure the absolute path of an existing external vault with:

```powershell
python -m src.vault.cli configure --vault "C:\Path\To\Existing Vault"
python -m src.vault.cli status
```

The ignored `.clew.local.json` stores `version: 1` and the canonical vault path.
Never guess a home-directory location, create a vault, use the clone as a
vault, or infer learning from configuration.

Configuration and status do not read course or learner-file contents. They
check Git tracking metadata and report reserved `model` and `artifacts` path
names without determining ownership. Configure alone adds ignore rules;
status is read-only. Never initialize or push vault Git. Ignore rules do not
untrack or encrypt content. Ask before writing where reserved-path ownership or
the learner-model format is uncertain.

## Read, tutor, and retain genuine evidence

Use `course-content` 3.0.0 for bounded reading of selected `clew/v1` courses.
Follow relevant links, cite sources, and surface ambiguity or missing assets.
Do not automatically rename, reorganize, or migrate notes. Teacher notes are
read-only unless the learner explicitly requests a change.

Use `learner-model` 3.0.0 for continuity grounded in actual goals, attempted
work, feedback, outcomes, and explicitly confirmed future preferences. Keep one
compact `model/learner.md` summary with exactly one
`<!-- clew-learning-memory: v1 -->` marker. Meaningful dated sessions use
`model/sessions/YYYY-MM-DD-topic.md` with collision suffixes. Store original
attempts once and link them; artifacts are optional.

Bare continuation, recall, and inspection are read-only. Only meaningful
learning input, decisions, or results justify writes. Correct current memory
directly, preserving actual earlier answers. Clarify ambiguous forget,
stop-use, and explicitly scoped local deletion requests. Unknown prior formats
require an explicit migration decision.

Do not create profile/index files, typed learner graphs, evidence IDs,
tombstone machinery, numerical scores, automatic schedules, or domain taxonomy.
Do not infer mastery, a diagnosed misconception, a standing preference, or a
successful outcome from insufficient evidence. Skills are instructions, not a
storage or access-control backend.

## Hosted Copilot

Ordinary tasks permit bounded task-relevant reads into hosted Copilot/model
context. Local storage does not imply local-only inference. Retrieve only enough
source and learner context for the request; course-only lookup does not require
learner records.

Never bulk-upload the model, access unrelated learners, add passive telemetry,
publish records, or grant institutional access. Local correction or deletion
cannot erase previously sent hosted context. Make no provider retention,
training, deletion, encryption, or complete network-audit promises.

## Dependencies

Runtime skills are `course-content` and `learner-model`, both pinned to
`clew-skills` revision
`d4e0880642b0870857749978417cb9561487626a`. Restore them with APM 0.28.0 and
`apm install --frozen`, keeping both `copilot` and `agent-skills` targets.

## Skill dependencies

Do not edit generated files under `.agents/skills/`. Manage dependency changes
through `apm.yml` and APM, preserving immutable pins, the lockfile, LF deployment
line endings, licenses, and notices. Test with synthetic notes and disposable
vaults, never real learner records.

`study-plan`, `synthesise`, `active-recall`, and `repair-attempt` are first-party
source directories, like `ingestion` and `clew-import`, not generated APM
dependencies. Keep these skills small and reuse installed content, memory and
Obsidian instructions. They add no package dependencies, UI or storage backend.
The tutor retains automatic capture ownership; skills must not start episodes
or duplicate memory writes.
