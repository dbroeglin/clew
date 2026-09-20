import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { inspectMemory, prepareDeletion, prepareMemoryChange } from "../controls.mjs";
import { CaptureError } from "../errors.mjs";
import { makeVault, writeSession, writeSummary } from "./fixtures.mjs";

test("bounded inspection reads one compact-memory file and rejects path escape", async () => {
    const vault = await makeVault({ model: "recognized" });
    const inspected = await inspectMemory(vault, "model/learner.md");
    assert.equal(inspected.path, "model/learner.md");
    assert.match(inspected.content, /clew-learning-memory/);
    await assert.rejects(
        () => inspectMemory(vault, "../outside.md"),
        (error) => error instanceof CaptureError && error.code === "invalid_memory_path",
    );
    await assert.rejects(
        () => inspectMemory(vault, "courses/private.md"),
        (error) => error instanceof CaptureError && error.code === "invalid_memory_path",
    );
});

test("correction and stop-use tools prepare exact replacements without writing", async () => {
    const vault = await makeVault();
    await writeSummary(vault, "# Learner\n\n## Preferences\n- Use flashcards every day.");
    const before = await readFile(path.join(vault, "model", "learner.md"), "utf8");
    const prepared = await prepareMemoryChange(vault, {
        operation: "stop_use",
        path: "model/learner.md",
        expectedText: "- Use flashcards every day.",
        replacementText: "- Do not treat flashcards as a standing preference.",
    });
    assert.equal(prepared.destructive, false);
    assert.match(prepared.instruction, /learner-model skill/);
    const after = await readFile(path.join(vault, "model", "learner.md"), "utf8");
    assert.equal(after, before);
});

test("memory changes reject ambiguous targets", async () => {
    const vault = await makeVault();
    await writeSummary(vault, "# Learner\n\n- repeated\n- repeated");
    await assert.rejects(
        () => prepareMemoryChange(vault, {
            operation: "correction",
            path: "model/learner.md",
            expectedText: "repeated",
            replacementText: "corrected",
        }),
        (error) => error instanceof CaptureError && error.code === "memory_change_ambiguous",
    );
});

test("deletion preparation reports exact scope and references but deletes nothing", async () => {
    const vault = await makeVault();
    await mkdir(path.join(vault, "artifacts"), { recursive: true });
    await writeFile(path.join(vault, "artifacts", "proof.md"), "private proof text", "utf8");
    await writeSummary(vault, "# Learner\n\nSee proof.md.");
    await writeSession(vault, "2026-09-20-proof.md", "Worked on proof.md.\n");

    const plan = await prepareDeletion(vault, { path: "artifacts/proof.md" });
    assert.equal(plan.destructive, true);
    assert.equal(plan.requiresSeparateConfirmation, true);
    assert.equal(plan.wholeFile, true);
    assert.deepEqual(new Set(plan.affectedReferences), new Set([
        "model/learner.md",
        "model/sessions/2026-09-20-proof.md",
    ]));
    assert.equal(await readFile(path.join(vault, "artifacts", "proof.md"), "utf8"), "private proof text");
});

test("inspection refuses oversized context", async () => {
    const vault = await makeVault();
    await mkdir(path.join(vault, "artifacts"), { recursive: true });
    await writeFile(path.join(vault, "artifacts", "large.md"), "x".repeat(16 * 1024 + 1), "utf8");
    await assert.rejects(
        () => inspectMemory(vault, "artifacts/large.md"),
        (error) => error instanceof CaptureError && error.code === "memory_too_large",
    );
});
