# Clew

Agent skills for faithful document processing and personalized learning.
Architecture decisions are indexed in [docs/adr/README.md](docs/adr/README.md).

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

The skill uses the bundled PDF converter and a **project-level** UV environment.
Setup uses `uv sync --locked`. Configure a root `.env` using `.env.example` as
guidance, with real Azure endpoints and a vision/structured-output deployment.
Authentication uses Entra ID through `DefaultAzureCredential`, not API keys.
Do not commit `.env`.

From the repository root, a direct conversion looks like:

```powershell
uv run --locked --env-file .env python ".agents\skills\clew-import\scripts\digest_pdf.py" "C:\courses\chapter_1.pdf" --output "C:\courses\chapter_1"
```

This sends document content to configured Azure services and may incur charges.
The output must not already exist. A bundle includes the original PDF in
`source`, Markdown, figures, raw extraction evidence, a manifest, and diagnostics.
Exit `2` means completed but needs review; `1` means failed and `130` interrupted.
The skill asks before deleting a verified failed output and retrying.

For read-only inspection with the environment already installed:

```powershell
uv run --locked --no-sync python -B ".agents\skills\clew-import\scripts\plan_imports.py" "C:\courses"
```

Add `--env-file .env` before `python` and `--check-env` after the input to check
the effective configuration without dumping its values. Plans show only resource
hosts and a configuration fingerprint for approval and change detection.
Inspection never converts or cleans up outputs. Plans use PowerShell quoting
and include argument arrays for other shells.

Only PDF Import is currently implemented. Obsidian Ingest, Enrich, Generate, and
other source formats are separate phases or future work.

## Development

```powershell
uv sync --locked
uv run --locked python -m unittest discover -s tests
```

Tests use synthetic documents and mocked/local SDK transports, not live Azure.
