import MarkdownIt from "markdown-it";
import { katex } from "@mdit/plugin-katex";

export function headingId(text) {
    return text.normalize("NFKC").toLowerCase().trim()
        .replace(/[^\p{L}\p{N}\s_-]/gu, "")
        .replace(/\s+/g, "-") || "section";
}

const markdown = new MarkdownIt({ html: false, linkify: false, typographer: false });
markdown.use(katex, {
    delimiters: "all",
    mathFence: true,
    output: "htmlAndMathml",
    trust: false,
    throwOnError: true,
    errorColor: "var(--cp-danger)",
    maxExpand: 1000,
    maxSize: 20,
    logger: () => "error",
});
const escape = markdown.utils.escapeHtml;

markdown.inline.ruler.before("link", "wikilink", (state, silent) => {
    if (state.src.slice(state.pos, state.pos + 2) !== "[[" || state.linkLevel > 0) {
        return false;
    }
    const end = state.src.indexOf("]]", state.pos + 2);
    if (end === -1) return false;
    const reference = state.src.slice(state.pos, end + 2);
    const inner = reference.slice(2, -2);
    if (!inner || inner.includes("\n") || inner.includes("[")) return false;
    if (!silent) {
        const open = state.push("link_open", "a", 1);
        open.attrSet("href", "#");
        open.attrSet("data-reader-reference", reference);
        open.attrSet("data-reader-kind", "wikilink");
        state.push("text", "", 0).content = inner.includes("|")
            ? inner.slice(inner.indexOf("|") + 1) : inner;
        state.push("link_close", "a", -1);
    }
    state.pos = end + 2;
    return true;
});

markdown.renderer.rules.link_open = (tokens, index, options, env, self) => {
    const token = tokens[index];
    if (token.attrGet("data-reader-kind")) return self.renderToken(tokens, index, options);
    const href = token.attrGet("href") || "";
    if (/^https?:\/\//i.test(href)) {
        token.attrSet("target", "_blank");
        token.attrSet("rel", "noopener noreferrer");
    } else if (href.startsWith("#")) {
        let anchor;
        try {
            anchor = decodeURIComponent(href.slice(1));
        } catch {
            anchor = href.slice(1);
        }
        token.attrSet("href", `#${headingId(anchor)}`);
    } else {
        token.attrSet("href", "#");
        token.attrSet("data-reader-reference", href);
        token.attrSet("data-reader-kind", "path");
    }
    return self.renderToken(tokens, index, options);
};

markdown.renderer.rules.image = (tokens, index, options, env) => {
    const token = tokens[index];
    const reference = token.attrGet("src") || "";
    const alt = markdown.renderer.renderInlineAsText(token.children || [], options, env);
    if (/^(?:[a-z][a-z0-9+.-]*:|[\\/]{2})/i.test(reference)) {
        return `<span class="image-unavailable">${escape(alt || "Image")}: remote images are not loaded.</span>`;
    }
    const query = new URLSearchParams({ document: env.document, reference, kind: "path" });
    return `<img src="asset?${escape(query.toString())}" alt="${escape(alt)}" loading="lazy">`;
};

markdown.core.ruler.push("reader_headings", (state) => {
    const tokens = state.tokens;
    const headings = [];
    const seen = new Map();
    for (let index = 0; index < tokens.length; index += 1) {
        if (tokens[index].type !== "heading_open") continue;
        const inline = tokens[index + 1];
        const text = (inline.children || []).map((token) => token.content).join("");
        const base = headingId(text);
        const count = seen.get(base) || 0;
        seen.set(base, count + 1);
        const id = count ? `${base}-${count}` : base;
        tokens[index].attrSet("id", id);
        headings.push({ id, text, level: Number(tokens[index].tag.slice(1)) });
    }
    state.env.headings = headings;
});

export function renderMarkdown(body, document) {
    const env = { document, headings: [] };
    // Use render(), not the low-level token renderer, so the math plugin resets page-local macros.
    const html = markdown.render(body, env);
    return { html, headings: env.headings };
}
