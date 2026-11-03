"""Render safe Markdown and assemble an entirely offline publication."""
from __future__ import annotations

import base64
import html
from html.parser import HTMLParser
import json
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from notes import Library, Note, hide_comments, local_path, parser, require

ASSETS = Path(__file__).resolve().parent.parent / "assets"

class _StaticTableParser(HTMLParser):
    """Render a deliberately small, inert subset of source HTML tables."""

    INLINE_TAGS = {"em", "i", "strong", "b", "sup", "sub"}
    CELL_TAGS = {"th", "td"}

    def __init__(self, render_inline):
        super().__init__(convert_charrefs=False)
        self.render_inline = render_inline
        self.stack: list[str] = []
        self.parts: list[str] = []
        self.valid = True
        self.tables = 0
        self.rows = 0
        self.cells = 0

    def _attributes(self, tag: str, attributes: list[tuple[str, str | None]]) -> str | None:
        if not attributes:
            return ""
        if tag not in self.CELL_TAGS:
            return None
        rendered = []
        seen = set()
        for name, value in attributes:
            name = name.lower()
            if (name not in {"colspan", "rowspan"} or name in seen or value is None
                    or not re.fullmatch(r"[1-9][0-9]{0,2}", value) or int(value) > 100):
                return None
            seen.add(name)
            rendered.append(f' {name}="{value}"')
        return "".join(rendered)

    @staticmethod
    def _output_tag(tag: str) -> str:
        return {"i": "em", "b": "strong"}.get(tag, tag)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.valid:
            return
        tag = tag.lower()
        parent = self.stack[-1] if self.stack else None
        if tag == "table":
            allowed = parent is None and self.tables == 0
            self.tables += 1
        elif tag == "caption":
            allowed = parent == "table"
        elif tag == "tr":
            allowed = parent == "table"
            self.rows += 1
        elif tag in self.CELL_TAGS:
            allowed = parent == "tr"
            self.cells += 1
        elif tag in self.INLINE_TAGS:
            allowed = parent in self.CELL_TAGS | {"caption"} | self.INLINE_TAGS
        elif tag == "br":
            allowed = parent in self.CELL_TAGS | {"caption"} | self.INLINE_TAGS
            if allowed and not attrs:
                self.parts.append("<br>")
                return
        else:
            allowed = False
        rendered_attrs = self._attributes(tag, attrs) if allowed else None
        if not allowed or rendered_attrs is None:
            self.valid = False
            return
        self.parts.append(f"<{self._output_tag(tag)}{rendered_attrs}>")
        if tag != "br":
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br":
            self.handle_starttag(tag, attrs)
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self.valid:
            return
        tag = tag.lower()
        if not self.stack or self.stack[-1] != tag or tag == "br":
            self.valid = False
            return
        self.stack.pop()
        self.parts.append(f"</{self._output_tag(tag)}>")

    def handle_data(self, data: str) -> None:
        if not self.valid:
            return
        if any(tag in self.CELL_TAGS or tag == "caption" for tag in self.stack):
            self.parts.append(self.render_inline(data))
        elif data.strip():
            self.valid = False
        else:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(html.unescape(f"&{name};"))

    def handle_charref(self, name: str) -> None:
        self.handle_data(html.unescape(f"&#{name};"))

    def handle_comment(self, data: str) -> None:
        self.valid = False

    def handle_decl(self, decl: str) -> None:
        self.valid = False

    def handle_pi(self, data: str) -> None:
        self.valid = False

    def render(self, source: str) -> str | None:
        self.feed(source)
        self.close()
        if not self.valid or self.stack or self.tables != 1 or not self.rows or not self.cells:
            return None
        return "".join(self.parts)


class Renderer:
    def __init__(self, library: Library, output: Path):
        self.library = library
        self.output = output
        self.note_order = {note.id: index for index, note in enumerate(library.notes, start=1)}
        self.warnings: list[str] = []
        self.emitted: set[str] = set()
        self.links: set[str] = set()
        self.course_links: dict[str, tuple[Note, str]] = {}
        self.md = parser()
        self.md.add_render_rule("math_inline", self.math_inline)
        self.md.add_render_rule("math_block", self.math_block)
        self.md.inline.ruler.before("link", "wikilink", self.wikilink)
        self.md.add_render_rule("clew_wikilink", self.wiki_html)
        self.md.add_render_rule("image", self.image_html)
        self.md.add_render_rule("link_open", self.link_html)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def anchor(self, note: Note, fragment: str = "") -> str:
        index = self.note_order[note.id]
        encoded = base64.urlsafe_b64encode(fragment.encode("utf-8")).decode("ascii").rstrip("=")
        return f"note-{index}" + ("-" + encoded if encoded else "")

    def target(self, note: Note, fragment: str) -> str:
        identifier = self.anchor(note, fragment)
        if identifier in self.emitted:
            return ""
        self.emitted.add(identifier)
        return f'<span id="{identifier}" class="anchor"></span>'

    @staticmethod
    def check_math(tex: str) -> str:
        require(not re.search(r"\\(?:require|href|url|htmlClass|htmlId|htmlStyle|includegraphics)\b", tex),
                "Unsupported active or externally loaded TeX command.")
        return html.escape(tex)

    def math_inline(self, tokens, index, options, env) -> str:
        return '<span class="math-inline">$' + self.check_math(tokens[index].content) + "$</span>"

    def math_block(self, tokens, index, options, env) -> str:
        return '<div class="math-block">$$' + self.check_math(tokens[index].content) + "$$</div>\n"

    @staticmethod
    def wikilink(state, silent: bool) -> bool:
        match = re.match(r"(!?)\[\[([^\]\n]+)\]\]", state.src[state.pos:])
        if not match:
            return False
        if not silent:
            token = state.push("clew_wikilink", "", 0)
            token.content = match[2]
            token.meta["embed"] = bool(match[1])
        state.pos += len(match[0])
        return True

    def wiki_html(self, tokens, index, options, env) -> str:
        token = tokens[index]
        ref, _, label = token.content.partition("|")
        if token.meta["embed"]:
            require(not ref.lower().endswith(".md") and "#" not in ref,
                    f"Note transclusion is unsupported; select its content explicitly: {ref}")
            return self.image(ref, label or Path(ref).name, env["note"])
        note, fragment = self.library.resolve(ref, env["note"])
        note.select(fragment)
        identifier = self.anchor(note, fragment)
        self.links.add(identifier)
        self.remember_course_link(note, fragment, env["note"])
        return f'<a href="#{identifier}">{html.escape(label or fragment.lstrip("^") or note.title)}</a>'

    def remember_course_link(self, target: Note, fragment: str, origin: Note) -> None:
        if origin.metadata.get("type") == "help" and target.role in {"course", "mixed"}:
            self.course_links[self.anchor(target, fragment)] = (target, fragment)

    def image(self, ref: str, label: str, note: Note) -> str:
        parsed = urlsplit(ref)
        require(not parsed.scheme and not parsed.netloc and not parsed.query and not parsed.fragment,
                f"Only local raster figures can be embedded: {ref}")
        path = local_path(note.path.parent / unquote(parsed.path))
        require(path.is_file(), f"Missing figure: {path}")
        data = path.read_bytes()
        signatures = {
            ".png": ("image/png", data.startswith(b"\x89PNG\r\n\x1a\n")),
            ".jpg": ("image/jpeg", data.startswith(b"\xff\xd8\xff")),
            ".jpeg": ("image/jpeg", data.startswith(b"\xff\xd8\xff")),
            ".gif": ("image/gif", data.startswith((b"GIF87a", b"GIF89a"))),
            ".webp": ("image/webp", data.startswith(b"RIFF") and data[8:12] == b"WEBP"),
        }
        mime, valid = signatures.get(path.suffix.lower(), ("", False))
        require(valid, f"Unsupported or invalid figure (SVG is not executed): {path}")
        encoded = base64.b64encode(data).decode("ascii")
        return f'<img alt="{html.escape(label, quote=True)}" src="data:{mime};base64,{encoded}">'

    def image_html(self, tokens, index, options, env) -> str:
        token = tokens[index]
        return self.image(token.attrGet("src") or "", token.content, env["note"])

    def link_html(self, tokens, index, options, env) -> str:
        token = tokens[index]
        ref = token.attrGet("href") or ""
        parsed = urlsplit(ref)
        require(parsed.scheme.lower() in {"", "http", "https", "mailto"},
                f"Unsafe URL scheme: {ref}")
        require(not parsed.netloc or bool(parsed.scheme), f"Protocol-relative link is unsupported: {ref}")
        if parsed.scheme:
            token.attrSet("rel", "noopener noreferrer")
            self.warn("External links are optional navigation; opening them may contact external sites.")
        elif not parsed.path or parsed.path.lower().endswith(".md"):
            target = unquote(parsed.path) + ("#" + unquote(parsed.fragment) if parsed.fragment else "")
            note, fragment = self.library.resolve(target, env["note"])
            note.select(fragment)
            identifier = self.anchor(note, fragment)
            self.links.add(identifier)
            self.remember_course_link(note, fragment, env["note"])
            token.attrSet("href", "#" + identifier)
        else:
            require(parsed.path.lower().endswith(".pdf") and not parsed.query,
                    f"Unsupported local link: {ref}")
            path = local_path(env["note"].path.parent / unquote(parsed.path))
            if not path.is_file():
                self.warn(f"Optional source PDF is missing: {path}")
            try:
                import os
                relative = os.path.relpath(path, self.output.parent).replace("\\", "/")
                uri = quote(relative, safe="/")
            except ValueError:
                uri = path.as_uri()
            token.attrSet("href", uri + ("#" + parsed.fragment if parsed.fragment else ""))
            self.warn("Source PDF links are external to the HTML; moving the file can break them.")
        return self.md.renderer.renderToken(tokens, index, options, env)

    def __call__(self, text: str, note: Note, fragment: str = "") -> str:
        prefix = self.target(note, fragment)
        if text == note.select(fragment):
            chunks = []
            for part in note.select_parts(fragment):
                anchor = self.target(note, "^" + part.block) if part.block else ""
                chunks.append(anchor + self.render_text(part.display(), note))
            return prefix + "\n".join(chunks)
        return prefix + self.render_text(text, note)

    @staticmethod
    def fenced_code_ranges(text: str) -> list[tuple[int, int]]:
        ranges = []
        fence = None
        start = 0
        offset = 0
        for line in text.splitlines(keepends=True):
            content = line.rstrip("\r\n")
            match = re.match(r" {0,3}(`{3,}|~{3,})(.*)$", content)
            if match:
                marker, suffix = match.groups()
                if fence is None:
                    fence = (marker[0], len(marker))
                    start = offset
                elif marker[0] == fence[0] and len(marker) >= fence[1] and not suffix.strip():
                    ranges.append((start, offset + len(line)))
                    fence = None
            offset += len(line)
        if fence is not None:
            ranges.append((start, len(text)))
        return ranges

    @classmethod
    def static_table_blocks(cls, text: str) -> list[tuple[int, int, str]]:
        fenced = cls.fenced_code_ranges(text)
        blocks = []
        search_from = 0
        while opening := re.search(r"<table\b[^>]*>", text[search_from:], re.IGNORECASE):
            open_start = search_from + opening.start()
            open_end = search_from + opening.end()
            line_start = max(text.rfind("\n", 0, open_start), text.rfind("\r", 0, open_start)) + 1
            prefix = text[line_start:open_start]
            closing = re.search(r"</table\s*>", text[open_end:], re.IGNORECASE)
            if not re.fullmatch(r"[ \t]{0,3}", prefix) or closing is None:
                search_from = open_end
                continue
            close_end = open_end + closing.end()
            line_ends = [position for position in (text.find("\r", close_end), text.find("\n", close_end))
                         if position >= 0]
            line_end = min(line_ends) if line_ends else len(text)
            if text[close_end:line_end].strip():
                search_from = close_end
                continue
            if any(line_start < fence_end and close_end > fence_start for fence_start, fence_end in fenced):
                search_from = close_end
                continue
            blocks.append((line_start, line_end, text[line_start:close_end]))
            search_from = line_end
        return blocks

    def render_static_tables(self, text: str, note: Note) -> tuple[str, dict[str, str]]:
        if "<table" not in text.lower():
            return text, {}
        replacements = {}
        pieces = []
        cursor = 0
        newline = "\r\n" if "\r\n" in text else "\r" if "\r" in text else "\n"
        for index, (start, end, source) in enumerate(self.static_table_blocks(text)):
            table = _StaticTableParser(
                lambda value: self.md.renderInline(value, {"note": note})
            ).render(source)
            if table is None:
                continue
            marker = f"CLEWSTATICHTMLTABLETOKEN{index}END"
            while marker in text:
                marker += "X"
            pieces.extend((text[cursor:start], newline * 2, marker, newline * 2))
            replacements[marker] = table
            cursor = end
        if not replacements:
            return text, replacements
        pieces.append(text[cursor:])
        return "".join(pieces), replacements

    def render_text(self, text: str, note: Note) -> str:
        # Unknown callouts remain readable instead of being silently unwrapped.
        if re.search(r"(?m)^> \[!", text):
            self.warn(f"Unrecognized callout is displayed as quoted text: {note.path}")
        text, tables = self.render_static_tables(hide_comments(text), note)
        if re.search(r"</?[A-Za-z][^>]*>", text):
            self.warn(f"Raw HTML is displayed as literal text, never executed: {note.path}")
        require(not re.search(r"(?m)^\s*```(?:dataview|dataviewjs)\b", text),
                f"Dataview requires Obsidian; select actual content instead: {note.path}")
        tokens = self.md.parse(text, {"note": note})
        for index, token in enumerate(tokens):
            if token.type == "heading_open":
                heading = tokens[index + 1].content
                identifier = self.anchor(note, heading)
                if identifier not in self.emitted:
                    token.attrSet("id", identifier)
                    self.emitted.add(identifier)
        rendered = self.md.renderer.render(tokens, self.md.options, {"note": note})
        for marker, table in tables.items():
            rendered = rendered.replace(f"<p>{marker}</p>", table)
        return rendered

    def validate_links(self) -> None:
        missing = self.links - self.emitted
        require(not missing, f"Links target content outside the publication: {sorted(missing)}")


def assemble(data: dict) -> str:
    template = (ASSETS / "template.html").read_text(encoding="utf-8")
    runtime = (ASSETS / "mathjax" / "tex-svg.js").read_text(encoding="utf-8")
    require("</script" not in runtime.lower(), "Math runtime contains an unsafe script terminator.")
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    encoded = encoded.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    licenses = ((ASSETS.parent / "LICENSE").read_text(encoding="utf-8") + "\n\n"
                "MathJax 3.2.2, unmodified tex-svg.js, Apache License 2.0\n\n"
                + (ASSETS / "mathjax" / "LICENSE").read_text(encoding="utf-8"))
    values = {
        "TITLE": html.escape(data["title"]),
        "STYLE": (ASSETS / "style.css").read_text(encoding="utf-8"),
        "DATA": encoded,
        "LICENSE": html.escape(licenses),
        "MATHJAX": runtime,
        "SCRIPT": (ASSETS / "interaction.js").read_text(encoding="utf-8"),
    }
    return re.sub(r"\{\{(TITLE|STYLE|DATA|LICENSE|MATHJAX|SCRIPT)\}\}",
                  lambda match: values[match[1]], template)
