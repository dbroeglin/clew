/** Deterministic `summary.md` for an Activity folder: no clock, no model, only events and data. */
import { splitAddress } from "./data.mjs";
import { minutes, replay } from "./events.mjs";

const label = (text) => String(text).replace(/[[\]|\r\n]+/g, " ").replace(/\s+/g, " ").trim();

export function renderSummary({ header, events, index }) {
    const progress = replay(events);
    const { data } = index;
    const target = (address) => {
        const [id, fragment] = splitAddress(address);
        const source = index.sources.get(id);
        return source ? source.path.replace(/\.md$/i, "") + (fragment ? `#${fragment}` : "") : null;
    };
    const link = (address, text, table = false) => {
        const path = target(address);
        return path ? `[[${path}${table ? "\\|" : "|"}${label(text)}]]` : `${label(text)} (${address})`;
    };
    const questionStates = [...progress.questions.values()];
    let total = 0;
    const body = [];
    for (const exercise of data.exercises) {
        const questions = exercise.questions.map((id) => index.questionsById.get(id)).filter(Boolean);
        const state = progress.exercises.get(exercise.address);
        if (!state && !questions.some((q) => progress.questions.has(q.address))) continue;
        const ms = (state?.ms ?? 0) + questions.reduce((sum, q) => sum + (progress.questions.get(q.address)?.ms ?? 0), 0);
        total += ms;
        body.push(`### ${link(exercise.address, exercise.title)} · ${minutes(ms)}`, "",
            "| Question | Indices | Correction | Tuteur | Temps |", "| --- | --- | --- | --- | --- |");
        for (const question of questions) {
            const s = progress.questions.get(question.address);
            const hints = question.hints.length ? `${s?.hints ?? 0}/${question.hints.length}` : "—";
            body.push(`| ${link(question.address, question.label, true)} | ${hints} | ${s?.correctionSeen ? "vue" : "—"} | ${s?.tutor || "—"} | ${minutes(s?.ms ?? 0)} |`);
        }
        body.push("");
    }
    const lines = [
        "---",
        "type: clew-activity",
        `publication: ${JSON.stringify(header.title)}`,
        `layout: ${JSON.stringify(header.layout)}`,
        `session: ${JSON.stringify(header.session)}`,
        `started: ${JSON.stringify(progress.first ?? header.ts)}`,
        `updated: ${JSON.stringify(progress.last ?? header.ts)}`,
        "---",
        "",
        `# Activité · ${label(header.title)}`,
        "",
        "Résumé généré par le canevas Clew à partir de `activity.jsonl` et réécrit à chaque action. " +
            "Les durées sont estimées à partir des écarts entre actions, plafonnés à 10 min.",
        "",
        `Questions travaillées : ${questionStates.length} · indices révélés : ${questionStates.reduce((n, s) => n + s.hints, 0)}` +
            ` · corrections vues : ${questionStates.filter((s) => s.correctionSeen).length}` +
            ` · demandes au tuteur : ${questionStates.reduce((n, s) => n + s.tutor, 0)}` +
            ` · passages montrés par le tuteur : ${progress.tutorShows} · temps estimé : ${minutes(total)}`,
        "",
        "## Exercices",
        "",
        ...(body.length ? body : ["_Aucun exercice commencé._", ""]),
        "## Cours consultés",
        "",
    ];
    if (!progress.courses.size) lines.push("_Aucun passage de cours ouvert._");
    for (const [address, count] of progress.courses) {
        lines.push(`- ${link(address, index.courses.get(address)?.title ?? address)} · ${count} fois`);
    }
    lines.push("", "## Liens et PDF ouverts", "");
    const opened = new Map();
    for (const event of progress.links) {
        const key = `${event.type} ${event.url} ${event.page ?? ""}`;
        opened.set(key, { event, count: (opened.get(key)?.count ?? 0) + 1 });
    }
    if (!opened.size) lines.push("_Aucun lien ouvert._");
    for (const { event, count } of opened.values()) {
        const times = count > 1 ? ` · ${count} fois` : "";
        if (event.type === "pdf_opened" && !event.url.startsWith("file:")) {
            const name = label(event.url.split("/").pop());
            const page = event.page ? `#page=${event.page}` : "";
            lines.push(`- PDF [[${event.url}${page}|${name}${event.page ? ` p. ${event.page}` : ""}]]${times}`);
        } else {
            lines.push(`- <${event.url}>${times}`);
        }
    }
    lines.push("", "## Notes de la publication", "");
    const sources = data.sources ?? [];
    for (const source of sources.filter((s) => s.type !== "help")) {
        lines.push(`- [[${source.path.replace(/\.md$/i, "")}|${label(source.title || source.id)}]]${source.role ? ` · ${source.role}` : ""}`);
    }
    const help = sources.filter((s) => s.type === "help").length;
    if (help) lines.push(`- ${help} notes d'aide`);
    return `${lines.join("\n")}\n`;
}
