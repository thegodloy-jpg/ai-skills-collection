# Benchmark workbook specification

Use this reference when preparing input, running the generator, or validating its output.

## Input contract

The baseline CSV is required. The tuning CSV is optional and enables comparison mode. Filenames may use `-base`/`-tuning` or `-基线`/`-调优`; the generator relies on file contents rather than naming.

Required columns:

```text
scenario_name,input_length,output_length,max_concurrency,
request_throughput,output_token_throughput,total_token_throughput,
mean_ttft,p90_ttft,mean_tpot,p90_tpot
```

The generator detects comma, tab, or semicolon delimiters. It attempts strict UTF-8 first and falls back to the Windows ANSI code page (GBK on zh-CN) for invalid UTF-8 bytes.

Before execution, verify that required numeric fields parse as numbers and that at least one supported scenario is populated. Unknown scenario names are not rendered by the current script, so report them and stop unless the user explicitly approves their omission or the mapping is updated.

## Scenario mapping and SLA

Rows are sorted by `max_concurrency` inside each scenario block. Aliases `复杂任务` and `通用复杂任务` map to the same canonical scenario so baseline/tuning comparison remains aligned.

| CSV scenario or alias | Display label | Mean TPOT limit | Mean TTFT limit |
|---|---|---:|---:|
| `对话`, `中短对话` | 对话(2K/2K) - 中短对话 | 60 ms | 8 s |
| `通用复杂任务`, `复杂任务` | 通用复杂任务(8K/1K) - 较长输入 | 60 ms | 12 s |
| `合同分析` | 合同分析(16K/4K) - 长输入，中等输出 | 60 ms | 15 s |
| `Agent应用` | AI Coding/Agent（64K/1K）- 长输入，90% Prefix Cache命中率 | 120 ms | 30 s |
| `AI Coding` | AI Coding/Agent (128K/1K) - 超长输入，90% Prefix Cache命中率 | 120 ms | 30 s |
| `特长下行文` | 特长下行文 | no configured SLA | no configured SLA |
| `特长上下文` | 特长上下文（1M/1K）99% Prefix Cache命中率 | no configured SLA | no configured SLA |

For a configured SLA, highlight the highest-concurrency row whose mean TPOT and mean TTFT both pass. If no row passes, highlight the first/lowest-concurrency row. Scenarios without a configured SLA also highlight the first/lowest-concurrency row. The SLA fill color is `#50D092`.

## Column mapping

| Excel column | Content | CSV source or rule |
|---|---|---|
| A | Model | `-ModelName`; blank when not provided |
| B | Model parameters/quantization | blank unless a future explicit input is added |
| C | Hardware and card count | `-CardMachine`; blank when not provided |
| D-F | Hardware/software/parallelism details | blank; never inherit template defaults |
| G | Scenario | canonical display label |
| H | SLA | scenario SLA text |
| I | Acceleration feature | baseline `无`; tuning `KV稀疏,` + newline + `投机推理` |
| J | Concurrency | `max_concurrency` |
| K | Input length | `input_length` |
| L | Output length | `output_length` |
| M | Mean TTFT (s) | `mean_ttft / 1000` |
| N | P90 TTFT (s) | `p90_ttft / 1000` |
| O | Mean TPOT (ms) | `mean_tpot` |
| P | P90 TPOT (ms) | `p90_tpot` |
| Q | Per-request output throughput | `output_token_throughput / max_concurrency` |
| R | Total output throughput | `output_token_throughput` |
| S | Per-request E2E throughput | `total_token_throughput / max_concurrency` |
| T | Total E2E throughput | `total_token_throughput` |
| U | QPS | `request_throughput` |
| V | Notes | blank |
| W, tuning only | Baseline total throughput | baseline T value for the same canonical scenario and concurrency |
| X, tuning only | Improvement | `(tuning T - baseline T) / baseline T * 100`, formatted with two decimals |

When a tuning scenario/concurrency has no baseline match, W/X remain blank. Never compare rows only by position.

## Generator parameters

| Parameter | Required | Meaning |
|---|---:|---|
| `-OutputPath` | yes | New `.xlsx` destination |
| `-BaseCsv` | yes | Baseline CSV |
| `-TuningCsv` | no | Tuning CSV; omit for baseline-only |
| `-TemplatePath` | no | Compatible template workbook |
| `-CardMachine` | recommended | Hardware/card-count label written to column C |
| `-ModelName` | recommended | Full model name written to column A |
| `-SheetBaselineName` | yes | Baseline worksheet name |
| `-SheetTuningName` | comparison only | Tuning worksheet name |

Self-built comparison example:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  "<skill-dir>\scripts\build_perf_xlsx.ps1" `
  -OutputPath "D:\reports\H20+Model（基线+调优）性能数据-20260914.xlsx" `
  -BaseCsv "D:\data\benchmark-model-base.csv" `
  -TuningCsv "D:\data\benchmark-model-tuning.csv" `
  -CardMachine "H20 4机" `
  -ModelName "Model-FP8" `
  -SheetBaselineName "H20 4机+Model（基线）" `
  -SheetTuningName "H20 4机+Model（调优）"
```

## Template mode

Template mode currently expects worksheets named exactly:

```text
910C单机+DSV4-Flash-0731-w8a8(基线)
910C单机+DSV4-Flash-0731-w8a8(调优)
说明
```

Verify those names before using `-TemplatePath`. If they differ, prefer self-built mode or deliberately adapt the generator; do not let a template mismatch destroy a source workbook. Always write to a separate output path rather than modifying the template in place.

## Validation checklist

After generation, re-open the workbook and verify:

1. expected sheet count, names, and order, with no default blank sheets;
2. baseline header I1=`开源加速特性`, tuning I1=`Wings-infer 加速特性`;
3. baseline range ends at V and tuning range ends at X;
4. scenario rows and concurrency values match the source CSV;
5. M/N are TTFT milliseconds converted to seconds; O/P remain milliseconds;
6. Q/S are per-concurrency divisions and R/T are totals;
7. W/X match the same scenario+concurrency baseline row;
8. exactly one `#50D092` row per populated scenario block;
9. A-F contain only supplied/verified environment information;
10. every table cell has thin continuous black borders;
11. output opens without repair prompts and the script leaves no unexpected `EXCEL.EXE` process.

## PowerShell and Excel COM constraints

- Keep the script encoded as UTF-8 with BOM.
- Execute with Windows PowerShell 5.1 and `-ExecutionPolicy Bypass -File`.
- Use the script's `Cell` helper for variable-column access; `Cells.Item($row, $variableColumn)` can mis-bind under PowerShell 5.1 COM.
- Assign typed values directly to `.Value2`; indirect object-typed assignment can trigger conversion errors.
- Compute divisions before placing values into a PowerShell array literal.
- If the output workbook is locked, stop and report the lock instead of killing unrelated Excel sessions.
