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

The page prompt asks for minimal, image-evidenced corrections, not proofreading
or cosmetic rewriting. A non-mutating check flags known LaTeX commands leaked
into ordinary Markdown as `needs_review`, with page and block-line evidence.
It preserves the generated Markdown and raw responses; it does not repair
content, rescan old bundles, or prove transcription fidelity. See the skill
instructions for the bounded command list and exclusions.

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

Before planning, the skill inspects the identified vault and representative
notes, chooses a suitable existing learning-material container, and asks for
placement confirmation. Ambiguity prompts a focused question, never a silent
vault-root fallback. No fixed subject/level hierarchy is imposed. Missing
containers can be proposed but need explicit creation approval.

Ingest preserves supplied text, formulas, and figures. Missing exercises or
corrections are allowed; added learning aids belong to Enrich. New exercises and
inferred prerequisite graphs remain future work. HTML Generate is a separate
publication phase.

Each ingest creates one new directory:

```text
algebre/
  index.md
  courses/      course and section notes together, with meaningful names
  exercices/    exercise notes with question anchors
  corriges/     correction notes with answer anchors
  sources/
    cours/
      chapitre.pdf
      document.md
      figures/  referenced figures
    feuille/    another independently retained source
    corrige/    another independently retained source
  ingest.json   plan, provenance, file ownership, and review findings
```

Only required type directories are created. Stable source IDs prevent collisions
between identically named inputs. Original PDFs and Markdown are byte-identical
copies, stored together directly under each source ID without a second `source/`
directory; only referenced figures are copied. Raw extraction evidence and logs stay
in the untouched original bundles. The retained subset is not a complete Import
bundle. All created files live under the ingest root: removing that exact
directory removes the entire ingest, with no shared or scattered assets.
Approved new parent containers are shared vault organization and may remain;
they are never automatically deleted.
There is no automatic deletion, overwrite, merge, or incremental update.

With the shared environment installed, inspect inputs without writing:

```powershell
uv run --package clew-ingest --locked --no-sync python -B ".agents\skills\clew-ingest\scripts\inspect_bundles.py" "C:\courses\course" "C:\courses\exercises" "C:\courses\corrections"
uv run --package clew-ingest --locked --no-sync python -B ".agents\skills\clew-ingest\scripts\inspect_vault.py" "C:\vault"
```

The skill reads the sources and authors a versioned plan using the
[documented format](.agents/skills/clew-ingest/references/formats.md).
Check that plan without creating its destination:

```powershell
uv run --package clew-ingest --locked --no-sync python -B ".agents\skills\clew-ingest\scripts\write_ingest.py" "C:\plans\ingest.json" --check
```

Review the confirmed placement, any parent directories to create, boundaries,
matches, evidence, exact output paths, and issues.
Only after approval, execute using the returned plan hash:

```powershell
uv run --package clew-ingest --locked --no-sync python ".agents\skills\clew-ingest\scripts\write_ingest.py" "C:\plans\ingest.json" --plan-sha256 "<approved plan hash>"
uv run --package clew-ingest --locked --no-sync python -B ".agents\skills\clew-ingest\scripts\validate_ingest.py" "C:\vault\courses\PT\maths\algebre"
```

The destination must be a new direct child of the confirmed non-root vault
parent, outside earlier ingests. Missing parents need explicit approval and
`placement.create_parent: true`; read-only checks report their exact paths.
The illustrated hierarchy is not mandatory. Changed sources or
plans block execution. Ambiguous matches remain unlinked source content with
visible review findings. Failed partial output is preserved, never automatically
cleaned up or reused. Validation checks exact coverage and allowed structural
projection, hashes, anchors, relationships, and root ownership. It can operate
after external bundle locations disappear or the complete ingest is moved.

Generated source links open individual original PDF pages using `#page=N`, for
example `[page 2](../sources/feuille/chapitre.pdf#page=2)`. Multiple pages get
separate links; selected-page imports retain their original page numbers.
Source-authored links and retained Markdown remain faithful.

Ingest output is version 3; plans are version 2 with required placement, and note
schemas remain version 1. Approval hashes include the output version and full
placement. Earlier version-1 plans and version-1/2 outputs are rejected, not
migrated or modified: confirm placement, reuse the original Import bundles, and
approve a fresh plan/new destination without repeating PDF conversion.

The tools make no cloud calls and require no Obsidian installation or plugin.
For a standalone copied skill, run `uv sync` in its directory initially,
`uv sync --locked` subsequently, omit `--package clew-ingest`, and use the local
`scripts` directory. Setup is separate from routine read-only inspection.

## Course-linked Enrich

The [clew-enrich skill](.agents/skills/clew-enrich/SKILL.md) adds individual-question
hints and explanations of **supplied** corrections to a selected current
chapter. The agent authors the additions using ordinary file-editing tools;
Python checks their structure and source preservation, not their pedagogical
correctness. No embedded model, cloud service, or enrichment writer is needed.

Ordinary numbered questions and answers receive structural callouts and stable
anchors without rewriting the supplied text. Separate `aides/` notes use the
[small note contract](.agents/skills/clew-enrich/references/formats.md): question
and supplied-answer links, ordered `hint`/`explanation` callouts, and precise
course heading/block links. Existing anchors and human-written aids are preserved.
Missing corrections are valid; Enrich never invents answers or silently fixes
supplied mathematics. Ambiguous matches or unsupported reasoning need a user
decision. Each concrete editing scope is reviewed before changing user material.

Before approved edits, capture current exercise/correction text and the visible
chapter inventory in a **new local scratch file outside the chapter and repository**:

```powershell
uv run --package clew-enrich --locked --no-sync python -B ".agents\skills\clew-enrich\scripts\validate_enrich.py" "C:\vault\chapter" --capture "C:\scratch\enrich-before.json"
```

After the agent applies only the approved edits:

```powershell
uv run --package clew-enrich --locked --no-sync python -B ".agents\skills\clew-enrich\scripts\validate_enrich.py" "C:\vault\chapter" --before "C:\scratch\enrich-before.json"
```

Validation checks supplied lines, formulas, indentation, numbering and shared
instructions after removing only documented structural additions. It checks
unique anchors/IDs, question/answer agreement, and precise course targets.
Courses, sources, index, ingest record, and existing aid files must stay unchanged;
only new Markdown aid notes/directories under `aides/` are allowed.
Failures identify the cause and never repair notes or recapture the baseline.
The baseline contains local source text: do not commit or publish it.

This is an additive first increment, not a revision-history or approval-hash
framework. Ingest's exact-snapshot validator remains unchanged and will report
the later structural edits/new aids as changes. Current-note Generate deliberately
does not call that validator. See [ADR-0007](docs/adr/0007-course-linked-question-enrichment.md).

The [small English synthetic chapter](tests/clew_enrich/fixtures/chapter) and
[enriched overlay](tests/clew_enrich/fixtures/enriched) contain one short course,
two exercises/four questions, three supplied answers, six hints, and three
explanations. They illustrate current-note topology, not a complete retained
Import/Ingest archive. No private teaching material is included.

## Offline HTML Generate

The [clew-generate skill](.agents/skills/clew-generate/SKILL.md) publishes current
selected course, exercise, correction, and optional aid notes as one offline
interactive HTML file. The agent chooses scope/order and unresolved mappings in
a small [JSON layout](.agents/skills/clew-generate/references/formats.md);
deterministic Python reads the current notes and renders them. Human edits are
accepted. No Ingest validation, approval hashes, run ledger, Obsidian plugin,
server, embedded model, or Azure call is required.

Supply a chapter folder or its Ingest `index.md` rather than listing note files.
Generate discovers the `courses/`, `exercices/`, and `corriges/` topology,
optional aids, and existing metadata/relationships automatically. When only a
vault/container and course name are known, `inspect_notes.py --list-chapters`
lists chapter titles for the skill to select. Retained `sources/` documents and
hidden configuration are excluded; arbitrary explicit notes remain supported.

Expandable exercises display methods, progressive hints, inline supplied
corrections, supplied-answer explanations, and contextual course excerpts when
those already exist. Hints and explanations use the side panel; explanations
are available from a revealed supplied correction. Course links inside these
aids open the precise referenced passage in that panel, including when the
course is also in the reading view.
Unavailable controls are omitted; Generate never authors teaching material.
Guided-step tabs remain outside this release; the narrow Enrich skill above
authors the optional aids, never Generate.
The responsive layout uses light/dark styling; it is not a pixel-identical
copy of the separately authored mock.

Repeated view markup and static labels live in native `<template>` blocks in
the skill's `assets/template.html`. JavaScript clones/populates these views and
attaches behavior through stable data hooks; styling stays in `assets/style.css`.
Layout edits do not require a frontend framework or JavaScript markup changes.

HTML embeds styles, scripts, figures, and a pinned licensed MathJax SVG runtime.
It opens directly from the filesystem without CDNs or network rendering
dependencies. Original PDFs remain optional external page-addressed links:
moving the HTML can break those links without affecting the publication.
Supported Markdown and explicit limitations are documented in the skill:
raw HTML is escaped, while SVG, remote figures, Dataview, note transclusions,
and dynamic TeX extensions are unsupported rather than silently executed.

With the workspace environment installed:

```powershell
uv run --package clew-generate --locked --no-sync python -B ".agents\skills\clew-generate\scripts\inspect_notes.py" "C:\vault" --list-chapters
uv run --package clew-generate --locked --no-sync python -B ".agents\skills\clew-generate\scripts\inspect_notes.py" "C:\vault\courses\PT\maths\algebre"
uv run --package clew-generate --locked --no-sync python -B ".agents\skills\clew-generate\scripts\generate_html.py" "C:\plans\layout.json" --check
uv run --package clew-generate --locked --no-sync python ".agents\skills\clew-generate\scripts\generate_html.py" "C:\plans\layout.json"
```

Check scope and warnings before publication. The output parent must exist;
existing HTML is refused unless replacing that exact file was explicitly
requested with `--overwrite`. Source notes are never changed. A standalone
copy uses its own `uv sync` setup and local `scripts` paths, without `--package`.

PDF Import, faithful Ingest, course-linked hints/correction explanations, and
HTML Generate are implemented. Broader Enrich ambitions and other source
formats remain future work.

## Development

```powershell
uv sync --all-packages --locked
uv run --package clew-import --locked --no-sync python -B -m unittest discover -s "tests\clew_import"
uv run --package clew-ingest --locked --no-sync python -B -m unittest discover -s "tests\clew_ingest"
uv run --package clew-enrich --locked --no-sync python -B -m unittest discover -s "tests\clew_enrich"
uv run --package clew-generate --locked --no-sync python -B -m unittest discover -s "tests\clew_generate"
```

Script tests and fixtures belong to `tests/clew_import/`, `tests/clew_ingest/`,
`tests/clew_enrich/`, and `tests/clew_generate/`,
never inside skill directories. Tests use synthetic documents and mocked/local
SDK transports, not live Azure. Workflow eval descriptions remain inside skills.
Ingest tests also install an unchanged copied skill into an independent UV
environment and run ingestion end to end. The offline fixture builds temporary
local wheels from the installed, locked runtime distributions, retaining their
licenses and rebuilding wheel records; it requires neither registry access nor
repository files at runtime. These fixtures remain outside the skill and are
removed with the test's temporary directory.

Generate tests include a synthetic three-exercise/six-question chapter and an
independent copied-skill UV environment using temporary wheels built from the
installed locked runtime distributions (shared `tests/runtime_fixtures.py`).
Enrich tests use the compact English fixture for source-preservation/reference
checks and standalone validation. Generate also uses it to check question/answer
and aid matching. Optional browser checks use the root development dependency
Playwright and installed
Microsoft Edge, opening local HTML with HTTP(S) requests blocked:

```powershell
$env:CLEW_TEST_BROWSER = "1"
uv run --package clew-generate --locked --no-sync python -B -m unittest discover -s "tests\clew_generate"
Remove-Item Env:\CLEW_TEST_BROWSER
```

An additional live-PyPI resolution check is opt-in (it never contacts Azure or
a document service):

```powershell
$env:CLEW_TEST_STANDALONE = "1"
uv run --package clew-ingest --locked --no-sync python -B -m unittest discover -s "tests\clew_ingest" -k standalone_uv
Remove-Item Env:\CLEW_TEST_STANDALONE
```
