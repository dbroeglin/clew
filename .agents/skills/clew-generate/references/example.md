# A small publication

For an ordinary Ingest chapter, there is no need to list its individual notes:

```json
{
  "schema_version": 1,
  "title": "Revision d'algebre",
  "notes": ["C:/vault/courses/PT/maths/algebre"],
  "output": "C:/publications/algebre.html"
}
```

`inspect_notes.py <chapter>` discovers the current course, exercises,
corrections, optional aids, and their existing links/order. If only the vault
and course name are known, `inspect_notes.py <vault> --list-chapters` helps the
skill identify the matching chapter without asking for note filenames.
Unresolved semantic mappings still belong to the skill, not the discovery script.

Select current course, exercise, and correction notes. Suppose the exercise has
two anchored question callouts and the correction already links its answers
through `question::` fields. Only the question-specific course excerpts need a
layout choice:

```json
{
  "schema_version": 1,
  "title": "Revision d'algebre",
  "notes": ["C:/vault/cours.md", "C:/vault/exercice.md", "C:/vault/corrige.md"],
  "output": "C:/publications/algebre.html",
  "questions": {
    "exercice#^q-1": {"courses": ["cours#Sous-espace vectoriel"]},
    "exercice#^q-2": {"courses": ["cours#Somme directe"]}
  }
}
```

Role defaults use the current note frontmatter. Without it, supply `courses`
and `exercises` arrays explicitly. The generator uses existing answer links;
there is no need to copy correction prose into JSON.

Run `generate_html.py layout.json --check`, review selection and warnings,
then publish. Both questions have correction controls; neither has a method or
hint button without selected existing help. Adding a help note to `notes`
enables its matching aids on the next run.

The output parent must already exist. A repeated publication defaults to a new
filename; replacing this exact derived HTML uses separately requested
`--overwrite`. Current note edits are read directly. No hash comparison,
Ingest validation, PDF conversion, or model call happens during rendering.
