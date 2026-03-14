# `yuque-openapi` Skill 详细说明

## Skill 定位

`yuque-openapi` 是一个围绕 Yuque OpenAPI 封装的跨平台工作流 skill，目标是让本地 Markdown 内容、目录结构和语雀知识库之间可以稳定地双向流动。

它的重点不是只做单个 API 调用，而是把常见的文档协作动作整理成一套可重复执行的命令式流程，包括：

- 内容同步
- 目录同步
- 批量任务执行
- 快照备份与恢复
- 基础 Repo / Doc 管理

## 这个 Skill 解决什么问题

在很多文档工作流里，内容可能先在本地生成，再同步到语雀；也可能先在语雀维护，再导出回本地做版本管理。这个 skill 的作用就是把这些来回切换的操作标准化，减少手工复制、目录错位、文档丢失和批量执行不一致的问题。

它尤其适合下面几类需求：

- 本地 Markdown 是主数据源，需要批量推送到语雀。
- 语雀知识库是主数据源，需要定期导出到本地做备份或迁移。
- 本地目录和远程文档都在变更，需要先规划再同步，避免直接覆盖。
- 需要把本地文档树结构同步成语雀中的 TOC 层级。
- 需要执行跨多个知识库的重复性任务，并希望把任务配置固化下来。

## 核心能力

### 1. 空间、知识库和文档发现

这个 skill 可以先帮助你确认“要同步到哪里”或“从哪里导出来”。

支持的发现类能力包括：

- 获取当前用户信息。
- 枚举个人空间和群组空间。
- 列出用户或群组下的知识库。
- 列出知识库中的文档。
- 通过 id 或 `namespace/repo`、slug 等方式定位目标资源。

这类能力适合用在同步前的目标确认、自动化脚本前置检查，以及批量任务配置阶段。

### 2. Repo 和 Doc 的基础 CRUD

除了同步，这个 skill 也支持知识库和文档的基础管理操作。

包括：

- 创建知识库。
- 读取知识库详情。
- 更新知识库配置。
- 删除知识库。
- 创建文档。
- 更新文档。
- 按“存在则更新，不存在则创建”的方式写入文档。
- 删除文档。

它的作用是让“内容管理”和“内容同步”可以放在同一套 CLI 工作流里处理，不需要在多套脚本之间来回切换。

### 3. 单文档 Markdown 同步

如果只是同步一篇文档，这个 skill 提供了比较直接的文件级操作：

- `push-markdown`：把本地 Markdown 文件推送到语雀文档。
- `pull-markdown`：把语雀文档拉取为本地 Markdown 文件。

这部分能力适合：

- 生成式内容写完后快速发布到语雀。
- 按篇导出远程文档做本地留档。
- 小范围修正文档，不想动整个目录同步流程。

这个 skill 还会优先利用 front matter 中的 `yuque_doc_id` 或 `yuque_doc_slug` 做稳定映射，降低重复创建和错绑文档的风险。

### 4. 整目录增量同步

这是 `yuque-openapi` 最核心的能力之一，面向“一个本地 Markdown 目录”和“一个语雀知识库”之间的批量同步。

相关命令包括：

- `plan-dir-markdown`
- `push-dir-markdown`
- `pull-dir-markdown`
- `export-repo-markdown`

它解决的核心问题有：

- 识别哪些文件应该推送。
- 识别哪些远程文档应该拉回本地。
- 判断哪些内容没有变化可以跳过。
- 标记本地和远程都改过的冲突项。
- 通过 `yuque-index.json` 维持文档 id、slug、路径和内容哈希之间的映射关系。

这让目录级同步不再只是“全量覆盖”，而是更接近一个可审查、可回放、可增量的同步过程。

### 5. TOC 与目录结构重建

除了文档正文，语雀知识库里的层级结构本身也经常需要维护。这个 skill 支持把本地 Markdown 树映射成语雀侧的 TOC。

相关能力包括：

- `sync-dir-toc`：只重建远程 TOC。
- `push-dir-markdown --sync-toc`：同步正文后顺便更新 TOC。

它的作用在于：

- 让本地目录结构成为远程层级的来源。
- 统一父子文档关系，减少手工维护目录的成本。
- 在 TOC 重写前自动做快照，降低误操作风险。

默认情况下，这类操作会阻止“本地缺文件却直接裁剪远程 TOC”的危险行为。只有明确允许 prune，才会继续执行。

### 6. 自动快照与恢复

TOC 重建和目录级同步一旦出错，影响范围通常比较大。这个 skill 为此补了恢复机制。

相关能力包括：

- 在 TOC 变更前自动导出快照。
- 生成包含文档导出、`repo.json`、`toc.json`、`toc.md` 和 `snapshot.json` 的备份目录。
- 使用 `restore-repo-snapshot` 恢复文档和 TOC。
- 用 `--dry-run` 先预览恢复动作。

这部分的价值很直接：让目录重建类操作具备回滚抓手，而不是只能靠人工补救。

### 7. Manifest 批量任务

当操作不再只是一个 repo、一个目录时，批量任务就很重要。这个 skill 支持把多步操作写成 manifest 文件统一执行。

相关能力包括：

- `validate-manifest`：先检查任务结构是否正确。
- `run-manifest`：按顺序执行 JSON 中定义的任务。
- 使用 `assets/manifests/` 里的模板快速起步。
- 通过 `plan-dir-markdown --write-manifest` 把同步计划直接转成可执行任务。

这类能力很适合：

- 多知识库批量导出。
- 多目录批量推送。
- 需要复用、审查、版本管理的同步任务。
- 希望避免手写 shell 循环的自动化场景。

### 8. 原始 API 调用与能力扩展

如果某个 Yuque OpenAPI 端点还没有被 CLI 显式封装，这个 skill 也支持通过 `raw <METHOD> <PATH>` 直接发起请求。

它的作用是：

- 在 CLI 新增能力前先验证接口可行性。
- 处理偶发的、低频的特殊接口需求。
- 为后续扩展命令提供试验入口。

这让 skill 不会因为“命令暂时没封装”而完全卡住。

## 推荐工作流

这个 skill 比较推荐下面的使用顺序：

1. 先用 `me` 校验 token 和 API 可用性。
2. 用 `list-spaces`、`list-repos` 找到正确的空间和知识库。
3. 根据任务范围选择最小可行同步方式：
   `push-markdown` 适合单文件，`plan-dir-markdown` 适合整目录，`sync-dir-toc` 适合只修结构。
4. 在批量同步前先查看计划结果或写出 manifest。
5. 在 TOC 重写前确认本地目录完整，尽量保留自动快照。
6. 如果是重复任务，把流程固化到 manifest 中，避免每次手工敲命令。

## 安全边界和注意事项

这个 skill 的安全设计主要集中在几个方面：

- 优先从 `YUQUE_TOKEN` 或 `YUQUE_ACCESS_TOKEN` 读取 token，避免把敏感信息直接写进命令或代码。
- 对删除类操作要求显式确认，避免误删。
- 对 TOC 重写默认启用 prune 防护，避免本地不完整时误裁远程结构。
- 在远程目录结构变更前自动做快照，方便恢复。
- 默认优先使用 Markdown 格式，减少跨格式同步时的意外差异。

这意味着它更偏向“稳妥可审查”的工作流，而不是“无保护的一把梭”式同步工具。

## 目录中的关键资源

`skills/yuque-openapi/` 下的资源大致可以这样理解：

- [`../skills/yuque-openapi/SKILL.md`](../skills/yuque-openapi/SKILL.md)：skill 的总入口说明。
- `scripts/yuque_api.py`：CLI 主入口。
- `scripts/selftest_yuque_api.py`：离线回归测试。
- `scripts/check_yuque_skill.py`：本地快速检查脚本。
- `references/`：按主题拆分的操作说明。
- `assets/manifests/`：常见批量任务模板。
- `agents/openai.yaml`：与 agent 集成相关的配置文件。

## 参考阅读

如果你要进一步深入某一块能力，可以继续读这些原始说明：

- [`../skills/yuque-openapi/references/repo-doc-crud.md`](../skills/yuque-openapi/references/repo-doc-crud.md)
- [`../skills/yuque-openapi/references/dir-sync.md`](../skills/yuque-openapi/references/dir-sync.md)
- [`../skills/yuque-openapi/references/toc-sync.md`](../skills/yuque-openapi/references/toc-sync.md)
- [`../skills/yuque-openapi/references/manifest.md`](../skills/yuque-openapi/references/manifest.md)
- [`../skills/yuque-openapi/references/troubleshooting.md`](../skills/yuque-openapi/references/troubleshooting.md)
