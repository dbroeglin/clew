import { readFileSync } from "node:fs";
import { join } from "node:path";

export function loadUi(repoRoot) {
    const path = join(repoRoot, ".agents", "skills", "clew-generate", "assets", "locales", "en.json");
    const ui = JSON.parse(readFileSync(path, "utf8"));
    if (ui.locale !== "en" || !ui.messages || typeof ui.messages !== "object") {
        throw new Error(`Invalid Clew UI catalog: ${path}`);
    }
    return ui;
}

export function uiText(ui, key, values = {}) {
    const template = key === "locale" ? ui?.locale : ui?.messages?.[key];
    if (typeof template !== "string") throw new Error(`Missing Clew UI message: ${key}`);
    return template.replace(/\{([A-Za-z][A-Za-z0-9_]*)\}/g, (_, name) => {
        if (!Object.prototype.hasOwnProperty.call(values, name)) {
            throw new Error(`Missing value "${name}" for Clew UI message: ${key}`);
        }
        return String(values[name]);
    });
}

export function renderUiTemplate(template, ui) {
    const rendered = template.replace(/\{\{UI:([a-z0-9_.]+)\}\}/g, (_, key) => {
        const value = uiText(ui, key);
        return value.replace(/[&<>"']/g, (character) => ({
            "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
        })[character]);
    });
    if (/\{\{UI:[^}]+\}\}/.test(rendered)) throw new Error("Unresolved Clew UI template placeholder.");
    const encoded = JSON.stringify(ui).replace(/</g, "\\u003c").replace(/>/g, "\\u003e")
        .replace(/&/g, "\\u0026").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
    if (!rendered.includes("{{UI_DATA}}")) throw new Error("Missing Clew UI data hook.");
    return rendered.replace("{{UI_DATA}}", encoded);
}
