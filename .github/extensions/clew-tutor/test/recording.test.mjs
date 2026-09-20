import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { createCaptureLayer } from "../capture.mjs";
import { CaptureError } from "../errors.mjs";
import { applyRecordingRequest } from "./reference-recorder.mjs";
import { event, makeVault } from "./fixtures.mjs";

function activated(vault) {
    const capture = createCaptureLayer();
    assert.equal(capture.activate({ learner: "learner-1", vault, activation: "explicit-human" }).ok, true);
    return capture;
}

test("a summary request is semantic, bounded and recordable in a synthetic vault", async () => {
    const vault = await makeVault({ model: "recognized" });
    const capture = activated(vault);
    capture.admit(event({
        kind: "goal",
        text: "Understand eigenvectors before Friday",
        ref: { itemId: "linear-algebra" },
    }));

    const [request] = capture.requests();
    assert.equal(request.operation, "update_summary");
    assert.equal(request.target, "summary");
    assert.equal(request.category, "goal");
    assert.deepEqual(request.sources, ["chat"]);
    assert.equal(request.learnerInputs.length, 1);
    assert.equal(Object.hasOwn(request, "vaultContent"), false);
    assert.equal(Object.hasOwn(request, "transcript"), false);

    const result = await applyRecordingRequest(vault, request);
    assert.equal(result.status, "recorded");
    capture.reportRecording(request.key, result);
    const summary = await readFile(path.join(vault, "model", "learner.md"), "utf8");
    assert.match(summary, /Understand eigenvectors before Friday/);
    const completion = await capture.completion();
    assert.equal(completion.recorded.length, 1);
    assert.equal(completion.reported[0].status, "recorded");
});

test("attempt and supplied-work requests produce dated session and artifact evidence", async () => {
    const vault = await makeVault({ model: "recognized" });
    const capture = activated(vault);
    capture.admit(event({
        kind: "attempt",
        text: "I differentiated x squared as 2x.",
        ref: { attemptId: "attempt-1", itemId: "derivatives" },
    }));
    capture.admit(event({
        interactionId: "artifact-1",
        kind: "supplied_work",
        text: "My completed proof with two cases.",
        ref: { itemId: "proof-homework" },
    }));

    const requests = capture.requests();
    assert.deepEqual(requests.map((request) => request.operation).sort(), ["record_session", "save_artifact"]);
    for (const request of requests) {
        const result = await applyRecordingRequest(vault, request);
        assert.equal(result.status, "recorded");
        capture.reportRecording(request.key, result);
    }
    const completion = await capture.completion();
    assert.equal(completion.unrecorded.length, 0);
    assert.equal(completion.recorded.length, 2);
});

test("read-only activity emits no recording request", async () => {
    const capture = activated(await makeVault({ model: "recognized" }));
    const result = capture.admit(event({ kind: "recall", text: "What did we cover last time?" }));
    assert.equal(result.classification.write, false);
    assert.deepEqual(capture.requests(), []);
});

test("partial and failed results remain explicit instead of looking successful", async () => {
    const vault = await makeVault({ model: "recognized" });
    const capture = activated(vault);
    capture.admit(event({
        kind: "supplied_work",
        text: "A synthetic lab report.",
        ref: { itemId: "lab-report" },
    }));
    const [request] = capture.requests();
    const partial = await applyRecordingRequest(vault, request, { failAfterArtifact: true });
    assert.equal(partial.status, "partial");
    assert.equal(partial.persistedPaths.length, 1);
    assert.match(partial.error, /synthetic failure/);
    assert.equal(capture.reportRecording(request.key, partial).status, "partial");

    assert.throws(
        () => capture.reportRecording("missing-request", { status: "failed", error: "not found" }),
        (error) => error instanceof CaptureError && error.code === "unknown_recording_request",
    );
    assert.throws(
        () => capture.reportRecording(request.key, {
            status: "recorded",
            persistedPaths: ["C:\\private\\outside.md"],
        }),
        (error) => error instanceof CaptureError && error.code === "invalid_recording_result",
    );
    assert.throws(
        () => capture.reportRecording(request.key, {
            status: "recorded",
            persistedPaths: ["model/sessions/wrong-target.md"],
        }),
        (error) => error instanceof CaptureError && error.code === "invalid_recording_result",
    );
});

test("event payloads are bounded before request creation", async () => {
    const capture = activated(await makeVault({ model: "recognized" }));
    assert.throws(
        () => capture.admit(event({ kind: "goal", text: "x".repeat(8193) })),
        (error) => error instanceof CaptureError && error.code === "invalid_event",
    );
});

test("session completion requires matching evidence, not only a same-day filename", async () => {
    const vault = await makeVault({ model: "recognized" });
    const capture = activated(vault);
    capture.admit(event({
        kind: "attempt",
        text: "My answer used the chain rule.",
        ref: { attemptId: "chain-rule", itemId: "derivatives" },
    }));
    const unrelated = {
        ...capture.requests()[0],
        learnerInputs: [{ ...capture.requests()[0].learnerInputs[0], text: "Unrelated same-day work." }],
        ref: { attemptId: "unrelated", itemId: "other" },
    };
    await applyRecordingRequest(vault, unrelated);
    const completion = await capture.completion();
    assert.equal(completion.recorded.length, 0);
    assert.equal(completion.unrecorded.length, 1);
});

test("concurrent distinct session requests allocate collision-safe filenames", async () => {
    const vault = await makeVault({ model: "recognized" });
    const first = activated(vault);
    const second = activated(vault);
    first.admit(event({
        interactionId: "concurrent-1",
        kind: "attempt",
        text: "First distinct attempt.",
        ref: { attemptId: "first", itemId: "same-topic" },
    }));
    second.admit(event({
        interactionId: "concurrent-2",
        kind: "attempt",
        text: "Second distinct attempt.",
        ref: { attemptId: "second", itemId: "same-topic" },
    }));
    const results = await Promise.all([
        applyRecordingRequest(vault, first.requests()[0]),
        applyRecordingRequest(vault, second.requests()[0]),
    ]);
    assert.equal(results.every((result) => result.status === "recorded"), true);
    assert.equal(new Set(results.flatMap((result) => result.persistedPaths)).size, 2);
});

test("one correlated request keeps the original plus recent evidence within a fixed bound", async () => {
    const capture = activated(await makeVault({ model: "recognized" }));
    for (let index = 0; index < 30; index += 1) {
        capture.admit(event({
            interactionId: `bounded-${index}`,
            kind: index === 0 ? "attempt" : "revision",
            text: `revision ${index} ${"x".repeat(2000)}`,
            ref: { attemptId: "bounded-attempt", itemId: "limits" },
            at: `2026-09-20T10:${String(index).padStart(2, "0")}:00.000Z`,
        }));
    }
    const [request] = capture.requests();
    assert.equal(request.learnerInputs[0].interactionId, "bounded-0");
    assert.equal(request.learnerInputs.length <= 20, true);
    assert.equal(request.learnerInputs.reduce((total, input) => total + input.text.length, 0) <= 32 * 1024, true);
    assert.equal(request.omittedInteractionCount > 0, true);
});
