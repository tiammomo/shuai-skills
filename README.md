# Shuai Skills

这个仓库用于沉淀、维护和扩展可复用的 skills。它既包含可直接调用的真实 skill，也包含如何创建、验证、维护 skill 的配套文档。

## Skills 是什么

你可以把 skill 理解成一个面向 Codex 或 agent 的“能力包”。它不是单篇说明文档，而是一组围绕某类任务组织起来的可复用资源，通常包含：

- `SKILL.md`
  作为入口说明，定义这个 skill 做什么、什么时候触发、先读哪些参考资料。
- `agents/openai.yaml`
  作为 UI 和调用侧的元数据。
- `scripts/`
  放稳定、可重复执行的脚本逻辑。
- `references/`
  放按需加载的接口文档、规则、工作流和领域知识。
- `assets/`
  放模板、样例或输出时会复用的资源。

## 如何使用这个仓库

如果你想直接使用仓库里已有的 skill，建议这样看：

1. 先看下面的“当前已有 Skills”，判断你要的是语雀同步还是飞书文档同步。
2. 再进入对应的仓库级文档：
   - [docs/yuque-openapi.md](./docs/yuque-openapi.md)
   - [docs/feishu-doc-sync.md](./docs/feishu-doc-sync.md)
3. 确认要落地执行时，再打开对应 skill 目录内的 `SKILL.md` 和 `references/`。

如果你想新建或扩展一个 skill，建议按这条路径：

1. 快速上手：
   看 [docs/skill-quickstart.md](./docs/skill-quickstart.md)
2. 完整制作流程：
   看 [docs/skill-authoring.md](./docs/skill-authoring.md)
3. 结构与规范：
   看 [docs/skill-spec.md](./docs/skill-spec.md)

## Skills 相关规范

本仓库里维护 skill 时，建议统一遵守这些基本规范：

- skill 名称使用小写字母、数字和连字符。
- `SKILL.md` frontmatter 只保留 `name` 和 `description`。
- `description` 要同时写清“做什么”和“什么时候用”。
- `SKILL.md` 保持精简，把详细说明拆到 `references/`。
- 反复执行、容易出错的逻辑放到 `scripts/`。
- 模板、样例和图标放到 `assets/`，不要塞进长说明里。
- `agents/openai.yaml` 中的 `default_prompt` 应显式提到 `$skill-name`。
- 新增或修改 skill 后，至少做一轮结构校验，必要时补脚本 smoke check 或自测。

更完整的规范说明见 [docs/skill-spec.md](./docs/skill-spec.md)。

## 当前已有 Skills

截至 2026-03-17，这个仓库已经有两个方向明确、可直接继续扩展的真实 skill：

| Skill | 主要平台 | 当前状态 | 代表能力 | 仓库级文档 |
| --- | --- | --- | --- | --- |
| `yuque-openapi` | 语雀 | 较成熟 | 单文档推送/拉取、目录级增量同步、TOC 重建、快照恢复、批量 manifest、Repo/Doc CRUD、原始 API 调用 | [docs/yuque-openapi.md](./docs/yuque-openapi.md) |
| `feishu-doc-sync` | 飞书云文档 | tenant / user 主链路已可用，仍在持续增强 | tenant/user 鉴权、单文档读写、目录级 push/pull、`sync-dir` dry-run / conflict detection / protected bidirectional execution / prune、`feishu-index.json` 回写 | [docs/feishu-doc-sync.md](./docs/feishu-doc-sync.md) |

## 仓库级检查

当前仓库已经把两个业务 skill 的离线检查固定成统一入口，并新增了 GitHub Actions 工作流自动跑：

- `python skills/feishu-doc-sync/scripts/check_feishu_skill.py`
- `python skills/yuque-openapi/scripts/check_yuque_skill.py`

在 GitHub Actions 里，这两个检查会以 `--skip-validate` 运行，避免依赖本地 `skill-creator` 校验脚本路径，同时保留 smoke/selftest 与 CLI help 回归。

## 如何选择 Skill

- 如果你的目标是“本地 Markdown 与语雀知识库协同”，优先看 `yuque-openapi`。
- 如果你的目标是“本地 Markdown 与飞书云文档协同”，优先看 `feishu-doc-sync`。
- 如果你的目标是“继续给仓库新增一个新的 skill”，先看 `skill-quickstart`、`skill-authoring` 和 `skill-spec`。

## 文档导航

- [docs/README.md](./docs/README.md)：文档总览与阅读顺序。
- [docs/yuque-openapi.md](./docs/yuque-openapi.md)：语雀同步 skill 的仓库级能力说明。
- [docs/feishu-doc-sync.md](./docs/feishu-doc-sync.md)：飞书文档同步 skill 的仓库级能力说明。
- [docs/skill-quickstart.md](./docs/skill-quickstart.md)：快速上手创建一个新的 skill。
- [docs/skill-authoring.md](./docs/skill-authoring.md)：如何在本仓库中制作新的 skill。
- [docs/skill-spec.md](./docs/skill-spec.md)：skills 的结构规范、命名规范和编写约束。

## 两个已有 Skill 的定位

### `yuque-openapi`

这是当前仓库里最成熟的同步型 skill，主要解决本地 Markdown 与语雀知识库之间的协同问题，包括：

- 把本地 Markdown 推送到语雀。
- 把语雀文档或整个知识库导出回本地。
- 做目录级增量规划、冲突识别和双向同步。
- 根据本地目录结构重建远程 TOC，并在变更前自动快照备份。
- 通过 manifest 执行多仓库、批量、可复用的同步任务。

想继续看：

- [docs/yuque-openapi.md](./docs/yuque-openapi.md)
- [skills/yuque-openapi/SKILL.md](./skills/yuque-openapi/SKILL.md)

### `feishu-doc-sync`

这是面向飞书云文档的同步型 skill，当前重点放在本地 Markdown 与飞书 docx 文档之间的 tenant / user 双模式同步能力建设。

截至 2026-03-17，本仓库已经实测打通了：

- `tenant_access_token` / `user_access_token` 鉴权
- 创建文档
- 读取文档元数据与纯文本内容
- 列出 app 可见根目录文件
- 列出 user 可见根目录与目录树
- 追加 Markdown 到远程文档
- 替换远程文档正文
- 单文件 `push-markdown`
- 目录级 `push-dir`
- 目录级 `pull-dir`
- 目录级 `sync-dir --dry-run`
- 目录级 `sync-dir --dry-run --detect-conflicts --include-diff`
- 目录级 `sync-dir --execute-bidirectional --confirm-bidirectional`
- 目录级 `sync-dir --prune --confirm-prune`
- user 模式受保护的单文档与目录级 push / bidirectional sync
- `feishu-index.json` 自动回写

想继续看：

- [docs/feishu-doc-sync.md](./docs/feishu-doc-sync.md)
- [skills/feishu-doc-sync/SKILL.md](./skills/feishu-doc-sync/SKILL.md)

## 仓库结构

```text
.
|- skills/
|  |- yuque-openapi/
|  `- feishu-doc-sync/
`- docs/
```

## 后续扩展

这个仓库不会只停留在当前两个同步型 skill。后续还会继续加入更多面向不同工具、平台和任务场景的 skills。

新增 skill 时，建议同步完成这几件事：

- 在 `skills/<skill-name>/` 下维护 skill 本体。
- 在 `docs/` 下补对应的仓库级说明或教程入口。
- 在本 README 中补一行 skill 简介、状态和文档链接。

## License

本仓库采用 Apache License 2.0 开源协议。完整内容见 [LICENSE](./LICENSE)。
