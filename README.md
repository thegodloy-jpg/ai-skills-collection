# AI Skills Collection

把常用 AI 技能整理为可安装、可追溯的合集，面向 Codex，也可按需复制到支持 Agent Skills 的工具中。

本仓库记录 **43 项技能**：**22 项提供完整文件**，另 **21 项提供官方安装说明与用途索引**。包含小红书笔记中的 10 项技能，以及它们运行所需的 3 项共享依赖。清单快照日期：2026-10-10。

## 快速安装

需要 Python 3.10+ 和 Git。以下命令在 PowerShell、Bash 中均可使用：

```sh
git clone https://github.com/thegodloy-jpg/ai-skills-collection.git
cd ai-skills-collection
python install.py --all
```

安装到 `$CODEX_HOME/skills`；未设置 `CODEX_HOME` 时安装到 `~/.codex/skills`。安装器只复制本地技能文件，自动补齐技能之间的依赖，保留许可证。它不会覆盖已有同名目录；如果有冲突，会在复制任何技能前停止。

按需安装：

```sh
python install.py --skills grill-me frontend-design
```

上面的命令也会安装 `grill-me` 所需的 `grilling`。指定其他位置：

```sh
python install.py --skills grill-with-docs --dest ./my-skills
```

`--all` 安装本仓库可分发的 22 项，不包含需要通过产品官方入口安装的 21 项。已有技能的使用者可先安装到独立目录，再自行比较需要更新的内容。

## 笔记中的 10 项

| Skill | 用途 | 来源 |
|---|---|---|
| [find-skills](skills/find-skills/SKILL.md) | 搜索和安装技能 | [Vercel](https://github.com/vercel-labs/skills) |
| [grill-me](skills/grill-me/SKILL.md) | 通过追问澄清需求和方案 | [Matt Pocock](https://github.com/mattpocock/skills) |
| [grill-with-docs](skills/grill-with-docs/SKILL.md) | 追问方案并生成设计文档 | Matt Pocock |
| [improve-codebase-architecture](skills/improve-codebase-architecture/SKILL.md) | 检查代码架构并提出改进机会 | Matt Pocock |
| [tdd](skills/tdd/SKILL.md) | 测试驱动开发 | Matt Pocock |
| [frontend-design](skills/frontend-design/SKILL.md) | 前端界面与视觉设计 | [Anthropic](https://github.com/anthropics/skills) |
| [agent-browser](skills/agent-browser/SKILL.md) | 浏览器自动化 | [Vercel](https://github.com/vercel-labs/agent-browser) |
| [setup-matt-pocock-skills](skills/setup-matt-pocock-skills/SKILL.md) | 配置项目工程技能工作流 | Matt Pocock |
| [handoff](skills/handoff/SKILL.md) | 生成交接文档 | Matt Pocock |
| [triage](skills/triage/SKILL.md) | 整理、分类和核实 Issue、PR | Matt Pocock |

共享依赖同样完整收录：[grilling](skills/grilling/SKILL.md)、[domain-modeling](skills/domain-modeling/SKILL.md)、[codebase-design](skills/codebase-design/SKILL.md)。安装器会递归补齐所选技能的依赖。

## 其他完整收录的技能

| Skill | 用途 |
|---|---|
| [build-technical-learning-loop](skills/build-technical-learning-loop/SKILL.md) | 设计技术学习问题链与学习框架 |
| [connect-claude-code-api](skills/connect-claude-code-api/SKILL.md) | 将外部模型 API 接入 Claude Code |
| [life-decision-guide](skills/life-decision-guide/SKILL.md) | 基于《高性价比人生指南》辅助决策 |
| [personal-kb-summarizer](skills/personal-kb-summarizer/SKILL.md) | 将对话整理为知识库结构化摘要 |
| [playwright](skills/playwright/SKILL.md) | 通过 Playwright 自动操作浏览器 |
| [imagegen](skills/imagegen/SKILL.md) | 生成和编辑图片 |
| [openai-docs](skills/openai-docs/SKILL.md) | 检索官方 OpenAI 文档 |
| [skill-creator](skills/skill-creator/SKILL.md) | 创建和维护技能 |
| [skill-installer](skills/skill-installer/SKILL.md) | 从 GitHub 安装技能 |

## 使用与运行依赖

安装完成后，在支持的客户端中用 `$技能名` 显式调用，例如：

```text
$grill-me 帮我梳理这个需求
$tdd 为这个功能先写行为测试
```

`grill-me`、`grill-with-docs`、`improve-codebase-architecture`、`setup-matt-pocock-skills`、`handoff`、`triage` 保留上游的手动调用策略。

技能文件与它们调用的工具分别安装：

- `agent-browser`：安装 Node.js 24+，然后运行 `npm install -g agent-browser`。已有可识别的 Chrome 时可直接使用；没有时运行 `agent-browser install`。本仓库的 `SKILL.md` 是官方入口，实际工作流由 `agent-browser skills get core` 提供。
- `playwright`：需要 Bash 和 Node/npm/npx。Windows 可使用 Git Bash 或 WSL；若改变了技能安装位置，请按其说明设置 `PWCLI`。
- `imagegen`：取决于客户端图片工具或其脚本所需的 OpenAI API 凭据；安装文件本身不会配置账户或调用 API。
- GitHub/GitLab 工作流：使用相关功能时需要 `gh` / `glab` 及相应账户访问权限。
- `life-decision-guide`：需要读取或联网获取 [HowToLiveBetter](https://github.com/eternity4719/HowToLiveBetter) 正文，书籍全文未打包。
- `setup-matt-pocock-skills`：安装不会自动执行项目配置；实际调用时按技能说明配置目标项目。

复制目录即可用于其他支持 Agent Skills 的客户端，但工具名称、连接器和运行环境仍需由目标客户端提供。[官方技能说明](https://learn.chatgpt.com/docs/build-skills)介绍了技能的结构与加载方式。

## 其余 21 项如何使用

Google Drive、Pages、Work Pets、Documents、PDF、Presentations、Spreadsheets、Sites、Template Creator、Plugin Management 的 20 项技能，以及 `review-agent`，见[官方安装索引](external/README.md)。其中有专有许可、明确禁止再分发的文件，或尚未核实的当前快照许可，因此未复制产品缓存内容。

对于插件，请从支持的 ChatGPT/Codex 产品插件目录安装，并完成需要的账户连接。技能的 Markdown 不会提供连接器、认证或产品专有运行时；相关边界见[官方说明](https://developers.openai.com/plugins/concepts/skills)。

## 来源、许可与维护

- [catalog.json](catalog.json)：全部 43 项的用途、来源、分发方式、依赖和完整文件 SHA-256。
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)：第三方来源、版本和许可，以及合集中的改动说明。
- [licenses/](licenses/)：从上游固定提交取得的许可正文与声明。
- 完整复制第三方技能目录及其 `agents/`、`references/`、`scripts/`、`assets/`；排除编译缓存和凭据文件。
- 本仓库的原创整理、安装脚本和 3 项仓库所有者提供的原创技能使用 [MIT](LICENSE)。第三方技能保留各自许可证，根 MIT 不替代第三方授权。

这是独立整理的技能合集，各项目的版权与维护归原作者所有。更新第三方内容时应同时更新来源、许可、依赖与文件校验值。
