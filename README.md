# clew

Every learner in a classroom receives the same artifact. Teachers know this is wrong but cannot produce thirty versions of a workbook. Clew builds a persistent, evidence-based model of an individual learner — what they know, how they work best, where they consistently stumble — and re-renders authoritative course content into artifacts made for that learner: an explainer chunked for someone who loses the thread after two paragraphs, a diagram-first walkthrough for someone who does not think in prose, a practice set that targets the three misconceptions this learner actually holds. The learner drives it directly on a shared canvas where both they and the agent can work.

Every challenge is its own labyrinth. Clew takes its name from the ball of thread that guided Theseus through the maze. Rather than offering everyone the same map, it adapts to your challenges, your starting point, and what you discover along the way—helping you find a path that makes sense for you.

But the thread is not the hero. You are. Clew helps you see a way forward; it doesn’t walk the path for you. The choices, the effort, and the discoveries remain yours.

## Architecture decisions

[Architecture Decision Records](docs/adr/README.md) capture significant decisions,
their rationale, alternatives, and consequences. Start with the
[ADR template](docs/adr/template.md); proposed decisions require explicit human
approval before acceptance.

## Learner vault

Learner records and personal artifacts live in an explicitly selected external
vault, never in this repository clone. Configure the absolute path of an
existing vault with the CLI (recommended):

```powershell
python -m src.vault.cli configure --vault "C:\Users\Student\Documents\My Learning Vault"
python -m src.vault.cli status
```

This writes `.clew.local.json` in the repository root. Its complete schema is:

```json
{
  "version": 1,
  "vault": "<absolute path to an existing vault>"
}
```

The `version` must be the number `1`. The `vault` must be an absolute path to
an existing directory outside this repository. No additional properties are
accepted. For example:

```json
{
  "version": 1,
  "vault": "C:\\Users\\Student\\Documents\\My Learning Vault"
}
```

```json
{
  "version": 1,
  "vault": "/home/student/Documents/My Learning Vault"
}
```

On Windows, JSON requires each backslash to be escaped as `\\`.

To create the file manually, copy
[`.clew.local.example.json`](.clew.local.example.json) to `.clew.local.json`,
replace the `REPLACE_WITH_...` placeholder with the absolute path appropriate
for your operating system, then validate it:

```powershell
Copy-Item .clew.local.example.json .clew.local.json
python -m src.vault.cli status
```

The local file is ignored by Git. Configuration does not create a vault,
course, learner record, or artifact. The CLI additionally checks Git tracking
metadata and reports reserved `model` and `artifacts` names without claiming
ownership. `configure` adds private-path ignore rules to a version-controlled
vault; `status` is read-only. Ignore rules do not untrack, erase, or encrypt
existing content.

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
| [Clew skills](https://github.com/francesco-kruk/clew-skills) | `course-content`, `learner-model` |

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
environment. The [project Python setup](#python-tools) now supplies the ingestion
runtime; APM installation alone does not install Python packages. Additional
course-validator requirements remain declared in the
[installed skill](.agents/skills/course-content/requirements.txt) and are not
added by the ingestion setup. Packaging the intermediate PDF digest as `clew/v1`
course sections remains separate integration work.

### First-party skills

[`learner-model`](.agents/skills/learner-model/SKILL.md) 3.0.0 keeps compact,
evidence-grounded continuity in `model/learner.md`, meaningful dated session
notes, and optional artifacts. Bare continuation and inspection are read-only.
It does not create typed learner graphs, numerical mastery scores, automatic
schedules, or a tombstone engine. Unknown earlier formats require an explicit
migration decision. See the
[learner-model contract](docs/LEARNER_MODEL.md) and
[Proposed ADR-0004](docs/adr/adr-0004-compact-learner-memory-and-hosted-processing.md).

Learner files remain local and portable, but bounded task-relevant contents can
enter hosted GitHub Copilot/model processing. Local storage is not local-only
inference, and local correction or deletion cannot erase context already sent
to a host. Never bulk-upload learner memory or promise provider retention,
training, deletion, encryption, or complete network auditing.

[`ingestion`](.agents/skills/ingestion/SKILL.md) guides standalone PDF digestion:
Document Intelligence Markdown and JSON, OpenAI page-image verification of text
and formulas, and clean instructional figure extraction without Catalyst.
It is also maintained here rather than generated by APM. It does not organize
courses or update learner records. The model returns authoritative final
Markdown and informational fixes/confidence, which Python displays without
content checks. A format-only Markdown parse gates publication; it does not
rewrite the content or verify the mathematics. One document is assembled after
the whole requested pass; splitting into course files comes later. See the
[PDF ingestion guide](docs/PDF_INGESTION.md) for Azure configuration, the output
contract, and quality-review limits.

## Python tools

The standalone tools share a [UV](https://docs.astral.sh/uv/) environment.
`pyproject.toml` declares dependencies using public PyPI, separately from the
APM-managed agent-skill dependencies. **Portable lockfile generation is pending:**
the implementation host can reach its configured mirror but not public PyPI's
download host. An existing mirror-backed lockfile has been preserved rather
than replaced locally; it is not included in this change and does not include
the newly added parser dependencies. No portable `uv.lock` is committed here.
The local environment has those dependencies for `uv run --no-sync`.
On a machine with public PyPI access, regenerate and review `uv.lock` before
committing it and using the locked commands:

```powershell
uv lock
uv sync --locked
uv run --locked python scripts\digest_pdf.py --help
```

Configure the endpoints in a local `.env` using `.env.example`, then ingest an
authorized PDF into a new directory:

```powershell
uv run --locked --env-file .env python scripts\digest_pdf.py course.pdf --output digests\course --pages 1-3
```

Omit `--pages` for the complete document. Generated digests and local credentials
are not committed. Course-content integration is intentionally deferred.
