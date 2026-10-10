# Whole-document preparation contract (version 1)

The skill has two resumable steps. Conversion produces complete schema-3 bundles;
preparation consumes selected bundle Markdown without calling the converter.
All runtime helpers in this reference are relative to this portable skill.
Python >=3.11 and the skill's declared dependencies are required. No other skill,
vault plugin, repository documentation, `.env`, Node process, or cloud access is
required for local preparation/validation.

## Plan

Unknown plan/operation keys and non-integer schema versions are rejected.
Document/chapter IDs are lowercase ASCII slugs. Anchor IDs contain Latin ASCII
letters, digits, and dashes. All IDs are stable; `b-N` selectors are only the
source inspector's fingerprint-bound temporary block addresses.

```json
{
  "schema_version": 1,
  "id": "sequences",
  "title": "Sequences",
  "destination": "C:\\vault\\Maths\\Sequences",
  "placement": {
    "vault": "C:\\vault",
    "parent": "Maths",
    "rationale": "Existing comparable mathematics chapters use this container.",
    "create_parent": false
  },
  "documents": [
    {
      "id": "course",
      "bundle": "C:\\imports\\course",
      "fingerprint": "<64-character inspection fingerprint>",
      "role": "course",
      "operations": [],
      "reviews": []
    }
  ]
}
```

`vault` and `bundle` paths are absolute host paths. `parent` is a non-root
portable relative visible directory, not an owned root/configuration directory.
The new chapter is a direct child. Missing parents require explicit approval and
`create_parent: true`. The final preparation approval includes this placement.
Do not nest inside another prepared root (`.clew/preparation.json` or partial
`.clew/baselines/`) or legacy `ingest.json` root. A vault-level
`.clew/imports.json` inventory alone does not claim chapter ownership.

Each selected PDF gets exactly one document object and one complete editable
note. Roles are `course`, `exercise`, `correction`, `mixed`, or `unknown`.
Defaults are `unknown`; never infer a role from filenames alone.
Folders are `Course-<PDF basename>`, `Exercise-<PDF basename>`,
`Correction-<PDF basename>`, or the basename for mixed/unknown.
An optional explicit `folder` overrides only that single visible folder name
when a collision/unsafe name requires an approved decision. The original PDF
filename and Markdown basename remain unchanged; unsafe original basenames
must be resolved before preparation, not silently renamed. Case-insensitive
folder/note collisions are errors.

Inside each folder: `<basename>.md`, `<original-filename>.pdf`, and referenced
`figures/` paths. The chapter additionally contains `index.md` and private
`.clew/preparation.json`, `.clew/baselines/<document-id>/document.md`.
Do not copy unused figures, raw extraction artifacts, configuration, or logs.
Keep the baseline and PDF byte-identical; the retained subset is not a complete
conversion bundle.

## Operations

Selectors must exist in the inspected source and cover complete parser-safe
blocks, not just arbitrary numeric lines. They refer to the original source
snapshot, not positions after previous operations. The compiler applies
operations in one deterministic batch; overlapping callout edits, crossing
units, conflicting edits, stale sources, and unsafe nesting are errors.

### Unit scope and entry

```json
{"op":"unit","kind":"exercise","id":"ex-01","start":"b-3","end":"b-8"}
```

Kinds: `section`, `exercise`, `correction`. Unit scope retains all its original
source content; opening/closing Obsidian comments make boundaries explicit:

```markdown
%% clew:unit exercise ex-01 %%

## Exercise 1

Exercise ^ex-01

Original shared context and individually addressed questions.

[PDF p. 2](sheet.pdf#page=2)

%% /clew:unit ex-01 %%
```

For exercises/corrections, the generated entry paragraph is a native link
target, not a source sentence.
It follows the selected first heading, or precedes non-heading content. Its
anchor is reused if already present within the unit. Only sections can contain
other units. Exercises/corrections cannot contain other exercises/corrections.
Do not place unit entry markers inside a callout.

Sections must start at an existing source heading. They retain original headings
for navigation and get no generated block IDs. A section's scope ID in comments
is internal bookkeeping, not a link target. Use `note.md#Heading%20title` for a
section; heading changes or duplicates can invalidate a title-based link.
Linking to
`#^ex-01` reaches the entry point; it does not natively embed the entire unit.
Unit comments define its source scope for local checks and future consumers.

A correction may declare a verified exercise match:

```json
{
  "op": "unit", "kind": "correction", "id": "corr-01",
  "start": "b-3", "end": "b-7",
  "exercise": {
    "target": {"document": "sheet", "anchor": "ex-01"},
    "evidence": [{"document": "answers", "start": "b-4", "end": "b-7"}]
  }
}
```

The generated `[Exercise](../Exercise-sheet/sheet.md#^ex-01)`
is a visible structural relationship link. A match needs nonempty source
evidence. Python checks evidence location and ownership, not semantic truth.
It appears in the correction footer before its PDF link. Relationship links
use exactly the labels `Exercise` or `Question`. For a callout, put the
relationship and PDF links together on the final quoted line, in that order,
separated by ` · `; a callout without a relationship has only its PDF link.
Keep one blank quoted line between the callout content and its footer. Collapse
additional consecutive blank quote lines at that boundary, but preserve blank
lines within the supplied body. Do not add quoted blank lines after the links.
The validator uses that convention and checks the destination's
document role, target kind, and ownership; filenames alone are not proof.
No prefix, metadata wrapper, or plugin is required.
No match means no fabricated link: generate a visible review warning.

### Source-derived callouts

```json
{"op":"callout","kind":"theorem","id":"thm-limit","start":"b-4","end":"b-6"}
```

Kinds: `definition`, `theorem`, `property`, `lemma`, `proposition`, `corollary`,
`example`, `remark`, `proof`, `question`, `answer`.
For a one-line ATX or two-line setext heading, preserve its exact inline title
while changing only heading syntax into a callout header. Otherwise add a
generated kind label and retain the selected body verbatim with explicit
`> ` prefixes. Custom callouts fall back to Obsidian's note appearance unless
the user separately installs styling.

```markdown
> [!theorem] Original theorem title
>
> Original statement, equations, and proof if included in the selected source.
>
> [PDF p. 3](course.pdf#page=3)

^thm-limit

```

The standalone anchor has blank separators and targets the whole callout.
Native Obsidian does not support links to its interior, so independently
addressed questions/answers must not be enclosed in another callout.
Pre-existing supported callouts may be annotated without changing their kind;
pre-existing anchors must be part of the selected safe range. Do not double-wrap
or regenerate them. Unsupported or inseparable content is preserved/reviewed.

Questions declare `owner`, the local exercise entry ID:

```json
{"op":"callout","kind":"question","id":"ex-01-q-01","owner":"ex-01",
 "start":"b-5","end":"b-5"}
```

Supplied answers declare the local correction owner and an optional question:

```json
{
  "op": "callout", "kind": "answer", "id": "ex-01-r-01", "owner": "corr-01",
  "start": "b-4", "end": "b-4",
  "question": {
    "target": {"document": "sheet", "anchor": "ex-01-q-01"},
    "evidence": [{"document": "answers", "start": "b-4", "end": "b-4"}]
  }
}
```

Answers render as `[!reponse]` with a verified `[Question](...)` link followed
by ` · ` and the PDF link on the same final quoted line. Questions render as
`[!question]` with only their compact PDF footer link.
Ownership comes from the unique enclosing exercise/correction scope, not a
redundant parent backlink. All matches must agree with the correction's exercise
association.
Missing answers are valid; separate supplied correction variants may reference
the same exercise/question. Do not add `needs`, prerequisites, aids, or inferred
course links in this increment.

### Anchor and heading level

```json
{"op":"anchor","id":"context-01","block":"b-4"}
{"op":"heading","block":"b-2","level":2}
```

Paragraph anchors attach to the end of the paragraph; structured-block anchors
use a standalone line and blank separators. Existing IDs are reused, never
renumbered. Heading adjustments change only heading syntax, preserving inline
text, mathematics, and source order. Complex multiline heading promotion is
unsupported rather than silently collapsed.

## Automatic provenance, links, and review warnings

Parsed original `<!-- page: N -->` markers supply page provenance and are removed
from the editable note by recorded mechanical edits. Code lookalikes remain
source text. Each section entry gets one compact
`[PDF p. N](filename.pdf#page=N)` link to its starting original PDF page.
Exercise/correction units instead place it on their final line, with any
correction-to-exercise relationship before it; their entry anchors stay at
the beginning for navigation and ownership.
Each learning callout ends with one quoted footer line containing its PDF link
and, for a matched answer, the verified question link first, separated by
` · `. Keep exactly one blank quoted line between the supplied content and the
footer. Remove only additional consecutive empty quote lines at that terminal
boundary; preserve body-internal spacing and do not add empty quoted lines
after the footer. The footer remains inside the callout, before its native block
anchor, not above the supplied content.
Do not list every covered page or repeat links at page breaks. Full coverage
remains recoverable from the plan's selectors and immutable source baseline.
Never use printed page labels or range fragments.

New links are relative Markdown links; URL-encode paths and preserve `#^id`
block fragments. Moving the complete chapter leaves relationships intact.
Source-authored links remain untouched except required destination-only remaps
from `source/<PDF>` to the adjacent PDF, `document.md` to the editable note,
and unique promoted self-heading targets to their new stable callout ID.
Do not remap ambiguous headings or replace source link labels/captions.
Reference usages are kept; their definitions supply destination edits.

Optional `reviews` contain `code`, a single-line `message`, and optional source
`block`. Automatic findings include conversion issues, unmatched supplied
answers/corrections, unclassified headings, heading gaps, unknown/mixed roles,
and offline-unverified external destinations.

```json
{"code":"inseparable-questions","block":"b-5",
 "message":"Two source subquestions share one protected table; retain one addressable block."}
```

Review decisions do not waive unsafe edits or broken links. The compiler inserts
escaped messages into generated `[!warning] Clew review` callouts in a
**Review required** appendix after all supplied content and closed source units.
Each warning includes a location link when it has an anchor, otherwise its
original Markdown line. The index summarizes the findings after navigation.
Generated unit/review bookkeeping uses standalone `%% clew:... %%` Obsidian
comments (hidden in Reading view, visible in Source mode). Review JSON escapes
percent signs so messages cannot close their comment. Native anchors and links
remain outside comments. The parser recognizes the reserved Clew comment lines
without interpreting code/math lookalikes. Only this generated style is
supported; source-authored comments are never blanket-converted.
Warnings do not modify supplied prose and are excluded only by their exact
recorded insertions in source projection.

## Validation and persistence

`prepare_documents.py --check` returns status, exact paths, parent creation,
previews/diffs, source/plan hashes, findings and required approval. It performs
no writes. Hard errors block execution. Review-only output exits 2 and is
eligible for execution only after its warnings/scope are approved.

`.clew/preparation.json` records version 1, `writing`/`complete`, plan/hash,
document identities, original page counts/coverage, immutable source hashes,
prepared note/index hashes, exact narrow changes with original-slice hashes,
and review findings. It is local provenance, not a tamper-proof signature,
publication requirement, or authorization token.

Initial/persisted `--fidelity` checks verify exact untouched intervals and
independently reverse permitted heading syntax, quoted prefixes, page comments,
link destinations, and generated insertions. Recovery must equal the original
Markdown exactly, including newlines and whitespace. Parsed math/code/table
structure must also remain intact. No broad whitespace normalization or
AST-to-Markdown serialization is used.

Default `validate_documents.py` accepts manual source-note edits and locates
documents by persistent ID, including a renamed document folder. It still
checks schemas, native anchor attachment/uniqueness, unit boundaries, owner and
match kinds, current local references, PDF pages, immutable baselines and
retained artifacts. It never edits notes or updates baselines.
`--fidelity` intentionally detects changes to the initial prepared snapshot.

The validator reports one-based physical note lines, codes, error/review
severity, affected IDs/targets, and actionable text. Broken/ambiguous local
targets, invalid PDF pages, path escapes/redirects, private targets, unsafe
schemes, malformed fields/markers and contradictory owners are errors.
Heuristic structure uncertainty and missing supplied matches are reviews.
Raw HTML link attributes, unsupported local fragments, and unlocatable required
link edits are explicit errors, not unverified passes. Existing supported
wikilinks are resolved; newly generated links remain relative Markdown.
Link lookalikes in code/math are ignored. External URLs are never fetched;
they are visibly reported as not remotely verified.

Local helper exits: 0 clean, 2 review-only, 1 errors. Validate completion records
and persisted files rather than relying on exit codes alone. Partial failures
remain in their owned root; never merge, overwrite, delete, or automatically
retry. The whole prepared root can be relocated without external bundle access.
Existing conversion bundles and legacy user note archives are not migrated.
Enrich/Generate support for this new document-level contract is deferred.
