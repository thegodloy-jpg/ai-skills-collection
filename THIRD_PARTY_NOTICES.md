# Third-party notices

Snapshot date: 2026-10-10. This repository is an independent collection; inclusion does not imply endorsement by upstream authors.

## Bundled content

| Source | Included skills | License | Snapshot / provenance |
|---|---|---|---|
| [mattpocock/skills](https://github.com/mattpocock/skills) | 10 engineering/productivity skills | [MIT](licenses/mattpocock-skills-MIT.txt) | `49dd158d1076134a641b33efb035946536778336` |
| [vercel-labs/skills](https://github.com/vercel-labs/skills) | `find-skills` | [MIT](licenses/vercel-skills-MIT.txt) | `c164f76adf927d30e8b17add45083d963da6dffe`; [third-party notice](licenses/vercel-skills-ThirdPartyNoticeText.txt) preserved |
| [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser) | `agent-browser` discovery skill | [Apache-2.0](licenses/agent-browser-Apache-2.0.txt) | `0207911f1bd4d0393eddaa90f2e50f96e0fb8974` |
| [anthropics/skills](https://github.com/anthropics/skills) | `frontend-design` | [Apache-2.0](skills/frontend-design/LICENSE.txt) | `9d630808e4add0a7146de4af9384155d5dee350a` |
| [eternity4719/HowToLiveBetter](https://github.com/eternity4719/HowToLiveBetter) | `life-decision-guide` | [MIT for skills](licenses/HowToLiveBetter-MIT.txt) | Installed snapshot; license scope checked at `bb25081b423091f9e22059aab6b4ed7343a2266d` |
| OpenAI Codex bundled skills; public project [openai/skills](https://github.com/openai/skills) | `imagegen`, `openai-docs`, `skill-creator`, `skill-installer`, `playwright` | Apache-2.0 in each directory | Installed snapshot, identified by file hashes in `catalog.json`; not claimed to equal the current public repository version |

`playwright/NOTICE.txt` preserves attribution to Microsoft Playwright CLI and the Codex adaptation. All existing notices and license files are retained.

The HowToLiveBetter book text is licensed under [CC BY 4.0](licenses/HowToLiveBetter-CC-BY-4.0.txt), while its `skills/` directory is explicitly covered by MIT. The book text is not bundled. Original source: 《高性价比人生指南》 by eternity4719 and contributors, https://github.com/eternity4719/HowToLiveBetter .

## Collection changes

- Skill source files are preserved byte for byte, except `skills/life-decision-guide/README.md`, which has a prominent added note clarifying that references to “this repository” in the upstream instructions refer to HowToLiveBetter. The note points to the collection installation instructions. No skill execution instructions were changed.
- Required upstream root licenses and Vercel's notice were added inside the corresponding skill directories so a standalone installation retains attribution.
- Python bytecode caches were excluded.
- Three owner-supplied original skills (`build-technical-learning-loop`, `connect-claude-code-api`, `personal-kb-summarizer`) are distributed under this collection's MIT license, also copied into those skill directories.
- `original_files_sha256` records the installed source files before these packaging changes; `files_sha256` records the actual distributable files checked by the installer.

## Indexed content that is not bundled

The 20 product-plugin skills and `review-agent` are documented in [external/README.md](external/README.md). No proprietary plugin skill source, product runtime, connection credentials, or account configuration is redistributed.

Google Drive declares MIT in plugin metadata, but the installed version differs from the publicly accessible snapshot and no corresponding license text was found. Documents has a specific license restricting redistribution despite MIT plugin metadata. PDF, Presentations and Spreadsheets have unverified snapshot-level redistribution terms. Other listed plugins explicitly declare Proprietary. These distinctions are recorded in `catalog.json`; they are not claims that all product plugins share one license.

The repository-level MIT license covers only the collection's original material and the owner-supplied skills identified above. It does not relicense third-party material.
