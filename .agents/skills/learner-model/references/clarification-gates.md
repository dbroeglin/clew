# Clarification gates

The specification is authoritative but does not yet define a complete executable
storage contract. These are reasons to ask, not rules to implement speculatively.
First look for an explicit local configuration or an already documented
resolution. If none exists, explain the affected operation and ask for the
smallest missing decision. An answer can clarify a gap; it cannot silently
waive a model invariant.

| Gap or tension | Safe behavior |
| --- | --- |
| Private data processed by a hosted agent | Verify the execution boundary before opening notes. Local tool execution does not establish local inference. Stop private operations if the guarantee cannot be met. |
| Confidence posterior, initial confidence, or evidence combination | Thresholds and weights are given, but no update formula is specified. Do not turn evidence counts or weights into arbitrary probabilities. Ask for the rule. |
| Universal confidence, timestamp, scheduling, and efficacy requirements versus object schemas | Concepts omit explicit confidence; goals lack review/decay fields; several schemas lack efficacy or confirmation fields that general rules discuss. Do not invent keys, omit invariants, or assume a deadline resolves every mismatch. Ask for the applicable schema contract. |
| Append-only ledger versus inline `tombstoned` fields | No tombstone-event schema or overlay location is specified. Do not flip an old line's flag, add a new observation type to the closed list, or invent a sidecar. Ask for the append-only representation and its reader semantics. |
| Tombstoning observations shared by unrelated attributes | Deletion must remove the target's support without cascading into unrelated attributes. Explain shared support and ask for scoped suppression/recomputation semantics before any mutation. |
| New IDs, duplicate session filenames, merge disposition | Preserve IDs and aliases, inspect collisions, and use existing allocation/disambiguation rules. The surviving alias alone does not specify what to write into an absorbed note or how to redirect backlinks. Ask where needed. |
| Decision record storage, inactive dimensions, and baseline values | Section 4 defines an object but no path or inactive-decision encoding. Do not invent directories, unsupported values, attributes, or sources just to populate seven decisions. Ask for a convention. |
| Confidence thresholds versus the worked example | Section 11 preempts a misconception at confidence 0.55, below section 6.2's action thresholds. Enforce the explicit thresholds; if asked to reproduce that action exactly, explain the conflict and ask. |
| First-use proposal versus unconfirmed `T_ACT` | Eligibility does not waive section 6.6. Propose before first application and wait for the response. Keep at most one proposal per exchange. |
| Repair attempt counting | Text and examples do not fully specify initialization and whether starting an intervention increments the counter. Preserve history, count a documented failure/recurrence once, and clarify initialization or ambiguous transitions rather than double-counting. |
| Probe dates, missing durability, interval rounding, and initial schedules | Use explicit existing scheduling policy. Do not assume floor/ceiling, initialization, or calendar anchoring. Ask before persisting a guessed date. |
| Half-life anchors and re-evidence | Half-lives alone do not establish when decay was last applied, how evidence resets it, or how to avoid applying it twice. Ask for the calculation and anchor. |
| Preference expiry and retirement | Prose mentions expiry/retirement without corresponding fields/statuses in the preference schema. Preserve the record and ask for the representation. |
| Domain and scope mapping | Do not equate course names with domains or assume a hierarchy such as Calculus inheriting Mathematics preferences without a defined mapping. Ask when the selection depends on that hierarchy. |
| Efficacy estimator and confounding | Four pairs is a reporting minimum, not an estimator. Ask how outcomes are normalized/combined and how dimension effects are isolated when other decisions differ. Keep unknown efficacy unmeasured. |
| Tier or offline action not supported by actual tools | Record actual capability and do not claim inference, verification, generation, or transmission that did not happen. |

Read-only explanations and synthetic dry runs remain useful while a write is
blocked. Clearly identify missing inputs and proposed changes, and do not
present a hypothetical record as persisted learner knowledge.
