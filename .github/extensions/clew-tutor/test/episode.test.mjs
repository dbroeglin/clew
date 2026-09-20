import assert from "node:assert/strict";
import test from "node:test";
import { createEpisode } from "../episode.mjs";

const binding = { learner: "learner-1", vault: "/synthetic/vault", activation: "explicit-human" };

test("a new episode is inactive and admits nothing", () => {
    const episode = createEpisode();
    assert.equal(episode.state, "inactive");
    assert.equal(episode.admits(), false);
});

test("activation requires an explicit human action and a known learner and vault", () => {
    assert.equal(createEpisode().activate({ ...binding, activation: "agent-present" }).blocked, true);
    assert.equal(createEpisode().activate({ activation: "explicit-human" }).blocked, true);
    const episode = createEpisode();
    const result = episode.activate(binding);
    assert.equal(result.ok, true);
    assert.equal(episode.state, "active");
    assert.equal(episode.admits(), true);
});

test("pause stops admission and resume restores it", () => {
    const episode = createEpisode();
    episode.activate(binding);
    episode.pause();
    assert.equal(episode.state, "paused");
    assert.equal(episode.admits(), false);
    episode.resume();
    assert.equal(episode.admits(), true);
});

test("ending clears the learner and vault binding", () => {
    const episode = createEpisode();
    episode.activate(binding);
    episode.end();
    assert.equal(episode.state, "inactive");
    assert.equal(episode.learner, null);
    assert.equal(episode.vault, null);
});

test("a fresh episode after a reload does not resume capture on its own", () => {
    // State is in-memory, so a reload is modeled as a new episode: it starts inactive
    // and must be explicitly re-activated rather than inferring capture from process life.
    const reloaded = createEpisode();
    assert.equal(reloaded.state, "inactive");
    assert.equal(reloaded.admits(), false);
});
