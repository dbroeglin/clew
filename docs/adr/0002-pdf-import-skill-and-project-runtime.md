# ADR-0002: PDF Import skill and project-level Python runtime

- Status: Proposed
- Date: 2026-10-04

## Context

[ADR-0001](0001-document-processing-pipeline.md) separates Import, Ingest,
Enrich, and Generate. Import converts source documents faithfully and preserves
originals, Markdown, and supporting assets for downstream processing.

The existing
[`digest_pdf.py` in dbroeglin/clew-old](https://github.com/dbroeglin/clew-old/blob/77c1e4c4569e4e8067f20d3809edd582b1f9a257/scripts/digest_pdf.py)
already converts PDFs into Markdown with LaTeX, instructional figures, provenance,
and diagnostic artifacts. It uses Azure Document Intelligence for layout and OCR,
then a vision-capable Azure OpenAI/Foundry deployment for figure classification
and page reconciliation. It authenticates through `DefaultAzureCredential`.

We want to reuse this implementation, not redesign conversion. A local skill
should guide execution, check configuration, and interpret the result. Python
dependencies and the UV virtual environment should belong to the project, not
the skill.

The initial request was to copy the script exactly. During clarification, the
user authorized one functional change: copy the original PDF into the resulting
directory. The existing script only records the source filename and hash; it
does not retain the PDF.

Alternatives include a verbatim script with source copying performed by the
skill, a rewritten importer, or a separate virtual environment inside the skill.
The first would make source preservation depend on the invocation path; the
others introduce unnecessary behavioral or environment divergence.

## Decision

This record is a proposal. Do not implement it until the user has reviewed and
accepted it.

### Scope and ownership

Implement the initial **PDF-only** Import phase as the first-party local skill
`clew-import` at `.agents/skills/clew-import/SKILL.md`. Bundle its executable at
`.agents/skills/clew-import/scripts/digest_pdf.py`.

The skill facilitates execution of this script. It does not perform a second
conversion, rewrite the generated Markdown, organize Obsidian notes, enrich
learning material, or generate HTML. TeX, Word, and PowerPoint remain future
Import implementations under ADR-0001; this skill must not claim to support them.

Use the upstream script at commit
`77c1e4c4569e4e8067f20d3809edd582b1f9a257` as the exact baseline. Its Git blob is
`d0eff2c0daa9e454360eb649db459b4c72408d42`. Retain upstream license obligations
and record this provenance in the skill documentation. Do not silently recopy a
moving upstream `main` later.

Apart from source preservation and its manifest reference, retain the script's
CLI, prompts, models, extraction logic, validations, diagnostics, and exit
semantics. Any further functional change requires separate agreement.

### Retained source and artifact contract

Each invocation requires a source PDF and an explicit, previously nonexistent
output directory. Preserve the script's refusal to overwrite any existing output,
including a partial run. Do not delete or reuse an output automatically.

After local PDF validation and creation of the output directory, but before the
first cloud submission, copy the complete input PDF to
`source/<original-filename>` within the output. This isolated subdirectory avoids
collisions with generated artifact names while retaining the original filename.
Copy the complete PDF even when `--pages` selects only part of it. Do not modify
or move the input file.

Treat copy failures as import failures through the existing diagnostic flow; do
not submit to cloud services when source preservation fails. Add a relative
`source.path` to the completion manifest, retaining its existing source name,
SHA-256, and page count. The copied bytes must match the recorded source hash.

Retain all existing outputs:

- `document.md`: converted Markdown with LaTeX and relative figure links.
- `figures/`: accepted instructional figures.
- `raw/`: layout results, page images, model responses, crops, and assembled
  Markdown used for inspection.
- `manifest.json`: completion status, configuration, source association, pages,
  figures, and review issues.
- `run.json`: progress and failure diagnostics, when the output has been created.

The result is a self-contained Import bundle, not an Obsidian course structure.
The caller selects its location. A bundle placed in a vault already retains its
source there; a bundle produced outside a vault must be preserved as a unit when
subsequently placed in the vault. The exact vault layout and that downstream
placement workflow remain deferred, not silently implemented by this skill.

### Project-level UV runtime

Create a repository-root `pyproject.toml` with Python `>=3.11` and
`[tool.uv] package = false`. Declare the script's direct runtime dependencies
using the upstream version ranges:

- `azure-ai-documentintelligence>=1.0.2,<2`
- `azure-identity>=1.25,<2`
- `markdown-it-py>=3,<5`
- `mdit-py-plugins>=0.4,<1`
- `openai>=2,<4`
- `pillow>=11.3,<13`
- `pydantic>=2.11,<3`
- `pymupdf>=1.26,<2`

Do not bring across unrelated upstream application dependencies. Commit the
project-level `uv.lock`; keep `.venv/` untracked. Do not add skill-level dependency
manifests, virtual environments, or inline script dependency metadata.

Run from the repository root, using the project interpreter and an explicit
root environment file. The invocation contract is:

```powershell
uv run --locked --env-file .env python .agents\skills\clew-import\scripts\digest_pdf.py "C:\path\input.pdf" --output "C:\path\new-import"
```

Use `uv sync --locked` for setup when needed. If UV is unavailable or the lockfile
does not match the manifest, report the blocker rather than switching to global
Python, installing ad hoc dependencies, or regenerating the lockfile during an
import. UV loads `.env`; do not add dotenv loading to the conversion script.

### Configuration and execution preflight

Provide a root `.env.example` documenting endpoint configuration and Entra ID
authentication without real credentials. Ignore `.env` and local environment
variants while keeping the example tracked.

Before execution, the skill must:

- Locate the repository root and confirm UV, the project manifest, lockfile, and
  a root `.env` are present.
- Require nonempty, non-placeholder `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` and
  `AZURE_OPENAI_DEPLOYMENT`, and exactly one of `AZURE_AI_PROJECT_ENDPOINT` or
  `AZURE_OPENAI_BASE_URL` in the effective environment. Account for inherited
  environment variables as well as `.env`; retain the script's authoritative
  endpoint validation.
- Explain that authentication uses `DefaultAzureCredential`, typically with an
  existing Azure CLI login, not an API key in `.env`. Surface authentication or
  authorization failures without automatically changing accounts or credentials.
- Confirm the PDF and a new output path, and pass requested optional CLI arguments
  through unchanged. Do not silently enable paid high-resolution OCR.
- Make clear that PDF content is sent to the configured Azure services and may
  incur charges; obtain the user's authorization for the selected document and
  destinations before a cloud run.

Missing or invalid configuration blocks execution with actionable guidance.
Never print `.env` contents, secrets, or tokens. Do not create a real `.env`,
provision Azure resources, change access permissions, or initiate login without
the user's direction. No additional wrapper executable is required; this
preflight is part of the skill's execution instructions.

### Result handling and implementation acceptance

Preserve and explain the existing exit codes: `0` means extracted, `2` means
completed but needs review, `1` means failed, and `130` means interrupted.
Exit `2` is not an unqualified success. Inspect the completion manifest on
completed runs and report artifact locations and review issues. On failure,
report available diagnostics and preserve partial artifacts; do not retry a
paid run automatically.

Before considering the implementation ready, verify the copied script differs
from the pinned upstream baseline only in the agreed source-preservation change.
Use offline tests with mocked service clients to cover a byte-identical retained
PDF, its manifest path and hash, copying the full PDF for selected-page imports,
copy failure before cloud submission, and refusal to overwrite existing output.
Exercise existing success, review, and failure behavior without real credentials
or paid calls. Verify project-level execution with `uv run --locked` and CLI help.
A live cloud smoke test requires separately authorized inputs and configuration.

## Consequences

- The first PDF Import implementation reuses established conversion behavior and
  keeps conversion separate from Ingest and Enrich.
- Source retention also works for direct script invocations, not only when an
  agent follows the skill.
- A pinned baseline and narrow documented deviation make future comparisons and
  upstream updates reviewable.
- One project environment and lockfile provide reproducible execution across
  skills, at the cost of managing shared dependency compatibility.
- The implementation depends on Azure services, an appropriate vision and
  structured-output deployment, authentication, network access, and usage costs.
  Preflight does not guarantee service availability or extraction fidelity.
- Each bundle retains a complete source PDF and substantial diagnostic artifacts,
  increasing storage needs and preserving potentially sensitive source content.
- Non-PDF formats, vault organization, artifact lifecycle policies, automatic
  retries/resume, and downstream pipeline phases remain outside this decision.
