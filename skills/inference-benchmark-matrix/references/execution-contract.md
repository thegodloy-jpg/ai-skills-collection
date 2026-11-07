# Execution contract

## Configuration

Create a JSON file on the benchmark host. `mode_a.py` uses only the Python standard library.

```json
{
  "schema_version": 1,
  "experiment_id": "example-model-baseline-smoke",
  "arm": {
    "id": "baseline",
    "parent": null,
    "intended_delta": "baseline",
    "image": "registry.example/inference-engine:pinned-tag",
    "image_digest": "verify-before-run",
    "service_command_sha256": "verify-before-run"
  },
  "benchmark": {
    "script_path": "@bundled",
    "model_path": "/path/to/tokenizer-or-model",
    "model_name": "served-model-name",
    "base_url": "http://benchmark-target:8000/v1",
    "accelerator_type": "ascend",
    "temperature": 0,
    "result_root": "/var/ai-model/benchmark-results",
    "extra_args": []
  },
  "cache": {
    "policy": "cold",
    "strict": true
  },
  "repetitions": 1,
  "scenarios": [
    {"id": "2k2k-c4", "input_tokens": 2048, "output_tokens": 2048, "num_prompts": 4, "max_concurrency": 4, "prefix_rate": 0.0},
    {"id": "2k2k-c32", "input_tokens": 2048, "output_tokens": 2048, "num_prompts": 32, "max_concurrency": 32, "prefix_rate": 0.0},
    {"id": "64k1k-c4", "input_tokens": 65536, "output_tokens": 1024, "num_prompts": 4, "max_concurrency": 4, "prefix_rate": 0.0}
  ]
}
```

`@bundled` resolves to `benchmark_new_v1.5.sh` next to `mode_a.py`. This lets the Skill be loaded and planned before a target host is chosen. For a non-bundled revision, use an absolute path or a path relative to the JSON file and treat the script revision as an experimental variable.

Omit `script_sha256` while planning if it is not known. Resolve and add the real 64-character digest before `run`; never use a placeholder digest. The bundled v1.5 digest is recorded below.

Allowed cache policies are `cold`, `shared-prefix-cold-start`, and `warm-reuse`. A shared-prefix case must have `prefix_rate > 0`; ordinary cold and warm-reuse cases may use any declared prefix rate.

`benchmark.extra_args` must not contain `-M`, `--mode`, `-c`, `--combinations`, `-r`, `--result-dir`, or `--no-reset-prefix-cache`; the runner owns those controls. Add `--enable-speculative` only if the benchmark dataset itself must use `speed_bench`, not because the server uses DSpark.

## Commands

After choosing a benchmark host, copy these three local files into one staging directory on that host:

```text
scripts/mode_a.py
scripts/benchmark_new_v1.5.sh
<resolved experiment>.json
```

The staging directory is tooling, not result data. Prefer `/var/ai-model/benchmark-tools/inference-benchmark-matrix/<bundle-sha-prefix>/` when `/var/ai-model` is the requested physical-host storage. Verify the transferred benchmark script before execution:

```bash
sha256sum benchmark_new_v1.5.sh
# 2cf49c2656549569d7be41367564a6a8ea7237190cc9ae18917c8b18c4a947b1
```

Then run on the benchmark host:

```bash
python3 mode_a.py plan --config experiment.json
python3 mode_a.py run --config experiment.json --allow-execute
python3 mode_a.py validate --config experiment.json --result-dir /absolute/run/path
```

`plan` prints resolved per-unit commands and performs no write or network action. `run` creates a unique directory beneath `result_root/experiment_id/arm-id`, performs health/cache prechecks, executes every unit separately, and writes a normalized summary. `validate` scans an existing run directory without sending requests.

Do not access a previous test host to discover the benchmark script. The only remote access needed for a new invocation is target discovery/preflight, staging the bundled files, service control when authorized, and the actual benchmark.

## Required evidence before run

- both serving hosts, local IPs/NICs, and device counts;
- exact image reference and local image digest on every host;
- model path and an identity/checksum manifest if available;
- resolved service command for every host plus its SHA256;
- Python, vLLM/vllm-ascend, Transformers, torch/torch_npu, CANN, driver, firmware, OS, and Docker versions;
- benchmark script absolute path and SHA256;
- real `/v1/models` response;
- free space under the physical-host result root.

Record service logs independently because the benchmark runner does not own the distributed service lifecycle. Use a single clock/timezone and preserve an arm start/end marker to extract the correct log window.

## v1.5 behavior handled by the runner

- The Skill bundles a 52,039-byte public copy with documentation-only endpoint examples. Its SHA256 is `2cf49c2656549569d7be41367564a6a8ea7237190cc9ae18917c8b18c4a947b1`.
- Some copies have a UTF-8 BOM before the shebang. The runner copies the file into `inputs/`, strips the BOM from the copy, and records both source and runnable hashes.
- v1.5 defaults to five warm-up requests.
- A fixed combination is `input output prompts concurrency [prefix_rate]`.
- v1.5's internal prefix reset is fail-open. The runner calls the reset endpoint itself, requires `{"success": true}` in strict mode, then passes `--no-reset-prefix-cache` to prevent duplicate reset logic.
- v1.5 contains SLA turning-point behavior, but Mode A never adds `-M sla-turning-point`.

## Validity states

- `VALID`: command exit code is zero, reset policy was satisfied, a matching metrics row exists, and `failed_requests == 0`.
- `INVALID`: a run completed but violates reset, scenario, failure, or engine/device criteria.
- `INCOMPLETE`: process, file, or required evidence is missing.

Do not overwrite or merge an existing experiment directory. To retry missing or invalid units, first run `validate`, create a new config containing only that explicit scenario subset, give it a new experiment ID or retry label, and run it as a separate timestamped batch. Keep the original evidence intact.
