---
name: inference-benchmark-matrix
description: Run and validate controlled fixed-scenario A/B performance matrices for distributed LLM inference services with benchmark_new_v1.5.sh or compatible scripts. Use when comparing images, speculative-token counts, PLE/offload/cache features, or DP/TP/EP topologies while changing one variable at a time. Supports plan, dry-run, execution, evidence capture, and result validation; do not use it for SLA turning-point searches unless the user explicitly asks to leave Mode A.
---

# Inference Benchmark Matrix

Use **Mode A**: fixed workloads plus a causal experiment tree. Treat one `arm x scenario x repetition` as the smallest valid run.

Read [references/mode-a.md](references/mode-a.md) before planning an experiment. Read [references/execution-contract.md](references/execution-contract.md) before remote execution or validation. Use the bundled [benchmark_new_v1.5.sh](scripts/benchmark_new_v1.5.sh); do not log into a historical host merely to locate or fetch the benchmark script.

## Interpret the request

Classify the action as one of:

- `plan`: explain the matrix and required inputs; do not touch remote systems.
- `dry-run`: resolve commands, paths, variable deltas, and expected outputs; do not start or stop services.
- `run`: execute the requested arms and scenarios, monitor them, validate outputs, and return measured data.
- `analyze`: validate and compare existing results without launching workloads.

Do not reinterpret `--enable-speculative` in the benchmark script as enabling DSpark in the server. Server speculation belongs to the service arm; that benchmark flag only selects a benchmark dataset.

## Build the matrix

1. Freeze model files, engine image digest, driver/CANN, hosts, device topology, service arguments, sampling, benchmark script hash, and workload.
2. Give every arm an ID, parent arm, and exactly one intended variable delta. If an arm changes more than one causal variable, split it or label it `exploratory` instead of causal.
3. Pass every workload explicitly with `-c`; never rely on script defaults.
4. Default to the core-three suite unless the user supplies another whitelist:
   - `2k2k-c4`: `2048 2048 4 4 0.0`
   - `2k2k-c32`: `2048 2048 32 32 0.0`
   - `64k1k-c4`: `65536 1024 4 4 0.0`

## Execute

Only execute after the user selects `run` or otherwise explicitly asks to start testing.

1. Load the local Skill first. Resolve the experiment and use `script_path: "@bundled"`; target-machine discovery comes afterward.
2. Once the target is known, recheck host identity, service ownership, image digest, model path, base URL, free disk, and result root. Never embed passwords in the Skill, config, command history, or artifacts.
3. Stage `mode_a.py`, `benchmark_new_v1.5.sh`, and the resolved JSON together on the benchmark host. Verify the bundled script SHA256 after transfer. Do not replace the bundled script with a remote copy unless the user explicitly chooses a different script revision as an experiment variable.
4. If the service is already running and matches the arm, reuse it. If an arm requires a service change, start or restart it only from a user-supplied or already verified launch command. Never infer permission to reboot hosts, upgrade firmware, or replace drivers.
5. Require a real `/v1/models` response before a benchmark. A listening port alone is insufficient.
6. For cold-cache or shared-prefix runs, reset the prefix cache before every measured unit and require an explicit success response. Do not accept v1.5's fail-open behavior.
7. Use [scripts/mode_a.py](scripts/mode_a.py) on the benchmark host. Start with `plan`; invoke `run --allow-execute` only in run mode. The runner copies the bundled source into the run directory, strips its UTF-8 BOM from the runnable copy, records both hashes and commands, executes one scenario at a time, and validates `core_metrics.csv`.
8. Stream both benchmark and inference logs. Preserve each arm's resolved service command and time window so the matching engine log can be extracted.
9. Stop immediately on a health failure, cache-reset failure, benchmark nonzero exit, missing metrics, scenario mismatch, failed request, engine crash, or device/HCCL error. Mark the unit invalid; do not silently average it.

## Validate and report

Use the runner's `validate` command for existing results. Report measured results separately from configuration facts and hypotheses.

For every unit, include:

- arm, parent, intended delta, image digest, service-command hash, script source hash, and run timestamps;
- input/output length, prompt count, concurrency, prefix ratio, cache-reset status, and repetition;
- TTFT, TPOT, E2E, request throughput, output-token throughput, total-token throughput, and failed requests;
- paths to `manifest.json`, `runner.log`, `core_metrics.csv`, engine logs, and the generated `mode_a_summary.csv`;
- verdict: `VALID`, `INVALID`, or `INCOMPLETE`, with the exact reason.

Do not call a result faster merely from a single metric. Compare tail latency, throughput, stability, error signals, and output quality. Prefer at least three valid repetitions for final conclusions; one repetition is a smoke or directional result.

## Optional model profiles

Read a model profile only when that model is in scope. For a DeepSeek V4.1 two-host configuration example, use [references/deepseek-v41-a3.md](references/deepseek-v41-a3.md). The profile is illustrative, not public-machine measurement evidence; verify all configuration values before execution. Profiles contain no credential and do not grant authority to start services.
