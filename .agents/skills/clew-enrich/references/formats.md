# Enrich prepared-document format

Enrich consumes a completed `clew-import` chapter. It does not consume legacy
exercise-per-note chapters or alter the Import format. Import keeps each
complete PDF as one Markdown note with frontmatter such as:

```yaml
---
schema_version: 1
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
> [Question](../Exercise-sheet/sheet.md#^ex-01-q-01)
> [PDF p. 1](solutions.pdf#page=1)

^ex-01-r-01

[Exercise](../Exercise-sheet/sheet.md#^ex-01)
[PDF p. 1](solutions.pdf#page=1)

%% /clew:unit corr-01 %%
```

Addresses include the document ID and local anchor. An `ex-01-q-01` anchor in
another document is a different question. Follow explicit `Exercise` and
`Question` footer links; never infer ownership from filenames, numbering, or
matching anchor strings. Separate correction variants may target the same
question. Unmatched answers and questions without answers are valid.

## Aid notes

Each new aid is a separate Markdown file under chapter `aides/`. Its frontmatter
has `schema_version: 1`; `id` is unique across the chapter, and `question`
targets an anchored imported question. `correction`, when present, targets the
supplied answer linked to that same question. Explanations require `correction`;
hints do not.

```markdown
---
clew_schema: 1
id: aid-ex-01-q-01
type: help
question: "[[sheet#^ex-01-q-01]]"
correction: "[[solutions#^ex-01-r-01]]"
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

A question may have a hint-only aid when no answer is supplied. Omit
`correction` in that case. Do not create an answer or an explanation for a
missing answer. An aid may contain ordered, anchored `hint` and `explanation`
callouts; counts are not fixed. Keep prose concise, specific to its question,
and visibly separate from imported source material.

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

There is no migration path for legacy archives in this increment. Generate
remains a legacy-layout consumer and does not publish these prepared-document
aid notes.
