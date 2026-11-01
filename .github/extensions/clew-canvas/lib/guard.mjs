/** Tutor write guard: Obsidian vault content is read-only except publication layouts. */
import { relative, resolve } from "node:path";
import { findVault, toPosix } from "./paths.mjs";

const PATH_KEYS = ["path", "file_path", "filePath", "filename", "target", "destination", "source", "new_path", "old_path"];
const MUTATING = /create|edit|write|patch|replace|insert|delete|remove|move|rename/i;

export function isMutatingTool(name) {
    return typeof name === "string" && MUTATING.test(name);
}

/** File paths that a file-mutating tool call targets. Free text such as messages is ignored. */
export function targetPaths(args) {
    if (!args || typeof args !== "object") return [];
    const paths = PATH_KEYS.map((key) => args[key]).filter((value) => typeof value === "string" && value);
    for (const key of ["paths", "files"]) {
        if (Array.isArray(args[key])) paths.push(...args[key].filter((value) => typeof value === "string" && value));
    }
    for (const patch of [args.input, args.patch]) {
        if (typeof patch !== "string") continue;
        for (const match of patch.matchAll(/^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+?)\s*$/gm)) paths.push(match[1]);
    }
    return paths;
}

export function isLayoutPath(vault, path) {
    const parts = relative(vault, path).split(/[\\/]/);
    return parts.length === 3 && parts[0].toLowerCase() === "activity" && parts[1].toLowerCase() === "layouts" &&
        /\.json$/i.test(parts[2]);
}

/** Denial reason for a tool call, or null when it may proceed. */
export function vaultWriteDenial({ toolName, toolArgs, cwd }) {
    if (!isMutatingTool(toolName)) return null;
    for (const raw of targetPaths(toolArgs)) {
        const path = resolve(cwd, raw);
        const vault = findVault(path);
        if (!vault || isLayoutPath(vault, path)) continue;
        return `Clew tutor guard: "${toPosix(relative(vault, path)) || "."}" is inside the Obsidian vault, which is ` +
            "read-only for the tutor. Only publication layouts in Activity/Layouts/*.json may be written.";
    }
    return null;
}

export function isTutorAgent(name) {
    return typeof name === "string" && name.trim().toLowerCase().replace(/[\s_]+/g, "-") === "clew-tutor";
}
