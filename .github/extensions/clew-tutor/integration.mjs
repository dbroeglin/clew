import { createCaptureLayer } from "./capture.mjs";
import { createPromptTracker } from "./chat.mjs";
import { CaptureError } from "./errors.mjs";

function requestFor(capture, classification) {
    if (!classification.write) return null;
    return capture.requests().find((request) =>
        request.sourceInteractionIds.includes(classification.event.interactionId)
    ) ?? null;
}

export function createTutorIntegration({ promptLimit = 20 } = {}) {
    const capture = createCaptureLayer();
    const prompts = createPromptTracker({ limit: promptLimit });
    let selected = false;
    let activationArmed = false;

    function setSelected(nextSelected, { explicit = true } = {}) {
        selected = nextSelected === true;
        if (!selected) {
            activationArmed = false;
            if (capture.state === "active") return capture.pause();
            return { ok: true, state: capture.state };
        }
        if (capture.state === "paused") {
            activationArmed = false;
            return capture.resume();
        }
        if (explicit && capture.state === "inactive") activationArmed = true;
        return { ok: true, state: capture.state };
    }

    function bind({ learner, vaultPath }) {
        if (!selected) {
            throw new CaptureError("tutor_not_selected", "Select the Clew Tutor agent before binding a learner.");
        }
        if (capture.state !== "inactive") {
            if (capture.learner !== learner || capture.vault !== vaultPath) {
                throw new CaptureError(
                    "episode_already_bound",
                    "End the current episode before binding a different learner or vault.",
                );
            }
            return { ok: true, state: capture.state, learner: capture.learner, vault: capture.vault };
        }
        if (!activationArmed) {
            throw new CaptureError(
                "explicit_activation_required",
                "Reselect Clew Tutor after a reload or ended episode before binding.",
            );
        }
        const activated = capture.activate({ learner, vault: vaultPath, activation: "explicit-human" });
        if (activated.ok) activationArmed = false;
        return activated;
    }

    function beginPrompt(at = new Date().toISOString()) {
        if (!selected || capture.state === "paused") return null;
        if (capture.state !== "active" && !activationArmed) return null;
        return prompts.begin(at);
    }

    function disposePrompt(input) {
        if (capture.state !== "active") {
            throw new CaptureError("inactive_episode", "Prompt disposition requires an active tutor episode.");
        }
        prompts.requirePending(input.promptId);
        const result = capture.admit({
            interactionId: input.interactionId ?? input.promptId,
            source: "chat",
            kind: input.kind,
            origin: "learner",
            at: input.at,
            text: input.text ?? "",
            futureScope: input.futureScope,
            ref: input.ref,
        });
        const request = requestFor(capture, result.classification);
        prompts.resolve(input.promptId, { ...result, request });
        return { ...result, request };
    }

    function recordCanvas(kind, input) {
        if (input.learnerOrigin !== true) {
            throw new CaptureError(
                "unverified_learner_origin",
                "Canvas capture requires learnerOrigin:true and a source interaction identifier.",
            );
        }
        const result = capture.admit({
            interactionId: input.interactionId,
            source: "canvas",
            kind,
            origin: "learner",
            at: input.at ?? new Date().toISOString(),
            text: input.text ?? "",
            futureScope: input.futureScope,
            ref: {
                attemptId: input.attemptId,
                itemId: input.itemId,
                proposalId: input.proposalId,
            },
        });
        return { ...result, request: requestFor(capture, result.classification) };
    }

    function reportRecording(requestKey, result) {
        const reported = capture.reportRecording(requestKey, result);
        prompts.markReported(requestKey, reported.status);
        return reported;
    }

    function end() {
        prompts.clear();
        activationArmed = false;
        return capture.end();
    }

    function resume() {
        if (!selected) {
            throw new CaptureError("tutor_not_selected", "Select the Clew Tutor agent before resuming capture.");
        }
        return capture.resume();
    }

    return {
        get selected() { return selected; },
        get activationArmed() { return activationArmed; },
        capture,
        prompts,
        setSelected,
        bind,
        beginPrompt,
        disposePrompt,
        recordCanvas,
        reportRecording,
        pause: () => capture.pause(),
        resume,
        end,
        status: () => ({
            selected,
            activationArmed,
            state: capture.state,
            learner: capture.learner,
            vault: capture.vault,
            prompts: prompts.list(),
            requests: capture.requests(),
            results: capture.recordingResults(),
        }),
    };
}
