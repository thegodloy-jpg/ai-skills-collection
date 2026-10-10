# Decomposition Patterns

Use these patterns as candidates, not mandatory schemas. Select the smallest chain whose outputs feed the next decisions.

## Contents

- Pattern selection
- Continue a layered learning path
- Storage or residency
- Data movement or communication
- Execution or configuration
- Distributed system
- Optimization method
- API or data contract
- Scheduler
- Compression and closure tests

## Pattern selection

| Topic shape | Candidate chain | Typical final output |
|---|---|---|
| Continuation of a prior layer | Inherited artifact -> current gap -> current result -> downstream handoff | One new layer without redefining earlier work |
| Storage or residency | Object -> placement -> pressure/lifecycle | Keep, move, evict, restore, or recompute |
| Data movement or communication | Source/target/amount -> path -> cost/bottleneck -> strategy/tradeoff | Effective movement cost and downstream input |
| Execution or configuration | Input -> resolution/transform -> effective output | Final command, state, or behavior |
| Distributed system | Roles -> data/state flow -> failure/recovery | End-to-end request outcome |
| Optimization method | Baseline -> bottleneck -> mechanism -> tradeoff | When the method helps or hurts |
| API or data contract | Source -> transformation -> response -> consumer | Authoritative field and interpretation |
| Scheduler | Work unit -> constraints -> policy -> observable effect | Placement, ordering, fairness, or SLO result |
| Failure diagnosis | Symptom -> evidence chain -> cause -> boundary | Evidence-backed explanation, not an assumed fix |

## Continue a layered learning path

Use when the current request follows an earlier chapter, angle, paper, or artifact.

```text
Original learning outcome
    -> inherited artifact and deferred interface
    -> current unresolved layer
    -> current result
    -> next-layer decision or final use
```

Do not redefine an object, state, or mapping already established upstream. A new topic label identifies the current layer; it does not replace the original learning outcome. Reject a decomposition that produces a useful standalone tutorial but no output consumed by the larger learning path.

Reconcile the handoff field by field. Preserve upstream units and conditions; label any new field as derived, assumed, or missing. Name every downstream consumer when the current result fans out to more than one later decision.

## Storage or residency

Use when the topic concerns memory, caches, persistence, or tiering.

```text
What is stored?
    -> Where can it reside?
    -> What happens under pressure or later access?
```

Keep communication paths, compute kernels, and service routing as named deferred layers unless requested.

## Data movement or communication

Use when a prior storage, placement, or execution result creates a concrete movement task.

```text
Inherited source, target, amount, and action; explicit or derived direction
    -> end-to-end path and distinct path segments
    -> effective cost and bottleneck
    -> strategy targeted at that bottleneck
    -> cost and constraints handed to downstream decisions
```

Treat device-local access, cross-device transfer, storage I/O, and remote-network transfer as different path segments. Do not promote every endpoint or internal component into an independent top-level question.

Diagnose the baseline path and bottleneck before asking about optimization strategy. If an earlier layer already defines the moved object, its location, or its lifecycle action, consume those results rather than teaching them again. Stop at the communication result when a final choice still requires compute cost, placement policy, request scheduling, or an SLO.

Keep inherited endpoints, amount, and action fixed unless their owner explicitly reopens them. If direction is derived from the endpoints, mark it as derived rather than upstream-exported.

Separate these views when they differ:

| View | Meaning |
|---|---|
| Logical flow | source and target visible to the higher-level workflow |
| Physical path | actual devices, links, copies, and shared resources traversed |
| Control path | who submits, registers, schedules, or confirms the operation |
| Fallback path | what happens when the preferred mechanism is unavailable |

For cost reasoning, choose either a decomposed model or an observed end-to-end model. Declare units, per-device versus aggregate scope, per-task versus per-operation frequency, logical versus physical amount, concurrency assumptions, and omitted terms. Do not charge a component again when an observed total already includes it.

Let communication strategies change only communication-owned variables such as path selection among already available routes, chunking, queueing, concurrency, and overlap capability. Return endpoint, placement, replica, admission, or launch-time changes to their owning layer. Output intrinsic movement cost and capability; mark deadline- or compute-window-dependent values as conditional downstream derivations.

## Execution or configuration

Use when the learner needs the actual runtime truth rather than a list of defaults.

```text
What enters the system?
    -> How is it parsed, merged, gated, or adapted?
    -> What effective output is emitted?
```

Treat the final rendered command, request, file, or state as the behavioral endpoint.

## Distributed system

Use when several components jointly own a result.

```text
Who owns each responsibility?
    -> How does data or state move?
    -> What happens on success, contention, and failure?
```

Do not merge control-plane choice, data-plane movement, and storage location into one question.

## Optimization method

Use when evaluating a technique rather than merely defining it.

```text
What is the baseline?
    -> What bottleneck is measured?
    -> What mechanism changes it?
    -> What cost, correctness, or workload boundary appears?
```

Avoid declaring an optimization beneficial without comparing its end-to-end cost with the baseline.

## API or data contract

Use when a field passes through several layers or a UI consumes a response.

```text
Where is the value produced?
    -> How is it transformed or merged?
    -> Which field is authoritative?
    -> How should the consumer interpret it?
```

Separate enablement, capacity, status, and diagnostics when they have different owners.

## Scheduler

Use when the system admits, places, orders, or prioritizes work.

```text
What work unit enters the decision?
    -> Which hard constraints define the feasible set?
    -> Which policy selects or orders feasible options?
    -> What observable decision or no-decision state results?
```

Separate hard eligibility filters from soft ranking or fairness policy. End the chain at the scheduler's observable decision; keep post-decision execution, startup, and runtime failure handling in a deferred layer unless requested. Treat an end-to-end walkthrough as the closure test, not as another domain question.

## Compression test

For each proposed question, ask:

| Test | Remove or revise when... |
|---|---|
| Dependency | no later question consumes its output |
| Uniqueness | another question already supplies the same result |
| Scope | it belongs to a deliberately deferred layer |
| Decision value | it adds facts but changes no explanation or decision |
| Learnability | it requires advanced detail before the base object is defined |
| Essentiality | removing it still allows the question to produce its output and pass acceptance |
| Representation uniqueness | another table, diagram, formula, or paragraph already expresses the same relationship |

## Closure test

A chain is closed only when a learner can:

1. identify the starting object, input, or baseline;
2. trace every transformation or state transition;
3. explain the final state or decision;
4. run one representative scenario through the chain;
5. name what remains undecidable until the next learning layer;
6. identify the owner and required inputs of every deferred decision.
