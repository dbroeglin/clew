# ADR-0008: Document-internal learning-unit contract

- Status: Accepted
- Date: 2026-10-05

## Context

Source file identity and exercise identity are different. Whole-document
storage needs stable addresses without losing shared context or multiplying
question-sized files.

## Decision

Import preparation keeps one complete note per PDF. Inside it, sections,
exercises and supplied correction units have explicit source scopes.
Sections navigate by existing headings; their scope IDs are not native anchors.
Exercises/corrections have native entry anchors. Each question/answer has one
valid enclosing owning unit. Course statements
have individually anchored callouts where safe.

Preserve original headings and hierarchy; no size cutoff or automatic heading
split defines semantic units. Only sections may contain other units.
Keep independently addressed question/answer callouts at top level: Obsidian
cannot address parts inside enclosing callouts/quotes/tables.
Entry anchors navigate to units, not native embeds of all following content.

IDs are assigned once and reused, not regenerated from headings/line hashes.
Complete addresses identify document plus local block ID. Corrections link
verified exercise units; answers link verified questions of that same exercise.
Match statements/reasoning with source evidence, never numbering alone.
Variants are allowed; missing matches stay unlinked with visible warnings.

Use relative Markdown links with exact `Exercise` and `Question`
labels. Correction-to-exercise unit links use their own footer line. In a
learning callout, put the verified relationship link and compact PDF provenance
on one final quoted line, relationship first and PDF last, separated by ` · `.
Keep one blank quoted line before the footer, collapse duplicate blank quote
lines only at that terminal boundary, preserve internal body spacing, and add
no quoted blank lines after links. The validator uses these conventions plus
destination roles/kinds and ownership, not filename guesses or plugin metadata.
Derive question/answer ownership from enclosing scopes without redundant parent
backlinks. Keep verified cross-document links after supplied content. Prepare
anchors now for future Aides references to questions, supplied answers and
precise course passages. Aid authorship is not an Import responsibility.

Current Enrich/Generate runtimes still use their legacy one-note-per-exercise/
correction contract. Their document-internal-unit refactors are deferred.
Do not claim compatibility or modify user archives to simulate it.

## Consequences

Storage stays faithful and simple, while future learning/publishing views can
select units. Validation proves typed structure, not semantic matching.
