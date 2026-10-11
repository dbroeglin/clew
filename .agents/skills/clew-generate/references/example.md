# Publish a current whole-document chapter

Suppose a current chapter contains `Course-course/course.md`,
`Exercise-sheet/sheet.md`, `Correction-solutions/solutions.md`, optional
`aides/`, and a `type: chapter` index. The sheet contains exercise scopes
`ex-1`, `ex-2` and anchored questions. The correction document has several
supplied correction units with `Exercise` / `Question` footer links.

Publish the chapter without enumerating notes or reading producer records:

```json
{
  "schema_version": 1,
  "title": "Sequences",
  "notes": ["C:/vault/Maths/Sequences"],
  "output": "C:/publications/sequences.html"
}
```

Inspect the folder/index first. If only the vault and chapter title are known,
bounded `inspect_notes.py <vault> --list-chapters` identifies matching chapters.
Read the current content, not only metadata.

The sheet creates two exercise views, not one sheet-sized exercise.
Its introductions, section context and review appendix remain once in source
order. Question and correction controls reuse the current anchored links.
Without aids there are no hint/method/explanation buttons; answers are not
invented for questions without supplied corrections.

For only exercise 1, add:

```json
"exercises": ["sheet#^ex-1"]
```

For selected questions:

```json
"exercises": ["sheet#^q-2", "sheet#^q-1"]
```

Both questions remain in exercise `sheet#^ex-1` in source order with shared
unit context. Another exercise in `sheet.md` remains a distinct unit.
Do not combine whole-document/unit selectors with overlapping child selectors.
Native Obsidian `#^ex-1` addresses the entry paragraph; Generate's exercise
selector deliberately expands that entry to its scoped publication view.

Normally answer and aid links require no question overrides. Explicit choices
can narrow supplied variants or existing course passages:

```json
"questions": {
  "sheet#^q-1": {
    "corrections": ["solutions#^r-1"],
    "courses": ["course#Geometric limits"]
  }
}
```

Select an answer or correction unit, never the whole multi-unit correction
document as one answer. Existing associations must still agree.

Question-addressed help notes contain anchored hints/explanations.
Explanations also name a specific supplied answer through `correction`
frontmatter. Their course links open precise passages in the side panel,
while answers reveal inline. `courses: []` hides full-course reading but
does not remove aid-linked excerpts.

Run `generate_html.py layout.json --check`, review scope and warnings, then
publish. The output parent already exists. Replacing that exact derived HTML
requires a user request and `--overwrite`. Sources remain unchanged. No
preparation/Enrich baseline validation, PDF conversion or model call occurs
inside the renderer.
