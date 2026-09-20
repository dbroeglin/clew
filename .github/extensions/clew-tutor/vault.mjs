import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

// The single marker that identifies a compact learner-memory summary.
export const MEMORY_MARKER = "<!-- clew-learning-memory: v1 -->";

async function listing(dir) {
    try {
        return await readdir(dir, { withFileTypes: true });
    } catch (error) {
        if (error.code === "ENOENT") return null;
        throw error;
    }
}

// Inspect <vault>/model to decide the ownership/migration state that gates the first
// capture write. This reads only directory names and the summary's marker line; it never
// reads or writes learner content, and never migrates anything.
export async function inspectModel(vaultPath) {
    const modelDir = path.join(vaultPath, "model");
    const entries = await listing(modelDir);
    if (entries === null || entries.length === 0) {
        return { state: "empty", reason: "no existing model directory" };
    }
    const names = new Set(entries.map((entry) => entry.name.toLowerCase()));
    if (names.has("profile.md") || names.has("index.md")) {
        return { state: "needs_migration", reason: "advanced or legacy profile.md/index.md present" };
    }
    let text;
    try {
        text = await readFile(path.join(modelDir, "learner.md"), "utf8");
    } catch (error) {
        if (error.code === "ENOENT") {
            return { state: "needs_migration", reason: "nonempty model without the recognized summary" };
        }
        throw error;
    }
    const markers = text.split(MEMORY_MARKER).length - 1;
    if (markers !== 1) {
        return { state: "needs_migration", reason: `expected exactly one memory marker, found ${markers}` };
    }
    return { state: "recognized", reason: "recognized compact learner memory" };
}

// The ownership/migration gate: capture writes are blocked until an existing, unrecognized
// model is explicitly resolved. Course reading is never gated by this.
export async function preflight(vaultPath) {
    const model = await inspectModel(vaultPath);
    return {
        allowCaptureWrites: model.state !== "needs_migration",
        state: model.state,
        reason: model.reason,
    };
}

export async function readSummary(vaultPath) {
    try {
        return await readFile(path.join(vaultPath, "model", "learner.md"), "utf8");
    } catch (error) {
        if (error.code === "ENOENT") return null;
        throw error;
    }
}

export async function readSessions(vaultPath) {
    const entries = await listing(path.join(vaultPath, "model", "sessions"));
    if (!entries) return [];
    return entries.filter((entry) => entry.isFile() && entry.name.endsWith(".md")).map((entry) => entry.name);
}
