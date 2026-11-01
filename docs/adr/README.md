# Architecture decision records

Use this index to discover the relevant decisions, then read only those records.
Records describe the current coherent design and are revised in place; Git
history retains earlier states. Update this index with every record change.
See [ADR-0000](0000-record-architecture-decisions.md) for conventions.
Runtime instructions live in the [skills reference](../skills.md) and portable
skills, not in ADRs.

| ADR | Decision | Status | Summary |
| --- | --- | --- | --- |
| [ADR-0000](0000-record-architecture-decisions.md) | Record architecture decisions | Accepted | Stable IDs, progressive discovery and in-place revisions. |
| [ADR-0001](0001-document-processing-pipeline.md) | Document processing pipeline | Accepted | Whole-document Import, optional Enrich aids and current-unit offline publication. |
| [ADR-0002](0002-pdf-import-skill-and-project-runtime.md) | PDF Import and project runtime | Accepted | Pinned conversion, retained bundles, version-bound future checkpoints and explicit cloud/resume/restart gates. |
| [ADR-0003](0003-autonomous-portable-skills.md) | Autonomous portable skills | Accepted | Skill-owned runtime intent, host-owned resolution, external tests and documentation integrity. |
| [ADR-0004](0004-faithful-multi-bundle-ingest.md) | Whole-document preparation | Accepted | One note per PDF, typed edits, compact provenance, Obsidian comments, final review appendices and pedantic validation. |
| [ADR-0005](0005-conservative-import-and-latex-leakage-review.md) | Conservative transcription and leakage review | Accepted | Image-evidenced transcription and non-mutating review. |
| [ADR-0006](0006-current-note-offline-html-generation.md) | Current-note offline HTML | Accepted | Current document-unit publication without producer records; offline HTML-first views. |
| [ADR-0007](0007-course-linked-question-enrichment.md) | Course-linked question enrichment | Accepted | Scratch-first, exact-approved aids with real navigation, semantic review and additive preservation. |
| [ADR-0008](0008-exercise-unit-pipeline-contract.md) | Document-internal learning units | Accepted | Heading navigation, stable entries, scoped ownership and compact relationship/PDF callout footers. |
| [ADR-0009](0009-direct-markdown-page-transcription.md) | Direct Markdown page transcription | Accepted | Direct page text, strict figure JSON and retained raw responses. |
| [ADR-0010](0010-source-grounded-page-review-and-retries.md) | Source-grounded review and retries | Accepted | High-effort review, resume-preserved correction bounds, retained evidence and usage-based cost estimates. |
| [ADR-0011](0011-npm-workspace-and-offline-import-mathjax.md) | npm workspace and offline MathJax | Accepted | Hoisted root setup, skill-local declarations and browser-free candidate checks. |
| [ADR-0012](0012-canvas-live-reader-and-activity-capture.md) | Canvas live reader and activity capture | Accepted | Copilot App canvas over Generate data mode, vault activity record, digest/ask tutor bridge and guarded tutor agent. |
