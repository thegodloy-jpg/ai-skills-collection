# {{Technical topic}}: minimal learning loop

> Core outcome: {{stable capability across learning layers}}.
> Current-layer outcome: {{result produced by this guide}}.
> Scope: {{current layer}}. Deferred: {{adjacent layers}}.
> Inherited input: {{prior artifact or none}}.
> Downstream consumers: {{later decisions, learning layers, or final use}}.

Delete every unused line or section. All diagrams are optional. Use one primary representation for each relationship; do not present the same dependency, branch, or example as both a table and a diagram.

## Learning contract

Use this dependency table by default. Add or remove rows instead of forcing three questions. Replace it with one Mermaid diagram only when sequence or branching is materially clearer; do not keep both.

| Question | Consumes | Produces | Decision owner | Deferred boundary |
|---|---|---|---|---|
| {{Q1}} | {{prerequisite}} | {{artifact/state}} | {{owner}} | {{not answered here}} |
| {{Q2}} | {{Q1 output}} | {{artifact/state}} | {{owner}} | {{not answered here}} |
| {{Q3}} | {{Q2 output}} | {{decision/result}} | {{owner}} | {{not answered here}} |

For a continuation with nontrivial field handoff, keep this ledger internally. Include it in the guide only when readers need to audit the interface.

| Field | Upstream anchor | Status | Unit/condition | Current use | Owner |
|---|---|---|---|---|---|
| {{field}} | {{source location}} | exact / derived / assumed / missing | {{constraint}} | {{use}} | {{owner}} |

---

## {{N}}. {{Question}}

Repeat this section only for dependency-essential questions.

| Item | Core answer |
|---|---|
| Definition | {{what it is and is not}} |
| Constraint | {{why it matters}} |
| Core logic | {{minimum rule, state transition, formula, or decision}} |
| Boundary | {{what this question does not decide and who owns it}} |

```text
{{one compact formula or mapping only when it enables the question's output}}
```

**Acceptance:** {{one observable explanation, mapping, or calculation the learner can now perform}}.

---

## End-to-end example

Use one example across the chain. Prefer this table; replace it with one Mermaid diagram only when state transitions or branching are the lesson.

| Stage | Input/state | Decision/action | Output/state |
|---|---|---|---|
| 1 | {{...}} | {{...}} | {{...}} |
| 2 | {{...}} | {{...}} | {{...}} |
| 3 | {{...}} | {{...}} | {{...}} |

## Advanced or source-specific mapping

Keep this section only when the user requests implementation variants, paper details, extra strategies, or quantitative depth that is not required for the core loop.

| Finding | Core question | Why advanced | Source boundary |
|---|---|---|---|
| {{...}} | {{...}} | {{...}} | {{...}} |

## Downstream handoff

| Consumer | Fields handed off | Missing inputs | Decision owner |
|---|---|---|---|
| {{later topic or decision}} | {{current outputs}} | {{not produced here}} | {{owner}} |

## Sources

| Claim area | Claim type | Primary source | Scope or conditions |
|---|---|---|---|
| {{...}} | general / source-specific / illustrative / measured / inference | {{link}} | {{version, workload, assumptions, or experiment conditions}} |
