---
name: perf-benchmark
description: Generate a formatted Excel performance-summary workbook from native benchmark CSV files, for either baseline-only or baseline-versus-tuning results. Use for benchmark/performance reports involving concurrency, TTFT, TPOT, throughput, QPS, SLA highlighting, or tuning improvement; do not use for unrelated spreadsheets, PDFs, or Google Docs.
metadata:
  short-description: Generate benchmark Excel performance reports
  source-version: "2026.8.25"
---

# Performance Benchmark Report

Turn native benchmark CSV results into a consistent `.xlsx` report with scenario blocks, SLA highlighting, and optional baseline-versus-tuning comparisons.

## Execution boundary

- This skill creates or validates local Excel workbooks. It does not run inference services or benchmarks unless the user separately requests that work.
- Do not overwrite an existing workbook unless the user explicitly selected that path for replacement. Prefer a new output path.
- Use only actual user-provided or verified environment values. Do not inherit stale model, hardware, software, or parallelism text from a template.

## Required environment

- Windows with Windows PowerShell 5.1 (`powershell.exe`).
- Microsoft Excel installed and available through COM.
- No conflicting Excel process or workbook lock on the output path.

The generator is [scripts/build_perf_xlsx.ps1](scripts/build_perf_xlsx.ps1). It must remain UTF-8 with BOM because it contains Chinese PowerShell literals.

## Workflow

Before generating a workbook, read [references/report-spec.md](references/report-spec.md) completely.

1. Resolve the model name, hardware/card-count label, mode (`baseline` or `baseline+tuning`), base CSV, optional tuning CSV, optional template, and output path. Ask only for values that cannot be inferred safely.
2. Inspect the CSV headers, delimiter, encoding, scenarios, concurrency values, and numeric fields. Reject an empty CSV, missing required fields, or a dataset with no recognized scenario instead of emitting a misleading workbook.
3. Use self-built mode unless the user supplies a compatible template and explicitly wants its exact layout.
4. Choose worksheet names of at most 31 characters. Use recognizable abbreviations without changing the full model value written into the report.
5. Run the script through Windows PowerShell 5.1:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<skill>\scripts\build_perf_xlsx.ps1" `
  -OutputPath "<output.xlsx>" `
  -BaseCsv "<baseline.csv>" `
  -TuningCsv "<tuning.csv>" `
  -CardMachine "<hardware and card count>" `
  -ModelName "<full model name>" `
  -SheetBaselineName "<baseline sheet name>" `
  -SheetTuningName "<tuning sheet name>"
```

For baseline-only mode, omit `-TuningCsv` and `-SheetTuningName`. Add `-TemplatePath` only for a verified compatible template.

6. Capture the script exit code and the `OK: <path>` line. A created file alone is not completion evidence.
7. Re-open the workbook with Excel COM and validate sheet order, used ranges, headers, formulas/values, SLA-highlight count, comparison columns, borders, and absence of unintended blank sheets. Report the final absolute path.

## Output invariants

- Self-built baseline-only: `说明`, then `基线`.
- Self-built comparison: `说明`, then `调优`, then `基线`.
- Baseline sheet ends at column V (22); tuning ends at X (24).
- Tuning columns W/X contain matched baseline total throughput and improvement percentage.
- Each populated scenario block has exactly one SLA-highlighted row.
- The full table has thin continuous black cell borders.
- Long worksheet names are sanitized and shortened to Excel's 31-character limit.

Do not claim success if Excel COM remains running unexpectedly, workbook validation fails, required data was ignored, or the output is only partially written.
