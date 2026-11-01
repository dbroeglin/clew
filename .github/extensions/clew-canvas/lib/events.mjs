/** Activity event vocabulary, validation and replay into progress. */
export const STUDENT_EVENTS = new Set([
    "exercise_started", "method_shown", "hint_revealed", "correction_shown", "correction_hidden",
    "explanation_opened", "course_opened",
]);
export const GAP_CAP_MS = 10 * 60_000;
const CLOCK_SKEW_MS = 60_000;
const MAX_CLIENT_AGE_MS = 7 * 24 * 3600_000;

/** Client timestamps are kept when plausible so queued offline events keep their order. */
export function eventTime(ts, now) {
    const current = now.getTime();
    const time = typeof ts === "string" ? Date.parse(ts) : NaN;
    if (Number.isFinite(time) && time <= current + CLOCK_SKEW_MS && time >= current - MAX_CLIENT_AGE_MS) {
        return new Date(Math.min(time, current)).toISOString();
    }
    return now.toISOString();
}

/** Attach validated question/exercise/course context fields to an event. */
export function withContext(event, input, index, { strict = true } = {}) {
    const fail = (message) => {
        if (strict) throw new Error(message);
    };
    if (input.exercise !== undefined) {
        if (index.exercises.has(input.exercise)) event.exercise = input.exercise;
        else fail(`Unknown exercise: ${input.exercise}`);
    }
    if (input.question !== undefined) {
        if (index.questions.has(input.question)) event.question = input.question;
        else fail(`Unknown question: ${input.question}`);
    }
    if (input.course !== undefined) {
        if (index.courses.has(input.course)) event.course = input.course;
        else fail(`Unknown course passage: ${input.course}`);
    }
    if (event.question && !event.exercise) {
        const exercise = index.exerciseOf.get(event.question);
        if (exercise) event.exercise = exercise.address;
    }
    return event;
}

export function studentEvent(input, index, now) {
    if (!input || typeof input !== "object") throw new Error("Event must be an object.");
    const { type } = input;
    if (!STUDENT_EVENTS.has(type)) throw new Error(`Unsupported event type: ${type}`);
    const event = withContext({ v: 1, ts: eventTime(input.ts, now), type, actor: "student" }, input, index);
    const needs = { exercise_started: "exercise", course_opened: "course" }[type] ?? "question";
    if (!event[needs]) throw new Error(`${type} requires ${needs}.`);
    if (type === "hint_revealed") {
        const total = index.questions.get(event.question).hints.length;
        if (!Number.isInteger(input.index) || input.index < 1 || input.index > total) {
            throw new Error(`Invalid hint index for ${event.question}.`);
        }
        Object.assign(event, { index: input.index, total });
    }
    return event;
}

function emptyQuestion() {
    return { hints: 0, total: 0, correction: false, correctionSeen: false, method: 0, explanations: 0,
             tutor: 0, ms: 0 };
}

/**
 * Derive progress from events. Time is approximated from gaps between student
 * events: each gap (capped) goes to the question, or else the exercise, of the
 * earlier event. Opening or closing the canvas breaks the chain.
 */
export function replay(events) {
    const questions = new Map();
    const exercises = new Map();
    const courses = new Map();
    const links = [];
    let focus = null;
    let previous = null;
    let first = null;
    let last = null;
    let tutorShows = 0;
    const question = (address) => {
        if (!questions.has(address)) questions.set(address, emptyQuestion());
        return questions.get(address);
    };
    const exercise = (address) => {
        if (!exercises.has(address)) exercises.set(address, { started: false, ms: 0 });
        return exercises.get(address);
    };
    for (const event of events) {
        const time = Date.parse(event.ts);
        if (!Number.isFinite(time)) continue;
        first ??= event.ts;
        last = event.ts;
        if (event.type === "canvas_opened" || event.type === "canvas_rehydrated") {
            previous = null;
            continue;
        }
        const student = event.actor === "student";
        if (previous && (student || event.type === "canvas_closed")) {
            const gap = Math.min(Math.max(time - previous.time, 0), GAP_CAP_MS);
            if (previous.question) question(previous.question).ms += gap;
            else exercise(previous.exercise).ms += gap;
        }
        if (event.type === "canvas_closed") {
            previous = null;
            continue;
        }
        if (event.exercise && student) exercise(event.exercise);
        switch (event.type) {
            case "exercise_started": exercise(event.exercise).started = true; break;
            case "method_shown": question(event.question).method += 1; break;
            case "hint_revealed": {
                const state = question(event.question);
                state.hints = Math.max(state.hints, event.index);
                state.total = event.total;
                break;
            }
            case "correction_shown": Object.assign(question(event.question), { correction: true, correctionSeen: true }); break;
            case "correction_hidden": question(event.question).correction = false; break;
            case "explanation_opened": question(event.question).explanations += 1; break;
            case "course_opened": courses.set(event.course, (courses.get(event.course) ?? 0) + 1); break;
            case "link_opened":
            case "pdf_opened": links.push(event); break;
            case "tutor_requested": question(event.question).tutor += 1; break;
            case "tutor_show": tutorShows += 1; break;
            default: break;
        }
        if (student) {
            previous = event.question || event.exercise
                ? { time, question: event.question, exercise: event.exercise } : null;
            if (event.question || event.exercise || event.course) {
                focus = { ts: event.ts, exercise: event.exercise, question: event.question, course: event.course };
            }
        }
    }
    return { questions, exercises, courses, links, focus, first, last, tutorShows };
}

export function minutes(ms) {
    if (!ms) return "—";
    return ms < 60_000 ? "<1 min" : `~${Math.round(ms / 60_000)} min`;
}
