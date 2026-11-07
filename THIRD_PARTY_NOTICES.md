# Third-party notices

Initial snapshot date: 2026-10-10; additions recorded through 2026-11-07. Pinned source revisions are listed per entry. This repository is an independent collection; inclusion does not imply endorsement by upstream authors.

## Bundled content

| Source | Included skills | License | Snapshot / provenance |
|---|---|---|---|
| [mattpocock/skills](https://github.com/mattpocock/skills) | 10 engineering/productivity skills | [MIT](licenses/mattpocock-skills-MIT.txt) | `49dd158d1076134a641b33efb035946536778336` |
| [vercel-labs/skills](https://github.com/vercel-labs/skills) | `find-skills` | [MIT](licenses/vercel-skills-MIT.txt) | `c164f76adf927d30e8b17add45083d963da6dffe`; [third-party notice](licenses/vercel-skills-ThirdPartyNoticeText.txt) preserved |
| [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser) | `agent-browser` discovery skill | [Apache-2.0](licenses/agent-browser-Apache-2.0.txt) | `0207911f1bd4d0393eddaa90f2e50f96e0fb8974` |
| [anthropics/skills](https://github.com/anthropics/skills) | `frontend-design` | [Apache-2.0](skills/frontend-design/LICENSE.txt) | `9d630808e4add0a7146de4af9384155d5dee350a` |
| [eternity4719/HowToLiveBetter](https://github.com/eternity4719/HowToLiveBetter) | `life-decision-guide` | [MIT for skills](licenses/HowToLiveBetter-MIT.txt) | Installed snapshot; license scope checked at `bb25081b423091f9e22059aab6b4ed7343a2266d` |
| OpenAI Codex bundled skills; public project [openai/skills](https://github.com/openai/skills) | `imagegen`, `openai-docs`, `skill-creator`, `skill-installer`, `playwright` | Apache-2.0 in each directory | Installed snapshot, identified by file hashes in `catalog.json`; not claimed to equal the current public repository version |
| [jgraph/drawio-mcp](https://github.com/jgraph/drawio-mcp) | `drawio` | [Apache-2.0](skills/drawio/LICENSE.txt), Copyright 2025 JGraph Ltd | `a4515e4dc986e22d369551ac213399d6fb653bde` |
| [ai-zixun/humanizer-zh](https://github.com/ai-zixun/humanizer-zh) | `humanizer-zh` | [MIT](skills/humanizer-zh/LICENSE), Copyright 2026 aizixun | `f75f1ac9735c4f10da1bba0148e0ea7228c5c3b3`; version file says 1.3.0; this commit includes two README updates after that tag |
| [jwynia/agent-skills](https://github.com/jwynia/agent-skills) | `presentation-design` | MIT declaration and author `jwynia` retained in SKILL.md; [standard MIT text](skills/presentation-design/LICENSE.txt) added | `e02ec7e226a6e4f8419fd3b88a1d8e472d421b32`, `skills/general/communication/presentation-design/SKILL.md` |

`playwright/NOTICE.txt` preserves attribution to Microsoft Playwright CLI and the Codex adaptation. All existing notices and license files are retained.

The HowToLiveBetter book text is licensed under [CC BY 4.0](licenses/HowToLiveBetter-CC-BY-4.0.txt), while its `skills/` directory is explicitly covered by MIT. The book text is not bundled. Original source: 《高性价比人生指南》 by eternity4719 and contributors, https://github.com/eternity4719/HowToLiveBetter .

## Collection changes

- Source snapshots and packaging changes are recorded per entry in `catalog.json`. `skills/life-decision-guide/README.md` retains its clarification that upstream references to “this repository” refer to HowToLiveBetter. New local snapshots use LF text line endings while retaining UTF-8 BOM where required by Windows PowerShell 5.1.
- Required upstream root licenses and Vercel's notice were added inside the corresponding skill directories so a standalone installation retains attribution.
- Python bytecode caches, Git internals and personal installation metadata are excluded.
- Eleven owner-supplied skills (`build-technical-learning-loop`, `connect-claude-code-api`, `personal-kb-summarizer`, `technical-doc-workflow`, `chat-context-archiver`, `day0-workspace`, `image-release`, `inference-benchmark-matrix`, `inference-root-cause`, `perf-benchmark`, `perf-e2e-compare`) are distributed under this collection's MIT license, also copied into those skill directories. This records owner-supplied local snapshots, not a claim of a verified public upstream for each file.
- Public operational examples use a generic configurable DAY0 root and RFC 5737 documentation hosts in place of personal directories and actual service addresses. Benchmark script hashes and byte counts are updated to match the distributed copy. Actual model workspace manifests, service credentials, logs and benchmark results are not bundled.
- The `drawio` installation record is excluded. Its pinned upstream license is included. `presentation-design` declares MIT in its pinned SKILL.md; standard MIT license text is added with its declared author, without inventing an upstream standalone license file.
- `original_files_sha256` records the installed source files before these packaging changes; `files_sha256` records the actual distributable files checked by the installer.

## Indexed content that is not bundled

The 20 product-plugin skills, `review-agent` and the locally installed `pptx` snapshot are documented in [external/README.md](external/README.md). The local `pptx/LICENSE.txt` prohibits redistribution; a different current public upstream license is not applied retroactively to this unverified local snapshot. No source from that local directory is bundled.

Google Drive declares MIT in plugin metadata, but the installed version differs from the publicly accessible snapshot and no corresponding license text was found. Documents has a specific license restricting redistribution despite MIT plugin metadata. PDF, Presentations and Spreadsheets have unverified snapshot-level redistribution terms. Other listed plugins explicitly declare Proprietary. These distinctions are recorded in `catalog.json`; they are not claims that all product plugins share one license.

The repository-level MIT license covers only the collection's original material and the owner-supplied skills identified above. It does not relicense third-party material.
