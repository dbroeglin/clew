"""Parse and check current native Obsidian addresses without repairing notes."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import posixpath
import re
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote, urlsplit

from pydantic import ValidationError

from document_formats import CALLOUT_KINDS, Finding, Record, Role, Slug
from document_io import require, yaml_object
from markdown_source import ANCHOR, CALLOUT, Link, MarkdownSource, source_lines

RELATIONSHIP = re.compile(
    r"^(?: {0,3}>[ \t]*)?(?=\[(exercise|question)\]\()"
    r"(\[[^\r\n]*?\]\([^\r\n]*?\))[ \t]*$", re.I)
RELATIONSHIP_START = re.compile(
    r"^(?: {0,3}>[ \t]*)?\[(exercise|question)\]\(", re.I)
OPEN_UNIT = re.compile(r"%% clew:unit (section|exercise|correction) ([A-Za-z0-9-]+) %%")
CLOSE_UNIT = re.compile(r"%% /clew:unit ([A-Za-z0-9-]+) %%")
REVIEW = re.compile(r"%% clew:review (\{.*\}) %%")
SAFE_SCHEMES = {"http", "https", "mailto", "tel", "ftp"}


class NoteMetadata(Record):
    clew_schema: int
    id: Slug
    type: str
    role: Role | None = None
    source_pdf: str | None = None
    source_pages: list[int] | None = None
    title: str | None = None

    model_config = {**Record.model_config, "extra": "allow"}


@dataclass
class Target:
    path: str
    id: str
    kind: str
    start: int
    end: int
    fields: dict[str, Link] = field(default_factory=dict)


class Note:
    def __init__(self, path: str, text: str) -> None:
        self.path, self.text = path, text
        match = re.match(r"\A---(?:\r\n|\r|\n)(.*?)(?:\r\n|\r|\n)---(?:(?:\r\n|\r|\n)|$)", text, re.S)
        require(match is not None, f"Missing or unclosed frontmatter: {path}")
        self.metadata = NoteMetadata.model_validate(yaml_object(match[1]))
        require(self.metadata.clew_schema == 1, f"Unsupported document schema: {path}")
        require(self.metadata.type in {"document", "chapter"}, f"Unsupported note type: {path}")
        if self.metadata.type == "document":
            require(self.metadata.role is not None and self.metadata.source_pdf is not None
                    and self.metadata.source_pages is not None, f"Missing document metadata: {path}")
        self.header_lines = len(source_lines(text[:match.end()]))
        self.body = text[match.end():]
        self.source = MarkdownSource(self.body)
        self.anchors: dict[str, list[Target]] = {}
        self.units: list[Target] = []
        self.callouts: list[Target] = []
        self.findings: list[Finding] = []
        self.fields: list[tuple[int, str, Link]] = []
        self._anchors()
        self._fields()
        self._units()
        self._callouts()
        self._headings()

    def finding(self, code: str, line: int, message: str, *, severity="error", anchor=None, target=None):
        self.findings.append(Finding(code=code, severity=severity, path=self.path,
                                     line=max(1, line + self.header_lines + 1), message=message,
                                     anchor=anchor, target=target))

    def _anchors(self) -> None:
        structured = [token for token in self.source.tokens
                      if token.level == 0 and token.map and token.type in {
                          "blockquote_open", "table_open", "ordered_list_open", "bullet_list_open"}]
        for index, token in enumerate(self.source.tokens):
            if token.type != "paragraph_open" or token.map is None:
                continue
            start, end = token.map
            content = self.source.tokens[index + 1].content.rstrip()
            match = re.search(r"(?:^|\s)\^([A-Za-z0-9-]+)$", content)
            if match is None:
                if content.startswith("^") and end == start + 1:
                    self.finding("invalid-anchor", start, "Block identifier contains unsupported characters.")
                continue
            anchor = match[1]
            kind, a, b = "block", start, end
            if token.level > 0:
                # List items can be native targets; quote/table interiors cannot.
                owner = next((item for item in self.source.tokens if item.type == "list_item_open"
                              and item.map and item.map[0] <= start < item.map[1]), None)
                quoted = any(item.type == "blockquote_open" and item.map
                             and item.map[0] <= start < item.map[1] for item in self.source.tokens)
                if owner is None or quoted:
                    self.finding("unsupported-anchor", start,
                                 "Native links cannot address the interior of a quote, callout, or table.",
                                 anchor=anchor)
                    continue
                a, b = owner.map
            elif ANCHOR.fullmatch(content):
                previous = [item for item in structured if item.map[1] <= start
                            and all(not line.strip() for line in self.source.lines[item.map[1]:start])]
                if not previous or end != start + 1:
                    self.finding("orphan-anchor", start,
                                 "Standalone block ID must follow one structured block with blank separators.",
                                 anchor=anchor)
                    continue
                chosen = max(previous, key=lambda item: item.map[1])
                a, b = chosen.map
                if start == b or end < len(self.source.lines) and self.source.lines[end].strip():
                    self.finding("anchor-separator", start,
                                 "Standalone block ID needs a blank line before and after.", anchor=anchor)
                kind = "callout" if chosen.type == "blockquote_open" else "block"
            target = Target(self.path, anchor, kind, a, b)
            self.anchors.setdefault(anchor, []).append(target)
        for anchor, targets in self.anchors.items():
            if len(targets) > 1:
                self.finding("duplicate-anchor", targets[-1].start,
                             "Block ID is repeated in this document.", anchor=anchor)

    def _fields(self) -> None:
        inline_lines = set()
        for token in self.source.tokens:
            if token.type == "inline" and token.map:
                inline_lines.update(range(*token.map))
        for line_index in sorted(inline_lines):
            raw = self.source.lines[line_index]
            offset = self.source.offsets[line_index]
            starts = [match for match in RELATIONSHIP_START.finditer(raw)
                      if not any(a <= offset + match.start() < b for a, b in self.source.protected_inline)]
            matches = [match for match in RELATIONSHIP.finditer(raw.rstrip("\r\n"))
                       if not any(a <= offset + match.start() < b for a, b in self.source.protected_inline)]
            for start in starts:
                match = next((item for item in matches if item.start() == start.start()), None)
                if match is None:
                    self.finding("malformed-field", line_index,
                                 "Relationship footer must contain exactly one native link.")
                    continue
                links = [item for item in self.source.links
                         if item.start is not None and offset + match.start() <= item.start
                         and item.end <= offset + match.end()]
                if len(links) != 1 or links[0].image:
                    self.finding("malformed-field", line_index,
                                 "Relationship footer must contain exactly one non-embedded link.")
                    continue
                self.fields.append((line_index, match[1].lower(), links[0]))

    def _units(self) -> None:
        stack: list[Target] = []
        for token in self.source.tokens:
            if token.type not in {"html_block", "clew_comment"} or token.map is None:
                continue
            start, end = token.map
            raw = "".join(self.source.lines[start:end]).strip()
            if token.type == "clew_comment":
                if not raw.endswith("%%"):
                    self.finding("structural-marker", start, "Unclosed Obsidian preparation comment.")
                    continue
            opening, closing, review = OPEN_UNIT.fullmatch(raw), CLOSE_UNIT.fullmatch(raw), REVIEW.fullmatch(raw)
            if opening:
                if stack and stack[-1].kind != "section":
                    self.finding("unit-nesting", start, "Only sections may contain source units.")
                unit = Target(self.path, opening[2], opening[1], start, len(self.source.lines))
                if any(item.id == unit.id for item in self.units + stack):
                    self.finding("duplicate-unit", start, "Source unit ID is repeated.", anchor=unit.id)
                stack.append(unit)
            elif closing:
                if not stack or stack[-1].id != closing[1]:
                    self.finding("unit-boundary", start, "Closing source unit does not match the open unit.")
                    continue
                unit = stack.pop()
                unit.end = end
                if unit.kind == "section":
                    if not any(unit.start < heading["start"] < unit.end for heading in self.source.headings):
                        self.finding("unit-heading", start, "Section needs an existing heading in its scope.")
                else:
                    native = self.anchors.get(unit.id, [])
                    if len(native) != 1 or not unit.start < native[0].start < unit.end:
                        self.finding("unit-anchor", start, "Unit needs one native entry anchor inside its scope.",
                                     anchor=unit.id)
                    else:
                        native[0].kind = unit.kind
                self.units.append(unit)
            elif review:
                try:
                    data = json.loads(review[1])
                    require(isinstance(data, dict) and set(data) == {"code", "message", "anchor"}
                            and isinstance(data["code"], str) and isinstance(data["message"], str),
                            "Invalid review marker.")
                    following = end
                    while following < len(self.source.lines) and not self.source.lines[following].strip():
                        following += 1
                    require(following < len(self.source.lines) and self.source.lines[following].strip()
                            == "> [!warning] Clew review", "Review marker has no visible warning callout.")
                    self.finding(data["code"], start, data["message"], severity="review", anchor=data["anchor"])
                except (ValueError, TypeError) as error:
                    self.finding("review-marker", start, str(error))
            elif token.type == "clew_comment":
                self.finding("structural-marker", start, "Malformed or unsupported preparation marker.")
            if token.type == "html_block" and re.search(r"\b(?:href|src)\s*=", raw, re.I):
                self.finding("html-link", start, "HTML link/resource attributes are outside the checked link syntax.")
        for unit in stack:
            self.finding("unclosed-unit", unit.start, "Source unit has no matching closing marker.", anchor=unit.id)

    def _callouts(self) -> None:
        for token in self.source.tokens:
            if token.type != "blockquote_open" or token.level != 0 or token.map is None:
                continue
            start, end = token.map
            header = CALLOUT.fullmatch(self.source.lines[start].rstrip("\r\n"))
            if header is None:
                continue
            kind = "answer" if header[1].lower() == "reponse" else header[1].lower()
            if kind not in CALLOUT_KINDS:
                continue
            anchors = [target for targets in self.anchors.values() for target in targets
                       if target.start == start and target.end == end]
            if len(anchors) != 1:
                self.finding("callout-anchor", start, "Learning callout needs one standalone native block ID.")
                continue
            target = anchors[0]
            target.kind = kind
            if not all(line.startswith(">") for line in self.source.lines[start:end]):
                self.finding("callout-quoting", start, "Learning callout must quote every line explicitly.",
                             anchor=target.id)
            for line, role, link in self.fields:
                if start < line < end:
                    if role in target.fields:
                        self.finding("duplicate-field", line, f"Duplicate {role} relationship.", anchor=target.id)
                    target.fields[role] = link
            body = [line.lstrip()[1:].strip() for line in self.source.lines[start + 1:end]]
            substantive = [line for line in body if line and not RELATIONSHIP.fullmatch(line)
                           and not line.startswith("[PDF p. ")]
            if not substantive:
                self.finding("empty-callout", start, "Learning callout contains no supplied body content.",
                             severity="error" if kind in {"question", "answer"} else "review", anchor=target.id)
            self.callouts.append(target)
        for unit in self.units:
            for line, role, link in self.fields:
                if unit.start < line < unit.end and not any(
                    item.start <= line < item.end for item in self.callouts):
                    if any(other is not unit and unit.start < other.start <= line < other.end <= unit.end
                           for other in self.units):
                        continue
                    if role in unit.fields:
                        self.finding("duplicate-field", line, f"Duplicate {role} relationship.", anchor=unit.id)
                    unit.fields[role] = link
            if unit.kind in {"exercise", "correction"} and not any(
                unit.start < item.start < item.end < unit.end for item in self.callouts
                if item.kind == ("question" if unit.kind == "exercise" else "answer")):
                self.finding("empty-unit", unit.start, f"{unit.kind.capitalize()} has no addressed source blocks.",
                             severity="review", anchor=unit.id)
        for line, role, _ in self.fields:
            if not any(item.start <= line < item.end for item in self.units + self.callouts):
                self.finding("orphan-field", line, f"{role} relationship has no owning source unit.")

    def _headings(self) -> None:
        if self.metadata.type == "chapter":
            return
        previous = 0
        for heading in self.source.headings:
            start = heading["start"]
            if previous and heading["level"] > previous + 1:
                self.finding("heading-gap", start,
                             f"Heading level jumps from {previous} to {heading['level']}.", severity="review")
            previous = heading["level"]
            kind = heading["kind"]
            owning = [unit for unit in self.units if unit.start <= start < unit.end]
            entry = next((unit for unit in owning if not any(
                other["start"] < start and unit.start < other["start"] < unit.end
                for other in self.source.headings)), None)
            if entry is None or entry.kind != kind:
                self.finding("unclassified-unit", start, f"Review the {kind} heading: {heading['label']}",
                             severity="review")

    def enclosing_unit(self, item: Target, kind: str) -> Target | None:
        owners = [unit for unit in self.units if unit.kind == kind
                  and unit.start < item.start < item.end < unit.end]
        return owners[0] if len(owners) == 1 else None


def resolve_link(link: Link, origin: Note, notes: dict[str, Note], files: set[str],
                 findings: list[Finding], pdf_counts: dict[str, int]) -> Target | None:
    def finding(code, message, severity="error"):
        findings.append(Finding(code=code, severity=severity, path=origin.path,
                                line=link.line + origin.header_lines, message=message, target=link.target))

    try:
        parsed = urlsplit(link.target)
    except ValueError as error:
        finding("invalid-link", str(error))
        return None
    if parsed.scheme or link.target.startswith("//"):
        if parsed.scheme.lower() not in SAFE_SCHEMES and not link.target.startswith("//"):
            finding("unsafe-link", "Unsupported or active URL scheme.")
        else:
            finding("external-link", "External destination was not checked remotely.", "review")
        return None
    path, fragment = unquote(parsed.path), unquote(parsed.fragment)
    if "\\" in path or path.startswith("/") or PureWindowsPath(path).drive or parsed.query:
        finding("invalid-local-link", "Use a relative portable path without a query.")
        return None
    if any(ord(char) < 32 for char in path + fragment):
        finding("invalid-local-link", "Local path/fragment contains a control character.")
        return None
    if any(part.startswith(".") and part not in {".", ".."} for part in path.split("/")):
        finding("private-link", "Links must not target private/configuration files.")
        return None
    target = posixpath.normpath(posixpath.join(posixpath.dirname(origin.path), path)) if path else origin.path
    if target.startswith("../") or target in {".", ".."}:
        finding("escaping-link", "Relative link escapes the selected chapter.")
        return None
    if link.kind == "wiki" and path:
        options = {name for name in files if name in {target, target + ".md", path, path + ".md"}
                   or name.endswith("/" + path) or name.endswith("/" + path + ".md")}
    else:
        options = {name for name in files if name.casefold() == target.casefold()}
    if len(options) != 1:
        finding("ambiguous-link" if options else "missing-link",
                "Destination is ambiguous." if options else "Destination does not exist in the chapter.")
        return None
    target = next(iter(options))
    if target.startswith(".") or any(part.startswith(".") for part in target.split("/")):
        finding("private-link", "Links must not target private/configuration files.")
        return None
    if target.lower().endswith(".pdf"):
        if fragment and (re.fullmatch(r"page=[1-9][0-9]*", fragment) is None
                         or not 1 <= int(fragment[5:]) <= pdf_counts.get(target, 0)):
            finding("pdf-page", "PDF fragment must identify an existing original page with page=N.")
        return Target(target, fragment, "pdf", 0, 0)
    if not fragment:
        return Target(target, "", "note" if target in notes else "asset", 0, 0)
    if target not in notes:
        finding("asset-fragment", "Fragment syntax is unsupported for this asset.")
        return None
    note = notes[target]
    if fragment.startswith("^"):
        targets = note.anchors.get(fragment[1:], [])
        if len(targets) != 1:
            finding("missing-anchor" if not targets else "ambiguous-anchor",
                    "Block target is missing or duplicated.")
            return None
        return targets[0]
    headings = [heading for heading in note.source.headings if fragment in {heading["label"], heading["text"]}]
    if len(headings) != 1:
        finding("missing-heading" if not headings else "ambiguous-heading",
                "Heading target is missing or duplicated; use a block ID for repeated headings.")
        return None
    return Target(target, fragment, "section", headings[0]["start"], headings[0]["end"])


def validate_notes(notes: dict[str, Note], files: set[str], pdf_counts: dict[str, int]) -> list[Finding]:
    findings = [finding for note in notes.values() for finding in note.findings]
    identifiers = {}
    registry = {(note.path, unit.id): unit for note in notes.values() for unit in note.units}
    registry.update({(note.path, item.id): item for note in notes.values() for item in note.callouts})
    for note in notes.values():
        if note.metadata.id in identifiers:
            note.finding("duplicate-document-id", 0, "Document ID is used by another note.")
            findings.append(note.findings[-1])
        identifiers[note.metadata.id] = note.path
        for line, label in note.source.unresolved_references:
            findings.append(Finding(code="undefined-reference", severity="error", path=note.path,
                                    line=line + note.header_lines, message=f"Undefined reference link: [{label}]"))
        for duplicate in note.source.environment.get("duplicate_refs", []):
            findings.append(Finding(code="duplicate-reference", severity="error", path=note.path,
                                    line=duplicate["map"][0] + note.header_lines + 1,
                                    message=f"Duplicate reference definition: [{duplicate['label']}]"))
        for token in note.source.tokens:
            if token.type == "inline":
                for child in token.children or []:
                    if child.type == "html_inline" and re.search(r"\b(?:href|src)\s*=", child.content, re.I):
                        findings.append(Finding(code="html-link", severity="error", path=note.path,
                                                line=(token.map or [0])[0] + note.header_lines + 1,
                                                message="HTML link/resource attributes are not checked link syntax."))
        for link in note.source.links:
            resolve_link(link, note, notes, files, findings, pdf_counts)
        for item in note.units + note.callouts:
            resolved = {}
            invalid_fields = set()
            for key, link in item.fields.items():
                target = resolve_link(link, note, notes, files, [], pdf_counts)
                if target is not None:
                    resolved[key] = registry.get((target.path, target.id), target)
                else:
                    invalid_fields.add(key)
            allowed = {"exercise"} if item.kind == "correction" else (
                {"question"} if item.kind == "answer" else set())
            for key in item.fields.keys() - allowed:
                findings.append(Finding(code="unexpected-field", severity="error", path=note.path,
                                        line=item.start + note.header_lines + 1,
                                        message=f"{key} is not a relationship for {item.kind}.", anchor=item.id))
            owner_key = {"question": "exercise", "answer": "correction"}.get(item.kind)
            owner = note.enclosing_unit(item, owner_key) if owner_key else None
            if owner_key:
                if owner is None:
                    findings.append(Finding(code="unit-owner", severity="error", path=note.path,
                                            line=item.start + note.header_lines + 1, anchor=item.id,
                                            message=f"{item.kind.capitalize()} needs its enclosing {owner_key} unit."))
            if item.kind == "correction":
                exercise = resolved.get("exercise")
                if exercise is None and "exercise" not in invalid_fields:
                    findings.append(Finding(code="unmatched-correction", severity="review", path=note.path,
                                            line=item.start + note.header_lines + 1, anchor=item.id,
                                            message="This supplied correction has no verified exercise match."))
                elif exercise is not None and exercise.kind != "exercise":
                    findings.append(Finding(code="relationship-kind", severity="error", path=note.path,
                                            line=item.start + note.header_lines + 1, anchor=item.id,
                                            message="Correction must reference an exercise unit."))
            if item.kind == "answer":
                question = resolved.get("question")
                if question is None and "question" not in invalid_fields:
                    findings.append(Finding(code="unmatched-answer", severity="review", path=note.path,
                                            line=item.start + note.header_lines + 1, anchor=item.id,
                                            message="This supplied answer has no verified question match."))
                elif question is not None:
                    correction = owner
                    if question.kind != "question" or question.path not in notes:
                        findings.append(Finding(code="relationship-kind", severity="error", path=note.path,
                                                line=item.start + note.header_lines + 1, anchor=item.id,
                                                message="Answer must reference an addressed question."))
                        continue
                    question_note = notes[question.path]
                    question_owner = question_note.enclosing_unit(question, "exercise")
                    correction_exercise = resolve_link(correction.fields["exercise"], note, notes, files, [],
                                                       pdf_counts) if correction and "exercise" in correction.fields else None
                    if question.kind != "question" or question_owner is None or correction_exercise is None \
                            or (question_owner.path, question_owner.id) != (
                                correction_exercise.path, correction_exercise.id):
                        findings.append(Finding(code="answer-exercise", severity="error", path=note.path,
                                                line=item.start + note.header_lines + 1, anchor=item.id,
                                                message="Answer target disagrees with its correction's exercise."))
    unique = {}
    for finding in findings:
        key = finding.code, finding.path, finding.message, finding.anchor, finding.target
        unique.setdefault(key, finding)
    return sorted(unique.values(), key=lambda item: (item.path, item.line, item.code, item.message))
