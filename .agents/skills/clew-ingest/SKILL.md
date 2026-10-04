---
name: clew-ingest
description: >-
  Structure one or several existing clew-import PDF bundles into faithful,
  Obsidian-compatible course, exercise, and correction notes with retained
  sources. Use when asked to ingest imported course material, organize imported
  exercises and corrections, or plan that organization. The agent chooses
  boundaries and source-evidenced links; small local scripts execute an explicitly
  approved plan. Not PDF conversion, enrichment, or HTML generation.
---

# Clew Ingest

Organize supplied content without changing its meaning. Accept one or several
explicitly selected Import bundles: course, exercises, and corrections may be in
different bundles or mixed in one. Missing exercises or corrections are allowed.
Never generate missing material, summarize, paraphrase, translate, correct the
source, infer competency prerequisites, or silently discard difficult passages.
Those are separate enrichment tasks. Do not produce HTML.

The host agent supplies the intelligence. Python performs inspection, exact
slicing, structural wrapping, copying, and validation, not pedagogical decisions.
Optional subagents may inspect a bounded independent source, but are not a
requirement and cannot authorize execution.

## Runtime and portable assets

Requires Python >=3.11, UV, and an agent capable of reading Markdown, authoring
JSON, and obtaining explicit user decisions. Dependencies are declared in this
skill's `pyproject.toml`; no Azure credentials, cloud SDK, Obsidian installation,
plugin, repository ADR, or import executable is needed.

Consume completed clew-import schema-version-3 bundles: `manifest.json`,
`document.md`, original PDF at `source.path`, original source SHA-256, page records,
figure records, and issues. Raw page files must be present for initial inspection;
they are not copied. The producer skill need not be installed.

In a Clew UV workspace, run from its root with `--package clew-ingest --locked`.
A copied standalone skill runs from its own directory without `--package`, using
its local `scripts` path. Setup is a separate visible step: workspace
`uv sync --all-packages --locked`; initial standalone `uv sync`, then
`uv sync --locked` subsequently. Obtain setup approval under the host's rules.
Do not edit a host manifest/lock or install dependencies during inspection.
Use `--no-sync` after setup so read-only commands cannot install anything.

All examples below use PowerShell paths. Adapt quoting and separators to the
host platform. Helpers emit portable forward-slash relative references in JSON
and Markdown, not shell commands.

## 1. Inspect selected inputs, without writing

Ask for bundle paths and a new destination if not supplied. Do not recursively
select neighboring sources or invent a vault destination.

```powershell
uv run --package clew-ingest --locked --no-sync python -B ".agents\skills\clew-ingest\scripts\inspect_bundles.py" "C:\courses\course" "C:\courses\exercises" "C:\courses\corrections"
```

Read the JSON report and the actual `document.md` files. Inspection checks
completion, retained PDF identity, page coverage, local assets, and safe line
boundaries. `needs_review` is not verified content: carry every import issue
into the ingest plan and show it to the user. Malformed/incomplete bundles,
missing assets, redirected paths, or unsupported local-link syntax are blockers.
Report their precise cause; do not rewrite imported Markdown as a silent fix.

Non-redirecting OneDrive placeholders are supported. Reads may hydrate files.
Report hydration/access errors; do not change synchronization settings, skip
sources silently, or follow symlinks/junctions. Shared inputs may change later.

Read [the plan and note contract](references/formats.md) and
[the worked example](references/example.md) before authoring a plan.
The helper reports `safe_boundaries` as **zero-based line boundaries**. Plan
ranges are **one-based inclusive lines**: both `start - 1` and `end` must be
safe boundaries. A parser boundary is a mechanical permission, not a sensible
semantic cut.

To inspect a selected range exactly:

```powershell
uv run --package clew-ingest --locked --no-sync python -B ".agents\skills\clew-ingest\scripts\slice_markdown.py" "C:\courses\course\document.md" --start 1 --end 12 --sha256 "<files.document.md hash from inspection>"
```

## 2. Decide structure and propose a concrete plan

Choose coherent subtopics; keep statements with proofs, figures with explanations,
and exercise context with questions. Do not impose a fixed page/token count or
automatically split at headings. If a question cannot be separated safely, keep
the larger unit and flag it rather than breaking a formula, list, or table.

Choose meaningful course/section filenames together under `courses/`.
Exercises belong in `exercices/`, corrections in `corriges/`. Choose one ingest
namespace and distinct source IDs. Every source gets its own `sources/<source-id>/`
directory even when original filenames match. The user approves these choices.

Match answers to questions using supplied numbering, statements, and reasoning,
not filename similarity alone. An exercise may have multiple supplied corrections.
Only add `needs` when an earlier question's result is actually reused. Store
evidence ranges for every relationship. Do not introduce `teaches`, `assesses`,
competency notes, misconceptions, rubrics, or inferred prerequisite graphs.

Preserve all selected content exactly once, including introductions, shared
instructions, unnumbered questions, and repeated-looking passages. Keep source
reading order. Missing/ambiguous matches remain source content with review
issues, not fabricated targets. Add explicit plan issues explaining uncertainty;
do not imply that an omitted uncertain link was verified.

Author a version-1 JSON plan in a host-approved planning location, **outside**
the input bundles and intended output. Author selectors, not rewritten prose.
Keep planning files out of the source documents and user course tree unless
the user explicitly requests that location.

Check it without materializing:

```powershell
uv run --package clew-ingest --locked --no-sync python -B ".agents\skills\clew-ingest\scripts\write_ingest.py" "C:\plans\ingest.json" --check
```

Show the complete source set and roles, destination, meaningful note names,
boundaries and rationale, reading order, question/answer matches, dependency
evidence, copied-source subset, review issues, output file list, exact execution
command, and returned `plan_sha256`. Ask for explicit approval before writing.
Approval of skill implementation, a general request to ingest, or approval of a
different run is not approval of this concrete plan.

## 3. Execute only that approved plan

```powershell
uv run --package clew-ingest --locked --no-sync python ".agents\skills\clew-ingest\scripts\write_ingest.py" "C:\plans\ingest.json" --plan-sha256 "<approved plan hash>"
```

The hash binds the command to the inspected plan; it is not proof of permission.
The agent must obtain permission. Inputs and plan are rechecked before writing.
If either changes, stop and obtain approval of the changed plan.

Only a new output root is allowed, with an existing parent. Never merge, overwrite,
delete, or write inside an input bundle. All notes, source copies, figures, index,
and provenance live beneath that root. External inputs remain unchanged.
Copy byte-identical original PDFs and Markdown, plus referenced figures only.
Raw extraction artifacts, cloud configuration, and logs remain in the original
bundles. The retained subset is not a complete clew-import bundle.

## 4. Validate and report

```powershell
uv run --package clew-ingest --locked --no-sync python -B ".agents\skills\clew-ingest\scripts\validate_ingest.py" "C:\vault\algebre"
```

The writer validates before marking completion; independently validate the
persisted root and inspect representative notes, equations, figures, and links.
Mechanical fidelity does not establish that the agent's boundaries or matching
decisions are pedagogically correct.

All JSON helpers return `0` for completed checks/operations, including visible
review findings, and `1` for errors. Slicing emits Markdown rather than JSON.
`needs_review` is a report status, not an error to hide. `ingest.json` must have
`status: complete`; a process exit alone is not completion evidence.

On failure, stop. Preserve partial output; show the exact root and actionable
diagnostic. Do not retry into that root, delete it, or continue another ingest
automatically. Interruption can leave a `writing` record; it is incomplete.

Report the ingest root, index, note counts, source set, and unresolved review
items. **Removing the exact ingest root removes every file from that ingest.**
No files are shared with another ingest; no cleanup helper is supplied. A later
request to delete it needs a separate scoped approval, especially in shared
synchronized folders. Do not delete original bundles as part of removal.

## Maintenance

Executable tests and fixtures are repository-owned and deliberately **outside**
the distributable skill (`tests/clew_ingest/` in Clew). They are not required at
runtime. Bundled `evals/evals.json` describes agent decision/approval cases.
Authored assets use the bundled MIT license; runtime packages retain their own
licenses. No moving upstream code is fetched during ingestion.
