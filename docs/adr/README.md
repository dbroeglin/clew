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
| [ADR-0002](0002-pdf-import-skill-and-project-runtime.md) | PDF Import skill and project-level Python runtime | Accepted; partially superseded by ADR-0003, ADR-0004, and ADR-0005 | Plan recursive PDF conversion into sibling bundles; subsequent records refine runtime ownership, tests and retention, and conservative transcription with leakage review. |
| [ADR-0003](0003-autonomous-portable-skills.md) | Autonomous, portable skills | Accepted; script-test ownership partially superseded by ADR-0004 | Self-contained runtime artifacts, skill-owned dependencies, a shared UV workspace, explicit integrations, and documentation integrity; script tests now live outside skills. |
| [ADR-0004](0004-faithful-multi-bundle-ingest.md) | Faithful multi-bundle ingest | Accepted | Confirmed contextual vault placement and agent-approved structuring through small deterministic tools; page-addressed retained sources, one removable output root, and repository-owned script tests. |
| [ADR-0005](0005-conservative-import-and-latex-leakage-review.md) | Conservative Import and LaTeX leakage review | Accepted | Partially supersede ADR-0002's pinned prompt and validation: minimal image-evidenced transcription and non-mutating review for known LaTeX commands in ordinary text. |
| [ADR-0006](0006-current-note-offline-html-generation.md) | Current-note offline HTML generation | Accepted | Topology-led chapter discovery and a small JSON layout feed offline rendering with HTML-first native templates, without Ingest validation or approval hashes. |
| [ADR-0007](0007-course-linked-question-enrichment.md) | Course-linked question enrichment | Accepted | Agent-authored anchored hints and supplied-answer explanations, local before/after preservation checks, and precise course links in Generate's side panel. |
| [ADR-0008](0008-exercise-unit-pipeline-contract.md) | Exercise-unit pipeline contract | Accepted | One note per exercise/correction unit, anchored internal questions/answers, scoped structuring review, preserved enrichment ownership, and exercise-based HTML grouping; historical handling is deferred. |
