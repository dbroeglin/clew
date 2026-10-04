"""Render safe Markdown and assemble an entirely offline publication."""
from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from notes import Library, Note, local_path, parser, require

ASSETS = Path(__file__).resolve().parent.parent / "assets"


class Renderer:
    def __init__(self, library: Library, output: Path):
        self.library = library
        self.output = output
        self.warnings: list[str] = []
        self.emitted: set[str] = set()
        self.links: set[str] = set()
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
        index = self.library.notes.index(note) + 1
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
        return f'<a href="#{identifier}">{html.escape(label or fragment.lstrip("^") or note.title)}</a>'

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
        if not text.strip():
            return ""
        prefix = self.target(note, fragment)
        if text == note.select(fragment):
            chunks = []
            for part in note.select_parts(fragment):
                if part.text.strip():
                    anchor = self.target(note, "^" + part.block) if part.block else ""
                    chunks.append(anchor + self.render_text(part.display(), note))
            return prefix + "\n".join(chunks)
        return prefix + self.render_text(text, note)

    def render_text(self, text: str, note: Note) -> str:
        # Unknown callouts remain readable instead of being silently unwrapped.
        if re.search(r"(?m)^> \[!", text):
            self.warn(f"Unrecognized callout is displayed as quoted text: {note.path}")
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
        return self.md.renderer.render(tokens, self.md.options, {"note": note})

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
