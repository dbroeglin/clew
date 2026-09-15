# clew

Every learner in a classroom receives the same artifact. Teachers know this is wrong but cannot produce thirty versions of a workbook. Clew builds a persistent, evidence-based model of an individual learner — what they know, how they work best, where they consistently stumble — and re-renders authoritative course content into artifacts made for that learner: an explainer chunked for someone who loses the thread after two paragraphs, a diagram-first walkthrough for someone who does not think in prose, a practice set that targets the three misconceptions this learner actually holds. The learner drives it directly on a shared canvas where both they and the agent can work.

Every challenge is its own labyrinth. Clew takes its name from the ball of thread that guided Theseus through the maze. Rather than offering everyone the same map, it adapts to your challenges, your starting point, and what you discover along the way—helping you find a path that makes sense for you.

But the thread is not the hero. You are. Clew helps you see a way forward; it doesn’t walk the path for you. The choices, the effort, and the discoveries remain yours.

## Agent skills

This repository uses [Microsoft APM](https://github.com/microsoft/apm) to manage
project-local agent skills, targeting GitHub Copilot. Install APM (this setup was
generated with version 0.28.0), then restore the pinned dependencies from the
repository root:

```sh
apm install --frozen
```

| Source | Skills |
| --- | --- |
| [Anthropic](https://github.com/anthropics/skills) | `skill-creator` |
| [Kepano's Obsidian skills](https://github.com/kepano/obsidian-skills) | `defuddle`, `json-canvas`, `obsidian-bases`, `obsidian-cli`, `obsidian-markdown` |

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
