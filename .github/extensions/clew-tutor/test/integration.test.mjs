import assert from "node:assert/strict";
import test from "node:test";
import { CaptureError } from "../errors.mjs";
import { createTutorIntegration } from "../integration.mjs";
import { makeVault } from "./fixtures.mjs";

async function activeIntegration(options) {
    const integration = createTutorIntegration(options);
    integration.setSelected(true);
    integration.bind({ learner: "learner-1", vaultPath: await makeVault({ model: "recognized" }) });
    return integration;
}

test("the first prompt after tutor selection can be disposed after binding in the same turn", async () => {
    const integration = createTutorIntegration();
    integration.setSelected(true);
    const prompt = integration.beginPrompt("2026-09-20T09:59:00.000Z");
    assert.ok(prompt);
    integration.bind({ learner: "learner-1", vaultPath: await makeVault({ model: "recognized" }) });
    const result = integration.disposePrompt({
        promptId: prompt.id,
        kind: "goal",
        at: "2026-09-20T09:59:00.000Z",
        text: "Use this first tutor prompt as my goal",
    });
    assert.equal(result.request.target, "summary");
});

test("automatic chat capture requires one explicit disposition per active prompt", async () => {
    const integration = await activeIntegration();
    const prompt = integration.beginPrompt("2026-09-20T10:00:00.000Z");
    assert.match(integration.prompts.nextBlockReason(), new RegExp(prompt.id));
    assert.equal(integration.prompts.nextBlockReason(), null);

    const result = integration.disposePrompt({
        promptId: prompt.id,
        kind: "goal",
        at: "2026-09-20T10:00:00.000Z",
        text: "Practice limits every weekday",
        futureScope: true,
        ref: { itemId: "limits" },
    });
    assert.equal(result.classification.write, true);
    assert.equal(result.request.operation, "update_summary");
    assert.equal(integration.prompts.unresolved().length, 0);
});

test("read-only prompt disposition creates no request", async () => {
    const integration = await activeIntegration();
    const prompt = integration.beginPrompt("2026-09-20T10:01:00.000Z");
    const result = integration.disposePrompt({
        promptId: prompt.id,
        kind: "question",
        at: "2026-09-20T10:01:00.000Z",
        text: "",
    });
    assert.equal(result.classification.write, false);
    assert.equal(result.request, null);
    assert.equal(integration.status().prompts[0].state, "read_only");
});

test("a prompt cannot be disposed twice or admitted after its identity expires", async () => {
    const integration = await activeIntegration();
    const prompt = integration.beginPrompt("2026-09-20T10:01:30.000Z");
    integration.disposePrompt({
        promptId: prompt.id,
        kind: "question",
        at: "2026-09-20T10:01:30.000Z",
    });
    assert.throws(
        () => integration.disposePrompt({
            promptId: prompt.id,
            interactionId: "different-id",
            kind: "goal",
            at: "2026-09-20T10:01:31.000Z",
            text: "This must not become a ghost request",
        }),
        (error) => error instanceof CaptureError && error.code === "prompt_already_disposed",
    );
    assert.equal(integration.capture.requests().length, 0);
});

test("an active episode cannot be rebound to another learner or vault", async () => {
    const integration = await activeIntegration();
    assert.throws(
        () => integration.bind({ learner: "learner-2", vaultPath: integration.capture.vault }),
        (error) => error instanceof CaptureError && error.code === "episode_already_bound",
    );
    assert.equal(integration.capture.learner, "learner-1");
    assert.equal(integration.capture.requests().length, 0);
});

test("selection pauses capture and a fresh integration does not recover in-memory state", async () => {
    const integration = await activeIntegration();
    integration.beginPrompt("2026-09-20T10:02:00.000Z");
    assert.equal(integration.setSelected(false).state, "paused");
    assert.equal(integration.beginPrompt("2026-09-20T10:03:00.000Z"), null);
    assert.throws(
        () => integration.resume(),
        (error) => error instanceof CaptureError && error.code === "tutor_not_selected",
    );
    assert.equal(integration.setSelected(true).state, "active");

    const reloaded = createTutorIntegration();
    reloaded.setSelected(true, { explicit: false });
    assert.equal(reloaded.capture.state, "inactive");
    assert.equal(reloaded.beginPrompt("2026-09-20T10:03:30.000Z"), null);
    assert.throws(
        () => reloaded.bind({ learner: "learner-1", vaultPath: integration.capture.vault }),
        (error) => error instanceof CaptureError && error.code === "explicit_activation_required",
    );
    assert.deepEqual(reloaded.prompts.list(), []);
    assert.deepEqual(reloaded.capture.requests(), []);
});

test("ending an episode requires another explicit tutor selection before rebinding", async () => {
    const integration = await activeIntegration();
    const vaultPath = integration.capture.vault;
    integration.end();
    assert.equal(integration.beginPrompt("2026-09-20T10:03:45.000Z"), null);
    assert.throws(
        () => integration.bind({ learner: "learner-1", vaultPath }),
        (error) => error instanceof CaptureError && error.code === "explicit_activation_required",
    );
    integration.setSelected(true);
    assert.ok(integration.beginPrompt("2026-09-20T10:03:50.000Z"));
});

test("headless canvas capture rejects unverified origin and correlates chat with the same attempt", async () => {
    const integration = await activeIntegration();
    assert.throws(
        () => integration.recordCanvas("attempt", {
            learnerOrigin: false,
            interactionId: "canvas-1",
            attemptId: "attempt-1",
            itemId: "limits",
            text: "answer",
        }),
        (error) => error instanceof CaptureError && error.code === "unverified_learner_origin",
    );

    const prompt = integration.beginPrompt("2026-09-20T10:04:00.000Z");
    integration.disposePrompt({
        promptId: prompt.id,
        interactionId: "chat-1",
        kind: "attempt",
        at: "2026-09-20T10:04:00.000Z",
        text: "My first limit is 2.",
        ref: { attemptId: "attempt-1", itemId: "limits" },
    });
    integration.recordCanvas("revision", {
        learnerOrigin: true,
        interactionId: "canvas-2",
        attemptId: "attempt-1",
        itemId: "limits",
        text: "I revised the limit to 3.",
        at: "2026-09-20T10:05:00.000Z",
    });

    const [request] = integration.capture.requests();
    assert.equal(integration.capture.requests().length, 1);
    assert.deepEqual(new Set(request.sources), new Set(["chat", "canvas"]));
    assert.equal(request.learnerInputs.length, 2);
});

test("a takeaway about an attempt remains a separate summary request", async () => {
    const integration = await activeIntegration();
    integration.recordCanvas("attempt", {
        learnerOrigin: true,
        interactionId: "canvas-attempt",
        attemptId: "attempt-2",
        itemId: "limits",
        text: "I first answered 2.",
        at: "2026-09-20T10:05:00.000Z",
    });
    const prompt = integration.beginPrompt("2026-09-20T10:05:30.000Z");
    integration.disposePrompt({
        promptId: prompt.id,
        interactionId: "chat-takeaway",
        kind: "takeaway",
        at: "2026-09-20T10:05:30.000Z",
        text: "I need to check the direction of approach.",
        ref: { attemptId: "attempt-2", itemId: "limits" },
    });
    assert.deepEqual(
        new Set(integration.capture.requests().map((request) => request.target)),
        new Set(["session", "summary"]),
    );
});

test("independent tutor sessions do not share candidates or prompt state", async () => {
    const [first, second] = await Promise.all([activeIntegration(), activeIntegration()]);
    const firstPrompt = first.beginPrompt("2026-09-20T10:06:00.000Z");
    first.disposePrompt({
        promptId: firstPrompt.id,
        kind: "goal",
        at: "2026-09-20T10:06:00.000Z",
        text: "First learner goal",
    });
    assert.equal(first.capture.requests().length, 1);
    assert.equal(second.capture.requests().length, 0);
    assert.equal(second.prompts.list().length, 0);
});

test("prompt tracking is bounded and expiration is explicit", async () => {
    const integration = await activeIntegration({ promptLimit: 2 });
    const first = integration.beginPrompt("2026-09-20T10:07:00.000Z");
    integration.beginPrompt("2026-09-20T10:08:00.000Z");
    integration.beginPrompt("2026-09-20T10:09:00.000Z");
    assert.equal(integration.prompts.list().length, 2);
    assert.throws(
        () => integration.disposePrompt({
            promptId: first.id,
            kind: "question",
            at: "2026-09-20T10:07:00.000Z",
        }),
        (error) => error instanceof CaptureError && error.code === "unknown_prompt",
    );
});
