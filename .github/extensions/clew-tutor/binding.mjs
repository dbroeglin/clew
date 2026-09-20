import { realpath, stat } from "node:fs/promises";
import path from "node:path";
import { CaptureError } from "./errors.mjs";

export async function validateVaultBinding(vaultPath, repositoryPath = process.cwd()) {
    if (typeof vaultPath !== "string" || !path.isAbsolute(vaultPath)) {
        throw new CaptureError("invalid_vault", "The vault path must be absolute.");
    }
    let info;
    try {
        info = await stat(vaultPath);
    } catch (error) {
        if (error.code === "ENOENT") {
            throw new CaptureError("invalid_vault", "The configured vault directory does not exist.");
        }
        throw error;
    }
    if (!info.isDirectory()) {
        throw new CaptureError("invalid_vault", "The configured vault path must be a directory.");
    }
    const [vault, repository] = await Promise.all([realpath(vaultPath), realpath(repositoryPath)]);
    const relative = path.relative(repository, vault);
    if (relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
        throw new CaptureError("invalid_vault", "The learner vault must be outside the repository.");
    }
    return vault;
}
