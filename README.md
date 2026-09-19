# clew

Every learner in a classroom receives the same artifact. Teachers know this is wrong but cannot produce thirty versions of a workbook. Clew builds a persistent, evidence-based model of an individual learner — what they know, how they work best, where they consistently stumble — and re-renders authoritative course content into artifacts made for that learner: an explainer chunked for someone who loses the thread after two paragraphs, a diagram-first walkthrough for someone who does not think in prose, a practice set that targets the three misconceptions this learner actually holds. The learner drives it directly on a shared canvas where both they and the agent can work.

Every challenge is its own labyrinth. Clew takes its name from the ball of thread that guided Theseus through the maze. Rather than offering everyone the same map, it adapts to your challenges, your starting point, and what you discover along the way—helping you find a path that makes sense for you.

But the thread is not the hero. You are. Clew helps you see a way forward; it doesn’t walk the path for you. The choices, the effort, and the discoveries remain yours.

## Architecture decisions

[Architecture Decision Records](docs/adr/README.md) capture significant decisions,
their rationale, alternatives, and consequences. Start with the
[ADR template](docs/adr/template.md); proposed decisions require explicit human
approval before acceptance.

## Course reader extension

The first Clew UX surface is a
[GitHub Copilot App course-reader extension](.github/extensions/clew-course-reader/README.md).
It displays Markdown and KaTeX mathematics, follows top-level `previous` and
`next` frontmatter links, and lets selected passages be staged as chat-composer
attachments without automatically sending them. Its contents list shows the
current page's headings and can be collapsed. The session can open, navigate,
and refresh the reader. It is read-only and scoped to a chosen course within a vault;
it does not read or update private learner records.

Restore its pinned runtime dependencies with
`npm --prefix .github\extensions\clew-course-reader ci --ignore-scripts`, then
reload extensions in the App. The extension README covers opening a course,
the session action contract, and the included
[synthetic reader tour](examples/reader-vault/courses/reader-tour/hub.md).

## Agent skills

This repository uses [Microsoft APM](https://github.com/microsoft/apm) to manage
project-local agent skills, targeting GitHub Copilot. The `agent-skills` target
is also enabled to honor `course-content`'s declared target; both use the shared
`.agents/skills/` directory. Install APM (this setup was generated with version
0.28.0), then restore the pinned dependencies from the repository root:

```sh
apm install --frozen
```

| Source | Skills |
| --- | --- |
| [Anthropic](https://github.com/anthropics/skills) | `skill-creator` |
| [Kepano's Obsidian skills](https://github.com/kepano/obsidian-skills) | `defuddle`, `json-canvas`, `obsidian-bases`, `obsidian-cli`, `obsidian-markdown` |
| [GitHub Awesome Copilot](https://github.com/github/awesome-copilot) | `create-architectural-decision-record` |
| [Clew skills](https://github.com/francesco-kruk/clew-skills) | `course-content` |

`apm.yml` pins upstream commits; `apm.lock.yaml` records the resolved dependencies
and deployed file hashes. Skills and their bundled resources live in
`.agents/skills/`. Keep those files, the manifest, and the lockfile in version
control; `apm_modules/` is a generated cache and is gitignored.
Third-party license notices are preserved in `THIRD_PARTY_NOTICES.txt` and the
bundled skill licenses.

To change a dependency version, update its commit reference in `apm.yml` and run
`apm install` to regenerate the lockfile and deployed skills. Edit the upstream
dependency or its version rather than modifying generated skill files directly.
The skills provide agent instructions; external tools they use, such as Obsidian
or the Defuddle CLI, must be installed separately when needed.

When updating the ADR skill, compare its embedded template with
`docs/adr/template.md` and review the process guidance for compatibility.

### Course content

[`course-content`](.agents/skills/course-content/SKILL.md) 3.0.0 describes one
`clew/v1` course structure: course/chapter indexes, complete semantic Markdown
sections, original PDFs with provenance, and shared canonical concept notes.
[Proposed ADR-0001](docs/adr/adr-0001-unified-clew-content-structure.md) records
the rationale, alternatives and integration boundaries. Installing the skill
does not constitute acceptance of the ADR.

Reading requires an explicitly authorized external Obsidian vault and selected
course/note, not the repository itself. The gitignored `.clew.local.json`
declares `version: 1` and an absolute `vault` path. Ordinary course reads need
neither a running Obsidian app nor Python and must not access learner records.

Python helpers require Python 3.11 or newer through the consuming project's uv
environment. This repository does not yet have `pyproject.toml` or `uv.lock`;
APM installation alone does not configure that runtime. Project uv setup,
alignment of PDF producers such as `digest`, and updates to the learner
specification's older course-hub references remain separate integration work.

### First-party skills

[`learner-model`](.agents/skills/learner-model/SKILL.md) guides agents operating on
Clew's local learner records: recording evidence, maintaining concepts,
misconceptions, preferences and goals, scheduling reviews, resolving adaptation
decisions, and honoring inspection, correction and deletion requests. It follows
[`docs/LEARNER_MODEL.md`](docs/LEARNER_MODEL.md) and asks for clarification when
an unspecified storage or inference rule blocks a write. Private model data
requires local processing; a hosted agent must not read it through local tools.

This skill is maintained here, not generated from an APM dependency. Its
`evals/evals.json` contains three synthetic dry-run scenarios that do not access
real learner data. The skill provides operational instructions, not a model
storage engine or structural enforcement of the specification.
