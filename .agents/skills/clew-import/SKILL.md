---
name: clew-import
description: >-
  Convert local PDFs and prepare their whole Markdown documents for Obsidian
  with stable anchors, callouts, PDF-page links, and supplied-answer matches.
  Use for PDF conversion, directory import planning, organizing completed
  conversion bundles in a vault, or validating prepared documents. One portable
  skill, two resumable steps: paid conversion and deterministic local
  preparation. Preserve source content; no splitting, OCR repair during
  preparation, learning-content enrichment, or HTML generation.
---

# Clew Import

Convert local PDFs, then prepare their **whole** converted Markdown for Obsidian.
These are two resumable steps in this one skill. A conversion-only request stops
after step A. A preparation request can start with explicitly selected completed
conversion bundles without reconversion or cloud configuration. Never summarize,
translate, solve exercises, correct author claims, generate aids, or publish HTML.

Step A preserves the existing converter below. Step B uses source selectors and
local Python, not LLM-authored replacement Markdown. Read
[the preparation contract](references/preparation.md) and
[the worked example](references/example.md) before planning step B.
Do not import runtime code from a sibling skill or require repository ADRs/tests.
Enrich and Generate currently consume the older exercise-per-note layout, not
this skill's new whole-document output; do not run them on it as a supported
handoff. Their refactors are separate work.

The executable is `scripts/digest_pdf.py` relative to this skill. Python
dependencies and supported Python versions are declared in this skill's
`pyproject.toml`. The skill can run as a standalone UV project. When installed
as a member of a UV workspace, use the host's shared lockfile and `.venv`; in the
Clew workspace select the `clew-import` package. Offline formula checking also
requires Node.js >=22 and npm >=10. This skill's `package.json` declares
`mathjax-full` 3.2.2 and its `scripts/check_math.cjs` runs MathJax without a
browser. In Clew, this is the `@clew/import` npm workspace: install from the
repository root, using its `package-lock.json` and hoisted root `node_modules`,
not a separate skill-local installation. Node itself is the installed host
runtime on PATH, not an executable copied into the repository.
Real configuration remains in
the execution project root's untracked `.env`; use this skill's `.env.example`
as the complete template. Never require repository ADRs or other documentation
to operate this skill.

## Step A: PDF conversion

### 1. Inspect without changing anything

Confirm the input location. If it was not supplied, ask for one. Default outputs
are beside their PDFs: `chapter_1.pdf` -> `chapter_1`, including nested PDFs.
Do not invent a vault layout or ask for a separate destination by default.

Inspect the Python and npm manifests/locks, UV/Node/npm availability, `.env`
presence, project `.venv`, and npm dependencies. Never dump `.env` or inherited
environment contents, or print
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

Node dependency setup is a separate approved local action, not a cloud import:
run `npm ci --ignore-scripts --no-audit --no-fund` from the Clew root. Do not
run `npm install` inside a Clew skill, use `npx`, install a global MathJax, or
silently download dependencies during discovery/conversion. npm's hoisted
workspace installation uses one root lock and installation tree for compatible
versions; incompatible future dependencies can cause nesting and must be
resolved deliberately, not hidden. For a standalone copied skill, approve an
initial `npm install --ignore-scripts --no-audit --no-fund` in its directory
to create that host's lock, then use `npm ci --ignore-scripts --no-audit
--no-fund` subsequently. A missing Clew npm lock is a repository blocker, not
permission to regenerate it during imports. Missing Node/npm requires separate
host setup; do not install or change runtimes automatically.

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
`--high-resolution-ocr`, `--no-page-review`, and `--debug` options to the
planner. Do not enable high-resolution OCR without an explicit request:
it is a paid add-on.
Do not silently change rendering, page scope, deployment, or token budget.
Source-grounded LLM page review is enabled by default; disable it only when
the user requests `--no-page-review`. The plan's `page_review` records the
enabled state and two-corrective-attempt limit; each eligible entry's
`page_model_requests` gives minimum/maximum logical OpenAI page requests.

The planner does not upload, convert, create directories, or delete anything.
It does launch the local Node checker for a read-only smoke test; it does not
launch a browser or run npm. It reports missing/unusable MathJax as a preflight
blocker and includes `node_setup_command` alongside the UV setup command.
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

Windows synchronization, scanning, or readers can temporarily block replacement
of progress diagnostics. The converter writes `run.json.tmp` once per save,
then atomically replaces `run.json`. Only that replacement retries Windows
errors 5 (access denied), 32 (sharing violation), or 33 (lock violation): five
logged backoff waits of 0.1, 0.2, 0.4, 0.8, and 1.6 seconds, at most six
replacement attempts and 3.1 seconds of waiting per save. Other errors and
temporary-file write failures propagate immediately; exhausted retries remain
explicit failures. This does not repeat cloud calls, restart imports, delete
outputs, or change permissions. A persistent lock still requires investigation;
an output outside the synchronized folder can avoid synchronization contention.

Shared sources or outputs may change on another laptop or through a collaborator.
Recheck source identity and output ownership before execution or cleanup. Warn
that deleting a synchronized failed-output directory can propagate that deletion
to other devices and people. Approval for conversion is not deletion approval.

### 2. Propose the exact plan and get approval

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
Explain the default page-review cost before approval: each page uses an initial
transcription and one judge call, with up to two corrective transcription/judge
pairs (2-6 logical OpenAI requests per page). Figure classification and SDK
transport retries are additional. The same configured deployment and endpoint
handle transcription, review, and corrective attempts; no separate judge
deployment or service is used. Approval for that bounded plan covers its
in-run page corrections, not deleting/restarting an import, retrying failures,
or reprocessing completed bundles. Do not add your own retries after the bound.

### 3. Execute the approved commands

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

The page prompt requires minimal, image-evidenced corrections, preserves correct
source wording and notation (including source mistakes), and confines LaTeX to
math delimiters. Literal commands discussed by the source belong in code;
typographic gaps in prose and headings become ordinary spaces.

Page reconciliation requests plain-text Markdown, not a JSON `markdown`/`fixes`
envelope. No self-reported corrections or confidence scores are requested or
logged. Unreadable source content is marked in place in the Markdown; a page
without substantive content returns `<!-- Blank page. -->`. Empty or
whitespace-only output is a failure, not a successful blank page. Incomplete
responses and refusals without extraction remain failures.

Figure classification still requests strict JSON and validates its decision,
kind, reason, and alt text before using a crop. Raw page and figure
`*.response.json` files retain the complete API response before completion or
content checks; page response text is now Markdown directly, while figure
response text remains JSON. Python preserves page text, including TeX
backslashes and whitespace, without parsing an inner JSON string. Assembly
only adds the existing page comments and inter-page separators to the selected
final candidates.

### Source-grounded judge and bounded corrective attempts

By default, every candidate page is reviewed in a fresh Responses API request
to the same deployment, without the transcription conversation or earlier judge
feedback. The judge receives the original page image, original OCR/formula
hints, figure metadata, the complete candidate Markdown, and local format
findings. It examines the whole page for omissions, duplication, changed
variables, signs, inequalities, exponents, denominators, grouping, numbering,
and source-visible typography, plus Markdown/LaTeX representation problems.
Its MathJax guidance covers the target base, ams, newcommand, and configmacros
packages and llbracket/rrbracket macros. Before judging, a separate local
checker actually runs MathJax; the judge receives its located errors in
`local_format_issues`. Neither checker nor judge depends on another installed
skill.

The judge returns strict JSON with `findings`, not replacement Markdown or
confidence scores. Each finding has `category` (`transcription`, `format`, or
`uncertain`), `location`, `description`, `source_evidence`, and `instruction`.
Location, description, source evidence, and instruction must be nonblank and
contain no unexpected control characters; defects involving controls must be
described by code point rather than copied into report fields. Source mistakes
are not transcription errors: do not correct the author's mathematics,
spelling, or source numbering.
Unclear source material must be marked honestly, not reconstructed by guessing.

If a judge finds a transcription/format discrepancy, or the executed MathJax
check finds an error, the converter makes at most two corrective attempts
within the same shared budget. Renderer errors cannot be ignored by an empty
judge report. Each attempt receives the original image/hints,
previous candidate, and current feedback. Feedback is fallible: the page
transcriber must verify it against the source and return a complete plain
Markdown page with only source-evidenced changes. Each new candidate is judged
from scratch across the whole page, including possible regressions elsewhere.
Uncertainty-only findings with no renderer errors stop without a guessed
correction. On success,
select the latest candidate unchanged. If the final judge still reports
findings or local checks still flag issues, preserve the last candidate and
publish `needs_review` with exit `2`; do not hide issues, delete outputs, or
loop until a pass. An empty judge report is not proof of source fidelity, and
the same model in a separate request can share the transcriber's blind spots.

Retain every full candidate response, exact candidate Markdown, and complete
judge response under `raw/pages/page-NNNN.attempt-AA.response.json`,
`page-NNNN.attempt-AA.md`, and `page-NNNN.attempt-AA.review.response.json`.
The existing `raw/pages/page-NNNN.response.json` references the selected final
candidate on completion. Manifest schema 3 gains additive configuration fields
`page_review`, `max_page_retries`, and `mathjax_version`, plus per-page `review` with `status`
(`passed` or `needs_review`) and `attempts`. Each attempt records its number,
`raw_markdown`, `raw_response`, `raw_review`, `raw_math`, structured `findings`, and local
`format_issues`. `passed` means no issues were found, not verified correctness.
The planner checks all referenced attempt artifacts when inspecting a reviewed
completed bundle. Raw API evidence is retained before validation. Empty,
incomplete, refused, malformed, or invalid judge/corrective responses are
explicit failures, not passes and not reasons for automatic content retries.
Partial artifacts and diagnostics remain for the failure gate below.

`--no-page-review` disables the judge and corrective loop, retaining the
single-transcription behavior and existing raw page response paths without
per-page review records. Local non-mutating checks remain enabled. Existing
completed imports, with or without judge metadata, are not rescanned, migrated,
modified, or reconverted automatically.

### Independent local format review

The converter does not perform string replacements or reconstruct TeX itself.
A non-mutating check reports possible LaTeX leakage in parsed ordinary text
using this bounded command list: `\quad`, `\qquad`, `\hspace`, `\vspace`,
`\enspace`, `\thinspace`,
`\frac`, `\dfrac`, `\tfrac`, `\sqrt`, `\mathbb`, `\mathcal`, `\mathrm`, `\mathbf`,
`\text`, `\begin`, `\end`, `\left`, and `\right`. Findings include the original
PDF page, page-local Markdown block line or line range, and a short excerpt.
They appear in manifest `issues`, produce status `needs_review` and exit `2`,
and must be reported if still present in the selected final candidate.
Candidate findings are also supplied to the judge. These leakage/control flags
alone do not trigger corrections; a correctable judge finding or executed
MathJax error does. Local findings cannot be cleared by an empty judge report.

The check excludes math, code, link destinations, image paths, raw HTML tokens,
and recognizable Windows drive, UNC, and dot-relative paths. Link labels and
text between inline HTML tags are still ordinary text. Unknown commands, raw
HTML blocks, and other formula errors can escape detection; literal commands
outside code or ambiguous relative paths can produce false positives. Neither
the prompt, this check, nor a clean completion proves content fidelity.
Previously completed bundles are not automatically rescanned or modified.

A second local check flags Unicode `Cc` control characters anywhere in page
Markdown except newline, carriage return, and tab. Findings identify the
original PDF page, page-local line, and code points such as U+0008 or U+001B.
It never removes characters or rewrites candidate text. These two local checks
are not complete TeX, MathJax, mathematical-correctness, or source-fidelity
validators.

### Executed offline MathJax check

The planner and converter preflight render a known expression before any
conversion writes, credentials initialization, or cloud submission. Each
candidate page then gets one Node process that initializes MathJax once and
typesets all parsed expressions to SVG in memory using `liteAdaptor`. No
browser, DOM application, network, temporary SVG, or screenshot is required.
The checker uses MathJax 3.2.2, only the base/ams/newcommand/configmacros
packages, and `llbracket: \lbrack\!\lbrack` /
`rrbracket: \rbrack\!\rbrack` macros. It does not autoload extra extensions.
Active/external commands `\require`, `\href`, `\url`, `\htmlClass`, `\htmlId`,
`\htmlStyle`, and `\includegraphics` are rejected. Unexpected control
characters are also rejected before invoking TeX, avoiding renderer crashes.

Math extraction uses CommonMark with tables and dollar math, with raw HTML
disabled to match downstream Markdown publication. Code blocks, code spans,
image alt text, and link/image destinations are not checked as formulas.
Inline and display expressions retain page-local block line ranges and IDs.
Each fresh candidate batch replays only already-selected prior-page math in
source order, then its current expressions; definitions can persist within a
page or across selected pages, but discarded attempts cannot contaminate a
later check. Content outside the selected scope is not reconstructed.

TeX error callbacks and SVG error nodes count as failures even when MathJax
returns SVG successfully. A missing runtime/dependency, timeout (60 seconds
per batch), malformed or inconsistent protocol, or unexpected checker failure
fails the import explicitly rather than producing a render pass. Ordinary
formula errors feed the bounded correction loop and, if unresolved, yield
`needs_review`. With `--no-page-review`, MathJax still checks the single
transcription but does not make judge/corrective calls.

`raw/pages/page-NNNN.math.json` records the selected candidate's check.
Reviewed candidates additionally retain `page-NNNN.attempt-AA.math.json`,
referenced by each attempt's `raw_math`; each page also has `raw_math`.
Reports contain engine version/packages/macros, the replayed-context count,
every exact formula with display mode and block lines, and its errors.
The planner requires these artifacts when `configuration.mathjax_version` is
present; historical completed imports without them remain valid and unchanged.
Reports do not alter the retained Markdown. Renderability is not source
fidelity, mathematical correctness, proof of complete extraction, resolved
cross-references, or final-layout validation; the source-grounded judge remains
necessary. Only parsed dollar-delimited expressions are checked: missing or
unrecognized delimiters can prevent extraction and still need source review.

`source/<original-filename>` contains a byte-identical copy of the entire input
PDF, even for a selected-page import. `document.md`, `figures`, `raw`,
`manifest.json`, and `run.json` remain together. No input PDF is moved or changed.
Step B can copy a retained subset into its own output: the original PDF,
unchanged imported Markdown baseline, and referenced figures, with source metadata.
Raw extraction evidence and diagnostics remain in this untouched complete bundle;
the subset must not be presented as a complete conversion bundle. Do not remove
external bundles after preparation.

### 4. Failure: explicit delete-and-retry gate

On failure, stop the batch. Show the failed command, relevant error, and
diagnostic locations. Do not expose configuration or SDK credentials in a
report. Ask whether the user approves **deleting this run's exact output
directory and retrying this command**, warning that diagnostics and partial
artifacts will be lost and paid cloud work may repeat.
This gate concerns failed whole imports; it is separate from the explicitly
planned, bounded page-correction loop inside a running import. Judge/API/schema
failures do not authorize a restart or cleanup.

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

## Step B: Whole-document Obsidian preparation

### 1. Inspect selected bundles and the identified vault

Require explicitly selected completed bundle paths and a user-identified vault.
Do not scan unrelated locations for a vault or select neighboring bundles
automatically. Read all selected `document.md` files and review their figures,
headings, exercises, questions, supplied answers, and conversion issues.

```powershell
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\inspect_bundles.py" "C:\courses\cours" "C:\courses\exercices" "C:\courses\corriges"
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\inspect_vault.py" "C:\vault"
```

Local commands need the installed Python environment only: no `.env`, Azure
credentials, Node process, Obsidian, plugin, or network. Missing setup is a
separate visible host-approved step. Use `--no-sync` during inspection.
Standalone copies omit `--package` and use their local `scripts` paths.

The bundle inspector checks retained PDF hashes and actual page counts, imported
coverage, page/figure evidence, local asset declarations, and additive review/math
artifacts when present. `needs_review` is completed but unverified material:
carry its issues into preparation, including visible warnings. Missing,
incomplete, malformed, redirected, or changed sources are blockers.
The read-only Markdown inventory exposes fingerprint-bound `b-N` selectors,
one-based source line ranges, safe blocks, headings, original page numbers, and
existing anchors. Selectors are temporary addresses for this exact source,
not permanent Obsidian IDs. Do not invent offsets or treat parser safety as
proof of a sensible semantic boundary.

Read relevant existing vault notes yourself to understand placement conventions.
The inventory lists paths/sample counts, not their meaning. Review omitted
subtrees with `--within`, `--depth`, and `--max-directories` if necessary.
Choose one new chapter under a suitable non-root vault parent, outside earlier
owned roots. Do not impose a fixed subject/level hierarchy. Include placement
rationale and any exact missing parent containers to create in the concrete plan.
Resolve genuine ambiguity with one focused user question; one final preparation
approval covers placement and writing, not an additional placement-only ceremony.

### 2. Choose structural operations, never rewrite source prose

Create **one complete editable Markdown note per PDF**, retaining source order,
introductions, shared instructions, proofs, equations, figures, numbering,
supplied mistakes, and repeated-looking passages. Mixed sources stay in one
document. No line-coverage partition or source-note splitting is needed.

Role is based on source content, not filenames alone. Recognized documents use
`Course-<basename>`, `Exercise-<basename>`, or `Correction-<basename>` folders;
unknown/mixed documents use the original PDF basename. Each contains the
basename `.md`, original PDF filename, and referenced `figures/`. Case-insensitive
collisions or nonportable basenames require an explicitly approved folder/name
decision; never silently suffix or rename. The private `.clew/baselines/` keeps
immutable original Markdown. The record is `.clew/preparation.json`, not a
legacy `ingest.json`.

Use only the contract's typed operations:

- `unit`: mark a section, exercise, or supplied correction scope and give it
  a native entry anchor; correction-to-exercise matches require source evidence.
- `callout`: wrap a selected definition/theorem/property/lemma/proposition/
  corollary/example/remark/proof or question/answer with its source-derived
  title and exact body. Questions identify their owning exercise; answers
  identify their correction and, when verified, their target question.
- `anchor`: add or reuse an ID on one safe block.
- `heading`: change only a selected heading's structural level.

Python additionally inserts metadata, original-PDF-page provenance, required
destination-only PDF/self-link remaps, and visible review warnings. The agent
authors selectors, IDs, relationships/evidence, and review reasons, **not**
replacement source Markdown. Generic text replacement, OCR repair, deletion,
reordering, blanket regex classification, and whole-tree reserialization are
not operations.

Keep genuine headings for whole-section navigation. Use stable block IDs for
precise statements/questions/answers. A section/exercise entry anchor targets a
navigation point, not a native embed of every following paragraph.
Question/answer callouts stay independently addressable at top level: native
Obsidian does not support links to parts inside enclosing callouts/quotes/tables.
If content cannot be addressed safely, preserve the coherent passage and report
it with a scoped warning instead of corrupting syntax.

IDs are unique within their document, ASCII letters/digits/dashes, assigned once,
and independent of line numbers/title hashes. Reuse existing IDs; do not
renumber them when visible source labels change. Match corrections from supplied
statements/reasoning, never positions or numbering alone. Uncertain answers and
corrections remain unlinked, with a visible warning beside their source content.
Do not invent missing material or infer course prerequisites.

### 3. Preview and approve the exact local preparation

Author a version-1 plan outside the bundles and intended output, in the host's
planning storage. Read the complete contract/example first.

```powershell
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\prepare_documents.py" "C:\plans\preparation.json" --check
```

Show the full source set/roles, placement/rationale, folder/file list, operations
and boundaries, exercise/question/answer ownership, matches/evidence, visible
warnings, exact diffs, command, and returned `plan_sha256`. Obtain **one explicit
approval** for that concrete preparation. General implementation approval or
cloud-conversion approval is not permission to write user notes.
Hard errors block approval/execution; review-only findings are disclosed and
inserted as generated `[!warning] Clew review` callouts in affected notes and
summarized in the index. Never hide findings to obtain a clean report.

### 4. Execute the approved plan and validate persisted output

```powershell
uv run --package clew-import --locked --no-sync python ".agents\skills\clew-import\scripts\prepare_documents.py" "C:\plans\preparation.json" --plan-sha256 "<approved hash>"
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\validate_documents.py" "C:\vault\Maths\chapter" --fidelity
```

The hash binds the source/operation/output contract; it is not proof of permission.
Changed sources, plan, or an existing output root require a fresh plan, not
automatic overwrite or hash updates. Only a new owned chapter and explicitly
approved missing parent containers may be created. All notes, PDFs, figures,
index, baselines, and record live under that root. No source bundle is modified.
Copy only retained PDFs and referenced figures, not Azure config or raw evidence.

The writer checks candidate structure/links and independent exact source
projection before writing, then checks persisted fidelity before marking complete.
A failure preserves its exact partial root and `writing` record; stop, report it,
and never delete/retry/merge automatically. Any removal needs separate scoped
approval. Removing the exact prepared root removes its own files; shared approved
parent containers and original conversion bundles must not be deleted.

### 5. Validate current notes after manual edits

```powershell
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\validate_documents.py" "C:\vault\Maths\chapter"
```

Default validation accepts manual prose edits and checks current schemas,
anchors, unit structure/ownership, reference syntax, local notes/figures, and PDF
page bounds. Immutable baselines/PDFs/retained assets remain checked.
Moving the entire chapter preserves its relative links and needs no external
bundle. After a deliberate per-document folder rename, keep the note/PDF/figures
together and update relative links; default validation locates documents by ID.
`--fidelity` intentionally reports changes since the original prepared snapshot,
including document relocation; it never recaptures baselines or restores notes.

The validator aggregates coded errors/review findings with paths, one-based
locations, affected IDs/targets, and actionable diagnostics. It is read-only.
External URLs are reported as not remotely verified, never fetched or claimed
working. A syntactic pass cannot prove theorem boundaries, semantic matches,
mathematical correctness, or Obsidian visual layout.

Preparation/validation helpers exit `0` for clean checks, `2` for review-only,
and `1` for errors. A completed prepared root requires version 1 and
`status: complete`; an exit code alone is not completion. The existing step-A
planner/converter exits keep their documented separate meanings.
Report the chapter root/index, one-note-per-PDF count, roles, validation mode,
and all unresolved warnings. Enrich/Generate support for this new format remains
deferred; existing legacy note archives are neither migrated nor modified.

## Provenance and maintenance

`digest_pdf.py` is copied from `dbroeglin/clew-old` at commit
`77c1e4c4569e4e8067f20d3809edd582b1f9a257`, blob
`d0eff2c0daa9e454360eb649db459b4c72408d42`, under the repository MIT license.
Functional deviations are source preservation and hash verification with the
relative `source.path` in the manifest, conservative page-transcription prompt
instructions, and a non-mutating review check for known LaTeX commands outside
math. Page responses now use direct Markdown rather than the upstream JSON
envelope and self-reported fixes/confidence list; figure responses retain strict
structured output. Default independent page judging and up to two corrective
attempts add source-grounded review feedback and retain every draft/judgment.
Non-mutating LaTeX leakage and control-character checks use the existing
`needs_review` status and exit `2`; Python preserves selected model Markdown
without string repairs. `--no-page-review` opts out of the judge loop. Existing
artifact references, manifest schema 3, and exit-code meanings remain supported;
review metadata and attempt evidence are additive.
Atomic `run.json` replacement also has bounded local backoff for Windows
access/sharing/lock errors, without repeating cloud work.
Executed MathJax checks now run from this skill's own Node helper and declared
dependency, retaining check reports and using the existing corrective budget.

Do not fetch a moving upstream revision during an import. Workflow evaluations
are bundled under `evals`. Executable tests and fixtures are repository-owned,
outside skill directories; they are not required to operate a standalone copy.
For development in Clew run:

```powershell
uv run --package clew-import --locked --no-sync python -B -m unittest discover -s "tests\clew_import"
npm run test:mathjax
```

Standalone runtime commands above remain self-contained; development tests
are run from the source repository. Tests and evaluations must not make real
cloud calls or remove user data.
