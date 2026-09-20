import assert from "node:assert/strict";
import test from "node:test";
import { correlate } from "../correlation.mjs";
import { classify } from "../gating.mjs";
import { event } from "./fixtures.mjs";

function candidates(...raws) {
    return correlate(raws.map((raw) => classify(raw)));
}

test("the same work across chat and canvas correlates into one candidate", () => {
    const result = candidates(
        event({ kind: "attempt", source: "canvas", ref: { attemptId: "a1" }, text: "x = 3" }),
        event({ kind: "takeaway", source: "chat", ref: { attemptId: "a1" }, text: "I see why x = 3" }),
    );
    assert.equal(result.length, 1);
    assert.deepEqual([...result[0].sources].sort(), ["canvas", "chat"]);
});

test("genuinely distinct attempts stay distinct", () => {
    const result = candidates(
        event({ kind: "attempt", source: "canvas", ref: { attemptId: "a1" }, text: "x = 3" }),
        event({ kind: "attempt", source: "canvas", ref: { attemptId: "a2" }, text: "x = 3" }),
    );
    assert.equal(result.length, 2);
});

test("re-delivery of the same interaction is idempotent", () => {
    const duplicate = event({ kind: "goal", interactionId: "dup", text: "same goal" });
    const result = candidates(duplicate, { ...duplicate });
    assert.equal(result.length, 1);
});

test("read-only and non-learner classifications never become candidates", () => {
    const result = candidates(
        event({ kind: "recall" }),
        event({ kind: "takeaway", origin: "assistant", text: "not the learner" }),
    );
    assert.equal(result.length, 0);
});
