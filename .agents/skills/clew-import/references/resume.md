# Resume an interrupted conversion

Read this contract before planning or executing a resume. It applies only to
step-A runs started by a checkpoint-enabled `digest_pdf.py`. Older interrupted
outputs without `checkpoint.json` are not adopted or migrated. Preserve them
and report the limitation. Completed historical bundles remain supported.

## Inspect and approve

Use the original PDF, destination, page selection, DPI, high-resolution OCR
option, token budget, review option, Azure endpoints/deployment, converter
scripts, Python interpreter and dependency versions. Resume checks the source SHA-256 and
retained copy, normalized page selection, effective configuration fingerprint,
runtime fingerprint and every committed output checksum. Missing/changed
artifacts, unexpected files, redirects, unknown reparse tags, incompatible
settings and an active same-filesystem process lock are blockers.

Do not guess missing options, change deployments, silently increase the token
budget, or bypass a fingerprint mismatch. Keep the original runtime available
until its pending digestions finish. A deployment name/endpoint fingerprint
cannot detect a provider changing the model behind that same deployment; do not
change deployment backing models during a pending run.

For example, for an interrupted default import:

```powershell
uv run --package clew-import --locked --no-sync --env-file .env python -B ".agents\skills\clew-import\scripts\plan_imports.py" "C:\courses\chapter.pdf" --resume --check-env
```

Repeat original non-default flags. For a custom destination, add
`--output "C:\digests\chapter"` to the planner; this option requires one explicit
PDF, not a directory scan. `--resume` on a directory plans only existing
checkpoint-enabled digestions and reports absent/nonresumable targets as
blocked. Without `--resume`, partial targets remain blocked. Completed matches
are still `already_converted`, never paid reprocessing.

The read-only plan classifies a compatible partial target as `resume`, exposes
its checkpoint SHA-256, completed page/model requests, failed returned
responses, uncertain requests and DI action, and emits the exact command with
`--resume --checkpoint-sha256 <hash>`. Its page-request range is a conservative
remaining-work bound after subtracting usable saved page calls; potentially
reusable received-but-not-yet-validated calls also reduce its lower bound. Figures,
repeated failed requests and SDK transport retries are additional.

Disclose the source, destination, unchanged settings, resource hosts, cached
work, remaining work and possible repeat charges. Obtain fresh approval for
that exact resume command. Original conversion approval, interruption, or
"continue" is not resume approval. Resume never grants deletion permission.
Recheck source/configuration and the approved checkpoint fingerprint immediately
before execution; any change requires a new plan. Do not require destination
absence for this explicitly approved mode.

## Execute and inspect completion

An illustrative command, with the hash returned by the current plan:

```powershell
uv run --package clew-import --locked --no-sync --env-file .env python ".agents\skills\clew-import\scripts\digest_pdf.py" "C:\courses\chapter.pdf" --output "C:\courses\chapter" --resume --checkpoint-sha256 "<approved checkpoint SHA-256>"
```

Standalone copies omit `--package clew-import` and use their local `scripts`
paths. A direct user-run `--resume` can omit the optional fingerprint; an agent
must use the plan-bound command. All original non-default flags must be repeated.

The converter replays deterministic orchestration/local checks, reuses committed
valid cloud responses, and continues at missing paid steps. Reuse reconstructs
figure choices, page candidates, independent judgments and the original
two-correction budget. It replays only selected prior-page mathematics to
restore MathJax macro context. It does not reconsider completed pages with new
model calls or reset attempt numbers. A completed checkpoint is a checksum-
verified no-op, including `needs_review`; it is not a way to clear findings.

DI layout and saved crops are reused. If analysis was submitted and its ID was
committed but the layout was not, resume polls that existing operation using
authenticated GET requests. An expired, failed or unavailable operation fails
explicitly without resubmitting the PDF. An attempted submission with neither
a committed operation ID nor saved layout is ambiguous and blocked; inspect
the original failure rather than automatically repeating analysis.

An OpenAI timeout/interruption with no committed response may repeat a billed
request; `store=False` prevents reliable remote recovery. A saved invalid,
incomplete or refused response remains a failure in its original invocation.
An explicitly approved later resume can retry that failed logical step once
in that invocation, preserving its previous full response. This is not a
guessed corrective attempt, an unlimited automatic loop, or a fresh budget.
Each further failure stops and requires a fresh decision.

Converter exits and completion checks remain 0 extracted, 2 completed-needs-
review, 1 failed and 130 interrupted. Verify the persisted manifest, document,
retained PDF and referenced evidence. Report all review issues and returned
usage. Returned usage includes prior and new saved responses exactly once,
including rejected responses; replayed requests add no usage. Unobserved
interrupted requests make the price estimate unavailable and are explicitly
counted rather than treated as free work.

## Checkpoint and synchronization limits

`checkpoint.json` schema 1 is separate from the completion manifest schema 3
and diagnostic `run.json` schema 1. It binds source/configuration/runtime,
tracks artifact hashes and pending local writes, records DI submission/ID,
and keeps a paid-call ledger. Full returned OpenAI responses also live in
immutable numbered `raw/checkpoints/response-NNNNNN.json` files; conventional
page/attempt/figure response paths still reference the selected evidence.
These files, generated artifacts and checkpoint stay together.

Local writes stage their expected checksum in the checkpoint before atomic
replacement. A resume can finish a verified interrupted local write without
repeating a cloud call. Incomplete temporary data is regenerated, not accepted
as a completed response; abandoned partial temporary files stay identified in
the checkpoint until their owning step is regenerated. Do not edit checkpoints
or evidence to force reuse. Progress-record replacement shares the converter's
bounded local Windows lock backoff: WinError 5/32/33, five waits of
0.1/0.2/0.4/0.8/1.6 seconds, without rewriting the temporary record or repeating
cloud calls. Other write errors and exhausted retries remain explicit failures.

The persistent `.digest.lock` file is an OS advisory lock, not a stale-file
marker. It releases automatically when the process exits or crashes. Do not
delete it as an unlock operation. It prevents cooperating processes using the
same filesystem from writing concurrently; it is **not** a distributed lock
across OneDrive replicas. Ensure the previous process is stopped on every
device and synchronization is complete before resuming elsewhere.
