# Learner-model contract

The authoritative learner-model 3.0.0 contract lives in the installed
[specification](../.agents/skills/learner-model/references/learner-model-spec.md),
[clarification gates](../.agents/skills/learner-model/references/clarification-gates.md),
and [operational skill](../.agents/skills/learner-model/SKILL.md).
Canonical package sources belong in
[clew-skills](https://github.com/francesco-kruk/clew-skills), not in a second
specification here.

The `course-content` and `learner-model` runtime skills are pinned to
`clew-skills` revision
`d4e0880642b0870857749978417cb9561487626a`. Restore the matching release with
APM 0.28.0 and `apm install --frozen`, retaining both `copilot` and
`agent-skills` targets.

Memory is one compact `model/learner.md` summary with exactly one
`<!-- clew-learning-memory: v1 -->` marker, dates, and ordinary source/evidence
links. Goals, Confirmed preferences, and Learning notes are recommended optional
headings, not mandatory schema sections. Meaningful sessions use
`model/sessions/YYYY-MM-DD-topic.md` with collision suffixes `-2`, and so on.
Store original attempts once and link them; artifacts are optional when useful.

Bare continuation or inspection is read-only. Only meaningful learning input,
decisions, or results justify updates. Configuration and status operations
neither read nor create memory; a path-only exchange asks for the learner's
goal. Corrections are direct, with a concise note when useful. Clarify ambiguous
forget, stop-use, and explicitly scoped local deletion requests.

No profile/index files, typed-record graph, evidence-ID machinery, overlays,
tombstone engine, numerical scores, automatic schedules, or domain taxonomy
are required or supported by this contract. Unknown existing models, including
the earlier advanced format, require an explicit migration decision.

Preserve learner ownership, attributable evidence, no trait labels, and bounded
retrieval. Ask before writing where reserved `model` or `artifacts` ownership is
uncertain. Skills are instructions, not an enforced backend.

Learner records are stored in an external local vault, but relevant bounded
context may be processed by hosted GitHub Copilot. Local storage is not
local-only inference. Local correction or deletion cannot erase hosted context
already sent; do not promise provider retention, training, deletion, encryption,
or complete network auditing.

Rationale is recorded in
[ADR-0004](adr/adr-0004-compact-learner-memory-and-hosted-processing.md), which
remains Proposed until explicit human lifecycle approval.
