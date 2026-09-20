import { CaptureError } from "./errors.mjs";

// Who actually produced an interaction. Only `learner` input can become memory;
// everything else is context, never recorded as the learner's own activity.
export const ORIGINS = new Set(["learner", "assistant", "agent", "system", "injection"]);

export const SOURCES = new Set(["chat", "canvas"]);

// Kinds that can carry genuine learning activity worth recording.
export const MEANINGFUL_KINDS = new Set([
    "goal", "preference", "takeaway", "attempt", "supplied_work",
    "correction", "stop_use", "hint_request", "proposal_response", "revision",
]);

// Kinds that are always read-only: they may shape a reply but are never a write
// trigger, and admitting one must not create a session, note or timestamp.
export const READ_ONLY_KINDS = new Set([
    "question", "recall", "continue", "inspect", "config", "status",
    "view_change", "agent_action",
]);

const ISO_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

// Normalize a raw host event into the closed shape the capture layer reasons over.
// A malformed event is rejected rather than guessed, so an unknown surface cannot
// smuggle unclassified input past the gate.
export function normalizeEvent(raw) {
    if (!raw || typeof raw !== "object") {
        throw new CaptureError("invalid_event", "An interaction event object is required.");
    }
    const { interactionId, source, kind, origin } = raw;
    if (typeof interactionId !== "string" || interactionId.length === 0) {
        throw new CaptureError("invalid_event", "interactionId is required and must be a non-empty string.");
    }
    if (!SOURCES.has(source)) {
        throw new CaptureError("invalid_event", `Unknown interaction source: ${String(source)}`);
    }
    if (!MEANINGFUL_KINDS.has(kind) && !READ_ONLY_KINDS.has(kind)) {
        throw new CaptureError("invalid_event", `Unknown interaction kind: ${String(kind)}`);
    }
    if (!ORIGINS.has(origin)) {
        throw new CaptureError("invalid_event", `Unknown interaction origin: ${String(origin)}`);
    }
    if (typeof raw.at !== "string" || !ISO_TIMESTAMP.test(raw.at)) {
        throw new CaptureError("invalid_event", "A valid ISO-8601 `at` timestamp is required.");
    }
    return {
        interactionId,
        source,
        kind,
        origin,
        at: raw.at,
        text: typeof raw.text === "string" ? raw.text : "",
        futureScope: raw.futureScope === true,
        ref: raw.ref && typeof raw.ref === "object" ? { ...raw.ref } : {},
    };
}
