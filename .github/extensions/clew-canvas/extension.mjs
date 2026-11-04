// Clew canvas: browse a prepared publication in a Copilot App canvas, capture the student's activity
// in the vault and bridge it to the tutor agent. Logic lives in lib/; this file only wires the SDK.
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { CanvasError, createCanvas, joinSession } from "@github/copilot-sdk/extension";
import { CanvasApp } from "./lib/app.mjs";
import { RequestError } from "./lib/reader.mjs";

const repoRoot = fileURLToPath(new URL("../../../", import.meta.url));
let app = null;
let session = null;
let resolveReady;
const ready = new Promise((done) => (resolveReady = done));

const log = (message, level = "info") => {
    Promise.resolve(session?.log(message, { level, ephemeral: level === "info" })).catch(() => {});
};

function guarded(handler) {
    return async (ctx) => {
        await ready;
        try {
            return await handler(ctx);
        } catch (error) {
            if (error instanceof CanvasError) throw error;
            const code = error instanceof RequestError ? (error.status === 503 ? "unavailable" : "invalid_input") : "clew_error";
            throw new CanvasError(code, error.message);
        }
    };
}

session = await joinSession({
    hooks: {
        onUserPromptSubmitted: async () => app?.onUserPromptSubmitted(),
        onPreToolUse: async (input) => app?.onPreToolUse(input),
    },
    canvases: [
        createCanvas({
            id: "clew-canvas",
            displayName: "Clew",
            description: "Interactive course and exercise reader for a prepared Clew publication layout; records the student's activity in the vault.",
            inputSchema: {
                type: "object",
                properties: {
                    layout: { type: "string", description: "Path of the publication layout JSON, normally <vault>/Activity/Layouts/<publication>.json." },
                },
                required: ["layout"],
            },
            actions: [
                {
                    name: "get_state",
                    description: "Read the student's progress: exercises, per-question hints revealed, corrections viewed, time, courses opened. " +
                        "Pass question (an address) for its statement and details, courses: true for the course list. Never reveals hints or answers.",
                    inputSchema: {
                        type: "object",
                        properties: { question: { type: "string" }, courses: { type: "boolean" } },
                    },
                    handler: guarded((ctx) => app.getState(ctx)),
                },
                {
                    name: "show",
                    description: "Scroll the student's canvas to a question, exercise or course address and highlight it. Does not reveal content.",
                    inputSchema: { type: "object", properties: { target: { type: "string" } }, required: ["target"] },
                    handler: guarded((ctx) => app.show(ctx)),
                },
            ],
            open: guarded((ctx) => app.open(ctx)),
            onClose: async (ctx) => {
                await ready;
                app.close(ctx);
            },
        }),
    ],
});

const stateDir = join(session.workspacePath ?? join(tmpdir(), "clew-canvas", session.sessionId), "clew-canvas");
app = await new CanvasApp({ repoRoot, sessionId: session.sessionId, stateDir, log }).start();
app.attach(session);
resolveReady();
