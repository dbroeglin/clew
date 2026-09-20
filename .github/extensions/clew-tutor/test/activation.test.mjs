import assert from "node:assert/strict";
import test from "node:test";
import { isTutorAgent, rootSelectionFromEvent } from "../activation.mjs";

test("agent identity accepts the stable id or display name", () => {
    assert.equal(isTutorAgent({ id: "clew-tutor" }), true);
    assert.equal(isTutorAgent({ displayName: "Clew Tutor" }), true);
    assert.equal(isTutorAgent({ id: "general-purpose", displayName: "General purpose" }), false);
});

test("delegated custom-agent events never activate or pause root capture", () => {
    const delegated = {
        agentId: "delegated-instance",
        data: { agentName: "clew-tutor", agentDisplayName: "Clew Tutor" },
    };
    assert.equal(rootSelectionFromEvent(delegated), null);
    assert.equal(rootSelectionFromEvent({
        data: { agentName: "clew-tutor", agentDisplayName: "Clew Tutor" },
    }), true);
    assert.equal(rootSelectionFromEvent({
        data: { agentName: "other", agentDisplayName: "Other" },
    }), false);
});
