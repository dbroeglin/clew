---
title: "ADR-0003: Standalone Azure-assisted PDF digestion"
status: "Proposed"
date: "2026-09-19"
authors: "Requesting Clew maintainer; GitHub Copilot (draft)"
tags: ["architecture", "decision", "ingestion"]
supersedes: ""
superseded_by: ""
---

# ADR-0003: Standalone Azure-assisted PDF digestion

## Status

**Proposed** | Accepted | Rejected | Superseded | Deprecated

The requesting maintainer specified the extraction pipeline and authorized its
implementation on 2026-09-19. This records that requested implementation for
architectural review; it does not infer acceptance of this ADR. Course-content
structure is being developed separately and remains outside this decision.

This record was renumbered to ADR-0003 before review because the upstream
course-reader proposal already occupies ADR-0002. The extraction bundle is an
intermediate artifact, not a second course format or a `clew/v1` course package.
Packaging it for the course-content contract remains separate work.

The proposal was updated on 2026-09-19 at the maintainer's request to use
PyMuPDF, matching ARGUS and ITSARAG, instead of the initial PDFium renderer.
Its lifecycle status remains Proposed.

On 2026-09-19, after a live PDF exposed duplicate OCR formula fragments and
ordinary prose misclassified as mathematics, the maintainer authorized explicit,
audited merges/text corrections while retaining failures for unexplained
omissions. This implementation refinement does not accept the ADR.

Later on 2026-09-19, the maintainer replaced that prototype contract: the model
returns authoritative final Markdown and an informational list of fixes with
confidence. Python displays those reports without checking them. Processing
remains page-by-page, but assembling the whole requested document must precede
any splitting into multiple course files. The ADR remains Proposed.

The maintainer then requested a format-only parse of that assembled Markdown:
reject parser failures, but otherwise trust the model's content and fix reports.

## Context

Clew needs faithful Markdown, LaTeX formulas, and clean instructional figures
from course PDFs before integrating the result into a course-content structure.
The maintainer identified ARGUS and ITSARAG as reference patterns but explicitly
excluded a Catalyst dependency and requested simple Python scripts using UV.
The maintainer clarified that DI Markdown supplies the baseline text, OpenAI
checks completeness and formulas, and DI JSON supplies figure extraction.
An authorized Foundry OpenAI deployment and Document Intelligence resource are
assumed; provisioning is not part of ingestion.

This checkout had no Python environment. The maintainer explicitly requested a
minimal project-level `pyproject.toml` and `uv.lock` rather than an isolated UV
script or waiting for another branch.

## Decision

Propose one standalone Python entry point, operated by a first-party ingestion
skill, with the following boundaries:

- **IMP-001**: Request DI layout Markdown, formulas, Unicode-code-point spans,
  JSON, and native figure output. Preserve the original extraction.
- **IMP-002**: Retrieve crops using the JSON figure IDs and regions; use
  structured vision decisions to retain instructional figures, reject branding
  and decoration, and flag uncertain or multi-page figures.
- **IMP-003**: Render pages with PyMuPDF and reconcile each page's baseline
  Markdown against its image using OpenAI. The model returns final Markdown,
  including LaTeX and supplied asset links, plus descriptions/confidence for
  its fixes. Python treats that Markdown as authoritative and displays fixes
  without content checks, thresholds, or reconstruction.
- **IMP-004**: After every requested page finishes, assemble one document from
  the unchanged model outputs, with page-provenance comments. Parse its Markdown
  as a format gate and reject parser failures without rewriting the text.
  Splitting is a separate later operation. Preserve raw evidence and
  figure-selection review status; do not define course organization, retrieval,
  or learner-model writes.
- **IMP-005**: Use the Azure DI SDK, Azure Identity, OpenAI SDK, Pydantic, PyMuPDF,
  Pillow, and `markdown-it-py` with the dollar-math plugin directly, managed
  through UV. Use Entra authentication and an
  explicit DI endpoint rather than assuming a project endpoint supplies it.

This implements the requested OCR-plus-visual-evidence pattern without coupling
the extraction tool to Catalyst or to the unfinished course structure.

## Consequences

### Positive

- **POS-001**: The pipeline is independently executable and inspectable, with no
  orchestration framework, embedding store, or search service.
- **POS-002**: Raw Markdown, JSON, page renders, responses, and figure decisions
  preserve evidence; model-reported fixes explain corrections without brittle
  formula-ID bookkeeping or a second content-authoring layer in Python.
- **POS-003**: Native DI figure crops cover rendered/vector content without
  recreating crop-coordinate transforms. PyMuPDF and Pillow align PDF/image
  handling with the reference implementations.

### Negative

- **NEG-001**: Source content leaves the machine for two Azure services.
  Authorized course material is eligible; private learner-model records are not.
- **NEG-002**: Formula extraction and model calls cost money. Page-by-page
  reconciliation trades additional latency and tokens for visual verification.
- **NEG-003**: Model-authored content is trusted, not independently checked.
  Self-reported confidence is not a calibrated accuracy measurement. A complete
  extraction does not prove mathematical fidelity; missing/clipped figure crops
  still use the separate figure-review workflow.
- **NEG-004**: The first version retains partial output on failure and requires
  a new destination for retries. It has no resume or automatic correction loop.
- **NEG-005**: PyMuPDF is offered under AGPL or a commercial license. Using the
  reference libraries does not relicense them under Catalyst's or Clew's license;
  distribution and hosted deployment need an appropriate licensing review.

## Alternatives Considered

### Use Catalyst and the original examples directly

- **ALT-001**: **Description**: Adopt the reference package and its orchestration,
  PDF helper, evaluation, and optional search/embedding machinery.
- **ALT-002**: **Rejection Reason**: The maintainer explicitly requested no
  Catalyst dependency and a small standalone ingestion tool.

### Keep DI text unchanged and use OpenAI only for figure filtering

- **ALT-003**: **Description**: Export baseline Markdown and formulas directly,
  adding semantic figure selection without page-image reconciliation.
- **ALT-004**: **Rejection Reason**: The maintainer explicitly requested OpenAI
  verification of content completeness, especially formulas.

### Isolate dependencies in a UV script or wait for the other branch

- **ALT-005**: **Description**: Avoid establishing a project environment in this
  branch, using script metadata or postponing environment setup.
- **ALT-006**: **Rejection Reason**: The maintainer selected a minimal shared
  `pyproject.toml` and `uv.lock` for this implementation.

### Retain the initial PDFium renderer

- **ALT-007**: **Description**: Keep PDFium for page rendering while using native
  DI figure crops.
- **ALT-008**: **Rejection Reason**: The maintainer explicitly requested the
  libraries used by ARGUS and ITSARAG, selecting PyMuPDF instead.

### Render every DI formula candidate as a separate equation

- **ALT-009**: **Description**: Require every DI formula ID to have its own math
  marker, even if OCR duplicated an equation fragment or misclassified prose.
- **ALT-010**: **Rejection Reason**: A live page demonstrated that this can force
  artificial/duplicate math into faithful Markdown. The maintainer selected
  audited corrections initially, then replaced formula accounting altogether
  with authoritative model-authored Markdown.

### Validate synchronized Markdown, formula IDs, and correction records

- **ALT-011**: **Description**: Require the model to maintain placeholders,
  formula definitions, and explicit merges/prose corrections, then gate output
  on Python checks relating those structures.
- **ALT-012**: **Rejection Reason**: Live runs failed on repeated symbols and
  inconsistent bookkeeping even when the text was usable. The maintainer
  explicitly chose final Markdown plus display-only fixes/confidence.

### Repair invalid model responses in a validation loop

- **ALT-013**: **Description**: Make additional model requests with validation
  feedback until the bookkeeping constraints pass, within an attempt limit.
- **ALT-014**: **Rejection Reason**: Not adopted. The maintainer chose to remove
  that content-validation contract rather than retry until the model satisfies
  it. Normal SDK transport retries are separate.

## Implementation Notes

- **IMP-006**: Keep the ADR Proposed until explicit human lifecycle approval.
  Reconcile ADR numbering and Python configuration with the other branch before
  merging; no existing course structure is assumed here.
- **IMP-007**: A new destination and completion manifest distinguish an actual
  digest from a partial failed run. Figure-review issues have a separate exit
  status; model-reported page fixes/confidence do not affect completion status.
- **IMP-008**: Local synthetic tests cover contracts, rendering, and failures.
  Representative live Azure/PDF evaluation is required to establish real
  extraction quality; mocks cannot establish that.
- **IMP-009**: Public PyPI artifact downloads failed TLS negotiation on the
  implementation host. The maintainer chose public configuration with portable
  lock generation pending rather than committing a mirror-specific lock.
  Generate and review `uv.lock` on a host with public PyPI access.
- **IMP-010**: The historical version-2 prototype recorded formula corrections
  and emitted per-page Markdown. New version-3 manifests retain page provenance
  and raw response paths, not a formula/correction ledger. Existing outputs are
  not migrated or overwritten.
- **IMP-011**: Only the final assembled `document.md` is published after all
  requested pages finish. Raw images/API responses remain diagnostic artifacts,
  not prematurely split course content. Page groups process a selected scope;
  they are not a resume or course-splitting mechanism.
- **IMP-012**: Parse once using CommonMark plus tables/HTML/dollar math, then
  publish the original string without AST-to-Markdown regeneration. Preserve
  `raw/assembled.md` on parse failure. Markdown's permissiveness and opaque
  LaTeX content mean this gate is not a linter or mathematical verification.

## References

- **REF-001**: [ARGUS reference at the inspected commit](https://github.com/Azure-Samples/az-ai-catalyst/blob/6c16d16b1140c103fd526b88645a0ea95336af9a/examples/argus.py).
- **REF-002**: [ITSARAG reference at the inspected commit](https://github.com/Azure-Samples/az-ai-catalyst/blob/6c16d16b1140c103fd526b88645a0ea95336af9a/examples/itsarag.py).
- **REF-003**: [PDF ingestion configuration and output contract](../PDF_INGESTION.md).
- **REF-004**: [Learner model specification](../LEARNER_MODEL.md), whose private
  records are outside this cloud ingestion boundary.
- **REF-005**: [ADR process](README.md).
- **REF-006**: [Unified Clew content structure](adr-0001-unified-clew-content-structure.md),
  the downstream course contract; this extraction step does not implement its
  sectioning, navigation, or source-map packaging.
