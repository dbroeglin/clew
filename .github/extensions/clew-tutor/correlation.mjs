// Derive the key that decides whether two meaningful events describe the same work.
// An explicit attempt identity binds a chat discussion to its canvas submission; an item
// plus category groups same-topic activity; otherwise each interaction stands alone.
export function correlationKey(classification) {
    const ref = classification.event.ref ?? {};
    if (ref.attemptId) return `attempt:${ref.attemptId}`;
    if (ref.itemId) return `item:${ref.itemId}:${classification.category}`;
    return `interaction:${classification.event.interactionId}`;
}

// Group meaningful classifications into candidates so the same work is one candidate while
// genuinely distinct attempts stay distinct. Re-delivery of the same interactionId is
// idempotent. This is best-effort correlation, not an enforced exactly-once guarantee.
export function correlate(classifications) {
    const byKey = new Map();
    const seen = new Set();
    for (const classification of classifications) {
        if (!classification.write) continue;
        if (seen.has(classification.event.interactionId)) continue;
        seen.add(classification.event.interactionId);
        const key = correlationKey(classification);
        let candidate = byKey.get(key);
        if (!candidate) {
            candidate = {
                key,
                category: classification.category,
                target: classification.target,
                sources: new Set(),
                events: [],
            };
            byKey.set(key, candidate);
        }
        candidate.sources.add(classification.event.source);
        candidate.events.push(classification.event);
    }
    return [...byKey.values()].map((candidate) => ({
        key: candidate.key,
        category: candidate.category,
        target: candidate.target,
        sources: [...candidate.sources],
        events: candidate.events,
    }));
}
