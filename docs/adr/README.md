# Architecture decision records

Use this index to find decisions relevant to a task, then open the linked records
for their context and rationale. It is the starting point for both contributors
and AI agents; reading every ADR is not necessary.

Keep entries in ascending numeric order. Update this index whenever an ADR is
added or its status changes, including links between superseded and replacement
records. See [ADR-0000](0000-record-architecture-decisions.md) for conventions.

| ADR | Decision | Status | Summary |
| --- | --- | --- | --- |
| [ADR-0000](0000-record-architecture-decisions.md) | Record architecture decisions | Accepted | Use Markdown ADRs and a README index for progressive discovery by contributors and AI agents. |
| [ADR-0001](0001-document-processing-pipeline.md) | Document processing pipeline | Accepted | Separate Import, faithful Ingest, optional Enrich, and repeatable HTML Generate stages with persisted artifacts and Obsidian content. |
| [ADR-0002](0002-pdf-import-skill-and-project-runtime.md) | PDF Import skill and project-level Python runtime | Accepted; partially superseded by ADR-0003 and ADR-0004 | Plan recursive PDF conversion into sibling bundles; ADR-0003 refines runtime ownership and ADR-0004 refines tests and downstream retention. |
| [ADR-0003](0003-autonomous-portable-skills.md) | Autonomous, portable skills | Accepted; script-test ownership partially superseded by ADR-0004 | Self-contained runtime artifacts, skill-owned dependencies, a shared UV workspace, explicit integrations, and documentation integrity; script tests now live outside skills. |
| [ADR-0004](0004-faithful-multi-bundle-ingest.md) | Faithful multi-bundle ingest | Accepted | Confirmed contextual vault placement and agent-approved structuring through small deterministic tools; page-addressed retained sources, one removable output root, and repository-owned script tests. |
