# First-increment note format

Use current chapter notes under `courses/`, `exercices/`, `corriges/`, and
separate aids under `aides/`. Those directory names and `[!reponse]` are existing
format keywords, independent of the teaching language.

An exercise note owns one actual exercise, including all subquestions and shared
context. A correction note owns one supplied correction unit for that exercise.
Keep these source units intact; multiple supplied variants may use separate
correction notes. `type: help` files are auxiliary additions, not finer source
exercise/correction units. Native notes already have internal question/answer
blocks before optional enrichment.

Unit IDs and note-local anchors form full addresses. Repeated `q-1` anchors in
different exercise notes are distinct. An answer link must agree with the
correction's declared `exercises` association and all other answers in that unit.
When no association is declared in a current note, resolved answer links must
still agree on one owning exercise; ambiguous matches require a decision.
`exercises`, when present, is an array of references resolving to at most one
whole exercise note, never a question fragment. Validation checks ownership even
when the target question exists and repeats another exercise's local anchor.

Do not alter source frontmatter. Preserve all supplied lines and their order.
Wrap only explicitly selected question/answer spans. Reuse existing anchors,
labels, source fields, and question links. IDs are unique across learning notes;
anchors are unique within each note and use ASCII letters, digits, and dashes.

For example, a source question followed by one blank line:

```markdown
1. Determine the limit of $u_n=7(2/5)^n$.

```

becomes this structural representation, including the source blank line as `>`:

```markdown
> [!question] Exercise 1 - Question 1
> 1. Determine the limit of $u_n=7(2/5)^n$.
>

^q-ex1-1

```

A supplied answer gets its explicit question link on the first quoted field
line. When a source/needs field already exists, append the question field to
that same structural line without changing the existing fields:

```markdown
> [!reponse] Exercise 1 - Answer 1
> [question:: [[worksheet#^q-ex1-1]]]
> 1. Since $|2/5|<1$, the limit is $0$.
>

^r-ex1-1

```

Do not add this answer if it was not supplied. Keep shared instructions outside
the wrappers. Prefix every source line inside a wrapper with `> ` (or `>` for
an empty line); preserve its remaining indentation exactly. Lazy blockquote
continuations and folded callout variants are outside this first contract.
Do not introduce new `src`/`needs` fields or change Ingest structural comments.

An aid note for this question is:

```markdown
---
schema_version: 1
id: aid-ex1-1
type: help
question: "[[worksheet#^q-ex1-1]]"
correction: "[[solutions#^r-ex1-1]]"
---

> [!hint]
> Compare $|2/5|$ with $1$ using
> [[course#Geometric limits|the geometric limit result]].

^hint-1

> [!hint]
> The factor $7$ is constant; apply the second statement in
> [[course#Geometric limits|the same result]].

^hint-2

> [!explanation]
> The condition $|q|<1$ holds. Multiplication by a fixed constant
> preserves the zero limit, as stated in
> [[course#Geometric limits|the course]].

^explanation-1
```

`question` must resolve to a question block; `correction`, when present, must
resolve to a supplied answer block linked to that same question. A note may
contain hints only: omit `correction` when no supplied answer exists.
Explanations require `correction`. Callouts are anchored, nonempty, and follow
their intended presentation order. Counts are not fixed.

Every hint/explanation needs at least one explicit course heading/block link.
Selectors resolve within the chosen chapter by note ID, unique filename/stem,
or relative Markdown path. Prefer IDs and wikilinks, such as
`[[course#Exact heading|label]]` and `[[course#^theorem|label]]`.
Ordinary local Markdown `.md` links are also recognized. Duplicate headings
need a stable block anchor already present in the course; do not edit the
course just to disambiguate it. Ask if no precise existing target is available.
Text inside code or mathematics is not interpreted as a course reference.

The baseline is version-1 local JSON containing the chapter path and original
visible directory/file inventory and hashes, with current exercise/correction text. It is not
a publishing artifact, proof of permission, or cryptographic attestation.
Validation allows only unchanged original files, documented structural edits
to exercise/correction Markdown, and new Markdown under `aides/`.

Source projection removes the question/answer wrapper headers, their anchors,
new question fields, and their explicit unquoted anchor separators. Existing
ordinary block anchors are also structural; their identities must be retained.
Quoted source blank lines, list/formula indentation, and other source lines remain
exact. Body line endings may differ, but there is no broad whitespace normalization;
original frontmatter is preserved exactly.
Preexisting anchored blocks retain their IDs, kind, label, and question match.
