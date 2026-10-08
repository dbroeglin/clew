# Clew

Clew turns course PDFs into faithful Obsidian-compatible notes and an offline
interactive learning page. Four agent skills keep conversion, organization,
optional learning aids, and publication separate, so you can edit your notes
and publish them again without reconverting the PDFs.

## Get started

Clew's skills live in `.agents/skills/`. Open this repository in an agent that
loads project skills from that folder. If your agent uses a different skills
folder, copy the skill directories there; each one is self-contained. Ask for a
skill by name, as in the example prompts below; invocation syntax varies by
agent.

The skills require Python >=3.11 and [UV](https://docs.astral.sh/uv/). Install
the shared environment once from the repository root, or ask your agent to do
it:

```powershell
uv sync --all-packages --locked
```

PDF Import also requires Azure Document Intelligence and a
vision/structured-output Azure OpenAI or Foundry deployment. Create an untracked
`.env` at the repository root from
[`.agents/skills/clew-import/.env.example`](.agents/skills/clew-import/.env.example),
then sign in with Entra ID, for example with `az login`; API keys are not used.
Ingest, Enrich, and Generate need no Azure configuration or Obsidian
installation. See [runtime setup and configuration](docs/skills.md#runtime-and-portability)
for details and standalone use.

## Main workflow

**Import -> Ingest -> Enrich (optional) -> Generate**

| Stage | Call | Result |
| --- | --- | --- |
| Import | `clew-import` with a PDF or PDF directory | Retained PDFs, converted Markdown, and figures. |
| Ingest | `clew-ingest` with selected Import bundles and a vault | Faithful course, exercise, and supplied-correction notes. |
| Enrich (optional) | `clew-enrich` with a chapter and exercise scope | Progressive hints and supplied-answer explanations linked to the course. |
| Generate | `clew-generate` with a chapter and HTML output path | One offline interactive HTML file from the current notes. |

### 1. Import your PDFs

For example, `C:\courses\algebre` contains `cours.pdf`, `exercices.pdf`, and
`corriges.pdf`:

```text
Use clew-import to inspect C:\courses\algebre and plan imports for the PDFs
that still need conversion.
```

Review the selected PDFs, destinations, options, and any existing-output
conflicts. The skill waits for approval before conversion: **Import sends
document content to your configured Azure services and can incur charges.**
It reports extraction issues for review rather than silently correcting them.
Completed bundles normally sit beside each PDF, in a folder with the same stem.

### 2. Organize the imported material

Select the completed bundles reported by Import:

```text
Use clew-ingest to organize C:\courses\algebre\cours,
C:\courses\algebre\exercices, and C:\courses\algebre\corriges in the vault
C:\vault. Propose chapter placement and a faithful organization.
```

Confirm placement based on your vault's existing conventions, then review and
approve the concrete organization plan. Ingest creates one note per exercise
and per supplied correction, keeping all of its questions or answers together.
It preserves supplied text, formulas, and figures, keeps original sources
available, and does not invent missing exercises or answers. It creates a new
chapter rather than merging with or overwriting an existing one.

The remaining examples assume the agreed chapter is `C:\vault\Maths\algebre`;
this is an example, not a required vault hierarchy.

### 3. Add learning aids, if useful

Skip this stage to publish only the supplied material.

```text
Use clew-enrich on C:\vault\Maths\algebre for the questions in exercise 1.
Propose progressive hints and explanations of any supplied corrections,
linked to precise passages in the course.
```

Review the proposed aids and approve the editing scope. Enrich keeps generated
aid prose separate from source content, preserves existing aids, and never
invents a missing answer. This version adds hints and explanations; broader
enrichment such as new exercises is not implemented.

### 4. Publish the current notes

Choose an output file in an existing folder:

```text
Use clew-generate to publish C:\vault\Maths\algebre as
C:\publications\algebre.html.
```

Supply the chapter folder or its `index.md`; you do not need to enumerate its
notes. Before writing, the skill shows the selected material and output path,
and asks you only about genuinely ambiguous course or correction mappings.
The page includes current courses, expandable exercises, supplied
corrections, and any existing aids. It opens directly in a browser and renders
offline. Links to original PDFs remain external and can break if the HTML moves.

After editing notes or adding aids, call `clew-generate` again. Existing HTML
is not replaced unless you explicitly request replacement of that exact file.
Generate never changes your notes or reruns the earlier stages.

## Scope and documentation

You can start at Ingest with existing completed Import bundles. Enrich and
Generate also work on existing chapters whose notes follow the formats in the
[skills reference](docs/skills.md#course-linked-enrich); they don't need Ingest
output or the earlier skills. Course-only material and missing corrections are valid. Import currently
supports **PDF only**; TeX, Word, and PowerPoint are not implemented.

- [Skills reference](docs/skills.md): setup, configuration, artifact formats,
  limitations, direct commands, and development checks.
- [Architecture decisions](docs/adr/README.md): current decisions and their
  historical refinements.
- [Contributor and agent guidance](AGENTS.md): portability and documentation
  requirements.
