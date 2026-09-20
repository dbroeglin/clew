import assert from "node:assert/strict";
import test from "node:test";
import { inspectModel, preflight, readSessions, readSummary } from "../vault.mjs";
import { makeVault, writeSession } from "./fixtures.mjs";

test("an empty or missing model allows capture writes", async () => {
    const result = await preflight(await makeVault());
    assert.equal(result.allowCaptureWrites, true);
    assert.equal(result.state, "empty");
});

test("a recognized compact summary is writable", async () => {
    const result = await inspectModel(await makeVault({ model: "recognized" }));
    assert.equal(result.state, "recognized");
});

test("advanced, unrecognized or duplicate-marker models require migration", async () => {
    for (const model of ["advanced", "unrecognized", "double-marker"]) {
        const result = await preflight(await makeVault({ model }));
        assert.equal(result.allowCaptureWrites, false, `${model} must block writes`);
        assert.equal(result.state, "needs_migration");
    }
});

test("the readers return memory content without writing", async () => {
    const vault = await makeVault({ model: "recognized" });
    await writeSession(vault, "2026-09-20-limits.md");
    assert.match(await readSummary(vault), /clew-learning-memory/);
    assert.deepEqual(await readSessions(vault), ["2026-09-20-limits.md"]);
});
