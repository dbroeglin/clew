const TUTOR_AGENT = "clew-tutor";

function normalizeAgentName(value) {
    return String(value ?? "").toLowerCase().replaceAll(" ", "-");
}

export function isTutorAgent(agent) {
    return [agent?.id, agent?.name, agent?.displayName]
        .some((value) => normalizeAgentName(value) === TUTOR_AGENT);
}

export function rootSelectionFromEvent(event) {
    if (event.agentId !== undefined) return null;
    return isTutorAgent({
        id: event.data?.agentName,
        name: event.data?.agentName,
        displayName: event.data?.agentDisplayName,
    });
}
