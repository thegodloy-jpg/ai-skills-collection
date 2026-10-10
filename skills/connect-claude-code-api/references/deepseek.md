# DeepSeek 接入参考

本参考来自 2026-10-01 的官方文档和本机会话验证。每次应用时重新核对当前 API 模型列表、官方规格和客户端版本，不将本页模型版本视为永久事实。

## 入口与鉴权

Anthropic 兼容 base URL：`https://api.deepseek.com/anthropic`。

Claude Code 官方接入示例使用 `ANTHROPIC_AUTH_TOKEN`。对应 SDK/API 也支持 `x-api-key`；已有配置用 Bearer token 时，可在此次 Claude 路由中将冲突的 `ANTHROPIC_API_KEY` 设为空，而不是删除原来的登录数据。

用用户授权的凭据查询 `GET https://api.deepseek.com/models`，不输出 Key。创建 skill 或阅读本参考不需要调用收费接口。

## 已核对的模型与能力

| Claude 别名 | API ID | 当时的服务端版本 | 上下文 | 能力 |
|---|---|---|---|---|
| Opus | `deepseek-v4-pro` | DeepSeek-V4-Pro-0813 | 1M | 文本、思考、工具调用；不支持图片 |
| Sonnet | `deepseek-flash` | DeepSeek-V4.1-Flash | 1M | 文本、图片、思考、工具调用 |
| Haiku | `deepseek-flash` | 同 Sonnet | 1M | 与 Sonnet 使用同一个模型 |

官方快速接入示例把三个别名全部映射到 Flash，适用于统一使用 Flash 的情形。用户要求按实际模型分档时，使用上表。官方还规定 `claude-opus*` 请求映射到 Pro，`claude-sonnet*`、`claude-haiku*` 请求映射到 Flash；优先直接使用已核对的真实 API ID。

未知模型名可能被兼容接口自动映射到 Flash，因此“请求成功”不能代替模型 ID 核对。旧 Flash 模型 ID 也可能已被替换为新的 Flash 版本。

## 合并配置示例

下列片段合并到用户配置中，不整文件覆盖。凭据由 agent 在用户授权的本机位置另行设置；示例刻意不含凭据。

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
    "ANTHROPIC_MODEL": "sonnet",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "deepseek-v4-pro[1m]",
    "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME": "DeepSeek V4 Pro (Opus)",
    "ANTHROPIC_DEFAULT_OPUS_MODEL_DESCRIPTION": "DeepSeek-V4-Pro-0813 | 1M context | thinking + tools | text only",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "deepseek-flash[1m]",
    "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME": "DeepSeek V4.1 Flash (Sonnet)",
    "ANTHROPIC_DEFAULT_SONNET_MODEL_DESCRIPTION": "DeepSeek-V4.1-Flash | 1M context | thinking + tools | text + images",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deepseek-flash[1m]",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME": "DeepSeek V4.1 Flash (Haiku)",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL_DESCRIPTION": "Same DeepSeek-V4.1-Flash as Sonnet | 1M context | text + images"
  }
}
```

默认 `sonnet` 保持日常会话使用 Flash；用户选择 Pro 时保留该偏好。检查 `CLAUDE_CODE_SUBAGENT_MODEL` 是否已有固定 Flash 绑定，它可能让部分子任务继续使用 Flash；不要把调整主模型与调整所有子任务混为一谈。

本机 Claude Code 2.1.195 的 SDK 初始化已返回上述三个标签，三个别名最小请求均返回 `OK`，客户端 `modelUsage` 记录分别为 Pro、Flash、Flash，均带 `[1m]`。这是客户端映射和连通性证据，未测完整工具调用、图片理解、思考质量或 VS Code 重载后的屏幕显示。

当时 `_SUPPORTED_CAPABILITIES` 并未纠正此网关路径的全部 SDK 能力标志，因此最终配置只保留有效的 ID、名称、说明和上下文标记。Default 行仍可能使用 Claude 内置价格；DeepSeek 实际计费以提供商为准。

## 思考强度

官方文档的实际强度映射为：`minimal/low → low`，`medium/high/xhigh → high`，`max/ultra → max`。不能把 UI 中的 xhigh 解释为 DeepSeek 的独立 xhigh 档位。不要因为示例包含 max 就替用户强制提高强度。

一次最小 DeepSeek 请求可以使用：

```powershell
python scripts/verify_claude_api.py --claude-binary 'C:/path/to/claude.exe' --mode smoke --model opus --expect-model deepseek-v4-pro --effort low --disable-thinking
```

Sonnet、Haiku 的预期模型均为 `deepseek-flash`。只需要验证连通性时禁用思考；思考和工具能力的专项验证另按当前任务需要执行。

## 当前官方来源

- [接入 Claude Code](https://api-docs.deepseek.com/zh-cn/quick_start/agent_integrations/claude_code/)
- [Anthropic API 兼容性和模型映射](https://api-docs.deepseek.com/zh-cn/guides/anthropic_api/)
- [模型版本、上下文、视觉能力和计费](https://api-docs.deepseek.com/quick_start/pricing/)
- [思考模式与 effort 映射](https://api-docs.deepseek.com/guides/thinking_mode/)
