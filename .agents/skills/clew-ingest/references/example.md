# Small source-directed examples

These are decision examples, not fixed page limits or automatic grouping rules.

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
`sources/poly/`.

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

## Course without exercises

Create only course/section notes, their course relationships, the index,
provenance, and retained source subset. Do not create empty exercise/correction
notes or ask a model to supply them. Empty type directories are unnecessary.
