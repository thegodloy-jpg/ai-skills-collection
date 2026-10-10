---
name: connect-claude-code-api
description: "将外部模型 API 接入 Claude Code CLI 或 VS Code 官方扩展，核对 Anthropic 协议兼容性，配置真实模型映射和 /model 标签，备份并验证调用。用于接入、切换提供商或修复模型标签与实际调用不一致的问题。"
---

# Claude Code 外部 API 接入

让 Claude Code 的原生客户端通过提供商的 Anthropic 兼容入口调用外部模型。保持用户选定的提供商、使用范围和默认模型偏好。

## 确认有效运行路径

- 区分 VS Code 官方扩展 `anthropic.claude-code`、终端 CLI 和其他名称相近的扩展；按用户实际使用的入口操作。
- 检查扩展/CLI 版本、实际可执行文件、用户配置、VS Code 用户数据目录和活动 profile。终端 `claude` 可能是设置路由变量的 `.cmd`、shell shim 或本地代理；官方扩展通常使用自带二进制，不能仅凭 `Get-Command claude` 推断扩展的路径。
- 配置目录默认是 `~/.claude`，同时检查 `CLAUDE_CONFIG_DIR`。共享配置通常在其中的 `settings.json`；还要检查适用的项目配置、托管配置、扩展环境变量和 `claudeProcessWrapper` 是否覆盖结果。
- 仅输出脱敏后的配置摘要。不要在查找安装位置时打印完整设置、进程环境、凭据或整段日志。

## 核对协议和真实模型

查询提供商当前官方文档，确认 Anthropic Messages 兼容入口、鉴权方式、可用模型 ID、上下文长度和能力。能查询模型列表时，用一次只读请求核对当前 Key 可用的模型；模型列表本身不能证明思考、视觉或工具调用能力。

- `ANTHROPIC_BASE_URL` 填兼容接口的 base URL，由客户端追加 Messages 路径。不要把普通 OpenAI `/v1` 入口或完整 `/messages` 路径当作兼容 base URL。
- 仅支持 OpenAI 协议的提供商需要协议适配。先复用已安装的路由器、提供商官方兼容入口或现有代理；没有可用适配时说明缺少的组件，在当前任务范围内推进必要的适配工作，不能把改 URL 当作转换完成。
- 确认 Bearer token 与 `x-api-key` 的具体支持情况。选择对应的 `ANTHROPIC_AUTH_TOKEN` 或 `ANTHROPIC_API_KEY`，检查旧凭据冲突；不要清除用户原来的 OAuth 登录数据。
- 用于接入的授权延续到必要的可逆配置工作。仅生成方案或明确要求只分析时保持只读。

接入 DeepSeek 时，阅读 [DeepSeek 参考](references/deepseek.md)。其他提供商按其自己的官方规格建立映射。

## 建立映射和显示标签

先列出一张可审查的表：Claude 别名、提供商模型 ID、实际能力、是否共用同一个模型。不要为了填满三个别名而虚构三个不同档位；通用快速接入示例可能把所有别名指向同一模型，不一定符合用户要求的能力映射。

| 配置项 | 用途 |
|---|---|
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | `opus`，以及 `opusplan` 的规划阶段 |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | `sonnet`，以及 `opusplan` 的执行阶段 |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | `haiku` 和部分后台任务 |
| 对应的 `_NAME`、`_DESCRIPTION` | `/model` 的标签和模型说明 |
| `ANTHROPIC_MODEL` 或现有 `model` 配置 | 新会话使用的模型；检查实际优先级 |
| `CLAUDE_CODE_SUBAGENT_MODEL` | 子任务默认模型，单独检查已有固定绑定 |

- `_NAME` 应同时保留提供商实际模型和 Claude 别名，例如 `DeepSeek V4 Pro (Opus)`。`_DESCRIPTION` 写有证据的上下文、视觉和工具能力；共享模型要明确注明。
- 只在提供商真实支持、当前客户端能正确处理时使用 `[1m]`。它是客户端的上下文标记，客户端会去掉后缀再发送 API ID；不能靠后缀扩大服务端容量。对未知模型还要检查 SDK 返回的上下文元数据。
- `_SUPPORTED_CAPABILITIES` 的生效范围取决于版本和提供商模式。当前官方文档区分第三方云平台与通过 `ANTHROPIC_BASE_URL` 连接的网关；名称变量生效不代表能力变量也生效。检查运行时元数据后再使用，避免堆积无效变量。
- 不把 `medium`、`xhigh` 等客户端 effort 标签理解为提供商一定存在的独立强度档位。按官方映射说明，不默认强制 `max` 或改自动压缩阈值。
- Claude Code 的内置价格、Auto/Adaptive 等提示可能来自 Claude 的本地元数据，不能作为外部提供商的计费或能力证据。如界面仍有此类提示，报告其边界。

## 安全落盘

默认将共享路由写到用户 `~/.claude/settings.json` 的 `env`，仅修改与此次接入有关的字段。保留代理、权限、hooks、插件和其他配置。VS Code 官方扩展可在活动用户设置中启用 `claudeCode.disableLoginPrompt`；不要顺带改权限模式。

- 写前备份将要修改的文件，保持备份与原凭据文件相同的访问保护；记录可恢复路径。
- Claude JSON 做合并。VS Code 设置可能是 JSONC，应保留注释和其他键，不要用普通 JSON 解析失败后的覆盖写入方式修复。
- 凭据只进入用户授权的本机凭据/配置位置，不能进入项目共享配置、Git、skill 文件、示例、日志或总结。后续验证从已保存的配置或进程环境读取，不把 Key 放在命令行参数中。
- 写前确认原文件没有被其他进程修改；写后解析并脱敏核对。失败时恢复本次写入，不覆盖用户随后作出的改动。
- 配置创建本身不授权安装升级客户端、全局改 PATH、关闭代理或重建现有路由器。

## 分层验证

验证前检查现有用户 hooks 是否会在测试启动时触发额外动作。使用实际运行入口的二进制，临时空目录、无工具、最小提示、无会话持久化和有限超时。

可复用 [验证脚本](scripts/verify_claude_api.py)。以下命令从 skill 目录运行，或将脚本路径展开为绝对路径：

```powershell
# 先用实际扩展/CLI 二进制路径替换示例路径。
python scripts/verify_claude_api.py --claude-binary 'C:/path/to/claude.exe' --mode picker
python scripts/verify_claude_api.py --claude-binary 'C:/path/to/claude.exe' --mode smoke --model opus --expect-model provider-pro
```

1. 配置层：JSON 有效、字段合并正确，最终生效路径没有覆盖或遗留路由冲突。
2. 界面元数据层：SDK 初始化返回的 `models` 中，别名、`displayName`、`description` 符合映射。脚本的 picker 模式只请求初始化元数据。
3. 请求层：对每个不同模型及必要别名做一次最小真实请求。脚本的 smoke 模式会产生少量提供商用量；输出 `requested_model_ids`，核对客户端解析后的模型 ID，避免只看 `OK`。
4. 服务端层：CLI `modelUsage` 是客户端记录，不能单独证明服务端最终使用的模型。提供商若会静默回退或映射未知 ID，结合已确认的模型列表、官方映射，并尽量检查服务端响应/请求追踪。模型自报名称不作为身份证据。

401/403 时检查凭据和入口，不反复试用；404/模型错误时核对路径和 ID，不能静默换成其他模型并宣称成功；超时或 429 使用有限重试，并明确未完成哪层验证。

完成后简洁报告实际映射、默认模型、配置和备份位置、验证证据及必要的界面刷新动作。VS Code 通常需要 `Developer: Reload Window` 后新建对话；不要强制关闭用户会话来触发刷新。

官方机制参考：[Claude Code VS Code 配置](https://code.claude.com/docs/en/vs-code)、[模型配置与别名](https://code.claude.com/docs/en/model-config)、[LLM 网关](https://code.claude.com/docs/en/llm-gateway)。具体变量和版本支持每次按当前文档核对。
