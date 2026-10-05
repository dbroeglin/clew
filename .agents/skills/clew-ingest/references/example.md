# Small source-directed examples

These are decision examples, not fixed page limits or automatic grouping rules.

## Contextual placement

The user identifies `C:\vault`. A read-only inventory lists comparable chapters
under `courses/PT/maths`, and representative notes confirm their programme and
subject. The supplied algebra source fits that context. Propose
`C:\vault\courses\PT\maths\algebre`, explain the evidence, and ask for placement
confirmation before authoring the detailed plan. Record:

```json
{
  "vault": "C:\\vault",
  "parent": "courses/PT/maths",
  "rationale": "Matches the existing PT mathematics chapters and supplied algebra material.",
  "create_parent": false
}
```

If the actual vault uses `Mathematiques/PT`, use that instead; the example is
not a required taxonomy. If the level is unclear, ask rather than invent it.
If the parent is missing, propose its exact creation and use `create_parent:
true` only after confirmation. Never fall back to the vault root or nest inside
another ingest. Final approval must still cover the full checked plan and any
missing container paths.

## One mixed source

Suppose inspection finds these safe ranges:

| Lines | Content | Selected destination |
| --- | --- | --- |
| 1-4 | Course introduction | `algebre-introduction` (course) |
| 5-20 | Vector spaces, statement and proof | `algebre-espaces-vectoriels` (section) |
| 21-25 | Exercise instructions | `algebre-exercice-noyau` (exercise), text |
| 26-30 | Question 1 | same exercise, `q-noyau` |
| 31-35 | Question 2 explicitly using question 1 | same exercise, `q-image` |
| 36-42 | Supplied answer 1 | `algebre-exercice-noyau-corrige`, `r-noyau` |
| 43-48 | Supplied answer 2 | same correction, `r-image` |

The skill chooses these boundaries after reading the material. Select all lines,
including blank lines and page markers, without gaps/overlap. Use the actual
safe ranges; never force the illustrative numbers onto a different source.

Course and section notes both go in `courses/`. The exercise/correction live in
their respective directories, and one retained bundle subset lives under
`sources/poly/`, with its PDF beside `document.md` and optional `figures/`.
There is no inner `source/` folder in the ingest output.

An exercise spanning original PDF pages 2 and 4 gets separate Sources links:
`[page 2](../sources/poly/chapitre.pdf#page=2)` and
`[page 4](../sources/poly/chapitre.pdf#page=4)`. A partial import starting at page
3 links its index to `sources/poly/chapitre.pdf#page=3`, not page 1. Retained
Markdown and its source-authored links stay unchanged.

Question dependencies and matches:

```json
{
  "rel": "needs",
  "origin": "algebre-exercice-noyau#^q-image",
  "target": "algebre-exercice-noyau#^q-noyau",
  "evidence": [{"source": "poly", "start": 31, "end": 35}]
}
```

Also record the section's course parent, correction's exercise association, and
each established answer's `question` link, with their real source evidence.
The script rejects a forward dependency. The agent rejects a plausible but
unsupported dependency even if the script would accept it.

## Several sources

Select a course bundle, exercise bundle, and correction bundle explicitly.
Assign IDs `cours`, `feuille`, and `corrige`. Each source's entire imported
Markdown gets its own complete range coverage, and each retained subset goes
under its own `sources/<id>/`.

The correction may refer to a question in the exercise source; the evidence
records the supplied labels/text used to match them. Identically named PDFs or
`figures/figure-1.png` assets never collide because source IDs scope their copies
and rewritten links. Notes can contain parts from more than one selected source.

If a correction's numbering is ambiguous, preserve its answer block, omit the
uncertain relationship, and add an issue explaining the uncertainty. The output
validator will report the unmatched answer as well.

## Several exercises, not several question files

If the exercise source contains two exercises with two questions each, create
two exercise notes, each with its context and two anchored question parts.
Two corresponding supplied correction units become two correction notes, each
with its own answer parts. Do not create one sheet note or four question notes.
Shared sheet instructions remain faithfully assigned in source order, with
their intended context shown in the plan.

Both exercises may use local anchors `q-1` and `q-2`: their full note/block
addresses differ. A correction labelled "Exercise 3" may answer the exercise
labelled "Exercise 2" if the supplied content establishes numbering drift.
Retain the printed labels and record the actual matching evidence; do not zip
the inventories or change the source numbering.

Enrich can add question-scoped help notes without moving these source units.
Generate presents two exercises and four question views directly from the
internal blocks, even before enrichment.

## Course without exercises

Create only course/section notes, their course relationships, the index,
provenance, and retained source subset. Do not create empty exercise/correction
notes or ask a model to supply them. Empty type directories are unnecessary.
