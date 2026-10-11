# ADR-0002: PDF Import skill and project-level Python runtime

- Status: Accepted
- Date: 2026-10-04

## Context

An existing pinned converter provides PDF layout/OCR, vision reconciliation,
figures and diagnostic evidence. Reusing it avoids a new conversion engine.

## Decision

`clew-import` owns conversion and local preparation. Its conversion executable
is `scripts/digest_pdf.py`, derived from `dbroeglin/clew-old` commit
`77c1e4c4569e4e8067f20d3809edd582b1f9a257`, blob
`d0eff2c0daa9e454360eb649db459b4c72408d42`, under MIT.
Keep explicit provenance and do not fetch moving upstream code.

Conversion uses Document Intelligence and Azure OpenAI/Foundry with Entra ID
`DefaultAzureCredential`. Configuration templates/dependencies are skill-owned;
real `.env`, locks and environments are host-owned. No API keys, automatic
login/provisioning or leaked configuration. Clew uses a shared UV environment.

Inspect recursively and deterministically, allowing non-redirecting OneDrive
placeholders but refusing redirects/unknown reparse tags. Exclude recognized
conversion/prepared/legacy owned roots and retained copies. Conflicts are visible.
Complete source/hash/artifact/page-scope matches reuse existing bundles;
partial/stale/unrelated outputs are not overwritten by default.

Before paid conversion, approve exact PDFs, hosts, options, commands and charges.
Recheck source/configuration and destination absence. Outputs default to sibling
basename directories, explicitly passed to `--output`.
Retain schema-3 bundles: byte-identical complete original PDF at `source/<name>`,
`document.md`, figures, raw evidence, manifest and run diagnostics.

Direct page responses, conservative transcription, bounded judging and offline
formula checks follow ADR-0005/0009/0010/0011. Existing complete bundles remain
valid without additive newer review metadata. Converter exits remain 0
extracted, 2 complete-needs-review, 1 failed, 130 interrupted.
Planner 2 denotes conflicts/preflight blockers, not a completed conversion.

New conversions maintain a separate schema-1 `checkpoint.json` with source,
normalized scope, effective options/configuration and converter/Python-interpreter/dependency
fingerprints, committed artifact hashes, pending local writes, DI submission/ID,
and a paid-call ledger. Immutable numbered `raw/checkpoints` responses preserve
all returned API evidence, including rejected responses. Explicit `--resume`
replays deterministic orchestration/local checks and reuses usable responses
without resetting bounded corrective attempts. Conventional artifact paths and
completion schema 3 remain stable. Old partial runs without checkpoints are
not adopted; historical completed bundles stay supported.

The read-only planner supports explicit resume and a custom output for a single
PDF, reports cached/failed/uncertain requests and remaining-work bounds, and
binds its command to the current checkpoint hash. Fresh approval covers
remaining/repeated paid work, not deletion. Recheck source, configuration,
checkpoint and artifacts before execution. Changed settings, scripts/dependency
versions, missing/changed artifacts, redirects or unexpected files block reuse.
A deployment fingerprint cannot detect provider-side backing-model changes.

Poll DI by saved operation ID if no layout was saved; never silently resubmit an
unknown, failed or expired operation. A submitted request without saved ID/result
is blocked. Unobserved OpenAI responses may require repeated paid requests;
resume does not promise exactly-once billing. Restore usage from saved responses
once, including rejected responses, and suppress the price estimate when
interrupted attempts have no observed usage.

An OS advisory output lock prevents cooperating same-filesystem processes from
writing concurrently and releases on process termination. It is not a
distributed lock across synchronization replicas. A verified completed
checkpoint is a no-op, including review-required completion.

Failed/interrupted runs preserve diagnostics and first offer a separately
approved compatible checkpoint resume. Delete-and-restart needs fresh
exact-path approval, ownership checks, no unexpected files/redirects, source
rechecks and synchronized-deletion warning. No automatic batch continuation,
cleanup or repeated restart loop.
Local preparation consumes completed bundles without cloud configuration;
its subset does not replace the full raw-evidence bundle.

## Consequences

Conversion artifacts and exit meanings remain stable, while compatible future
interruptions can reuse paid work rather than requiring a complete restart.
Preserving the original runtime and unchanged configuration is deliberate;
legacy partial-run recovery and configuration migrations are outside scope. Paid work,
local organization and deletion have distinct permissions. Hashes and successful
parsing do not establish transcription fidelity.
