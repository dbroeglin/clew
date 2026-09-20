import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { MEMORY_MARKER } from "../vault.mjs";

const SUMMARY_SECTIONS = {
    goal: "Goals",
    preference: "Preferences",
    "learning-note": "Learning notes",
    correction: "Corrections",
    "stop-use": "Preferences",
};

function firstLearnerText(request) {
    return request.learnerInputs.map((input) => input.text.trim()).filter(Boolean).join("\n");
}

function slug(value) {
    const normalized = String(value ?? "learning").toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "");
    return normalized.slice(0, 48) || "learning";
}

async function readOrNull(filePath) {
    try {
        return await readFile(filePath, "utf8");
    } catch (error) {
        if (error.code === "ENOENT") return null;
        throw error;
    }
}

async function recordSummary(vaultPath, request) {
    const modelDir = path.join(vaultPath, "model");
    const summaryPath = path.join(modelDir, "learner.md");
    await mkdir(modelDir, { recursive: true });
    let content = await readOrNull(summaryPath);
    if (content === null) content = `${MEMORY_MARKER}\n\n# Learner\n`;
    const section = SUMMARY_SECTIONS[request.category] ?? "Learning notes";
    const text = firstLearnerText(request);
    if (content.includes(text)) return "model/learner.md";
    const heading = `## ${section}`;
    if (!content.includes(heading)) content = `${content.trimEnd()}\n\n${heading}\n`;
    content = `${content.trimEnd()}\n- ${text.replaceAll("\n", "\n  ")}\n`;
    await writeFile(summaryPath, content, "utf8");
    return "model/learner.md";
}

async function sessionFiles(vaultPath) {
    const directory = path.join(vaultPath, "model", "sessions");
    try {
        return await readdir(directory);
    } catch (error) {
        if (error.code === "ENOENT") return [];
        throw error;
    }
}

async function existingSessionFor(vaultPath, text) {
    for (const name of await sessionFiles(vaultPath)) {
        if (!name.endsWith(".md")) continue;
        const content = await readFile(path.join(vaultPath, "model", "sessions", name), "utf8");
        if (content.includes(text)) return `model/sessions/${name}`;
    }
    return null;
}

async function writeUniqueSession(vaultPath, request, extraLines = []) {
    const text = firstLearnerText(request);
    const existing = await existingSessionFor(vaultPath, text);
    if (existing) return existing;
    const directory = path.join(vaultPath, "model", "sessions");
    await mkdir(directory, { recursive: true });
    const day = request.occurredAt.slice(0, 10);
    const topic = slug(request.ref.itemId ?? request.category);
    const evidence = request.learnerInputs.map((input) => `- **${input.kind}:** ${input.text}`).join("\n");
    const content = `# Learning session — ${day}\n\n## Evidence\n${evidence}\n${extraLines.length ? `\n${extraLines.join("\n")}\n` : ""}`;
    for (let suffix = 0; suffix < 100; suffix += 1) {
        const name = `${day}-${topic}${suffix === 0 ? "" : `-${suffix + 1}`}.md`;
        try {
            await writeFile(path.join(directory, name), content, { encoding: "utf8", flag: "wx" });
            return `model/sessions/${name}`;
        } catch (error) {
            if (error.code !== "EEXIST") throw error;
        }
    }
    throw new Error("Could not allocate a unique synthetic session note.");
}

async function writeArtifact(vaultPath, request) {
    const directory = path.join(vaultPath, "artifacts");
    await mkdir(directory, { recursive: true });
    const day = request.occurredAt.slice(0, 10);
    const name = `${day}-${slug(request.ref.itemId ?? request.category)}.md`;
    const artifactPath = path.join(directory, name);
    const text = firstLearnerText(request);
    const existing = await readOrNull(artifactPath);
    if (existing !== text) await writeFile(artifactPath, text, "utf8");
    return `artifacts/${name}`;
}

// Test-only reference implementation. Production code emits requests and the
// tutor agent applies the pinned learner-model skill; this helper only proves the
// request contract against disposable synthetic vaults.
export async function applyRecordingRequest(vaultPath, request, options = {}) {
    const persistedPaths = [];
    try {
        if (request.operation === "update_summary") {
            persistedPaths.push(await recordSummary(vaultPath, request));
        } else if (request.operation === "record_session") {
            persistedPaths.push(await writeUniqueSession(vaultPath, request));
        } else if (request.operation === "save_artifact") {
            const artifact = await writeArtifact(vaultPath, request);
            persistedPaths.push(artifact);
            if (options.failAfterArtifact) throw new Error("synthetic failure after artifact write");
            persistedPaths.push(await writeUniqueSession(vaultPath, request, [`- Artifact: [[${artifact}]]`]));
        } else {
            throw new Error(`Unknown recording operation: ${request.operation}`);
        }
        return { status: "recorded", persistedPaths };
    } catch (error) {
        return {
            status: persistedPaths.length > 0 ? "partial" : "failed",
            persistedPaths,
            error: error.message,
        };
    }
}
