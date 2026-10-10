# ADR-0000: Record architecture decisions

- Status: Accepted
- Date: 2026-10-04

## Context

Contributors and agents need discoverable, coherent design decisions rather
than a chain of historical exceptions. Git already preserves prior states.

## Decision

Keep significant decisions under `docs/adr/` with stable four-digit identifiers,
descriptive filenames, status/date and Context / Decision / Consequences.
Discover them through `docs/adr/README.md`; read only relevant records.

Revise relevant existing records **in place** when a decision changes, as a
coherent current design. Do not append supersession chains or preserve
contradictory historical commands in operative records. New independent
decisions can receive a new sequential identifier. Never reuse identifiers.
Update the index and all affected records/links in the same change.
Runtime instructions belong in portable skills; ADRs explain decisions.

## Consequences

The current index describes one consistent system. Prior rationale is available
in Git history. Documentation coherence remains part of task completion.
