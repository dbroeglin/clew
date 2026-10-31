# ADR-0012: Publish prepared chapters through Git

- Status: Accepted
- Date: 2026-10-31

## Context

Converting PDFs costs paid cloud calls and time. A teacher who has prepared
and possibly enriched a chapter wants students to obtain the same chapter
without converting it again. GitHub and Azure DevOps repositories are already
available to teachers and students, and plain `git` works with both and with
their existing credential helpers or SSH keys.

A prepared chapter's private `.clew/preparation.json` holds the preparation
plan with absolute local paths and private baselines. These are not meant to
be shared, and an installed copy cannot reproduce them. Git may also rewrite
line endings or route files through LFS filters, which would silently change
published bytes.

## Decision

Add a thin `clew-export` skill with no scripts. It clones an existing,
teacher-created remote into scratch storage, runs Import's
`publish_chapter.py` into `Courses/<chapter-name>/`, and gets one approval
covering the files, sizes, destination and sharing consequences. It then
stages only that folder, commits, pushes without force, and verifies a fresh
clone. It uses plain `git` only: no `gh`/`az`, no repository or credential
management, and no credentials in URLs. Republishing removes and rewrites
only that chapter folder as a new commit. Several chapters may share one
repository.

`clew-import` owns the published format and both sides of it. A published
chapter contains the visible chapter files (including Enrich aids), a
`.gitattributes` that disables text, filter, ident and encoding conversion,
and a reduced `.clew/preparation.json` with `kind: published`. That record
holds the chapter ID and title, each document's ID, path and role, and every
published file's SHA-256. The private plan, baselines, local paths and hidden
entries are never published. Its `documents` shape stays compatible with
Enrich's reading of a completed chapter.

Import's step C clones a published repository into scratch storage and
installs one chapter into the vault with `install_chapter.py`. It uses the
same placement rules as preparation and one approval. It copies only recorded
files and validates the result.

For published records, default validation checks document identities, the
chapter index, portable names and unchanged recorded non-Markdown files, and
accepts Markdown edits and added aids. `--fidelity` means the exact published
snapshot: all recorded hashes and no extra files. Publishing requires a valid
chapter; installation requires a download that passes `--fidelity`. Import's
validator leaves `type: help` notes under `aides/` to Enrich.

Files over 100 MiB are refused and over 50 MiB need review; Git LFS is not
used. Installed chapters are not updated in place, and published history is
never rewritten.

## Consequences

Students install a teacher's chapter with only `git` and Import's local Python
environment, without conversion credentials or charges. Every published file
is readable by everyone with repository access, so the teacher confirms the
right to share and the repository's visibility at approval.

An installed chapter has no baselines, so source projection fidelity cannot
be rechecked on the student side; the teacher's published hashes are the
reference instead. The hashes detect accidental or careless changes but are
not a signature: anyone who can push to the repository can publish different
content. Updates require installing under a new folder name. Concurrent
publishers resolve conflicts by rerunning from a fresh clone.
