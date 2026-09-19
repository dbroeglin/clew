# PDF ingestion

`scripts/digest_pdf.py` is a standalone PDF digestion tool, not a course-content
builder. It produces Markdown with LaTeX and a curated figure directory.
The first-party [ingestion skill](../.agents/skills/ingestion/SKILL.md) guides
agents through running and reviewing it.

The result is an intermediate extraction, not a `clew/v1` course package.
After the whole document is processed, a separately authorized packaging step
can use the [course-content contract](../.agents/skills/course-content/SKILL.md).
This script does not implement its sectioning, navigation, or source-map schema.

## Pipeline

1. Analyze the PDF with Document Intelligence `prebuilt-layout`, requesting
   Markdown, the `formulas` add-on, and figure output. Preserve both the JSON and
   the original Markdown. Request Unicode-code-point offsets so Python slicing
   works with accents, mathematical symbols, and non-BMP characters.
2. Use figure IDs and page regions from the JSON to retrieve native PNG crops.
   This captures rendered figure regions, including vector drawings, rather
   than dumping embedded PDF image objects. Native crops avoid duplicating
   page-rotation and CropBox transforms and normally exclude captions.
3. Ask the vision model to distinguish instructional figures from logos, icons,
   decoration, and text/table/equation-only crops. Keep source captions separate
   from generated alt text. A small diagram is not rejected merely for its size.
4. Render each selected PDF page with PyMuPDF, respecting its rotation and
   CropBox. Give OpenAI that image, baseline Markdown, OCR formula hints, and
   available figure asset paths. The model returns final corrected Markdown
   containing its LaTeX, tables, captions, and image links, plus a list of fixes
   and self-reported confidence.
5. Treat the returned Markdown as authoritative. Python displays each fix and
   confidence but does not verify them, apply a threshold, reconstruct formulas,
   count markers, or rewrite the model's content. Basic response-format parsing
   and service/IO error handling remain; there is no semantic repair loop.
6. After every requested page has finished, assemble one `document.md`, keeping
   each model-authored page unchanged and adding page-boundary comments.
   Parse the assembled Markdown once as a format gate, without rendering or
   rewriting it. A parser failure rejects publication. Splitting into
   course-content files is a separate, later operation, not part of the
   page-processing loop.

This borrows the OCR-plus-visual-evidence pattern from
[ARGUS](https://github.com/Azure-Samples/az-ai-catalyst/blob/6c16d16b1140c103fd526b88645a0ea95336af9a/examples/argus.py)
and the DI-figure approach from
[ITSARAG](https://github.com/Azure-Samples/az-ai-catalyst/blob/6c16d16b1140c103fd526b88645a0ea95336af9a/examples/itsarag.py).
It does not depend on or copy Catalyst's implementation or prompts. There is no
MLflow, Azure AI Search, embedding pipeline, course schema, or learner-model
mutation. PDF processing uses PyMuPDF and Pillow, matching the reference
implementations' libraries. PyMuPDF is offered under AGPL or a commercial
license; review the applicable terms before distribution or hosted deployment.

## Setup

Install [UV](https://docs.astral.sh/uv/). The project targets public PyPI.
**A portable, current `uv.lock` is pending**: this implementation host can install
from its configured mirror, but public PyPI artifact downloads fail TLS
negotiation. An existing mirror-backed lockfile has been preserved rather than
replaced; it predates the parser dependencies now installed in the local
environment and is not committed in this change. Use `uv run --no-sync` in this
worktree. On a machine with public
PyPI access, regenerate and review the lockfile for commit, then restore the
environment:

```powershell
uv lock
uv sync --locked
Copy-Item .env.example .env
```

Fill in `.env` with your service endpoints and deployment name, not keys:

| Variable | Meaning |
| --- | --- |
| `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` | The DI resource's custom-subdomain HTTPS endpoint, e.g. `https://RESOURCE.cognitiveservices.azure.com`. |
| `AZURE_AI_PROJECT_ENDPOINT` | Foundry project endpoint, e.g. `https://RESOURCE.services.ai.azure.com/api/projects/PROJECT`. |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name of an OpenAI model supporting **image input, Responses, and structured outputs**. |
| `AZURE_OPENAI_BASE_URL` | Alternative to the project endpoint: the complete resource API URL ending in `/openai/v1/`. Set exactly one of this and `AZURE_AI_PROJECT_ENDPOINT`. |

The script uses `DefaultAzureCredential`. Authenticate locally with `az login`,
or use an appropriately authorized managed identity/service principal. The
identity needs access to **both** services. A Foundry project does not by itself
grant access to an arbitrary DI resource: provide its actual endpoint and
permissions rather than deriving it from the project URL.

The OpenAI client appends `/openai/v1/` to a project endpoint and obtains an
Entra token for `https://ai.azure.com/.default`. DI's client uses its own
`https://cognitiveservices.azure.com/.default` scope and API `2024-11-30`.
The OpenAI v1 endpoint needs no dated API-version parameter. API keys and
connection-string discovery are deliberately not part of this script.

Responses input items explicitly use `type: "message"` with typed text/image
content. Foundry can reject a multimodal message without that discriminator
with HTTP 400, `invalid_value`, at `input[1]`; this is a request-format problem,
not a PDF or authentication error.

For relevant official API contracts, see
[DI Markdown](https://learn.microsoft.com/azure/ai-services/document-intelligence/concept/markdown-elements),
[formula extraction](https://learn.microsoft.com/azure/ai-services/document-intelligence/concept/add-on-capabilities#formula-extraction),
[figure output](https://github.com/Azure/azure-sdk-for-python/blob/azure-ai-documentintelligence_1.0.2/sdk/documentintelligence/azure-ai-documentintelligence/samples/sample_analyze_result_figures.py),
and [OpenAI structured outputs](https://learn.microsoft.com/azure/ai-foundry/openai/how-to/structured-outputs).

## Run

Start with a representative selection including equations and a useful figure:

```powershell
uv run --locked --env-file .env python scripts\digest_pdf.py course.pdf --output digests\course-sample --pages 1-3,7
```

For the whole PDF, use a different output directory and omit `--pages`:

```powershell
uv run --locked --env-file .env python scripts\digest_pdf.py course.pdf --output digests\course
```

If environment variables are already set, omit `--env-file .env`. Run `--help`
without credentials to see all options.

- `--pages`: one-based original PDF page numbers, not printed page labels.
  Accepts individual pages, ranges, or comma-separated groups such as `13`,
  `13-15`, or `13-15,20`. Only those pages are analyzed and reconciled; the source
  PDF is still uploaded in full. Output keeps the original page numbers.
- `--dpi`: page-image rendering resolution, default `200`, allowed `72-600`.
  Native DI figure crops are not resampled by this option.
- `--high-resolution-ocr`: enable the additional paid small-print OCR feature.
  Formula extraction is always enabled and also incurs add-on charges.
- `--max-output-tokens`: per-request response budget, default `16000`; adjust within
  your deployment's limit for dense pages or models that spend tokens reasoning.
- `--debug`: also print full exception tracebacks in the terminal. Once a new
  output directory has been created, failures are recorded in `run.json` even
  without this flag. It does not enable verbose SDK HTTP/header logging.

Each run performs one DI analysis, one model request per single-page figure
candidate, and one per selected page, excluding SDK retries. Try a small sample
before paying for a long document.
`store=False` is set on OpenAI requests; this does not mean local-only processing
or override Azure's service-side retention and abuse-monitoring policies.

Only upload material authorized for these services. Never upload private
learner-model records or credentials. The original PDF is not modified.

## Output contract

```text
digest/
  document.md
  manifest.json
  run.json
  figures/
    figure-0001.png
  raw/
    assembled.md
    document-intelligence.json
    document-intelligence.md
    figures/
      figure-0001.png
      figure-0001.response.json
    pages/
      page-0001.png
      page-0001.response.json
```

`document.md` is written only after the entire requested pass finishes and the
assembled Markdown parses. It
preserves each model-returned Markdown string verbatim, separated by provenance
comments such as `<!-- page: 13 -->`. The model is given relative `figures/`
paths to use directly. No final per-page Markdown files or course sections are
published during extraction. Raw page images/responses are diagnostic evidence,
not a premature content split.

The format gate uses `markdown-it-py` with CommonMark, tables, HTML, and dollar
math support. Markdown is permissive: many unconventional strings and unmatched
delimiters are valid literal text. This is not a linter, HTML validator, LaTeX
compiler, or content/accuracy check. The parser's output is not rendered back
to Markdown, so successful parsing does not alter the model's text. On failure,
`raw/assembled.md` and the page responses remain available, but no final
`document.md` or completion manifest is published.

`manifest.json` (schema version 3) records the source filename and SHA-256,
original page count, selected page records, model/analysis configuration, every figure
decision and reason, source captions, raw evidence paths, and review issues.
The full JSON preserves all DI spans, polygons, and formula observations.
This is a versioned **extraction** manifest, not the forthcoming course schema.

Each page response has two fields: `markdown` and `fixes`. A fix contains
`description` and `confidence`; the prompt asks for a self-reported value from
0 to 1. These are displayed exactly as reports, without range checks, semantic
checks, confidence thresholds, or effects on completion status. Fix reports
remain in the raw response snapshots, but are not converted into a separate
validated correction ledger or manifest formula inventory. Self-reported
confidence is not an independent accuracy measurement.

Earlier manifest versions used per-page Markdown files and formula-ID
accounting. Existing outputs are not rewritten or migrated by a new run.

`run.json` is a diagnostic record, not a completion marker. It tracks the current
stage, input/output paths, selected pages, DI operation ID, and timestamps.
On failure it retains the exception type, message, explicitly chained causes,
available HTTP status, service code/request IDs, relevant raw artifact path,
and traceback. A stopped process may leave it at `running`; that is not evidence
of a completed digest.
The script writes this record only in a directory it created for that run.

Only accepted figures appear in `figures/`. Rejected and uncertain candidates
remain in `raw/figures/` for auditing. The page model receives a null asset path
for an uncertain figure and is instructed not to invent a link. Its returned
Markdown is not subsequently rewritten by Python.
Cross-page figures are explicitly marked for review rather than using only the
last bounding region. They have a native crop and manifest reason but no
vision-classification response.

| Exit code | Interpretation |
| --- | --- |
| `0` | Every requested page was processed and the assembled document parsed, with no pending figure reviews. |
| `2` | The assembled document exists, but figure-selection issues require review. Model-reported fixes/confidence do not cause this status. |
| `1` | The command failed. Inspect the reported stage, `run.json`, and any completion manifest before using its output. |
| `130` | Interrupted with Ctrl+C. Local diagnostics are retained; an already submitted Azure analysis may still finish server-side. |

The script refuses existing output directories, including partial runs. Retry
into a new directory. There is no automatic resume, overwrite, cleanup, or
fallback that quietly bypasses a failed model/service call.

## Troubleshooting

An **output-already-exists** error is a preflight refusal, not an Azure error.
The script does not start another analysis or change the existing directory.
It now distinguishes an existing completed digest from incomplete/unrecognized
output and shows any previous recorded stage and error. Older partial runs
without `run.json` have no saved traceback: that original cause cannot be
recovered from the directory-conflict error alone.

Choose a fresh output path; do not create it first. In this worktree's already
installed environment, a diagnostic retry can use:

```powershell
uv run --no-sync --env-file .env python scripts\digest_pdf.py course.pdf --output digests\smoke-retry --pages 1-3 --debug
```

To isolate a failing page or test a noncontiguous group, use a new destination:

```powershell
uv run --no-sync --env-file .env python scripts\digest_pdf.py course.pdf --output digests\page13 --pages 13 --debug
uv run --no-sync --env-file .env python scripts\digest_pdf.py course.pdf --output digests\selected --pages "13-15,20" --debug
```

`--no-sync` uses the existing environment without re-resolving dependencies.
Use `--locked` instead after restoring a reviewed project lockfile. Neither flag
makes extraction offline: a real PDF run still calls Azure.

Errors identify the stage (configuration, PDF rendering, DI submission/polling,
figure download/classification, page reconciliation, or output writing) and the
page/figure where relevant. Authentication, missing deployment/endpoint, quota,
network, schema, and filesystem errors include targeted next steps. Inspect a
saved report without resubmitting the PDF:

```powershell
Get-Content digests\smoke-retry\run.json -Raw
(Get-Content digests\smoke-retry\run.json -Raw | ConvertFrom-Json).error.traceback
```

Only selected service diagnostic headers are recorded, not authorization
headers, environment variables, or complete HTTP request bodies. Nevertheless,
exception messages and raw responses can contain source excerpts or resource
identifiers; keep diagnostic files private and redact them before sharing.
If writing the report itself fails, the terminal reports that separately
without replacing the original error.

## Limits and quality review

The paid DI tier supports PDFs up to 500 MB and 2000 pages; the free tier returns
only two pages and has a smaller file-size limit. The script checks that **all**
requested page numbers actually returned, so a truncated free-tier analysis
cannot masquerade as a complete extraction. Unlock password-protected PDFs
before ingestion.

DI can miss a figure or split/group it imperfectly. Native crops have no fixed
DPI guarantee. Clipped/ambiguous crops need review; this tool does not invent
local bounding boxes or silently repair them. A page's image lets the model
recover textual content missed by OCR, but it cannot manufacture a missing
DI figure crop. Compare pages with figures against the resulting asset set.

The selected model owns the content corrections and final Markdown. Apart from
the assembled-document format parse, Python
does not audit its mathematics, compare prose with OCR, or validate its claimed
fixes. This deliberately avoids failures from duplicated OCR detections,
repeated symbols, and conflicting formula bookkeeping. A complete run is not
independent proof of transcription accuracy.

DI formula confidence is documented as hard-coded and is not used as a quality
threshold. Model-reported fix confidence is also informational only. Optional
human review is separate from this extraction pass; it does not turn into an
automatic validation/retry loop.

The local regression suite uses synthetic PDFs, the real PDF renderer, and
mocked Azure responses. It checks the plumbing, verbatim Markdown handling,
display-only fixes, the parser-failure gate, and publication after all pages finish, **not** the
correctness of model-authored content:

```powershell
uv run --locked python -m unittest discover -s tests -v
```

`.env`, `.venv`, and the `digest/` and `digests/` output roots are ignored by Git.
If you choose a different output location, protect it yourself. Do not commit
source PDFs or generated content without permission to share that material.
