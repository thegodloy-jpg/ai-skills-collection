# 分散数据输入契约

仅在 Mode B（分散 CSV/XLSX 建表）中读取。

## 支持来源

- 单个或多个 `.csv`、`.xlsx`；目录输入会递归扫描。
- CSV 支持逗号、制表符或分号，编码依次尝试 UTF-8 BOM、UTF-8、GBK/CP936。
- XLSX 会扫描可见 sheet；`说明`等无性能表头的 sheet 会忽略。
- 自动忽略 Excel 锁文件 `~$*.xlsx`。
- 不自动解析日志、Markdown、PDF、图片或截图。

## 规范字段

生成器需要以下字段：

```text
scenario_name,input_length,output_length,max_concurrency,
request_throughput,output_token_throughput,total_token_throughput,
mean_ttft,p90_ttft,mean_tpot,p90_tpot
```

常见中英文表头会自动映射，例如“场景、输入长度、输出长度、并发、QPS、总输出吞吐、总 E2E 吞吐、Mean TTFT、TTFT P90、Mean TPOT、TPOT P90”。缺少必需字段时停止。

原生 benchmark CSV 的 TTFT 默认单位为毫秒。Excel 表头明确标记 `(s)` 或“秒”时转换为毫秒；标记 `(ms)` 或“毫秒”时保持不变。无法判断时使用 manifest 明确 `ttft_unit`，不要猜测。

## 角色识别

自动识别来源路径或 sheet 名中的：

- 基线：`baseline`、`base`、`基线`
- 调优：`tuning`、`tuned`、`optimized`、`调优`、`优化`

同时命中两种角色或完全无法识别时停止。使用 manifest 显式设置 `role`。

## 场景规则

支持性能报告中的标准场景及显示名：对话、通用复杂任务、合同分析、Agent 应用 64K、AI Coding 128K、特长下行文、特长上下文。合并单元格或空白场景会继承最近的非空场景值。

未知场景必须通过 manifest 的 `scenario_map` 映射到受支持场景。不要自行合并不同语义的场景。

## 重复与冲突

唯一键是 `role + scenario_name + max_concurrency`。

- 所有指标一致的重复行会去重并记录数量。
- 同一键的任一指标不同即为冲突，停止生成。
- 不使用最后一行覆盖、平均值、最近并发或插值解决冲突。

## Manifest 示例

JSON 中的相对路径优先相对于 manifest 所在目录解析，也可相对于 `-InputPath` 目录解析。

```json
{
  "scenario_map": {
    "短对话测试": "对话"
  },
  "sources": [
    {
      "path": "raw/base.xlsx",
      "sheet": "结果",
      "role": "baseline",
      "ttft_unit": "s",
      "columns": {
        "scenario_name": "业务场景",
        "max_concurrency": "并发数"
      }
    },
    {
      "path": "raw/tuning.csv",
      "role": "tuning",
      "scenario": "对话"
    }
  ]
}
```

`columns` 的键是规范字段名，值是来源表头。`scenario` 可为缺少场景列的整个来源指定固定场景。路径可包含 `*`、`?` 和 `**` 通配符。

## 中间证据

Mode B 在运行目录保留：

- `normalized/baseline.csv`
- `normalized/tuning.csv`
- `normalized/normalization-report.json`
- 生成并完成 E2E 校验的 staged 工作簿

`normalization-report.json` 必须记录发现、接受、忽略、未识别、冲突、去重和最终行数。失败时保留报告，不把部分数据包装成成功结果。
