import { readSessions, readSummary } from "./vault.mjs";

// Best-effort observation of whether each candidate appears recorded in the compact memory.
// It only reads memory; it never writes. Because the tutor agent's edits are not atomic and
// no durable backlog is kept, this cannot guarantee exactly-once recovery across a crash or
// reload - an unrecorded candidate is surfaced for the learner to complete, not auto-written.
export async function reconcile(vaultPath, candidates) {
    const summary = (await readSummary(vaultPath)) ?? "";
    const sessions = await readSessions(vaultPath);
    const recorded = [];
    const unrecorded = [];
    for (const candidate of candidates) {
        const seen = candidate.target === "summary"
            ? appearsInSummary(summary, candidate)
            : appearsInSessions(sessions, candidate);
        (seen ? recorded : unrecorded).push(candidate);
    }
    return { recorded, unrecorded };
}

function leadingWords(text, count = 6) {
    return text.toLowerCase().split(/\s+/).filter(Boolean).slice(0, count);
}

// A summary-targeted candidate counts as recorded when the summary contains the leading
// words of one of its learner statements. Detail and exact wording are not asserted.
function appearsInSummary(summary, candidate) {
    const haystack = summary.toLowerCase();
    return candidate.events.some((event) => {
        const words = leadingWords(event.text);
        return words.length > 0 && words.every((word) => haystack.includes(word));
    });
}

// A session-targeted candidate counts as recorded when a dated session note exists for the
// candidate's day. Topic and answer detail are left to the agent's note.
function appearsInSessions(sessions, candidate) {
    const days = new Set(candidate.events.map((event) => event.at.slice(0, 10)));
    return sessions.some((name) => [...days].some((day) => name.startsWith(day)));
}
