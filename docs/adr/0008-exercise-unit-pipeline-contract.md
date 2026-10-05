# ADR-0008: Exercise-unit pipeline contract

- Status: Accepted
- Date: 2026-10-05

## Context

ADR-0004 lets the agent choose faithful source ranges, ADR-0007 adds anchored
question aids, and ADR-0006 publishes current notes. Their interfaces support
internal question/answer structure, but do not establish exercise-level storage
as a shared invariant. Exact coverage alone allowed whole exercise/correction
sheets to become all-text notes. A later course-only split did not repair that
missing structure.

Neither one note per source document nor one note per question is the intended
unit. Source heading depth, printed numbering, file count, and parser-safe cuts
also do not prove semantic boundaries or correction matches.

## Decision

### Store exercises; address questions inside them

Ingest creates one note per actual source exercise, retaining its shared context
and all subquestions. A correction note contains one supplied correction unit
for an exercise, with its context and answers. Independent exercises and their
corrections must not be aggregated. Questions and answers must not become
separate exercise/correction notes. Distinct supplied correction variants for
the same exercise remain possible.

Anchored `question` and `reponse` blocks provide internal structure. Preserve
source hierarchy, labels, and source order. Wrap independently addressable
questions/answers at safe boundaries; keep inseparable structures coherent
inside their owning note and explain the decision. Even an unnumbered exercise
has an anchored question. Never generate missing answers.

Note IDs identify units; note-local block IDs identify their children.
`exercise-id#^q-1` and `another-exercise-id#^q-1` are different questions.
Correction associations and answer targets must agree on the owning exercise.
Match statements and reasoning, not filenames or positional/number-only pairing.
Preserve numbering drift and report unresolved matches.

Course notes cover coherent subtopics, retaining related statements, proofs,
figures, and context. Review meaningful numbered peers independently of Markdown
heading depth; neither a size cutoff nor automatic heading splitting is used.

### Assign ownership at the stage boundaries

**Ingest establishes units and internal structure.** The agent reads all selected
content and reviews course, exercise, and correction granularity. Parser-backed
outlines expose candidates and safe boundaries, not pedagogical decisions.
Normal plan checks reject aggregation, question/answer-per-file fragmentation,
and omitted structural blocks. Course grouping and misleading candidates need
explicit note- and source-scoped reasons shown before approval. Exceptions do
not authorize aggregating real exercises or fragmenting one into question notes.
An unsafe exercise boundary is a visible blocker, not permission to break source
syntax or quietly relax the contract.

**Enrich preserves units.** Existing source files, IDs, source projection,
anchors, and associations remain intact. Question-scoped `type: help` notes are
auxiliary teaching additions, not finer source exercise/correction units.
Supplied answer links must target questions of the correction's owning exercise.
Unresolved matches require a decision before dependent explanations are added.

**Generate presents units.** Exercise views are grouped by resolved owning note
identity. Internal blocks determine question views and supplied-answer panels,
including when several question or heading selectors refer to the same exercise.
Selected shared context accompanies its unit. Duplicate/overlapping question
selections are explicit errors. Do not invent structure or teaching content.

Generate still reads current notes without producer installations, retained
Import text, `ingest.json`, snapshot validation, or approval hashes. Native Ingest
content works before optional Enrich. Publication never splits or changes notes.
Keep the existing offline, HTML-first templates and interactions.

### Keep the change small and portable

Reuse existing note types, schemas, roles, source selectors, relationships,
evidence, and issues; do not add a unit ledger or cross-skill runtime imports.
Each skill states the full operational contract inside its portable directory.
Executable tests and synthetic fixtures remain repository-owned.

This implementation concerns fresh generation. Historical record handling,
migration, and compatibility are deferred, not permanently excluded by this
decision. Do not change user archives as part of establishing this contract.

## Consequences

- Exercise-level notes remain readable without multiplying files for questions.
- Internal stable addresses support precise enrichment and granular HTML.
- Fidelity checks no longer substitute for reviewing omitted source structure.
- Candidate outlines and scoped exceptions expose decisions, but cannot prove
  semantic matching or pedagogical coherence; agent review remains necessary.
- Strict checks can block unsafe or ambiguous inputs rather than publish a
  success-shaped aggregate. User approval is still required for concrete writes.
- These rules refine ADR-0004's granularity, ADR-0007's preservation/ownership,
  and ADR-0006's view grouping without replacing their stage independence,
  retention, permission, or runtime decisions.
- Whole-document grouping and question-per-file storage were rejected because
  they confuse source units with either import packaging or presentation.
