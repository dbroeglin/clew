# Enrich prepared-document format

Enrich consumes a completed `clew-import` chapter. It does not consume legacy
exercise-per-note chapters or alter the Import format. Import keeps each
complete PDF as one Markdown note with frontmatter such as:

```yaml
---
clew_schema: 1
id: sheet
type: document
role: exercise
source_pdf: sheet.pdf
source_pages: [1]
title: Exercises
---
```

The chapter contains an Import `index.md` (`type: chapter`) and a complete
`.clew/preparation.json` (`status: complete`). Documents may be in
`Course-<basename>`, `Exercise-<basename>`, `Correction-<basename>`, or
basename folders; filenames and folders are not proof of role or association.
Use frontmatter roles, persistent document IDs, structural unit scopes, and
native anchors.

## Source ownership and links

Exercise and correction units remain in their source documents. Unit comments
mark the full scope; exercise/correction entry IDs are native block anchors.
Question and answer callouts have their own native block anchors and belong to
their enclosing source unit. Never split a whole sheet into question-sized
notes or put independently addressable callouts inside an outer quote/callout.

For example, an exercise may look like:

```markdown
%% clew:unit exercise ex-01 %%

## Exercise 1

Exercise ^ex-01

Let $u_n=7(2/5)^n$.

> [!question] Question 1
> 1. Determine its limit.
> [PDF p. 1](sheet.pdf#page=1)

^ex-01-q-01

%% /clew:unit ex-01 %%
```

A supplied answer stays in its correction unit and links to its question with
the Import relationship footer. The correction unit's `Exercise` footer
declares its owning exercise when that association was verified:

```markdown
%% clew:unit correction corr-01 %%

## Correction 1

Correction ^corr-01

> [!reponse] Answer 1
> Since $|2/5|<1$, the limit is $0$.
>
> [Question](../Exercise-sheet/sheet.md#^ex-01-q-01) · [PDF p. 1](solutions.pdf#page=1)

^ex-01-r-01

[Exercise](../Exercise-sheet/sheet.md#^ex-01)
[PDF p. 1](solutions.pdf#page=1)

%% /clew:unit corr-01 %%
```

Internal addresses include the document ID and local anchor. An `ex-01-q-01` anchor in
another document is a different question. Follow explicit `Exercise` and
`Question` footer links; never infer ownership from filenames, numbering, or
matching anchor strings. Separate correction variants may target the same
question. Unmatched answers and questions without answers are valid.

IDs do not navigate in Obsidian. A document with `id: course-document` saved as
`Course-analysis/analysis.md` is linked as `[[analysis#...|Readable label]]`,
not `[[course-document#...]]`. Use a unique actual filename (with or without
`.md`) or exact chapter-relative path such as `Course-analysis/analysis` when
basenames are ambiguous. Markdown note paths are relative to the origin note;
they are not resolved as IDs or bare filename searches.

## Aid notes

Each new aid is a separate Markdown file under chapter `aides/`. Its frontmatter
has `schema_version: 1`; `id` is unique across the chapter, and `question`
targets an anchored imported question. `correction`, when present, targets the
supplied answer linked to that same question. Explanations require `correction`;
hints do not.

```markdown
---
schema_version: 1
id: aid-ex-01-q-01
type: help
question: "[[sheet#^ex-01-q-01|Exercise 1 - question 1]]"
correction: "[[solutions#^ex-01-r-01|Supplied geometric-limit correction]]"
---

> [!hint]
> Compare $|2/5|$ with $1$ using
> [[course#Geometric limits|the geometric limit result]].

^hint-1

> [!explanation]
> The ratio has absolute value below one, so its powers tend to zero by
> [[course#^thm-geometric|the course theorem]].

^explanation-1
```

Course references must resolve to one exact heading or existing block anchor
in a selected document with `role: course`. Heading links need a unique exact
heading; use a block link to disambiguate duplicates. Text inside code or math
does not count as a reference. Markdown note links and wikilinks are supported.
Links to other local note anchors must also resolve; external learning sources
are not used.

Every new frontmatter question/correction link and local body link has a
nonempty display label. Choose a natural concept, theorem, exercise, or question
label; not an internal anchor ID. The checker enforces label presence for new
aids only, leaving existing human-authored aids unchanged. Navigation checks
still apply to existing aids. A resolving link is not proof of relevant evidence:
read the precise paragraph or heading section, especially when an anchor is
attached only to a title. Do not edit a course to create a better anchor.

Plain `[!hint]` / `[!explanation]`, collapsed `[!hint]-`, and expanded
`[!explanation]+` callouts are supported, with optional titles. Put the block ID
on its own line after each callout, as above. For multiline display mathematics,
keep explicit quote prefixes and blank quoted lines before the opening `$$` and
after the closing `$$` so adjacent prose and links are not parsed as inline math:

```markdown
> [!explanation]- Controlling a remainder
> Apply [[course#Taylor bound|the bound on the Taylor remainder]].
>
> $$
> |r(x)|\leq Mx^2.
> $$
>
> Now sum the termwise bounds.

^explanation-remainder
```

LF, CRLF, and CR line endings are accepted. Proposal manifests hash original
draft bytes; do not normalize approved files when copying them to the chapter.

A question may have a hint-only aid when no answer is supplied. Omit
`correction` in that case. Do not create an answer or an explanation for a
missing answer. An aid may contain ordered, anchored `hint` and `explanation`
callouts; counts are not fixed. Hints remain short and progressive; explanations
are as detailed as the supplied reasoning needs, not generic summaries. Make
calculations and hypotheses explicit and cite the relevant course results at
their use. Keep additions visibly separate from imported source material.
Every individual hint/explanation callout contains its own parsed precise course
link; a shared mapping table or a citation in the next callout does not count.
Elementary transitions belong inside their course-supported explanation rather
than separate unsupported callouts. Merge such transitions with the reasoning
they support; do not manufacture an unrelated course citation.

For a genuine supplied contradiction or missing support, obtain a user decision.
Under an approved hints-only policy, state a neutral, source-evidenced warning
outside the hints and omit `correction` and explanations. A supported omitted
starting rank or uniformity argument is not automatically a contradiction.
Explain it without replacing the supplied method. List targets with no
supported aid; do not fabricate a course citation to achieve full counts.

## Preservation and validation

Capture one new local baseline outside both the chapter and repository before
editing. Version-2 baselines record the chapter path, visible file and directory
inventory, and SHA-256 hashes. They do not contain source text. The inventory
includes Import's `.clew/` preparation record and retained files while
excluding other hidden entries.

Validation accepts only unchanged existing files and new Markdown aids under
`aides/`. Existing aid notes are immutable, including human edits. The validator
checks prepared document identities against `.clew/preparation.json`, unit
ownership, unique anchors, answer/question links, aid references, and precise
course passages. It is read-only and cannot establish semantic correctness.

There is no migration path for legacy archives. Generate consumes current
document-internal units and these aids without requiring this validator or
its baseline. Supplied answers reveal inline; hints/explanations and their
precise course links open in the side panel.
