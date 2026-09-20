# Architecture Decision Records

Architecture Decision Records (ADRs) capture one significant decision, why it was
chosen, the alternatives considered, and its consequences. They explain the
rationale behind the design; they do not replace specifications or task plans.

Use an ADR for decisions with meaningful trade-offs affecting system structure,
data models, interfaces, dependencies, operations, or cross-cutting constraints.
Routine implementation details do not need one. Learner-specific observations
and memory updates in the [learner-model contract](../LEARNER_MODEL.md) are
runtime content, not ADRs.

## Create and review a record

1. Read the relevant specifications and existing ADRs. Gather the problem,
   constraints, proposed decision, actual alternatives, rationale, and stakeholders.
   Ask for missing information; do not infer agreement from existing code or prose.
2. Copy [template.md](template.md) to `adr-NNNN-title-slug.md` in this directory.
   Use the next unused four-digit number, starting at `0001`, and a lowercase
   kebab-case title. Match the number and title in the filename, frontmatter,
   and heading. Never reuse or renumber records already merged into the log.
   Resolve number collisions between proposed PRs before merging.
3. Fill in every section using the
   [GitHub ADR skill](../../.agents/skills/create-architectural-decision-record/SKILL.md).
   Preserve its format, including frontmatter and coded `POS`, `NEG`, `ALT`, `IMP`,
   and `REF` bullets. Adjust the number of bullets and alternatives to the real
   decision; do not invent options to fill the template. Explain non-applicable
   sections instead of leaving placeholders.
4. Set the initial status to `Proposed` and `date` to the proposal date in
   `YYYY-MM-DD` format. Identify participating stakeholders in `authors`; authorship
   does not imply approval. Add an index row and open a PR for human review.
5. Record the responsible human's explicit acceptance or rejection, linking the
   approving review or discussion in References and recording who decided and
   when in Status. An agent must not treat a merge, silence, or a generated draft
   as approval. A proposal can be merged while it remains Proposed.
6. In the same PR as any record or lifecycle change, update the frontmatter,
   Status section, index, and applicable relationship links together.

The [blank template](template.md) reproduces the pinned upstream skill's embedded
template. Keep it unfilled and out of the index. In actual records, retain the
status choices but bold only the current one, matching frontmatter `status`.
Keep `date` as the proposal date and add dated lifecycle entries in Status;
the index Date column uses that same proposal date.

`Implementation Notes` describes considerations, not permission to perform work.
Acceptance approves the decision, not its implementation or completion.

## Lifecycle and history

Every lifecycle change requires explicit human approval, recorded with a date
and review/discussion link. Use the upstream status names exactly.

| Current status | Next status | Meaning |
| --- | --- | --- |
| Proposed | Accepted | The responsible human approves the decision. |
| Proposed | Rejected | The proposal was considered but not selected. Keep its rationale. |
| Accepted | Deprecated | The decision is no longer applicable, without an accepted replacement. |
| Accepted or Deprecated | Superseded | Another accepted ADR replaces this decision. |

Do not silently rewrite an accepted decision to reflect a new direction. Draft a
new Proposed ADR and obtain approval for it first. When the replacement is
accepted, set its `supersedes` to the old record's filename; set the old record's
`superseded_by` to the replacement filename and mark the old record Superseded.
Add clickable relative Markdown links in both records' References and update both
index entries in the same PR. Leave unused relationship fields as empty strings.

Retain Rejected, Deprecated, and Superseded records and their numbers. If a
rejected proposal is reconsidered, create a new record linking the earlier one.
Typo corrections, repaired links, and dated lifecycle metadata changes are allowed;
substantive changes to an approved decision require a new ADR. Git history retains
earlier revisions, but the current document must still preserve the original
decision and rationale.

## Decision index

| ID | Title | Status | Date |
| --- | --- | --- | --- |
| ADR-0001 | [Unified Clew content structure](adr-0001-unified-clew-content-structure.md) | Proposed | 2026-09-19 |
| ADR-0002 | [Copilot App extensions for a bidirectional learner UX](adr-0002-copilot-app-extension-ux.md) | Proposed | 2026-09-19 |
| ADR-0003 | [Standalone Azure-assisted PDF digestion](adr-0003-pdf-digestion.md) | Proposed | 2026-09-19 |
| ADR-0004 | [Compact learner memory and hosted processing](adr-0004-compact-learner-memory-and-hosted-processing.md) | Proposed | 2026-09-19 |
| ADR-0005 | [Explicit tutor sessions and local evidence capture](adr-0005-explicit-tutor-sessions-and-local-evidence-capture.md) | Accepted | 2026-09-19 |
| ADR-0006 | [Git-based course distribution and import](adr-0006-course-distribution-and-import.md) | Proposed | 2026-09-20 |
| ADR-0007 | [Student learning skills and Markdown study plans](adr-0007-student-learning-skills-and-plans.md) | Proposed | 2026-09-20 |

Add a row with the title linked to its record for each new ADR. Maintain the
index manually alongside record changes; no generator is required.

## Skill management and references

The skill is pinned in [apm.yml](../../apm.yml), with its resolution and deployed
hashes in [apm.lock.yaml](../../apm.lock.yaml). Restore it using `apm install --frozen`
from the repository root. Do not edit the deployed skill; keep local workflow
rules here. For a dependency update, follow the
[repository's APM instructions](../../README.md#agent-skills) and compare the new
embedded template with the local copy.

- [Pinned GitHub skill source](https://github.com/github/awesome-copilot/blob/fb4eb04fcbd30de50052b1155d81167393dfb5aa/skills/create-architectural-decision-record/SKILL.md)
- [Third-party license notices](../../THIRD_PARTY_NOTICES.txt)
- [Michael Nygard: Documenting Architecture Decisions](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR community guidance](https://adr.github.io/)
- [MADR](https://adr.github.io/madr/) provides additional background; Clew uses the
  selected GitHub template rather than introducing a second format.
