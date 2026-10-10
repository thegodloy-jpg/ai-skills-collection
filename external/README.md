# 官方插件与产品内置技能索引

这里记录主清单中未打包源码的 **21 项技能**：20 项来自产品插件，1 项为产品内置的 `review-agent`。本页只包含用途和公开安装指引，不包含这些插件的原始技能正文、连接器或运行时。

## 安装入口

在支持的 ChatGPT/Codex 产品中打开 Plugins 目录，搜索对应插件并按产品提示安装、连接账户。可参考[官方插件入门说明](https://developers.openai.com/plugins/quickstart)。Google Drive 另有[官方公开源码目录](https://github.com/openai/plugins/tree/main/plugins/google-drive)。

插件目录和可用能力依产品版本、账户及组织设置而定。如果当前产品没有提供某项能力，本合集没有独立安装它的命令。复制 Markdown 不会创建连接器、认证、Excel 会话或产品运行时；[官方技能与 MCP 边界说明](https://developers.openai.com/plugins/concepts/skills)对此有进一步解释。

## 完整清单

| Skill | 用途 | 安装的插件 / 产品能力 |
|---|---|---|
| `google-drive:google-docs` | 创建和编辑 Google Docs | Google Drive |
| `google-drive:google-drive` | 查找和管理云端文件 | Google Drive |
| `google-drive:google-drive-comments` | 处理云端文件评论 | Google Drive |
| `google-drive:google-sheets` | 编辑 Google Sheets | Google Drive |
| `google-drive:google-slides` | 编辑 Google Slides | Google Drive |
| `pages:maintain-space` | 维护页面内容 | Pages |
| `pages:manage-schedules` | 管理页面定时任务 | Pages |
| `pages:organize-space` | 组织页面结构 | Pages |
| `pages:write-page` | 创建和编辑页面 | Pages |
| `work-pets:create-pet` | 创建工作宠物 | Work Pets |
| `work-pets:pets` | 管理工作宠物 | Work Pets |
| `work-pets:update-pet` | 更新工作宠物 | Work Pets |
| `spreadsheets:Spreadsheets` | 创建和编辑电子表格文件 | Spreadsheets |
| `spreadsheets:excel-live-control` | 控制已连接的 Excel 会话 | Spreadsheets；需要 Excel 加载项和连接会话 |
| `documents:documents` | 创建和编辑 Word 文档 | Documents |
| `pdf:pdf` | 读取和生成 PDF | PDF |
| `presentations:Presentations` | 创建和编辑演示文稿 | Presentations |
| `sites:sites` | 构建和发布网站 | Sites |
| `template-creator:template-creator` | 从参考资料创建可复用模板 | Template Creator |
| `plugin-management:plugin-management` | 管理插件连接与权限 | Plugin Management |
| `review-agent` | 对代码变更进行只读审查 | 宿主产品提供时使用；未核实单独公开安装入口 |

## 为什么仅提供索引

- Pages、Work Pets、Sites、Template Creator、Plugin Management 的元数据明确标为 Proprietary。
- Documents 的技能许可证明确限制复制和向第三方分发，因此没有复制其缓存。
- Google Drive 的插件元数据标为 MIT，但当前安装快照与公开版本不同，也没有取得相应许可正文；同时它依赖账户连接器。这里保留官方入口与该区别，未把其当前缓存作为可独立使用的开源包发布。
- PDF、Presentations、Spreadsheets 当前快照的许可正文未核实，部分功能还依赖产品提供的运行时。
- `review-agent` 当前安装目录没有独立再分发许可。

这些判断针对本次清单对应的安装快照，不替代各项目以后公布的授权。完整版本和来源元数据见 [catalog.json](../catalog.json)。

如果只需要可复制的本地 PDF 技能，可另查看 [OpenAI Skills 的公开 PDF 版本](https://github.com/openai/skills/tree/main/skills/.curated/pdf)及其目录内许可；它不是本清单记录的产品插件快照。
