---
name: clew-import
description: >-
  Import local PDFs into faithful Markdown, LaTeX, figures, and retained-source
  bundles. Use when asked to import or convert a PDF, inspect a local directory
  for PDFs needing conversion, plan document imports, or retry a failed Clew
  import. Recursively discover sources, propose exact UV commands, and wait for
  approval before cloud conversion or failed-output cleanup. PDF-only; not
  Obsidian ingestion, learning-content enrichment, or HTML generation.
---

# Clew Import

Convert a local PDF, or PDFs discovered recursively in a local directory, into
faithful retained-source bundles for later document processing. Preserve source
content and meaning: do not summarize, translate, correct the author's claims,
organize Obsidian notes, enrich learning material, or generate HTML.

The executable is `scripts/digest_pdf.py` relative to this skill. Python
dependencies and supported Python versions are declared in this skill's
`pyproject.toml`. The skill can run as a standalone UV project. When installed
as a member of a UV workspace, use the host's shared lockfile and `.venv`; in the
Clew workspace select the `clew-import` package. Real configuration remains in
the execution project root's untracked `.env`; use this skill's `.env.example`
as the complete template. Never require repository ADRs or other documentation
to operate this skill.

## 1. Inspect without changing anything

Confirm the input location. If it was not supplied, ask for one. Default outputs
are beside their PDFs: `chapter_1.pdf` -> `chapter_1`, including nested PDFs.
Do not invent a vault layout or ask for a separate destination by default.

Inspect the root manifest, lockfile, UV availability, `.env` presence, and
project `.venv`. Never dump `.env` or inherited environment contents, or print
tokens or credentials. Show only the planner's resource hosts to identify the
cloud destinations for approval. An absent `.env` blocks conversion even if
inherited variables exist.

If the project environment is absent, do a read-only filesystem inventory first:
show candidate PDFs, obvious output conflicts, and the applicable setup command.
In the Clew workspace it is `uv sync --all-packages --locked`; for a copied
standalone skill, run `uv sync` in the skill directory to create its host-owned
lock and environment, then use `uv sync --locked` subsequently. Ask for setup
approval. Do not run `uv run` in its ordinary
sync mode during discovery: it can create an environment and install packages.
After approved setup, finish the detailed plan below and request conversion
approval separately. If UV or the lockfile is missing, report the blocker;
do not install UV or fall back to global Python. A missing Clew workspace lock is
a repository blocker. A standalone copy without a lock may create its host-owned
lock only through the separately approved initial `uv sync`.

With the project environment present, use the read-only planner from the
repository root. In PowerShell, for an input such as `C:\courses`:

```powershell
uv run --package clew-import --locked --no-sync --env-file .env python -B ".agents\skills\clew-import\scripts\plan_imports.py" "C:\courses" --check-env
```

If `.env` is absent, omit `--env-file .env` and `--check-env` to inspect sources
without loading configuration. The resulting plan will report the missing file.
For a copied standalone skill, run the same script from that skill's directory
without `--package clew-import`, using its local `scripts` path. Use
platform-appropriate path separators and shell quoting. The helper's
`command` fields are PowerShell syntax; on other shells, reconstruct commands
from their `argv` arrays with correct quoting.

Pass through any requested `--pages`, `--dpi`, `--max-output-tokens`,
`--high-resolution-ocr`, and `--debug` options to the planner. Do not enable
high-resolution OCR without an explicit request: it is a paid add-on.
Do not silently change rendering, page scope, deployment, or token budget.

The planner does not upload, convert, create directories, or delete anything.
Its exit code is `0` for a plan without blockers, `2` for a plan with conflicts
or preflight blockers, and `1` for an inspection error. These are **planner**
codes, not the converter's codes. Parse the JSON; do not treat `2` as a failed
conversion requiring cleanup.

During manual inventory, use the same rules as the helper:

- Scan case-insensitive `.pdf` extensions recursively, in deterministic path
  order. Do not traverse symlinks, junctions, or other path-redirection reparse
  points. Allow OneDrive folders and non-redirecting cloud placeholders.
- Exclude recognized Import bundles, including their retained `source` PDFs.
  Use metadata and structure, never directory names alone. Report ambiguous
  metadata as a conflict rather than silently hiding it or converting its copies.
- A new valid PDF with no existing target is **convert**.
- A completed manifest with matching source and retained-source SHA-256,
  required artifacts, and requested page coverage is **already converted**.
  Report `needs_review` issues, but do not reconvert it.
- Existing unrelated, stale, partial, malformed, or incomplete targets are
  **blocked**, as are target collisions or invalid PDFs.
- All pages are requested by default. A completed selected-page digest does not
  count as a completed full-document import.

Never replace a blocked target as part of routine discovery. Ask for the user's
decision with its precise path and reason. Permission to convert other PDFs
does not authorize deleting that directory. Do not follow a manifest reference
outside its bundle.

### OneDrive and shared synchronized folders

OneDrive is a supported source and output location, including Files On-Demand.
Do not reject a file or directory merely because Windows reports
`FILE_ATTRIBUTE_REPARSE_POINT`. The planner checks `st_reparse_tag`: Windows'
name-surrogate bit (`0x20000000`) marks path redirection, while cloud placeholder
tags do not. A reparse point whose tag is unavailable remains blocked; use this
same distinction during manual inventory and retry cleanup.

Reading PDFs, hashing files, or inspecting manifests may make OneDrive download
online-only content. If hydration, access, or enumeration fails, report the exact
path and error and ask for the file to be made available locally; do not skip it
silently or report a successful import. Do not change OneDrive settings.

Shared sources or outputs may change on another laptop or through a collaborator.
Recheck source identity and output ownership before execution or cleanup. Warn
that deleting a synchronized failed-output directory can propagate that deletion
to other devices and people. Approval for conversion is not deletion approval.

## 2. Propose the exact plan and get approval

Show the execution project directory, every candidate and classification,
source-to-output mapping, review issues, and preflight blockers. Include **all**
relevant commands: approved setup if needed, configuration actions still needed,
and one exact conversion command per eligible PDF. Do not expose secrets in
those commands. If nothing needs conversion, say so and report any blocked or
review items; do not ask for an empty cloud run.

Configuration must have non-placeholder values for:

- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- Exactly one of `AZURE_AI_PROJECT_ENDPOINT` or `AZURE_OPENAI_BASE_URL`

`--check-env` validates the effective environment after UV loads `.env`, including
inherited variables, using the converter's endpoint rules. File presence is not
proof that configuration or authentication is valid. Use `.env.example` for
guidance; do not create a real `.env` or copy its placeholder values as a fix.

Authentication is Entra ID through `DefaultAzureCredential`, commonly an
existing Azure CLI login. Do not put API keys in `.env`, automatically log in,
switch accounts, provision resources, or change permissions. Report actionable
configuration/authentication failures.

Explain that the selected PDFs, page images, and extracted text are transmitted
to the configured Azure Document Intelligence and OpenAI/Foundry services and
can incur charges. Obtain user approval for the exact PDFs, destinations,
options, and commands before running conversions. A request to **plan** is not
permission to execute. A plan approval is not permission to delete outputs.

## 3. Execute the approved commands

Run sequentially from the execution project root with its UV environment:

```powershell
uv run --package clew-import --locked --env-file .env python ".agents\skills\clew-import\scripts\digest_pdf.py" "C:\courses\chapter_1.pdf" --output "C:\courses\chapter_1"
```

Immediately before each run, recheck the source SHA-256 against the plan and
verify that the resolved output is absent, including dangling links. Record
those facts and the exact paths for ownership checks if this run fails.
Recheck the planner's configuration fingerprint without printing settings.
If the source, destination, options, or configuration changed,
stop and obtain approval for an updated plan.

Preserve the converter's outputs and result meanings:

| Exit | Meaning | Action |
| --- | --- | --- |
| 0 | Extracted | Inspect the manifest and report the bundle. |
| 2 | Completed, needs review | Inspect and report issues; do not delete or retry. |
| 1 | Failed | Pause immediately and follow the retry gate below. |
| 130 | Interrupted | Preserve artifacts; do not resume without approval. |

A zero exit is not enough: confirm that the manifest, Markdown, retained PDF,
and referenced artifacts form a complete bundle for the requested scope. Do
not rewrite model output or treat a hash match as a content-fidelity guarantee.
Inspect diagnostics if a completion check fails.

`source/<original-filename>` contains a byte-identical copy of the entire input
PDF, even for a selected-page import. `document.md`, `figures`, `raw`,
`manifest.json`, and `run.json` remain together. No input PDF is moved or changed.
If the output is outside a vault, future Ingest must preserve the bundle when
placing it in the vault. This skill does not structure Obsidian notes.

## 4. Failure: explicit delete-and-retry gate

On failure, stop the batch. Show the failed command, relevant error, and
diagnostic locations. Do not expose configuration or SDK credentials in a
report. Ask whether the user approves **deleting this run's exact output
directory and retrying this command**, warning that diagnostics and partial
artifacts will be lost and paid cloud work may repeat.

Before a specifically approved deletion:

1. Re-inspect the exact resolved path. Verify it was absent immediately before
   this run and created by the run, using your recorded observations and
   `run.json` where available. Do not rely only on a directory name.
2. Reject a symlink, junction, path-redirection reparse point, or a reparse point
   with an unavailable tag, the selected input directory,
   execution project root, source location, any ancestor of an original planned input, or any
   pre-existing blocked target. Inspect contents and stop if unexpected files,
   human edits, concurrent modifications, or uncertain ownership are present.
   A OneDrive cloud placeholder alone is not a reason to reject cleanup, but the
   user must approve the exact deletion and its synchronized consequences.
3. Show the exact cleanup command, addressed with literal-path semantics, and
   the exact retry command. On PowerShell the cleanup is
   `Remove-Item -LiteralPath '<verified-exact-output>' -Recurse`; never use
   wildcards, an unresolved variable, or a parent directory.
4. Delete only that verified failed output, then recheck source/configuration
   and run the approved conversion command. If deletion fails, stop: never
   claim cleanup succeeded or retry into an existing directory.

If no output was created, explain that no deletion is needed and ask permission
to retry. Setup or configuration failure never justifies deleting an import
output. Correct diagnosed settings only with agreement. Each repeated failure
requires a fresh delete-and-retry approval; never implement an automatic loop.
If retry is declined, leave artifacts intact and ask how to handle the remaining
plan. Interruption does not imply permission to restart.

## Provenance and maintenance

`digest_pdf.py` is copied from `dbroeglin/clew-old` at commit
`77c1e4c4569e4e8067f20d3809edd582b1f9a257`, blob
`d0eff2c0daa9e454360eb649db459b4c72408d42`, under the repository MIT license.
The only functional deviation is source preservation, its hash verification,
and the relative `source.path` in the manifest. Conversion prompts, CLI,
validation, and exit codes remain upstream behavior.

Do not fetch a moving upstream revision during an import. Offline tests and
workflow evaluations are bundled in this skill under `tests` and `evals`.
In Clew run:

```powershell
uv run --package clew-import --locked python -m unittest discover -s ".agents\skills\clew-import\tests"
```

For a standalone copy, run the equivalent command from the skill directory
without `--package clew-import`. Tests and evaluations must not make real cloud
calls or remove user data.
