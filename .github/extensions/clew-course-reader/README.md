# Clew Course Reader

A read-only GitHub Copilot App canvas for a chosen course inside the current
vault. The learner can navigate and stage selected passages in chat; the session can
open pages, navigate, inspect the current excerpt, and refresh the reader.
[ADR-0002](../../../docs/adr/adr-0002-copilot-app-extension-ux.md) describes the
architecture and remains **Proposed**.

## Install

Use a Copilot App version with extension canvases and Node.js 22.12 or newer.
From the repository root:

```powershell
npm --prefix .github\extensions\clew-course-reader ci --ignore-scripts
```

Then call `extensions_reload`. Use `extensions_manage` with operation `inspect`
and name `clew-course-reader` to diagnose loading errors. The host discovers
`extension.mjs` automatically and supplies `@github/copilot-sdk`; do not install
an extra SDK copy. npm manages the pinned renderer dependencies here; APM still
manages the repository's agent skills.

## Open a course

Ask the session to open the **Clew Course Reader** with the current vault's
absolute path and a vault-relative course directory. The extension does not
discover or read Obsidian's configuration.

```json
{
  "canvasId": "clew-course-reader",
  "instanceId": "course-reading",
  "input": {
    "vaultPath": "C:\\path\\to\\current-vault",
    "coursePath": "courses/my-course",
    "entry": "hub.md"
  }
}
```

These are `open_canvas` arguments. `entry` is optional and defaults to `hub.md`;
a saved reading position takes precedence. To change pages explicitly after
opening, invoke `open_page`. The directory must be a course within the vault,
not the entire vault, a private `model` directory, or a hidden directory.

For a synthetic demonstration, use the absolute path of
[`examples/reader-vault`](../../../examples/reader-vault) as `vaultPath` and
`courses/reader-tour` as `coursePath`. No real learner records are needed.

## Course format

Navigation is authored in top-level YAML frontmatter. Quote wikilinks so YAML
does not interpret them as lists.

```yaml
---
title: Working with derivatives
previous: "./01-limits.md"
next: "[[courses/my-course/03-integration|Integration]]"
---
```

`previous` and `next` each accept a nonempty string, `null`, or omission.
`title` is optional; the first H1 or filename supplies the display title.
Other metadata is neither shown nor sent to the session.

| Reference | Resolution |
| --- | --- |
| `./lesson.md`, `../hub.md` | Relative to the current note, confined to the course |
| `[[courses/my-course/lesson]]` | Vault-relative path, if inside this course |
| `[[chapter/lesson]]` | Course-relative qualified path |
| `[[Lesson]]` | Unique matching basename within the course |
| `[[Lesson#A heading\|Continue]]` | Note plus heading, with optional display label |

`.md` may be omitted. Ambiguous basenames are errors, not a choice of the first
match. Missing or invalid targets disable the affected navigation control and
show a diagnostic; they do not prevent reading the current page. Invalid YAML
or unsupported property types are explicit load errors. Source-relative
Markdown links in the body and body wikilinks use the same course boundary.
Missing headings fail without leaving the current page.

## Markdown and mathematics

The reader renders standard Markdown, tables, strikethrough, code, links, and
local PNG/JPEG/GIF/WebP/AVIF images. Raw HTML is displayed as text, not executed.
Remote images are not fetched; ordinary external HTTP(S) links open only when
selected. Obsidian note embeds, block references, and plugin-specific syntax
are not implemented.

KaTeX renders mathematical formulas locally, including:

````markdown
Inline: $E = mc^2$ or \(a^2 + b^2 = c^2\).

$$
\int_0^1 x^2\,dx = \frac{1}{3}
$$

\[
\sum_{n=1}^{N} n = \frac{N(N+1)}{2}
\]

```math
\begin{pmatrix}a & b \\ c & d\end{pmatrix}
```
````

Ordinary inline code and code fences stay literal. Output includes MathML for
accessibility. KaTeX CSS and fonts come from the installed package through the
same loopback server, with no CDN. Unsupported TeX is shown as an error with its
original source and a diagnostic. Trusted HTML/URL commands are disabled; macro
expansion is bounded and macro definitions do not leak between pages.

## Reading and asking in chat

The permanent interface contains the course name, rendered content,
Previous/Next, and a collapsible contents list for the **current page's
headings**. Contents starts collapsed and preserves your open/closed choice
while navigating in that panel. Refresh remains a session action, not an extra
reader button.

**Reader to composer:** select a passage in the course content and choose the
contextual **Ask in chat** action. The complete selected text is staged as an
attachment chip in the current chat composer. Write your question there and
send it when ready. The reader never sends a message automatically and has no
separate explanation or preview dialog.

The excerpt includes its full, canonical source file path and the section
heading where the selection starts, when one exists. These are references in
the excerpt metadata, not a separate attachment of the whole Markdown file.
The reader does not invent source line numbers or change your typed question.

The provider uses the documented
`session.rpc.extensions.sendAttachmentsToMessage` API with an `extension_context`
attachment bound to the current canvas instance. It does not call `session.send`.
If the SDK lacks this capability, the contextual action is not offered; host
rejections are reported without substituting a different workflow. Explicit
retries of the same staging request are deduplicated within the running
provider. Staging is never automatically retried.

**Session to reader:** discover the schema with `list_canvas_capabilities`, then
use `invoke_canvas_action` with the panel's `instanceId`:

| Action | Input | Effect |
| --- | --- | --- |
| `get_state` | `{}` | Current page, headings, navigation, revision, and grounded excerpt |
| `open_page` | `{"path":"chapter/lesson.md"}` | Open a course-relative note |
| `navigate` | `{"direction":"next"}` or `{"direction":"previous"}` | Follow authored frontmatter |
| `refresh` | `{}` | Reload the current note after a source edit |

Mutating actions also accept `expectedRevision` from `get_state`. Browser
commands always supply it; outdated views get `stale_view` rather than moving
from a different page. Both surfaces use the same controller. SSE pushes the
result into all open panels for that course.

## State, privacy, and limits

Only the last course-relative page is stored, under the session workspace's
`files/clew-course-reader/<course-path-hash>.json`. There are no navigation
timestamps, reading histories, learner observations, or course-file writes.
The saved position survives provider reloads and new panel IDs in that session.
An invalid bookmark or unavailable session workspace is reported, not silently
replaced by a default. A different course or session has independent state.

All note and image paths, including symlink targets, must stay inside the
selected course. Basename resolution searches only that course, skips hidden,
private-model, and symlink entries, and stops at 10,000 entries; qualified links
avoid the search. Notes are limited to 1 MiB and raster images to 10 MiB.

**Ask in chat** preserves the entire selected passage, including Unicode and
whitespace, with its source-file and section references. It has no 12,000-character
selection cap and does not silently truncate on a host rejection. The existing
`get_state` tool excerpt is separately bounded to 12,000 Unicode characters with
truncation metadata; it is not the source for selection attachments.

If the source changes after selection, staging fails until the session refreshes
the reader and the learner selects again. Selections do not create learner
observations or write course files. The provider does not implement adaptation
or grant a hosted session access to private learner data.

Each panel binds an ephemeral server to `127.0.0.1` only. Its random capability
URL, host/origin checks, fixed resource routes, bounded JSON bodies, and content
security policy protect the local interface. Closing a panel releases its
server and SSE connections. Runtime reload rehydrates a new URL; old URLs
should not be bookmarked or shared.

## Development

```powershell
npm --prefix .github\extensions\clew-course-reader run check
npm --prefix .github\extensions\clew-course-reader test
npm --prefix .github\extensions\clew-course-reader run test:browser
```

The Node tests use disposable synthetic vaults. Reload the extension after
editing its files, then check discovery, open, navigation, refresh, invalid
inputs, restart behavior, and selection-to-composer staging in the App. Confirm
that staging does not submit a user message or overwrite a drafted question.

Browser checks use headless Microsoft Edge on Windows and Playwright Chromium
elsewhere. Install the selected browser if it is absent; set
`PLAYWRIGHT_CHANNEL` to use another installed Playwright-supported channel.
The npm lockfile omits registry-specific download URLs so it can be restored
through the developer's configured npm registry.
