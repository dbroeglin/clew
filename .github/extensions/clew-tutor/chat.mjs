import { CaptureError } from "./errors.mjs";

// Bounded, in-memory prompt disposition tracking. It retains no prompt text and
// deliberately does not survive reload: the accepted design has no durable inbox.
export function createPromptTracker({ limit = 20 } = {}) {
    let sequence = 0;
    const prompts = new Map();

    function begin(at) {
        sequence += 1;
        const id = `prompt-${Date.parse(at) || Date.now()}-${sequence}`;
        prompts.set(id, { id, at, state: "pending", blockIssued: false });
        while (prompts.size > limit) {
            const oldest = prompts.keys().next().value;
            prompts.delete(oldest);
        }
        return prompts.get(id);
    }

    function resolve(id, result) {
        const prompt = prompts.get(id);
        if (!prompt) throw new CaptureError("unknown_prompt", `Unknown or expired prompt: ${id}`);
        if (prompt.state !== "pending") {
            throw new CaptureError("prompt_already_disposed", `Prompt ${id} is already ${prompt.state}.`);
        }
        prompt.state = result.classification.write ? "pending_recording" : "read_only";
        prompt.reason = result.classification.reason;
        prompt.requestKey = result.request?.key ?? null;
        return { ...prompt };
    }

    function markReported(requestKey, status) {
        for (const prompt of prompts.values()) {
            if (prompt.requestKey === requestKey) prompt.state = status;
        }
    }

    function unresolved() {
        return [...prompts.values()].filter((prompt) => prompt.state === "pending");
    }

    function nextBlockReason() {
        const prompt = unresolved().find((candidate) => !candidate.blockIssued);
        if (!prompt) return null;
        prompt.blockIssued = true;
        return `Classify the active learner prompt ${prompt.id} with clew_tutor_dispose_prompt before ending the turn.`;
    }

    return {
        begin,
        requirePending: (id) => {
            const prompt = prompts.get(id);
            if (!prompt) throw new CaptureError("unknown_prompt", `Unknown or expired prompt: ${id}`);
            if (prompt.state !== "pending") {
                throw new CaptureError("prompt_already_disposed", `Prompt ${id} is already ${prompt.state}.`);
            }
            return { ...prompt };
        },
        resolve,
        markReported,
        unresolved,
        list: () => [...prompts.values()].map((prompt) => ({ ...prompt })),
        nextBlockReason,
        clear: () => prompts.clear(),
    };
}
