/** Text the extension adds to the Copilot session: activity digests and tutor requests. */
import { htmlToText } from "./data.mjs";
import { minutes } from "./events.mjs";

const clock = (ts) => `${ts.slice(11, 19)}Z`;

export function describe(event, index) {
    const question = event.question ? index?.questions.get(event.question) : null;
    const exercise = event.exercise ? index?.exercises.get(event.exercise) : null;
    const course = event.course ? index?.courses.get(event.course) : null;
    const q = event.question ? `${question?.label ?? "a question"}${exercise ? ` of ${exercise.title}` : ""} [${event.question}]` : "";
    const e = event.exercise ? `${exercise?.title ?? "an exercise"} [${event.exercise}]` : "";
    const c = event.course ? `course passage "${course?.title ?? event.course}" [${event.course}]` : "";
    switch (event.type) {
        case "canvas_opened": return "Student opened the canvas.";
        case "canvas_rehydrated": return "Student reconnected to the canvas.";
        case "canvas_closed": return "The canvas was closed.";
        case "content_changed": {
            const notes = [...(event.notes ?? []).map((n) => n.id), ...(event.removed ?? [])];
            return `Course notes changed (${notes.join(", ") || "layout"}); the canvas reloaded them.`;
        }
        case "exercise_started": return `Student started ${e}.`;
        case "method_shown": return `Student opened the method for ${q}.`;
        case "hint_revealed": return `Student revealed hint ${event.index}/${event.total} for ${q}.`;
        case "correction_shown": return `Student showed the supplied correction for ${q}.`;
        case "correction_hidden": return `Student hid the supplied correction for ${q}.`;
        case "explanation_opened": return `Student opened the explanations for ${q}.`;
        case "course_opened": return `Student opened ${c}${q ? ` from ${q}` : ""}.`;
        case "link_opened": return `Student opened the link ${event.url}${q ? ` from ${q}` : ""}.`;
        case "pdf_opened": return `Student opened the PDF ${event.url}${event.page ? ` at page ${event.page}` : ""}${q ? ` from ${q}` : ""}.`;
        case "tutor_requested": return `Student asked the tutor for help with ${q}.`;
        case "tutor_show": return `Tutor showed ${q || e || c}.`;
        default: return `${event.type}.`;
    }
}

/** Compact digest of events the agent has not seen yet, or null when there are none. */
export function digestText({ title, instances, events, index, limit = 30 }) {
    const relevant = events.filter((event) => event.type !== "tutor_show");
    if (!relevant.length) return null;
    const shown = relevant.slice(-limit);
    const canvas = instances.length ? instances.map((id) => `"${id}"`).join(", ") : "closed";
    const lines = [`Clew canvas activity since the previous message (publication "${title}", canvas instance ${canvas}):`];
    if (relevant.length > shown.length) lines.push(`- (${relevant.length - shown.length} earlier events omitted)`);
    for (const event of shown) lines.push(`- ${clock(event.ts)} ${describe(event, index)}`);
    lines.push("Use invoke_canvas_action get_state for full progress.");
    return lines.join("\n");
}

export function askPrompt({ title, instance, question, exercise, state, recent }) {
    const s = state ?? {};
    const method = s.method ? "viewed" : question.method ? "not viewed" : "not available";
    return [
        `[Clew canvas] The student pressed "Ask the tutor" on ${question.label}${exercise ? ` of ${exercise.title}` : ""} ` +
            `[${question.address}] in publication "${title}" (canvas instance "${instance}").`,
        `Progress on this question: hints revealed ${s.hints ?? 0}/${question.hints.length}; ` +
            `supplied correction ${s.correctionSeen ? "viewed" : "not viewed"}; method ${method}; ` +
            `explanations opened ${s.explanations ?? 0} times; approximate time on question ${minutes(s.ms ?? 0)}; ` +
            `tutor requests ${s.tutor ?? 1} including this one.`,
        "Question statement (HTML removed, TeX kept):",
        htmlToText(question.html, 3000),
        recent ?? "",
        "Respond as the Clew tutor: do not give the answer, a hint's content or the correction; ask one guiding " +
            "question, in French; you may point to a course passage with invoke_canvas_action show.",
    ].filter(Boolean).join("\n");
}
