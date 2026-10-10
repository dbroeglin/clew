# Skills reference

The [README](../README.md) describes end-user skill calls. This reference covers
runtime setup, artifact contracts, direct commands, limits, and development.
Portable skill instructions remain complete without this reference.

## Runtime and portability

Each `.agents/skills/` directory owns its instructions, scripts, dependencies,
configuration templates, evals, licenses and provenance. Executable tests and
fixtures live in repository-owned `tests/<skill_name>/`, never inside skills.
Clew hosts three skills: Import, Enrich, and Generate.

Python >=3.11 and UV are required. From the repository root:

```powershell
uv sync --all-packages --locked
```

Routine read-only commands use `--no-sync` so they cannot install dependencies.
A copied standalone skill initially uses `uv sync`, subsequently
`uv sync --locked`; omit `--package` and use its local `scripts` paths.
The host owns locks/environments; skills own dependency declarations.

Conversion also requires Node.js >=22 and npm >=10 on PATH. Import declares
`mathjax-full` 3.2.2 in its own `package.json`; the root npm workspace owns
`package-lock.json` and hoisted `node_modules`:

```powershell
npm ci --ignore-scripts --no-audit --no-fund
```

Do not install separately in workspace members, use `npx`, or install globally
during a run. Standalone Import initially uses `npm install --ignore-scripts
--no-audit --no-fund`, then `npm ci` with that host's lock. Incompatible
dependencies can cause npm nesting; verify hoisting after dependency changes.

Only conversion needs Azure configuration. Local preparation/validation,
Enrich and Generate need no Azure credentials, Obsidian installation, plugin,
or Node process. The host agent's handling of content follows its data policies.
OneDrive non-redirecting placeholders are supported; reads may hydrate them.
Access/hydration errors are reported. Symlinks, junctions, redirected paths and
reparse points with unknown tags are refused.

## PDF Import

[`clew-import`](../.agents/skills/clew-import/SKILL.md) contains **two resumable
steps**, not two runtime skills. Conversion-only requests stop after step A;
step B accepts explicitly selected completed bundles without reconversion.

Use the skill's [`.env.example`](../.agents/skills/clew-import/.env.example)
for the execution root's untracked `.env`. Configuration requires non-placeholder
`AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, and exactly
one of `AZURE_AI_PROJECT_ENDPOINT`/`AZURE_OPENAI_BASE_URL`.
Entra ID authentication uses `DefaultAzureCredential`, not API keys.
Never dump configuration, log in automatically, switch accounts, or provision
resources as an import fix.

```powershell
uv run --package clew-import --locked --no-sync --env-file .env python -B ".agents\skills\clew-import\scripts\plan_imports.py" "C:\courses" --check-env
uv run --package clew-import --locked --env-file .env python ".agents\skills\clew-import\scripts\digest_pdf.py" "C:\courses\chapter.pdf" --output "C:\courses\chapter"
```

Discovery is recursive and deterministic, excluding recognized conversion,
prepared, and legacy ingest roots and their retained PDFs. Ambiguous metadata
is a conflict, not hidden content. Matching complete bundles are skipped for
conversion; stale, partial, malformed or unrelated targets are blocked.
All pages are requested by default; selected-page imports are not full imports.

Conversion requires approval of exact PDFs, resource hosts, options, commands,
and possible charges. It sends PDFs, page images and extracted text to configured
Azure services. Setup and failure cleanup need their own scoped approvals.
Existing outputs are never automatically overwritten or reused.

### Conversion and evidence

The converter uses Document Intelligence and vision reconciliation. Page
responses are direct Markdown, without an inner JSON envelope or self-reported
fixes/confidence. Structured JSON remains for figure classification and judging.
Original wording, notation and author mistakes are preserved; unreadable content
is marked honestly. Blank pages use `<!-- Blank page. -->`; empty output fails.

Pages render at 200 DPI and use image `detail: high`; there is no documented
model-independent optimal DPI. Image resizing/token accounting varies by model
and detail setting, so 200 DPI remains a practical default rather than a
guaranteed optimum. Document Intelligence's paid `ocrHighResolution` add-on is a
separate feature for small text in large/dense documents. For GPT-6.1-Sol, page
transcription and review use high reasoning effort; figure classification keeps
the deployment default. Recheck supported effort values when changing models.

Default fresh source-grounded page judging uses the same deployment. Each page
has initial transcription/judge calls and at most two corrective pairs:
2-6 logical OpenAI page requests, plus figures and SDK transport retries.
`--no-page-review` explicitly disables judging/corrective calls, not local checks.
Corrective attempts are part of the approved bounded conversion, not permission
to restart or delete a failed output.

At completion, the CLI and schema-3 manifest report Responses API token usage and
an explicitly labeled GPT-6.1-Sol OpenAI standard list-price estimate, based on
returned usage (including cached input when reported). This is not an Azure
invoice; cache-write premiums and SDK retries may be absent. Document
Intelligence processed-page count and high-resolution OCR use are reported
separately, without a dollar estimate because Azure rates vary by region and
contract. Missing per-response usage makes the OpenAI estimate incomplete,
never zero; a response model that does not match GPT-6.1-Sol also suppresses the
estimate, as does a response that omits its model. See the
[OpenAI GPT-6.1-Sol pricing](https://developers.openai.com/api/docs/models/gpt-6.1-sol)
and [image-cost calculator](https://developers.openai.com/api/docs/guides/image-cost-calculator),
plus the [reasoning-effort guide](https://developers.openai.com/api/docs/guides/reasoning).

Non-mutating LaTeX-leakage and unexpected-control checks complement offline
MathJax 3.2.2 TeX/SVG checking. MathJax uses base/ams/newcommand/configmacros and
the configured llbracket/rrbracket macros, without browser/network or autoload.
Only parsed dollar math is checked; code, image alt text and destinations are
excluded. Selected previous-page math supplies macro context; discarded drafts
cannot contaminate later candidates. Renderer errors feed the same two-attempt
budget and cannot be cleared by a judge pass. Node/runtime, timeout (60 seconds),
protocol or engine failures are explicit conversion failures.

Schema-3 bundles contain `document.md`, `source/<original-filename>.pdf`,
referenced `figures/`, complete `raw/` evidence, `manifest.json` and `run.json`.
PDF copies are byte-identical, including the complete PDF for selected pages.
Raw page/candidate/judge/math reports retain source evidence; additive review/
math metadata does not invalidate older complete bundles.
Neither parsing, judging nor rendering proves faithful mathematics.

Converter exits: 0 extracted, 2 complete with review findings, 1 failed,
130 interrupted. Planner exits: 0 unblocked plan, 2 conflicts/preflight blockers,
1 inspection error. Check manifests and persisted artifacts, not exits alone.
On failure preserve output and pause; deleting a verified exact failed root and
retrying requires separate approval, including synchronized-deletion consequences.
Diagnostic replacement alone has bounded Windows lock backoff (five waits:
0.1, 0.2, 0.4, 0.8, 1.6 seconds); it does not repeat cloud calls.

## Whole-document preparation

Read the portable [contract](../.agents/skills/clew-import/references/preparation.md)
and [example](../.agents/skills/clew-import/references/example.md).

```powershell
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\inspect_bundles.py" "C:\courses\course" "C:\courses\sheet" "C:\courses\answers"
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\inspect_vault.py" "C:\vault"
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\prepare_documents.py" "C:\plans\preparation.json" --check
uv run --package clew-import --locked --no-sync python ".agents\skills\clew-import\scripts\prepare_documents.py" "C:\plans\preparation.json" --plan-sha256 "<approved hash>"
```

The agent reads complete documents, chooses vault placement from existing
conventions, classifies roles, selects safe source blocks, and matches supplied
answers using evidence. Python applies a closed structural operation set:
unit boundaries/entries, callout wrapping, anchor insertion and heading-level
changes. No generic text replacement, OCR repair, whole-tree reserialization,
source splitting, content generation or inferred prerequisites.

One concrete local approval includes placement, exact missing parent creation,
folder names, operations, diffs, matches/evidence, copied files and warnings.
Conversion approval is separate. Changed sources/plans invalidate approval.
Only a new chapter root is allowed; no merge/overwrite/update or automatic
cleanup/retry. Failed roots remain incomplete.
Prepared ownership is identified by `.clew/preparation.json` or partial
`.clew/baselines/`, not an unrelated vault-level `.clew/imports.json` inventory.

```text
<chapter>\
  index.md
  Course-<basename>\<basename>.md, <basename>.pdf, figures\
  Exercise-<basename>\<basename>.md, <basename>.pdf, figures\
  Correction-<basename>\<basename>.md, <basename>.pdf, figures\
  <unknown-or-mixed-basename>\<basename>.md, <basename>.pdf, figures\
  .clew\preparation.json
  .clew\baselines\<document-id>\document.md
```

There is one complete editable note per PDF. Baselines/PDFs/figures are retained
locally; external conversion diagnostics remain untouched. This subset is not
a complete conversion bundle. Explicit folder overrides resolve collisions;
no silent suffixing. All chapter-owned files share one root.

Persistent exercise/correction entry anchors differ from temporary
fingerprint-bound `b-N` source selectors. Sections use genuine heading links,
not generated block IDs; their scope IDs are private bookkeeping. Heading
renames/duplicates can break title-based links. Block IDs target exact
entries/statements, not every following block. Top-level question/answer
callouts have unique enclosing owner scopes and
verified target links; native Obsidian cannot address callout/quote/table
interiors. IDs are stable, unique locally, and independent of line/title hashes.
Relative Markdown links keep the whole chapter movable.
PDF provenance uses a single compact `PDF p. N` starting-page link at each
section entry and on the final line of each exercise/correction unit and learning
callout, after its generated relationship links. A callout puts any verified
`[Question](...)` answer relationship and its PDF link on one final quoted line,
separated by ` · `, with the PDF link last. Keep one blank quoted line between
callout content and links; collapse only duplicate blank quote lines at that
terminal boundary, preserve body-internal spacing, and add no quoted blank lines
after the footer. Unit entry anchors remain at the beginning for exercises/
corrections. Relationships use plain `[Exercise](...)` correction-to-exercise
and `[Question](...)` answer-to-question links without repeated prefixes or
metadata wrappers. Validation checks labels, destination kinds and ownership;
no plugin is required.
Questions have only a PDF footer; redundant links back to their parent exercise
or correction are omitted.
Page-break links and covered-page lists are omitted. Generated bookkeeping
uses Obsidian `%%` comments. Only this generated format is supported; existing
prepared notes are not automatically migrated.

Unmatched corrections/answers remain unlinked. Suspicious valid structure and
conversion issues appear as generated warning callouts in an end appendix of
each affected note, with anchor/source-line locations, and after index navigation.
Hard errors (broken links, invalid anchors/owners, unsafe boundaries)
cannot be waived by review reasons.

### Pedantic validation

```powershell
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\validate_documents.py" "C:\vault\Maths\chapter"
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\validate_documents.py" "C:\vault\Maths\chapter" --fidelity
```

Default checks accept manual content changes while checking current schema,
anchor attachment/uniqueness, unit scope/ownership, reference syntax, note/
figure existence, fragments and actual original PDF page bounds. Retained
baselines/PDFs/figures remain immutable. Documents are located by persistent ID,
so a deliberate folder rename works after relative links are updated.

Initial preparation additionally requires exact source projection: independently
reverse only recorded structural changes and recover the original bytes/text,
without whitespace normalization. Math/code/table structure is checked too.
`--fidelity` deliberately detects subsequent snapshot changes; it never
recaptures baselines or restores user notes.

Validation aggregates codes, error/review severity, paths, one-based locations,
anchors/targets and diagnostics. It is offline and read-only. External URLs are
reported as not remotely verified, not fetched or claimed working. Unsupported
HTML resource links/local fragments, paths escaping the chapter and redirects
are explicit errors. Parser passes do not establish semantic matching or visual
layout. Local helpers exit 0 clean, 2 review-only, 1 errors. Completion requires
a version-1 `.clew/preparation.json` with `status: complete`.

## Course-linked Enrich

[`clew-enrich`](../.agents/skills/clew-enrich/SKILL.md) remains implemented for
the **legacy exercise-per-note layout**, not new whole-document chapters.
Its document-unit refactor is deferred; existing archives are not migrated.

It adds question-specific hints and supplied-answer explanations as separate
`aides/` notes, preserving source units, existing anchors and aids. Missing
answers are not invented. The agent authors approved additions; a local
baseline validator checks preservation and precise course links.
See its [format](../.agents/skills/clew-enrich/references/formats.md).

```powershell
uv run --package clew-enrich --locked --no-sync python -B ".agents\skills\clew-enrich\scripts\validate_enrich.py" "C:\vault\legacy-chapter" --capture "C:\scratch\before.json"
uv run --package clew-enrich --locked --no-sync python -B ".agents\skills\clew-enrich\scripts\validate_enrich.py" "C:\vault\legacy-chapter" --before "C:\scratch\before.json"
```

Baselines belong outside the chapter/repository, not in published content.
Courses, retained sources, indexes, existing aids and frontmatter stay unchanged.
No missing-answer generation, broader learning enrichment or revision framework.

## Offline HTML Generate

[`clew-generate`](../.agents/skills/clew-generate/SKILL.md) likewise remains a
legacy-note consumer. It does not yet publish new `type: document` chapters.
Existing course/exercise/correction/help notes can still be published without
Import, a producer record or snapshot validation.

```powershell
uv run --package clew-generate --locked --no-sync python -B ".agents\skills\clew-generate\scripts\inspect_notes.py" "C:\vault" --list-chapters
uv run --package clew-generate --locked --no-sync python -B ".agents\skills\clew-generate\scripts\generate_html.py" "C:\plans\layout.json" --check
uv run --package clew-generate --locked --no-sync python ".agents\skills\clew-generate\scripts\generate_html.py" "C:\plans\layout.json"
```

Legacy topology uses `courses/`, `exercices/`, `corriges/`, optional `aides/`.
One exercise note owns all its questions; supplied correction units stay intact.
Python renders current Markdown and embeds figures, fixed HTML-first templates,
CSS, interaction code and pinned offline MathJax. No runtime CDN/server or
source-note changes. Hints/explanations/course excerpts use contextual panels;
supplied corrections stay inline. Missing controls are omitted, not fabricated.
PDF references remain external and can break if HTML moves.
Output parent must exist; existing HTML requires explicit exact-file replacement.
See the [layout contract](../.agents/skills/clew-generate/references/formats.md)
for raw HTML, transclusion, remote-resource and dynamic-math limitations.

## Development

```powershell
uv sync --all-packages --locked
npm ci --ignore-scripts --no-audit --no-fund
uv run --package clew-import --locked --no-sync python -B -m unittest discover -s "tests\clew_import"
uv run --package clew-enrich --locked --no-sync python -B -m unittest discover -s "tests\clew_enrich"
uv run --package clew-generate --locked --no-sync python -B -m unittest discover -s "tests\clew_generate"
npm run test:mathjax
```

Tests use independently authored synthetic material and mocked/local transports,
not real cloud calls or user archives. Import tests cover both steps, negative
structure/link diagnostics, source preservation, warnings, lifecycle, relocation
and standalone runtime. Enrich/Generate dedicated suites preserve legacy behavior;
there is no claim of new-format pipeline compatibility.
Standalone fixtures use temporary local wheels from installed locked
distributions via `tests/runtime_fixtures.py`, outside the copied skill.

Optional Generate browser checks use installed Edge and block HTTP(S):

```powershell
$env:CLEW_TEST_BROWSER = "1"
uv run --package clew-generate --locked --no-sync python -B -m unittest discover -s "tests\clew_generate"
Remove-Item Env:\CLEW_TEST_BROWSER
```

Architecture records are indexed in [docs/adr](adr/README.md). Runtime rules
must still be stated completely inside portable skills.
