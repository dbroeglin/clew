import assert from "node:assert/strict";
import test from "node:test";
import { classify } from "../gating.mjs";
import { event } from "./fixtures.mjs";

test("meaningful learner activity is classified to its compact-memory target", () => {
    assert.deepEqual(pick(classify(event({ kind: "goal" }))), { write: true, target: "summary", category: "goal" });
    assert.deepEqual(pick(classify(event({ kind: "takeaway" }))), { write: true, target: "summary", category: "learning-note" });
    assert.deepEqual(pick(classify(event({ kind: "correction" }))), { write: true, target: "summary", category: "correction" });
    assert.deepEqual(pick(classify(event({ kind: "attempt", source: "canvas" }))), { write: true, target: "session", category: "attempt" });
    assert.deepEqual(pick(classify(event({ kind: "supplied_work" }))), { write: true, target: "artifact", category: "supplied-work" });
});

test("a preference is recorded only with explicit future scope", () => {
    assert.equal(classify(event({ kind: "preference", futureScope: false })).write, false);
    assert.equal(classify(event({ kind: "preference", futureScope: true })).write, true);
});

test("non-learner input is never recorded as learner memory", () => {
    for (const origin of ["assistant", "agent", "system", "injection"]) {
        const decision = classify(event({ kind: "takeaway", origin }));
        assert.equal(decision.write, false, `${origin} must not be a write`);
    }
});

test("recall, inspection, configuration and agent canvas actions are read-only", () => {
    for (const kind of ["question", "recall", "continue", "inspect", "config", "status", "view_change", "agent_action"]) {
        assert.equal(classify(event({ kind })).write, false, `${kind} must be read-only`);
    }
});

test("malformed events are rejected rather than guessed", () => {
    assert.throws(() => classify(event({ kind: "unknown_kind" })), { code: "invalid_event" });
    assert.throws(() => classify(event({ origin: "robot" })), { code: "invalid_event" });
    assert.throws(() => classify(event({ at: "not-a-date" })), { code: "invalid_event" });
    assert.throws(() => classify(event({ kind: "goal", text: "   " })), { code: "invalid_event" });
    assert.throws(() => classify({ source: "chat", kind: "goal", origin: "learner", at: "2026-09-20T10:00:00Z" }), { code: "invalid_event" });
});

function pick(decision) {
    return { write: decision.write, target: decision.target, category: decision.category };
}
