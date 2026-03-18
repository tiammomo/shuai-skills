# Shuai Skills

这个仓库用于沉淀、维护和扩展可复用的 skills。它既包含可直接调用的业务 skill，也包含围绕 skill 设计、校验和维护的仓库级规范。

## 什么是渐进式 skill

这个仓库把 skill 统一设计成“渐进式加载”能力包，而不是把所有背景、规则和实现都堆进一个 `SKILL.md`。

一个渐进式 skill 通常按三层加载：

1. frontmatter：只负责触发，说明“做什么”和“什么时候用”。
2. `SKILL.md`：只保留任务路由、安全约束和默认工作流。
3. `references/`、`scripts/`、`assets/`：只在当前任务真的需要时再读取或执行。

这样做的目标很简单：

- 让 skill 更容易触发。
- 让上下文更节省。
- 让脚本和参考资料更容易复用。
- 让后续扩展不会把 `SKILL.md` 变成超长说明书。

## 仓库级约束

本仓库里的 skill 默认遵守这些规则：

- `SKILL.md` frontmatter 只保留 `name` 和 `description`。
- `description` 要同时写清“做什么”和“Use when ...”触发场景。
- `SKILL.md` 至少包含 `## Task Router`、`## Progressive Loading`、`## Default Workflow`。
- `SKILL.md` 默认控制在 500 行以内；超过这个量级优先拆到 `references/`。
- `references/` 只放按需加载的规则、接口、专题说明，不放仓库级 README。
- `scripts/` 只放需要稳定执行或反复复用的实现。
- `assets/` 只放模板和输出资源，不放长篇说明。
- reference 导航尽量保持从 `SKILL.md` 一跳可达，避免多层跳转。

## 当前 Skills

截至 2026-03-18，这个仓库主要维护两个业务 skill：

| Skill | 平台 | 当前状态 | 代表能力 | 入口 |
| --- | --- | --- | --- | --- |
| `yuque-openapi` | 语雀 | 比较成熟 | 单文档 push/pull、目录规划、TOC 重建、快照恢复、manifest 批处理、review diff/report | [docs/yuque-openapi.md](./docs/yuque-openapi.md) |
| `feishu-doc-sync` | 飞书云文档 | 主链路已完整可用 | tenant/user 双模式读写、目录级 push/pull、`sync-dir` dry-run / conflict detection / protected bidirectional sync / prune、媒体上传与回填、高保真导出 | [docs/feishu-doc-sync.md](./docs/feishu-doc-sync.md) |

## 仓库级检查

当前仓库把“渐进式结构检查”和业务 smoke check 都固定成了可重复执行的入口：

- `python scripts/check_progressive_skills.py`
- `python skills/feishu-doc-sync/scripts/check_feishu_skill.py`
- `python skills/yuque-openapi/scripts/check_yuque_skill.py`

其中 `check_progressive_skills.py` 会检查 `SKILL.md` 结构、长 reference 的 `## Contents` 导航，以及 reference 是否能从 `SKILL.md` 在两跳内到达。两个业务 `check_*.py` 也建议统一支持 `--validator`、`--skip-selftest`、`--skip-validate`、`--skip-help-smoke`。

GitHub Actions 也会自动跑这些检查，确保 skill 结构和业务能力一起回归。

## 如何使用这个仓库

如果你想直接使用已有 skill：

1. 先看业务说明文档：
   [docs/yuque-openapi.md](./docs/yuque-openapi.md) 或 [docs/feishu-doc-sync.md](./docs/feishu-doc-sync.md)
2. 再打开对应 skill 的 `SKILL.md`，只按任务需要读取 router 指向的 `references/`
3. 需要执行或排查实现时，再进入 `scripts/`

如果你想新增或维护 skill：

1. 学习路径：看 [docs/skill-learning-guide.md](./docs/skill-learning-guide.md)
2. 实战模板：看 [docs/skill-design-template.md](./docs/skill-design-template.md)
3. 快速起步：看 [docs/skill-quickstart.md](./docs/skill-quickstart.md)
4. 完整流程：看 [docs/skill-authoring.md](./docs/skill-authoring.md)
5. 结构规范：看 [docs/skill-spec.md](./docs/skill-spec.md)

## 文档导航

- [docs/README.md](./docs/README.md)：文档总览。
- [docs/skill-learning-guide.md](./docs/skill-learning-guide.md)：结合飞书和语雀 skill 学习如何阅读和构建 skill。
- [docs/skill-design-template.md](./docs/skill-design-template.md)：从需求到 skill 设计表的实战模板。
- [docs/skill-quickstart.md](./docs/skill-quickstart.md)：最小可用 skill 的快速起步。
- [docs/skill-authoring.md](./docs/skill-authoring.md)：如何在本仓库里制作和迭代 skill。
- [docs/skill-spec.md](./docs/skill-spec.md)：渐进式 skill 的结构规范和校验要求。
- [docs/yuque-openapi.md](./docs/yuque-openapi.md)：语雀 sync skill 的仓库级说明。
- [docs/feishu-doc-sync.md](./docs/feishu-doc-sync.md)：飞书 sync skill 的仓库级说明。

## License

本仓库采用 Apache License 2.0。完整内容见 [LICENSE](./LICENSE)。
