# Generate layout and supported notes

## Layout version 1

```json
{
  "schema_version": 1,
  "title": "Algebre",
  "output": "algebre.html",
  "notes": ["cours.md", "exercice.md", "corrige.md", "aides.md"],
  "courses": ["cours"],
  "exercises": ["exercice"],
  "questions": {
    "exercice#^q-1": {
      "corrections": ["corrige#^r-1"],
      "method": "aides#^methode",
      "hints": ["aides#^indice-1", "aides#^indice-2"],
      "explanations": ["aides#^explication-1"],
      "courses": ["cours#Sous-espace vectoriel"]
    }
  }
}
```

Required: `schema_version`, nonempty `title`, `output`, and nonempty `notes`.
Unknown layout/options keys are rejected. Paths are absolute or relative to the
layout file; output must be `.html` under an existing parent.
Nothing requires a fixed vault layout, Ingest record, or immutable notes.

For normal Ingest content, `notes: ["C:/vault/courses/PT/maths/algebre"]`
is sufficient. A chapter directory or its schema-1 `type: ingest` `index.md`
expands to current Markdown under `courses/`, `exercices/`, and `corriges/`,
recursively within those role directories. Optional `aides/` and chapter-root
notes with `type: help` are included. Explicit files can be combined with chapter
inputs; overlapping discovered notes are included once.

Existing frontmatter supplies IDs/roles/order. Notes without a type inherit the
known directory role. Discovered roles follow course/exercise/correction/help
order; notes follow positive integer `order` metadata with deterministic ID/path
ties. Section `courses` links group sections with their parent course.
An explicit file list still preserves user-specified ordering.
No `ingest.json` content is read or validated. The index supplies chapter title
but is not itself rendered as a learning note; `sources/` and hidden entries
are excluded. A vault root is not a publication scope: first use
`inspect_notes.py <vault> --list-chapters`, then select the desired chapter.
The list operation stops at chapter roots and reports inventory-limit omissions.

Optional `courses` and `exercises` are ordered arrays of selectors. Defaults
select notes with frontmatter `type: course`/`section` or `type: exercise`.
Explicit empty arrays suppress that role. For explicit files without metadata,
specify the role; chapter-discovered notes inherit their directory role.
At least one course or exercise is required. Unselected notes can
still provide correction/help/excerpt targets; listing a note does not imply
displaying its entire body.

References accept frontmatter `id`, filename stem, filename, absolute path, or
an existing wikilink `[[id#^block|label]]`. Relative paths within ordinary
Markdown links resolve from the originating note. IDs/names must resolve
uniquely among selected notes. Selectors:

- `note`: its current displayed body, without frontmatter/known structural fields.
- `note#^block`: an existing standalone block anchor.
- `note#Exact heading`: that heading and content until the next same/higher-level
  heading. Duplicate headings are ambiguous; select a block or range instead.
- `note#L12-L20`: physical one-based inclusive UTF-8 source lines, including
  frontmatter in numbering. Both boundaries must be parser-safe and outside
  frontmatter. Do not split a paragraph, callout, table, code fence, or formula.

`questions` maps published question addresses to optional overrides:
`corrections`, `hints`, `explanations`, and `courses` arrays, plus `method` as a
selector or null.
Arrays preserve order. Explicit empty arrays suppress auto-selected material;
`method: null` suppresses automatic methods. Unused overrides are errors.
Mappings are semantic agent decisions; the script checks references, not their
pedagogical truth. Explanations require a selected correction. When selecting
an explanation from a question-addressed help note, its question and correction
links must agree with the published question and selected supplied answer.

For an exercise containing anchored `[!question]` callouts, each callout is a
question and surrounding plain text is shared context. Otherwise the selected
body is one unnumbered question, with no duplicated introduction. To split a
plain exercise into several questions without changing its notes, list explicit
question selectors in `exercises`; each becomes an independent exercise view.
This initial version does not guess numbered-list question boundaries.

## Current Ingest notes

Consume note-schema-1 frontmatter, `question`/`reponse` callouts, standalone
anchors, and `[question:: [[exercise#^q-id]]]` fields. Answer fields provide
automatic correction matches. Multiple supplied answers are displayed in
selected-note order unless overridden. Exercise `courses` frontmatter supplies
default contextual links; explicit question `courses` narrows them to excerpts.

Remove only recognized frontmatter, exact `clew-part` structural comments,
known structural field lines, callout wrappers, and standalone anchors from
display. Keep current content and Sources sections. Retained original Markdown
is not used to overwrite or verify current notes. No Ingest validator is called.

## Optional existing aids

A minimal additional note can contain:

```markdown
---
id: aide-sev
type: help
question: "[[exercice#^q-1]]"
correction: "[[corrige#^r-1]]"
---

> [!method]
> Utiliser le critere du cours.

^methode

> [!hint]
> Examiner la fonction nulle.

^indice-1

> [!hint]
> Examiner une combinaison lineaire.

^indice-2

> [!explanation]
> La correction applique le critere de stabilite par combinaison lineaire.
> Voir [[cours#Sous-espace vectoriel|le critere du cours]].

^explication-1
```

Anchored `method` and `hint` callouts are selected automatically for the exact
question target. At most one automatic method is allowed; multiple methods
require an explicit selection. Hints follow selected-note and in-note order,
with no fixed count. An explicit layout can reference other preexisting
Markdown instead. No aids are authored by Generate.

Anchored `explanation` callouts are selected automatically only when the help
note's `correction` points to a supplied answer linked to that same question.
The answer must be included in the selected corrections, either directly or
inside a selected note/heading. Wrong question/answer links are errors.
Explanations appear in the side panel from the revealed inline correction;
they are never appended to the supplied answer's prose.

Course links inside help notes register exact heading/block excerpts
automatically. They open in the side panel, including when the course is also
selected for reading or the reading view is suppressed. No extra layout mapping
is necessary for those authored links. Target notes must still be in `notes`.

This publication convention also consumes the first-increment `clew-enrich`
output. Generate needs no installed Enrich skill or validation snapshot.
Humans can author/edit the same notes; a general revision/provenance contract
remains outside this version.

## Markdown, links, and assets

CommonMark with tables and dollar-delimited math is rendered in Python.
Lists, code, blockquotes, known callouts, and heading/block references are
supported. Link targets must be published somewhere: add their view to the
layout rather than accepting a broken internal link. Contextual course targets
can open in the side panel. All target notes must be included by a selected
chapter or selected explicitly in `notes`.

Local PNG/JPEG/GIF/WebP figures, including `![[figure.png]]`, are embedded after
checking type signatures. Use Markdown syntax for relative image paths.
Raw HTML is escaped and warned about; SVG and remote figures are rejected.
Note transclusions and Dataview are rejected rather than silently evaluated.
HTTP(S)/mailto links remain optional navigation. JavaScript and other active
URL schemes are not emitted as links.

Local `.pdf` links, including original `#page=N`, are rebased to the output
directory. Missing PDFs produce warnings, not a rendering failure.
Other local attachment link types are unsupported.

Bundled MathJax uses base, AMS, newcommand, and configmacros with local SVG
fonts. Dynamic extensions and active/external TeX commands are rejected.
Unsupported formulas are reported visibly in the browser; generation is not
a mathematical correctness checker.
