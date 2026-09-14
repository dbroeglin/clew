# Clew — The Learner Model

**Complete specification of the model, its objects, its lifecycles, and its guarantees.**

Clew builds a persistent, evidence-based model of an individual learner and uses it to adapt the
material that learner receives. This document defines what that model holds, how it changes, what it
refuses to hold, and what the learner can always do to it.

---

## 1. Principles

Six rules. A schema or update rule that violates one is wrong, however convenient.

1. **Indexed by domain, never by course.** A course is a vehicle; a domain is a body of knowledge.
   Course names appear only as *values*, never as keys or folders.
2. **No trait labels, ever.** Not clinical ("dyslexic"), not pedagogical ("visual learner"). The
   model holds observed working conditions and measured effects, both revisable.
3. **Two axes, not one.** Every adaptive attribute carries **confidence** (does he hold this?) and
   **efficacy** (does acting on it measurably help him?). They are independent and both required.
4. **No attribute without provenance.** At least one observation, a timestamp, and a confidence
   value, or the attribute must not be created.
5. **Everything is due.** Every attribute carries a next-due date and a decay rule. Nothing sits
   unchallenged forever on stale evidence.
6. **Nothing is deleted, only resolved or tombstoned.** History is the point. Renumbering and
   re-creation destroy the strongest signals in the model.

---

## 2. Object model

Six object types. The first four are the learner model proper; `Session` is the episode record;
`Provenance` is the ledger underneath all of them.

| Object | Path | Keyed by | Answers |
|---|---|---|---|
| **Concept** | `model/concepts/<domain>/<concept>.md` | domain + concept id | What does he know, how durably, what's damaging it, when to re-check |
| **Misconception** | `model/misconceptions/<domain>/M### - <name>.md` | permanent global id | What wrong rule does he hold, how confident, what repair was tried, did it hold |
| **Preference** | `model/preferences/<scope>/<name>.md` | dimension + scope | What working condition suits him here, is it confirmed, does it actually help |
| **Goal** | `model/goals/<name>.md` | id | What is he working toward, by when |
| **Session** | `model/sessions/<year>/YYYY-MM-DD - <mode> - <topic>.md` | date | What happened, in which domains, at what capability |
| **Provenance** | `model/provenance/<year>/<month>.jsonl` | append-only | Every observation, forever |

Course hubs (`courses/<course>/hub.md`) are **not** part of the learner model. They are read-only
course metadata supplying `primary_domains`, `prerequisite_domains`, and the concept index. The model
joins to them by course name.

**Why domain and not course.** A learner's connected course changes; the model must survive that.
If knowledge state is keyed to course-scoped identifiers, swapping courses orphans the model — a
routine operation destroys Clew's core asset. Domain indexing also makes the strongest diagnostic
signal available at all: the same wrong rule resurfacing in a *different* course is how you learn a
repair was skin-deep. `(a+b)² = a²+b²` met during differential equations is an **Algebra** bug.

---

## 3. Schemas

Shared rules: dates are `YYYY-MM-DD`. Empty list is `[]`; unknown scalar is `null`; a defined key is
never omitted, because a missing key and an empty one behave differently in filters. `confidence` and
`efficacy` are `0.0–1.0` and `-1.0–1.0` respectively, or `null` for unmeasured.

### 3.1 Concept

```yaml
---
type: concept
concept_id: LA.EIGEN.001        # from course material where available; else derived and stable
concept: Eigenvalues
domain: Linear Algebra          # where the concept lives, not where it is used
required_by:                    # list of objects — never flatten to strings
  - course: Differential Equations
    plan_week: 0                # 0 = prerequisite
  - course: Vector Spaces
    plan_week: 6                # core content
level: practiced                # unseen | introduced | practiced | fluent | mastered
boundary_stated: false          # required true before promotion to mastered
evidence_count: 4
durability: 0.55                # per-concept retention estimate, 0-1; distinct from level
last_assessed: 2026-01-19
next_review: 2026-01-26
review_interval_days: 7
open_misconceptions:
  - "[[M012 - Linearity over-generalization]]"
expansion_blocked: true         # derived: true while any open high-severity misconception links here
provenance: [obs-4471, obs-4502, obs-4513, obs-4530]
---
```

**Mastery ladder.**

| Level | Means |
|---|---|
| `unseen` | Not yet encountered. |
| `introduced` | Has seen it; cannot use it unaided. |
| `practiced` | Correct on familiar surface structure, slow or with hints. |
| `fluent` | Correct and quick on unfamiliar surface structure. |
| `mastered` | Fluent, **and** can state the boundary conditions and explain why they hold. |

Promotion to `mastered` requires `boundary_stated: true`. Correct answers alone are insufficient —
the gap between fluent and mastered is where misconceptions hide.

**`durability` is not `level`.** Level is current standing; durability is how fast it decays for this
learner on this concept. Two concepts at `fluent` with durability 0.9 and 0.3 need completely
different schedules. Durability is estimated from the delta between assessments over elapsed time and
is the per-concept modifier on the global interval rule (§6.1).

**`required_by` is load-bearing.** One `Eigenvalues` note is week-0 prerequisite for one course and
week-6 core for another: one mastery level, one schedule, one evidence count. Filed under courses this
note would exist twice, diverge, and cause Clew to re-teach something already fluent.

### 3.2 Misconception

```yaml
---
type: misconception
id: M012                        # global, permanent, never reused
aliases: []                     # ids merged INTO this entry when two proved to be one bug
catalog_id: CAT-ALG-01          # the generic prior; null if novel to this learner
name: Linearity over-generalization
domain: Algebra                 # the most primitive domain the wrong rule is statable in
origin: provisional             # course-defined | provisional
status: repairing               # candidate | active | repairing | resolved | durable
severity: high                  # high | medium | low
confidence: 0.8                 # posterior that he actually holds this rule
reproduced_under_variation: true
surfaced_in:                    # courses where actually observed — values, not keys
  - Differential Equations
concepts:                       # concept notes this bug damages
  - "[[Chain Rule]]"
  - "[[Logarithm Laws]]"
first_observed: 2026-01-12
last_probed: 2026-01-19
next_probe: 2026-01-26
probe_count: 3
repair_attempts: 1
interventions:                  # what was tried, and whether it held
  - date: 2026-01-14
    framing: worked-example     # visual-first | narrative | worked-example | procedural
    artifact: "[[Chain Rule - Explainer 2026-01-14]]"
    outcome: failed             # held | failed | pending
    confirmed_at: null          # date delayed retrieval confirmed the repair
expires_on: 2026-04-19          # absent re-evidence, terminal state at this date
provenance: [obs-4390, obs-4471, obs-4502]
---
```

Body carries proof, frontmatter carries state:

```markdown
## The wrong rule
f(a+b) = f(a) + f(b), applied to any f that looks like an operation.

## Correct rule and its boundary
Additivity holds only for linear f. Boundary: f(x) = cx.

## Evidence
- 2026-01-19 — asked to expand (x+3)²; wrote x² + 9. Reproduced on (a+b)³, so not a slip.
- 2026-01-12 — wrote ln(x+1) = ln x + ln 1 unprompted mid-solution.

## Why the wrong rule felt right
Every f he had met before was a scaling. Distributivity of × over + generalises silently.
```

**Catalogue is the prior, ledger is the posterior.** `catalog_id` links to the generic bug students in
this subject typically hold; the entry is what *this* learner demonstrated. A provisional
misconception may later be promoted into the catalogue; the entry keeps its id either way.

**`severity` drives prioritisation.** `high` = corrupts downstream reasoning and blocks concept
interval expansion. `low` = local and self-limiting. Without this, "practise the weakest concepts"
has no ordering.

**`repair_attempts > 1` is the most important number in the model.** It means a repair failed and the
bug came back. Resolved bugs that resurface **reopen the existing entry** and increment the counter —
they never mint a new one. `interventions` is what makes the retry intelligent: don't re-run the
framing that already failed.

**`durable`** is a status, not a failure state: a bug that has survived repeated repair and is now
known to be persistent. It changes strategy — work around it and flag it proactively rather than
attempt repair a fourth time.

**ID discipline.** Permanent and never reused; renumbering breaks every link. Two entries proved to be
one bug are merged by adding the absorbed id to `aliases`, never by deletion.

### 3.3 Preference

```yaml
---
type: preference
id: P007
dimension: chunk_length         # one of the adapted dimensions (§4)
scope: Mathematics              # domain name, or `global` for accessibility-class preferences
condition: "~120-word sections with increased spacing"   # observed working condition
value: 120
confidence: 0.7                 # does he hold this preference
efficacy: 0.18                  # does acting on it improve HIS measured performance; null = unmeasured
efficacy_n: 6                   # artifact pairs the efficacy estimate rests on
learner_confirmed: true
proposed_at: 2026-01-15
confirmed_at: 2026-01-15
last_updated: 2026-01-22
next_review: 2026-02-19
provenance: [obs-4402, obs-4455, obs-4501]
---
```

**Two axes, and they come apart.** Confidence moves on what the learner says, accepts, and declines.
Efficacy moves only on measured performance against his own prior history. Learners routinely prefer
the format that feels fluent over the one that works; an attribute with high confidence and neutral
efficacy is a **cosmetic adaptation**, and this is the only instrument that can detect it.

**`scope` is domain-level, not global**, except for accessibility-class preferences (reduced motion,
sign/operator colour coding, contrast) which are genuinely person-level and carry everywhere. A
learner may work better with worked-example framing in mathematics and narrative framing in history.
Scoping by domain is also what prevents `modality_framing` from degenerating into a trait label: a
trait does not vary by subject.

**`condition` is an observed working condition and never a characterisation.** "Performs better with
~120-word sections" is permitted. "Dyslexic", "visual learner", "struggles with abstraction" are not.
This is enforced at write time (§9).

### 3.4 Goal

```yaml
---
type: goal
id: G002
goal: Pass the Differential Equations final
kind: exam                      # exam | project | self-set | deadline
deadline: 2026-05-14
domains: [Ordinary Differential Equations, Linear Algebra]
concepts: []
status: active                  # active | met | abandoned | expired
confidence: 1.0                 # self-reported goals are high-confidence by nature
provenance: [obs-4301]
---
```

### 3.5 Session

```yaml
---
type: session
date: 2026-01-19
mode: practice                  # explain | practice | ingest | review
course: Differential Equations  # the vehicle; null for a course-less session
domains: [Calculus, Algebra]    # what was ACTUALLY exercised
concepts: ["[[Chain Rule]]"]
artifacts: ["[[Chain Rule - Practice 2026-01-19]]"]
adaptation_decisions: "[[AD-2026-01-19-01]]"
misconceptions_probed: ["[[M012 - Linearity over-generalization]]"]
misconceptions_found: []
outcome: partial-repair         # diagnosed | partial-repair | repaired | no-change | blocked
tier: 3                         # capability tier the session actually ran at
duration_min: 35
---
```

**`course` and `domains` differ on purpose** — this is the whole model in miniature. The session
happened *inside* a DE course but exercised *calculus and algebra*. Recording only the course loses
that, and with it the ability to see the bug resurface elsewhere.

**`tier` records how capable Clew was when the conclusion was drawn.** Tier 3 = full inference;
tier 2 = inference available, degraded context; tier 1 = no inference (offline, signed out,
entitlement exhausted). Observations recorded at tier 1 carry reduced evidential weight (§6.3)
because nothing was verified. At tier 1 Clew must also never claim to have done something it could
not do.

Sessions give the provenance ledger episode structure. Without them, the provenance chain is an
atomised list and "what happened two weeks ago" is unanswerable.

### 3.6 Provenance entry

Append-only. One line per observation.

```yaml
id: obs-4502
timestamp: 2026-01-19T14:22:03
session: "[[2026-01-19 - practice - Chain Rule]]"
type: wrong-answer              # see the closed list below
tier: 3
context:
  artifact: "[[Chain Rule - Practice 2026-01-19]]"
  concept: "[[Chain Rule]]"
  item: 4
content: "Expanded (x+3)² as x² + 9."
informs: [M012, "[[Chain Rule]]"]
tombstoned: false
tombstone_reason: null
```

**Closed list of observation types.** Only these are recorded:

| Type | Informs |
|---|---|
| `statement` — explicit statement in conversation | preferences, knowledge, goals |
| `wrong-answer` — wrong answer on a practice item | knowledge, misconceptions |
| `hint-request` — hints requested before solving | knowledge, misconceptions |
| `artifact-edit` — edits and annotations to an artifact | preferences |
| `proposal-response` — acceptance or rejection of an adaptation proposal | preferences (confidence) |
| `supplied-work` — content of learner-supplied work | knowledge, misconceptions |
| `performance-delta` — measured outcome change across adaptation decision sets | preferences (efficacy) |
| `correction` — learner correction via the inspector | any attribute; outranks inference |

`performance-delta` powers §6.5. It is derived from practice results already recorded, not from new
instrumentation — no passive telemetry is involved.

Entries are never edited or removed, only tombstoned. Tombstoning hides the entry from the learner's
view and removes its contribution to attribute values; the line stays in the ledger.

---

## 4. Adaptation decisions

Separate objects, resolved before generation, recorded permanently.

```yaml
---
type: adaptation_decisions
id: AD-2026-01-19-01
resolved_at: 2026-01-19T14:05:00
concept: "[[Chain Rule]]"
domain: Calculus
decisions:
  chunk_length: {value: 120, from: [P007], confidence: 0.7}
  progressive_disclosure: {value: collapsed, from: [P011], confidence: 0.5}
  information_density: {value: low, from: [P007], confidence: 0.7}
  signposting: {value: explicit, from: [P014], confidence: 0.8}
  modality_framing: {value: worked-example, from: [P021], confidence: 0.6}
  prerequisite_scaffolding: {value: [Limits], from: ["[[Limits]]"], confidence: 0.9}
  misconception_preemption: {value: [M012], from: [M012], confidence: 0.8}
sent_over_boundary: true
---
```

Seven decisions, each tracing to the attributes that produced it. This object, plus the grounded
course excerpt, is **the only thing that crosses the machine boundary** — and because it is a
discrete serialised artifact, what was sent can be demonstrated exactly.

Every decision pairs a structural difference with a presentational one. The `from` field is what
makes two-way tracing work: attribute → artifacts it influenced, and artifact → attributes that
shaped it.

---

## 5. The loop

**Observe → Infer → Resolve → Transform → Measure → Reinforce**

The two closing steps are the difference between a model that tracks what the learner *likes* and one
that tracks what *works*.

1. **Observe.** A deliberate learner action produces a provenance entry.
2. **Infer.** Accumulated observations move an attribute's confidence. Nothing changes until a named
   threshold is crossed.
3. **Resolve.** Adaptation decisions are computed from the model, as a separate act, prior to and
   independent of generation.
4. **Transform.** The artifact is produced under those decisions, which it records.
5. **Measure.** Performance on that concept under decision set A is compared against this learner's
   own history under set B. The delta is recorded as a `performance-delta` observation.
6. **Reinforce.** A decision's **efficacy** rises only if measured performance improved. Confidence
   and efficacy move on different evidence and are never conflated.

---

## 6. Change rules

### 6.1 Scheduling and decay

Nothing in the model sits unchallenged. Every attribute has `next_review` or `next_probe`.

**Concept review intervals.** Base rule, modified per concept by `durability`:

| Assessment result | Interval change |
|---|---|
| Correct, at `fluent` or above | `interval × (1 + durability)`, capped at 90 days |
| Correct, below `fluent` | `interval × 1.5`, capped at 30 days |
| Hesitant or hint-assisted | interval unchanged |
| Wrong | reset to 1 day |

**A concept with an open `high`-severity misconception is barred from interval expansion.** Fluency on
top of a broken rule is memorisation. This is the `expansion_blocked` derived field.

**Repaired misconceptions are re-probed at 1, 7 and 28 days.** A repair confirmed at 28 days sets
`interventions[].confirmed_at` and moves status to `resolved`. A failure at any checkpoint reopens
the entry and increments `repair_attempts`.

**Confidence decays absent re-evidence**, on a per-category half-life:

| Category | Half-life | Rationale |
|---|---|---|
| Knowledge state | governed by `durability`, not a fixed half-life | Retention is the thing being modelled |
| Misconception | 120 days | Unrehearsed bugs may have been repaired incidentally |
| Preference — interface | 180 days | Working conditions are relatively stable |
| Preference — accessibility | no decay | Person-level and persistent |
| Goal | to `deadline`, then `expired` | Goals have natural terminal dates |

**Expiry is a terminal state, not just drift.** An attribute reaching `expires_on` without
re-evidence moves to `resolved` (misconceptions) or is retired (preferences). It is never deleted.

### 6.2 Thresholds

Thresholds are explicit, named, and inspectable. These are provisional and expected to be revised
repeatedly; they are configuration, not embedded behaviour.

| Name | Value | Effect |
|---|---|---|
| `T_CREATE` | 0.35 | Below this, an inference is not written as an attribute at all |
| `T_PROPOSE` | 0.60 | An unconfirmed preference at or above this is proposed to the learner |
| `T_ACT` | 0.60 confirmed, or 0.75 unconfirmed | The attribute may influence adaptation decisions |
| `T_RESOLVE` | 0.20 | A misconception falling below this becomes `resolved` |
| `T_VARIATION` | 2 distinct item structures | Required before a wrong answer becomes a misconception |
| `T_EFFICACY_N` | 4 artifact pairs | Minimum before an efficacy estimate is reported rather than `null` |
| `T_DURABLE` | `repair_attempts ≥ 3` | Misconception moves to `durable`; stop attempting repair |

### 6.3 Evidence weighting

Not every observation counts equally.

- Tier-1 observations carry **0.5×** weight — nothing was verified.
- `correction` observations **override** inferred values outright and set `learner_confirmed`.
- `statement` (self-reported) observations carry no special authority: an intake claim is an
  observation like any other and is revisable like any other.
- `supplied-work` observations carry **1.5×** weight on knowledge and misconceptions. A marked past
  paper contains more signal about a learner than an hour of conversation.

### 6.4 The slip filter

**A wrong answer is not a misconception.** Before an entry is created:

- The error must **reproduce under variation** — at least `T_VARIATION` items differing in surface
  structure, not repetition of the same item.
- Until then it is held as an unpromoted pattern in the provenance ledger with no attribute.

This is a sharper test than statistical repetition, and it matters because Clew names the
misconception to the learner when it acts on one. Naming a broken rule when the learner made an
arithmetic slip is expensive — it is exactly the condescension that makes learners disable
adaptation.

### 6.5 Efficacy measurement

For a preference `P` influencing dimension `D`:

1. Find artifacts on the same concept or within the same domain produced under decision sets that
   differ in `D`.
2. Compare practice outcomes — first-attempt correctness, hint depth required, error recurrence —
   **against this learner's own history only**. There is no population baseline.
3. Record the delta as a `performance-delta` observation.
4. Below `T_EFFICACY_N` pairs, efficacy is reported as `null` / *unmeasured*, never as zero.

An attribute with confidence above `T_ACT` and measured efficacy at or below zero across sufficient n
is **surfaced to the learner in the inspector as an adaptation that does not appear to be helping**,
with the option to drop it. Clew does not silently keep doing something it has evidence does not
work.

### 6.6 Confirmation

- First application of an adaptation is proposed in plain language before generating.
- Accepting records a confirming observation and marks `learner_confirmed`; it applies silently
  thereafter and is never re-confirmed.
- Declining lowers confidence and records the rejection; Clew may propose again if confidence
  re-crosses `T_PROPOSE` on new evidence.
- At most one proposal per exchange.
- Confirmation sets `learner_confirmed`, never `efficacy`. Agreement is not evidence of effect.

---

## 7. Read path

Session start loads cheapest-first, and stops as soon as it has what the request needs. This is also
the operative definition of "what is needed for the current request".

1. **Review queue** — every attribute with `next_review` or `next_probe` at or before today.
2. **Course hub** — `primary_domains` + `prerequisite_domains` of the connected course.
3. **Open misconceptions in those domains only** — not the whole ledger.
4. **Concept levels for concepts in those domains**, plus any reached via `required_by`.
5. **Preferences** scoped to those domains, plus all `global`-scoped ones.
6. **Active goals.**

Steps 2–6 are exactly the folders implied by the course hub's domain lists, which makes candidate
generation mechanical rather than a search.

---

## 8. Ownership

- **Inspect.** Every attribute, grouped by category, with confidence, efficacy, confirmation status,
  and full provenance chain — every observation behind it, what it was, when, and at what tier.
- **Correct.** In the learner's own words. A correction is itself an observation, recorded with
  provenance, and takes precedence over any inferred value.
- **Delete.** Removes the attribute from the learner's view and tombstones its supporting
  observations. The append-only ledger is never rewritten. Deletion does not cascade into unrelated
  attributes, and Clew states plainly what will change first.
- **Trace both ways.** Attribute → artifacts it influenced, artifact → attributes that produced it.
- **Learner's language throughout.** No internal identifiers, no raw scores without interpretation.
  `confidence: 0.8` is displayed as "fairly sure"; `efficacy: 0.18` as "this seems to be helping."

Storage is on the learner's machine, human-readable and portable. There is no automatic backup and
no cross-device sync; the learner is told this plainly once, at a point where it matters.

**What crosses the boundary** is the resolved adaptation decisions and the grounded course excerpt,
and nothing else — enforced by construction, demonstrable after the fact.

---

## 9. Write-time invariants

Enforced structurally. A write violating any of these fails rather than warns.

1. No attribute without ≥1 provenance entry, a confidence value, and a timestamp.
2. No free-text psychological, clinical, or diagnostic characterisation in any field.
3. No trait-style pedagogical label (`visual learner`, `kinaesthetic`) — only dimension + measured
   condition + scope.
4. No domain name may equal a course name.
5. No misconception id reused; merges go through `aliases`.
6. No provenance entry edited or deleted; only tombstoned.
7. No misconception created without `reproduced_under_variation: true`.
8. No promotion to `mastered` without `boundary_stated: true`.
9. No payload crosses the boundary except a serialised `adaptation_decisions` object and a grounded
   excerpt.

---

## 10. What the model does not contain

Excluded, with the reason and the cost stated honestly.

| Excluded | Reason | Cost accepted |
|---|---|---|
| **Passive telemetry** — dwell, scroll, replay, skips, abandonment | Uninterpretable without context (long dwell = engaged or stuck?) and produces a black-box model | **Real.** The Measure step is powered by practice performance and explicit actions alone, so efficacy converges more slowly and `T_EFFICACY_N` is reached later. Revisit if efficacy proves unmeasurable in practice. |
| **Institutional dashboards**, even de-identified and aggregated | Aggregation still requires transmission, breaking the boundary guarantee, and introduces a second stakeholder where there is exactly one actor | No institutional adoption path in the first version. Accepted. |
| **Teacher override of attributes** | Would sit above the learner in the correction hierarchy, inverting ownership | Course-defined misconceptions remain the teacher's only channel into the model, and they enter as *priors*, not as facts. |
| **Clinical or diagnostic characterisation** | Permanently out of scope | None. |
| **VARK-style modality taxonomy as learner traits** | The meshing hypothesis is not supported by the evidence, and "auditory learner" is precisely the trait label principle 2 forbids | None — `modality_framing` is retained as a *content* dimension, domain-scoped and efficacy-measured, which is the defensible form. |

---

## 11. Worked example

The signal this model exists to capture, end to end:

1. **Sep.** During *Differential Equations*, the learner writes `ln(x+1) = ln x + ln 1`. One
   observation. Below `T_VARIATION` — no attribute created.
2. **Sep.** Asked to expand `(x+3)²`, writes `x² + 9`. Different surface structure; variation
   satisfied. **M012** created in **Algebra** — not in Differential Equations — at confidence 0.55,
   severity `high`, `surfaced_in: [Differential Equations]`.
3. **Sep.** `Chain Rule` and `Logarithm Laws` acquire `open_misconceptions: [M012]`. Both become
   `expansion_blocked` — neither can have its review interval extended while a high-severity bug
   damages it, however many correct answers arrive.
4. **Sep.** An explainer is generated with `misconception_preemption: [M012]` and
   `modality_framing: worked-example`. Status → `repairing`; an `interventions` entry opens.
5. **Oct.** Re-probed at 1 and 7 days: clean. At 28 days: fails. `repair_attempts` → 1,
   `interventions[0].outcome: failed`. The worked-example framing is now known not to have worked
   *for this bug*.
6. **Oct.** Second repair attempt selects `visual-first` — because the ledger records which framing
   already failed. Holds at 1, 7, 28. `confirmed_at` set; status → `resolved`; confidence 0.18,
   below `T_RESOLVE`. **The entry is kept.**
7. **Feb.** Course replaced with *Economics*. The learner model is untouched — M012 lives in Algebra,
   and `Chain Rule` and `Logarithm Laws` keep their levels, durability, and schedules.
8. **Mar.** While manipulating an elasticity expression, the same wrong rule appears. M012 is
   **reopened** — not re-created. `repair_attempts` → 2. `surfaced_in` becomes
   `[Differential Equations, Economics]`.
9. **Mar.** `repair_attempts: 2` with two framings exhausted is the strongest diagnostic signal in the
   model, and it exists only because the bug was filed by domain, the entry was never deleted, the
   interventions were tracked, and the id was never reused.
10. **Mar.** Meanwhile `P021` (`modality_framing: visual-first`, scope `Mathematics`) shows
    confidence 0.7 and efficacy 0.22 over 6 pairs — it is helping. `P011`
    (`progressive_disclosure: collapsed`, scope `Mathematics`) shows confidence 0.8 but efficacy
    −0.04 over 7 pairs: he likes it and it is not working. The inspector surfaces exactly that, in
    those words, and offers to drop it.

Step 10 is the test: the learner can point at something and say *"it did that because of something I
actually did"* — and be right.

---

## 12. Open questions

1. **Cold start.** How few observations produce a first artifact that is visibly personal rather than
   generic? The intake, `supplied-work` weighting, and course-defined misconceptions as priors carry
   the weight; none of them is validated.
2. **Threshold and decay values.** §6.2 and §6.1 name every constant but validate none. The decay
   half-lives in particular are guesses.
3. **Efficacy without telemetry.** Whether `T_EFFICACY_N` is reachable in realistic use from practice
   performance alone is the central unproven assumption of §6.5. If it is not, either the Measure
   step or the telemetry exclusion has to give.
4. **Regeneration and edits.** What "untouched region" means when the structure itself is adapted.
5. **Source view.** A per-artifact "show me the unadapted source" is an *inspection act*, not a mode,
   and closes a real trust gap — the learner currently cannot verify what Clew did to their
   material. Recommend adopting; not yet decided.
6. **Typography as an adapted dimension.** Deferred. Four interface dimensions ship; accessibility-class
   preferences (contrast, reduced motion) are retained at `global` scope.
