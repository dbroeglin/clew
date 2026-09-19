# Validating the Clew structure

Use Python 3.11 or newer through the **consuming Clew project's uv environment**,
not a skill-local project, standalone venv or global interpreter. The project
root and its `pyproject.toml`/`uv.lock` are separate from the external vault.
Resolve that project explicitly from the task context.
If it does not yet have uv project configuration, ask to establish that in Clew;
do not silently create a separate project inside the skill or vault.

Only when a required helper dependency is missing, add the declared requirements
(PyYAML and jsonschema) to that authorized project. This changes its manifest
and lockfile; obtain authorization if those changes are not already in scope:

```powershell
uv add --project "<Clew project>" --requirements "<installed course-content>\requirements.txt"
```

Preserve existing project constraints and surface resolution conflicts.
Do not use `pip`, create a skill-owned environment, or use `uv --with` to bypass
the project. Every subsequent Python command uses `uv run --project`:

```powershell
uv run --project "<Clew project>" python "<installed course-content>\scripts\validate_clew.py" --vault "C:\LearningVault" --course mechanics
uv run --project "<Clew project>" python "<installed course-content>\scripts\validate_clew.py" --vault "C:\LearningVault" --course mechanics --strict
```

The validator is read-only, does not discover a vault, run Obsidian, fetch URLs,
render PDFs, repair content or migrate other formats.

`--vault` is an explicit authorized vault root. `--course` is the single
lowercase kebab-case directory key under `courses`, not a path or title.
There are no package/catalog inputs or alternate format switches.

## Scope and outcomes

The validator inventories the selected course, reads its course/chapter/section
notes and follows explicitly linked shared concepts, including their concept
relationships. It does not scan the whole concept library or unrelated courses.
Explicit cross-course note targets are checked for schema, identity, existence
and requested anchors only. Their whole course and provenance are not
recursively validated; those dependencies are reported separately. Running the
helper authorizes these bounded content reads, not access to learner data.

It checks:

- Fixed layout, current schemas, unique identities in the checked scope, exact
  case, regular files, safe paths and no symlink/reparse traversal.
- The complete course/chapter/section tree, parent/course references, contents
  order and reciprocal section navigation across chapters.
- Shared canonical definitions, evidence/relationship target kinds, visible
  navigation, real headings/blocks, body assets and prerequisite cycles.
- Source-map membership and page bounds, primary PDF links, source/Markdown/map
  hashes, report coverage, fidelity consistency and optional item/alternate
  mappings.

Sections exceeding the 1,200-word guideline produce a review warning, not an
automatic split or strict-mode failure. Whole PDF files are hashed as streams,
not cached in memory or extracted as text.

Structural errors fail in both modes. Structurally sound `needs-review` or
`partial` sections and unresolved source-page coverage are warnings by default;
`--strict` makes these errors. Intentionally omitted originals and bounded
external-course dependencies remain warnings in both modes. Strict validation
is not legal approval, proof of source correctness, live Obsidian testing or an
independent visual comparison. Source page counts and comparison records are
producer assertions; actual hashes and declared bounds are checked.

Stdout is exactly one JSON object:

```json
{
  "schema": "clew-validation/v1",
  "ok": true,
  "strict": false,
  "course": "courses/mechanics",
  "errors": [],
  "warnings": [
    {
      "code": "fidelity",
      "path": "courses/mechanics/sections/average-speed.md",
      "message": "Section is needs-review."
    }
  ],
  "scope": {
    "concepts": ["concepts/physics-average-speed.md"],
    "external_notes": []
  }
}
```

Diagnostics always have `code`, `path` and `message`; do not depend on message
wording or ordering. Exit status is 0 for success (including draft warnings),
1 for validation/dependency/I/O failures, and 2 for CLI syntax errors.
No failure is returned as success. Missing dependencies produce a diagnostic
with installation guidance rather than an import traceback.

Python callers can load `scripts/validate_clew.py` by its installed path and call
`validate_course(vault_dir, course, strict=False)`. It returns the same report
without printing or exiting. `vault_dir` accepts a string or `pathlib.Path`;
`course` is the directory key and `strict` is a boolean.

Changes to shared concept definitions can affect other courses. Validate those
courses explicitly too; a scoped result does not claim vault-wide uniqueness
or validity. File checks cannot guarantee transactional reads under concurrent
edits or replace operating-system access controls.
