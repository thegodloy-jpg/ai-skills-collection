---
name: perf-e2e-compare
description: 汇总分散的 benchmark CSV/XLSX 或修复现有大模型性能 Excel：规范化基线/调优数据，校验 E2E 总吞吐，并按场景和并发写入基线总 TPS 与提升比。适用于分散数据建表和已有工作簿对比；不解析非结构化日志、PDF 或截图。
metadata:
  short-description: 分散性能数据建表与 E2E 吞吐对比
---

# 性能数据建表与 E2E 对比

把结构化但分散的性能数据生成规范 Excel，或对已有 `.xlsx` 工作簿做可追溯的基线/调优 E2E 对比。此 Skill 只处理本地文件，不运行推理服务或性能测试。

## 选择模式

- **Mode A：已有工作簿修复。** 用户已经有包含基线、调优 sheet 的性能 `.xlsx`，需要校验总 E2E、补充同并发基线和提升比。读取 [references/workbook-contract.md](references/workbook-contract.md)，使用 `scripts/update_e2e_compare.ps1`。
- **Mode B：分散数据建表。** 输入是一个或多个 CSV/XLSX，可能分布在目录或多个 sheet。读取 [references/scattered-input-contract.md](references/scattered-input-contract.md)，使用 `scripts/build_scattered_perf_xlsx.ps1`。该模式会调用同机已安装的 `perf-benchmark` 生成器，再执行 Mode A 的最终校验。
- **Mode C：单组性能汇总。** 只有一组可用的结构化测点且没有对照时，用 `perf-benchmark` 的单组入口生成表格；表名按实际证据状态命名，不把实验自动称为接受基线，不计算提升比。该模式不是 Mode B 的双角色比较。

日志、PDF、截图或无法识别字段的任意表格不属于自动处理范围。需要先添加专用解析器或由用户确认映射，不能静默猜测。

## 共同约束

- 使用 Windows PowerShell 5.1 和 Microsoft Excel COM。目标文件被打开或锁定时停止，不关闭或覆盖用户的 Excel 会话。
- 仅使用用户提供或已验证的模型、硬件和环境值；不从模板继承陈旧信息。
- 仅按“规范化场景名 + 完全相同的并发”匹配。不要按行号、邻近并发或场景极限值替代。
- 无同并发基线的调优行，其 W/X 保持空白。
- 修改已有文件前创建带时间戳的备份。优先生成新输出；只有用户明确选择原路径时才覆盖。
- 此结果只证明数据整理、工作簿计算和匹配一致，不证明 benchmark 已完整运行、服务性能有效或模型准确率达标。
- 已有可靠的软件版本、环境变量或启动命令时，按运行角色和证据状态记录到工作簿；缺失项留空，不从模板或示例补造。历史实测配置和后续候选配置不得混写为一次已验证运行。

## Mode A：已有工作簿

1. 只读检查路径、锁状态、sheet 名称、行列范围，以及 G/J/S/T/V/W/X 列现状。
2. 明确唯一的基线和调优 sheet。缺失或重名时报告候选项，不猜测。
3. 运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  "<skill-dir>\scripts\update_e2e_compare.ps1" `
  -WorkbookPath "<workbook.xlsx>" `
  -BaselineSheetName "<baseline sheet>" `
  -TuningSheetName "<tuning sheet>" `
  -BaselineHeader "同并发基线 E2E 总吞吐 (tps)" `
  -RatioHeader "E2E 总吞吐提升比 (调优-基线)/基线"
```

V 列默认视为备注并保留。只有只读检查确认 V 全部是误放的数值对比数据时，才追加 `-ClearMisplacedComparisonFromNotes`。

## Mode B：分散 CSV/XLSX 建表

1. 先做只读清单：文件、sheet、表头、编码、分隔符、角色候选、单位、场景和并发。
2. 能从文件名、目录名或 sheet 名唯一识别 `baseline/base/基线` 与 `tuning/tuned/optimized/调优/优化` 时可自动分类；否则创建 manifest，由用户或已有事实明确映射。
3. 输出路径属于模型性能证据时，先使用 `day0-workspace` 解析模型和硬件场景并分配记录目录。
4. 运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  "<skill-dir>\scripts\build_scattered_perf_xlsx.ps1" `
  -InputPath "<file-or-directory>" `
  -OutputPath "<new-report.xlsx>" `
  -ModelName "<verified model name>" `
  -CardMachine "<verified hardware/card count>" `
  -BaselineSheetName "<baseline sheet>" `
  -TuningSheetName "<tuning sheet>" `
  -BaselineHeader "同并发基线 E2E 总吞吐 (tps)" `
  -RatioHeader "E2E 总吞吐提升比 (调优-基线)/基线"
```

字段、角色、单位、场景别名或重复数据存在歧义时，增加 `-ManifestPath "<manifest.json>"`。不要为了让流程通过而忽略未识别来源或冲突行。

生成器的特性名、前缀描述和 SLA 是模板内容，不能当成本次实测事实；发布前核对并用已核验内容修正，不支持的内容应清空或明确标注未知。

## Mode C：单组性能汇总

核对单组 CSV 的场景、并发、字段和单位，读取并遵循本机 `perf-benchmark` 的 `SKILL.md` 和报告契约。调用其 `build_perf_xlsx.ps1` 时，`-BaseCsv` 是单组输入的技术参数，不表示该数据已被接受为基线；`-SheetBaselineName` 应使用能反映实际状态的名称。缺少必需字段或存在未知场景时停止，不能从其他分位数、不同场景或日志猜测。用户只给了一组时不得复制成两组来生成提升比。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  "<skills-root>\perf-benchmark\scripts\build_perf_xlsx.ps1" `
  -OutputPath "<new-report.xlsx>" -BaseCsv "<verified-single-run.csv>" `
  -ModelName "<verified model name>" -CardMachine "<verified hardware/card count>" `
  -SheetBaselineName "<single-run sheet name>"
```

输出需通过生成器 `OK:`、Excel COM 重开、原始测点与指标逐行核对、E2E 总吞吐与 `T = S × J` 核验，并检查实际场景的 SLA 与可视格式；不得报告 Mode B 的 `BUILD_VALIDATION=PASS` 或基线/调优匹配数。其后可使用下述表内展示步骤修正生成器模板的特性、SLA 和前缀描述。优先明确标注这是单次测量而非经过比较的调优收益。

## 表内展示格式

当用户要求按性能表展示硬件、软件与启动命令、并行策略、SLA 或加速特性时，在完成数据整理或对比后，读取 [表内展示契约](references/workbook-presentation.md)，以已核验的信息和每个 sheet 的实际场景构造 JSON，再调用 `scripts/format_workbook_presentation.ps1` 生成独立副本。E 列可在实际命令前使用多行展示有证据的软件版本；字段、来源和时间口径按契约核对。H 列按场景分行展示 TPOT 和 TTFT，I 列填写明确指定的特性名称；相同并行配置不要重复追加。用户示例是布局参考，不是其他模型的默认值。

只在提供成对、明确的 SLA 上限和经原始证据核实的合格并发列表时重算该场景高亮；展示的近似范围下限不是实测下限。配置的前缀比例不等于缓存命中率。只有用户明确指定或有证据支持时才标记 `SmartDecoding`，不要把所有 DSpark 自动等同于已验证的 Wings 集成。分别保留各运行的来源和证据状态，不能把未验证的新镜像写成历史测量环境。缺失信息留空或保留原值，不虚构。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  "<skill-dir>\scripts\format_workbook_presentation.ps1" `
  -WorkbookPath "<existing-report.xlsx>" `
  -PresentationPath "<verified-presentation.json>" `
  -OutputPath "<new-report-with-presentation.xlsx>"
```

独立格式步骤以 `PRESENTATION_VALIDATION=PASS` 和输出 SHA-256 为完成依据；它不替代 Mode A/B 的对比校验。输入被锁定或输出已存在时停止，保留原工作簿与其他 Excel 会话。

## 运行配置记录

Mode A 或 Mode B 处理完成后，可使用 [运行配置契约](references/runtime-metadata.md) 将已知配置加入**新的**工作簿副本；此步骤不改变原有模式的输入和完成条件。`records` 可分别记录基线、调优以及相同角色下不同证据状态，基线-only 工作簿也可使用。该脚本的角色仅支持 baseline/tuning；Mode C 的单次实验若不属于这两种角色，不得为使用脚本而错误标记为基线，应在说明页或表内记录真实状态和来源。读取并核实每条信息的来源，未知信息不填写；启动命令按原文保留换行和引号，不把历史基线和未验证的新变量合成实测命令。不得写入密钥、密码或 token。

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  "<skill-dir>\scripts\write_runtime_metadata.ps1" `
  -WorkbookPath "<existing-report.xlsx>" `
  -MetadataPath "<verified-runtime-metadata.json>" `
  -OutputPath "<new-report-with-runtime-config.xlsx>"
```

输入文件被锁、输出文件已存在或已有 `运行配置` sheet 时停止，不覆盖。脚本应返回 `RUNTIME_METADATA_VALIDATION=PASS` 和新文件 SHA-256；它只验证内容及表结构，不证明启动命令或服务已实际运行。记录输入 JSON 和验证输出的证据路径；保护用户既有 Excel 会话。

## 完成条件

- Mode A 必须返回 `SAVED=...` 和 `VALIDATION=PASS`。
- Mode B 必须返回 `NORMALIZATION=PASS`、生成器的 `OK: ...`、E2E 的 `VALIDATION=PASS` 以及 `BUILD_VALIDATION=PASS`。
- Mode C 必须返回生成器 `OK:`，并完成源数据、E2E 和格式的独立回读验证；不报告未执行的 Mode B 标记。
- 无额外 Excel 进程或目标锁文件；最终文件可由 Excel COM 重新打开。
- 报告绝对文件路径、实际 sheet、规范化行数、匹配数、无匹配数、未识别/冲突状态、备份路径、证据目录和最终 SHA-256。
