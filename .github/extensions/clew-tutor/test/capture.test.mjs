import assert from "node:assert/strict";
import test from "node:test";
import { createCaptureLayer } from "../capture.mjs";
import { event, makeVault, writeSummary } from "./fixtures.mjs";

function activated(vault) {
    const capture = createCaptureLayer();
    assert.equal(capture.activate({ learner: "l1", vault, activation: "explicit-human" }).ok, true);
    return capture;
}

test("only meaningful learner activity in an active episode becomes a candidate", async () => {
    const capture = activated(await makeVault({ model: "recognized" }));
    assert.equal(capture.admit(event({ kind: "goal", text: "master limits before the exam" })).admitted, true);
    assert.equal(capture.admit(event({ kind: "takeaway", origin: "assistant", text: "here is the answer" })).admitted, false);
    assert.equal(capture.admit(event({ kind: "recall" })).admitted, false);
    const candidates = capture.candidates();
    assert.equal(candidates.length, 1);
    assert.equal(candidates[0].category, "goal");
});

test("a paused or ended episode admits nothing", async () => {
    const capture = activated(await makeVault({ model: "recognized" }));
    capture.pause();
    assert.equal(capture.admit(event({ kind: "goal", text: "paused goal" })).admitted, false);
    capture.end();
    assert.equal(capture.admit(event({ kind: "goal", text: "ended goal" })).admitted, false);
    assert.equal(capture.candidates().length, 0);
});

test("the ownership/migration preflight blocks writes to an unrecognized model", async () => {
    const capture = activated(await makeVault({ model: "advanced" }));
    const preflight = await capture.preflight();
    assert.equal(preflight.allowCaptureWrites, false);
    assert.equal(preflight.state, "needs_migration");
});

test("completion surfaces an unrecorded candidate and clears once the agent records it", async () => {
    const vault = await makeVault({ model: "recognized" });
    const capture = activated(vault);
    capture.admit(event({ kind: "goal", text: "finish the derivatives worksheet" }));

    let completion = await capture.completion();
    assert.equal(completion.unrecorded.length, 1);
    assert.equal(completion.recorded.length, 0);

    // Simulate the tutor agent recording the goal into the summary through the skill.
    await writeSummary(vault, "## Goals\n- finish the derivatives worksheet (learner statement, 2026-09-20).");

    completion = await capture.completion();
    assert.equal(completion.recorded.length, 1);
    assert.equal(completion.unrecorded.length, 0);
});
