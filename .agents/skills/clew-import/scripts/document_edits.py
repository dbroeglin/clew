"""Compile a closed operation set into small edits of original source text."""
from __future__ import annotations

from dataclasses import dataclass
import json
import posixpath
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from bundle_sources import Bundle
from document_formats import (Address, Anchor, Callout, Change, Document, Finding,
                              Heading, Plan, Unit)
from document_io import digest, relative_path, require
from markdown_source import ANCHOR, CALLOUT, MarkdownSource

PREFIXES = {"course": "Course-", "exercise": "Exercise-", "correction": "Correction-"}


def document_path(document: Document, bundle: Bundle) -> str:
    basename = bundle.source["name"][:-4]
    folder = document.folder or PREFIXES.get(document.role, "") + basename
    require("/" not in folder and not folder.startswith("."), "Document folder must be one visible name.")
    relative_path(folder)
    relative_path(basename + ".md")
    return f"{folder}/{basename}.md"


def relative_link(origin: str, target: str, label: str, fragment: str = "") -> str:
    path = posixpath.relpath(target, posixpath.dirname(origin))
    return f"[{label}]({quote(path, safe='/')}{quote(fragment, safe='#^=-')})"


def address_link(origin: str, target: Address, paths: dict[str, str], label: str) -> str:
    require(target.document in paths, f"Unknown linked document: {target.document}")
    return relative_link(origin, paths[target.document], label, "#^" + target.anchor)


def escape_text(text: str) -> str:
    text = "".join(char if ord(char) >= 32 else f"U+{ord(char):04X}" for char in text)
    return re.sub(r"([\\`*_{}\[\]<>()!#$|>%])", r"\\\1", text)


def frontmatter(values: dict, newline: str) -> str:
    return "---" + newline + "".join(
        f"{key}: {json.dumps(value, ensure_ascii=False)}{newline}" for key, value in values.items()
    ) + "---" + newline + newline


@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    after: str
    kind: str = "insert"
    order: tuple[int, int] = (100, 0)


@dataclass
class Compiled:
    text: str
    changes: list[Change]
    findings: list[Finding]


def apply_edits(source: str, edits: list[Edit]) -> tuple[str, list[Change]]:
    cursor, output_size = 0, 0
    parts, changes = [], []
    for edit in sorted(edits, key=lambda item: (item.start, item.order, item.end)):
        require(cursor <= edit.start <= edit.end <= len(source),
                f"Overlapping or invalid source edits at offset {edit.start}.")
        untouched = source[cursor:edit.start]
        parts.append(untouched)
        output_size += len(untouched)
        changes.append(Change(
            kind=edit.kind, start=edit.start, end=edit.end, output_start=output_size,
            output_end=output_size + len(edit.after),
            before_sha256=digest(source[edit.start:edit.end].encode("utf-8")), after=edit.after))
        parts.append(edit.after)
        output_size += len(edit.after)
        cursor = edit.end
    parts.append(source[cursor:])
    return "".join(parts), changes


def verify_projection(actual: str, original: str, changes: list[Change]) -> None:
    """Check untouched intervals and independently reverse each narrow syntax edit."""
    before_cursor, after_cursor = 0, 0
    recovered = []
    links = None
    for change in changes:
        require(before_cursor <= change.start <= change.end <= len(original)
                and after_cursor <= change.output_start <= change.output_end <= len(actual),
                "Invalid/reordered source-projection locations.")
        before = original[change.start:change.end]
        require(digest(before.encode("utf-8")) == change.before_sha256,
                "Projection source slice hash differs.")
        after = actual[change.output_start:change.output_end]
        require(after == change.after, f"Prepared structural edit changed at offset {change.output_start}.")
        require(actual[after_cursor:change.output_start] == original[before_cursor:change.start],
                f"Source content changed near original offset {before_cursor}.")
        if change.kind in {"insert", "quote-prefix"}:
            require(not before, "Insertion unexpectedly removes source text.")
            if change.kind == "quote-prefix":
                require(after == "> ", "Invalid quote prefix.")
        elif change.kind == "heading-prefix":
            require(not before or re.fullmatch(r" {0,3}#{1,6}[ \t]*", before) is not None,
                    "Heading edit removes more than a heading prefix.")
        elif change.kind == "heading-suffix":
            require(re.fullmatch(r"[ \t]+#+[ \t]*|[ \t]*[=-]+[ \t]*(?:\r\n|\r|\n)?", before)
                    is not None, "Heading edit removes more than heading syntax.")
        elif change.kind == "page-marker":
            require(re.fullmatch(r"[ \t]*<!-- page: [1-9][0-9]* -->[ \t]*(?:\r\n|\r|\n)?", before)
                    is not None, "Page-marker edit removes substantive content.")
        elif change.kind == "callout-spacing":
            raw = before.rstrip("\r\n")
            require(not after and (not raw.strip()
                                   or re.fullmatch(r" {0,3}>[ \t]*", raw) is not None),
                    "Callout spacing edit removes nonblank source content.")
        elif change.kind == "link-destination":
            if links is None:
                links = MarkdownSource(original).links
            require(any(item.destination_start == change.start and item.destination_end == change.end
                        for item in links), "Link edit is not an exact parsed destination.")
        recovered.append(actual[after_cursor:change.output_start] + before)
        before_cursor, after_cursor = change.end, change.output_end
    recovered.append(actual[after_cursor:])
    require("".join(recovered) == original, "Prepared content does not recover the original Markdown exactly.")


def verify_syntax(original: MarkdownSource, prepared: MarkdownSource) -> None:
    def signature(source):
        result = []
        table = None
        quote_depth = 0
        for token in source.tokens:
            if token.type == "blockquote_open":
                quote_depth += 1
            elif token.type == "blockquote_close":
                quote_depth -= 1
            if token.type == "table_open":
                table = []
            if table is not None:
                table.append((token.type, token.content, token.markup))
                if token.type == "table_close":
                    result.append(("table", tuple(table)))
                    table = None
            elif token.type in {"fence", "code_block", "math_block", "math_block_label"}:
                content = token.content
                if token.type.startswith("math_block") and quote_depth:
                    # Dollarmath's block token retains container prefixes unlike prose tokens.
                    lines = content.split("\n")
                    for index, line in enumerate(lines):
                        for _ in range(quote_depth):
                            line = re.sub(r"^ {0,3}>[ \t]?", "", line, count=1)
                        lines[index] = line
                    content = "\n".join(lines)
                result.append((token.type, content, token.info, token.markup))
            for child in token.children or []:
                if child.type in {"math_inline", "math_inline_double", "code_inline"}:
                    result.append((child.type, child.content, child.markup))
        return result

    require(signature(original) == signature(prepared),
            "Structural edits changed parsed mathematics, code, or table structure.")


def operation_ranges(document: Document, source: MarkdownSource) -> dict[int, tuple[int, int]]:
    result = {}
    for index, operation in enumerate(document.operations):
        if isinstance(operation, (Unit, Callout)):
            result[index] = source.select(operation.start, operation.end)
        else:
            require(operation.block in source.blocks, f"Unknown block: {operation.block}")
            block = source.blocks[operation.block]
            result[index] = block.start, block.end
    return result


def check_operations(plan: Plan, bundles: dict[str, Bundle]) -> None:
    registry = {}
    ranges = {}
    for document in plan.documents:
        source = bundles[document.id].markdown
        ranges[document.id] = operation_ranges(document, source)
        wrapped = []
        units = []
        for index, operation in enumerate(document.operations):
            start, end = ranges[document.id][index]
            if isinstance(operation, (Unit, Callout, Anchor)):
                key = document.id, operation.id
                require(key not in registry, f"Duplicate planned anchor: {key}")
                registry[key] = operation, start, end
            if isinstance(operation, Callout):
                require(all(end <= a or b <= start for a, b in wrapped),
                        f"Overlapping callout operations in {document.id} at line {start + 1}.")
                wrapped.append((start, end))
            if isinstance(operation, Unit):
                if operation.kind == "section":
                    require(source.blocks[operation.start].kind == "heading",
                            "A section must start at an existing source heading.")
                for a, b, kind in units:
                    require((start, end) != (a, b), "Two units cannot own the exact same source span.")
                    require(not (a < start < b < end or start < a < end < b),
                            "Unit spans cross instead of nesting.")
                    if a <= start and end <= b or start <= a and b <= end:
                        outer = kind if a <= start and end <= b else operation.kind
                        require(outer == "section", "Only sections can contain other source units.")
                units.append((start, end, operation.kind))
        for index, operation in enumerate(document.operations):
            if isinstance(operation, (Anchor, Heading, Unit)):
                start, end = ranges[document.id][index]
                if isinstance(operation, Unit):
                    require(all(not a < end < b for a, b in wrapped),
                            "Unit closing boundary lies inside a callout.")
                    end = source.blocks[operation.start].end
                require(all(end <= a or b <= start for a, b in wrapped),
                        "An anchor, heading, or unit entry would target the interior of a callout.")
            if isinstance(operation, Callout) and operation.owner is not None:
                owner = registry.get((document.id, operation.owner))
                require(owner is not None and isinstance(owner[0], Unit),
                        f"Unknown unit owner: {document.id}#^{operation.owner}")
                require(owner[0].kind == ("exercise" if operation.kind == "question" else "correction"),
                        "Question/answer owner has the wrong unit kind.")
                start, end = ranges[document.id][index]
                require(owner[1] <= start and end <= owner[2], "Question/answer lies outside its owning unit.")
    for document in plan.documents:
        for operation in document.operations:
            match = operation.exercise if isinstance(operation, Unit) else (
                operation.question if isinstance(operation, Callout) else None)
            if match is None:
                continue
            key = match.target.document, match.target.anchor
            target = registry.get(key)
            require(target is not None, f"Unknown relationship target: {key}")
            expected = "exercise" if isinstance(operation, Unit) else "question"
            require(getattr(target[0], "kind", None) == expected, "Relationship target has the wrong kind.")
            for evidence in match.evidence:
                require(evidence.document in bundles, "Unknown relationship evidence document.")
                a, b = bundles[evidence.document].markdown.span(evidence.start, evidence.end)
                require(bool(bundles[evidence.document].markdown.text[a:b].strip()), "Empty match evidence.")
            if isinstance(operation, Callout):
                owner = registry[(document.id, operation.owner)][0]
                require(isinstance(owner, Unit) and owner.exercise is not None,
                        "Matched answer needs a matched correction unit.")
                require(isinstance(target[0], Callout) and target[0].owner == owner.exercise.target.anchor
                        and match.target.document == owner.exercise.target.document,
                        "Answer question does not belong to its correction's exercise.")


def source_reviews(document: Document, bundle: Bundle, path: str) -> list[Finding]:
    source = bundle.markdown
    findings = []

    def review(code, line, message, anchor=None):
        findings.append(Finding(code=code, severity="review", path=path, line=line,
                                message=message, anchor=anchor))

    for item in bundle.manifest["issues"]:
        message = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        review("conversion-review", 1, message)
    if bundle.manifest["status"] == "needs_review" and not bundle.manifest["issues"]:
        review("conversion-review", 1, "The completed conversion is marked needs_review.")
    for item in document.reviews:
        require(item.block is None or item.block in source.blocks, "Review targets an unknown block.")
        review(item.code, source.blocks[item.block].start + 1 if item.block else 1, item.message)
    external = set()
    for link in source.links:
        parsed = urlsplit(link.target)
        if (parsed.scheme in {"http", "https", "ftp", "mailto", "tel"} or link.target.startswith("//")) \
                and link.target not in external:
            external.add(link.target)
            review("external-link", link.line, "External destination was not checked remotely.")
    classified = {}
    levels = {}
    for operation in document.operations:
        if isinstance(operation, (Unit, Callout)):
            classified[source.blocks[operation.start].start] = operation.kind
        if isinstance(operation, Unit) and operation.kind == "correction" and operation.exercise is None:
            review("unmatched-correction", source.blocks[operation.start].start + 1,
                   "This supplied correction has no verified exercise match.", operation.id)
        if isinstance(operation, Callout) and operation.kind == "answer" and operation.question is None:
            review("unmatched-answer", source.blocks[operation.start].start + 1,
                   "This supplied answer has no verified question match.", operation.id)
        if isinstance(operation, Heading):
            levels[source.blocks[operation.block].start] = operation.level
        if isinstance(operation, Unit) and operation.kind in {"exercise", "correction"}:
            start, end = source.select(operation.start, operation.end)
            kind = "question" if operation.kind == "exercise" else "answer"
            if not any(isinstance(other, Callout) and other.kind == kind and other.owner == operation.id
                       for other in document.operations):
                review("empty-unit", start + 1,
                       f"{operation.kind.capitalize()} has no addressed source blocks.", operation.id)
    previous = 0
    for heading in source.headings:
        line = heading["start"] + 1
        level = levels.get(heading["start"], heading["level"])
        if classified.get(heading["start"]) not in {
            "theorem", "definition", "property", "lemma", "proposition", "corollary",
            "example", "remark", "proof", "question", "answer",
        }:
            if previous and level > previous + 1:
                review("heading-gap", line, f"Heading level jumps from {previous} to {level}.")
            previous = level
        if classified.get(heading["start"]) != heading["kind"]:
            review("unclassified-unit", line,
                   f"Review the {heading['kind']} heading: {heading['label']}")
    for (start, end) in [source.select(op.start, op.end) for op in document.operations
                         if isinstance(op, Callout)]:
        for heading in source.headings:
            if start < heading["start"] < end:
                review("enclosed-heading", heading["start"] + 1,
                       "This source heading remains inside one callout and is not independently addressable.")
    if document.role in {"exercise", "correction"}:
        role = "question" if document.role == "exercise" else "answer"
        spans = [source.select(op.start, op.end) for op in document.operations
                 if isinstance(op, Callout) and op.kind == role]
        for block in source.blocks.values():
            if block.kind == "item" and not any(a <= block.start < block.end <= b for a, b in spans):
                review("unclassified-item", block.start + 1,
                       f"Review this numbered source item; it has no addressed {role} block.")
    if document.role in {"mixed", "unknown"}:
        review("document-role", 1, f"Document role is {document.role}; no single source type was assumed.")
    return findings


def compile_document(document: Document, bundle: Bundle, path: str,
                     paths: dict[str, str]) -> Compiled:
    source = bundle.markdown
    newline_match = re.search(r"\r\n|\r|\n", source.text)
    nl = newline_match[0] if newline_match else "\n"
    edits: list[Edit] = []
    ranges = operation_ranges(document, source)
    findings = source_reviews(document, bundle, path)
    source_pdf = posixpath.join(posixpath.dirname(path), bundle.source["name"])

    def pdf_links(start, end):
        pages = source.pages(start, end)
        require(pages, "Selected source block has no original PDF page provenance.")
        page = pages[0]
        return relative_link(path, source_pdf, f"PDF p. {page}", f"#page={page}")

    def add(position, text, order=(100, 0), kind="insert", end=None):
        edits.append(Edit(position, position if end is None else end, text, kind, order))

    def standalone(position, anchor, order=(20, 0)):
        prefix = "" if position == 0 or source.text[position - 1] in "\r\n" else nl
        add(position, prefix + nl + "^" + anchor + nl + nl, order)

    def existing_anchor(anchor):
        for token in source.tokens:
            if token.type != "paragraph_open" or token.level != 0 or token.map is None:
                continue
            a, b = token.map
            raw = "".join(source.lines[a:b]).rstrip("\r\n")
            if re.search(r"(?:^|\s)\^" + re.escape(anchor) + r"$", raw):
                return a, b
        return None

    add(0, frontmatter({"clew_schema": 1, "id": document.id, "type": "document",
                       "role": document.role, "source_pdf": bundle.source["name"],
                       "source_pages": bundle.pages}, nl), (-100, 0))
    promoted = {}
    for index, operation in enumerate(document.operations):
        start, end = ranges[index]
        a, b = source.offsets[start], source.offsets[end]
        addressed = (isinstance(operation, (Callout, Anchor))
                     or isinstance(operation, Unit) and operation.kind != "section")
        existing = existing_anchor(operation.id) if addressed else None
        if existing is not None:
            require(start <= existing[0] and existing[1] <= end,
                    "Existing anchor belongs to another source block.")
        if isinstance(operation, Unit):
            add(a, nl + f"%% clew:unit {operation.kind} {operation.id} %%" + nl + nl,
                (40, -end))
            ending = "" if b == 0 or source.text[b - 1] in "\r\n" else nl
            add(b, ending + nl + f"%% /clew:unit {operation.id} %%" + nl + nl, (30, -start))
            first = source.blocks[operation.start]
            position = source.offsets[first.end] if first.kind == "heading" else a
            fields = []
            if operation.exercise is not None:
                fields.append(address_link(
                    path, operation.exercise.target, paths, "Exercise"))
            entry = pdf_links(start, end) if operation.kind == "section" else operation.kind.capitalize()
            if existing is None and operation.kind != "section":
                entry += " ^" + operation.id
            add(position, nl + entry + nl + nl, (45, 0))
            if operation.kind != "section":
                footer = nl.join([*fields, pdf_links(start, end)])
                add(b, ending + nl + footer + nl + nl, (25, 0))
        elif isinstance(operation, Callout):
            first = source.blocks[operation.start]
            fields = []
            if operation.question is not None:
                fields.append(address_link(
                    path, operation.question.target, paths, "Question"))
            field_text = ">" + nl
            callout_kind = "reponse" if operation.kind == "answer" else operation.kind
            original_callout = CALLOUT.fullmatch(source.lines[start].rstrip("\r\n")) if first.kind == "quote" else None
            body_start = start
            callout_end = first.end
            if original_callout:
                require(original_callout[1].lower() in {callout_kind, operation.kind},
                        "Do not reclassify an existing source callout silently.")
                while (callout_end > start
                       and not source.lines[callout_end - 1].startswith(">")
                       and not source.lines[callout_end - 1].strip()):
                    callout_end -= 1
                require(all(line.startswith(">") for line in source.lines[start:callout_end]),
                        "Existing callout needs explicit quoting for safe structural edits.")
                add(source.offsets[start + 1], field_text, (10, 0))
                body_start = start + 1
            else:
                if first.kind == "heading":
                    require(first.end - first.start <= 2, "Multiline heading cannot become a callout title safely.")
                    raw = source.lines[start].rstrip("\r\n")
                    prefix = re.match(r" {0,3}#{1,6}(?:[ \t]+|$)", raw)
                    if prefix:
                        add(a, f"> [!{callout_kind}] ", kind="heading-prefix", end=a + prefix.end())
                        suffix = re.search(r"[ \t]+(?<!\\)#+[ \t]*$", raw)
                        if suffix and suffix.start() >= prefix.end():
                            add(a + suffix.start(), "", kind="heading-suffix", end=a + suffix.end())
                    else:
                        require(first.end - start == 2 and re.fullmatch(
                            r" {0,3}[=-]+[ \t]*(?:\r\n|\r|\n)?", source.lines[start + 1]),
                            "Unsupported heading syntax for a callout.")
                        add(a, f"> [!{callout_kind}] ", kind="heading-prefix")
                        add(source.offsets[start + 1], "", kind="heading-suffix", end=source.offsets[start + 2])
                    body_start = first.end
                    add(source.offsets[first.end], field_text, (10, 0))
                    promoted[first.label] = operation.id
                    for heading in source.headings:
                        if heading["start"] == first.start:
                            promoted[heading["text"]] = operation.id
                else:
                    label = operation.kind.capitalize()
                    if first.kind == "item":
                        label += " " + first.label
                    add(a, f"> [!{callout_kind}] {label}{nl}" + field_text, (60, 0))
            content_end = callout_end if original_callout else end
            terminal_blank_lines = []
            for line in range(content_end - 1, body_start - 1, -1):
                if line in source.markers:
                    break
                raw = source.lines[line].rstrip("\r\n")
                empty = (re.fullmatch(r" {0,3}>[ \t]*", raw) is not None
                         if original_callout else not raw.strip())
                if not empty:
                    break
                terminal_blank_lines.append(line)
            trimmed_lines = set(terminal_blank_lines[1:])
            for line in trimmed_lines:
                add(source.offsets[line], "", kind="callout-spacing",
                    end=source.offsets[line + 1])
            if not original_callout:
                for line in range(body_start, end):
                    if line not in source.markers and line not in trimmed_lines:
                        add(source.offsets[line], "> ", kind="quote-prefix")
            footer_position = source.offsets[callout_end] if original_callout else b
            ending = "" if footer_position == 0 or source.text[footer_position - 1] in "\r\n" else nl
            separator = "" if terminal_blank_lines else ">" + nl
            footer = " · ".join([*fields, pdf_links(start, end)])
            add(footer_position, ending + separator + "> " + footer + nl, (10, 0))
            if existing is None:
                standalone(b, operation.id)
        elif isinstance(operation, Anchor):
            if existing is None:
                block = source.blocks[operation.block]
                if block.kind == "paragraph" and ANCHOR.fullmatch(source.lines[start].strip()) is None:
                    position = b - len(source.lines[end - 1]) + len(source.lines[end - 1].rstrip("\r\n"))
                    add(position, " ^" + operation.id)
                else:
                    standalone(b, operation.id)
        elif isinstance(operation, Heading):
            block = source.blocks[operation.block]
            require(block.kind == "heading", "Heading adjustment targets a non-heading.")
            raw = source.lines[start].rstrip("\r\n")
            prefix = re.match(r" {0,3}#{1,6}(?:[ \t]+|$)", raw)
            if prefix:
                add(a, "#" * operation.level + " ", kind="heading-prefix", end=a + prefix.end())
            else:
                require(end - start == 2, "Multiline setext heading adjustment is unsupported.")
                add(a, "#" * operation.level + " ", kind="heading-prefix")
                add(source.offsets[start + 1], "", kind="heading-suffix", end=b)
    for line in source.markers:
        a, b = source.offsets[line], source.offsets[line + 1]
        add(a, "", kind="page-marker", end=b)
    for item in source.links:
        if item.reference and item.kind != "definition":
            continue
        parsed = urlsplit(item.target)
        if parsed.scheme or item.target.startswith("//"):
            continue
        original_path, fragment = unquote(parsed.path), unquote(parsed.fragment)
        new_path = (bundle.source["name"] if original_path == bundle.source["path"] else
                    posixpath.basename(path) if original_path == "document.md" else original_path)
        new_fragment = "^" + promoted[fragment] if fragment in promoted else fragment
        if new_path != original_path or new_fragment != fragment:
            require(item.destination_start is not None and item.destination_end is not None,
                    f"Cannot locate source link destination losslessly at line {item.line}.")
            destination = urlunsplit(("", "", quote(new_path, safe="/"), parsed.query,
                                      quote(new_fragment, safe="^=-")))
            if item.kind == "wiki":
                destination = new_path + ("#" + new_fragment if new_fragment else "")
            add(item.destination_start, destination, kind="link-destination", end=item.destination_end)
    seen = set()
    reviews = []
    for finding in findings:
        key = finding.code, finding.line, finding.message
        if key in seen:
            continue
        seen.add(key)
        data = {"code": finding.code, "message": finding.message, "anchor": finding.anchor}
        marker = (json.dumps(data, ensure_ascii=True).replace("<", "\\u003c")
                  .replace(">", "\\u003e").replace("%", "\\u0025"))
        location = (relative_link(path, path, "Location", "#^" + finding.anchor)
                    if finding.anchor else f"Original Markdown line {finding.line}")
        reviews.append("%% clew:review " + marker + " %%" + nl
                       + "> [!warning] Clew review" + nl + "> " + escape_text(finding.message)
                       + nl + "> " + location + nl + nl)
    if reviews:
        add(len(source.text), nl + nl + "**Review required**" + nl + nl
            + "".join(reviews), (90, 0))
    text, changes = apply_edits(source.text, edits)
    verify_projection(text, source.text, changes)
    return Compiled(text, changes, findings)
