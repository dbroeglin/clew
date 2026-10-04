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
| [ADR-0002](0002-pdf-import-skill-and-project-runtime.md) | PDF Import skill and project-level Python runtime | Accepted | Plan recursive PDF conversion into sibling bundles using the existing converter, project-level UV configuration, retained originals, and explicitly approved failed-run cleanup and retries. |
