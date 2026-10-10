# Whole-document example

This independently authored material illustrates structure, not a supplied
course or a mathematical correction. Actual plans must use inspected selectors
and fingerprints from their own selected bundles.

Three converted PDFs named `course.pdf`, `sheet.pdf`, and `solutions.pdf`
become:

```text
Sequences\
  index.md
  Course-course\
    course.md
    course.pdf
  Exercise-sheet\
    sheet.md
    sheet.pdf
  Correction-solutions\
    solutions.md
    solutions.pdf
  .clew\
    preparation.json
    baselines\
      course\document.md
      sheet\document.md
      solutions\document.md
```

Each note retains its entire selected converted document. Source figures stay
in that document folder's `figures/`. Mixed/unknown PDFs use a basename folder
instead of a guessed role prefix.

## Course

Original source:

```markdown
<!-- page: 1 -->

## Geometric limits

### Theorem 1

If $|q|<1$, then $q^n$ tends to zero.
```

Assume the inspector returned `b-2` for the section heading, `b-3` for
the theorem heading and `b-4` for its paragraph. The plan operations are:

```json
[
  {"op":"unit","kind":"section","id":"sec-geometric","start":"b-2","end":"b-4"},
  {"op":"callout","kind":"theorem","id":"thm-geometric","start":"b-3","end":"b-4"}
]
```

Prepared note body, with structural blank lines shortened for illustration:

```markdown
%% clew:unit section sec-geometric %%

## Geometric limits

[PDF p. 1](course.pdf#page=1)

> [!theorem] Theorem 1
>
> If $|q|<1$, then $q^n$ tends to zero.
>
> [PDF p. 1](course.pdf#page=1)

^thm-geometric

%% /clew:unit sec-geometric %%
```

The exact generated note also has `clew_schema: 1`, `type: document`, `role`,
`id`, `source_pdf`, and `source_pages` frontmatter. Neither the agent nor Python
rewrites the statement. The compiler changes its heading wrapper and prefixes
the original body, preserving source whitespace and equations.

Use `course.md#Geometric%20limits` for the section; the scope ID `sec-geometric`
is private bookkeeping, not a native anchor. Use
`course.md#^thm-geometric` for the exact theorem callout.

## Exercises and supplied answers

The whole sheet contains an exercise unit, shared context and two separately
anchored questions:

```markdown
%% clew:unit exercise ex-01 %%

## Exercise 1

Exercise ^ex-01

Let $u_n=7(2/5)^n$.

> [!question] Question 1
>
> 1. Determine its limit.
>
> [PDF p. 1](sheet.pdf#page=1)

^ex-01-q-01

> [!question] Question 2
>
> 2. Find a bound.
>
> [PDF p. 1](sheet.pdf#page=1)

^ex-01-q-02

[PDF p. 1](sheet.pdf#page=1)

%% /clew:unit ex-01 %%
```

Do not enclose both questions in an outer callout: native Obsidian cannot
address parts inside that callout. The comments express unit scope without
splitting the source sheet. Question ownership comes from that scope, so no
parent Exercise backlink is needed.

A supplied answer in the complete `solutions.md`:

```markdown
%% clew:unit correction corr-01 %%

## Correction 1

Correction ^corr-01

> [!reponse] Answer 1
>
> 1. The limit is $0$.
>
> [Question](../Exercise-sheet/sheet.md#^ex-01-q-01)
> [PDF p. 1](solutions.pdf#page=1)

^ex-01-r-01

[Exercise](../Exercise-sheet/sheet.md#^ex-01)
[PDF p. 1](solutions.pdf#page=1)

%% /clew:unit corr-01 %%
```

The generated correction footer is one paragraph even when shown wrapped here.
Every linked answer must target a question owned by that correction's linked
exercise. Several supplied correction variants may legitimately target the
same question. No missing answer is generated.

If a match is uncertain, omit its relationship in the plan. The resulting
note receives a generated warning after all source units, in its final appendix:

```markdown
**Review required**

%% clew:review {"code":"unmatched-answer","message":"This supplied answer has no verified question match.","anchor":"ex-01-r-01"} %%
> [!warning] Clew review
> This supplied answer has no verified question match.
> [Location](solutions.md#^ex-01-r-01)
```

The source answer remains unchanged and addressable. The index and validator
report the same unresolved finding; a review-only status is not a clean pass.

## Approvals and checks

Approve cloud conversion separately if needed. For local preparation, inspect
the bundles/vault, author a complete version-1 plan with the actual fingerprints,
then run `prepare_documents.py --check`. Review placement, exact operations,
diffs, matches/evidence, copied files, and warnings in **one** approval.

Execute using the returned `--plan-sha256`, then validate the persisted chapter
with `validate_documents.py --fidelity`. Later manual edits use default
structure/link validation; fidelity checks deliberately report differences.
Moving this complete chapter preserves the relative links.

Future aid notes can link to `sheet.md#^ex-01-q-01`,
`solutions.md#^ex-01-r-01`, and `course.md#^thm-geometric`, but aid authorship
and Enrich/Generate consumer refactors are not implemented by this skill.
