# Clew

Clew builds autonomous, portable agent skills for faithful document processing
and personalized learning. Each skill directory is intended to be a distributable
artifact: it contains its operating instructions, code, direct dependency
declarations, configuration guidance, workflow evals, and provenance rather than
depending on knowledge hidden elsewhere in this repository.

Clew hosts those independent skill projects in one UV workspace so development
uses a shared lockfile and virtual environment. A copied skill can still resolve
and install its declared dependencies as its own UV project. External services,
platform capabilities, host integrations, and dependencies on other skills must
be explicit.

Architecture decisions are indexed in [docs/adr/README.md](docs/adr/README.md).
[ADR-0003](docs/adr/0003-autonomous-portable-skills.md) defines the portable-skill
contract and makes coherent, complete, correct documentation part of the
definition of done for every task and pull request.
[ADR-0004](docs/adr/0004-faithful-multi-bundle-ingest.md) refines Ingest and
places executable script tests and fixtures in repository-owned `tests/` suites,
**outside skill directories**. A copied skill needs no repository tests to run.

## PDF Import

The local [clew-import skill](.agents/skills/clew-import/SKILL.md) accepts a PDF
or a directory, recursively identifies what needs conversion, and proposes exact
commands before execution. `chapter_1.pdf` defaults to a sibling `chapter_1`
bundle. Completed imports are checked by source hash, artifacts, and page scope;
existing conflicts require a decision rather than automatic replacement.

OneDrive folders and Files On-Demand are supported. Reading online-only PDFs
or import artifacts may download their contents; access or hydration failures
are reported rather than silently skipped. Actual symlinks and junctions remain
blocked. Retry cleanup still needs explicit approval: deletion in a shared
synchronized folder can propagate to collaborators and other devices.

The skill uses its bundled PDF converter and declares its dependencies in
[its own UV project](.agents/skills/clew-import/pyproject.toml). Clew resolves
all skills into one shared environment; setup uses
`uv sync --all-packages --locked`. Configure a root `.env` using the skill's
[`.env.example`](.agents/skills/clew-import/.env.example) as guidance, with real
Azure endpoints and a vision/structured-output deployment. Authentication uses
Entra ID through `DefaultAzureCredential`, not API keys. Do not commit `.env`.

From the repository root, a direct conversion looks like:

```powershell
uv run --package clew-import --locked --env-file .env python ".agents\skills\clew-import\scripts\digest_pdf.py" "C:\courses\chapter_1.pdf" --output "C:\courses\chapter_1"
```

This sends document content to configured Azure services and may incur charges.
The output must not already exist. A bundle includes the original PDF in
`source`, Markdown, figures, raw extraction evidence, a manifest, and diagnostics.
Exit `2` means completed but needs review; `1` means failed and `130` interrupted.
The skill asks before deleting a verified failed output and retrying.

For read-only inspection with the environment already installed:

```powershell
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\plan_imports.py" "C:\courses"
```

Add `--env-file .env` before `python` and `--check-env` after the input to check
the effective configuration without dumping its values. Plans show only resource
hosts and a configuration fingerprint for approval and change detection.
Inspection never converts or cleans up outputs. Plans use PowerShell quoting
and include argument arrays for other shells.

## Faithful Ingest

The [clew-ingest skill](.agents/skills/clew-ingest/SKILL.md) consumes one or
several explicitly selected completed Import bundles. Course, exercises, and
corrections may be separate or mixed sources. The agent chooses coherent
boundaries, meaningful note names, question/answer matches, and source-evidenced
relationships; small Python tools execute those decisions deterministically.
Every concrete ingest plan requires user approval before writing.

Ingest preserves supplied text, formulas, and figures. Missing exercises or
corrections are allowed; generated material and inferred prerequisite graphs
belong to future Enrich work. HTML Generate is also a separate future phase.

Each ingest creates one new directory:

```text
algebre/
  index.md
  courses/      course and section notes together, with meaningful names
  exercices/    exercise notes with question anchors
  corriges/     correction notes with answer anchors
  sources/
    cours/      original PDF, imported Markdown, referenced figures
    feuille/    another independently retained source
    corrige/    another independently retained source
  ingest.json   plan, provenance, file ownership, and review findings
```

Only required type directories are created. Stable source IDs prevent collisions
between identically named inputs. Original PDFs and Markdown are byte-identical
copies; only referenced figures are copied. Raw extraction evidence and logs stay
in the untouched original bundles. The retained subset is not a complete Import
bundle. All created files live under the ingest root: removing that exact
directory removes the entire ingest, with no shared or scattered assets.
There is no automatic deletion, overwrite, merge, or incremental update.

With the shared environment installed, inspect inputs without writing:

```powershell
uv run --package clew-ingest --locked --no-sync python -B ".agents\skills\clew-ingest\scripts\inspect_bundles.py" "C:\courses\course" "C:\courses\exercises" "C:\courses\corrections"
```

The skill reads the sources and authors a versioned plan using the
[documented format](.agents/skills/clew-ingest/references/formats.md).
Check that plan without creating its destination:

```powershell
uv run --package clew-ingest --locked --no-sync python -B ".agents\skills\clew-ingest\scripts\write_ingest.py" "C:\plans\ingest.json" --check
```

Review the boundaries, matches, evidence, exact output paths, and issues.
Only after approval, execute using the returned plan hash:

```powershell
uv run --package clew-ingest --locked --no-sync python ".agents\skills\clew-ingest\scripts\write_ingest.py" "C:\plans\ingest.json" --plan-sha256 "<approved plan hash>"
uv run --package clew-ingest --locked --no-sync python -B ".agents\skills\clew-ingest\scripts\validate_ingest.py" "C:\vault\algebre"
```

The destination parent must exist; the destination must not. Changed sources or
plans block execution. Ambiguous matches remain unlinked source content with
visible review findings. Failed partial output is preserved, never automatically
cleaned up or reused. Validation checks exact coverage and allowed structural
projection, hashes, anchors, relationships, and root ownership. It can operate
after external bundle locations disappear or the complete ingest is moved.

The tools make no cloud calls and require no Obsidian installation or plugin.
For a standalone copied skill, run `uv sync` in its directory initially,
`uv sync --locked` subsequently, omit `--package clew-ingest`, and use the local
`scripts` directory. Setup is separate from routine read-only inspection.

PDF Import and faithful Ingest are implemented. Enrich, HTML Generate, and other
source formats remain future work.

## Development

```powershell
uv sync --all-packages --locked
uv run --package clew-import --locked --no-sync python -B -m unittest discover -s "tests\clew_import"
uv run --package clew-ingest --locked --no-sync python -B -m unittest discover -s "tests\clew_ingest"
```

Script tests and fixtures belong to `tests/clew_import/` and `tests/clew_ingest/`,
never inside skill directories. Tests use synthetic documents and mocked/local
SDK transports, not live Azure. Workflow eval descriptions remain inside skills.
Ingest tests also install an unchanged copied skill into an independent UV
environment and run ingestion end to end. The offline fixture builds temporary
local wheels from the installed, locked runtime distributions, retaining their
licenses and rebuilding wheel records; it requires neither registry access nor
repository files at runtime. These fixtures remain outside the skill and are
removed with the test's temporary directory.

An additional live-PyPI resolution check is opt-in (it never contacts Azure or
a document service):

```powershell
$env:CLEW_TEST_STANDALONE = "1"
uv run --package clew-ingest --locked --no-sync python -B -m unittest discover -s "tests\clew_ingest" -k standalone_uv
Remove-Item Env:\CLEW_TEST_STANDALONE
```
