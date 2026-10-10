---
name: build-technical-learning-loop
description: "Analyze and refine learning questions for complex technical systems, papers, or source-code paths; preserve the original learning goal, field-level handoffs, and decision ownership across sequential angles; reduce broad asks to a minimal dependency-complete question chain; define current and deferred scope; answer in staged closed loops; and optionally create concise Markdown with tables and necessary Mermaid diagrams. Use when users ask whether their questions are reasonable, want to reduce learning cost, continue from one learning layer or paper to another, build a reusable study framework, answer only a specified phase, convert results into a compact guide, or extend the framework with later sources. Do not use for simple factual explanations, ordinary rewrites, or direct implementation tasks without learning-framework design."
---

# Build Technical Learning Loop

Turn a broad technical-learning request into a scoped, dependency-complete path that can be answered, validated, documented, and extended without repeatedly redesigning the method.

## Honor the requested phase

Infer the active phase from the user's latest request. Execute multiple phases only when the user requests them together.

| Phase | Typical request | Required behavior |
|---|---|---|
| Analyze | Asks whether the current questions are reasonable | Diagnose the framing and scope only. Do not answer the full topic, deliver a replacement chain, or edit files. |
| Refine | Asks to simplify or concentrate the questions | Produce the minimum dependency-complete question chain and explain material removals. |
| Answer | Asks to answer with the approved logic | Answer the approved chain without silently expanding deferred topics. |
| Document | Asks to organize the result as Markdown | Create or edit only the requested artifact, then validate it. |
| Extend | Asks to incorporate a later paper or source | Map new evidence into the existing framework before changing base conclusions. |

Treat explicit boundaries such as "analyze only," "do not modify yet," and "defer communication" as hard constraints, including semantically equivalent requests in other languages. Do not advance to a later phase merely because the next step is obvious. Reply in the user's language unless they request otherwise.

## Establish the learning contract

Extract or infer:

- the stable core learning outcome and the narrower current-layer outcome;
- whether this is a standalone request or a continuation of an earlier learning layer;
- prior artifacts, conclusions, and deferred interfaces that the current layer must consume;
- every known downstream decision or learning layer that will consume the current output, and who owns each decision;
- the source set: papers, documentation, code, measurements, or examples;
- the current scope and deliberately deferred adjacent layers;
- the learner's current depth and desired output density;
- the requested artifact and mutation boundary.

Make safe assumptions when they do not change scope. Ask only when a missing choice would materially alter the learning path or artifact.

## Preserve continuity across learning layers

When the user says "from the previous angle," "next topic," "based on the earlier document," or otherwise continues an existing path, inspect the prior artifact or conversation before choosing a new decomposition pattern.

Extract this handoff contract:

| Field | Meaning |
|---|---|
| Core outcome | The original capability the learner is trying to build |
| Inherited input | A prior result that is already established and must not become a new question |
| Current gap | The unresolved layer requested now |
| Current output | The result this layer must add |
| Downstream consumers | The later questions or decisions that will use the result |

Keep the core outcome stable while changing angles. Start the new chain at the prior layer's explicitly deferred interface. Do not restart with definitions, inventories, or questions that the previous artifact already answered.

Read the continuation and data-movement sections in [references/decomposition-patterns.md](references/decomposition-patterns.md) when a request crosses learning layers or turns a prior storage result into a communication, computation, or scheduling question.

## Reconcile fields and decision ownership

For a continuation, build this internal ledger before decomposing the new layer. Show it only when it helps the learner verify the handoff.

| Field | Upstream anchor | Status | Unit or condition | Current use | Decision owner |
|---|---|---|---|---|---|
| inherited or added field | explicit source location | exact / derived / assumed / missing | retained constraints | why this layer needs it | upstream / current / downstream |

- Mark `exact` only when the upstream artifact explicitly exports the field.
- Mark `derived` when it follows deterministically from inherited fields, and state the derivation.
- Mark `assumed` for illustrative or environment-dependent inputs; never attribute them to the upstream artifact.
- Preserve each inherited field's meaning, unit, scope, conditions, and source context.
- Treat inherited decisions as fixed unless the user explicitly reopens them. If an optimization needs to change one, hand back a requirement or candidate rather than silently changing it.
- Let the current layer decide only variables it owns. Label results that require downstream inputs as conditional derivations, not intrinsic current outputs.
- Support multiple downstream consumers. Name the fields each consumer receives, its missing inputs, and the owner of the eventual decision.

## Build the minimum dependency-complete chain

Run this section in Refine or a later requested phase. In Analyze, identify dependency gaps and scope problems, but do not deliver the rewritten question chain.

Prefer the fewest questions that preserve all prerequisite relationships, usually three to five. Do not force a fixed count or reuse a domain-specific chain blindly.

For each candidate question, define:

1. its input knowledge;
2. the concrete output it produces;
3. which later question consumes that output;
4. what adjacent topic it intentionally excludes;
5. who owns any decision it makes.

Remove a question when it duplicates another, supplies no downstream input, or belongs to a deferred layer. Add a question only when the later reasoning otherwise has a missing prerequisite.

Also remove a question when a prior learning artifact already supplies its output. Treat that artifact as an input to the current chain instead.

Keep closure proofs, examples, and acceptance checks outside the learning-question count. Promote one to a standalone question only when the user is explicitly learning validation methodology.

Read [references/decomposition-patterns.md](references/decomposition-patterns.md) when selecting angles for a new domain or when the initial questions mix abstraction layers.

## Prove closure before expanding detail

Confirm all of the following:

- the first question defines the object, state, or baseline used later;
- for a continuation, the first question consumes the inherited interface instead of redefining it;
- upstream exports and current imports have been reconciled field by field;
- every later question consumes a prior output;
- one end-to-end scenario can traverse the whole chain;
- the final state, decision, or observable result is explicit;
- deferred topics have named interfaces to the current scope;
- every current output and decision has an owner, and conditional results name their external inputs;
- all known downstream consumers and their required fields are named;
- each question has a short learning acceptance check.

If closure requires communication, computation, runtime, or another deferred layer, state that dependency instead of pretending the current scope can make the final decision.

## Answer each question consistently

Use this internal order, compressing headings when the answer is short:

1. **Definition** - say what the object or decision is and what it is not.
2. **Reason** - identify the constraint or problem that makes it relevant.
3. **Core logic** - give the minimum rules, state transition, formula, or decision tree.
4. **One example** - reuse the same representative example across the chain when possible.
5. **Boundary** - name what this question does not decide.
6. **Acceptance** - state what the learner should now be able to explain or calculate.

Distinguish:

- general definitions;
- source- or implementation-specific behavior;
- illustrative assumptions;
- unverified or environment-dependent claims.

For quantitative reasoning, declare the accounting basis, units, aggregation level, payment frequency, omitted terms, and whether a value is decomposed or observed end to end. Do not add decomposed components to a measured total that already includes them. Preserve the difference between logical quantities and physical work when the distinction affects the result.

When a flow can be described at several levels, distinguish logical endpoints, physical execution or data path, control path, and fallback path. Do not present a logical edge as proof of a specific physical implementation.

Read referenced papers, pages, code, or project documents before making precise claims. Prefer primary sources for technical behavior. Do not turn nominal capacity, peak bandwidth, defaults, or a paper's experiment into universal facts.

## Compress without breaking the chain

Preserve definitions, dependencies, decision rules, risks, boundaries, and the end-to-end example. Remove repeated explanation and secondary taxonomies.

Classify material before writing:

- **Core** - removing it prevents a question from producing its output or passing its acceptance check.
- **Advanced** - implementation variants, paper mappings, extra strategies, or quantitative detail not required for the base loop.

When the user requests a minimal or low-cost path, keep only core material in the main loop. Put requested advanced material after the closed core, clearly labeled, or omit it for later extension.

Choose the smallest useful representation:

- use a table for repeated fields, mappings, or comparisons;
- use a flowchart for state transitions, branching decisions, or multi-step dependencies;
- use a formula only when it enables a concrete calculation;
- use prose for a conclusion that needs no visual;
- prefer one end-to-end example over several unrelated examples.

Apply the essentiality test to every subsection, not only to top-level questions. Merge a prerequisite prelude into the first question, declare it as inherited input, or defer it.

Use one primary representation for each relationship: overview table or flowchart; example table or flowchart; prose, table, formula, or diagram within a question. Keep a second representation only when it performs a distinct teaching or validation function. Do not add diagrams merely to increase visual density. Keep a memory card only when the user wants review material.

## Create a Markdown guide only in Document phase

Read [assets/concise-learning-guide.md](assets/concise-learning-guide.md) before creating a new guide. Adapt its topology to the topic; do not copy unused sections.

When editing an existing guide:

- preserve its authoritative contract, working links, and useful source references;
- add the minimum structure needed for the approved learning chain;
- avoid rewriting unrelated sections;
- keep general facts separate from source-specific examples.

Before running structural validation, perform a semantic audit:

- reconcile inherited and newly introduced fields;
- verify that each decision belongs to the current layer or is explicitly handed off;
- label downstream-dependent results as conditional;
- retain units, aggregation level, assumptions, omitted terms, source type, and experiment or version conditions for exact claims;
- remove nonessential sections and duplicate representations;
- confirm that every named downstream consumer receives the fields it needs.

After writing, run:

```text
python scripts/validate_markdown.py <document.md>
```

Resolve the script path relative to this skill directory. If a full Mermaid renderer is unavailable, report that the source was structurally checked but not image-rendered.
Treat a successful script result as structural evidence only; it does not validate semantic boundaries, formulas, source support, or decision ownership.

## Extend with later sources

Before modifying the base guide, map each new finding:

| New finding | Existing question | Basic or advanced | Evidence type | Changes base conclusion? |
|---|---|---|---|---|

Append or revise only the affected layer. Keep advanced policies out of the minimal path unless they become prerequisites. If a later source contradicts the base, preserve the source boundary and explain why the conclusion changes.

## Guardrails

- Do not hard-code the KVCache "what is stored -> where it resides -> what happens under pressure" chain outside storage-residency topics.
- Do not reset the learning contract merely because the user moves to a new angle; preserve the original outcome and consume prior outputs.
- Do not silently add, mutate, or reattribute inherited fields; classify them as exact, derived, assumed, or missing.
- Do not let a current-layer strategy change an upstream-owned decision; return the required change to its owner.
- Do not report a downstream-dependent value as an intrinsic output of the current layer.
- Do not turn a successor layer into a standalone tutorial that no longer feeds the user's core objective.
- Do not turn the skill into a domain encyclopedia; keep evolving facts in project documents or source notes.
- Do not broaden "analyze" into implementation or document writes.
- Do not claim closure when the final decision depends on a deferred layer.
- Do not use exact numbers without units, scope, assumptions, and source context.
- Do not create README, changelog, or auxiliary files inside this skill.

## Bundled resources

- [references/decomposition-patterns.md](references/decomposition-patterns.md): choose a minimal question topology for common technical domains.
- [assets/concise-learning-guide.md](assets/concise-learning-guide.md): adapt a compact table-and-flow oriented Markdown skeleton.
- `scripts/validate_markdown.py`: run structural checks for UTF-8, fences, local links, Mermaid block structure, placeholders, and trailing whitespace; it intentionally does not certify semantic correctness.
