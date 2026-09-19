"""Read-only validation of one Clew course and its linked shared concepts."""

from __future__ import annotations

import argparse
from collections import Counter, deque
from dataclasses import dataclass
import hashlib
from itertools import zip_longest
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from urllib.parse import parse_qsl, unquote, urlsplit

try:
    import yaml
except ImportError:
    yaml = None

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError
except ImportError:
    Draft202012Validator = None


COURSE_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
DEVICE = re.compile(r"^(?:con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\.|$)", re.I)
WIKI = re.compile(r"!?\[\[([^\]\n]+)\]\]")
HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
RELATIONS = ("teaches", "prerequisites", "similar", "related")


def diagnostic(items, code, path, message):
    items.append({"code": code, "path": str(path), "message": message})


def valid_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    return all(
        part not in {"", ".", ".."}
        and not part.startswith(".")
        and not part.endswith((" ", "."))
        and not any(ord(char) < 32 or ord(char) == 127 for char in part)
        and not re.search(r'[<>:"|?*#%^\[\]]', part)
        and not DEVICE.match(part)
        for part in value.split("/")
    )


def reparse(info):
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def note_kind(name):
    parts = name.split("/")
    if len(parts) == 2 and parts[0] == "concepts" and name.endswith(".md"):
        return "concept"
    if len(parts) < 3 or parts[0] != "courses" or not COURSE_KEY.fullmatch(parts[1]):
        return None
    if len(parts) == 3 and parts[2] == "course.md":
        return "course"
    if len(parts) == 4 and name.endswith(".md"):
        return {"chapters": "chapter", "sections": "section"}.get(parts[2])
    return None


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate property: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Invalid JSON numeric constant: {value}")


def parse_json(raw):
    return json.loads(
        raw.decode("utf-8-sig"), object_pairs_hook=unique_pairs,
        parse_constant=reject_constant,
    )


def prose(text):
    text = re.sub(r"(?ms)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[ \t]*$", "", text)
    return re.sub(r"`+[^`\n]*`+", "", text)


def frontmatter(raw):
    text = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    if not text.startswith("---\n"):
        raise ValueError("Missing Clew YAML frontmatter.")
    end = re.search(r"(?m)^---[ \t]*$", text[4:])
    if not end:
        raise ValueError("Unclosed YAML frontmatter.")

    class UniqueLoader(yaml.SafeLoader):
        pass

    def mapping(loader, node, deep=False):
        pairs = loader.construct_pairs(node, deep=deep)
        if any(not isinstance(key, str) for key, _ in pairs):
            raise ValueError("YAML property names must be strings.")
        return unique_pairs(pairs)

    UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
    data = yaml.load(text[4:4 + end.start()], Loader=UniqueLoader)
    return data, text[4 + end.end():].lstrip("\n")


def links(text):
    """Yield literal destinations, without treating code samples as active links."""
    text = prose(text)
    for match in WIKI.finditer(text):
        yield match.group(1).replace("\\|", "|").split("|", 1)[0]
    text = WIKI.sub("", text)
    definitions = {}
    for match in re.finditer(r"(?m)^ {0,3}\[([^\]]+)\]:[ \t]*(<[^>]+>|\S+)", text):
        definitions[match.group(1).casefold()] = match.group(2).strip("<>")
        yield match.group(2).strip("<>")
    text = re.sub(r"(?m)^ {0,3}\[[^\]]+\]:.*$", "", text)
    for match in re.finditer(r"!?\[([^\]\n]*)\](?:\[([^\]\n]*)\])?", text):
        end = match.end()
        if end < len(text) and text[end] == "(":
            start = end + 1
            if text[start:start + 1] == "<":
                close = text.find(">", start + 1)
                if close != -1:
                    yield text[start + 1:close]
                continue
            depth, cursor = 1, start
            while cursor < len(text) and depth:
                if text[cursor] == "(" and text[cursor - 1:cursor] != "\\":
                    depth += 1
                elif text[cursor] == ")" and text[cursor - 1:cursor] != "\\":
                    depth -= 1
                cursor += 1
            if depth == 0:
                target = re.sub(r"""\s+["'].*["']$""", "", text[start:cursor - 1].strip())
                yield target.replace("\\(", "(").replace("\\)", ")")
        else:
            label = (match.group(2) or match.group(1)).casefold()
            if label in definitions:
                yield definitions[label]
            elif match.group(2) is not None:
                yield f"UNDEFINED-REFERENCE:{label}"
    for match in re.finditer(
        r"""<(?:img|a|source|video|audio)\b[^>]*?\b(?:src|href)=["']([^"']+)["']""",
        text, re.I,
    ):
        yield match.group(1)


def body_section(body, heading):
    matches = list(re.finditer(r"(?m)^## " + re.escape(heading) + r"[ \t]*$", prose(body)))
    if len(matches) != 1:
        return None
    tail = prose(body)[matches[0].end():]
    return re.split(r"(?m)^#{1,2} ", tail, maxsplit=1)[0]


@dataclass
class Note:
    path: str
    data: dict
    body: str


class ClewValidator:
    def __init__(self, vault, course, strict):
        self.root = Path(os.path.abspath(vault))
        self.prefix = f"courses/{course}"
        self.entry = f"{self.prefix}/course.md"
        self.strict = strict
        self.errors = []
        self.warnings = []
        self.files = set()
        self.bytes = {}
        self.paths = {}
        self.directories = {}
        self.notes = {}
        self.identities = {}
        self.concepts = set()
        self.external_notes = set()
        self.refs = {}
        self.body_refs = {}
        self.sources = {}
        self.pdf_counts = {}
        self.mappings = {}
        self.coverage = {}
        self.sequence = []
        self.schemas = {}

    def error(self, code, path, message):
        diagnostic(self.errors, code, path, message)

    def warn(self, code, path, message, readiness=False):
        diagnostic(self.errors if readiness and self.strict else self.warnings, code, path, message)

    def report(self):
        return {
            "schema": "clew-validation/v1", "ok": not self.errors,
            "strict": self.strict, "course": self.prefix,
            "errors": self.errors, "warnings": self.warnings,
            "scope": {
                "concepts": sorted(self.concepts),
                "external_notes": sorted(self.external_notes),
            },
        }

    def safe_path(self, relative, directory=False):
        key = (relative, directory)
        if key in self.paths:
            return self.paths[key]
        self.paths[key] = None
        if not valid_path(relative) or relative.split("/")[0] not in {"courses", "concepts"}:
            self.error("path", relative, "Expected a safe vault-relative content path.")
            return None
        path = self.root
        try:
            for component in relative.split("/"):
                if path not in self.directories:
                    self.directories[path] = {entry.name for entry in path.iterdir()}
                if component not in self.directories[path]:
                    case_match = any(name.casefold() == component.casefold() for name in self.directories[path])
                    self.error("case" if case_match else "missing", relative,
                               "Path case does not match." if case_match else "Target does not exist.")
                    return None
                path /= component
                info = path.lstat()
                if reparse(info):
                    self.error("path", relative, "Symlinks and reparse points are not allowed.")
                    return None
            if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
                self.error("path", relative, "Expected a directory." if directory else "Expected a regular file.")
                return None
        except OSError as exc:
            self.error("io", relative, str(exc))
            return None
        self.paths[key] = path
        return path

    def read(self, relative):
        if relative not in self.bytes:
            path = self.safe_path(relative)
            if path is None:
                return None
            try:
                self.bytes[relative] = path.read_bytes()
            except OSError as exc:
                self.error("io", relative, str(exc))
                return None
        return self.bytes[relative]

    def file_hash(self, relative):
        if relative in self.bytes:
            return hashlib.sha256(self.bytes[relative]).hexdigest()
        path = self.safe_path(relative)
        if path is None:
            return None
        try:
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as exc:
            self.error("io", relative, str(exc))
            return None

    def schema_ok(self, value, schema, location):
        problems = sorted(self.schemas[schema].iter_errors(value), key=lambda item: str(list(item.path)))
        for problem in problems:
            field = ".".join(map(str, problem.path))
            self.error("schema", location, f"{field or '$'}: {problem.message}")
        return not problems

    def document(self, name, schema):
        raw = self.read(name)
        if raw is None:
            return None
        try:
            data = parse_json(raw)
        except (ValueError, UnicodeError, RecursionError) as exc:
            self.error("json", name, str(exc))
            return None
        return data if self.schema_ok(data, schema, name) else None

    def load_note(self, name):
        if name in self.notes:
            return self.notes[name]
        self.notes[name] = None
        expected = note_kind(name)
        if expected is None:
            self.error("layout", name, "Not a Clew note location.")
            return None
        raw = self.read(name)
        if raw is None:
            return None
        try:
            data, body = frontmatter(raw)
        except (yaml.YAMLError, ValueError, UnicodeError, RecursionError) as exc:
            self.error("metadata", name, str(exc))
            return None
        if not self.schema_ok(data, "note", name):
            return None
        if data["kind"] != expected:
            self.error("kind", name, f"Location requires kind: {expected}.")
            return None
        identity = data["id"]
        if identity in self.identities:
            self.error("identity", name, f"ID already used by {self.identities[identity]}.")
        else:
            self.identities[identity] = name
        note = Note(name, data, body)
        self.notes[name] = note
        if len([match for match in HEADING.finditer(prose(body)) if len(match.group(1)) == 1]) != 1:
            self.error("body", name, "Exactly one title heading is required.")
        return note

    def inventory(self):
        root = self.safe_path(self.prefix, directory=True)
        if root is None:
            return
        folded = set()
        for current, directories, files in os.walk(root, followlinks=False):
            directories.sort()
            for name in list(directories):
                path = Path(current) / name
                relative = path.relative_to(self.root).as_posix()
                local = path.relative_to(root).parts
                if len(local) != 1 or local[0] not in {"chapters", "sections", "sources", "assets", "support"}:
                    self.error("layout", relative, "Directory is outside the fixed course layout.")
                    directories.remove(name)
                elif self.safe_path(relative, directory=True) is None:
                    directories.remove(name)
            for name in sorted(files):
                path = Path(current) / name
                relative = path.relative_to(self.root).as_posix()
                local = path.relative_to(root).parts
                extension = path.suffix.lower()
                allowed = (
                    relative == self.entry
                    or len(local) == 2 and (
                        local[0] in {"chapters", "sections"} and path.suffix == ".md"
                        or local[0] == "sources" and extension == ".pdf"
                        or local[0] == "assets" and extension in IMAGES
                        or local[0] == "support" and name in {"source-map.json", "verification.json"}
                    )
                )
                if not allowed:
                    self.error("layout", relative, "File is outside the fixed course layout.")
                    continue
                if relative.casefold() in folded:
                    self.error("collision", relative, "Case-insensitive path collision.")
                folded.add(relative.casefold())
                if self.safe_path(relative) is not None:
                    self.files.add(relative)

    def anchor(self, origin, target, anchor):
        if target.lower().endswith(".pdf"):
            try:
                pairs = parse_qsl(anchor, keep_blank_values=True, strict_parsing=True)
                params = unique_pairs(pairs)
                if not params or set(params) - {"page", "height", "selection", "annotation", "offset", "color", "rect"}:
                    raise ValueError("Unsupported PDF viewer fragment.")
                if "page" not in params and set(params) != {"height"}:
                    raise ValueError("PDF selection/position links require a physical page.")
                for key in ("page", "height"):
                    if key in params and not re.fullmatch(r"[1-9]\d*", params[key]):
                        raise ValueError(f"PDF {key} must be a positive integer.")
                if "page" in params:
                    count = self.pdf_counts.get(target)
                    if count is None or int(params["page"]) > count:
                        raise ValueError("PDF page is outside its declared source-map bounds.")
                if "selection" in params and not re.fullmatch(r"\d+,\d+,\d+,\d+", params["selection"]):
                    raise ValueError("Invalid PDF selection.")
                for key, size in (("offset", 3), ("rect", 4)):
                    if key in params:
                        values = params[key].split(",")
                        if len(values) != size or not all(math.isfinite(float(value)) for value in values):
                            raise ValueError(f"Invalid PDF {key}.")
                if any(not value for value in params.values()):
                    raise ValueError("Empty PDF viewer parameter.")
            except ValueError as exc:
                self.error("anchor", origin, str(exc))
            return
        note = self.load_note(target)
        if note is None:
            self.error("anchor", origin, f"Anchor target is not a valid note: {target}")
            return
        body = prose(note.body)
        if anchor.startswith("^"):
            matches = re.findall(r"(?m)(?:^|\s)\^" + re.escape(anchor[1:]) + r"[ \t]*$", body)
        else:
            matches = [match for match in HEADING.finditer(body) if match.group(2).casefold() == anchor.casefold()]
        if len(matches) != 1:
            self.error("anchor", origin, f"Missing or ambiguous anchor in {target}: {anchor}")

    def resolve(self, origin, target, expected=None, fragment=True):
        try:
            uri = urlsplit(target.strip())
        except ValueError as exc:
            self.error("link", origin, str(exc))
            return None
        if uri.scheme.lower() in {"https", "http", "mailto"} and expected is None:
            return None
        if uri.scheme or uri.netloc or uri.query:
            self.error("link", origin, f"Unsupported local target: {target}")
            return None
        name, anchor = unquote(uri.path), unquote(uri.fragment)
        if not name and anchor:
            name = origin
        if not PurePosixPath(name).suffix:
            name += ".md"
        kind = note_kind(name)
        selected_file = name.startswith(self.prefix + "/") and name in self.files
        if not valid_path(name) or not (selected_file or kind is not None):
            self.error("link", origin, f"Target is outside Clew content or the selected course: {target}")
            return None
        if self.safe_path(name) is None:
            return None
        if expected and (kind if expected != "pdf" else "pdf" if name.lower().endswith(".pdf") else None) != expected:
            self.error("kind", origin, f"Expected {expected} target: {target}")
            return None
        if not fragment and anchor:
            self.error("link", origin, f"Expected a whole-note target: {target}")
            return None
        if kind:
            if self.load_note(name) is None:
                return None
            if kind == "concept":
                self.concepts.add(name)
            elif not name.startswith(self.prefix + "/"):
                self.external_notes.add(name)
        if anchor:
            self.anchor(origin, name, anchor)
        return name, anchor

    def process_note(self, note):
        data, path = note.data, note.path
        refs = {}
        expected = {
            "course": "course",
            "parent": "course" if data["kind"] == "chapter" else "chapter",
            "children": "chapter" if data["kind"] == "course" else "section",
            "previous": "section", "next": "section", "evidence": "section", "source_refs": "pdf",
            **{field: "concept" for field in RELATIONS},
        }
        for field, target_kind in expected.items():
            if field not in data:
                continue
            values = data[field] if isinstance(data[field], list) else [data[field]]
            refs[field] = [
                self.resolve(path, value[2:-2], target_kind, field in {"evidence", "source_refs"})
                if value is not None else None for value in values
            ]
            present = [value for value in refs[field] if value is not None]
            if len(present) != len(set(present)):
                self.error("reference", path, f"{field} contains duplicate resolved targets.")
        self.refs[path] = refs
        visible = {resolved for target in links(note.body) if (resolved := self.resolve(path, target)) is not None}
        self.body_refs[path] = visible
        for field in ("course", "parent", "previous", "next", "source_refs", "evidence", *RELATIONS):
            for target in refs.get(field, []):
                if target is not None and target not in visible:
                    self.error("visible-link", path, f"{field} target must also appear in the body: {target[0]}")
        if data["kind"] == "concept":
            definition = body_section(note.body, "Definition")
            definition_prose = WIKI.sub("", definition or "")
            definition_prose = re.sub(r"!?\[[^\]\n]*\](?:\([^)\n]*\)|\[[^\]\n]*\])", "", definition_prose)
            if definition is None or not re.search(r"\w", definition_prose):
                self.error("definition", path, "Shared concepts require their own nonempty ## Definition.")
            evidence_body = body_section(note.body, "Evidence")
            evidence_links = {
                resolved for target in links(evidence_body or "")
                if (resolved := self.resolve(path, target)) is not None
            }
            if evidence_body is None or not set(refs.get("evidence", [])) <= evidence_links:
                self.error("evidence", path, "## Evidence must display the declared supporting section links.")
            for field in RELATIONS:
                if (path, "") in refs.get(field, []):
                    self.error("relationship", path, f"{field} must not refer to the same concept.")
        if data["kind"] == "section" and len(re.findall(r"\b\w+\b", prose(note.body))) > 1200:
            self.warn("chunk-size", path, "Section exceeds the 1,200-word guideline; review its semantic boundary.")

    def targets(self, path, field):
        return [target[0] for target in self.refs.get(path, {}).get(field, []) if target is not None]

    def check_contents(self, path, expected):
        note = self.notes.get(path)
        if note is None:
            return
        content = body_section(note.body, "Contents")
        visible = []
        if content is not None:
            for line in content.splitlines():
                if re.match(r"^\s*\d+[.)]\s+", line):
                    targets = list(links(line))
                    result = self.resolve(path, targets[0], fragment=False) if targets else None
                    visible.append(result[0] if result else None)
        if content is None or visible != expected:
            self.error("contents", path, "## Contents must list children once, in frontmatter order.")

    def hierarchy(self):
        chapters = {name for name in self.files if note_kind(name) == "chapter"}
        sections = {name for name in self.files if note_kind(name) == "section"}
        ordered_chapters = self.targets(self.entry, "children")
        if Counter(ordered_chapters) != Counter(chapters):
            self.error("hierarchy", self.entry, "children must include every chapter exactly once.")
        self.check_contents(self.entry, ordered_chapters)
        parents = {}
        for chapter in ordered_chapters:
            children = self.targets(chapter, "children")
            self.check_contents(chapter, children)
            for field in ("course", "parent"):
                if self.targets(chapter, field) != [self.entry]:
                    self.error("hierarchy", chapter, f"{field} must point to the course entry.")
            for child in children:
                parents[child] = chapter
            self.sequence.extend(children)
        if Counter(self.sequence) != Counter(sections):
            self.error("hierarchy", self.entry, "Every section must occur once in chapter children.")
        for index, path in enumerate(self.sequence):
            if self.targets(path, "course") != [self.entry] or self.targets(path, "parent") != [parents[path]]:
                self.error("hierarchy", path, "Section course/parent disagrees with the reading tree.")
            for field, expected in (
                ("previous", self.sequence[index - 1] if index else None),
                ("next", self.sequence[index + 1] if index + 1 < len(self.sequence) else None),
            ):
                actual = self.refs.get(path, {}).get(field, [])
                if actual != ([(expected, "")] if expected else [None]):
                    self.error("sequence", path, f"{field} disagrees with the flattened section sequence.")

    def check_span(self, span, path):
        source = self.sources.get(span["source_id"])
        start, end = span["page_start"], span["page_end"]
        if source is None or not 1 <= start <= end <= source["page_count"]:
            self.error("source-span", path, "Unknown source or out-of-bounds/reversed physical page range.")
            return False
        if any(not start <= int(page) <= end for page in span.get("printed_pages", {})):
            self.error("source-span", path, "Printed-page mappings must be inside their physical span.")
        if "rect" in span:
            x0, y0, x1, y1 = span["rect"]
            if start != end or not all(math.isfinite(value) for value in span["rect"]) or x0 >= x1 or y0 >= y1:
                self.error("source-span", path, "A rectangle needs one page, finite coordinates and positive area.")
        return True

    def source_map(self, data, path):
        course = self.notes.get(self.entry)
        if course and data["course_id"] != course.data["id"]:
            self.error("identity", path, "Source-map course_id does not match the course.")
        source_paths = set()
        for source in data["sources"]:
            identity, name = source["id"], source["path"]
            if identity in self.sources:
                self.error("identity", path, f"Duplicate source ID: {identity}")
                continue
            self.sources[identity] = source
            self.coverage[identity] = []
            if name is None:
                if not source["omission_reason"]:
                    self.error("source", path, "Omitted PDFs require omission_reason.")
                self.warn("source-omitted", path, f"Original PDF is not included: {source['filename']}")
                continue
            if source["omission_reason"] is not None:
                self.error("source", path, "Included PDFs must have omission_reason: null.")
            if name in source_paths:
                self.error("source", path, f"PDF path is declared more than once: {name}")
            source_paths.add(name)
            if name not in self.files or not name.startswith(self.prefix + "/sources/") or not name.lower().endswith(".pdf"):
                self.error("source", path, f"PDF must be in this course's sources directory: {name}")
                continue
            actual_hash = self.file_hash(name)
            if actual_hash is not None and actual_hash != source["sha256"]:
                self.error("hash", name, "Source SHA-256 does not match actual bytes.")
            self.pdf_counts[name] = source["page_count"]
        actual_pdfs = {name for name in self.files if name.lower().endswith(".pdf")}
        if actual_pdfs != source_paths:
            self.error("source", path, "Source map must declare every included PDF exactly once.")
        mapped_paths = set()
        for record in data["sections"]:
            name, identity = record["path"], record["id"]
            if identity in self.mappings or name in mapped_paths:
                self.error("identity", path, "Duplicate section ID/path in source map.")
                continue
            mapped_paths.add(name)
            if name not in self.files or note_kind(name) != "section":
                self.error("source", path, f"Mapped section is outside this course: {name}")
                continue
            note = self.notes.get(name)
            if note is None or note.data["id"] != identity:
                self.error("identity", name, "Mapped section ID disagrees with its note.")
                continue
            self.mappings[identity] = record
            for spans in [record["spans"], *(alternative["spans"] for alternative in record.get("alternatives", []))]:
                for span in spans:
                    if self.check_span(span, name):
                        self.coverage[span["source_id"]].append((span["page_start"], span["page_end"], identity))
            for item in record.get("items", []):
                self.anchor(name, name, item["anchor"])
                for span in item["spans"]:
                    if not self.check_span(span, name):
                        continue
                    cursor = span["page_start"]
                    for start, end in sorted(
                        (parent["page_start"], parent["page_end"]) for parent in record["spans"]
                        if parent["source_id"] == span["source_id"]
                    ):
                        if start > cursor:
                            break
                        if end >= cursor:
                            cursor = end + 1
                    if cursor <= span["page_end"]:
                        self.error("source-span", name, "Item spans must be contained in primary section coverage.")
                asset = item.get("asset_path")
                if asset is not None and (asset not in self.files or not asset.startswith(self.prefix + "/assets/")):
                    self.error("asset", name, f"Item asset must be in the course's assets directory: {asset}")
        expected_paths = {name for name in self.files if note_kind(name) == "section"}
        if mapped_paths != expected_paths:
            self.error("source", path, "Source map must include every section exactly once.")

    def primary_refs(self, records, first_only=False):
        seen = set()
        for record in records:
            for span in record["spans"]:
                source = self.sources.get(span["source_id"])
                if source is None or source["path"] is None:
                    continue
                start, end = span["page_start"], span["page_end"]
                if not 1 <= start <= end <= source["page_count"]:
                    continue
                for page in range(int(start), int(end) + 1):
                    key = source["path"] if first_only else (source["path"], page)
                    if key not in seen:
                        seen.add(key)
                        yield source["path"], f"page={page}"
                    if first_only:
                        break

    def check_source_refs(self):
        by_path = {record["path"]: record for record in self.mappings.values()}
        for name, note in list(self.notes.items()):
            if note is None or name not in self.files:
                continue
            if note.data["kind"] == "section":
                records = [by_path[name]] if name in by_path else []
            else:
                children = self.targets(name, "children") if note.data["kind"] == "chapter" else self.sequence
                records = [by_path[child] for child in children if child in by_path]
            expected = self.primary_refs(records, first_only=note.data["kind"] != "section")
            actual = self.refs.get(name, {}).get("source_refs", [])
            if any(left != right for left, right in zip_longest(expected, actual)):
                self.error("source-refs", name, "source_refs disagrees with primary source-map coverage.")
            for record in records:
                for span in record["spans"]:
                    source = self.sources.get(span["source_id"])
                    if source and source["path"] is None and source["filename"] not in note.body:
                        self.error("source-citation", name, "Omitted originals need visible filename/page citations.")
                if note.data["kind"] == "section":
                    for item in record.get("items", []):
                        if "asset_path" in item and (item["asset_path"], "") not in self.body_refs.get(name, set()):
                            self.error("asset", name, "Mapped item asset must be linked in its section body.")

    def concepts_and_assets(self):
        graph = {
            name: set(self.targets(name, "prerequisites")) & self.concepts
            for name in self.concepts
        }
        indegree = {name: 0 for name in graph}
        for targets in graph.values():
            for target in targets:
                indegree[target] += 1
        pending = deque(sorted(name for name, count in indegree.items() if count == 0))
        visited = set()
        while pending:
            name = pending.popleft()
            visited.add(name)
            for target in graph[name]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    pending.append(target)
        if len(visited) != len(graph):
            self.error("prerequisite-cycle", "concepts", "Cyclic prerequisites: " + ", ".join(sorted(set(graph) - visited)))
        used_assets = {
            target for name, targets in self.body_refs.items() if note_kind(name) == "section" and name in self.files
            for target, _ in targets
        }
        for name in sorted(self.files):
            if name.startswith(self.prefix + "/assets/") and name not in used_assets:
                self.error("asset", name, "Asset is not linked from a section body.")
        for identity in self.sources:
            if identity in self.identities:
                self.error("identity", self.identities[identity], "Source IDs and note IDs must be distinct.")
        for name in sorted(self.external_notes):
            self.warn("external-evidence", name, "Referenced note checked only; validate its course separately.")

    def verification(self, data, path, source_map_path):
        course = self.notes.get(self.entry)
        if course and data["course_id"] != course.data["id"]:
            self.error("identity", path, "Verification course_id does not match the course.")
        raw_map = self.read(source_map_path)
        if raw_map is not None and hashlib.sha256(raw_map).hexdigest() != data["source_map_sha256"]:
            self.error("hash", path, "Source-map SHA-256 is stale.")
        seen = set()
        for record in data["sections"]:
            identity = record["id"]
            if identity in seen:
                self.error("verification", path, f"Duplicate section verification: {identity}")
            seen.add(identity)
            mapping = self.mappings.get(identity)
            if mapping is None:
                self.error("verification", path, f"Unknown section verification: {identity}")
                continue
            name = mapping["path"]
            note = self.notes[name]
            raw = self.read(name)
            if raw is not None and hashlib.sha256(raw).hexdigest() != record["markdown_sha256"]:
                self.error("hash", name, "Markdown SHA-256 is stale.")
            if record["fidelity"] != note.data["fidelity"]:
                self.error("fidelity", name, "Note and verification fidelity disagree.")
            if record["fidelity"] != "verified":
                self.warn("fidelity", name, f"Section is {record['fidelity']}.", readiness=True)
        if seen != set(self.mappings):
            self.error("verification", path, "Verification must include every section exactly once.")
        pages, counts = set(), Counter()
        for record in data["pages"]:
            identity, page = record["source_id"], record["page"]
            source = self.sources.get(identity)
            if source is None or not 1 <= page <= source["page_count"]:
                self.error("verification", path, "Unknown source or out-of-bounds report page.")
                continue
            key = identity, page
            if key in pages:
                self.error("verification", path, f"Duplicate page record: {identity} page {page}")
            else:
                pages.add(key)
                counts[identity] += 1
            expected = {section for start, end, section in self.coverage[identity] if start <= page <= end}
            if set(record["section_ids"]) != expected:
                self.error("coverage", path, f"Page assignments disagree with source spans: {identity} page {page}")
            if record["status"] == "unresolved":
                self.warn("coverage", path, f"Unresolved coverage: {identity} page {page}: {record['reason']}", readiness=True)
        if any(counts[identity] != source["page_count"] for identity, source in self.sources.items()):
            self.error("coverage", path, "Every physical page of every source requires exactly one report record.")

    def run(self):
        try:
            for path in (self.root, *self.root.parents):
                if reparse(path.lstat()):
                    self.error("path", "vault", "Vault ancestors must not be symlinks or reparse points.")
                    return self.report()
            if not self.root.is_dir():
                self.error("path", "vault", "Expected an explicit vault directory.")
                return self.report()
            directory = Path(__file__).resolve().parent.parent / "schemas"
            for name in ("note", "source-map", "verification"):
                schema = parse_json((directory / f"{name}.schema.json").read_bytes())
                Draft202012Validator.check_schema(schema)
                self.schemas[name] = Draft202012Validator(schema)
            self.inventory()
            for name in sorted(self.files):
                if note_kind(name):
                    self.load_note(name)
            if self.load_note(self.entry) is None:
                return self.report()
            source_path = f"{self.prefix}/support/source-map.json"
            report_path = f"{self.prefix}/support/verification.json"
            source_map = self.document(source_path, "source-map")
            verification = self.document(report_path, "verification")
            if source_map is not None:
                self.source_map(source_map, source_path)
            pending = deque(sorted(name for name in self.files if note_kind(name)))
            processed = set()
            while pending:
                name = pending.popleft()
                if name in processed:
                    continue
                processed.add(name)
                note = self.load_note(name)
                if note is not None:
                    self.process_note(note)
                pending.extend(sorted(self.concepts - processed))
            self.hierarchy()
            self.check_source_refs()
            self.concepts_and_assets()
            if source_map is not None and verification is not None:
                self.verification(verification, report_path, source_path)
        except (OSError, UnicodeError, ValueError, RecursionError, SchemaError) as exc:
            self.error("read", self.prefix, str(exc))
        return self.report()


def validate_course(vault_dir, course, strict=False):
    errors = []
    if not isinstance(course, str) or not COURSE_KEY.fullmatch(course):
        diagnostic(errors, "argument", "course", "course must be a lowercase kebab-case directory key.")
    if type(strict) is not bool:
        diagnostic(errors, "argument", "strict", "strict must be a boolean.")
    if not isinstance(vault_dir, (str, Path)) or not str(vault_dir).strip():
        diagnostic(errors, "argument", "vault", "Supply an explicit vault directory.")
    if yaml is None or Draft202012Validator is None:
        diagnostic(
            errors, "dependency", "requirements.txt",
            'Use the Clew project environment: uv add --project "<Clew project>" '
            '--requirements "<installed course-content>\\requirements.txt"; '
            'then invoke the helper through uv run --project "<Clew project>" python.',
        )
    if errors:
        return {
            "schema": "clew-validation/v1", "ok": False,
            "strict": strict if type(strict) is bool else False,
            "course": f"courses/{course}" if isinstance(course, str) else None,
            "errors": errors, "warnings": [], "scope": {"concepts": [], "external_notes": []},
        }
    return ClewValidator(vault_dir, course, strict).run()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True, type=Path, help="Explicit authorized Clew vault root")
    parser.add_argument("--course", required=True, help="Directory key under courses/")
    parser.add_argument("--strict", action="store_true", help="Require verified sections and resolved page coverage")
    args = parser.parse_args(argv)
    result = validate_course(args.vault, args.course, args.strict)
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
