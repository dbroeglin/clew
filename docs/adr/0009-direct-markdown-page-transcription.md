# ADR-0009: Direct Markdown page transcription

- Status: Accepted; refined by ADR-0010
- Date: 2026-10-09

> **Refinement:** [ADR-0010](0010-source-grounded-page-review-and-retries.md)
> adds independent page judging, bounded corrective candidates, and retained
> attempt evidence. The selected candidate remains direct Markdown without
> inner JSON decoding or Python string repairs; figure classification stays
> structured. Its per-attempt judge report is separate from page authorship.

## Context

Investigation of imported mathematics found page responses where a single
backslash in the inner JSON `markdown` string decoded as a control character:
`\boldsymbol` and `\bb` began with JSON's backspace escape. The outer API response
was valid JSON; parsing its page-text envelope introduced the second decoding
step. Other defects were model-authored transcription errors, not JSON escapes.

The page schema contains an opaque Markdown string and self-reported fixes with
confidence scores. Those scores are only logged; neither they nor the schema
validate mathematical rendering or source fidelity. Figure classification is
different: its constrained fields drive asset acceptance and review decisions.

The user approved direct Markdown page responses while retaining structured
figure classification. Keeping the page envelope would retain an unnecessary
escaping burden; a richer document schema would expand scope without proving
faithfulness.

## Decision

Partially supersede [ADR-0002](0002-pdf-import-skill-and-project-runtime.md)'s
pinned models and response-format restriction for page transcription. Refine
[ADR-0005](0005-conservative-import-and-latex-leakage-review.md) without changing
its conservative transcription or independent, non-mutating leakage review.

Request plain-text output for page reconciliation. The model returns only
Markdown, without a JSON envelope, explanatory preamble, surrounding code
fence, or self-reported fixes/confidence list. Mark unreadable source content
in place. A page without substantive content returns `<!-- Blank page. -->`;
empty or whitespace-only output remains an explicit failure.

Return page text unchanged to review and assembly. Do not parse it as inner
JSON, repair TeX, normalize whitespace, or reconstruct formulas from OCR.
Assembly continues to add original-page markers and inter-page separators.
Retain strict JSON-schema output and explicit schema/decision validation for
figures, whose fields control crop publication.

Persist complete raw API responses before completion or content checks.
Incomplete responses and refusals without extraction remain failures. Preserve
diagnostics, complete-pass publication, retained sources, artifact paths,
manifest schema version 3, and exit meanings. Raw page `*.response.json` files
still contain API JSON, but their response text now contains Markdown directly.
Existing completed bundles are neither migrated nor reconverted; downstream
stages consume the unchanged Markdown/manifest contract, not the page envelope.

Document the complete operational rules inside the portable Import skill and
update the skills reference, workflow evaluations, and repository-owned offline
tests. No new dependency, cloud run, or change to supplied course bundles is
part of this decision.

## Consequences

- Direct page output removes the inner JSON escaping hazard and unnecessary
  self-reported correction metadata.
- Structured-output deployment support remains necessary for figures.
- External diagnostic readers must distinguish direct page text from older
  page envelopes; raw artifact filenames alone do not identify that format.
- Conservative prompts and review findings remain useful but cannot prove
  faithful transcription or valid TeX. Direct Markdown does not prevent
  incorrect inequalities, unbalanced braces, unsupported macros, or all
  control-character contamination.
- Blank pages have explicit retained evidence rather than silently accepting
  absent output. The model's blank-page assertion still requires source review.
