# Shuai Skills

这个仓库用于沉淀、维护和扩展可复用的 skills。它既包含具体 skill 本体，也包含如何创建、使用和规范化维护 skills 的配套文档。

## Skills 是什么

skill 可以理解为一个面向 Codex 或 agent 的“能力包”。它不是普通说明文档，而是一组围绕某类任务组织起来的可复用资源，通常用来补充：

- 特定领域的工作流
- 稳定可执行的脚本
- 按需加载的参考资料
- 输出时要复用的模板或资源

在这个仓库里，一个 skill 通常由这些部分组成：

- `SKILL.md`
  skill 的入口文件，负责说明这个 skill 做什么、什么时候应该触发。
- `agents/openai.yaml`
  面向 UI 和调用入口的元数据。
- `scripts/`
  需要稳定执行、反复复用的脚本。
- `references/`
  详细说明、接口文档、规则或领域知识。
- `assets/`
  模板、样例、图标或输出资源。

## 如何创建和使用 Skills

如果你想在本仓库里新增一个 skill，或者想理解 skills 的推荐工作流，可以直接按这条路径读：

1. 快速开始：
   看 [docs/skill-quickstart.md](./docs/skill-quickstart.md)
2. 完整制作流程：
   看 [docs/skill-authoring.md](./docs/skill-authoring.md)
3. 结构和编写规范：
   看 [docs/skill-spec.md](./docs/skill-spec.md)

如果你想先快速做出一个最小可用的 skill，首页可以先记住这 3 步：

1. 运行 `init_skill.py` 在 `skills/` 下创建骨架目录。
2. 用最小模板补好 `SKILL.md` 和 `agents/openai.yaml`。
3. 运行 `quick_validate.py` 校验结构是否正确。

完整步骤、命令示例和可复制模板见 [docs/skill-quickstart.md](./docs/skill-quickstart.md)。

## Skills 相关规范

本仓库里维护 skill 时，建议统一遵守这些基本规范：

- skill 名称使用小写字母、数字和连字符。
- `SKILL.md` frontmatter 只保留 `name` 和 `description`。
- `description` 要同时写清“做什么”和“什么时候用”。
- `SKILL.md` 保持精简，把详细说明拆到 `references/`。
- 反复执行、容易出错的逻辑放到 `scripts/`。
- 模板、图标、样例资源放到 `assets/`，不要把它们塞进长文档。
- `agents/openai.yaml` 中的 `default_prompt` 要显式提到 `$skill-name`。
- 新增或修改 skill 后，至少做一轮结构校验，必要时补脚本验证。

更完整的规范说明见 [docs/skill-spec.md](./docs/skill-spec.md)。

## 文档导航

- [docs/README.md](./docs/README.md)：文档总览。
- [docs/skill-quickstart.md](./docs/skill-quickstart.md)：快速上手创建一个新的 skill。
- [docs/skill-authoring.md](./docs/skill-authoring.md)：如何在本仓库中制作新的 skill。
- [docs/skill-spec.md](./docs/skill-spec.md)：skills 的结构规范、命名规范和编写约束。
- [docs/yuque-openapi.md](./docs/yuque-openapi.md)：当前已有 `yuque-openapi` skill 的详细说明。

## 当前已有 Skill

目前这个仓库已经收录了一个可直接使用的 skill：

| Skill | 简介 | 核心能力 | 详细文档 |
| --- | --- | --- | --- |
| `yuque-openapi` | 一个跨平台的 Yuque OpenAPI 工作流 skill，面向 Markdown 文档与知识库协同。 | 单文档推送/拉取、整目录增量同步、TOC 重建、自动快照恢复、批量 manifest 执行、Repo/Doc CRUD、原始 API 调用。 | [docs/yuque-openapi.md](./docs/yuque-openapi.md) |

## `yuque-openapi`：本仓库当前示例 Skill

`yuque-openapi` 目前既是本仓库里已经可用的一个真实 skill，也是一个很适合拿来参考 skill 结构的样例。

它主要解决的是本地 Markdown 与语雀知识库之间的协同问题，包括：

- 把本地 Markdown 推送到语雀。
- 把语雀文档或整个知识库导出回本地。
- 对本地目录和远程知识库做增量规划、冲突识别和双向同步。
- 根据本地目录结构重建远程 TOC，并在变更前自动做快照备份。
- 通过 manifest 执行多仓库、批量、可复用的同步任务。
- 发现空间、知识库、文档，并执行基础 CRUD 操作。

如果你想看它的完整能力说明，可以从这些入口继续读：

- [docs/yuque-openapi.md](./docs/yuque-openapi.md)
- [skills/yuque-openapi/SKILL.md](./skills/yuque-openapi/SKILL.md)
- [skills/yuque-openapi/agents/openai.yaml](./skills/yuque-openapi/agents/openai.yaml)

这个 skill 还自带了基础检查能力，适合作为“如何给 skill 配检查入口”的参考：

- `scripts/selftest_yuque_api.py`
- `scripts/check_yuque_skill.py`

## 仓库结构

```text
.
|- skills/
|  |- yuque-openapi/
|     |- SKILL.md
|     |- scripts/
|     |- references/
|     |- assets/
|     `- agents/
`- docs/
```

## 后续扩展

当前仓库只收录了一个 `yuque-openapi` skill，但它不会是最后一个。后续这个仓库还会继续加入更多面向不同任务、工具和领域的 skills。

新增 skill 时，建议同步完成这几件事：

- 在 `skills/<skill-name>/` 下维护 skill 本体。
- 在 `docs/` 下补对应说明或教程入口。
- 在本 README 中补一行 skill 简介和文档链接。
