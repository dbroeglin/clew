# Clew

Clew turns course PDFs into editable, source-preserving Obsidian documents.
**`clew-import` is one skill with two resumable steps:** convert PDFs, then
prepare each complete Markdown document with stable anchors, callouts, and
links to the original PDF pages. It does not split a course or exercise sheet
into many notes or rewrite supplied text to add structure.

## Get started

Skills live in `.agents/skills/`. Open this repository in an agent that loads
that directory, or copy a skill into your agent's supported skill folder.
Each skill contains its runtime instructions and dependencies. Invocation
syntax varies by agent; the examples below name the skill explicitly.

Python >=3.11 and [UV](https://docs.astral.sh/uv/) are required. Install the
shared environment once from the repository root:

```powershell
uv sync --all-packages --locked
```

PDF conversion additionally needs Azure Document Intelligence, a vision/
structured-output Azure OpenAI or Foundry deployment, and Entra ID
authentication. Use the skill's
[`.env.example`](.agents/skills/clew-import/.env.example) for an untracked
execution-root `.env`; API keys are not used.
Offline conversion formula checking needs Node.js >=22 and npm >=10:

```powershell
npm ci --ignore-scripts --no-audit --no-fund
```

Local preparation and validation need no Azure configuration, Obsidian
installation, plugin, or Node process. See the
[skills reference](docs/skills.md) for full setup and standalone use.

## 1. Convert your PDFs

For a folder containing `cours.pdf`, `exercices.pdf`, and `corriges.pdf`:

```text
Use clew-import to inspect C:\courses\algebre and plan conversion of the PDFs
that still need it.
```

Review selected PDFs, outputs, options, and conflicts.
**Conversion sends document content to your configured Azure services and can
incur charges**, so it requires explicit approval. Existing completed bundles
are reused, not silently reconverted.

The converter retains the original PDF, Markdown, figures, and diagnostics.
It checks formula rendering locally, reviews pages against their source, and
can make bounded corrective transcription attempts within the approved run.
Unresolved findings remain visible; source mistakes are not proofread away.
At completion it reports returned model-token usage and a clearly labeled
reference price estimate; this is not the final Azure charge.
Completed bundles normally sit beside their PDFs in same-basename folders.
You can stop here and prepare them later.

## 2. Prepare whole documents for Obsidian

```text
Use clew-import to prepare C:\courses\algebre\cours,
C:\courses\algebre\exercices, and C:\courses\algebre\corriges in C:\vault.
Keep each whole document, add stable course/exercise/question/answer anchors,
and propose source-evidenced correction links.
```

The agent reads the material and your vault's conventions, then previews the
exact placement, operations, links, warnings, and files in one approval.
Python applies narrowly defined structural edits to the original source;
the agent does not regenerate the Markdown.

Each PDF gets one folder with its complete editable note, PDF, and figures.
Recognized roles use `Course-<basename>`, `Exercise-<basename>`, and
`Correction-<basename>`; unknown or mixed documents keep their PDF basename.
A chapter index provides navigation. Private retained Markdown baselines allow
exact source-preservation checks without the external conversion folders.
New output never merges with or overwrites an existing chapter.

Sections remain navigable, important course statements become anchored
callouts, and questions/answers have explicit internal ownership. Corrections
reference verified question targets. Exercise and statement links sit in
unobtrusive footers. Uncertain matches stay unlinked with **warning callouts
in an end-of-document review appendix**, not only in a report.
Missing exercises or supplied corrections are valid; nothing is invented.
Relative Markdown links keep the complete chapter movable as one folder.

## Validate and edit

Preparation checks source preservation and current structure/links before
marking the output complete. After editing in Obsidian:

```text
Use clew-import to validate C:\vault\Maths\algebre without changing the notes.
```

The validator checks anchors, unit ownership, local note/figure links, and PDF
pages. Default checks accept handwritten content changes; a separate fidelity
check reports differences from the initial prepared snapshot.
External URLs are not fetched or claimed working. Mechanical checks do not
prove semantic matches, theorem boundaries, or mathematical correctness.

## Enrichment and publication

`clew-enrich` adds question-specific hints and supplied-answer explanations.
`clew-generate` publishes current notes as an offline interactive HTML file.
**Those skills currently support the legacy exercise-per-note layout, not the
new whole-document output.** Their document-internal-unit refactors are deferred.
Existing legacy note archives remain supported and are not migrated.

PDF is the only implemented conversion input. TeX, Word, PowerPoint, generated
exercises/answers, general OCR repair, and broader enrichment are outside this
workflow.

- [Skills reference](docs/skills.md): setup, artifact contracts, commands,
  limitations, validation, and development checks.
- [Architecture decisions](docs/adr/README.md): the current design.
- [Contributor and agent guidance](AGENTS.md): portability and documentation
  requirements.
