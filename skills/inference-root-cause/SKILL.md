---
name: inference-root-cause
description: Analyze inference-engine startup, runtime, correctness, stability, and performance failures by reconstructing execution paths, separating symptoms from causes, ranking competing hypotheses, and designing discriminating experiments. Use when the user asks for root cause, failure mechanism, fix rationale, a technical RCA report, or evidence-backed upstream Issue or PR material; do not use for routine deployment, log viewing, benchmarking, or image release.
---

# Inference Root Cause

Explain why an inference failure occurs and why a proposed fix works. Treat reports and upstream submissions as outputs of the root-cause analysis, not as substitutes for it.

## Scope and authority

- Default to analysis of evidence already in scope.
- Treat "analysis only" as prohibiting SSH, remote collection, service changes, builds, benchmark reruns, file edits, and GitHub writes.
- A request to diagnose does not authorize implementation. A request to draft does not authorize publication.
- Require current explicit authorization immediately before remote mutation, benchmark execution, code changes, or GitHub Issue, comment, or PR creation.
- Never store passwords, tokens, private keys, or long-lived credentials in a case, report, script, or command history.

## Two phases

### RCA

Use RCA by default. Reconstruct the mechanism, maintain competing hypotheses, design discriminating experiments, assess the root-cause confidence, and explain the fix principle.

### Upstream

Use only when the user asks to search, draft, publish, or follow up upstream. Derive the public artifact from the RCA, redact it, search open and closed Issues and PRs, and preserve the tested-revision boundary.

## Workspace output

- When the user supplies a workspace root, store generated artifacts under `<workspace-root>/模型/<model-slug>/故障/<case-id>/`. The public default for `DAY0` or "the DAY0 workspace" is `F:\DAY0`; set `--workspace-root` to use another environment. Workspace layout directory names are Chinese; model slugs and case IDs stay lowercase ASCII.
- Keep accepted reference configurations under `基线/`, controlled tuning work under `实验/`, RCA cases under `故障/`, and cross-run summaries under `报告/`. An experiment control is not automatically an accepted model baseline.
- Use lowercase ASCII slugs. Use immutable IDs such as `b001-*`, `e001-*`, and `inc-YYYYMMDD-*`; record success, failure, and confidence in manifests rather than directory names.
- Do not duplicate model weights, image archives, large profiler traces, or full benchmark trees into an incident. Preserve them in their canonical location and record relative paths plus hashes in `evidence-index.yaml`. Copy only small critical excerpts and public redactions into the case.
- Before initializing a case, resolve and verify that the final path stays below the requested workspace. Never overwrite an existing non-empty case directory. Use [scripts/init_case.py](scripts/init_case.py) for deterministic scaffolding, then fill the templates and run the evidence checker. Register the case in the model index only after the case and report pass validation; creation alone does not make it accepted evidence.

```bash
python scripts/init_case.py \
  --workspace-root 'F:\DAY0' \
  --model-slug deepseek-v4.1-flash-w8a8 \
  --case-id inc-20260918-engram-ple-507011 \
  --title 'DeepSeek V4.1 Engram PLE 507011'
```

## RCA workflow

1. **Freeze the claim boundary.** Record the model, hardware, topology, image digest, engine and dependency versions, launch configuration, workload, tested revision, current upstream revision, and evidence time window. Re-verify drift-prone facts when practical.
2. **Separate failure levels.** Distinguish symptom, first observed failing operation, low-level error, trigger, correlated variable, mechanism hypothesis, root cause, workaround, and fix. An error code, concurrency threshold, or feature flag is not itself a root cause.
3. **Reconstruct the execution path.** Follow the request through scheduling, batching, model runner, data preparation, memory ownership, communication, kernels, streams or events, completion, cleanup, and error propagation. For asynchronous or offload paths, explicitly trace allocate, register or map, populate, enqueue, synchronize, reuse, unregister, and free.
4. **Build competing hypotheses.** For each hypothesis record supporting evidence, contradicting evidence, missing evidence, predicted observations, and the smallest experiment that distinguishes it from alternatives. Rank hypotheses; do not select one because it merely fits a single log line.
5. **Design discriminating experiments.** Freeze unrelated variables and change one causal variable. Prefer a small revision, feature, synchronization, topology, or interaction ablation over a large performance matrix. State what result would support and falsify each hypothesis before execution.
6. **Assess confidence.** Use `observed`, `associated`, `mechanism_supported`, or `confirmed`. Confirm a root cause only when a concrete mechanism explains the evidence and trigger, competing explanations have been materially reduced, and a mechanism-directed fix passes the original reproduction plus a negative control.
7. **Explain the fix principle.** State the invalid assumption, the broken invariant, the new invariant established by the fix, why the failure is prevented, and expected correctness, performance, memory, compatibility, and rollback effects. Disabling a feature or lowering concurrency is normally a workaround, not a fix.
8. **Produce an artifact.** Use [assets/case-template.yaml](assets/case-template.yaml) for structured facts and [assets/root-cause-report-template.md](assets/root-cause-report-template.md) for a detailed RCA. A compact answer may omit empty report sections, but it must retain the evidence boundary and confidence level.

## Evidence rules

- Keep complete, partial, failed, and live results separate.
- A running container, HTTP 200, benchmark exit code 0, or successful model load does not prove request success, correctness, long-context support, or stability. Inspect actual request counts, failures, outputs, process state, and relevant logs.
- Keep a controlled baseline and variant. If more than one meaningful variable differs, describe the result as end-to-end comparison rather than causal attribution.
- Bind every mechanism claim to the exact tested revision. Do not apply an old failure to a force-pushed or rewritten head without retesting.
- Split distinct symptoms into separate causal trees. A crash and a decode regression may share a feature path without sharing one root cause.
- Preserve raw evidence. Create redacted derivatives for public use rather than rewriting the originals.
- Label community documentation, source inspection, target-environment observation, controlled experiment, inference, and hypothesis separately.

## Report and upstream routing

- Produce a detailed report when the incident is cross-node, destructive, recurrent, performance-sensitive, intended for upstream, or explicitly requested. Otherwise provide a compact RCA with the same confidence discipline.
- If an exact upstream Issue exists, prepare a focused evidence comment instead of a duplicate.
- If the problem is reproducible but the mechanism is unresolved, prepare an Issue.
- If the mechanism and code fix are validated on the current head, prepare a PR and link the Issue. Use `Fixes` only when the patch fully resolves the reported problem; otherwise use `Related to`.
- If the outcome is a configuration correction or workaround, record it as such and do not present it as an upstream code fix.
- Before public output, run the evidence checker in public mode and inspect every warning:

```bash
python scripts/check_evidence.py --case path/to/case.yaml --report path/to/report.md --public
```

The checker is a guardrail, not proof that the RCA is correct.

## Stop conditions

Stop and report the exact blocker when required evidence, access, authorization, a reproducible control, or the tested source revision is unavailable. Do not manufacture a root cause to complete the report. Give the smallest next observation or experiment that would materially change the diagnosis.
