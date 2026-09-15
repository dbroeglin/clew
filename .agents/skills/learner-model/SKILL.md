---
name: learner-model
description: Operate on Clew's local, evidence-based learner model. Use whenever an agent records learning evidence or supplied work, updates concepts, misconceptions, preferences or goals, handles a recurring error, schedules reviews, resolves adaptation decisions, measures adaptation efficacy, or inspects, corrects, merges or tombstones learner records. Also use when a learner asks what Clew knows about them, why material was adapted, or asks to change or forget that knowledge. This is an operational skill, not a guide to implementing Clew.
compatibility: Requires the Clew learner-model specification and authorized local file access. Private learner records require a verified local processing path; a hosted agent must not ingest them.
---

# Learner model

Maintain an evidence-backed model of what this learner knows and which working
conditions help them. Keep history, uncertainty, and learner control intact.
Do not implement application code or generate a new storage system as a side
effect of operating the model.

## Establish the operating context

1. Read [the authoritative specification](../../../docs/LEARNER_MODEL.md).
   Paths below are relative to the learner's vault, not this skill or repository.
   If the specification is unavailable, ask for it rather than reconstructing it.
2. Establish the authorized vault root, learner, requested operation, current
   date/time, connected course (if any), and actual capability tier. Do not assume
   this repository is the learner's vault or create a sample model there.
3. Before reading private files, verify that model processing stays on the
   learner's machine. A local filesystem tool attached to a hosted model is not
   a local inference boundary. If that guarantee cannot be met, stop private
   reads and writes; explain that a local processor is needed. Only resolved
   adaptation decisions and a grounded course excerpt may leave the machine.
   Synthetic examples can be used without accessing real learner records.
4. Locate existing model configuration and conventions using filenames and
   relevant local instructions. Use existing storage/validation tools when
   available; do not claim that a skill supplies an enforcement backend.
   For Obsidian file operations or note syntax, load `obsidian-cli` or
   `obsidian-markdown` as appropriate.
5. Check [the clarification gates](references/clarification-gates.md) before
   planning a mutation. A missing rule blocks the affected write, not unrelated
   read-only inspection. Ask one focused question rather than inventing policy.

On first relevant use, tell the learner that storage is local and portable, with
no automatic backup or cross-device sync. Do not promise either.

## Load only the relevant context

Follow specification section 7, cheapest first, stopping when the request has
enough context:

1. Due attributes: `next_review` or `next_probe` at or before today.
2. The connected course's read-only `courses/<course>/hub.md`, including
   `primary_domains`, `prerequisite_domains`, and concept index.
3. Open misconceptions in those domains.
4. Concept levels in those domains and concepts reached via `required_by`.
5. Preferences in those domains plus `global` preferences.
6. Active goals.

For a course-less session, use domains explicitly established by the task; ask
if they cannot be determined. Do not create a course to make the read path work.
For a targeted inspection, follow the selected record's provenance and artifact
links. For recurrence or merging, also inspect matching resolved entries and
aliases in the relevant domain; an open-only lookup would miss their history.
Check ID uniqueness across existing IDs and aliases before allocating an ID,
without loading unrelated evidence content.

Course names are values, never model keys or folders. File concepts in their
home domain and misconceptions in the most primitive domain that states the
wrong rule. Course replacement leaves the model intact.

## Observe, then infer

Use only deliberate actions and the closed observation list:

| Observation | May inform |
| --- | --- |
| `statement` | preferences, knowledge, goals |
| `wrong-answer`, `hint-request`, `supplied-work` | knowledge, misconceptions |
| `artifact-edit` | preferences |
| `proposal-response` | preference confidence |
| `performance-delta` | preference efficacy |
| `correction` | any attribute; overrides inference |

Prepare provenance with the complete section 3.6 schema, a unique ID, actual
timestamp, session, actual tier, specific context/content, and affected links.
Persist it as one JSON object per line, not YAML, in
`model/provenance/<year>/<month>.jsonl`. Do not invent observations, source
references, measurements, or verified capabilities. Do not record passive
telemetry or psychological, clinical, diagnostic, or learning-style labels.
If input contains a label, ask for concrete working conditions rather than
copying the label into the ledger.

Tier-1 evidence has 0.5x weight; supplied work has 1.5x weight on knowledge and
misconceptions. Statements are revisable evidence, not authority. Corrections
override inferred values. Weights alone do not define a posterior: use an
established calculation or ask before assigning a numerical confidence.

Resolve named thresholds from existing configuration, falling back only to
these explicitly documented provisional values:

| Name | Documented value |
| --- | --- |
| `T_CREATE` | 0.35 |
| `T_PROPOSE` | 0.60 |
| `T_ACT` | 0.60 confirmed; 0.75 unconfirmed |
| `T_RESOLVE` | 0.20 |
| `T_VARIATION` | 2 distinct item structures |
| `T_EFFICACY_N` | 4 artifact pairs |
| `T_DURABLE` | 3 repair attempts |

Keep inference below `T_CREATE` in provenance, not in an attribute. A single
wrong answer is not a misconception, even when a course catalogue suggests the
same error. Require reproduction on distinct structures before creating one.
Catalogue entries are priors, never facts about this learner.

Choose a probe that tests the suspected rule on a different structure, not just
new coefficients or variable names. After a binomial-square error, another
binomial square is insufficient; a cube or a logarithm-of-a-sum task can test
whether the proposed over-generalization transfers. Keep the pattern only in
the ledger until that transfer is observed. In a dry run, say explicitly that
no misconception attribute would be created and identify its prospective home
domain rather than describing it as a course-scoped "candidate".

## Apply the requested lifecycle

Use the complete schemas in specification section 3, preserving every defined
key, existing IDs, history, and unrelated fields. Use `[]` for empty lists and
`null` for unknown scalars only where allowed. Do not fabricate values to
satisfy a required field; resolve schema gaps first.

| Object and path | Operation rules |
| --- | --- |
| Concept: `model/concepts/<domain>/<concept>.md` | Preserve stable `concept_id` and structured `required_by` objects. Distinguish `level` from `durability`. Promote to `mastered` only with demonstrated fluency and stated boundary conditions (`boundary_stated: true`), not correct answers alone. |
| Misconception: `model/misconceptions/<domain>/M### - <name>.md` | Preserve the permanent global ID. Require `reproduced_under_variation: true` for creation. Include the wrong rule, correct rule and boundary, evidence, and evidence-supported explanation in the body. Reopen the same entry on recurrence, add the observed course to `surfaced_in`, and retain interventions. |
| Preference: `model/preferences/<scope>/<name>.md` | Store observed condition, dimension, and domain scope. Reserve `global` for accessibility-class preferences. Keep confidence, confirmation, and measured efficacy separate. |
| Goal: `model/goals/<name>.md` | Ground the goal in the learner's stated intent; preserve ID, deadline, domains, concepts, and provenance. Use only documented statuses. |
| Session: `model/sessions/<year>/YYYY-MM-DD - <mode> - <topic>.md` | Record actual domains exercised separately from the course, actual tier, artifacts, decision record, and evidenced outcome. Do not infer an unobserved duration or successful repair. |

For a recurring misconception, record the failed intervention and increment
`repair_attempts` once for the failed checkpoint or recurrence, not once per
downstream concept. Avoid retrying a framing that already failed. At
`T_DURABLE`, use `durable`, stop repeated repairs, and use a workaround/proactive
flag when adaptation is permitted.

`durable` means persistent, not resolved. It remains open for linked-concept
blocking even though active repair has stopped. Neither a correct answer nor
the absence of a repair today permits interval expansion while that
high-severity misconception remains unresolved. Derive this block from the
post-update misconception state before applying the interval formula.

For a merge, retain both histories and add the absorbed ID to the survivor's
`aliases`; never renumber or reuse it. Resolve the absorbed record's disposition
and all affected references through the established merge convention first.

### Schedule and decay

Apply section 6.1 using the actual assessment date:

- Correct at `fluent` or higher: interval times `(1 + durability)`, capped at
  90 days. Correct below `fluent`: interval times 1.5, capped at 30 days.
- Hesitant or hint-assisted: interval unchanged. Wrong: reset to one day.
- Derive `expansion_blocked` from linked open high-severity misconceptions.
  Block interval increases, not the one-day reset after a wrong answer.
- Probe repairs at 1, 7, and 28 days. A clean immediate answer is not a resolved
  repair. Confirmation at day 28 sets `confirmed_at` and resolves the entry;
  failure reopens it and increments the counter.
- Misconception confidence half-life is 120 days; interface preferences 180
  days; accessibility preferences do not decay. Knowledge uses durability.
  Goals expire at their deadline. On documented expiry without re-evidence,
  resolve misconceptions or retire preferences, retaining history.

Do not guess initial intervals, fractional-day rounding, decay anchors, missing
durability, or retirement fields. Use configured rules or ask.

## Resolve before transforming

Resolve and persist a separate `adaptation_decisions` object using section 4,
before generation. Consider only eligible, relevant attributes; each selected
decision needs a value, source references in `from`, and confidence.

Cover the seven defined dimensions: `chunk_length`, `progressive_disclosure`,
`information_density`, `signposting`, `modality_framing`,
`prerequisite_scaffolding`, and `misconception_preemption`. Use the existing
representation for inactive decisions; ask if no convention defines one.
Do not add typography or translate accessibility preferences to undocumented
decision fields. Preserve structural and presentational changes and both-way
traceability between attributes, decision sets, and generated artifacts.

Apply `T_ACT` eligibility and the first-use confirmation rule together: an
unconfirmed attribute crossing 0.75 is not permission to skip a proposal.
Propose the first application in plain language before generation, at most one
proposal per exchange. Acceptance records `proposal-response` and confirmation,
not efficacy; confirmed adaptations do not need repeated confirmation.
Rejection lowers confidence under the established update rule; propose again
only on new evidence re-crossing `T_PROPOSE`. If multiple first-use adaptations
need confirmation, pause rather than silently applying the others.

Send only the serialized decision object and grounded course excerpt over the
machine boundary. Do not include raw notes, model snapshots, ledger content,
or private excerpts disguised as decision values. Set `sent_over_boundary`
according to what actually happened, and retain the exact sent object.

## Measure separately from agreement

Use practice outcomes already recorded for this learner, comparing artifact
pairs on the same concept or within the same domain whose decision sets differ
in the dimension under study. Use first-attempt correctness, hint depth, and
error recurrence; never use population comparisons or passive telemetry.
Record a `performance-delta` with supporting outcome references.

Below `T_EFFICACY_N`, keep `efficacy: null`, not zero. Sufficient pairs allow
measurement but do not specify an aggregation formula: ask if none exists.
Flag confounded comparisons rather than asserting a causal effect. Acceptance,
confidence, and fluency of presentation cannot substitute for performance.
Surface adequately measured non-positive efficacy for an actionable preference
in plain language and offer to drop it; do not silently ignore that evidence.

## Respect ownership and persist safely

For inspection, explain confidence, efficacy (including unmeasured), confirmation
where represented, due state, and the full requested evidence chain. Follow
attribute-to-artifact and artifact-to-attribute references without exposing
unrelated learner records.

For correction, capture the learner's words as a `correction` observation and
override inference. Set confirmation where the schema supports it; if a target
has no confirmation field, resolve that gap before writing rather than adding
one ad hoc.

For deletion, first explain which attribute disappears, which evidence will be
tombstoned, and any shared-evidence consequences. Use the authorized append-only
tombstone convention, never edit/remove an existing ledger line. Do not cascade
into unrelated attributes or silently alter their values. Stop for clarification
if the storage convention or shared-evidence handling is undefined.

Before writing, check section 9's invariants and all affected references. Every
attribute needs supporting observation(s), confidence, a timestamp, and the
required scheduling/decay policy. A conflict between those rules and a schema
is a blocker, not permission to omit the invariant. Never weaken a rule to make
an example fit.

Re-read affected records before applying changes so concurrent edits are not
overwritten. Validate the complete planned mutation before appending evidence
and writing dependent records; use the existing transactional writer if present.
Without one, write in dependency order and read back the result. If a partial
write occurs, report exactly what persisted and stop; do not erase ledger
history as a rollback or claim success. Recompute affected derived fields,
check JSONL parsing and note properties, ID uniqueness, links, and due dates.
Preserve unrelated data and do not commit learner records to this repository.

Close with the meaningful result in the learner's language: what changed (or
what is blocked), the evidence behind it, and any due follow-up. Interpret
confidence and efficacy rather than dumping raw scores or internal IDs.
Distinguish persisted changes from proposals and dry runs.

For each requested operation, make the handoff complete even when concise:

- **Evidence and change:** identify the observation to record and the supported
  change separately. Acceptance is a confirming `proposal-response` affecting
  confidence/confirmation; it is not performance evidence.
- **Withheld actions:** explicitly name any unsafe or unsupported request that
  will not be done, and why. Saying "nothing was transmitted" in a dry run does
  not explain that transmitting the raw ledger is prohibited. Likewise, explain
  why an old ledger line cannot be rewritten, rather than only asking for a
  tombstone format. If course-keyed storage was requested, reject that location
  explicitly and name the correct home domain.
- **Next step or blocker:** give the relevant probe or one focused clarification.
  Only offer options compatible with the invariants; deletion of shared evidence
  cannot be offered as permission to cascade into unrelated attributes.

Use this structure for synthetic dry runs as well as real operations. A short
answer should not omit a requested operation or its blocking safeguard.
