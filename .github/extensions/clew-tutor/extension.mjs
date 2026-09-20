import { fileURLToPath } from "node:url";
import path from "node:path";
import { defineTool } from "@github/copilot-sdk";
import { createCanvas, joinSession } from "@github/copilot-sdk/extension";
import { isTutorAgent, rootSelectionFromEvent } from "./activation.mjs";
import { validateVaultBinding } from "./binding.mjs";
import { prepareDeletion, prepareMemoryChange, inspectMemory } from "./controls.mjs";
import { CaptureError } from "./errors.mjs";
import { createTutorIntegration } from "./integration.mjs";

const integration = createTutorIntegration();
let session;
const repositoryPath = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

const interactionKinds = [
    "goal", "preference", "takeaway", "attempt", "supplied_work",
    "correction", "stop_use", "hint_request", "proposal_response", "revision",
    "question", "recall", "continue", "inspect", "config", "status",
    "view_change", "agent_action",
];

const recordingResultSchema = {
    type: "object",
    additionalProperties: false,
    required: ["requestKey", "status"],
    properties: {
        requestKey: { type: "string", minLength: 1 },
        status: { type: "string", enum: ["recorded", "partial", "failed"] },
        persistedPaths: {
            type: "array",
            items: { type: "string", minLength: 1 },
            maxItems: 10,
        },
        error: { type: "string", minLength: 1, maxLength: 2000 },
    },
};

function json(value) {
    return JSON.stringify(value, null, 2);
}

async function syncSelection() {
    const current = await session.rpc.agent.getCurrent();
    return integration.setSelected(isTutorAgent(current.agent), { explicit: false });
}

function requireActiveBinding() {
    if (integration.capture.state !== "active" || !integration.capture.vault) {
        throw new CaptureError("inactive_episode", "An active, bound Clew Tutor episode is required.");
    }
    return integration.capture.vault;
}

async function status() {
    const base = integration.status();
    const preflight = await integration.capture.preflight();
    const resultByKey = new Map(base.results.map((result) => [result.requestKey, result]));
    return {
        ...base,
        requests: base.requests.map((request) => ({
            ...request,
            state: resultByKey.get(request.key)?.status
                ?? (preflight.allowCaptureWrites ? "pending" : "blocked"),
        })),
        preflight,
        completion: await integration.capture.completion(),
    };
}

async function bind(input) {
    await syncSelection();
    const vaultPath = await validateVaultBinding(input.vaultPath, repositoryPath);
    const activation = integration.bind({ ...input, vaultPath });
    return { activation, preflight: await integration.capture.preflight() };
}

async function gateRequest(result) {
    if (!result.request) return result;
    const preflight = await integration.capture.preflight();
    if (preflight.allowCaptureWrites) return { ...result, preflight };
    integration.prompts.markReported(result.request.key, "blocked");
    return {
        ...result,
        request: null,
        preflight,
        blocked: {
            requestKey: result.request.key,
            reason: preflight.reason,
        },
    };
}

function dispositionContext(promptId) {
    return [
        `Clew Tutor prompt ${promptId} is inside the explicitly selected tutor boundary.`,
        "If the episode is not bound yet, call clew_tutor_bind_session first.",
        "Before ending this turn, call clew_tutor_dispose_prompt exactly once for this prompt.",
        "Use a meaningful kind only for genuine learner goals, future-scoped preferences, takeaways, attempts, supplied work, corrections or stop-use decisions.",
        "Use a read-only kind for questions, recall, continuation, inspection, configuration, status or incidental chat.",
        "For a meaningful event, pass only the learner wording needed by compact memory; do not copy the whole conversation.",
        "After applying any returned recording request through the learner-model skill, call clew_tutor_report_recording.",
    ].join(" ");
}

const bindTool = defineTool("clew_tutor_bind_session", {
    description: "Bind and explicitly activate the selected Clew Tutor agent for one learner and configured external vault.",
    parameters: {
        type: "object",
        additionalProperties: false,
        required: ["learner", "vaultPath"],
        properties: {
            learner: { type: "string", minLength: 1 },
            vaultPath: { type: "string", minLength: 1 },
        },
    },
    handler: async (args) => {
        return json(await bind(args));
    },
});

const disposePromptTool = defineTool("clew_tutor_dispose_prompt", {
    description: "Classify one active learner prompt as meaningful or read-only and emit a semantic recording request when needed.",
    parameters: {
        type: "object",
        additionalProperties: false,
        required: ["promptId", "kind", "at"],
        properties: {
            promptId: { type: "string", minLength: 1 },
            interactionId: { type: "string", minLength: 1 },
            kind: { type: "string", enum: interactionKinds },
            at: { type: "string", format: "date-time" },
            text: { type: "string", maxLength: 8192 },
            futureScope: { type: "boolean" },
            ref: {
                type: "object",
                additionalProperties: false,
                properties: {
                    attemptId: { type: "string", minLength: 1 },
                    itemId: { type: "string", minLength: 1 },
                    proposalId: { type: "string", minLength: 1 },
                },
            },
        },
    },
    handler: async (args) => json(await gateRequest(integration.disposePrompt(args))),
});

const reportRecordingTool = defineTool("clew_tutor_report_recording", {
    description: "Report the best-effort result of applying a recording request through the learner-model skill.",
    parameters: recordingResultSchema,
    handler: async (args) => {
        const preflight = await integration.capture.preflight();
        if (!preflight.allowCaptureWrites) {
            throw new CaptureError("capture_blocked", preflight.reason);
        }
        return json(integration.reportRecording(args.requestKey, args));
    },
});

const episodeTool = defineTool("clew_tutor_episode", {
    description: "Pause, resume or end the active Clew Tutor capture episode.",
    parameters: {
        type: "object",
        additionalProperties: false,
        required: ["operation"],
        properties: {
            operation: { type: "string", enum: ["pause", "resume", "end"] },
        },
    },
    handler: ({ operation }) => {
        if (operation === "pause") return json(integration.pause());
        if (operation === "resume") return json(integration.resume());
        return json(integration.end());
    },
});

const statusTool = defineTool("clew_tutor_capture_status", {
    description: "Inspect active episode state, semantic recording requests, reported outcomes and best-effort completion.",
    parameters: { type: "object", additionalProperties: false },
    handler: async () => json(await status()),
});

const inspectTool = defineTool("clew_tutor_memory_inspect", {
    description: "Read one bounded compact-memory file from model/ or artifacts/ in the active vault.",
    parameters: {
        type: "object",
        additionalProperties: false,
        required: ["path"],
        properties: {
            path: { type: "string", minLength: 1 },
        },
    },
    handler: async ({ path }) => json(await inspectMemory(requireActiveBinding(), path)),
});

const prepareChangeTool = defineTool("clew_tutor_prepare_memory_change", {
    description: "Prepare an exact, non-destructive correction or stop-use replacement for the agent to apply through the learner-model skill.",
    parameters: {
        type: "object",
        additionalProperties: false,
        required: ["operation", "path", "expectedText", "replacementText"],
        properties: {
            operation: { type: "string", enum: ["correction", "stop_use"] },
            path: { type: "string", minLength: 1 },
            expectedText: { type: "string", minLength: 1, maxLength: 8192 },
            replacementText: { type: "string", minLength: 1, maxLength: 8192 },
        },
    },
    handler: async (args) => json(await prepareMemoryChange(requireActiveBinding(), args)),
});

const prepareDeletionTool = defineTool("clew_tutor_prepare_deletion", {
    description: "Resolve an exact compact-memory deletion scope and linked consequences without deleting anything.",
    parameters: {
        type: "object",
        additionalProperties: false,
        required: ["path"],
        properties: {
            path: { type: "string", minLength: 1 },
            passage: { type: "string", minLength: 1, maxLength: 8192 },
        },
    },
    handler: async (args) => json(await prepareDeletion(requireActiveBinding(), args)),
});

const practiceRef = {
    type: "object",
    additionalProperties: false,
    required: ["learnerOrigin", "interactionId", "attemptId", "itemId", "text"],
    properties: {
        learnerOrigin: { type: "boolean", const: true },
        interactionId: { type: "string", minLength: 1 },
        attemptId: { type: "string", minLength: 1 },
        itemId: { type: "string", minLength: 1 },
        proposalId: { type: "string", minLength: 1 },
        text: { type: "string", minLength: 1, maxLength: 8192 },
        at: { type: "string", format: "date-time" },
        futureScope: { type: "boolean" },
    },
};

const captureCanvas = createCanvas({
    id: "clew-tutor-capture",
    displayName: "Clew Tutor capture",
    description: "Headless, agent-callable learner-activity capture and completion tracking for one explicit tutor episode.",
    inputSchema: {
        type: "object",
        additionalProperties: false,
        required: ["learner", "vaultPath"],
        properties: {
            learner: { type: "string", minLength: 1 },
            vaultPath: { type: "string", minLength: 1 },
        },
    },
    open: async ({ input }) => {
        const { activation } = await bind(input);
        return {
            title: "Clew Tutor capture",
            status: activation.ok ? "Capture active; no visual practice UI is rendered." : activation.reason,
        };
    },
    actions: [
        {
            name: "submit_attempt",
            description: "Capture an explicitly attributed learner attempt.",
            inputSchema: practiceRef,
            handler: async ({ input }) => gateRequest(integration.recordCanvas("attempt", input)),
        },
        {
            name: "request_hint",
            description: "Capture an explicitly attributed learner request for help on an attempt.",
            inputSchema: practiceRef,
            handler: async ({ input }) => gateRequest(integration.recordCanvas("hint_request", input)),
        },
        {
            name: "respond_to_proposal",
            description: "Capture an explicitly attributed learner response to a proposed future preference.",
            inputSchema: practiceRef,
            handler: async ({ input }) => gateRequest(
                integration.recordCanvas("proposal_response", { ...input, futureScope: true }),
            ),
        },
        {
            name: "revise_attempt",
            description: "Capture an explicitly attributed learner revision of an existing attempt.",
            inputSchema: practiceRef,
            handler: async ({ input }) => gateRequest(integration.recordCanvas("revision", input)),
        },
        {
            name: "report_recording",
            description: "Report the result of an agent-applied learner-model edit.",
            inputSchema: recordingResultSchema,
            handler: async ({ input }) => {
                const preflight = await integration.capture.preflight();
                if (!preflight.allowCaptureWrites) {
                    throw new CaptureError("capture_blocked", preflight.reason);
                }
                return integration.reportRecording(input.requestKey, input);
            },
        },
        {
            name: "capture_status",
            description: "Return episode, preflight, request, result and completion state.",
            inputSchema: { type: "object", additionalProperties: false },
            handler: async () => status(),
        },
        {
            name: "pause_capture",
            description: "Pause capture while preserving the current in-memory episode.",
            inputSchema: { type: "object", additionalProperties: false },
            handler: () => integration.pause(),
        },
        {
            name: "resume_capture",
            description: "Resume a paused capture episode.",
            inputSchema: { type: "object", additionalProperties: false },
            handler: () => integration.resume(),
        },
        {
            name: "end_capture",
            description: "End capture and clear the in-memory episode state.",
            inputSchema: { type: "object", additionalProperties: false },
            handler: () => integration.end(),
        },
    ],
});

session = await joinSession({
    tools: [
        bindTool,
        disposePromptTool,
        reportRecordingTool,
        episodeTool,
        statusTool,
        inspectTool,
        prepareChangeTool,
        prepareDeletionTool,
    ],
    canvases: [captureCanvas],
    hooks: {
        onUserPromptSubmitted: async (input) => {
            try {
                await syncSelection();
            } catch (error) {
                integration.setSelected(false);
                await session.log(`Clew Tutor capture is inactive: could not verify agent selection (${error.message}).`, {
                    level: "warning",
                });
                return undefined;
            }
            const prompt = integration.beginPrompt(input.timestamp.toISOString());
            return prompt ? { additionalContext: dispositionContext(prompt.id) } : undefined;
        },
        onAgentStop: async () => {
            const reason = integration.capture.state === "active"
                ? integration.prompts.nextBlockReason()
                : null;
            return reason ? { decision: "block", reason } : undefined;
        },
        onSessionEnd: async () => {
            integration.end();
        },
    },
});

session.on("subagent.selected", (event) => {
    const selected = rootSelectionFromEvent(event);
    if (selected !== null) integration.setSelected(selected);
});
session.on("subagent.deselected", (event) => {
    if (event.agentId === undefined) integration.setSelected(false);
});
