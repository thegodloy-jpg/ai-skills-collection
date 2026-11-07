# Mode A: fixed-scenario causal benchmark

Mode A answers: **what changed, in which workload, by how much, and can the change be attributed to one variable?** It is not an automatic capacity search.

## Core-three workload suite

| ID | Input | Output | Prompts | Concurrency | Primary pressure |
|---|---:|---:|---:|---:|---|
| `2k2k-c4` | 2,048 | 2,048 | 4 | 4 | low-concurrency decode and single-request latency |
| `2k2k-c32` | 2,048 | 2,048 | 32 | 32 | scheduler, batching, decode throughput, tail latency |
| `64k1k-c4` | 65,536 | 1,024 | 4 | 4 | long-prefill, KV/cache pressure, TTFT |

Use prefix ratio `0.0` unless the experiment is explicitly about shared prefixes. Run each case with an explicit v1.5 combination:

```text
-c "2048 2048 4 4 0.0"
-c "2048 2048 32 32 0.0"
-c "65536 1024 4 4 0.0"
```

The number of prompts equals concurrency in this suite, so each client submits one measured request. Do not describe this as a saturation or capacity result.

## Causal arm design

```text
baseline
|
+-- candidate-1                              one intended variable changes
    |
    +-- candidate-2                          one additional intended variable changes
        |
        +-- candidate-2-branch-a             one branch variable changes
        +-- candidate-2-branch-b             a different branch variable changes
```

Every parent-child edge must declare its intended delta. If an image change necessarily changes bundled engine, CANN, or packages together, that edge measures the **whole image delta**, not one source patch. Record it honestly. Put model-specific arm names and values in that model's profile, not in this generic protocol.

## What each scenario can support

- `2k2k-c4`: direction of latency and speculative decode improvement. It does not prove high-load scalability.
- `2k2k-c32`: concurrency behavior, batching efficiency, throughput, and tail regression. It does not isolate prefill.
- `64k1k-c4`: long-context prefill and memory behavior. It does not prove one-million-token support.

For a release claim, run at least three valid repetitions per unit, report median and spread, and retain all raw runs. Use one repetition only for smoke testing or narrowing candidates.

## Cache policies

- `cold`: reset before every measured unit; use for ordinary fixed comparison.
- `shared-prefix-cold-start`: reset before the unit, then use a nonzero prefix ratio within that unit; use for prefix-cache features.
- `warm-reuse`: intentionally do not reset and document the warm-up/reuse sequence; never mix with cold data.

`VLLM_SERVER_DEV_MODE=1` only exposes development management endpoints. It does not itself clear the cache. Treat it as an experiment-only exposure and remove it from production-facing services.

## Attribution rules

Freeze all non-target variables. Invalid causal comparisons include:

- changing image and DSpark tokens together;
- enabling PLE while also changing DP/TP;
- comparing cold-cache data with warm-cache data;
- changing output length, prompt count, or concurrency between arms;
- calling the benchmark script's speed-bench dataset flag a server-side speculative setting;
- using a different script revision without treating the script as a variable.
