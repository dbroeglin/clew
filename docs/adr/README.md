# Architecture decision records

Use this index to find decisions relevant to a task, then open the linked records
for their context and rationale. It is the starting point for both contributors
and AI agents; reading every ADR is not necessary.

Keep entries in ascending numeric order. Update this index whenever an ADR is
added or its status changes, including links between superseded and replacement
records. See [ADR-0000](0000-record-architecture-decisions.md) for conventions.

Accepted records can contain historical context or superseded clauses. Follow
their status qualifiers and refinement notes rather than treating every old
example or deferred item as current guidance.

For operating instructions, start with the [user workflow](../../README.md),
the [skills reference](../skills.md), or the portable skill's `SKILL.md`.

| ADR | Decision | Status | Summary |
| --- | --- | --- | --- |
| [ADR-0000](0000-record-architecture-decisions.md) | Record architecture decisions | Accepted | Use Markdown ADRs and a README index for progressive discovery by contributors and AI agents. |
| [ADR-0001](0001-document-processing-pipeline.md) | Document processing pipeline | Accepted | Separate Import, faithful Ingest, optional Enrich, and repeatable HTML Generate stages with persisted artifacts and Obsidian content; later ADRs refine each stage. |
| [ADR-0002](0002-pdf-import-skill-and-project-runtime.md) | PDF Import skill and project-level Python runtime | Accepted; partially superseded by [ADR-0003](0003-autonomous-portable-skills.md), [ADR-0004](0004-faithful-multi-bundle-ingest.md), [ADR-0005](0005-conservative-import-and-latex-leakage-review.md), and [ADR-0009](0009-direct-markdown-page-transcription.md); refined by [ADR-0010](0010-source-grounded-page-review-and-retries.md) | Recursive PDF planning, cloud/restart gates, and complete bundles remain accepted; successors replace runtime/template ownership, downstream retention/test ownership, pinned prompt/content-check restrictions, and the page-response envelope; ADR-0010 adds bounded in-run page review/correction. |
| [ADR-0003](0003-autonomous-portable-skills.md) | Autonomous, portable skills | Accepted; script-test ownership partially superseded by [ADR-0004](0004-faithful-multi-bundle-ingest.md); refined by [ADR-0011](0011-npm-workspace-and-offline-import-mathjax.md) | Self-contained runtime artifacts, skill-owned dependencies, shared UV/npm resolution, explicit integrations, and documentation integrity; executable tests live outside skills. |
| [ADR-0004](0004-faithful-multi-bundle-ingest.md) | Faithful multi-bundle ingest | Accepted | Confirmed placement, approved structuring, page-addressed retained source subsets, one owned root, and repository-owned tests; later Enrich edits do not alter snapshot validation. |
| [ADR-0005](0005-conservative-import-and-latex-leakage-review.md) | Conservative Import and LaTeX leakage review | Accepted; partially superseded by [ADR-0010](0010-source-grounded-page-review-and-retries.md) | Minimal image-evidenced transcription and non-mutating LaTeX leakage review remain; ADR-0009 refines page responses and ADR-0010 replaces the prohibition on in-run corrective retries. |
| [ADR-0006](0006-current-note-offline-html-generation.md) | Current-note offline HTML generation | Accepted | Topology-led discovery and a small layout feed offline HTML-first rendering without earlier-stage validators or approval hashes; [ADR-0007](0007-course-linked-question-enrichment.md) adds supplied-answer explanations and aid-to-course panel links. |
| [ADR-0007](0007-course-linked-question-enrichment.md) | Course-linked question enrichment | Accepted | Agent-authored anchored hints and supplied-answer explanations, local before/after preservation checks, and precise course links in Generate; existing aids and missing answers stay unchanged. |
| [ADR-0008](0008-exercise-unit-pipeline-contract.md) | Exercise-unit pipeline contract | Accepted | One note per exercise/correction unit, anchored internal questions/answers, scoped structuring review, preserved enrichment ownership, and exercise-based HTML grouping; refines [ADR-0004](0004-faithful-multi-bundle-ingest.md), [ADR-0006](0006-current-note-offline-html-generation.md), and [ADR-0007](0007-course-linked-question-enrichment.md); historical handling is deferred. |
| [ADR-0009](0009-direct-markdown-page-transcription.md) | Direct Markdown page transcription | Accepted; refined by [ADR-0010](0010-source-grounded-page-review-and-retries.md) | Plain Markdown pages without a fixes/confidence envelope and strict JSON figure classification remain; ADR-0010 adds independent judging and retained corrective candidates without inner JSON page decoding. |
| [ADR-0010](0010-source-grounded-page-review-and-retries.md) | Source-grounded page review and bounded retries | Accepted; refined by [ADR-0011](0011-npm-workspace-and-offline-import-mathjax.md) | Default fresh same-deployment judging, at most two corrective attempts, retained evidence and unresolved findings; ADR-0011 adds executed math errors to the same budget. Existing completed imports and failed-import restart gates remain unchanged. |
| [ADR-0011](0011-npm-workspace-and-offline-import-mathjax.md) | npm workspace and offline Import MathJax validation | Accepted | Root npm manifest/lock and hoisted installation, portable skill dependency declarations, browser-free MathJax candidate checks, retained reports, early preflight, and renderer errors feeding the existing corrective budget. |
