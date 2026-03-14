# Shuai Skills

这个仓库用于沉淀和维护可复用的 skill。目前仓库中的能力以语雀 OpenAPI 工作流为主，重点解决本地 Markdown 与语雀知识库之间的同步、导出、批量执行与结构维护问题。

## 当前 Skills

| Skill | 简介 | 核心能力 | 详细文档 |
| --- | --- | --- | --- |
| `yuque-openapi` | 一个跨平台的 Yuque OpenAPI 工作流 skill，面向 Markdown 文档与知识库协同。 | 单文档推送/拉取、整目录增量同步、TOC 重建、自动快照恢复、批量 manifest 执行、Repo/Doc CRUD、原始 API 调用。 | [docs/yuque-openapi.md](./docs/yuque-openapi.md) |

## 能力概览

当前仓库里已有的 skill 主要覆盖下面几类场景：

- 把本地生成的 Markdown 文档推送到语雀知识库。
- 把语雀中的文档或整个知识库导出回本地 Markdown。
- 对本地目录和远程知识库做增量规划、冲突识别和双向同步。
- 从本地目录结构重建语雀目录树和 TOC，并在变更前自动做快照备份。
- 通过 manifest 模板执行多仓库、批量、可复用的同步任务。
- 发现空间、知识库、文档，并执行基础的创建、更新、删除等操作。

## 文档导航

- [docs/README.md](./docs/README.md)：文档总览。
- [docs/yuque-openapi.md](./docs/yuque-openapi.md)：`yuque-openapi` 的详细能力、作用、适用场景和工作流说明。
- [skills/yuque-openapi/SKILL.md](./skills/yuque-openapi/SKILL.md)：skill 原始定义。

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

## 说明

当前仓库只收录了一个 `yuque-openapi` skill，所以首页保持简洁，把详细能力拆到了 `docs/` 中。后续如果新增其他 skills，可以按相同结构继续补充：

- 在 `skills/<skill-name>/` 下维护 skill 本体。
- 在 `docs/` 下新增对应的详细介绍文档。
- 在本 README 中补一行简要能力说明和文档链接。
