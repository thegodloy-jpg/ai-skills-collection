# Root Cause Analysis: ${TITLE}

## 1. Conclusion Summary

- Incident status: `${STATUS}`
- Root-cause confidence: `${ROOT_CAUSE_CONFIDENCE}`
- Tested revision: `${TESTED_REVISION}`
- Current upstream revision: `${CURRENT_UPSTREAM_REVISION}`
- Current conclusion: ${CURRENT_CONCLUSION}
- Smallest useful next step: ${NEXT_STEP}

## 2. Scope and Evidence Boundary

State what was inspected or executed, the evidence time window, what changed, what remained fixed, and what was not verified.

## 3. Verified Facts

List direct observations with evidence IDs. Keep community statements, source inspection, controlled observations, inferences, and hypotheses distinct.

## 4. System Mechanism

Explain the relevant serving mechanism before discussing the failure. Cover ownership, lifetime, synchronization, communication, and cleanup where applicable.

## 5. Expected Execution Path

```text
request -> scheduler -> batch -> runner -> data preparation -> communication or transfer -> kernel -> completion -> cleanup
```

Replace the generic path with the actual revision-specific path.

## 6. Actual Failure Chain

Trace the first abnormal event through later errors. Do not mistake the location where an asynchronous error is reported for the operation that caused it.

## 7. Trigger and Non-trigger Conditions

| Dimension | Failing condition | Non-failing control | Interpretation |
|---|---|---|---|
| Feature or change | | | |
| Revision | | | |
| Topology | | | |
| Concurrency or shape | | | |

## 8. Competing Hypotheses

| ID | Mechanism hypothesis | Supporting evidence | Contradicting evidence | Prediction | Discriminating experiment | Status |
|---|---|---|---|---|---|---|
| H1 | | | | | | open |

## 9. Discriminating Experiments

For each experiment record the frozen variables, changed variable, support condition, falsification condition, result, and validity.

## 10. Root Cause Assessment

State `observed`, `associated`, `mechanism_supported`, or `confirmed`, and explain why the evidence meets that level and not the next one.

## 11. Fix Principle

- Invalid assumption:
- Broken invariant:
- Code or configuration change:
- New invariant:
- Why it prevents the failure:
- Why it is not merely masking the symptom:

## 12. Regression Validation

Include the original reproduction, negative control, repeated stability, correctness, performance, memory, compatibility, and rollback evidence.

## 13. Risks and Open Questions

List remaining uncertainty, untested revisions, unsupported topologies, performance costs, and evidence gaps.

## 14. Upstream Mapping

Record related documentation, Issues, PRs, duplicate-search outcome, and the exact tested-versus-current revision boundary. Keep publication optional until explicitly authorized.

## 15. Evidence Index

| ID | Type | Path or URL | Time or revision | Supports |
|---|---|---|---|---|
| E001 | | | | |
