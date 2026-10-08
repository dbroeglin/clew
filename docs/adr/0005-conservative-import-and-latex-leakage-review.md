# ADR-0005: Conservative Import and LaTeX leakage review

- Status: Accepted
- Date: 2026-10-04

## Context

Inspection of a completed mathematics import found nine headings containing
literal `\quad` commands. The source PDF and Document Intelligence headings
used ordinary typographic spacing; the page-reconciliation model introduced
the commands. Markdown parsing succeeds because these are legal literal text,
so the bundle was marked `extracted` without review issues.

[ADR-0002](0002-pdf-import-skill-and-project-runtime.md) intentionally preserved
the pinned upstream prompts and validation except for source retention.
The user has now approved conservative prompt instructions and a non-mutating
check for possible LaTeX leakage, without modifying the existing import.

Prompt-only prevention would leave recurrence invisible. Automatic replacement
could destroy genuine source commands or modify mathematics. A broad backslash
detector would confuse code, file paths, and literal command discussions with
transcription errors.

## Decision

Partially supersede
[ADR-0002](0002-pdf-import-skill-and-project-runtime.md)'s restriction on
modifying the upstream page prompt and Markdown content checks. Preserve its
other safety and artifact contracts, with runtime ownership governed by
[ADR-0003](0003-autonomous-portable-skills.md) and downstream retention/test
ownership governed by [ADR-0004](0004-faithful-multi-bundle-ingest.md).

Require the page-reconciliation model to make the smallest necessary,
image-evidenced corrections, preserving already-correct OCR text, source
mistakes, unusual wording, and mathematical notation. This does not make OCR
authoritative: the page image remains the source of truth.

Separate document formatting from mathematics explicitly. Use ordinary spaces
for typographic gaps in prose and headings, LaTeX only inside math delimiters,
and code for literal commands discussed by the source. Allow genuine inline
formulas in headings; do not wrap textual headings in math to render layout
commands. Require a final self-check without presenting it as verified fidelity.

Use the existing Markdown parser and math/table plugins to inspect ordinary
text in each generated page for a bounded list of known math/layout commands:
`\quad`, `\qquad`, `\hspace`, `\vspace`, `\enspace`, `\thinspace`, `\frac`,
`\dfrac`, `\tfrac`, `\sqrt`, `\mathbb`, `\mathcal`, `\mathrm`, `\mathbf`,
`\text`, `\begin`, `\end`, `\left`, and `\right`. Match complete control words.
Exclude math, code, link destinations, image paths, raw HTML tokens, and
recognizable Windows drive, UNC, and dot-relative paths. Check link labels and
ordinary text between inline HTML tags.

Append possible-leakage findings to the existing manifest `issues`, including
the original PDF page, page-local Markdown block line or line range, command,
and bounded excerpt. Warn in diagnostics and use the existing `needs_review`
manifest/run status and exit code `2`. Combine these findings with figure review
issues; no manifest schema or exit-code change is necessary.

Do not rewrite model Markdown, reconstruct formulas, retry services, apply
confidence thresholds, or mutate previously completed bundles. Preserve raw
responses and the existing assembled/final Markdown relationship. Parser errors
remain explicit failures.

Document these deviations in the portable skill, not only in this ADR. Add
offline regression coverage under the repository-owned import test suite and
workflow evaluations in the skill. No new dependency or cloud call is required.

## Consequences

- Correct source transcription is preferred to cosmetic consistency or author
  proofreading.
- Apparent LaTeX leakage becomes visible without destroying its raw evidence or
  changing generated content.
- Review findings are heuristic, not source-fidelity judgments. Literal commands
  outside code and ambiguous relative paths can cause false positives. Unknown
  commands, raw HTML blocks, and other formula errors can escape detection.
- Parser maps locate the containing Markdown block, not necessarily the exact
  command line within a multiline paragraph or table.
- Prompt-contract tests and offline review tests do not establish model
  compliance. Empirical evaluation requires separately authorized cloud work.
- Existing bundles remain untouched; reprocessing needs a separate scoped plan
  and approval, and completed review bundles are not failed-output cleanup
  candidates.
