# ADR-0005: Conservative Import and LaTeX leakage review

- Status: Accepted
- Date: 2026-10-04

## Context

Legal Markdown can contain transcription errors or LaTeX layout commands in
ordinary text. A model self-check cannot establish source fidelity.

## Decision

Require minimal image-evidenced transcription. Preserve correct wording,
notation and source mistakes; the page image is authoritative, OCR is fallible.
Use ordinary spacing in headings/prose, math delimiters for LaTeX, and code for
literal command discussions. Never silently proofread author mathematics.

Inspect parsed ordinary text for known commands: quad, qquad, hspace, vspace,
enspace, thinspace, frac, dfrac, tfrac, sqrt, mathbb, mathcal, mathrm, mathbf,
text, begin, end, left and right. Exclude math/code, destinations, raw HTML
tokens and recognizable Windows paths. Include source pages/block lines.
Preserve candidate Markdown; findings are review hints, not automatic repairs.
Unexpected controls are also reported. Source-grounded judging and executed
MathJax checks follow ADR-0010/0011, sharing a bounded corrective budget.
Completed bundles remain unchanged; local preparation has no OCR-repair API.

## Consequences

Heuristic findings can miss errors or have false positives. Clean parsing or
review is not fidelity proof. Evidence remains inspectable and unchanged.
