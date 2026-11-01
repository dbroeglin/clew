/** Durable learning record in the vault: `Activity/<date>-<publication>-<session8>/`. */
import { appendFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { localDate, slugify, vaultPath, writeAtomic } from "./paths.mjs";

export function readJsonl(path) {
    const records = [];
    if (!existsSync(path)) return records;
    for (const line of readFileSync(path, "utf8").split(/\r\n|\n|\r/)) {
        if (!line.trim()) continue;
        try {
            const record = JSON.parse(line);
            if (record && typeof record === "object" && typeof record.type === "string") records.push(record);
        } catch {
            // A torn final line from an interrupted write is skipped, not fatal.
        }
    }
    return records;
}

export class ActivityStore {
    constructor({ vault, layout, session, now = () => new Date() }) {
        this.vault = vault;
        this.layout = layout;
        this.layoutRel = vaultPath(vault, layout);
        this.session = session;
        this.now = now;
        this.root = join(vault, "Activity");
        this.folder = null;
    }

    get journal() { return join(this.folder, "activity.jsonl"); }
    get summaryPath() { return join(this.folder, "summary.md"); }
    get internal() { return join(this.folder, ".clew-activity"); }

    /** Existing folder of this session for this layout, whatever its date or title. */
    locate() {
        const suffix = `-${this.session.slice(0, 8)}`;
        let entries = [];
        try {
            entries = readdirSync(this.root, { withFileTypes: true });
        } catch {
            return null;
        }
        for (const entry of entries) {
            if (!entry.isDirectory() || !entry.name.endsWith(suffix)) continue;
            const header = readJsonl(join(this.root, entry.name, "activity.jsonl"))[0];
            if (header?.type === "header" && header.session === this.session && header.layout === this.layoutRel) {
                return join(this.root, entry.name);
            }
        }
        return null;
    }

    /** Open or create the folder; returns the header and the recorded events. */
    open(data) {
        this.folder = this.locate();
        if (!this.folder) {
            const base = `${localDate(this.now())}-${slugify(data.title)}-${this.session.slice(0, 8)}`;
            let name = base;
            for (let n = 2; existsSync(join(this.root, name)); n += 1) name = `${base}-${n}`;
            this.folder = join(this.root, name);
            mkdirSync(this.internal, { recursive: true });
            const header = {
                v: 1, type: "header", ts: this.now().toISOString(), session: this.session, title: data.title,
                layout: this.layoutRel,
                notes: (data.sources ?? []).map(({ id, path, sha256 }) => ({ id, path, sha256 })),
            };
            writeFileSync(this.journal, `${JSON.stringify(header)}\n`, { flag: "wx" });
        }
        mkdirSync(this.internal, { recursive: true });
        return this.load();
    }

    load() {
        const text = existsSync(this.journal) ? readFileSync(this.journal, "utf8") : "";
        if (text && !/[\r\n]$/.test(text)) appendFileSync(this.journal, "\n");
        const records = readJsonl(this.journal);
        const header = records[0]?.type === "header" ? records[0] : null;
        if (!header) throw new Error(`Activity journal has no header: ${this.journal}`);
        return { header, events: records.slice(1).filter((r) => r.type !== "header" && typeof r.ts === "string") };
    }

    append(event) {
        appendFileSync(this.journal, `${JSON.stringify(event)}\n`);
    }

    /** Copy the layout used for this session; returns whether an earlier snapshot differed. */
    snapshotLayout(text) {
        const path = join(this.internal, "layout.json");
        const previous = existsSync(path) ? readFileSync(path, "utf8") : null;
        if (previous === text) return false;
        writeAtomic(path, text);
        return previous !== null;
    }

    readState() {
        try {
            return JSON.parse(readFileSync(join(this.internal, "state.json"), "utf8"));
        } catch {
            return {};
        }
    }

    writeState(state) {
        writeAtomic(join(this.internal, "state.json"), `${JSON.stringify(state, null, 2)}\n`);
    }

    writeSummary(text) {
        if (existsSync(this.summaryPath) && readFileSync(this.summaryPath, "utf8") === text) return false;
        writeAtomic(this.summaryPath, text);
        return true;
    }
}
