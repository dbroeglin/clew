import { createHash, randomUUID } from "node:crypto";
import { EventEmitter } from "node:events";
import { mkdir, open, readFile, readdir, realpath, rename, stat, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { parseDocument } from "yaml";
import { headingId, renderMarkdown } from "./renderer.mjs";

export const MAX_NOTE_BYTES = 1024 * 1024;
export const MAX_EXCERPT_CHARACTERS = 12000;
const MAX_ASSET_BYTES = 10 * 1024 * 1024;
const MAX_WIKI_ENTRIES = 10000;
const IMAGE_TYPES = new Map([
    [".png", "image/png"], [".jpg", "image/jpeg"], [".jpeg", "image/jpeg"],
    [".gif", "image/gif"], [".webp", "image/webp"], [".avif", "image/avif"],
]);

export class ReaderError extends Error {
    constructor(code, message, status = 400, options) {
        super(message, options);
        this.name = "ReaderError";
        this.code = code;
        this.status = status;
    }
}

export function objectInput(input, allowed, required = []) {
    if (!input || typeof input !== "object" || Array.isArray(input)) {
        throw new ReaderError("invalid_input", "Expected an input object.");
    }
    if (Object.keys(input).some((key) => !allowed.includes(key))) {
        throw new ReaderError("invalid_input", "The input contains an unsupported property.");
    }
    if (required.some((key) => !Object.hasOwn(input, key))) {
        throw new ReaderError("invalid_input", `Required properties: ${required.join(", ")}.`);
    }
    return input;
}

function textInput(value, name) {
    if (typeof value !== "string" || !value.trim() || value.length > 4096 || value.includes("\0")) {
        throw new ReaderError("invalid_input", `${name} must be a nonempty string of at most 4096 characters.`);
    }
    return value.trim();
}

function within(root, candidate) {
    const relative = path.relative(root, candidate);
    return relative === "" || (!path.isAbsolute(relative) && relative !== ".."
        && !relative.startsWith(`..${path.sep}`));
}

function portable(value) {
    return value.split(path.sep).join("/");
}

function relativePath(value) {
    const result = textInput(value, "Path").replace(/\\/g, "/");
    if (path.posix.isAbsolute(result) || path.win32.isAbsolute(result) || result.includes(":")) {
        throw new ReaderError("outside_course", "Use a relative path inside the chosen course.");
    }
    return result;
}

function privatePath(value) {
    return value.split(/[\\/]/).some((part) => part.toLowerCase() === "model"
        || (part.startsWith(".") && part !== "." && part !== ".."));
}

function ioError(error, context) {
    if (error instanceof ReaderError) return error;
    const missing = error?.code === "ENOENT" || error?.code === "ENOTDIR";
    return new ReaderError(missing ? "not_found" : "io_error",
        missing ? `${context} was not found.` : `${context} could not be read or saved.`,
        missing ? 404 : 500, { cause: error });
}

async function limitedRead(filename, maximum, context) {
    let handle;
    try {
        handle = await open(filename, "r");
        const info = await handle.stat();
        if (!info.isFile()) throw new ReaderError("invalid_file", `${context} must be a regular file.`);
        if (info.size > maximum) throw new ReaderError("file_too_large", `${context} exceeds the ${maximum}-byte limit.`);
        const buffer = Buffer.alloc(maximum + 1);
        let length = 0;
        while (length < buffer.length) {
            const { bytesRead } = await handle.read(buffer, length, buffer.length - length);
            if (!bytesRead) break;
            length += bytesRead;
        }
        if (length > maximum) throw new ReaderError("file_too_large", `${context} exceeds the ${maximum}-byte limit.`);
        return buffer.subarray(0, length);
    } catch (error) {
        throw ioError(error, context);
    } finally {
        await handle?.close();
    }
}

export function parseNote(source) {
    const normalized = source.replace(/^\uFEFF/, "").replace(/\r\n/g, "\n");
    let metadata = {};
    let body = normalized;
    if (/^---[ \t]*\n/.test(normalized)) {
        const lines = normalized.split("\n");
        const end = lines.findIndex((line, index) => index > 0 && /^(---|\.\.\.)[ \t]*$/.test(line));
        if (end === -1) throw new ReaderError("invalid_frontmatter", "The YAML frontmatter has no closing delimiter.");
        try {
            const document = parseDocument(lines.slice(1, end).join("\n"), {
                uniqueKeys: true, strict: true, prettyErrors: false,
            });
            if (document.errors.length || document.warnings.length) {
                throw new Error([...document.errors, ...document.warnings].map((error) => error.message).join("; "));
            }
            metadata = document.toJS({ maxAliasCount: 0 }) ?? {};
        } catch (error) {
            throw new ReaderError("invalid_frontmatter", `Invalid YAML frontmatter: ${error.message}`, 400, { cause: error });
        }
        if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
            throw new ReaderError("invalid_frontmatter", "Frontmatter must be a YAML mapping.");
        }
        body = lines.slice(end + 1).join("\n");
    }
    for (const field of ["title", "previous", "next"]) {
        const value = metadata[field];
        if (value !== undefined && value !== null && (typeof value !== "string" || !value.trim())) {
            throw new ReaderError("invalid_frontmatter", `${field} must be a nonempty string or null.`);
        }
    }
    return {
        body,
        title: metadata.title?.trim() || null,
        previous: metadata.previous?.trim() || null,
        next: metadata.next?.trim() || null,
    };
}

function excerptFor(body) {
    let text = "";
    let totalCharacters = 0;
    for (const character of body) {
        totalCharacters += 1;
        if (totalCharacters <= MAX_EXCERPT_CHARACTERS) text += character;
    }
    return { text, truncated: totalCharacters > MAX_EXCERPT_CHARACTERS, totalCharacters };
}

function referenceParts(reference, kind) {
    let target = textInput(reference, "Reference");
    let label = null;
    if (kind === "wikilink" || target.startsWith("[[")) {
        kind = "wikilink";
        if (!target.startsWith("[[") || !target.endsWith("]]")) {
            throw new ReaderError("invalid_link", "A wikilink must have the form [[note]] or [[note|label]].");
        }
        target = target.slice(2, -2);
        const separator = target.indexOf("|");
        if (separator !== -1) {
            label = target.slice(separator + 1).trim();
            target = target.slice(0, separator);
        }
    }
    const separator = target.indexOf("#");
    let fragment = separator === -1 ? "" : target.slice(separator + 1);
    target = separator === -1 ? target : target.slice(0, separator);
    try {
        if (kind === "path") target = decodeURIComponent(target);
        fragment = decodeURIComponent(fragment);
    } catch (error) {
        throw new ReaderError("invalid_link", "The link contains invalid percent encoding.", 400, { cause: error });
    }
    if (fragment.startsWith("^")) {
        throw new ReaderError("unsupported_link", "Block-reference navigation is not supported; use a page or heading link.");
    }
    return { target: target.trim(), kind, label, anchor: fragment ? headingId(fragment) : null };
}

export async function resolveCourse(input) {
    objectInput(input, ["vaultPath", "coursePath", "entry"], ["vaultPath", "coursePath"]);
    const vaultInput = textInput(input.vaultPath, "vaultPath");
    if (!path.isAbsolute(vaultInput)) {
        throw new ReaderError("invalid_input", "vaultPath must be the absolute path of the current vault.");
    }
    const courseInput = relativePath(input.coursePath);
    if (privatePath(courseInput)) {
        throw new ReaderError("private_path", "Learner-model and hidden directories are not course sources.");
    }
    try {
        const vaultRoot = await realpath(vaultInput);
        const lexicalRoot = path.resolve(vaultRoot, courseInput);
        if (!within(vaultRoot, lexicalRoot) || lexicalRoot === vaultRoot) {
            throw new ReaderError("outside_course", "Choose a course subdirectory, not the whole vault or a path outside it.");
        }
        const courseRoot = await realpath(lexicalRoot);
        if (!within(vaultRoot, courseRoot) || courseRoot === vaultRoot
            || privatePath(path.relative(vaultRoot, courseRoot))) {
            throw new ReaderError("outside_course", "The course must stay inside the vault and outside private model directories.");
        }
        if (!(await stat(courseRoot)).isDirectory()) {
            throw new ReaderError("invalid_course", "The chosen course must be a directory.");
        }
        return {
            vaultRoot, courseRoot, course: portable(path.relative(vaultRoot, courseRoot)),
            entry: input.entry === undefined ? "hub.md" : relativePath(input.entry),
        };
    } catch (error) {
        throw ioError(error, "The chosen vault or course");
    }
}

export class CourseReader extends EventEmitter {
    constructor({ vaultRoot, courseRoot, course, workspacePath }) {
        super();
        if (typeof workspacePath !== "string" || !path.isAbsolute(workspacePath)) {
            throw new ReaderError("persistence_unavailable", "This session has no artifact workspace for the reading position.", 503);
        }
        this.vaultRoot = vaultRoot;
        this.courseRoot = courseRoot;
        this.course = course;
        const key = createHash("sha256").update(courseRoot).digest("hex");
        this.stateFile = path.join(workspacePath, "files", "clew-course-reader", `${key}.json`);
        this.pending = Promise.resolve();
        this.staged = new Map();
        this.revision = 0;
    }

    enqueue(operation) {
        const result = this.pending.then(operation);
        // The caller keeps the rejection; a failed command must not poison the next one.
        this.pending = result.then(() => undefined, () => undefined);
        return result;
    }

    async scopedFile(candidate, markdown = true) {
        if (!within(this.courseRoot, candidate) || privatePath(path.relative(this.courseRoot, candidate))) {
            throw new ReaderError("outside_course", "This link leaves the chosen course or targets a private directory.");
        }
        try {
            const canonical = await realpath(candidate);
            if (!within(this.courseRoot, canonical) || privatePath(path.relative(this.courseRoot, canonical))) {
                throw new ReaderError("outside_course", "This link resolves outside the chosen course.");
            }
            if (markdown && path.extname(canonical).toLowerCase() !== ".md") {
                throw new ReaderError("unsupported_file", "The reader opens Markdown (.md) notes only.");
            }
            if (!(await stat(canonical)).isFile()) {
                throw new ReaderError("invalid_file", "The link must point to a regular file.");
            }
            return canonical;
        } catch (error) {
            throw ioError(error, "The linked file");
        }
    }

    async courseFile(reference) {
        let target = relativePath(reference);
        if (!path.extname(target)) target += ".md";
        return this.scopedFile(path.resolve(this.courseRoot, target));
    }

    async wikiBasename(name) {
        const directories = [this.courseRoot];
        const matches = [];
        let entriesSeen = 0;
        while (directories.length) {
            const directory = await realpath(directories.pop());
            if (!within(this.courseRoot, directory)) {
                throw new ReaderError("outside_course", "A course directory now resolves outside the course.");
            }
            const entries = await readdir(directory, { withFileTypes: true });
            for (const entry of entries) {
                entriesSeen += 1;
                if (entriesSeen > MAX_WIKI_ENTRIES) {
                    throw new ReaderError("course_too_large", "Use a qualified wikilink; basename lookup is limited to 10000 course entries.");
                }
                if (privatePath(entry.name) || entry.isSymbolicLink()) continue;
                const filename = path.join(directory, entry.name);
                if (entry.isDirectory()) directories.push(filename);
                else if (entry.isFile() && entry.name.toLowerCase() === name.toLowerCase()) matches.push(filename);
            }
        }
        if (matches.length === 0) throw new ReaderError("not_found", `No course note matches "${name}".`, 404);
        if (matches.length !== 1) throw new ReaderError("ambiguous_link", `More than one course note matches "${name}"; qualify the wikilink.`);
        return this.scopedFile(matches[0]);
    }

    async resolveReference(reference, kind = "path", document = this.note.path) {
        const parts = referenceParts(reference, kind);
        if (!parts.target) {
            if (!parts.anchor) throw new ReaderError("invalid_link", "The link has no page or heading.");
            return { ...parts, filename: await this.courseFile(document) };
        }
        let target = relativePath(parts.target);
        if (target.includes("?")) throw new ReaderError("invalid_link", "Query strings are not course-note paths.");
        if (!path.extname(target)) target += ".md";
        let filename;
        if (parts.kind === "wikilink" && !target.includes("/")) {
            filename = await this.wikiBasename(target);
        } else if (parts.kind === "wikilink" && !target.startsWith(".")) {
            const vaultCandidate = path.resolve(this.vaultRoot, target);
            filename = await this.scopedFile(within(this.courseRoot, vaultCandidate)
                ? vaultCandidate : path.resolve(this.courseRoot, target));
        } else {
            filename = await this.scopedFile(path.resolve(this.courseRoot, path.dirname(document), target));
        }
        return { ...parts, filename };
    }

    async navigationInfo(reference, document) {
        if (!reference) return null;
        let label = reference;
        try {
            const result = await this.resolveReference(reference, "path", document);
            label = result.label || path.basename(result.filename, path.extname(result.filename));
            return { reference, label, path: portable(path.relative(this.courseRoot, result.filename)), available: true, error: null };
        } catch (error) {
            const problem = ioError(error, "The navigation target");
            return { reference, label, path: null, available: false, error: problem.message };
        }
    }

    async load(filename, anchor = null) {
        const buffer = await limitedRead(filename, MAX_NOTE_BYTES, "The course note");
        const parsed = parseNote(buffer.toString("utf8"));
        const document = portable(path.relative(this.courseRoot, filename));
        const rendered = renderMarkdown(parsed.body, document);
        if (anchor && !rendered.headings.some((heading) => heading.id === anchor)) {
            throw new ReaderError("heading_not_found", "That heading was not found in the target note.");
        }
        const [previous, next] = await Promise.all([
            this.navigationInfo(parsed.previous, document),
            this.navigationInfo(parsed.next, document),
        ]);
        return {
            path: document, title: parsed.title || rendered.headings.find((heading) => heading.level === 1)?.text
                || path.basename(filename, path.extname(filename)),
            ...rendered, previous, next, anchor,
            excerpt: excerptFor(parsed.body),
            hash: createHash("sha256").update(buffer).digest("hex"),
        };
    }

    async savePosition(document) {
        const directory = path.dirname(this.stateFile);
        const temporary = `${this.stateFile}.${randomUUID()}.tmp`;
        try {
            await mkdir(directory, { recursive: true });
            await writeFile(temporary, `${JSON.stringify({ version: 1, path: document })}\n`, { flag: "wx", mode: 0o600 });
            await rename(temporary, this.stateFile);
        } catch (error) {
            try {
                await unlink(temporary);
            } catch (cleanupError) {
                if (cleanupError.code !== "ENOENT") {
                    throw new AggregateError([error, cleanupError], "Could not save the reading position or clean up its temporary file.");
                }
            }
            throw ioError(error, "The reading position");
        }
    }

    async commit(note) {
        await this.savePosition(note.path);
        this.note = note;
        this.revision += 1;
        const state = this.snapshot();
        this.emit("state", state);
        return state;
    }

    async initialize(entry = "hub.md") {
        let document = entry;
        let saved;
        try {
            saved = await readFile(this.stateFile, "utf8");
        } catch (error) {
            if (error.code !== "ENOENT") throw ioError(error, "The reading position");
        }
        if (saved !== undefined) {
            try {
                const bookmark = JSON.parse(saved);
                objectInput(bookmark, ["version", "path"], ["version", "path"]);
                if (bookmark.version !== 1) throw new Error("Unknown bookmark version.");
                document = textInput(bookmark.path, "Saved path");
            } catch (error) {
                throw new ReaderError("invalid_bookmark", "The saved reading position is invalid; inspect the session's clew-course-reader artifact.", 400, { cause: error });
            }
        }
        return this.commit(await this.load(await this.courseFile(document)));
    }

    snapshot({ forAgent = false } = {}) {
        if (!this.note) throw new ReaderError("reader_not_ready", "The course reader has not finished opening.", 503);
        const { path: document, title, html, headings, previous, next, anchor, excerpt } = this.note;
        const state = { course: this.course, path: document, title, revision: this.revision, headings, previous, next, anchor, excerpt };
        return forAgent ? state : { ...state, html };
    }

    checkRevision(value) {
        if (value !== undefined && (!Number.isSafeInteger(value) || value < 1)) {
            throw new ReaderError("invalid_input", "expectedRevision must be a positive integer.");
        }
        if (value !== undefined && value !== this.revision) {
            throw new ReaderError("stale_view", "The page changed. Use the current view and try again.", 409);
        }
    }

    openPage(input) {
        objectInput(input, ["path", "expectedRevision"], ["path"]);
        return this.enqueue(async () => {
            this.checkRevision(input.expectedRevision);
            return this.commit(await this.load(await this.courseFile(input.path)));
        });
    }

    navigate(input) {
        objectInput(input, ["direction", "expectedRevision"], ["direction"]);
        if (!["previous", "next"].includes(input.direction)) {
            throw new ReaderError("invalid_input", "direction must be previous or next.");
        }
        return this.enqueue(async () => {
            this.checkRevision(input.expectedRevision);
            const link = this.note[input.direction];
            if (!link) throw new ReaderError("end_of_course", `This page has no ${input.direction} link.`);
            const target = await this.resolveReference(link.reference);
            return this.commit(await this.load(target.filename, target.anchor));
        });
    }

    follow(input) {
        objectInput(input, ["reference", "kind", "expectedRevision"], ["reference", "kind"]);
        if (!["path", "wikilink"].includes(input.kind)) throw new ReaderError("invalid_input", "Unsupported link kind.");
        return this.enqueue(async () => {
            this.checkRevision(input.expectedRevision);
            const target = await this.resolveReference(input.reference, input.kind);
            return this.commit(await this.load(target.filename, target.anchor));
        });
    }

    refresh(input = {}) {
        objectInput(input, ["expectedRevision"]);
        return this.enqueue(async () => {
            this.checkRevision(input.expectedRevision);
            return this.commit(await this.load(await this.courseFile(this.note.path)));
        });
    }

    attachSelection(input, stageAttachment) {
        objectInput(input, ["text", "headingId", "expectedRevision", "requestId"], ["text", "expectedRevision", "requestId"]);
        if (typeof input.text !== "string" || !input.text.trim()) {
            throw new ReaderError("empty_selection", "Select a course passage before asking in chat.");
        }
        if (!Number.isSafeInteger(input.expectedRevision) || input.expectedRevision < 1) {
            throw new ReaderError("invalid_input", "expectedRevision must be a positive integer.");
        }
        const headingId = input.headingId ?? null;
        if (headingId !== null && (typeof headingId !== "string" || !headingId)) {
            throw new ReaderError("invalid_heading", "The section reference must be a heading ID or null.");
        }
        if (typeof stageAttachment !== "function") {
            throw new ReaderError("composer_unavailable", "This host does not support adding course passages to the composer.", 503);
        }
        const requestId = textInput(input.requestId, "requestId");
        if (!/^[A-Za-z0-9-]{1,128}$/.test(requestId)) throw new ReaderError("invalid_input", "Invalid requestId.");
        const fingerprint = createHash("sha256").update(JSON.stringify([input.expectedRevision, input.text, headingId])).digest("hex");
        return this.enqueue(async () => {
            const previous = this.staged.get(requestId);
            if (previous) {
                if (previous.fingerprint !== fingerprint) {
                    throw new ReaderError("invalid_request_id", "A different selection must use a new requestId.");
                }
                return previous.result;
            }
            this.checkRevision(input.expectedRevision);
            const heading = headingId === null ? null : this.note.headings.find((entry) => entry.id === headingId);
            if (headingId !== null && !heading) {
                throw new ReaderError("invalid_heading", "That section is not in the current note. Select the passage again.");
            }
            const file = await this.courseFile(this.note.path);
            const latest = await limitedRead(file, MAX_NOTE_BYTES, "The course note");
            if (createHash("sha256").update(latest).digest("hex") !== this.note.hash) {
                throw new ReaderError("content_changed", "The source note changed on disk. Ask the session to refresh the reader, then select the passage again.", 409);
            }
            try {
                await stageAttachment({
                    type: "extension_context",
                    title: `Course excerpt: ${this.note.title}`,
                    payload: {
                        course: this.course,
                        path: this.note.path,
                        filePath: file,
                        heading: heading ? { id: heading.id, text: heading.text } : null,
                        text: input.text,
                    },
                });
            } catch (error) {
                const detail = error instanceof Error ? error.message : String(error);
                throw new ReaderError("composer_rejected", `The host could not add the passage to the composer: ${detail}`, 502, { cause: error });
            }
            const result = { staged: true, path: this.note.path };
            this.staged.set(requestId, { fingerprint, result });
            if (this.staged.size > 100) this.staged.delete(this.staged.keys().next().value);
            return result;
        });
    }

    async readAsset(document, reference, kind = "path") {
        if (kind !== "path") throw new ReaderError("unsupported_link", "Images must use a relative Markdown image path.");
        const source = await this.courseFile(document);
        const parts = referenceParts(reference, kind);
        const target = relativePath(parts.target);
        const filename = await this.scopedFile(path.resolve(path.dirname(source), target), false);
        const contentType = IMAGE_TYPES.get(path.extname(filename).toLowerCase());
        if (!contentType) throw new ReaderError("unsupported_image", "Only local PNG, JPEG, GIF, WebP and AVIF images are supported.");
        return { contentType, data: await limitedRead(filename, MAX_ASSET_BYTES, "The course image") };
    }
}
