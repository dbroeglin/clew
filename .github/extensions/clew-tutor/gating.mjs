import { MEANINGFUL_KINDS, normalizeEvent } from "./events.mjs";
import { CaptureError } from "./errors.mjs";

// Maps a meaningful, learner-authored kind to the compact-memory location it would
// update and a category label. These are the only targets the contract supports:
// the summary (model/learner.md), a dated session note, or an optional artifact.
const TARGETS = {
    goal: { target: "summary", category: "goal" },
    preference: { target: "summary", category: "preference" },
    proposal_response: { target: "summary", category: "preference" },
    takeaway: { target: "summary", category: "learning-note" },
    correction: { target: "summary", category: "correction" },
    stop_use: { target: "summary", category: "stop-use" },
    attempt: { target: "session", category: "attempt" },
    revision: { target: "session", category: "attempt" },
    hint_request: { target: "session", category: "help" },
    supplied_work: { target: "artifact", category: "supplied-work" },
};

// Decide whether an event is a meaningful write and, if so, where it belongs.
// This only classifies; the tutor agent, following the pinned skill, performs any
// actual edit. Read-only, non-learner and current-only inputs return write:false.
export function classify(rawEvent) {
    const event = normalizeEvent(rawEvent);
    if (event.origin !== "learner") {
        return decision(event, false, null, null, `not learner-authored (${event.origin})`);
    }
    if (!MEANINGFUL_KINDS.has(event.kind)) {
        return decision(event, false, null, null, `read-only kind (${event.kind})`);
    }
    if (event.text.trim().length === 0) {
        throw new CaptureError(
            "invalid_event",
            `Meaningful learner activity (${event.kind}) requires learner text.`,
        );
    }
    if (event.kind === "preference" && !event.futureScope) {
        return decision(event, false, null, null, "current-only request without explicit future scope");
    }
    const mapping = TARGETS[event.kind];
    return decision(event, true, mapping.target, mapping.category, "meaningful learner activity");
}

function decision(event, write, target, category, reason) {
    return { event, write, target, category, reason };
}
