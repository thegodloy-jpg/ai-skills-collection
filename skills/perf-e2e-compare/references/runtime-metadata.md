# 运行配置输入契约

在已有 `perf-e2e-compare` 或 `perf-benchmark` 工作簿上添加可追溯运行配置时使用。需要 Windows PowerShell 5.1 和 Microsoft Excel COM。脚本只向新输出工作簿添加 `运行配置` sheet，不改写输入工作簿；若源文件正在 Excel 中打开、输出已存在或已含同名 sheet，停止并保留现有内容。调用前人工去除密码、token、私钥、凭证及敏感连接信息；自动检查只拦截常见形式，不能替代人工检查。

JSON 使用 UTF-8。顶层 `records` 为非空数组，支持同一 `role` 的多条不同 `label`。每条包含：

| 字段 | 规则 |
|---|---|
| `role` | `baseline` 或 `tuning`；不从文件名猜测。 |
| `label` | 区分同角色不同配置，如 `historical`、`candidate`；同角色下不得重复。 |
| `evidence_status` | `observed` 表示该条信息有实际运行证据；`candidate` 表示候选、变更后或尚未验证。 |
| `source` | 已核验来源位置或明确的来源说明。 |
| `validation` | 实际验证范围或未验证说明，不得将静态检查写作运行通过。 |
| `software` | 可选对象；键值均为字符串，按已知事实分别填写操作系统、驱动、CUDA、Python、PyTorch、Transformers、引擎和镜像等；未知项省略。 |
| `environment` | 可选对象；键为环境变量名，值为字符串；禁止凭据。 |
| `startup_command` | 可选字符串；保留原文引号与换行，禁止凭据。 |

字段和每个值必须能装入单个 Excel 单元格（至多 32767 字符）；超长时停止，不截断。输入缺少环境变量或命令时应省略，不应推断缺失值。软件的 CUDA Toolkit、PyTorch 构建 CUDA 和驱动报告值应分开命名。一个命令只记录其实际来源；加入后续候选变量形成的新命令必须另列 `candidate`，并注明尚未进行对应组合的运行验证。

示例是结构说明，不是任何模型的默认配置：

```json
{
  "records": [
    {
      "role": "baseline",
      "label": "historical",
      "evidence_status": "observed",
      "source": "path/to/verified-original-launch",
      "validation": "Historical workload; actual service launch observed",
      "software": {"python": "3.12.3", "torch": "2.14.0+cu130"},
      "environment": {"VLLM_ALLOW_LONG_MAX_MODEL_LEN": "1"},
      "startup_command": "vllm serve /models/example --tensor-parallel-size 8"
    },
    {
      "role": "baseline",
      "label": "later-candidate",
      "evidence_status": "candidate",
      "source": "path/to/verified-candidate-config",
      "validation": "Candidate differs from historical baseline; full workload not validated",
      "environment": {"VLLM_ENABLE_CUDA_COMPATIBILITY": "1"}
    }
  ]
}
```

运行时提供三个不同的绝对路径：`-WorkbookPath`、`-MetadataPath`、`-OutputPath`。成功仅在 Excel COM 保存、重开、旧 sheet 公式和值、数字格式、填充颜色、边框、合并状态、工作簿计算设置以及新增 sheet 文本逐项回读通过、私有 Excel 进程退出后输出 `RUNTIME_METADATA_VALIDATION=PASS`。新配置以文本写入，避免将以 `=`、`+`、`-` 或 `@` 开头的内容当作公式；不得把测试数据塞进现有性能数据列。保留元数据 JSON 和校验日志，报告新工作簿绝对路径及 SHA-256。

Excel COM 可能在打开或保存某些 XLSX 后改变工作簿计算标记，例如带 `fullCalcOnLoad=1` 的文件；若原文件与保存副本的计算设置不一致，脚本会停止并不发布副本，原文件保持不变。此情况不能宣称通过，也不能静默忽略计算选项差异。对于独立服务验证，在新副本修复前需要另行确定如何保留工作簿设置。
