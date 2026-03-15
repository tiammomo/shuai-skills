# `feishu-doc-sync`

`feishu-doc-sync` 是本仓库里专门面向飞书云文档的同步型 skill，目标是把本地 Markdown 工作流逐步接到飞书 docx 文档上。

这篇文档是仓库级总览，重点说明它解决什么问题、当前做到哪一步、应该从哪里继续读。更细的命令规则和实现边界，放在 skill 目录内部的 `SKILL.md` 和 `references/` 里。

## 这个 Skill 解决什么问题

当你需要把本地 Markdown 与飞书云文档协同起来时，这个 skill 可以作为统一入口。它主要覆盖三类工作：

- 认证与权限校验
- 本地 Markdown 到飞书 docx 的写入与更新
- 本地目录与远程文档映射的维护

## 两种身份模式

这个 skill 同时考虑两种调用身份：

- `tenant` 模式
  以应用身份访问飞书资源，适合自动化、脚本化、定时任务和 app 可见范围内的同步。
- `user` 模式
  以用户身份访问飞书资源，适合“按某个用户自己的可见范围”来读取或同步文档。

当前进展并不完全对称：

- `tenant` 模式已经有真实读写链路。
- `user` 模式目前主要完成了授权 URL、授权码换 token、本地回调接码等认证基础设施；用户视角下的文档同步能力还在继续补。

## 当前已实测能力

截至 2026-03-15，本仓库已经做过真实飞书联调验证的 tenant 能力包括：

- 获取 `tenant_access_token`
- 创建 docx 文档
- 读取文档基本信息
- 读取文档纯文本内容
- 列出 app 可见根目录文件
- 递归列出指定 folder 下的可见文件
- 单文档 `pull-markdown`
- 目录级 `pull-dir`
- 单文档高保真 `pull-markdown --fidelity high`
- 目录级高保真 `pull-dir --fidelity high`
- 目录级 `sync-dir --dry-run`
- 目录级 `sync-dir --prune --confirm-prune`
- 显式媒体上传 `upload-media`
- 将 Markdown 转换为飞书文档块并追加到远程文档
- 清空远程文档正文后再写入新的 Markdown
- 执行单文件 `push-markdown`
- 执行目录级 `push-dir`
- 执行带远程目录镜像的 `push-dir --mirror-remote-folders`
- 将同步结果写回本地 `feishu-index.json`
- 删除远程测试文档

这意味着 tenant 模式已经不只是“规划脚手架”，而是具备了第一批真实可执行的 Markdown 同步能力。

## 当前推荐使用路径

如果你的目标是“尽快跑通 Markdown 到飞书”的最短路径，建议按这个顺序：

1. 先看 [../skills/feishu-doc-sync/references/auth.md](../skills/feishu-doc-sync/references/auth.md)
2. 再看 [../skills/feishu-doc-sync/references/tenant-mode.md](../skills/feishu-doc-sync/references/tenant-mode.md)
3. 然后看 [../skills/feishu-doc-sync/references/sync-rules.md](../skills/feishu-doc-sync/references/sync-rules.md)
4. 真正执行时，再打开 [../skills/feishu-doc-sync/SKILL.md](../skills/feishu-doc-sync/SKILL.md)

如果你只是要快速判断当前能不能直接用，可以重点看这些命令：

- `tenant-token`
- `validate-tenant`
- `create-document`
- `get-document`
- `get-raw-content`
- `append-markdown`
- `replace-markdown`
- `push-markdown`
- `push-dir`
- `pull-markdown`
- `pull-dir`
- `upload-media`
- `sync-dir --dry-run`
- `sync-dir --dry-run --detect-conflicts`
- `sync-dir --prune --confirm-prune`

## 当前边界

虽然 tenant 模式已经打通了第一条真实写入链路，但这还不是“全量完成”的飞书同步器。当前仍然存在这些明确边界：

- user 模式还没有补齐用户视角的文档同步能力
- 高保真 pull/export 目前只覆盖常见 block，复杂表格、嵌入块和部分高级结构仍需继续补
- 媒体上传已经可执行，但图片/附件到 Markdown 的自动回填还没有进入当前执行链路
- 已经具备基于 sync baseline 的 drift / conflict detection，但还没有块级 diff、冲突合并和双向自动 merge
- `replace-markdown` 当前聚焦根文档正文替换，不处理更复杂的嵌套块树编辑
- `sync-dir` 目前只开放了 prune 执行，混合 push/pull 仍未进入执行阶段

## 对应仓库位置

- [../skills/feishu-doc-sync/SKILL.md](../skills/feishu-doc-sync/SKILL.md)
- [../skills/feishu-doc-sync/references/auth.md](../skills/feishu-doc-sync/references/auth.md)
- [../skills/feishu-doc-sync/references/token.md](../skills/feishu-doc-sync/references/token.md)
- [../skills/feishu-doc-sync/references/tenant-mode.md](../skills/feishu-doc-sync/references/tenant-mode.md)
- [../skills/feishu-doc-sync/references/user-mode.md](../skills/feishu-doc-sync/references/user-mode.md)
- [../skills/feishu-doc-sync/references/sync-rules.md](../skills/feishu-doc-sync/references/sync-rules.md)

## 2026-03-15 Tenant Pull Additions

The tenant-mode baseline in this repo now also includes:

- `list-folder-files`
- `pull-markdown`
- `pull-dir`
- `sync-dir --dry-run`

These additions make the skill more useful for long-running tenant workflows because it can now:

- inspect app-visible nested folders instead of only the root
- export low-fidelity local Markdown from Feishu `raw_content`
- rebuild a local Markdown directory from the visible remote folder tree
- preview remote pull candidates, prune candidates, and visibility risks before later mixed sync work

## 2026-03-15 Tenant Folder Mirror Additions

本轮继续把 tenant 侧的目录同步往前推了一步，新增了：

- `push-dir --mirror-remote-folders`

这让当前 skill 在“本地 Markdown 目录结构要尽量映射到飞书目录结构”的场景下更实用了，因为它现在可以：

- 以 `--folder-token` 作为远程镜像根目录
- 仅对“尚未绑定 doc token、也没有显式 folder token”的新建文档推导远程目录
- 按本地相对目录逐级补建远程 folder
- 把最终使用的 `folder_token` 回写到 `feishu-index.json`

这意味着 tenant 模式已经不只是“单文件 push / 目录遍历 push”，而是开始具备了第一版目录镜像式写入能力。

## 2026-03-15 Tenant Prune Execution Additions

本轮又把 `sync-dir` 从纯规划往前推进了一步，新增了：

- `sync-dir --prune --confirm-prune`

这让当前 skill 在“本地文件已经删除，但远程飞书文档还留着”的场景下更可控，因为它现在可以：

- 基于同一套 dry-run 可见性扫描重建 prune candidate
- 在执行前自动创建 `.feishu-sync-backups/<timestamp>` 备份目录
- 先快照当前 `feishu-index.json` 和 sync plan
- 先导出待删远程文档的低保真备份，再执行删除
- 仅对删除成功的候选清理 `feishu-index.json`

这意味着第一阶段的“显式确认 prune + 备份 + index 清理”已经落地。

## 2026-03-15 Tenant Export And Media Additions

这一轮把第二阶段也往前推进了一段，新增了：

- `pull-markdown --fidelity high`
- `pull-dir --fidelity high`
- `upload-media`

这让当前 skill 在“要把飞书文档重新拉回本地 Markdown，并尽量保留结构”的场景下更实用了，因为它现在可以：

- 在 `raw_content` 低保真导出之外，基于 block tree 重建常见 Markdown 结构
- 在 front matter 中写回 `feishu_pull_fidelity`
- 对 heading、paragraph、list、quote、code、todo、callout、基础 image/file 引用做第一版高保真映射
- 显式上传图片或附件到 docx 工作流，并拿到 `file_token`

当前第二阶段还没有完全收口的部分是：

- 更复杂 block 的覆盖率还要继续补
- `push-markdown` / `push-dir` 还不会自动把本地图片引用改写成上传后的飞书媒体块
- prune 备份仍然使用低保真 `raw_content`

## 2026-03-15 Tenant Conflict Detection Additions

这一轮开始把第三阶段落成第一刀，新增了：

- `sync-dir --dry-run --detect-conflicts`

这让当前 skill 在“还不准备自动执行，但需要先知道本地和远端谁变了、变到什么程度”的场景下更有用了，因为它现在可以：

- 在 `feishu-index.json` 中记录 `body_hash`、`remote_revision_id`、`remote_content_hash` 这类同步基线
- 在 dry-run 中额外检查已映射且当前可见的远端文档
- 区分 `local_ahead`、`remote_ahead`、`local_and_remote_changed`、`baseline_incomplete`
- 按当前 `sync_direction` 给出 `push_candidate`、`pull_candidate`、`review_before_push`、`manual_conflict_review` 这类推荐动作

这一层目前仍然是“检测和分类”，不是“自动执行”：

- 还没有块级文本 diff
- 还没有自动冲突合并
- 还没有真正的 bidirectional execution

## 后续优化规划

建议后续继续按这两个方向推进：

1. 保真度收口
   继续补全高保真 block 覆盖、图片/附件自动映射、以及 prune 备份的 richer export。
2. 协同决策层
   在现在这版 review-first conflict detection 上，继续补块级 diff、冲突处置策略，以及真正的双向执行链路。
