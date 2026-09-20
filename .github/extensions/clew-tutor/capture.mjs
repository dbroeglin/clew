import { correlate } from "./correlation.mjs";
import { reconcile } from "./completion.mjs";
import { createEpisode } from "./episode.mjs";
import { classify } from "./gating.mjs";
import { preflight } from "./vault.mjs";

// The App capture layer. It orchestrates activation, gates and correlates learner activity,
// and observes whether memory was recorded. It never writes learner memory itself: the tutor
// agent performs any meaning-gated edit through the installed learner-model skill.
export function createCaptureLayer() {
    const episode = createEpisode();
    const admitted = [];

    function admit(rawEvent) {
        const classification = classify(rawEvent);
        if (!episode.admits()) {
            return { admitted: false, state: episode.state, classification, reason: "episode is not active" };
        }
        if (classification.write) admitted.push(classification);
        return { admitted: classification.write, state: episode.state, classification };
    }

    function candidates() {
        return correlate(admitted);
    }

    // The ownership/migration gate for the bound vault; capture writes wait on it.
    async function checkPreflight() {
        if (!episode.vault) {
            return { allowCaptureWrites: false, state: "unknown", reason: "no vault is bound to the episode" };
        }
        return preflight(episode.vault);
    }

    // Best-effort read of which candidates appear recorded versus still unrecorded.
    async function completion() {
        if (!episode.vault) return { recorded: [], unrecorded: [] };
        return reconcile(episode.vault, candidates());
    }

    return {
        get state() { return episode.state; },
        get learner() { return episode.learner; },
        get vault() { return episode.vault; },
        activate: (input) => episode.activate(input),
        pause: () => episode.pause(),
        resume: () => episode.resume(),
        end: () => {
            admitted.length = 0;
            return episode.end();
        },
        admit,
        candidates,
        preflight: checkPreflight,
        completion,
    };
}
