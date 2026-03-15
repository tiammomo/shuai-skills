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
- 将 Markdown 转换为飞书文档块并追加到远程文档
- 清空远程文档正文后再写入新的 Markdown
- 执行单文件 `push-markdown`
- 执行目录级 `push-dir`
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

## 当前边界

虽然 tenant 模式已经打通了第一条真实写入链路，但这还不是“全量完成”的飞书同步器。当前仍然存在这些明确边界：

- user 模式还没有补齐用户视角的文档同步能力
- pull/export 还没有实现为高保真 Markdown 回写
- 媒体上传、图片/附件同步还没有进入当前执行链路
- 还没有做块级 diff、冲突合并和双向自动 merge
- `replace-markdown` 当前聚焦根文档正文替换，不处理更复杂的嵌套块树编辑

## 对应仓库位置

- [../skills/feishu-doc-sync/SKILL.md](../skills/feishu-doc-sync/SKILL.md)
- [../skills/feishu-doc-sync/references/auth.md](../skills/feishu-doc-sync/references/auth.md)
- [../skills/feishu-doc-sync/references/token.md](../skills/feishu-doc-sync/references/token.md)
- [../skills/feishu-doc-sync/references/tenant-mode.md](../skills/feishu-doc-sync/references/tenant-mode.md)
- [../skills/feishu-doc-sync/references/user-mode.md](../skills/feishu-doc-sync/references/user-mode.md)
- [../skills/feishu-doc-sync/references/sync-rules.md](../skills/feishu-doc-sync/references/sync-rules.md)
