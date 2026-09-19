# Clew PDF provenance

The [Clew structure](clew-structure.md) is independent of PDF packaging.
`support/source-map.json` under the selected course is the authoritative
section-to-source mapping. `support/verification.json` records actual comparison
evidence. Neither is another reading hierarchy or a prerequisite for each lookup.

One course PDF or several chapter PDFs can map to the same stable section IDs
and semantic chunks. A section can span discontinuous pages or several PDFs.
Repackaging equivalent material changes mappings and generated PDF links,
not section IDs or concept identity. A new edition requires actual comparison,
not an assumed page offset. Preserve original bytes and compute their SHA-256.

## Source map

The machine-readable shape is `schemas/source-map.schema.json`.
All paths are **vault-relative** with `/` separators. Source and asset files
must be inside the selected course's `sources`/`assets` directories; mapped
sections are in its `sections` directory. Null source paths denote deliberately
omitted originals, never paths to the author's computer.

This synthetic fragment shows one section; a complete map lists every section
and source. Replace the hash placeholder with real evidence.

```json
{
  "schema": "clew-source-map/v1",
  "course_id": "course.mechanics",
  "sources": [
    {
      "id": "source.mechanics.motion",
      "filename": "Chapter 1.pdf",
      "path": "courses/mechanics/sources/motion.pdf",
      "sha256": "<SHA-256 of original bytes>",
      "page_count": 2,
      "citation": "Mechanics, chapter 1: Motion; author not supplied.",
      "edition": null,
      "omission_reason": null
    }
  ],
  "sections": [
    {
      "id": "section.mechanics.average-speed",
      "path": "courses/mechanics/sections/average-speed.md",
      "spans": [
        {
          "source_id": "source.mechanics.motion",
          "page_start": 2,
          "page_end": 2,
          "printed_pages": {"2": "12"}
        }
      ]
    }
  ]
}
```

Source IDs are stable identities distinct from note IDs. `filename` is the
original bibliographic filename; `path` is the delivered path. `citation`
preserves available attribution without inventing authorship. `edition` is
the supplied version or `null`. `page_count` is a positive integer;
`sha256` is 64 lowercase hexadecimal characters.

Each section has exactly one record matching its ID and path. Its nonempty
`spans` are in content order, not another course order. Physical pages are
one-based, inclusive and within the source's declared count. Optional
`printed_pages` maps physical page-number string keys within that span to
exact visible labels, including Roman numerals. Unknown labels are omitted;
never infer a fixed offset.

Optional `items` provides finer evidence. Each item has an actual section
heading or `^block-id` in `anchor`, nonempty `spans` contained within the
section's primary page coverage, and optionally an `asset_path`. The asset
must also be linked in that section's body. Use items to disambiguate shared
pages, figures, exercises or unresolved regions.

A span may have `rect: [x0, y0, x1, y1]`, finite coordinates in PDF points
from the top-left of the visible rotated page. Rectangles require one physical
page, nonnegative coordinates and positive area. The producer normalizes its
tool's coordinates and checks the actual page dimensions; the structural
validator does not render PDFs or independently measure their page boxes.

If both whole-course and chapter PDFs are kept, each section still has one
primary `spans` list. Optional `alternatives` contains objects with `spans`
and nonempty `equivalence_evidence` describing a real comparison. All source
IDs must be declared. Alternatives are equivalent representations, not extra
content, another sequence or permission to transcribe everything twice.

## Generated links and source inclusion

Generate section `source_refs` from primary spans: one quoted vault-relative
PDF `#page=N` wikilink per included physical page, deduplicated in first-occurrence
order. Generate index `source_refs` from the first relevant page of each included
primary source among descendants, in reading order. Display those links in the
note bodies. Body citations can additionally target specific source items.
Primary frontmatter references use plain page links, not viewer-specific
selection parameters. Body links can use native PDF viewer parameters.

If distribution is not authorized, omit the PDF, set `path: null` and a nonempty
`omission_reason`, but retain the original hash and page mapping. Generate no
links or embeds to omitted bytes; keep visible filename/page citations and the
limitation. `source_refs: []` is appropriate when every primary source was
intentionally omitted, not an assertion that the section has no sources.
Permission to distribute the transcription and extracted images also matters;
omitting a PDF does not confer those rights. The validator cannot establish
legal permission or recheck the bytes of an omitted source.

PDFs in the course must be declared in the source map. Ordinary figures and
fallback images must be reachable from section bodies, not hidden in reports.
Do not modify originals to insert annotations or backlinks. Use separate
personal notes or non-destructive viewer overlays.

## Fidelity and verification

The machine-readable report shape is `schemas/verification.schema.json`.
Every section has one `fidelity` value in both frontmatter and its report:

| Value | Meaning |
| --- | --- |
| `needs-review` | Comparison against current source/content is incomplete or stale. |
| `partial` | Known missing, unreadable, image-only or unresolved content, labelled in the body. |
| `verified` | All mapped content has been compared and preserved, with current persisted evidence. |

Known gaps take precedence: use `partial` while a fallback or missing region
remains, even if other regions also await review. A source figure preserved
as an image is not a gap; an untranscribed equation image is. A page citation,
link check or resolved image path alone cannot establish `verified`.
Keep source errors and label editorial observations rather than silently
correcting the source.

The report requires:

- `schema: "clew-verification/v1"`, the course ID and `source_map_sha256`.
- `sections`: exactly one record per section, with its ID, final
  `markdown_sha256`, `fidelity`, `checks` and `limitations`.
- `pages`: exactly one record per physical page of each source, with
  `source_id`, `page`, `status`, `section_ids` and `reason`.

Both hashes use 64 lowercase hexadecimal characters and refer to actual final
file bytes. Hash Markdown after navigation and fidelity metadata are finalized;
store the hash in the report, not inside the note. `checks` and `limitations`
are lists of nonempty strings, locating evidence/issues by source page or
section anchor. Verified sections require comparison evidence and no unresolved
limitations. Other states require an explanation of what is missing/unreviewed.

Page `status` is `mapped`, `excluded` or `unresolved`. Mapped section IDs agree
with primary/alternative spans. Excluded pages have no mapped sections and
explain deliberate exclusions such as blank pages or material outside the
conversion scope. Unresolved pages retain known assignments and explain the
coverage gap. `reason` may be `null` only for mapped pages.
A mapped page does not prove that every region, footnote or exercise survived.

Stale hashes, inconsistent records and broken mappings are structural errors,
even in draft validation. Honest `needs-review`/`partial` sections and unresolved
page coverage produce warnings by default and errors with `--strict`.
An intentionally omitted PDF remains a warning, not a strict-mode failure when
the transcription's evidence is otherwise complete.

On revisions, recheck affected content, mappings and links. Retain previous
comparisons only when their scope is demonstrably unchanged, recording that
scope in `checks`. Updating a hash or status is not itself a comparison.
Source-map page counts, stated checks, and equivalence claims are producer
evidence, not independent PDF inspection by the validator.
