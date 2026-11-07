---
name: chat-context-archiver
description: Organize conversation context into a structured markdown file at a user-specified path, auto-append a timestamp when needed, and return only the final saved path.
---

# Chat Context Archiver

## When to use this skill

Use this skill when the user asks to:

- summarize current or prior conversation context;
- preserve decisions, constraints, and progress into a markdown file;
- save that file to a specific path;
- get a direct output path for reuse in the next chat/session.

Typical phrases include:

- "整理聊天上下文"
- "保存本次过程到 md"
- "总结这次对话并写入指定路径"
- "export this conversation context to markdown"

## Inputs

- `target_path` (required): output location. Absolute path is preferred.
  - If `target_path` is an existing directory, save as `ctx_<topic-summary>_<timestamp>.md` in that directory.
  - If `target_path` ends with `/` or `\`, treat it as a directory and create it if needed.
  - If `target_path` is a file path without extension, append `.md`.
- `scope` (optional): default is current session.
- `include_key_paths` (fixed): always `true`.

If `target_path` is missing, ask one short question to get it.

## Output policy (fixed)

- Primary language: English.
- Key places must include concise Chinese annotation for readability.
- Include a dedicated `Key Files and Paths` section.
- In directory mode, generate a descriptive filename by extracting topic keywords from content.
- If target file already exists, auto-append timestamp to filename (format: `yyyyMMdd-HHmmss`).
- Final assistant reply must be a single line:
  - `Context saved: <absolute_path>`

## Workflow

1. Collect context from the conversation scope.
2. Extract only high-signal information:
   - user goals;
   - constraints and non-goals;
   - key decisions and rationale;
   - implemented artifacts and status;
   - pending work and risks;
   - concrete file paths and module names.
3. Build markdown from the template at `assets/context_template.md`.
4. Write file using `scripts/export_context.ps1`:
   - pass `target_path`;
   - pass generated markdown content via temp file;
   - rely on script for directory creation, timestamping, and final path output.
5. Return only the final path line from script output.

## Required content shape

Generated markdown should contain these sections in order:

1. Goal Overview / 目标概览
2. Constraints and Non-Goals / 约束与非目标
3. Decisions and Rationale / 决策与原因
4. Delivery Progress / 交付进展
5. Key Files and Paths / 关键文件与路径
6. Risks and Open Questions / 风险与待确认
7. Next Actions / 下一步

## Quality checks before returning

Use checklist in `references/quality_checklist.md`.

Hard requirements:

- no fabricated files or decisions;
- path list must be concrete and useful;
- language rule is respected (English main text + Chinese annotations at key headers/notes);
- final reply format is exactly:
  - `Context saved: <absolute_path>`
