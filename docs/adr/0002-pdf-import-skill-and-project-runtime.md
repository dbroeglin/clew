# ADR-0002: PDF Import skill and project-level Python runtime

- Status: Accepted
- Date: 2026-10-04

> **Supersession note:** [ADR-0003](0003-autonomous-portable-skills.md)
> supersedes this record's repository-root ownership of dependency declarations,
> configuration templates, and tests. Its PDF Import behavior, safety gates,
> artifact contract, and implementation provenance remain accepted.
> [ADR-0004](0004-faithful-multi-bundle-ingest.md) subsequently places script tests
> outside skills and refines downstream vault retention to a source subset.
> Import still produces and preserves complete bundles.

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

The skill must also accept a local directory, discover PDFs needing conversion,
and propose an exact execution plan before running anything. Existing outputs
must be inspected rather than overwritten. Failed conversions may be retried
only after explicit approval to remove their output and rerun the command.

The initial request was to copy the script exactly. During clarification, the
user authorized one functional change: copy the original PDF into the resulting
directory. The existing script only records the source filename and hash; it
does not retain the PDF.

Alternatives include a verbatim script with source copying performed by the
skill, a rewritten importer, or a separate virtual environment inside the skill.
The first would make source preservation depend on the invocation path; the
others introduce unnecessary behavioral or environment divergence.

## Decision

The user accepted this decision and its clarified directory workflow on
2026-10-04 and authorized implementation.

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
output directory at the script level. The skill defaults to a sibling directory
named after the source file without its final extension: `chapter_1.pdf` becomes
`chapter_1/` beside that PDF. Pass this resolved location explicitly through
`--output`; do not change the script's CLI to infer it.

Preserve the script's refusal to overwrite any existing output, including a
partial run. Do not delete or reuse an output automatically.

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

### Directory discovery and proposed execution plan

Accept either an individual local PDF or a local directory. Directory mode scans
recursively for `.pdf` files, case-insensitively, and sorts discovered source
paths for a deterministic plan. Do not follow symbolic links or directory
junctions out of the selected tree.

OneDrive and other shared synchronized folders are valid input and output
locations. Windows cloud placeholders are non-redirecting reparse points, not
symbolic links or junctions, and must not be blocked solely by the reparse-point
attribute. Inspect the name-surrogate tag bit to identify path redirection;
block reparse points whose tag is unavailable. File reads may hydrate online-only
content. Surface hydration and access failures, and retain source-change checks.
Retry deletion requires explicit approval with a warning that synchronization
can propagate the deletion to other people and devices.

Exclude recognized generated Import bundles and their entire contents, including
their retained `source/` PDFs, from recursive discovery. Recognition must use
consistent import metadata and artifact structure, or an output tracked as
created by the current invocation; a directory name alone is not sufficient.
Malformed metadata or an ambiguous candidate output is a conflict to report,
not grounds to silently hide a directory or treat its contents as fresh inputs.

For each source, determine its sibling target and classify it:

- **Convert:** the target does not exist and the PDF passes local preflight.
- **Already converted:** a valid completion manifest has status `extracted` or
  `needs_review`, the current PDF's SHA-256 matches the manifest, and required
  artifacts exist. These include `document.md`, the retained original with a
  matching hash, and the page and figure artifacts referenced by the manifest.
  Referenced paths must resolve inside the bundle.
- **Blocked:** the target is a file, an unrelated or unverifiable directory, a
  partial or stale import, has missing artifacts, or collides with another
  discovered source's target. Report invalid inputs as blocked as well.

Directory mode requests all pages by default. Only classify an existing import
as already converted when its page coverage matches the requested scope; a
selected-page digest is not a completed whole-document conversion. An explicit
page subset must be shown in the plan and passed through unchanged. A matching
`needs_review` bundle is skipped for conversion but its review issues are reported.
Matching hashes alone do not prove extraction fidelity.

Do not automatically replace blocked targets. Ask for the user's decision,
identifying the exact source, target, and reason. Never infer permission to remove
unrelated files or human edits from approval of other conversions.

Produce a plan showing every candidate, its classification and reason, source
and target paths, and all relevant commands. Include the repository working
directory, any required setup or configuration remediation, and one fully quoted
UV conversion command per eligible source, with its actual arguments. Plans must
be actionable without exposing environment values or credentials. If there is
nothing to convert, report that and any conflicts or review items.

Discovery and plan preparation are read-only. Wait for user approval before
environment setup or conversion; approval must cover the PDFs, configured cloud
destinations, options, and potential charges. Execute approved conversions
sequentially, rechecking target absence and source identity before each command.
If the source or relevant configuration changes after planning, obtain approval
for the updated plan rather than silently using the old authorization.

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
uv run --locked --env-file .env python ".agents\skills\clew-import\scripts\digest_pdf.py" "C:\path\chapter_1.pdf" --output "C:\path\chapter_1"
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
- Confirm the discovered PDFs and their proposed sibling output paths, and pass
  requested optional CLI arguments through unchanged. Do not silently enable
  paid high-resolution OCR.
- Make clear that PDF content is sent to the configured Azure services and may
  incur charges; obtain the user's authorization for the selected document and
  destinations before a cloud run.

Missing or invalid configuration blocks execution with actionable guidance.
Never print `.env` contents, secrets, or tokens. Do not create a real `.env`,
provision Azure resources, change access permissions, or initiate login without
the user's direction. No additional wrapper executable is required; this
preflight is part of the skill's execution instructions.

A read-only `scripts/plan_imports.py` helper inside the skill supports deterministic
discovery, PDF and manifest inspection, and exact command generation. It uses
the project environment but never sets it up, submits documents, deletes outputs,
or executes its proposed commands. If that environment is absent, present an
initial read-only filesystem inventory and request setup approval before using
the helper to complete the conversion plan. This is not a conversion wrapper;
approval, execution, configuration remediation, and retries remain skill actions.

### Result handling and approved retry

Preserve and explain the existing exit codes: `0` means extracted, `2` means
completed but needs review, `1` means failed, and `130` means interrupted.
Exit `2` is not an unqualified success. Inspect the completion manifest on
completed runs and report artifact locations and review issues. Exit `2` does not
trigger delete-and-retry.

If a conversion fails, pause the batch immediately. Report the failed command,
error, and available diagnostics, then ask whether the user approves deleting
that run's exact output directory and retrying. Explain that deletion discards
partial artifacts and diagnostics, and the retry can repeat paid cloud work.
Never delete or retry before this specific approval. Declining leaves the output
intact; ask how to proceed with the remaining plan.

Before an approved deletion, verify that the exact resolved target was absent
before this conversion and created by it. Reject targets that are the input
directory, source location, repository root, an ancestor of an original input, or a link
or junction. Check for unexpected files or modifications and stop for a decision
if ownership is uncertain. Delete only that verified target, never a wildcard,
parent directory, or other import output. A pre-existing blocked target is not
eligible for this failed-run cleanup procedure.

After deletion, rerun the same approved conversion command, correcting a
diagnosed configuration issue only with the user's agreement. If no output
directory was created, explain that cleanup is unnecessary and ask permission
to retry without deletion. Each subsequent failure needs a fresh approval;
there is no automatic retry loop. A setup or configuration failure does not
authorize deletion of any conversion output.

### Implementation acceptance

Before considering the implementation ready, verify the copied script differs
from the pinned upstream baseline only in the agreed source-preservation change.
Use offline tests with mocked service clients to cover a byte-identical retained
PDF, its manifest path and hash, copying the full PDF for selected-page imports,
copy failure before cloud submission, and refusal to overwrite existing output.
Exercise existing success, review, and failure behavior without real credentials
or paid calls. Verify project-level execution with `uv run --locked` and CLI help.
A live cloud smoke test requires separately authorized inputs and configuration.

Also exercise the skill workflow with fixtures for nested source directories,
recognized output exclusion, sibling naming and collisions, matching and changed
hashes, missing artifacts, selected-page versus all-page coverage, `needs_review`
results, and unrelated existing targets. Verify that plans contain all commands,
no setup or conversion runs before approval, failures pause the batch, and
cleanup and retries require fresh approval scoped to a verified failed output.

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
- Recursive planning avoids repeated conversion while making conflicts and
  review work visible. Hashing sources and checking artifacts adds local I/O.
- Explicit retry approval prevents destructive cleanup and repeated cloud charges
  from happening silently, but batch execution may require user intervention.
- Non-PDF formats, vault organization, artifact lifecycle policies, automatic
  retries/resume, and downstream pipeline phases remain outside this decision.
