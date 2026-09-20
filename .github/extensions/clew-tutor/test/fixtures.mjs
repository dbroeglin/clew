import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { MEMORY_MARKER } from "../vault.mjs";

let counter = 0;

// Build a normalized-shape raw event with learner/chat/goal defaults; override as needed.
export function event(overrides = {}) {
    counter += 1;
    return {
        interactionId: overrides.interactionId ?? `evt-${counter}`,
        source: overrides.source ?? "chat",
        kind: overrides.kind ?? "goal",
        origin: overrides.origin ?? "learner",
        at: overrides.at ?? "2026-09-20T10:00:00.000Z",
        text: overrides.text ?? "",
        futureScope: overrides.futureScope,
        ref: overrides.ref,
    };
}

// Create a throwaway vault directory in the OS temp area. `model` selects a starting shape:
// none, a recognized compact summary, an advanced profile, or unrecognized content.
export async function makeVault({ model } = {}) {
    const root = await mkdtemp(path.join(tmpdir(), "clew-tutor-"));
    if (model === "recognized") {
        await writeSummary(root, "# Learner");
    } else if (model === "advanced") {
        await mkdir(path.join(root, "model"), { recursive: true });
        await writeFile(path.join(root, "model", "profile.md"), "advanced profile\n", "utf8");
    } else if (model === "unrecognized") {
        await mkdir(path.join(root, "model"), { recursive: true });
        await writeFile(path.join(root, "model", "notes.md"), "loose notes\n", "utf8");
    } else if (model === "double-marker") {
        await mkdir(path.join(root, "model"), { recursive: true });
        await writeFile(path.join(root, "model", "learner.md"), `${MEMORY_MARKER}\n${MEMORY_MARKER}\n`, "utf8");
    }
    return root;
}

export async function writeSummary(root, body) {
    await mkdir(path.join(root, "model"), { recursive: true });
    await writeFile(path.join(root, "model", "learner.md"), `${MEMORY_MARKER}\n${body}\n`, "utf8");
}

export async function writeSession(root, name, body = "# session\n") {
    await mkdir(path.join(root, "model", "sessions"), { recursive: true });
    await writeFile(path.join(root, "model", "sessions", name), body, "utf8");
}
