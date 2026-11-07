# DAY0 schema

## Model registry

`catalog.yaml` is authoritative for routing. Every entry represents a base-model variant in one hardware scenario and contains:

- `id`: stable, scenario-qualified lowercase ASCII identifier.
- `base_model_id`: model/checkpoint variant without the hardware scenario.
- `scenario_id`: hardware platform and node-count scenario, such as `ascend-910c-dual-node`.
- `scenario_label`: human-facing scenario name.
- `display_name`: human-facing model and scenario name.
- `path`: workspace-relative model directory.
- `status`: normally `active` or `archived`.
- `aliases`: exact keys that identify this specific model and scenario.
- `base_aliases`: names or checkpoint paths that identify the base model but not its hardware scenario.

Scenario aliases are routing keys, not search patterns, and must be unique. Base aliases may be shared across scenarios; resolving one must return `SCENARIO_REQUIRED` and list candidates.

## Model directory

```text
模型/<base-model-id>-<hardware-scenario>/
|-- model.yaml
|-- state.yaml
|-- 基线/
|-- 实验/
|-- 故障/
`-- 报告/
```

Directory names are Chinese. Model IDs and record IDs are lowercase ASCII and must not be translated.

`state.yaml` contains reviewed pointers such as the accepted baseline. Record creation must not update those pointers automatically.

## Record directory

Every record has an immutable ID and the same evidence-oriented skeleton:

```text
<record-id>/
|-- manifest.yaml
|-- evidence-index.yaml
|-- 命令/
|-- 环境/
|-- 服务日志/
|-- 基准数据/
|-- 性能剖析/
|-- 分析/
`-- 参考资料/
```

The manifest records the scenario-qualified `model_id`, `record_id`, `kind`, title, creation time, status, parent baseline, and changed variables. Store image digests, checkpoint hashes, runtime versions, DP/TP/EP topology, launch parameters, workload, and evidence boundaries before comparing results.

## Legacy data

`legacy-sources.yaml` is a reference-only inventory. `assigned` means the identity is supported well enough to route future work; `pending` means the name is only a candidate. Registration does not authorize moving or deleting legacy content.
