import { existsSync, renameSync, statSync, writeFileSync, rmSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve, sep } from "node:path";

/** Nearest ancestor directory (or the directory itself) that contains `.obsidian/`. */
export function findVault(path) {
    let dir = resolve(path);
    try {
        if (!statSync(dir).isDirectory()) dir = dirname(dir);
    } catch {
        dir = dirname(dir);
    }
    for (;;) {
        if (existsSync(join(dir, ".obsidian"))) return dir;
        const parent = dirname(dir);
        if (parent === dir) return null;
        dir = parent;
    }
}

export function isInside(root, path) {
    const rel = relative(root, path);
    return rel === "" || (rel.split(/[\\/]/)[0] !== ".." && !isAbsolute(rel));
}

export function toPosix(rel) {
    return rel.split(sep).join("/");
}

export function vaultPath(vault, path) {
    return toPosix(relative(vault, path));
}

export function slugify(text) {
    return String(text).normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
        .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "publication";
}

export function localDate(date) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Replace a file through a sibling temporary file so readers never see partial content. */
export function writeAtomic(path, content) {
    const temporary = `${path}.${process.pid}.tmp`;
    writeFileSync(temporary, content);
    try {
        renameSync(temporary, path);
    } catch (error) {
        // Sync clients such as OneDrive can briefly lock the destination on Windows.
        rmSync(temporary, { force: true });
        writeFileSync(path, content);
        if (!existsSync(path)) throw error;
    }
}
