# Skills reference

For the end-to-end workflow and example skill prompts, start with the
[README](../README.md). This page covers runtime setup, artifact contracts,
direct script commands, limitations, and development checks. Normal use is
through a compatible agent calling the skills; direct commands do not replace
the skills' review and approval gates.

- [Runtime and portability](#runtime-and-portability)
  - [Shared learning-unit contract](#shared-learning-unit-contract)
- [PDF Import](#pdf-import)
- [Faithful Ingest](#faithful-ingest)
- [Course-linked Enrich](#course-linked-enrich)
- [Offline HTML Generate](#offline-html-generate)
- [Development](#development)

## Runtime and portability

Each directory under `.agents/skills/` is a portable skill artifact containing
complete operating instructions, executable assets, direct dependency
declarations, configuration guidance, workflow evaluations, licenses, and
provenance as applicable. Executable script tests and fixtures stay in the
repository's `tests/` suites; they are not required to operate a copied skill.

Clew hosts those independent skill projects in one UV workspace so development
uses a shared lockfile and virtual environment. A copied skill can still resolve
and install its declared dependencies as its own UV project. External services,
platform capabilities, host integrations, and dependencies on other skills must
be explicit.

Import also participates in an **npm workspace**. The root
[`package.json`](../package.json) names `.agents/skills/clew-import`; that
skill's own [Node manifest](../.agents/skills/clew-import/package.json) declares
its exact MathJax dependency. The root `package-lock.json` owns combined
resolution, and `.npmrc` selects npm's hoisted install strategy. Install once
from the repository root, with Node.js >=22 and npm >=10 available on PATH:

```powershell
npm ci --ignore-scripts --no-audit --no-fund
```

Do not install separately inside a workspace member. The current locked tree
has only root-hoisted dependencies; npm can nest incompatible versions, unlike
UV's single-environment conflict behavior. Dependency changes must explicitly
reconcile conflicts rather than promise unconditional hoisting. Node is a host
runtime, not a binary stored in the repository. A standalone copied Import
skill uses its own `package.json`: initially approve `npm install
--ignore-scripts --no-audit --no-fund`, then `npm ci --ignore-scripts --no-audit
--no-fund` with that host's lock. Other skills need no Node runtime.

All four skills require Python >=3.11 and [UV](https://docs.astral.sh/uv/).
From the repository root, install the shared environment as a separate setup
step, following the host's approval rules:

```powershell
uv sync --all-packages --locked
```

Routine inspection uses `--no-sync` to avoid installing dependencies. For a
standalone copied skill, run `uv sync` in its own directory initially, then
`uv sync --locked` subsequently. Omit `--package <skill-name>` and replace the
repository script path with its local `scripts` path. PowerShell examples below
run from the Clew repository root; adapt quoting and separators on other hosts.

Only Import requires Azure configuration and sends source content to cloud
services. Ingest, Enrich, and Generate use local tools; the host agent's own
handling of note content still follows that host's data policies. No Obsidian
installation or plugin is required. OneDrive folders and Files On-Demand are
supported: reading online-only files can download their contents, access or
hydration failures are reported rather than silently skipped, and symlinks and
junctions are refused.

PDF Import, faithful Ingest, course-linked hints and correction explanations,
and HTML Generate are implemented. Non-PDF sources and broader enrichment
remain future work.

Architecture decisions are indexed in [the ADR index](adr/README.md).
[ADR-0003](adr/0003-autonomous-portable-skills.md) defines runtime portability
and documentation integrity;
[ADR-0004](adr/0004-faithful-multi-bundle-ingest.md) defines repository-owned
script tests. The linked `SKILL.md` files are the complete portable operating
instructions, not wrappers that depend on this reference.

### Shared learning-unit contract

Ingest creates **one note per exercise and supplied correction unit**, not per
sheet or question. Shared context and all subquestions/answers stay in that unit;
stable internal anchors provide finer addresses. Course notes cover coherent
subtopics rather than arbitrary page counts or heading levels.

Enrich preserves those units and adds auxiliary question-scoped help notes.
Generate groups selected questions by their owning exercise and derives finer
HTML views from the internal structure, without changing source notes or needing
producer records. This works before optional enrichment. Matching uses source
content and evidence, not printed numbers alone. See
[ADR-0008](adr/0008-exercise-unit-pipeline-contract.md).
Historical record handling is deferred; this contract does not rule out future
compatibility or migration work.

## PDF Import

The local [clew-import skill](../.agents/skills/clew-import/SKILL.md) accepts a PDF
or a directory, recursively identifies what needs conversion, and proposes exact
commands before execution. `chapter_1.pdf` defaults to a sibling `chapter_1`
bundle. Completed imports are checked by source hash, artifacts, and page scope;
existing conflicts require a decision rather than automatic replacement.

OneDrive folders and Files On-Demand are supported as described in
[Runtime and portability](#runtime-and-portability). Retry cleanup still needs
explicit approval: deletion in a shared synchronized folder can propagate to
collaborators and other devices.

The skill uses its bundled PDF converter and declares its dependencies in
[its own UV project](../.agents/skills/clew-import/pyproject.toml). Configure a
root `.env` using the skill's
[`.env.example`](../.agents/skills/clew-import/.env.example) as guidance, with real
Azure endpoints and a vision/structured-output deployment. Authentication uses
Entra ID through `DefaultAzureCredential`, not API keys. Do not commit `.env`.

From the repository root, a direct conversion looks like:

```powershell
uv run --package clew-import --locked --env-file .env python ".agents\skills\clew-import\scripts\digest_pdf.py" "C:\courses\chapter_1.pdf" --output "C:\courses\chapter_1"
```

This sends document content to configured Azure services and may incur charges.
Page judging is enabled by default: each page uses one transcription and one
fresh review request to the same configured deployment, with up to two
corrective transcription/review pairs (2-6 logical OpenAI page requests).
Figure classifications and SDK transport retries are additional. The plan
discloses those bounds before conversion approval. Add `--no-page-review` to
both planner and converter only when opting out; this keeps one transcription
request per page with local checks but no LLM review or corrective attempts.
The output must not already exist. A bundle includes the original PDF in
`source`, Markdown, figures, raw extraction evidence, a manifest, and diagnostics.
Exit `2` means completed but needs review; `1` means failed and `130` interrupted.
The skill asks before deleting a verified failed output and retrying.

On Windows, replacing progress diagnostics (`run.json.tmp` -> `run.json`)
retries access-denied/sharing/lock errors (WinError 5, 32, 33) with five logged
backoff waits: 0.1, 0.2, 0.4, 0.8, and 1.6 seconds. Each save makes at most six
replacement attempts with 3.1 seconds of total waiting, preserving atomic
replacement. Other errors, temporary-file writes, and exhausted retries still
fail explicitly. This handles brief OneDrive/scanner/reader contention without
repeating cloud requests or restarting the import; it does not bypass
permissions or guarantee recovery from persistent locks.

The page prompt asks for minimal, image-evidenced corrections, not proofreading
or cosmetic rewriting. Pages return Markdown directly, without a JSON envelope
or self-reported fixes/confidence list. This removes the inner JSON escaping
layer around TeX, not the possibility of transcription errors. Unreadable
content is marked in place; pages without substantive content return
`<!-- Blank page. -->`. Empty or whitespace-only output, incomplete responses,
and refusals without extraction are failures. Figure classifications and the
separate page judge use strict JSON with schema and semantic validation, so
the deployment must support structured output.

The judge compares the whole candidate page with the original image, using
original OCR/formulas as hints. It reports location, discrepancy, visible source
evidence, and a minimal correction instruction, categorized as transcription,
format, or uncertainty. It must preserve author mistakes and never solve,
proofread, or normalize source content. The corrective transcriber receives
the prior candidate and feedback but must verify proposed changes against the
image; it returns a complete plain Markdown page. Each revision is judged in
a fresh request without earlier review feedback, to detect new regressions.
Uncertainty-only findings with no renderer errors stop without guessed
corrections. After at most two corrective attempts, unresolved findings are
published as `needs_review`, not
hidden or retried indefinitely. Empty/malformed/incomplete judge or corrective
responses fail explicitly. These in-run attempts are distinct from the
separately approved delete-and-restart gate for a failed whole import. Executed
MathJax errors also trigger corrections within that same budget, even if the
judge reports no findings.

Raw `*.response.json` artifacts still retain complete API responses before
checks. Their page response text is Markdown directly; figure and judge response
text is JSON. Every reviewed candidate has exact Markdown and full API evidence:
`raw/pages/page-NNNN.attempt-AA.md`, `.attempt-AA.response.json`, and
`.attempt-AA.review.response.json`. The existing `page-NNNN.response.json`
contains the selected final transcription on completion. Manifest schema 3
adds configuration `page_review`/`max_page_retries` and per-page `review`
status/attempts, including artifact references, findings, and local format
issues. The planner checks these additional references when present.
Selected page Markdown is unchanged, including backslashes and whitespace,
with only page markers and inter-page separators added during assembly.
Existing completed bundles remain valid and are not rescanned or modified;
canonical artifact references, manifest schema, and exit meanings stay supported.

A non-mutating check flags known LaTeX commands leaked
into ordinary Markdown as `needs_review`, with page and block-line evidence.
Another local check flags Unicode `Cc` controls except newline, carriage return,
and tab, with page/line/code-point evidence. These checks preserve candidate
text and raw responses, and supply findings to the judge rather than applying
string repairs. Remaining local findings require review even if the judge
reports no discrepancy.

**Every candidate is also checked by an executed offline MathJax renderer**,
including with `--no-page-review`. A local Node helper uses `liteAdaptor` and
in-memory SVG—no browser, network, SVG files, or screenshots. It pins MathJax
3.2.2 to match Generate's bundled version and uses the same selected
base/ams/newcommand/configmacros packages and llbracket/rrbracket macros,
without a runtime dependency on Generate or autoloaded extensions. It rejects
active/external commands and unexpected controls before TeX conversion.
Markdown extraction mirrors publication's CommonMark/tables/dollar-math
configuration, excluding code, image alt text, and destinations; reports retain
formula IDs, exact TeX, display mode, and page-local block lines. Prior selected
page expressions are replayed to preserve macro context, but earlier rejected
candidates cannot pollute a new check.

The checker captures TeX errors and error nodes, not just process exit status.
Its reports are retained as `raw/pages/page-NNNN.math.json` for the final
candidate and `.attempt-AA.math.json` for reviewed attempts; `raw_math`
references and `configuration.mathjax_version` extend manifest schema 3.
Missing/unusable Node or MathJax blocks conversion before cloud work; timeout
(60 seconds per batch), malformed protocol, and unexpected engine failures
remain explicit import failures. Normal formula errors feed the judge and
corrective transcriber and remain `needs_review` if unresolved. The read-only
planner runs a local smoke test and reports Node setup commands without
installing packages. Historical completed bundles need no new evidence.

Neither renderer checks nor the same-model judge prove source fidelity,
mathematical correctness, extraction completeness, resolved references, or
final layout. A wrong inequality can render successfully, and unrecognized or
missing math delimiters can escape formula extraction. See the skill
instructions for the complete contract and exclusions.

For read-only inspection with the environment already installed:

```powershell
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\plan_imports.py" "C:\courses"
```

Add `--env-file .env` before `python` and `--check-env` after the input to check
the effective configuration without dumping its values. Plans show only resource
hosts and a configuration fingerprint for approval and change detection.
Inspection never converts or cleans up outputs. Plans use PowerShell quoting
and include argument arrays for other shells, `page_review` settings, and
per-eligible-document `page_model_requests` bounds. Existing completed bundles
are skipped even if their historical imports did not use the judge.

## Faithful Ingest

The [clew-ingest skill](../.agents/skills/clew-ingest/SKILL.md) consumes one or
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
[documented format](../.agents/skills/clew-ingest/references/formats.md).
Check that plan without creating its destination:

```powershell
uv run --package clew-ingest --locked --no-sync python -B ".agents\skills\clew-ingest\scripts\write_ingest.py" "C:\plans\ingest.json" --check
```

Review the confirmed placement, any parent directories to create, boundaries,
matches, evidence, exact output paths, and issues.
Inspection exposes a parser-backed outline of headings, numbered peers, and
ordered items. Normal checks block whole-sheet aggregation, question/answer
files, and missing structural parts. The `structure` report shows unit ownership,
block counts/addresses, evidence, and exact scoped review reasons for course
grouping or ambiguous candidates; these are not automatic semantic decisions.
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

## Course-linked Enrich

The [clew-enrich skill](../.agents/skills/clew-enrich/SKILL.md) adds individual-question
hints and explanations of **supplied** corrections to a selected current
chapter. The agent authors the additions using ordinary file-editing tools;
Python checks their structure and source preservation, not their pedagogical
correctness. No embedded model, cloud service, or enrichment writer is needed.

Ordinary numbered questions and answers receive structural callouts and stable
anchors without rewriting the supplied text. Separate `aides/` notes use the
[small note contract](../.agents/skills/clew-enrich/references/formats.md): question
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
Correction associations and all answer links must agree on one owning exercise,
even when another exercise has the same local question anchor.
Courses, sources, index, ingest record, and existing aid files must stay unchanged;
only new Markdown aid notes/directories under `aides/` are allowed.
Failures identify the cause and never repair notes or recapture the baseline.
The baseline contains local source text: do not commit or publish it.

This is an additive first increment, not a revision-history or approval-hash
framework. Ingest's exact-snapshot validator remains unchanged and will report
the later structural edits/new aids as changes. Current-note Generate deliberately
does not call that validator. See [ADR-0007](adr/0007-course-linked-question-enrichment.md).

The [small English synthetic chapter](../tests/clew_enrich/fixtures/chapter) and
[enriched overlay](../tests/clew_enrich/fixtures/enriched) contain one short course,
two exercise notes/four questions, two correction-unit notes/three supplied
answers, six hints, and three
explanations. They illustrate current-note topology, not a complete retained
Import/Ingest archive. No private teaching material is included.

## Offline HTML Generate

The [clew-generate skill](../.agents/skills/clew-generate/SKILL.md) publishes current
selected course, exercise, correction, and optional aid notes as one offline
interactive HTML file. The agent chooses scope/order and unresolved mappings in
a small [JSON layout](../.agents/skills/clew-generate/references/formats.md);
deterministic Python reads the current notes and renders them. Human edits are
accepted. No Ingest validation, approval hashes, run ledger, Obsidian plugin,
server, embedded model, or Azure call is required.

Supply a chapter folder or its Ingest `index.md` rather than listing note files.
Generate discovers the `courses/`, `exercices/`, and `corriges/` topology,
optional aids, and existing metadata/relationships automatically. When only a
vault/container and course name are known, `inspect_notes.py --list-chapters`
lists chapter titles for the skill to select. Retained `sources/` documents and
hidden configuration are excluded; arbitrary explicit notes remain supported.
Selections from one exercise remain one owning exercise view, with internal
questions and selected context in source order. Aliased/overlapping selections
are rejected. Supplied-answer panels keep their correction-unit context without
adding unselected answers; Generate never splits source notes.

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
requested with `--overwrite`. Source notes are never changed.

## Development

```powershell
uv sync --all-packages --locked
uv run --package clew-import --locked --no-sync python -B -m unittest discover -s "tests\clew_import"
uv run --package clew-ingest --locked --no-sync python -B -m unittest discover -s "tests\clew_ingest"
uv run --package clew-enrich --locked --no-sync python -B -m unittest discover -s "tests\clew_enrich"
uv run --package clew-generate --locked --no-sync python -B -m unittest discover -s "tests\clew_generate"
npm run test:mathjax
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
The synthetic `tests/clew_ingest/test_pipeline.py` verifies isolated-process
Ingest, Enrich, and Generate handoffs, including native internal structure before
optional aids and current-note publication without a producer record.

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
