// App-local learning-episode state, deliberately distinct from the Copilot session
// and the agent identity. The state lives in memory only: a reload or restart begins
// inactive and requires a fresh explicit activation, so capture is never inferred
// from extension process lifetime.
export function createEpisode() {
    let state = "inactive";
    let learner = null;
    let vault = null;

    // Begin capture only on an explicit human activation with a known learner and vault.
    // Anything ambiguous leaves the episode inactive and returns a blocking reason,
    // rather than treating agent presence as consent.
    function activate({ learner: nextLearner, vault: nextVault, activation } = {}) {
        if (activation !== "explicit-human") {
            return { ok: false, blocked: true, state, reason: "activation is not an explicit human action" };
        }
        if (!nextLearner || !nextVault) {
            return { ok: false, blocked: true, state, reason: "learner and vault must be established before activation" };
        }
        learner = nextLearner;
        vault = nextVault;
        state = "active";
        return { ok: true, state, learner, vault };
    }

    function pause() {
        if (state !== "active") return { ok: false, state, reason: "episode is not active" };
        state = "paused";
        return { ok: true, state };
    }

    function resume() {
        if (state !== "paused") return { ok: false, state, reason: "episode is not paused" };
        state = "active";
        return { ok: true, state };
    }

    function end() {
        state = "inactive";
        learner = null;
        vault = null;
        return { ok: true, state };
    }

    // Whether a new interaction may be admitted for capture right now.
    function admits() {
        return state === "active";
    }

    return {
        get state() { return state; },
        get learner() { return learner; },
        get vault() { return vault; },
        activate, pause, resume, end, admits,
    };
}
