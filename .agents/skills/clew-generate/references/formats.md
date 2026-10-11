# Current documents and publication layout

## Input contract

Source notes have `clew_schema: 1`, a unique `id`, `type: document` and a
`role` of `course`, `exercise`, `correction`, `mixed` or `unknown`.
Chapter indexes have `clew_schema: 1` and `type: chapter`.
Help notes have unique IDs, `type: help`, and question/optional correction
references. Enrich's new aids use `schema_version: 1`.

A selected chapter folder or its `index.md` expands recursively to visible
document/help Markdown, excluding the index, hidden/configuration entries,
`.clew/` and `sources/`. No preparation record or baseline is read. Explicit
files preserve input order; discovered files have deterministic path order.
All IDs must be unique across selected notes. Roles never come from filenames.
Legacy source types and notes without current frontmatter are unsupported.

An exercise/correction unit is a source span:

```markdown
%% clew:unit exercise ex-1 %%

## Exercise 1

Exercise ^ex-1

Shared source instructions.

> [!question] Question 1
>
> Supplied question text.
>
> [PDF p. 1](sheet.pdf#page=1)

^q-1

[PDF p. 1](sheet.pdf#page=1)

%% /clew:unit ex-1 %%
```

Sections use `%% clew:unit section section-id %%` with matching closing
comments and navigate by actual headings. Their IDs are private bookkeeping,
not generated block anchors. Only sections may enclose other units.
Questions/answers must have unique native block anchors and one enclosing
exercise/correction scope. Inline `Exercise ^ex-1` / `Correction ^corr-1`
entry paragraphs are navigation scaffolding, hidden in HTML but addressable.
An entry anchor reused on supplied text, or a human-edited entry paragraph,
retains that text; only the exact generated navigation label is hidden.
The native entry block does not embed every following paragraph.

Current course statement callouts (`definition`, `theorem`, `property`, `lemma`,
`proposition`, `corollary`, `example`, `remark`, `proof`) retain their supplied
titles and text, without displaying Obsidian wrapper syntax. Block selectors
select the entire anchored statement, not its interior. Source comments are
hidden; code/math lookalikes remain literal content. LF, CRLF and CR are supported.

## Layout version 1

```json
{
  "schema_version": 1,
  "title": "Sequences",
  "output": "sequences.html",
  "notes": ["chapter"],
  "courses": ["course"],
  "exercises": ["sheet#^ex-1"],
  "questions": {
    "sheet#^q-1": {
      "corrections": ["solutions#^r-1"],
      "method": null,
      "hints": ["aid-q-1#^hint-1"],
      "explanations": ["aid-q-1#^explanation"],
      "courses": ["course#Geometric limits"]
    }
  }
}
```

Required keys are `schema_version`, nonempty `title`, `output` and nonempty
`notes`. Unknown keys are rejected. Paths are absolute or relative to the layout;
the output must be `.html` under an existing parent. JSON relative paths use `/`.
The layout selects existing content; never copy or author teaching prose in it.

Optional `courses` and `exercises` arrays set reading/display order. Defaults
read `role: course` documents and publish exercise units from `exercise`/`mixed`
documents. Empty arrays suppress a role. At least one course/exercise selection
is needed. Listed correction/help notes supply targets, not independent views.

Selectors accept unique document ID, stem, filename or selected absolute path,
and wikilinks such as `[[sheet#^q-1|label]]`. Markdown references resolve relative
to their originating note; URL-encoded paths/fragments are decoded.

- `sheet`: expand its exercise scopes and retain surrounding worksheet content
  once in source order.
- `sheet#^ex-1`: publish the owning exercise scope using its entry address.
- `sheet#^q-1`: publish that question in its owning exercise with unit context.
  Several question selectors from one unit stay grouped in source order.
- `course` or `course#^theorem`: read a whole course or one anchored statement.
- `note#Exact heading`: select that heading through the next same/higher-level
  heading. Duplicate headings are ambiguous. After exact matching fails,
  inline emphasis delimiters and doubled TeX command backslashes are normalized
  for reference matching only; displayed source text is not changed.
- `note#L12-L20`: one-based inclusive physical source lines, including
  frontmatter in numbering. Select complete parser-safe parts outside
  frontmatter; never bisect a callout, paragraph, list, table, code or math.

Whole documents/heading containers expand into distinct owning exercises,
not an invented sheet-sized question. Partial selections keep a unit's
non-question context; they do not add its unselected questions. Whole worksheet
streams retain introductions, section headings, inter-unit prose and visible
review appendices. A context-only selection within a unit creates no question.
An unstructured exercise remains source prose with a warning and no question
controls. Overlaps, including whole/child or aliases, are errors.

## Corrections and ownership

Supplied answers remain inside correction scopes, with relative footer links:

```markdown
%% clew:unit correction corr-1 %%

## Correction 1

Correction ^corr-1

Shared supplied reasoning.

> [!reponse] Answer 1
>
> Supplied answer text.
>
> [Question](../Exercise-sheet/sheet.md#^q-1) · [PDF p. 1](solutions.pdf#page=1)

^r-1

[Exercise](../Exercise-sheet/sheet.md#^ex-1)
[PDF p. 1](solutions.pdf#page=1)

%% /clew:unit corr-1 %%
```

Exact `Exercise` / `Question` labels identify relationships; PDF links are
provenance, not matches. Relationship lookalikes in code/math do not count.
Unit association and answer links must agree on one exercise entry, including
the document identity. Identical local anchors in other documents are distinct.
If no association is declared, linked answers must still share one owner.
Unmatched answers generate warnings, not guessed associations.

Question options may override ordered `corrections`, `hints`, `explanations`,
`courses` arrays or `method` (a selector or null). Empty arrays suppress automatic
choices. Duplicate options/unused question overrides are errors.

Correction selectors target an answer or one correction unit (entry, heading,
safe range, or a document with only one unit). A whole multi-unit correction
document is ambiguous. Selected panels include that unit's non-answer context
once in source order and only answers for the published question. Variants
remain separate even inside the same source document. Explicit choices can
resolve unlinked answers but cannot contradict an established owner or target.

## Optional aids and course excerpts

```markdown
---
schema_version: 1
id: aid-q-1
type: help
question: "[[sheet#^q-1]]"
correction: "[[solutions#^r-1]]"
---

> [!hint]
> Compare the ratio with one using [[course#^theorem|the course result]].

^hint-1

> [!explanation]
> The supplied reasoning applies [[course#Geometric limits|this result]].

^explanation
```

Automatically consume ordered anchored hints and explanations. Existing method
callouts can also be consumed; multiple methods require explicit selection.
Enrich authors hints/explanations, not methods, and is not a runtime dependency.

Each aid's question must resolve to an anchored question. Its optional
`correction` must target a supplied answer linked to that question.
Explanations require that correction and appear only for selected answers.
Hints remain valid without an answer. Existing human edits are read directly;
no Enrich baseline or validator is needed.

Course links inside aids register exact selected course heading/block excerpts
and open them in the side panel, even without the whole-course reading view.
Whole-course aid links are rejected as imprecise. No extra layout mapping is
needed. Every referenced note must be among the selected inputs.

## Rendering and persistence

Python renders CommonMark, tables, dollar math, safe headings/blocks and
recognized callouts. Native templates provide the existing interactive views.
Missing/ambiguous/unpublished note targets are errors, not broken links.
Visible review warnings remain content and are also reported.

Local PNG/JPEG/GIF/WebP images, including image wikilinks, are embedded after
signature checks. Raw HTML is escaped; SVG, remote figures, note transclusions
and Dataview are rejected. Active URL schemes are not emitted. HTTP(S)/mailto
links remain optional navigation. Local PDF links preserve `#page=N` and are
rebased to the output location; missing PDFs warn, and relocation can break
external PDF links without affecting offline reading.

Bundled MathJax uses base/AMS/newcommand/configmacros and local SVG fonts.
Dynamic/active TeX is rejected; browser math failures remain visible.
No claim of mathematical correctness follows from successful generation.

`--check` reads fresh inputs and builds in memory without writing. Output
parents must exist. Existing HTML requires explicitly requested `--overwrite`;
completed rendering precedes atomic replacement. Source notes and producer
records are never modified.
