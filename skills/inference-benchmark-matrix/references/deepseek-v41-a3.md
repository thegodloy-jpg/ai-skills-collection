# DeepSeek V4.1 A3 configuration example

This profile is a configuration example using RFC 5737 documentation addresses, not evidence measured on a public machine. Verify all hosts, paths, topology, images, and launch settings in the user's environment before a new run.

## Serving topology

- master: `192.0.2.252`, service endpoint `http://192.0.2.252:8000/v1`
- worker: `192.0.2.253`
- baseline topology: two hosts, `DP=4`, `DP local=2`, `TP=8`, expert parallel enabled
- baseline model name: `deepseek-v41`
- weights: `/var/ai-model/DeepSeek-V4.1-Flash-w8a8`
- physical-host result root: `/var/ai-model/benchmark-results`

Do not store the SSH password in a profile or artifact.

## Bundled benchmark v1.5 provenance

The Skill now contains:

```text
scripts/benchmark_new_v1.5.sh
```

Bundled public-copy SHA256:

```text
2cf49c2656549569d7be41367564a6a8ea7237190cc9ae18917c8b18c4a947b1
```

This 52,039-byte public copy is bundled locally with documentation-only endpoint examples. An illustrative source reference would be `example-benchmark-host:/path/to/benchmark_new_v1.5.sh`; it is not a required or verified remote location. The file has a UTF-8 BOM before the shebang, which the runner removes only from its per-run copy. Use `script_path: "@bundled"`; no historical host or path is needed.

## Root baseline A5

- image: `quay.io/ascend/vllm-ascend:deepseek-v4.1-flash-a3`; pin and record the current local digest
- DSpark speculative tokens: `5`
- PLE offload: off
- IndexCache: no added experiment override
- topology: `DP4/TP8`, expert parallel
- `VLLM_SERVER_DEV_MODE=1` is required only while strict prefix-reset testing is active

The launch command must retain the previously verified model-specific flags, including DeepSeek V4.1 tokenizer/reasoning/tool parsers, Ascend quantization, Engram, MC2 hierarchy configuration, compilation settings, and the correct master/worker data-parallel ranks. Reconstructing a launch command from this short profile is not allowed; use the full verified scripts or an archived resolved command.

## Recommended execution order

1. `A5` core-three, first as one repetition smoke, then three repetitions if valid.
2. `A6` with only DSpark tokens changed from 5 to 6.
3. `B6` with only the candidate image/build changed from A6.
4. `C6` with only `enable_engram_ple_offload=true` changed from B6.
5. Branch IndexCache and topology experiments only after C6 is stable.

The corresponding causal tree is:

```text
A5 official image, DSpark=5, PLE=off, DP4/TP8
|
+-- A6 official image, DSpark=6                   only DSpark token count changes
    |
    +-- B6 candidate image, DSpark=6, PLE=off     only image/build changes
        |
        +-- C6 candidate image, DSpark=6, PLE=on  only PLE changes
            |
            +-- C6-index4                          only IndexCache=4 changes
            +-- C6-index8                          only IndexCache=8 changes
            +-- C6-dp8-tp4                        only topology changes
            +-- C6-dp2-tp16                       only topology changes
```

Do not compare historical rows unless script hash, service configuration, cache policy, scenario tuple, and environment identity are compatible.
