# ADR-0010: Source-grounded page review and bounded retries

- Status: Accepted; refined by ADR-0011
- Date: 2026-10-10

> **Refinement:** [ADR-0011](0011-npm-workspace-and-offline-import-mathjax.md)
> adds an executed offline MathJax checker and root npm workspace. Executed
> render errors also trigger corrections within the existing two-attempt
> budget, even when the judge misses them. The original prohibition on a
> Generate runtime dependency remains; the checker belongs to Import.

## Context

Comparisons of completed Import bundles found source-visible variables and
formula terms changed by the transcription model even after direct Markdown
removed inner JSON escaping. Renderable mathematics and successful service
completion did not establish faithful transcription. The original prompt's
self-check also missed discrepancies that a separate source comparison found.

Some apparent improvements in older outputs were unauthorized repairs of
author mistakes. A mathematical proofreader is therefore not an appropriate
judge for faithful Import. Unbounded attempts could incur uncontrolled costs
or optimize for a judge's approval rather than source preservation.

The user approved a source-grounded judge-and-correct loop enabled by default,
with at most two corrective attempts and retained evidence. A separate
deployment, live reprocessing, or modification of completed bundles is not
part of this change.

## Decision

Partially supersede [ADR-0005](0005-conservative-import-and-latex-leakage-review.md)'s
prohibition on model corrective retries during an import, and refine
[ADR-0009](0009-direct-markdown-page-transcription.md)'s raw evidence and selection
contract. Its direct Markdown page output remains in force. Existing failure,
output ownership, cloud approval, and delete-and-restart gates from
[ADR-0002](0002-pdf-import-skill-and-project-runtime.md) remain in force.

Review each candidate in a fresh Responses API request to the same configured
vision/structured-output deployment. Supply the original image, original OCR
and formula hints, figure metadata, complete candidate Markdown, and local
format findings. Do not supply the transcription conversation or previous
judge feedback to the judge. Inspect the whole page for content discrepancies,
omissions, notation/typography changes, and representation defects. The image
is authoritative; OCR is fallible. Printed author mistakes are not defects
to repair, and unreadable source content is not permission to invent.

The judge returns a strict findings schema: category (`transcription`, `format`,
or `uncertain`), location, description, visible source evidence, and correction
instruction. These fields control the loop, unlike the removed transcriber's
self-reported fixes/confidence. The report contains no replacement page.
Reject malformed, semantically empty, or control-contaminated findings
explicitly; describe control defects by code point instead of repeating them
in feedback.

For transcription/format findings, request a complete new plain Markdown page
using original source inputs, previous candidate, and current review feedback.
The transcriber must treat feedback as fallible, verify it against the image,
preserve author claims, and change only source-evidenced discrepancies.
Judge every revised candidate from scratch, including possible new errors.
Allow at most two corrective attempts. Uncertainty-only findings stop without
guessing. Select the latest candidate unchanged and retain unresolved findings
as `needs_review` with exit `2`. A failed/incomplete/refused/malformed service
response is a failed import, not an automatic content retry or a success-shaped
fallback.

Preserve existing non-mutating LaTeX leakage review. Add a local scan for Unicode
`Cc` controls except newline, carriage return, and tab. Supply both checks to
the judge as fallible hints; no Python string replacement or formula
reconstruction is performed. Only correctable judge findings trigger a
corrective attempt. Remaining local flags cannot be erased by a judge pass.
MathJax package/macro guidance is embedded in the judge prompt; no renderer or
runtime dependency on Generate is added.

Enable the loop by default and provide `--no-page-review` in the converter and
read-only planner for an explicit opt-out. The plan discloses enabled state,
the two-attempt limit, and 2-6 logical OpenAI page requests per requested page
(one when disabled). Figure calls and SDK transport retries are additional.
Approval for the scoped cloud plan includes this bounded in-run work, never
output deletion/restart or unbounded retries. Do not automatically reprocess
old completed bundles because defaults changed.

Retain all candidate Markdown, complete candidate responses, and complete judge
responses in numbered `raw/pages/page-NNNN.attempt-AA.*` artifacts. On completion,
the canonical `page-NNNN.response.json` contains the selected final candidate.
Manifest schema 3 gains additive configuration and per-page review/attempt
records with artifact references and findings. Existing downstream Markdown,
source, page numbers, canonical references, and exit contracts remain supported.
The planner validates attempt-artifact presence and scope when review metadata
exists, while historical completed bundles remain valid without it.

Keep complete operating instructions and evals inside the portable Import
skill; keep offline executable tests under `tests/clew_import/`. Update the
skills reference and end-user workflow documentation in the same change.

## Consequences

- Independent calls can detect discrepancies missed by transcription self-checks,
  but the same deployment can share blind spots or produce false judgments.
- A judge pass is not proof of source fidelity, mathematical correctness, or
  successful MathJax rendering. Offline mocked tests validate orchestration,
  not empirical model quality; live evaluations require separately approved
  cloud inputs and charges.
- Reviewing all pages increases paid calls even when no correction is needed.
  The bound makes additional work explicit and finite.
- All attempts remain auditable; corrections replace candidates by selection,
  not by silently patching historical evidence.
- The loop does not solve cross-page semantic matching, author mistakes, or
  correction/exercise numbering inconsistencies.
