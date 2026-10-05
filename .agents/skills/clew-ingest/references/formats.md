# Versioned contracts

## Plan (version 2)

All objects reject unknown keys. IDs use lowercase ASCII letters/digits/dashes,
start with a letter, and have no consecutive/trailing dashes. Note IDs start
with `<ingest_id>-` and become filenames. Windows reserved names and unsafe
relative paths are rejected. Absolute input/output paths use host syntax.

```json
{
  "schema_version": 2,
  "ingest_id": "algebre",
  "title": "Algebre",
  "destination": "C:\\vault\\courses\\PT\\maths\\algebre",
  "placement": {
    "vault": "C:\\vault",
    "parent": "courses/PT/maths",
    "rationale": "Existing PT mathematics chapters use this container; confirmed by the user.",
    "create_parent": false
  },
  "sources": [
    {"id": "cours", "bundle": "C:\\imports\\cours", "fingerprint": "<inspection fingerprint>"}
  ],
  "notes": [
    {
      "id": "algebre-espaces-vectoriels",
      "type": "course",
      "title": "Espaces vectoriels",
      "title_origin": "source",
      "order": 10,
      "parts": [{"source": "cours", "start": 1, "end": 12, "role": "text"}]
    }
  ],
  "relationships": [],
  "issues": []
}
```

The illustrative hash must be replaced with the actual 64-character digest.
Required plan keys are all shown. Source IDs are distinct; paths select explicit
bundles. The fingerprint includes the import manifest and retained subset hashes.

`placement` is required. Its `vault` must be an existing absolute directory;
`parent` must be a visible non-root portable relative path within it, not a configuration
directory or inside an earlier ingest root. `destination` is a new direct child
of that parent. The agent chooses the location from source context and vault
conventions and obtains placement confirmation; scripts only enforce safety.
The example hierarchy is not mandatory. `rationale` is nonempty; `create_parent`
defaults to false. Missing parent containers require explicit creation approval
and `create_parent: true`. A rationale or hash is not proof of user permission.

Notes require `id`, `type`, `title`, `title_origin` (`source` or `agent`), positive
`order`, and `parts`. Types: `course`, `section`, `exercise`, `correction`.
Only a course-index note may have empty parts. Empty other notes are errors.

Each part selects `source`, `start`, `end`, and optional `role` (defaults to
`text`). Question/answer parts require an `id` prefixed `q-`/`r-`; optional `label`
preserves the printed question/answer label. Text parts cannot have block IDs.
Question parts belong to exercises; answer parts to corrections.

Each exercise note contains exactly one actual source exercise, with shared
context and all subquestions; each correction note contains one supplied
correction unit for an exercise. Separate supplied variants may have separate
correction notes. Do not aggregate independent exercises/corrections or create
exercise/correction files for their questions/answers. Exercise notes require
anchored question parts; correction notes require anchored supplied answer parts.
An all-text exercise/correction plan is incomplete structure, even with full
source coverage. Preserve safely addressable internal questions and source
hierarchy; explain inseparable blocks rather than splitting their owning note.

Course/section notes cover coherent subtopics. Review numbered peers even when
Markdown heading levels differ; no fixed size cutoff or automatic heading split
defines coherence. Misleading candidates and coherent grouping require
source-specific, note-scoped issues. Actual exercise boundaries that cannot be
cut safely are blockers, not permission to aggregate or corrupt the source.

Ranges are one-based inclusive lines in unchanged UTF-8 Markdown. Each source
line, including whitespace and page markers, must be assigned exactly once.
Start/end cannot bisect parser-mapped Markdown constructs. Parts preserve
per-source order in each note; sections preserve source order within their
course. Orders are unique per note type (sections scoped to their parent course).

Source page markers are metadata only: standalone parsed HTML comments matching
`<!-- page: N -->` are removed from displayed notes, never from retained Markdown.
Lookalikes in code remain. Source text otherwise stays exact, except local
destinations rewritten to the retained source and structural separators/wrappers.

Local CommonMark links/images must reference manifest-declared figures or the
retained PDF. Destinations must be portable relative paths, with no query/fragment.
Inline destinations and reference definitions with simple or angle-bracket paths
are supported. Reference usages and definitions must stay in the same note's
plain-text context or in the same question/answer part. Identical reference labels
from different sources cannot share a note. Plans violating those scopes are
blocked; regroup without changing source text. Complex destinations that cannot be located losslessly are
reported as blockers, not silently rewritten. External URLs and source fragment
links remain source content and are reported for review.

Relationships have `rel`, `origin`, `target`, and a nonempty `evidence` list.
Each evidence item is a valid source range (`source`, `start`, `end`) containing
source text. Scripts validate location, not the truth of the interpretation.

| rel | origin | target |
| --- | --- | --- |
| `course` | section or exercise note ID | course note ID |
| `correction` | correction note ID | exercise note ID |
| `question` | correction answer address | exercise question address |
| `needs` | exercise question address | earlier question in the same exercise |

Block addresses are `<note-id>#^<block-id>`. Sections require one course parent;
exercises may link several courses. Corrections have at most one exercise, but
one exercise may have multiple correction notes or supplied answers. Linked
answers must agree with the correction's exercise association. Question `needs`
must point backward; cycles and forward links are impossible under this rule.
Unmatched answers/corrections and missing answers produce review findings.

Issues contain `code`, `message`, and optional `note`. Include semantic uncertainty
explicitly. Import issues and structural missing-link findings are also emitted.
Do not add relationships merely to avoid warnings.

### Scoped structuring review

Normal checks reject aggregation, exercise/correction-per-question fragmentation,
and absent structural parts. The outline exposes candidates, not verified
pedagogical units. Source-specific review uses existing issues with a required
`note` and nonblank `message`, bound to the exact scope:

| Code | Reviewed scope |
| --- | --- |
| `structure-candidate:<source>:<start>` | A misleading exercise/correction heading, or an unheaded ordered list crossing notes that needs an explicit source-unit interpretation. `start` is the candidate's one-based line. |
| `structure-course-group:<source>:<family>` | Peer topics retained in one course/section note. Numbered family is the parent prefix, such as `4` for `4.1`/`4.6`, or `root` for top-level numbers. Unnumbered family is `heading-<parent-line-or-root>-<heading-level>`. |
| `structure-block-group:<source>:<start>` | Internal question/answer candidates retained in one structural part, or a contextual list kept plain. `start` is that plan part's first line. |

For example, `{"code":"structure-course-group:cours:4",
"note":"algebre-fonctions","message":"cours:120-190 contains the statement and
two cases of one proof; keep their numbered headings together."}` explains only
that source family in that note. Read the actual passages; do not generate
waivers automatically. Unknown, unused, duplicate, unscoped, or blank structure
exceptions are errors. A reason is review evidence, not mechanical proof of
semantic truth. No exception waives missing question/answer blocks or permits
grouping real independent exercises or splitting one into question notes.

## Persisted notes and ownership

All course and section notes share `courses/`. Exercises and corrections use
`exercices/` and `corriges/`. Frontmatter is readable YAML with JSON flow values
(valid YAML), English keys, source/agent title origin, draft status, order, sources,
and established relationships. Source references include source ID, retained
PDF path relative to the ingest root, page numbers, and original line ranges.

Plain source Markdown stays plain. Question/answer blocks become `question`/
`reponse` callouts with source fields and note-local anchors. Added wrappers and
metadata are structural, not new learning content. Exercise/correction note
links are emitted reciprocally. A course note lists linked sections/exercises.
Note IDs identify exercise/correction units; local block IDs identify their
questions/answers. The same `q-1` in two notes is not the same question. Enrich
preserves these units and addresses, adding auxiliary `type: help` notes where
appropriate. Generate consumes current notes directly, with finer question
views derived from these internal blocks before or after optional enrichment.
Neither downstream stage creates question/answer-sized source notes.
Invisible `clew-part` comments delimit source segments for independent fidelity
projection. That structural marker prefix is reserved. Validation unwraps
callouts, removes only documented separators, and reverses recorded local-link
rewrites to compare against the exact source ranges; it also checks canonical
note metadata/wrappers separately.
Each source-bearing note also includes clickable links to its retained PDFs
with original PDF page numbers; these provenance links are structural additions:
`[page 2](../sources/feuille/chapitre.pdf#page=2)`. Each page gets its own link,
not a range fragment. Discontiguous imports use actual PDF pages, not selection
positions or printed page labels. Index PDF links target the first imported page.
Source-authored PDF links are not given new page fragments.

`index.md` uses ordinary Markdown and wikilinks, not plugin queries. Stable
source copies live at `sources/<source-id>/<original-name>.pdf`,
`sources/<source-id>/document.md`, and their original `figures/` paths.
Source IDs disambiguate identical filenames across bundles.

`ingest.json` uses output schema version **3** and records `writing`/`complete` status, the plan and
its hash, source metadata/hashes, expected file hashes, and review findings.
The PDF sits next to `document.md`; there is no inner `source/` directory.
Snapshot metadata and snapshot file keys preserve the original Import-relative
references (including `source/<original-name>.pdf`). The output file inventory,
note frontmatter, and generated links use the flattened retained path instead.
Retained Markdown remains byte-identical, including its original relative links;
generated notes resolve those links to the new retained locations.
Only notes are the learning-content store. Validation reconstructs the allowed
structural projection from retained Markdown and compares the complete note
bytes, as well as coverage, hashes, links, and file ownership. Human edits are
reported as changes; this version does not merge them or overwrite them.

Validation uses no external bundle path and can validate a relocated complete
ingest without requiring the original vault or placement parent to exist.
It rejects extra files/directories as ownership uncertainty. A completion
record is not a cryptographic signature against deliberate record tampering.

Every created file belongs to one root; deleting that root is sufficient for
whole-ingest removal. No source bundle, shared attachment folder, or other ingest
is modified. Approved missing parent containers may also be created; these
shared directories are not chapter-owned and may remain after root removal.
Scripts never implement deletion.

Plan version 2 requires contextual placement; note schema remains version 1.
Output version 3 includes placement and page-addressed provenance, retaining
version 2's flat PDF layout. Approval hashes include the output version, so an
earlier approved hash cannot authorize changed output or placement. Rerun
`--check` and approve its new paths/hash before materialization. Existing
version-1/2 outputs and version-1 plans are rejected explicitly, never modified
or automatically migrated. Choose and confirm placement, then create a fresh
approved ingest in a new destination from the original Import bundles.

## Reports and commands

Inspector: JSON `bundles` with fingerprints, metadata, hashes, zero-based safe
boundaries, page markers, local references, and `outline` candidates. Outline
rows have `kind`, original `label`, one-based inclusive `start`/`end`,
`safe_start`/`safe_end`, hierarchy `level`/`parent`, and parsed `number` where
available. Ordered items also expose their heading `context`. Candidate ranges
do not authorize a cut; protected quote/list/formula boundaries still apply.

Vault inspector: read-only JSON `vault`, `scope`, `obsidian_marker`,
`directories` (relative paths, Markdown counts/sample paths, `has_ingest_record`),
`omitted` entries with reasons, and `requires_agent_review: true`. No note or
configuration contents are read. Optional `--within`, `--depth` (default 4),
`--max-directories` (128), and `--samples` (3) bound/focus discovery. Samples are
not exhaustive; the agent reads relevant notes and reviews inventory omissions.
An Obsidian installation or `.obsidian` marker is not required.

Writer `--check`: JSON exact paths, `plan_sha256`, `requires_approval: true`, and
review issues, plus `placement` and exact `create_directories` for any missing
parents. This is read-only, including when parent creation is approved.
`structure` shows candidate unit spans and owning notes, exact planned parts,
question/answer counts and full addresses, relationships/evidence, scoped
exceptions, and `requires_agent_review: true`. Heading-to-heading unit spans
can contain shared introductions assigned to the following note; actual plan
parts remain authoritative. Both check and write use these structuring gates,
as does read-only persisted validation.

Writer `--plan-sha256 HASH`: binds execution to that plan, creates only approved
missing containers and a new root,
validates, and reports the same persisted validation result. A hash is not user
authorization; the skill handles permission.

Validator: JSON file list, ingest ID, root, plan hash, issues, and report status
`validated` or `needs_review`. All JSON commands exit `0` on completed operations
with visible review findings, `1` on errors with stderr diagnostics. Slicer emits
exact Markdown to stdout. None of these commands perform model inference.
