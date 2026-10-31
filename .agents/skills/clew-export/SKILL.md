---
name: clew-export
description: >-
  Publish one completed clew-import chapter from an Obsidian vault to an
  existing GitHub or Azure DevOps Git repository, so students can install it
  with clew-import from the Git URL without paying to reconvert PDFs. Uses
  clew-import's local publish script and plain git, with one approval before
  commit and push. Not PDF conversion, enrichment, HTML generation, repository
  creation, or student installation.
---

# Clew Export

Publish exactly one completed `clew-import` chapter (with any `clew-enrich`
aids) into a teacher-owned Git repository. Students then install it with
`clew-import`'s "install a published chapter from Git" step: no conversion
credentials, cloud calls, or tokens are spent on their side.

The repository holds one folder per chapter:

```text
Courses/<chapter-name>/
  .gitattributes            byte-exact checkout: no EOL, LFS or encoding filters
  .clew/preparation.json    published record: chapter, documents, file hashes
  index.md
  <document folders with notes, PDFs and figures>
  aides/                    optional Enrich help notes
```

Publishing copies only the chapter's visible files. It never publishes the
teacher's private `.clew/` preparation plan, baselines or local paths, or
hidden entries such as `.obsidian`. Republishing replaces only
`Courses/<chapter-name>` with a new commit. Other chapters and repository
files are untouched, and history is never rewritten or force-pushed.

Do not create, configure, or delete remote repositories, branches, pull
requests, permissions, or credentials. Do not edit the vault chapter, run
conversion, add aids, or install the chapter for students.

## Runtime

Explicit dependencies:

- The **`clew-import` skill**, installed with its Python environment. This
  skill has no scripts: it runs Import's `publish_chapter.py` and
  `validate_documents.py`, which own the published format.
- **git** on PATH, with access to the remote already configured by the teacher
  (Git Credential Manager, SSH keys, or another credential helper), and a git
  `user.name`/`user.email` identity.
- A host that can run shell commands and obtain user decisions.

It needs no `gh`, `az`, Obsidian plugin, cloud SDK, `.env`, or Azure
credentials. Commands below are for the Clew workspace. With a standalone
`clew-import` copy, run its scripts from that skill's directory, omitting
`--package clew-import` and using `scripts\...`. Use `--no-sync`; setting up
the environment is a separate host-approved step. PowerShell examples use
Windows paths; adapt quoting to the platform.

## 1. Collect inputs and check them without writing

Require:

- **Chapter folder:** a completed Import chapter in the vault. Never scan the
  vault for other chapters.
- **Remote URL:** an existing repository, which may be empty.
- **Branch:** optional; defaults to the repository's default branch.
- **Chapter name in the repository:** one visible, portable folder name;
  defaults to the chapter folder name.

Accept `https://` URLs only without embedded user information (`user@` or
`user:token@`), and SSH URLs such as `git@github.com:owner/repo.git` or
`git@ssh.dev.azure.com:v3/org/project/repo`. Azure DevOps "Clone" URLs often
start with `https://<org>@dev.azure.com/`: ask the teacher to remove the
`<org>@` part; the credential helper still authenticates. Never ask for,
print, store, or put a token in a URL, command, file, or git config. Always
pass `--` before the URL.

Clone into new host scratch storage, outside the vault and any other
repository. Add `--branch "<branch>"` before `--` only when the teacher named
an existing branch:

```powershell
git clone --no-recurse-submodules -c core.autocrlf=false -- "<url>" "C:\scratch\export-1\repo"
git -C "C:\scratch\export-1\repo" branch --show-current
git -C "C:\scratch\export-1\repo" config user.name
git -C "C:\scratch\export-1\repo" config user.email
```

An empty remote is fine: the clone's current branch is the branch to create.
If the clone fails (authentication, missing repository or branch, network), or
the identity is missing, report it and stop. The teacher fixes access or
identity outside this skill; never configure it for them.

Then preview the publication:

```powershell
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\publish_chapter.py" "C:\vault\Maths\Sequences" --output "C:\scratch\export-1\repo\Courses\Sequences" --check
```

The check validates the current chapter (any error blocks publication), lists
every file with its size, and reports `target: new` or `republish`. Republish
means the folder already holds this same chapter ID. A folder holding other
content is an error: choose another chapter name. Files over 50 MiB need review
and files over 100 MiB are errors, because Git hosts warn about or reject them;
Git LFS is not used.

## 2. Obtain one explicit approval

Show:

- the remote URL and branch;
- `Courses/<chapter-name>` and whether it is new or a republish;
- the complete file list, sizes and total;
- all findings;
- the commit message (`Publish <title>` or `Republish <title>`);
- the returned `publish_sha256`.

State plainly that every listed file, including the source PDFs, becomes
readable by everyone with access to the repository. The teacher must have the
right to share them and must check the repository's visibility. Obtain one
explicit approval for this exact publication; a general request to export is
not approval. Hard errors block approval.

## 3. Write, commit and push

For a republish only, first remove the previous copy from the scratch clone:

```powershell
git -C "C:\scratch\export-1\repo" rm -r -q -- "Courses/Sequences"
```

Then write the approved snapshot, stage only that folder, and push:

```powershell
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\publish_chapter.py" "C:\vault\Maths\Sequences" --output "C:\scratch\export-1\repo\Courses\Sequences" --publish-sha256 "<approved hash>"
git -C "C:\scratch\export-1\repo" add --force -- "Courses/Sequences"
git -C "C:\scratch\export-1\repo" diff --cached --name-only
git -C "C:\scratch\export-1\repo" diff --cached --quiet
git -C "C:\scratch\export-1\repo" commit -q -m "Publish Sequences"
git -C "C:\scratch\export-1\repo" push origin "HEAD:refs/heads/<branch>"
git -C "C:\scratch\export-1\repo" rev-parse HEAD
```

The write refuses a changed chapter or output (hash mismatch), an existing
output folder, and changed bytes, then validates the exact written copy. A
failure leaves only partial scratch output and nothing has been pushed: report
it and restart from a fresh clone. `--force` makes `git add` include files
that a repository `.gitignore` would skip; the folder holds only the files the
script just wrote. The staged names must all be under
`Courses/<chapter-name>/`; otherwise stop.

If `git diff --cached --quiet` exits 0, the published copy is already
identical: report "already up to date" and do not commit or push.

Never use `--force` on push, and never pull, merge, rebase, or amend. If the
push is rejected (someone else pushed, a protected branch, or a host size
limit), report the message and stop. A rerun starts from step 1 with a fresh
clone and needs a new approval.

## 4. Verify from the remote and report

Clone the pushed branch again into new scratch storage and validate the exact
published snapshot:

```powershell
git clone --depth 1 --no-recurse-submodules -c core.autocrlf=false --branch "<branch>" -- "<url>" "C:\scratch\export-1\verify"
uv run --package clew-import --locked --no-sync python -B ".agents\skills\clew-import\scripts\validate_documents.py" "C:\scratch\export-1\verify\Courses\Sequences" --fidelity
```

`--fidelity` on a published chapter requires every recorded file with its
exact hash and no extra files. Report the remote URL, branch, chapter path,
commit SHA, file count, total size, and verification status. Tell the teacher
that students install it by asking `clew-import` to install the course from
that URL, and which chapter name to pick if the repository holds several. The
scratch clones stay where they are: list them so the teacher can delete them.
This skill never deletes them automatically.

## Maintenance

Workflow evaluations are under `evals`. The published format, the publish
script and its tests belong to `clew-import`. Changes to this workflow must
keep the commands above consistent with that skill's scripts.
