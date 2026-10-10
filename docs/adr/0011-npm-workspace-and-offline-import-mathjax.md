# ADR-0011: npm workspace and offline Import MathJax validation

- Status: Accepted
- Date: 2026-10-10

## Context

Import's LLM judge can miss malformed or unsupported mathematics. A successful
Markdown parse does not establish that formulas render. Generate already
includes offline MathJax 3.2.2, so an executable check must match that version
and its configured packages rather than accept arbitrary LaTeX.

The user requested browser-free formula checking in Import and a shared Node
installation at the repository root. Research of [npm workspaces](https://docs.npmjs.com/cli/v11/using-npm/workspaces/)
and [npm's hoisted installation](https://docs.npmjs.com/cli/v11/commands/npm-ci)
confirmed that root coordination, member dependency declarations, and one
combined lock are supported. Unlike UV's single environment, npm can nest
conflicting versions; a root-only tree is a checked property, not an
unconditional npm guarantee.

The user approved npm workspaces with root installation and a skill-local
dependency manifest, preserving [ADR-0003](0003-autonomous-portable-skills.md)'s
portable artifact and host-owned resolution contract. Root-only dependency
declarations would make a copied Import skill dependent on undocumented host
setup. A browser engine or dependency on Generate's runtime files would add
unnecessary coupling.

## Decision

Refine ADR-0003's runtime contract with an npm workspace. Add root
`package.json`, `package-lock.json`, and hoisted-install `.npmrc`; declare the
participating Import workspace and its pinned `mathjax-full` 3.2.2 dependency
in the skill's `package.json`. Node.js >=22 and npm >=10 are host-installed
runtimes on PATH, not binaries stored in the repository. Use one root
`npm ci --ignore-scripts --no-audit --no-fund` setup, and verify no workspace-local
dependency installation or nested version conflict is introduced. Do not run
member-local installs in Clew. A copied standalone skill uses its own manifest
and host-generated npm lock/environment. Normal discovery/conversion neither
installs packages nor edits host manifests/locks.

Refine [ADR-0010](0010-source-grounded-page-review-and-retries.md) by adding an
executed MathJax check before each candidate's judgment, including every
revision. Keep the current two-correction budget. The local helper is owned by
Import and uses Node, TeX/SVG processors, and `liteAdaptor`; no browser or
network is needed. Initialize once per candidate batch, typeset formulas to
SVG in memory, and capture TeX error callbacks and SVG error nodes. Use only
Generate's configured base/ams/newcommand/configmacros packages and
llbracket/rrbracket macros; do not silently autoload extra packages.

Parse math with publication-compatible CommonMark/tables/dollar-math rules,
excluding code, image alt text, and destinations. Retain exact formula text,
inline/display mode, IDs, and page-local block lines. Reject unsupported
active/external commands and unexpected controls before conversion. Replay
already-selected prior-page math to retain macro context, then check the current
candidate in a fresh process. Discarded drafts cannot contaminate subsequent
checks. Do not reconstruct omitted or out-of-scope content.

Executed math errors feed `local_format_issues` to the judge and corrective
transcriber. They trigger bounded corrections even if the judge reports no
discrepancy. Unresolved errors remain `needs_review`; `--no-page-review` still
checks the single candidate locally but makes no judge or corrective calls.
Missing/unusable Node or MathJax must fail preflight before output creation or
cloud submission. The planner runs a read-only smoke check and discloses setup.
Timeout (60 seconds per batch), malformed/inconsistent protocol, or unexpected
engine failure is an explicit import failure, not a formula pass or model retry.

Retain final `raw/pages/page-NNNN.math.json` and per-reviewed-candidate
`.attempt-AA.math.json` reports, with per-page/per-attempt `raw_math` references
and configuration `mathjax_version` in additive manifest schema 3 metadata.
Require new evidence when its configuration is present; accept and leave
historical completed bundles unchanged. Keep executable tests outside the skill,
including real MathJax cases, protocol/failure and correction-loop coverage,
workspace hoisting, and Generate compatibility checks. Update public setup,
runtime contracts, portable instructions, and workflow evaluations together.

## Consequences

- Node/npm is an explicit new Import setup requirement, with a shared root
  installation and no second package tree inside the workspace skill.
- Pinning MathJax 3.2.2 intentionally matches the current published renderer,
  despite upstream replacing `mathjax-full` with a MathJax 4 package. Upgrades
  must reconcile both configurations deliberately.
- Deterministic render errors complement source-grounded judgments and consume
  the existing correction budget, not unlimited retries or new cloud services.
- Formula renderability does not prove source fidelity, mathematical correctness,
  extraction completeness, cross-reference resolution, or final visual layout.
  Missing or unrecognized math delimiters may prevent formula extraction.
- Replaying selected previous math keeps source-order macro context without
  retaining rejected definitions, at the cost of repeating local work for later
  candidate pages.
- npm's hoisting can diverge from UV-style conflict behavior. Dependency changes
  require deliberate compatibility checks, not nested installs as a hidden fix.
