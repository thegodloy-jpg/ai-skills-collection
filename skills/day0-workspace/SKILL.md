---
name: day0-workspace
description: Resolve canonical base-model plus hardware-scenario identities and allocate durable record directories in F:\DAY0 for inference baselines, tuning experiments, benchmarks, profiles, logs, RCA cases, reports, and image-release evidence across conversations. Use before creating model-related artifacts; do not use it to run deployments, benchmarks, RCA analysis, or image release itself.
---

# DAY0 Workspace

Use `F:\DAY0` as the default durable source of truth; override it with `--workspace-root` or `DAY0_WORKSPACE_ROOT` for your environment. Addresses in examples are RFC 5737 documentation addresses and must be replaced with user-verified hosts. Conversation memory is only a navigation aid and must not replace the manifests on disk.

## Workflow

1. Resolve the model before writing anything:

```powershell
python scripts/day0ctl.py resolve --model "<model-id, alias, or checkpoint path>"
```

2. Resolve both the base model and hardware scenario. A base-model-only query returns `SCENARIO_REQUIRED`, even when only one scenario is currently registered. Missing or ambiguous resolution is a stop condition; do not guess or silently select a scenario.
3. When the user explicitly authorizes a new composite registration, use `register-model` with a scenario-qualified lowercase ASCII ID, `base_model_id`, `scenario_id`, and exact scenario aliases.
4. Allocate each body of work with `create-record`; then let the relevant specialist skill or workflow write into the returned directory.
5. Register external or already-existing evidence with `attach`. This records a reference; it does not copy or mutate the source.
6. Run `validate` after structural changes and before treating a record as durable evidence.

## Identity and storage rules

- A model workspace identity is `base model/checkpoint variant + hardware platform/node-count scenario`. Quantization variants normally use separate base IDs. Use distinct directories for 910C dual-node, 910C single-node, and 910B scenarios.
- Image, engine version, CANN, DP/TP/EP topology, speculative-token count, offload flags, and workload belong in record manifests rather than new model directories.
- Accept only exact normalized scenario matches against `id`, `display_name`, registered aliases, or a registered scenario path. Base aliases only identify candidate scenarios and must not select one. Never use broad regular expressions for routing.
- Store accepted configurations under `基线/`, controlled changes under `实验/`, failures and RCA under `故障/`, and cross-run deliverables under `报告/`. All workspace layout directory names are Chinese; model IDs and record IDs stay lowercase ASCII.
- A newly allocated record has status `collecting`. Creation does not promote an experiment to an accepted baseline.
- Do not move or delete paths in `legacy-sources.yaml`. Link them as evidence until migration is explicitly requested.
- Do not store credentials. Reference large artifacts instead of duplicating them by default.

## Commands

```powershell
# List registered models
python scripts/day0ctl.py status

# Resolve an explicit model and hardware scenario across conversations
python scripts/day0ctl.py resolve --model deepseek-v41-910c-dual

# Allocate a controlled experiment
python scripts/day0ctl.py create-record `
  --model deepseek-v41-910c-dual `
  --kind experiment `
  --slug dspark6-ple-on `
  --title "DSpark 6 with Engram PLE" `
  --changed-variable "enable_engram_ple_offload=true"

# Register an existing log without copying it
python scripts/day0ctl.py attach `
  --record-dir "<allocated-record-dir>" `
  --artifact "192.0.2.252:/var/ai-model/logs/engine.log" `
  --role service-log

# Validate the workspace
python scripts/day0ctl.py validate
```

Read [references/schema.md](references/schema.md) only when registering a model, interpreting manifests, or extending the directory schema.
