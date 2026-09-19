# The Clew course structure

Clew uses one course format, designed for Obsidian and efficient agent reading.
Every course, chapter, section and concept note declares `schema: clew/v1`.
There are no alternative authoring modes, compatibility readers or migrations
in this development iteration. The schemas in `../schemas/` and this contract
describe the same format.

## Fixed vault layout

```text
<vault>\
  courses\
    mechanics\
      course.md
      chapters\
        motion.md
        forces.md
      sections\
        distance-and-time.md
        average-speed.md
        forces.md
      sources\
        motion.pdf
        forces.pdf
      assets\
        distance-diagram.png
      support\
        source-map.json
        verification.json
  concepts\
    math-ratios.md
    physics-average-speed.md
```

`courses\<course>\course.md` is the sole course entry point. The course
directory name is a stable lowercase kebab-case key, not a changing title.
Chapter, section and concept Markdown files live directly in the directories
shown. `sources` contains original PDFs; `assets` contains needed images.
Empty asset directories are unnecessary. `support` contains the two named
JSON records. Raw extraction, tools, caches and personal work stay outside
the course directory. Native Obsidian views can be maintained elsewhere in
the vault; they are not another course representation.

Concepts belong to the shared `concepts` directory, not to individual courses.
Each shared note owns its canonical short definition and links to supporting
course sections. Do not create duplicate concept notes for each course.
Reuse an existing concept only after verifying identity and meaning; matching
titles alone do not establish equivalence.

Keep source PDFs unchanged. A whole-course PDF and separate chapter PDFs can
map to exactly the same sections. PDF boundaries never determine the Markdown
hierarchy. [Provenance](provenance.md) is a separate mapping, not a reading order.

## Identities, properties and links

All four note kinds require these flat YAML properties:

| Property | Meaning |
| --- | --- |
| `schema` | Exact string `clew/v1`. |
| `id` | Stable identity, using `[a-z0-9]+(?:[.-][a-z0-9]+)*`. |
| `kind` | `course`, `chapter`, `section` or `concept`. |
| `title` | Human-readable title. |
| `summary` | One short sentence for retrieval, not a substitute for the content. |

Use identities such as `course.mechanics`, `section.mechanics.average-speed`
and `concept.physics.average-speed`. Shared concept IDs are not course-scoped
or learner identities. IDs must remain unique within the content vault.
Renaming/reordering notes or repackaging PDFs must not change their IDs.
Changing concept meaning, splitting or merging content requires an explicit
author decision and reconciliation of affected links; do not silently reuse IDs.

Use safe filenames without device names, trailing spaces/periods or characters
that collide with links. Check collisions case-insensitively. All non-fragment
local links are **vault-relative**, starting with `courses/` or `concepts/`.
Use `/` in serialized links and JSON paths, including on Windows:

```markdown
[[courses/mechanics/sections/average-speed]]
[[courses/mechanics/sources/motion.pdf#page=2]]
[[concepts/physics-average-speed]]
```

No bare-basename search, course-relative paths, absolute paths, traversal or
vault-prefix guessing is part of this format. Ordinary Markdown link syntax
can also express these same vault-relative targets in Obsidian. Whole-note
links may omit `.md`; other file extensions are required. Body aliases and
actual heading/block references are supported. Metadata links have no aliases.
Structural and concept-relationship links target whole notes; concept `evidence`
may target exact section headings/blocks. Local paths cannot escape the content
directories through symlinks or filesystem aliases. External URLs are citations,
not permission to fetch or upload anything.

Lists remain lists even with one item. Optional `aliases`, `tags` and
`cssclasses` are lists of strings. Course domain lists and section/concept
`domains` preserve supplied classifications only. Omitted relationship fields
mean unclassified; `[]` means reviewed and none declared. Do not infer domains,
concepts or prerequisites from a title. Unknown properties/versions are not
silently accepted as another supported format.

## Course and chapter indexes

Course `children` is the authoritative ordered list of chapter links:

```yaml
---
schema: clew/v1
id: course.mechanics
kind: course
title: Mechanics
summary: Motion and forces with worked examples and practice.
children:
  - "[[courses/mechanics/chapters/motion]]"
  - "[[courses/mechanics/chapters/forces]]"
source_refs:
  - "[[courses/mechanics/sources/motion.pdf#page=1]]"
  - "[[courses/mechanics/sources/forces.pdf#page=1]]"
---
```

Each chapter has its course link, the same link as `parent`, and an ordered
list of section `children`:

```yaml
---
schema: clew/v1
id: chapter.mechanics.motion
kind: chapter
title: Motion
summary: Distance, elapsed time and average speed.
course: "[[courses/mechanics/course]]"
parent: "[[courses/mechanics/course]]"
children:
  - "[[courses/mechanics/sections/distance-and-time]]"
  - "[[courses/mechanics/sections/average-speed]]"
source_refs:
  - "[[courses/mechanics/sources/motion.pdf#page=1]]"
---
```

Both index bodies have one title heading and a `## Contents` section containing
a numbered list. The first link in each item targets its child, in exactly the
frontmatter order; follow it with the child's short summary. This materialized
view lets agents shortlist sections without reading every body. Chapter
indexes visibly link back to the course.

Both kinds require `source_refs`: generated PDF entry points for humans, the
first relevant page per included primary source in reading order. Display
these links in the body, labelled as originals. An intentionally omitted PDF
instead has a visible filename/page citation and inclusion limitation.

Do not put full chapter transcriptions into indexes or maintain a competing
index, `order` property or personalized reading sequence in the course.

## Complete section notes

```yaml
---
schema: clew/v1
id: section.mechanics.average-speed
kind: section
title: Average speed
summary: Calculates average speed from distance travelled and elapsed time.
course: "[[courses/mechanics/course]]"
parent: "[[courses/mechanics/chapters/motion]]"
previous: "[[courses/mechanics/sections/distance-and-time]]"
next: "[[courses/mechanics/sections/forces]]"
teaches:
  - "[[concepts/physics-average-speed]]"
prerequisites:
  - "[[concepts/math-ratios]]"
source_refs:
  - "[[courses/mechanics/sources/motion.pdf#page=2]]"
fidelity: needs-review
---
```

In addition to common properties, every section requires `course`, `parent`,
`previous`, `next`, `source_refs` and `fidelity`. Flatten course/chapter
`children` to derive reciprocal previous/next links **across chapter boundaries**.
Only the first `previous` and last `next` are `null`. Every chapter/section
appears exactly once in the hierarchy, with matching parent/course links.

A section contains the complete source-faithful explanation or activity:
assumptions, notation, units, examples, exercises and subparts, supplied answers,
footnotes, figures and citations. Aim for **400-1,200 words**, but never truncate,
pad or break a proof, worked example, table or exercise merely to meet a size
target. Use semantic headings, not PDF page breaks. Short definitions and longer
inseparable activities are valid exceptions.

Retain original section/example/exercise identifiers in headings. Include front
matter and appendices under source-grounded chapter groupings; ask when grouping
is ambiguous rather than inventing a textbook hierarchy. Preserve supplied
answer placement and link separate answers/exercises both ways. Do not invent
missing answers or put answers in retrieval summaries.

The body has one title heading, visible course/parent/previous/next links,
and its PDF source links. Keep finer page/region citations near their content,
with physical page numbers and known printed labels distinguished. Rendered
PDFs and transclusions are views, not replacements for actual Markdown text.
Verified mathematics remains editable; ordinary figures remain captioned
assets. Label unreadable/image-only fallback regions instead of guessing.

## Shared concepts

```yaml
---
schema: clew/v1
id: concept.physics.average-speed
kind: concept
title: Average speed
summary: A distance-to-time ratio, distinct from average velocity.
evidence:
  - "[[courses/mechanics/sections/average-speed]]"
prerequisites:
  - "[[concepts/math-ratios]]"
---
```

A shared concept has no owning `course`, parent, children or sequence links.
It requires a nonempty `evidence` list of supporting section links. Its body
has one title heading and `## Definition` with the canonical short definition
itself, not just an embed or a pointer. A separate `## Evidence` section shows
the supporting section links; keep relationship explanations outside the
canonical definition too. Detailed course explanations and exercises remain
in section notes.

| Relationship | Allowed on | Meaning |
| --- | --- | --- |
| `teaches` | Section | Concepts this section introduces or develops. |
| `prerequisites` | Section or concept | Concepts needed to understand this content. |
| `similar` | Concept | Concepts worth comparing, not identity/equivalence claims. |
| `related` | Section or concept | Another explained, useful conceptual connection. |
| `evidence` | Concept | Source sections grounding this note's canonical definition. |

Relationship lists target shared concept notes. Explain each asserted
relationship in the body's linked context, using source evidence or explicitly
labelled author-reviewed pedagogical synthesis. Do not promote unreviewed
suggestions, infer transitive edges or duplicate incoming edges into another
canonical graph. Obsidian backlinks supply incoming relationships.
Prerequisites must be acyclic; use a different relation for mutual connections.
Similar/related cycles are allowed. There is no concept quota or mandatory
taxonomy, and unclassified sections remain usable.

Adding a course is not permission to redefine a shared concept used by others.
Read its definition and evidence first, preserve its meaning, and obtain an
explicit author decision for changes affecting other courses. A course-only
read may follow relevant explicit shared concept links, but never learner
memory or unrelated vault content. These fields describe content, not mastery,
confidence, deficiencies or a schedule.

## Producing and checking a course

Establish source-based chunks and stable identities, write sections once,
reconcile shared concepts and provenance, then generate indexes and navigation
from their authorities. Regenerate views after edits; do not silently choose
between conflicting orders or source mappings.

Run the [Clew validator](validation.md) on the course and its referenced
concepts. Structurally valid drafts can pass with warnings; strict mode requires
verified sections and resolved page coverage. Validation cannot prove factual
correctness, transcription fidelity, legal rights or live Obsidian rendering.
Keep PDF originals, assets and support records together in the fixed layout;
shared concept dependencies remain at their vault-level locations.
