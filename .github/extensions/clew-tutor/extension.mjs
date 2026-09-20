import { CanvasError, createCanvas, joinSession } from "@github/copilot-sdk/extension";
import { createCaptureLayer } from "./capture.mjs";
import { CaptureError } from "./errors.mjs";

// Selecting the Clew Tutor agent as the root conversation agent is the explicit activation
// boundary (ADR-0005 DEC-001). A delegated subagent selection is not consent to capture the
// parent conversation, so activation follows the root selection only.
const TUTOR_AGENT_ID = "clew-tutor";

const string = { type: "string", minLength: 1, maxLength: 4096 };
const schema = (properties, required = []) => ({ type: "object", properties, required, additionalProperties: false });

const capture = createCaptureLayer();
let session;
let binding = { learner: null, vault: null };

async function invoke(operation) {
    try {
        return await operation();
    } catch (error) {
        if (error instanceof CaptureError) throw new CanvasError(error.code, error.message);
        console.error(error);
        throw new CanvasError("capture_error", "The Clew Tutor capture layer failed. Inspect the extension log for details.");
    }
}

// Keep episode activation aligned with the selected root agent, never process lifetime.
// SPIKE: the surface used here (`session.rpc.agent.getCurrent`, `isRoot`, and the
// `subagent.selected`/`subagent.deselected` events below) is asserted in ADR-0005 IMP-002
// and must be validated against the live App before this is relied on.
async function syncActivation() {
    const current = await session.rpc.agent?.getCurrent?.();
    const tutorIsRoot = current?.id === TUTOR_AGENT_ID && current?.isRoot === true;
    if (tutorIsRoot && capture.state === "inactive" && binding.learner && binding.vault) {
        capture.activate({ ...binding, activation: "explicit-human" });
    } else if (!tutorIsRoot && capture.state === "active") {
        capture.pause();
    }
}

function summarize(candidate) {
    return { key: candidate.key, category: candidate.category, target: candidate.target, sources: candidate.sources };
}

function describeCompletion(completion) {
    return {
        recorded: completion.recorded.map((candidate) => candidate.key),
        unrecorded: completion.unrecorded.map((candidate) => candidate.key),
    };
}

// Agent-facing status and completion surface. The tutor logs candidate learner activity it
// recognizes and asks what remains unrecorded; it never writes memory through this layer.
const canvas = createCanvas({
    id: "clew-tutor-capture",
    displayName: "Clew Tutor capture",
    description: "Track an explicit Clew learning session: activation status, correlated candidate activity and what is not yet recorded. It records nothing itself.",
    inputSchema: schema({
        vaultPath: { ...string, description: "Absolute path of the current vault; supplied explicitly, never auto-discovered." },
        learner: { ...string, description: "Identifier of the learner whose compact memory this session may update." },
    }, ["vaultPath", "learner"]),
    actions: [
        {
            name: "capture_status",
            description: "Report episode state, the ownership/migration preflight, correlated candidate activity and what is not yet recorded.",
            inputSchema: schema({}),
            handler: () => invoke(async () => ({
                state: capture.state,
                preflight: await capture.preflight(),
                candidates: capture.candidates().map(summarize),
                completion: describeCompletion(await capture.completion()),
            })),
        },
        {
            name: "record_learner_activity",
            description: "Log a candidate learner statement, decision or result observed in chat so completion can be tracked. Returns whether it is a meaningful write and where it belongs; it does not write memory.",
            inputSchema: schema({
                interactionId: string,
                kind: { ...string, description: "goal, preference, takeaway, attempt, supplied_work, correction, stop_use, hint_request, proposal_response or revision." },
                origin: { ...string, description: "learner for the learner's own input; assistant, agent, system or injection otherwise." },
                at: { ...string, description: "ISO-8601 timestamp of the interaction." },
                text: { type: "string", maxLength: 8192, description: "The learner's own words, when applicable." },
                futureScope: { type: "boolean", description: "For a preference, whether the learner stated an explicit future scope." },
            }, ["interactionId", "kind", "origin", "at"]),
            handler: (ctx) => invoke(async () => {
                const result = capture.admit({ source: "chat", ...(ctx.input ?? {}) });
                return {
                    admitted: result.admitted,
                    state: result.state,
                    write: result.classification.write,
                    target: result.classification.target,
                    category: result.classification.category,
                    reason: result.classification.reason,
                };
            }),
        },
    ],
    open: (ctx) => invoke(async () => {
        binding = { learner: ctx.input.learner, vault: ctx.input.vaultPath };
        await syncActivation();
        return { title: "Clew Tutor capture", status: capture.state };
    }),
    // Closing the status canvas does not end the episode; the root agent selection governs that.
    onClose: () => invoke(async () => {}),
});

session = await joinSession({ canvases: [canvas] });

// SPIKE: the event subscription mechanism is assumed; validate it against the live App.
session.on?.("subagent.selected", () => { syncActivation().catch((error) => console.error(error)); });
session.on?.("subagent.deselected", () => { syncActivation().catch((error) => console.error(error)); });

let closing = false;
function shutdown() {
    if (closing) return;
    closing = true;
    process.exit(0);
}
process.once("SIGTERM", shutdown);
process.once("SIGINT", shutdown);
process.once("disconnect", shutdown);
