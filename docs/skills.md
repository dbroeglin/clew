# Skills reference

The [README](../README.md) describes end-user skill calls. This reference covers
runtime setup, artifact contracts, direct commands, limits, and development.
Portable skill instructions remain complete without this reference.

## Runtime and portability

Each `.agents/skills/` directory owns its instructions, scripts, dependencies,
configuration templates, evals, licenses and provenance. Executable tests and
fixtures live in repository-owned `tests/<skill_name>/`, never inside skills.
Clew hosts four skills: Import, Enrich, Generate, and Export.

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
Enrich, Generate, Export and installing a published chapter need no Azure
credentials, Obsidian installation, plugin, or Node process. Export and
installation also need `git` on PATH with the user's own remote access.
The host agent's handling of content follows its data policies.
OneDrive non-redirecting placeholders are supported; reads may hydrate them.
Access/hydration errors are reported. Symlinks, junctions, redirected paths and
reparse points with unknown tags are refused.

## PDF Import

[`clew-import`](../.agents/skills/clew-import/SKILL.md) contains **two resumable
steps**, not two runtime skills. Conversion-only requests stop after step A;
step B accepts explicitly selected completed bundles without reconversion.
Step C installs a chapter published with Export; see
[Git sharing](#git-sharing-export-and-install).

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
conversion; stale, partial, malformed or unrelated targets are blocked by
default. Explicit resume planning can reuse compatible checkpoint-enabled
partial targets; older partial outputs are not migrated.
All pages are requested by default; selected-page imports are not full imports.

Conversion requires approval of exact PDFs, resource hosts, options, commands,
and possible charges. It sends PDFs, page images and extracted text to configured
Azure services. Setup and failure cleanup need their own scoped approvals.
Existing outputs are never automatically overwritten or resumed.

### Resuming a conversion

New conversions checkpoint paid work automatically; resume is explicit:

```powershell
uv run --package clew-import --locked --no-sync --env-file .env python -B ".agents\skills\clew-import\scripts\plan_imports.py" "C:\courses\chapter.pdf" --resume --check-env
uv run --package clew-import --locked --no-sync --env-file .env python ".agents\skills\clew-import\scripts\digest_pdf.py" "C:\courses\chapter.pdf" --output "C:\courses\chapter" --resume --checkpoint-sha256 "<approved checkpoint SHA-256>"
```

Repeat all original non-default conversion flags. The planner's `--output`
supports a custom destination for one explicitly selected PDF. `--resume` plans
existing digestions only; completed matches remain `already_converted`.
It reports cached/failed/uncertain calls, the DI recovery action, conservative
remaining page-request bounds, and the fingerprint bound into its command.
Resume needs fresh scoped cloud approval, not deletion approval; source,
configuration and checkpoint are rechecked before execution.

`checkpoint.json` schema 1 binds source hash/name/page count, normalized selected
pages, conversion options, effective Azure configuration fingerprint and
converter/Python interpreter/dependency fingerprint. It checks every committed artifact,
rejects unexpected files and redirects, stages local writes before atomic
replacement, and records DI operation identity and paid-call state. Complete
OpenAI responses are also retained in immutable numbered
`raw/checkpoints/response-NNNNNN.json` files. Conventional artifact paths and the
schema-3 completion manifest remain supported.

Valid cached responses reconstruct figures, candidates, judgments and the
original two-correction budget without new calls; local checks replay selected
prior-page math to restore macro context. Saved DI layout/crops are reused;
an operation with a saved ID can be polled without resubmitting. An attempted
submission without a saved ID/result is blocked, and an unavailable/expired DI
operation fails rather than silently submitting again. Invalid model responses
stay failed in the original invocation; a separately approved resume can retry
the failed logical step while retaining all prior returned evidence.

An interrupted OpenAI request without a committed response may have been billed
and may repeat. Usage reconstructs returned prior/new responses once, including
rejected responses; unobserved attempts make the reference estimate unavailable.
A completed checkpoint is a verified no-op, not a way to remove review findings.
Missing checkpoints, changed sources/settings/artifacts/runtime, and conflicting
processes block resume. Keep the original runtime until its runs finish; there
is no legacy adoption or silent configuration migration. The fingerprint cannot
detect a provider changing the model behind an unchanged deployment name.

The OS advisory `.digest.lock` is retained and released by process exit/crash.
It protects cooperating processes on the same filesystem, not separate OneDrive
replicas: stop other-device runs and finish synchronization before resuming.
Read the portable [resume contract](../.agents/skills/clew-import/references/resume.md)
for complete inspection, approval, failure and synchronization rules.

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
contract. Missing per-response usage or unobserved interrupted request attempts
makes the OpenAI estimate incomplete,
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
On failure preserve output and pause; first plan an explicit checkpoint resume
when supported. Deleting a verified exact failed root and
retrying requires separate approval, including synchronized-deletion consequences.
Diagnostic and checkpoint replacement have bounded Windows lock backoff (five waits:
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
recaptures baselines or restores user notes. Enrich help notes (`type: help`
under `aides/`) are left to Enrich's validator.

Validation aggregates codes, error/review severity, paths, one-based locations,
anchors/targets and diagnostics. It is offline and read-only. External URLs are
reported as not remotely verified, not fetched or claimed working. Unsupported
HTML resource links/local fragments, paths escaping the chapter and redirects
are explicit errors. Parser passes do not establish semantic matching or visual
layout. Local helpers exit 0 clean, 2 review-only, 1 errors. Completion requires
a version-1 `.clew/preparation.json` with `status: complete`.

## Course-linked Enrich

[`clew-enrich`](../.agents/skills/clew-enrich/SKILL.md) consumes completed
Import whole-document chapters: an Import `type: chapter` index,
`type: document` source notes, and `.clew/preparation.json` with
`status: complete`. It follows Import's document IDs, exercise/correction unit
comments, entry anchors, and question/answer anchors. It does not consume or
migrate legacy exercise-per-note chapters.

Answer associations recognize both Import's compact `[Question](...) ·
[PDF p. N](...)` footer and standalone `Question` relationship lines.
PDF provenance does not alter the linked question or its exercise ownership.

Enrich adds question-specific hints and supplied-answer explanations as
separate `aides/` notes without changing imported source documents,
preparation artifacts, index, retained sources, or existing aids. Missing
answers are not invented. The agent authors approved additions; a local
baseline validator checks unchanged files, document/unit ownership, supplied
answer associations, and precise course links. It needs the prepared Import
artifact but no Import runtime installation or cloud credentials. See its
[format](../.agents/skills/clew-enrich/references/formats.md).

Document IDs are ownership keys, not Obsidian link targets. Navigate using
unique real filenames or chapter-relative paths (optionally without `.md`);
Markdown links use origin-relative paths. New aids require readable display
labels in question/correction wikilinks and local body links. Existing aids are
not rewritten for new label requirements. Unique exact course headings and
existing block anchors are valid; a title-only anchor does not establish that
its following paragraphs support the claim.

Draft in scratch before writing the vault. For large selections, optional
bounded workers own disjoint exercise ranges and scratch batches; the host
consolidates and reviews all prose. Hints adapt to distinct decisions rather
than fixed counts. Explanations unpack supplied computations, hypotheses,
domains and bounds, with relevant course citations at use.
Every individual hint/explanation includes its own precise course reference;
shared mappings or another callout's citation do not count.
Keep elementary transitions within a course-supported explanation, not in
standalone callouts requiring artificial citations. Distinguish true
contradictions from compressed eventual-rank or uniformity arguments. Unsupported
topics need a user decision and truthful limitations, not artificial citations.

Generate publishes current document-internal units and these aids. It does not
require the Enrich baseline or validator and never edits source notes.

```powershell
uv run --package clew-enrich --locked --no-sync python -B ".agents\skills\clew-enrich\scripts\validate_enrich.py" "C:\vault\prepared-chapter" --capture "C:\scratch\before.json"
uv run --package clew-enrich --locked --no-sync python -B ".agents\skills\clew-enrich\scripts\review_enrich.py" "C:\vault\prepared-chapter" --before "C:\scratch\before.json" --drafts "C:\scratch\batch-1" "C:\scratch\batch-2" --proposal "C:\scratch\proposal.md"
```

Draft directories are explicit and flat; all their Markdown files are proposed
as `aides/<filename>`. The checker overlays them in memory, refuses overwrites
and duplicate destinations/question targets, and writes only a new scratch
preview and companion JSON manifest. Destinations differing only by case are
also rejected for cross-platform safety. These contain exact prose, question/answer/
course mappings, hashes, counts and uncovered questions. Existing output paths
are refused. Record both printed artifact hashes, review mathematical content
and citation relevance, then obtain approval of the exact proposal. An outline
or validator pass alone is insufficient.
Repair failing scratch drafts and retry before approval; do not weaken checks
or change source files. An unvalidated proposal cannot be persisted. Blank
quoted lines around multiline display mathematics keep nearby citations from
being parsed as math rather than links.

Copy only approved bytes with host tools, refusing existing destinations. Check
against the original baseline and the JSON manifest hash recorded at approval:

```powershell
uv run --package clew-enrich --locked --no-sync python -B ".agents\skills\clew-enrich\scripts\review_enrich.py" "C:\vault\prepared-chapter" --before "C:\scratch\before.json" --approved "C:\scratch\proposal.md" --manifest-sha256 "<recorded JSON manifest SHA-256>"
uv run --package clew-enrich --locked --no-sync python -B ".agents\skills\clew-enrich\scripts\validate_enrich.py" "C:\vault\prepared-chapter" --before "C:\scratch\before.json"
```

The approved-content check verifies the exact added-file set, rejects unrelated
new directories even under `aides/`, and checks byte equality, including newline
bytes, but cannot grant user permission or prove pedagogical
quality. The last command performs structural-only validation. Reports separate
explanation sections from explained-note counts. Optional read-only Obsidian
integration checks may confirm actual destinations/fragments within the chapter;
Obsidian is not required, and unperformed visual checks must not be claimed.

Baselines belong outside the chapter/repository, not in published content.
All preexisting files—including Import `.clew/` artifacts—stay unchanged. New
files are limited to Markdown aids under `aides/`. No missing-answer generation,
broader learning enrichment, legacy archive migration, or revision framework.
Source documents use `clew_schema: 1`; new help notes use `schema_version: 1`.
Plain/collapsed/expanded callouts and LF/CRLF/CR input are supported. Multiline
display math has explicit quote prefixes and blank quoted lines around its
`$$` delimiters, preserving real parsed course links outside math/code.

## Offline HTML Generate

[`clew-generate`](../.agents/skills/clew-generate/SKILL.md) consumes current
`clew_schema: 1`, `type: document` notes with explicit roles, scoped
exercise/correction units and stable question/answer anchors. A chapter folder
or its `type: chapter` index discovers visible document/help notes; explicit
current-format files work too. Private `.clew/`, retained `sources/` and vault
configuration are excluded. Legacy exercise-per-note archives are unsupported,
not automatically migrated.

Current edits are authoritative. Publication requires no Import runtime,
`.clew/preparation.json`, retained baselines, hashes or Enrich validator.
Generate checks current publication structure and selected references, not
producer completion or original-source fidelity.

```powershell
uv run --package clew-generate --locked --no-sync python -B ".agents\skills\clew-generate\scripts\inspect_notes.py" "C:\vault" --list-chapters
uv run --package clew-generate --locked --no-sync python -B ".agents\skills\clew-generate\scripts\generate_html.py" "C:\plans\layout.json" --check
uv run --package clew-generate --locked --no-sync python ".agents\skills\clew-generate\scripts\generate_html.py" "C:\plans\layout.json"
```

The small layout remains version 1. Whole worksheets expand to their exercise
units, retaining introductions, section context and review warnings once in
source order. `sheet#^ex-1` selects an exercise scope; native Obsidian links
still address only its entry. Partial question selectors group by their owning
unit, not document ID, and retain shared unit context. Duplicate/overlapping
selections and unsafe ranges are errors.

Exact `Exercise` / `Question` relationship footers determine correction/answer
ownership. Correction context is scoped to one unit, selected answers stay in
source order, and variants remain separate even within one document. Missing
matches warn rather than invent associations. Help notes reuse existing
question/correction references and precise course passages; human-authored
methods can also be consumed, while Enrich authors only hints/explanations.

Python renders current Markdown and embeds figures, fixed HTML-first templates,
CSS, interaction code and pinned offline MathJax. No runtime CDN/server or
source-note changes. Hints/explanations/course excerpts use contextual panels;
supplied corrections stay inline. Missing controls are omitted, not fabricated.
Browser Back/Forward and the panel's `Retour` button restore previous panel
views and revealed hints within the current page session.
PDF references remain external and can break if HTML moves.
Output parent must exist; existing HTML requires explicit exact-file replacement.
See the [layout contract](../.agents/skills/clew-generate/references/formats.md)
for raw HTML, transclusion, remote-resource and dynamic-math limitations.

## Git sharing: Export and install

[`clew-export`](../.agents/skills/clew-export/SKILL.md) publishes one completed
chapter, with its aids, to `Courses/<chapter-name>/` in an existing GitHub or
Azure DevOps repository. It has no scripts: it runs Import's publish script and
plain `git` with the teacher's own credential helper or SSH key. It never uses
`gh`/`az`, creates repositories, embeds credentials in URLs, force-pushes, or
rewrites history. Import's step C installs a published chapter from a
student's scratch clone into the vault.

```powershell
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\publish_chapter.py" "C:\vault\Maths\chapter" --output "C:\scratch\repo\Courses\chapter" --check
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\publish_chapter.py" "C:\vault\Maths\chapter" --output "C:\scratch\repo\Courses\chapter" --publish-sha256 "<approved hash>"
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\install_chapter.py" "C:\scratch\clone\Courses\chapter" --vault "C:\vault" --parent "Maths" --check
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\install_chapter.py" "C:\scratch\clone\Courses\chapter" --vault "C:\vault" --parent "Maths" --install-sha256 "<approved hash>"
```

A published chapter contains the visible chapter files, a `.gitattributes`
that disables line-ending, LFS and encoding conversion, and a reduced
`.clew/preparation.json` with `kind: published`. The record holds the chapter
ID and title, each document's ID, path and role, and every published file's
SHA-256. The private plan, local paths, baselines and hidden entries are not
published. Default validation of a published or installed chapter accepts
edited Markdown and added files but checks recorded non-Markdown files, such
as PDFs and figures. `--fidelity` requires the exact published snapshot.
Installation refuses any download that fails `--fidelity`.

Limits: files over 100 MiB are refused and over 50 MiB need review (Git LFS is
not used); a republish that replaces recorded PDFs or figures, or changes the
documents, needs review because another course with the same title has the
same chapter ID; a rejected push stops and is retried from a fresh clone;
installing over an existing folder is refused, so updates install under a new
name. Import planning skips installed chapters like prepared ones. See
[the preparation contract](../.agents/skills/clew-import/references/preparation.md#published-chapters)
for the exact record and checks.

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
and standalone runtime, plus publishing, installation and a local bare-repository
Git round trip (skipped without `git`). Export has no scripts or script tests;
its workflow evaluations are in the skill. Enrich tests cover prepared-document consumption,
navigation with IDs distinct from filenames, ambiguous basenames, new-link
labels, folded callouts, multiline math/newlines, additive preservation, scratch
proposal integrity, approved-byte equality and copied-skill runtime. Workflow
evaluations cover authoring quality, evidence relevance and exact approval.
Generate's suite covers multi-unit current-document publication, current Enrich
integration, source preservation, selection/ownership failures, supported
newline variants, relocation, standalone runtime and offline interactions.
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
