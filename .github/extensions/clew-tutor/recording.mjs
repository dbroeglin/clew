import path from "node:path";
import { CaptureError } from "./errors.mjs";

const OPERATIONS = {
    summary: "update_summary",
    session: "record_session",
    artifact: "save_artifact",
};

const RESULT_STATUSES = new Set(["recorded", "partial", "failed"]);
const MAX_REQUEST_EVENTS = 20;
const MAX_REQUEST_TEXT = 32 * 1024;

function mergedRef(events) {
    const result = {};
    for (const event of events) {
        for (const [key, value] of Object.entries(event.ref ?? {})) {
            if (value !== undefined && result[key] === undefined) result[key] = value;
        }
    }
    return result;
}

// Convert a correlated candidate into a semantic request for the tutor agent.
// The request describes intent and source context; it contains no Markdown patch,
// file writer, whole transcript, vault content, or inferred scores.
export function createRecordingRequest(candidate) {
    if (!candidate?.key || !candidate?.target || !OPERATIONS[candidate.target]) {
        throw new CaptureError("invalid_candidate", "A valid correlated capture candidate is required.");
    }
    const allEvents = candidate.events.map((event) => ({
        interactionId: event.interactionId,
        source: event.source,
        kind: event.kind,
        at: event.at,
        text: event.text,
    }));
    const selected = allEvents.length > 0 ? [allEvents[0]] : [];
    let textLength = selected[0]?.text.length ?? 0;
    for (let index = allEvents.length - 1; index > 0; index -= 1) {
        const event = allEvents[index];
        if (selected.length >= MAX_REQUEST_EVENTS || textLength + event.text.length > MAX_REQUEST_TEXT) continue;
        selected.push(event);
        textLength += event.text.length;
    }
    const events = selected.sort((left, right) => left.at.localeCompare(right.at));
    const selectedIds = new Set(events.map((event) => event.interactionId));
    const omittedInteractionCount = allEvents
        .filter((event) => !selectedIds.has(event.interactionId))
        .length;
    return {
        key: candidate.key,
        operation: OPERATIONS[candidate.target],
        target: candidate.target,
        category: candidate.category,
        occurredAt: allEvents.map((event) => event.at).sort()[0],
        sources: [...candidate.sources],
        sourceInteractionIds: events.map((event) => event.interactionId),
        ref: mergedRef(candidate.events),
        learnerInputs: events,
        omittedInteractionCount,
    };
}

export function createRecordingRequests(candidates) {
    return candidates.map(createRecordingRequest);
}

function normalizePaths(paths) {
    if (paths === undefined) return [];
    if (!Array.isArray(paths) || paths.some((value) => typeof value !== "string" || value.length === 0)) {
        throw new CaptureError("invalid_recording_result", "persistedPaths must be an array of non-empty strings.");
    }
    return [...new Set(paths.map((value) => {
        const normalized = value.replaceAll("\\", "/");
        const [root] = normalized.split("/");
        if (path.posix.isAbsolute(normalized) || normalized.split("/").includes("..")
            || !["model", "artifacts"].includes(root)) {
            throw new CaptureError(
                "invalid_recording_result",
                "persistedPaths must be vault-relative paths under model/ or artifacts/.",
            );
        }
        return normalized;
    }))];
}

// In-memory acknowledgement of what the tutor agent says happened after applying
// a request. This is honest reporting, not proof or durable exactly-once state.
export function createRecordingResultTracker() {
    const results = new Map();

    function report(requests, requestKey, raw = {}) {
        const request = requests.get(requestKey);
        if (!request) {
            throw new CaptureError("unknown_recording_request", `Unknown recording request: ${requestKey}`);
        }
        if (!RESULT_STATUSES.has(raw.status)) {
            throw new CaptureError("invalid_recording_result", "status must be recorded, partial or failed.");
        }
        const result = {
            requestKey,
            status: raw.status,
            persistedPaths: normalizePaths(raw.persistedPaths),
            error: typeof raw.error === "string" && raw.error.length > 0 ? raw.error : null,
            reportedAt: typeof raw.reportedAt === "string" ? raw.reportedAt : new Date().toISOString(),
        };
        if (result.status === "recorded" && result.persistedPaths.length === 0) {
            throw new CaptureError("invalid_recording_result", "A recorded result must identify at least one persisted path.");
        }
        if (result.status === "recorded") {
            const expected = request.target === "summary"
                ? (value) => value === "model/learner.md"
                : request.target === "session"
                    ? (value) => value.startsWith("model/sessions/")
                    : (value) => value.startsWith("artifacts/");
            if (!result.persistedPaths.some(expected)) {
                throw new CaptureError(
                    "invalid_recording_result",
                    `A recorded ${request.target} request must report its authoritative compact-memory target.`,
                );
            }
        }
        if (result.status !== "recorded" && !result.error) {
            throw new CaptureError("invalid_recording_result", "A partial or failed result must include an error.");
        }
        results.set(requestKey, result);
        return result;
    }

    return {
        report,
        get: (requestKey) => results.get(requestKey) ?? null,
        list: () => [...results.values()],
        clear: () => results.clear(),
    };
}
