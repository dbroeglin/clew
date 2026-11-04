/** Lookup tables over the compiled publication data written by `generate_html.py --data`. */
export function indexData(data) {
    const questionsById = new Map(data.questions.map((q) => [q.id, q]));
    const questions = new Map(data.questions.map((q) => [q.address, q]));
    const exercises = new Map();
    const exerciseOf = new Map();
    for (const exercise of data.exercises) {
        exercises.set(exercise.address, exercise);
        for (const id of exercise.questions) {
            const question = questionsById.get(id);
            if (question) exerciseOf.set(question.address, exercise);
        }
    }
    const coursesById = new Map(data.courses.map((c) => [c.id, c]));
    const courses = new Map();
    for (const course of data.courses) {
        if (course.address && !courses.has(course.address)) courses.set(course.address, course);
    }
    const sources = new Map((data.sources ?? []).map((s) => [s.id, s]));
    return { data, questions, questionsById, exercises, exerciseOf, courses, coursesById, sources };
}

export function splitAddress(address) {
    const at = address.indexOf("#");
    return at < 0 ? [address, ""] : [address.slice(0, at), address.slice(at + 1)];
}

const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: "\"", apos: "'", nbsp: " " };

/** Plain text for the agent: tags removed, TeX delimiters kept. */
export function htmlToText(html, limit = 4000) {
    const text = String(html)
        .replace(/<span class="anchor"[^>]*><\/span>/g, "")
        .replace(/<(br|\/p|\/li|\/h\d|\/tr|\/div|\/blockquote)\b[^>]*>/gi, "\n")
        .replace(/<[^>]+>/g, "")
        .replace(/&(#\d+|#x[0-9a-f]+|[a-z]+);/gi, (match, entity) => {
            if (entity[0] !== "#") return ENTITIES[entity.toLowerCase()] ?? match;
            const code = entity[1].toLowerCase() === "x" ? parseInt(entity.slice(2), 16) : parseInt(entity.slice(1), 10);
            return Number.isFinite(code) ? String.fromCodePoint(code) : match;
        })
        .replace(/[ \t]+/g, " ")
        .replace(/ *\n[ \n]*/g, "\n")
        .trim();
    return text.length > limit ? `${text.slice(0, limit)}…` : text;
}
