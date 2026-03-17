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
- `user` 模式现在已经有授权 URL、授权码换 token、本地回调接码，以及第一版用户视角读链路和受保护的单文档写链路；目录级写入和双向同步仍在继续补。

## 当前已实测能力

截至 2026-03-16，本仓库已经做过真实飞书联调验证的 tenant 能力包括：

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
- 目录级 `sync-dir --dry-run --detect-conflicts --include-diff`
- 目录级 `sync-dir --execute-bidirectional --confirm-bidirectional`
- 目录级 `sync-dir --execute-bidirectional --confirm-bidirectional --allow-auto-merge --adopt-remote-new --include-create-flow`
- 目录级 `sync-dir --prune --confirm-prune`
- 显式媒体上传 `upload-media`
- 将 Markdown 转换为飞书文档块并追加到远程文档
- 清空远程文档正文后再写入新的 Markdown
- 执行单文件 `push-markdown`
- 执行目录级 `push-dir`
- 执行带远程目录镜像的 `push-dir --mirror-remote-folders`
- 将同步结果写回本地 `feishu-index.json`
- 删除远程测试文档

截至 2026-03-17，本仓库也已经补上第一版 user 能力：

- `validate-user`
- `get-document --auth-mode user`
- `get-raw-content --auth-mode user`
- `list-root-files --auth-mode user`
- `list-folder-files --auth-mode user`
- `pull-markdown --auth-mode user`
- `pull-dir --auth-mode user`
- `append-markdown --auth-mode user --confirm-user-write`
- `replace-markdown --auth-mode user --confirm-user-write --confirm-replace`
- `push-markdown --auth-mode user --confirm-user-write`
- `push-markdown --auth-mode user --confirm-user-write --allow-user-create`
- `push-dir --auth-mode user --confirm-user-write`
- `push-dir --auth-mode user --confirm-user-write --allow-user-create`
- `sync-dir --auth-mode user --dry-run`
- `sync-dir --auth-mode user --dry-run --detect-conflicts`
- `sync-dir --auth-mode user --execute-bidirectional --confirm-bidirectional --confirm-user-write`
- `sync-dir --auth-mode user --execute-bidirectional --confirm-bidirectional --confirm-user-write --include-create-flow --allow-user-create`

这意味着 user 模式已经不再只是“拿 token 的授权脚手架”，而是具备了第一批真正可执行的用户视角读取、导出和受保护单文档写入能力。

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
- `validate-user`
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
- `sync-dir --dry-run --detect-conflicts --include-diff`
- `sync-dir --execute-bidirectional --confirm-bidirectional`
- `sync-dir --prune --confirm-prune`

## 当前边界

虽然 tenant 模式已经打通了第一条真实写入链路，但这还不是“全量完成”的飞书同步器。当前仍然存在这些明确边界：

- user 模式现在已经支持受保护的单文档和目录级 `push-dir`，以及 user-visible 的 `sync-dir` dry-run / protected bidirectional execution；远程 prune delete 仍然保持 tenant-only
- 高保真 pull/export 目前只覆盖常见 block，复杂表格、嵌入块和部分高级结构仍需继续补
- 媒体上传已经可执行，但图片/附件到 Markdown 的自动回填还没有进入当前执行链路
- 已经具备基于 sync baseline 的 drift / conflict detection，能给出语义级块预览、行级 diff 预览，以及基于 baseline 的语义 merge suggestion
- `replace-markdown` 当前聚焦根文档正文替换，不处理更复杂的嵌套块树编辑
- `sync-dir` 虽然已经开放了受保护的 bidirectional execution，并且可通过显式开关纳入 safe auto-merge、unmapped remote adoption、create flow，但默认仍然是 review-first，不会自动处理重叠冲突

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

## 2026-03-16 Tenant Conflict Diff Preview Additions

这一轮继续沿着第三阶段往前补了一层，新增了：

- `sync-dir --dry-run --detect-conflicts --include-diff`
- `--diff-fidelity low|high`
- `--diff-max-lines <N>`

这让当前 skill 在“需要先人工 review 本地和远端到底差在哪，再决定 push / pull / 暂缓处理”的场景下更顺手，因为它现在可以：

- 在现有 drift / conflict classification 结果旁边附带语义级块预览
- 同时保留截断版 line diff 方便精确核对 Markdown
- 默认用 `raw_content` 导出的可比较正文做 diff
- 在 `--diff-fidelity high` 下优先基于 block tree 重建常见 Markdown 结构后再做 diff
- 用 `--diff-max-lines` 控制每个文件返回的 diff 规模，避免 dry-run 输出失控

在当时那一版里，这一层依然是 review-first，不是自动执行：

- 还没有自动冲突合并
- 还没有真正的 bidirectional execution

## 2026-03-16 Tenant Semantic Diff And Protected Bidirectional Execution

这一轮继续把第三阶段往前推了一步，新增了：

- 语义级块 diff preview
- `sync-dir --execute-bidirectional --confirm-bidirectional`
- `--pull-fidelity low|high`

这让当前 skill 在“已经完成 mapping，并且只想让 clean push / clean pull 自动执行，但又不想放弃安全边界”的场景下更可用了，因为它现在可以：

- 先基于同一套 conflict detection 自动重建执行前计划
- 仅执行 `bidirectional` 文件里被判定为 `local_ahead` 或 `remote_ahead` 的候选
- 在 push 前备份当前远端飞书文档
- 在 pull 前备份当前本地 Markdown 文件
- 对 `local_and_remote_changed`、`baseline_incomplete`、不可见映射和缺失 doc token 的项直接拦截，不进入执行

这一层当前的边界仍然很明确：

- 默认不会自动 merge 本地和远端改动
- 默认不会自动为 unmapped remote doc 建立 bidirectional 映射
- 默认不会把 create flow 和 remote pull candidate 自动并进 bidirectional execution

## 2026-03-16 Tenant Semantic Merge Suggestions And Expanded Bidirectional Execution

这一轮把上面那层再往前补了一段，新增了：

- `local_and_remote_changed` 项的 baseline-aware semantic merge suggestion
- `sync-dir --execute-bidirectional --confirm-bidirectional --allow-auto-merge`
- `sync-dir --execute-bidirectional --confirm-bidirectional --adopt-remote-new`
- `sync-dir --execute-bidirectional --confirm-bidirectional --include-create-flow`

这让当前 skill 在“我愿意继续坚持保护边界，但希望一部分明确安全的 review 项能直接往前走”的场景下更实用了，因为它现在可以：

- 从 `baseline_body_snapshot`、当前本地正文和可比较的远端正文里推导语义 merge suggestion
- 只对“非重叠语义变化”的 `local_and_remote_changed` 项开放 opt-in auto-merge
- 把当前可见但尚未映射的 remote doc 作为受保护的 bidirectional adopt pull 处理
- 把本地未映射的 bidirectional 文件作为受保护的 create flow 处理
- 在 merge push 前同时备份本地和远端，并在 push 失败时回滚本地合并结果

这一层仍然保留明确边界：

- 不会自动解决重叠冲突或语义不明确的 merge
- 不会默认开启 auto-merge、remote adoption 或 create flow
- 还没有进入更强的媒体自动回填和全量 block round-trip

## 后续优化规划

建议后续继续按这两个方向推进：

1. 保真度收口
   继续补全高保真 block 覆盖、图片/附件自动映射、以及 prune 备份的 richer export。
2. 协同决策层
   在现在这版带语义 diff preview 和 protected bidirectional execution 的 review-first conflict detection 上，继续补冲突处置策略、语义 merge 建议，以及更广覆盖的双向执行链路。
