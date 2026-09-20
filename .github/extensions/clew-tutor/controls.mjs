import { lstat, readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { CaptureError } from "./errors.mjs";

const MAX_INSPECT_BYTES = 16 * 1024;
const ALLOWED_ROOTS = new Set(["model", "artifacts"]);

function resolveScopedPath(vaultPath, relativePath) {
    if (typeof relativePath !== "string" || relativePath.length === 0 || path.isAbsolute(relativePath)) {
        throw new CaptureError("invalid_memory_path", "A non-empty vault-relative path is required.");
    }
    const normalized = relativePath.replaceAll("\\", "/");
    const [root] = normalized.split("/");
    if (!ALLOWED_ROOTS.has(root)) {
        throw new CaptureError("invalid_memory_path", "Memory access is limited to model/ and artifacts/.");
    }
    const vault = path.resolve(vaultPath);
    const target = path.resolve(vault, ...normalized.split("/"));
    const relative = path.relative(vault, target);
    if (relative.startsWith("..") || path.isAbsolute(relative)) {
        throw new CaptureError("invalid_memory_path", "The path escapes the configured vault.");
    }
    return { target, relativePath: normalized };
}

async function rejectSymlink(target, vaultPath) {
    const vault = path.resolve(vaultPath);
    let current = target;
    while (current !== vault) {
        try {
            const info = await lstat(current);
            if (info.isSymbolicLink()) {
                throw new CaptureError("invalid_memory_path", `Symbolic links are not allowed: ${current}`);
            }
        } catch (error) {
            if (error.code !== "ENOENT") throw error;
        }
        const parent = path.dirname(current);
        if (parent === current) break;
        current = parent;
    }
}

export async function inspectMemory(vaultPath, relativePath) {
    const scoped = resolveScopedPath(vaultPath, relativePath);
    await rejectSymlink(scoped.target, vaultPath);
    const content = await readFile(scoped.target, "utf8");
    if (Buffer.byteLength(content, "utf8") > MAX_INSPECT_BYTES) {
        throw new CaptureError("memory_too_large", `Memory inspection is limited to ${MAX_INSPECT_BYTES} bytes.`);
    }
    return { path: scoped.relativePath, content };
}

function exactOccurrenceCount(content, text) {
    if (text.length === 0) return 0;
    return content.split(text).length - 1;
}

export async function prepareMemoryChange(vaultPath, input) {
    if (!["correction", "stop_use"].includes(input.operation)) {
        throw new CaptureError("invalid_memory_change", "operation must be correction or stop_use.");
    }
    if (typeof input.expectedText !== "string" || input.expectedText.length === 0) {
        throw new CaptureError("invalid_memory_change", "expectedText is required.");
    }
    if (typeof input.replacementText !== "string" || input.replacementText.length === 0) {
        throw new CaptureError("invalid_memory_change", "replacementText is required.");
    }
    const inspected = await inspectMemory(vaultPath, input.path);
    const occurrences = exactOccurrenceCount(inspected.content, input.expectedText);
    if (occurrences !== 1) {
        throw new CaptureError(
            "memory_change_ambiguous",
            `Expected target text exactly once in ${inspected.path}; found ${occurrences}.`,
        );
    }
    return {
        operation: input.operation,
        path: inspected.path,
        expectedText: input.expectedText,
        replacementText: input.replacementText,
        destructive: false,
        instruction: "Apply this exact replacement through the learner-model skill, then re-read the file.",
    };
}

async function modelFiles(vaultPath) {
    const result = ["model/learner.md"];
    const sessionsDir = path.join(vaultPath, "model", "sessions");
    try {
        const entries = await readdir(sessionsDir, { withFileTypes: true });
        for (const entry of entries.slice(0, 100)) {
            if (entry.isFile() && entry.name.endsWith(".md")) result.push(`model/sessions/${entry.name}`);
        }
    } catch (error) {
        if (error.code !== "ENOENT") throw error;
    }
    return result;
}

export async function prepareDeletion(vaultPath, input) {
    const inspected = await inspectMemory(vaultPath, input.path);
    const passage = typeof input.passage === "string" && input.passage.length > 0 ? input.passage : null;
    if (passage && exactOccurrenceCount(inspected.content, passage) !== 1) {
        throw new CaptureError("deletion_scope_ambiguous", "The requested passage must occur exactly once.");
    }
    const references = [];
    const needle = path.basename(inspected.path);
    for (const relativePath of await modelFiles(vaultPath)) {
        if (relativePath === inspected.path) continue;
        try {
            const candidate = await inspectMemory(vaultPath, relativePath);
            if (candidate.content.includes(needle) || (passage && candidate.content.includes(passage))) {
                references.push(relativePath);
            }
        } catch (error) {
            if (!["ENOENT", "memory_too_large"].includes(error.code)) throw error;
        }
    }
    return {
        operation: "delete",
        path: inspected.path,
        passage,
        wholeFile: passage === null,
        affectedReferences: references,
        destructive: true,
        requiresSeparateConfirmation: true,
        instruction: "Do not delete yet. Present this exact scope and affected references for explicit user confirmation.",
    };
}
