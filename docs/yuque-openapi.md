# `yuque-openapi` Skill 详细说明

## Skill 定位

`yuque-openapi` 是一个围绕 Yuque OpenAPI 封装的跨平台工作流 skill，目标是让本地 Markdown 内容、目录结构和语雀知识库之间可以稳定地双向流动。

它的重点不是只做单个 API 调用，而是把常见的文档协作动作整理成一套可重复执行的命令式流程，包括：

- 内容同步
- 目录同步
- 批量任务执行
- 快照备份与恢复
- 基础 Repo / Doc 管理

## 运行方式与自动化特性

这个 skill 的实现形态是一个可直接运行的 Python CLI，而不是只给 agent 看的说明文件。

它目前具备这些比较适合自动化接入的特征：

- 只依赖 Python 标准库，跨平台运行成本低。
- 优先通过 `YUQUE_TOKEN` 或 `YUQUE_ACCESS_TOKEN` 读取令牌，必要时也能显式传 `--token`。
- 支持 `--base-url`、`--retries`、`--retry-backoff`、`--retry-max-backoff`，也支持对应环境变量，便于代理、重试和 CI 场景。
- 支持 `json`、`jsonl`、`table`、`text` 四种输出格式。
- 支持 `--select` 对返回结果做字段投影，方便脚本只消费需要的字段。
- 列表类接口支持分页和 `--all` 自动翻页，不需要手工循环 offset。
- 针对 `429` 和 `5xx` 响应内建了重试与退避机制，降低批量执行时的偶发失败。

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

实现上还有几个重要细节：

- `list-spaces` 不是简单转发单个接口，而是把个人空间和群组空间整合成一份统一结果。
- `list-repos` 和 `create-repo` 支持 `owner-type=auto/user/group`，其中 `auto` 会先尝试用户空间，再在 `404` 时回退到群组空间。
- `list-repos`、`list-docs` 这类列表命令支持 `--all` 自动抓取全部分页结果。

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

除了基础 CRUD，这部分还有几项实际很重要的扩展能力：

- 文档写入不只支持 Markdown，也支持 `html`、`lake`、`asl`，并会根据格式自动选择 `body` 或 `body_asl`。
- 支持 `--body`、`--body-file` 和标准输入，适合处理较长正文或被其他命令管道输入的内容。
- 支持 `--extra-json`，可以把 CLI 暂时未显式建模的字段直接合并进请求体。
- `raw` 命令还支持 `--query-json` 和 `--data-json`，适合测试新端点或处理低频特殊请求。

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

单文档同步还有一套比较稳定的默认规则：

- `push-markdown` 默认会剥离 YAML front matter，只上传正文；如果确实希望连 front matter 一起上传，需要显式加 `--keep-front-matter`。
- 标题默认优先取显式 `--title`，否则从正文首个 H1 推导，再不行才退回到 front matter 标题或文件名。
- 更新目标会按 `--doc`、front matter 中的 `yuque_doc_id`、`yuque_doc_slug`、显式 `--slug`、文件名这个顺序做推断。
- `public` 和 `slug` 也会优先复用 front matter 或显式参数，便于反复推送时保持稳定身份。
- `pull-markdown --front-matter` 和 `export-repo-markdown --front-matter` 会把 repo、doc id、slug、title、public、format、更新时间写回本地，形成可回拉的 round-trip 信息。

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

目录级同步还有几条关键规则：

- `yuque-index.json` 不只是一个导出清单，而是目录级同步的状态文件，会记录 `relative_path`、`doc_id`、`doc_slug`、`title`、`public`、`format`、`content_hash`、`last_sync_at` 等字段。
- 读取索引时会兼容 `docs` 和 `files` 两种入口字段，也会对绝对路径和相对路径做归一化处理。
- `plan-dir-markdown` 生成的不是抽象建议，而是带 `operations` 数组的可执行计划，必要时还能直接落成 manifest JSON。
- 当索引里已有 `content_hash` 时，会做近似三方比较，判断是本地改了、远程改了，还是两边都改了。
- `pull-dir-markdown` 会优先复用索引和 front matter 中的映射，其次才按远程 TOC 推导路径，因此重复拉取时不容易把本地路径抖乱。
- 按 TOC 还原层级时，带子文档的父节点会落成 `<parent>/index.md`，叶子节点会落成 `<name>.md`。
- 新建远程文档时可按 `path` 或 `stem` 生成 slug，并带有自动避重逻辑，避免批量推送时 slug 冲突。

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

TOC 重建还有两个很实用的细节：

- 可以通过 `--write-toc-file` 先把生成出的 TOC Markdown 写到本地，便于审阅再决定是否上传。
- prune guard 的拦截发生在真正写 TOC 之前，如果本地树不完整，它会先拒绝执行，而不是先改远程再报错。

### 6. 自动快照与恢复

TOC 重建和目录级同步一旦出错，影响范围通常比较大。这个 skill 为此补了恢复机制。

相关能力包括：

- 在 TOC 变更前自动导出快照。
- 生成包含文档导出、`repo.json`、`toc.json`、`toc.md` 和 `snapshot.json` 的备份目录。
- 使用 `restore-repo-snapshot` 恢复文档和 TOC。
- 用 `--dry-run` 先预览恢复动作。

这部分的价值很直接：让目录重建类操作具备回滚抓手，而不是只能靠人工补救。

从实现上看，快照与恢复还有几条关键约束：

- 默认备份目录是本地根目录旁边的 `.yuque-backups/<namespace>__<repo>/<timestamp>/`。
- `snapshot.json` 带有 `schema_version`，恢复时会校验版本兼容性，而不是盲目套用旧快照。
- `restore-repo-snapshot` 支持直接传快照目录，也支持直接传 `snapshot.json`。
- 可以用 `--skip-docs` 只恢复 TOC，或用 `--skip-toc` 只恢复文档。
- 可以用 `--write-toc-file` 把将要恢复的 TOC 先落到本地。
- `--dry-run` 不会写远程，只会预览将要恢复哪些 markdown 文件和多少条 TOC。
- 如果要恢复到不同 repo，必须同时传 `--repo` 和 `--allow-repo-override`，避免误恢复到错误目标。

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

Manifest 批量任务还有几条实现细节：

- manifest 支持直接传 JSON 数组，也支持带根对象的 JSON，并兼容 `operations`、`requests`、`items` 三种任务字段名。
- `manifest` 参数既可以是文件路径，也可以传 `-` 从标准输入读取。
- 执行前会先做结构校验，包括未知字段、缺失必填参数和参数取值是否合法。
- `continue_on_error` 可以写在命令行上，也可以写在 manifest 根对象里。
- 运行过程中会输出进度信息，方便在批量任务里追踪当前执行到哪一步。

### 8. 原始 API 调用与能力扩展

如果某个 Yuque OpenAPI 端点还没有被 CLI 显式封装，这个 skill 也支持通过 `raw <METHOD> <PATH>` 直接发起请求。

它的作用是：

- 在 CLI 新增能力前先验证接口可行性。
- 处理偶发的、低频的特殊接口需求。
- 为后续扩展命令提供试验入口。

配合 `--query-json` 和 `--data-json`，它可以直接覆盖不少临时接口验证场景，让 skill 不会因为“命令暂时没封装”而完全卡住。

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
- 对 `429` 和 `5xx` 响应带有内建重试与退避，降低批量任务中的瞬时失败。

这意味着它更偏向“稳妥可审查”的工作流，而不是“无保护的一把梭”式同步工具。

## 校验与质量保障

这个 skill 已经带了一套基础校验能力，适合在继续扩展时做回归检查：

- `scripts/selftest_yuque_api.py` 覆盖了目录计划写 manifest、`push-dir-markdown --sync-toc` 自动备份、manifest 容错执行、prune guard、快照恢复和 dry-run 等关键路径。
- `scripts/check_yuque_skill.py` 可以一键串联离线自测、skill 校验和 CLI 帮助 smoke test。
- 这意味着当前文档中提到的核心工作流，大多已经有对应的最小验证，而不是纯概念描述。

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
