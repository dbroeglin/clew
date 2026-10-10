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
partial/stale/unrelated outputs are not overwritten.

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

Failed/interrupted runs preserve diagnostics. Delete-and-restart needs fresh
exact-path approval, ownership checks, no unexpected files/redirects, source
rechecks and synchronized-deletion warning. No automatic batch continuation,
cleanup or repeated restart loop.
Local preparation consumes completed bundles without cloud configuration;
its subset does not replace the full raw-evidence bundle.

## Consequences

Conversion behavior remains stable while preparation is simplified. Paid work,
local organization and deletion have distinct permissions. Hashes and successful
parsing do not establish transcription fidelity.
