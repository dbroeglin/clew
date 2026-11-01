/** Run clew-generate in data mode from this repository's locked uv environment. */
import { execFile } from "node:child_process";
import { join } from "node:path";

export const SETUP_COMMAND = "uv sync --all-packages --locked";

export function compileArgs({ repoRoot, layout, target, base }) {
    return ["run", "--package", "clew-generate", "--locked", "--no-sync", "python", "-B",
        join(repoRoot, ".agents", "skills", "clew-generate", "scripts", "generate_html.py"),
        layout, "--data", target, "--base", base];
}

export function explainFailure(error, stderr = "") {
    if (error?.code === "ENOENT") return `uv was not found on PATH. Install uv, then run: ${SETUP_COMMAND}`;
    const text = String(stderr);
    const generate = /Generate error: ([\s\S]*)/.exec(text);
    if (generate) return generate[1].trim();
    if (/ModuleNotFoundError|No module named|Failed to spawn/.test(text)) {
        return `The clew-generate Python environment is missing in this checkout. Run: ${SETUP_COMMAND}`;
    }
    if (error?.killed) return "Compilation timed out.";
    const tail = text.trim().split(/\r?\n/).slice(-5).join("\n");
    return (tail || String(error?.message ?? error)).slice(0, 2000);
}

export function compileData(options, run = execFile) {
    return new Promise((done) => {
        run("uv", compileArgs(options), {
            cwd: options.repoRoot, maxBuffer: 32 * 1024 * 1024, windowsHide: true, timeout: 5 * 60_000,
            env: { ...process.env, PYTHONIOENCODING: "utf-8" },
        }, (error, stdout, stderr) => {
            if (error) return done({ ok: false, error: explainFailure(error, stderr) });
            try {
                done({ ok: true, report: JSON.parse(stdout) });
            } catch {
                done({ ok: false, error: `Unexpected compiler output: ${String(stdout).slice(0, 500)}` });
            }
        });
    });
}
