# Skills 规范说明

这篇文档总结的是“在本仓库里维护 skill 时，建议遵守的结构和编写规范”。它主要基于当前仓库实践，以及 `skill-creator` 的规则整理而成。

如果你想看从 0 到 1 的制作步骤，请先读 [skill-authoring.md](./skill-authoring.md)。

## 1. 目录结构规范

一个 skill 文件夹建议长成这样：

```text
skills/<skill-name>/
|- SKILL.md
|- agents/
|  `- openai.yaml
|- scripts/
|- references/
`- assets/
```

其中：

- `SKILL.md` 必须存在。
- `agents/openai.yaml` 推荐存在。
- `scripts/`、`references/`、`assets/` 按需要创建，不需要时不要硬加。

## 2. 命名规范

skill 名称建议遵守这些规则：

- 只用小写字母、数字和连字符。
- 目录名和 skill 名保持一致。
- 尽量短、小而准。
- 名称要能反映动作或能力，而不是宽泛名词。

例如：

- `yuque-openapi`
- `gh-fix-ci`
- `skill-creator`

不推荐：

- `MySkill`
- `tools_for_docs`
- `all-in-one-helper`

## 3. `SKILL.md` frontmatter 规范

`SKILL.md` 顶部必须带 YAML frontmatter，而且只保留这两个字段：

```yaml
---
name: my-skill
description: Clear description of what the skill does and when to use it.
---
```

规范要点：

- `name`
  必须等于 skill 名。
- `description`
  要同时写“做什么”和“什么时候用”。
- 不要在 frontmatter 里随意加别的字段。

## 4. `description` 的编写规范

`description` 是 skill 最关键的触发信息之一，所以建议写得尽量明确。

应该包含：

- skill 提供什么能力。
- 适用于什么文件、场景、工具或任务。
- 用户可能会怎么描述这个需求。

不建议只写很泛的句子，比如：

- “A helpful skill.”
- “Use for many tasks.”
- “Document related helper.”

更好的写法是：

- “Cross-platform workflow for syncing local Markdown files or whole Markdown directories with Yuque knowledge bases...”

也就是像当前 [`skills/yuque-openapi/SKILL.md`](../skills/yuque-openapi/SKILL.md) 这样，把功能和触发场景一起写进描述里。

## 5. `SKILL.md` 正文规范

正文建议只保留真正必要的执行说明，不要写成泛化 README。

推荐保留：

- 简短目标说明
- 安全约束
- 任务路由
- 默认工作流
- 资源说明

不推荐塞进 `SKILL.md` 的内容：

- 过长的背景介绍
- 大段安装说明
- 大量和执行无关的设计讨论
- 面向人类读者的冗余教程

一句话原则：

- 核心流程写进 `SKILL.md`
- 详细材料拆进 `references/`

## 6. 正文措辞规范

建议使用偏命令式、执行式的写法，例如：

- “Use the bundled Python CLI...”
- “Read `references/dir-sync.md`.”
- “Run `validate-manifest` before execution.”

尽量避免：

- 过多铺垫性叙述
- 长篇背景理论
- 大段“为什么我这样设计”的创作说明

因为 skill 是给 agent 执行时用的，最重要的是“可行动性”和“可路由性”。

## 7. Progressive Disclosure 规范

skill 应尽量遵守“渐进披露”原则，也就是：

1. 先靠 frontmatter 触发
2. 再加载 `SKILL.md`
3. 需要时再读 `references/` 或执行 `scripts/`

这意味着：

- `SKILL.md` 要尽量精简。
- 大块说明、接口文档、策略细节应拆去 `references/`。
- 不要把所有内容都堆在一个文件里。

一个比较好的模式就是当前 `yuque-openapi`：

- `SKILL.md` 只做任务路由和总流程说明。
- 各专题细节分散在 `references/dir-sync.md`、`references/toc-sync.md`、`references/manifest.md` 等文件中。

## 8. `scripts/` 规范

什么时候应该放脚本：

- 同一段逻辑会反复重写。
- 这个操作容易出错，需要更高确定性。
- 需要对外暴露稳定参数和稳定输出。

脚本编写建议：

- 尽量让输入输出清晰。
- 报错信息要能帮助定位问题。
- 对关键路径提供最小验证。
- 新增脚本后最好实际跑一遍，而不是只写不测。

## 9. `references/` 规范

适合放进 `references/` 的内容包括：

- 详细接口说明
- 领域知识
- 公司规则
- 专题工作流
- 疑难排查说明

推荐做法：

- 按主题拆文件。
- 大文件前面加目录。
- 在 `SKILL.md` 里明确写出“什么时候该读哪一份 reference”。

不推荐做法：

- 把所有参考资料堆进一个超长文件。
- 让 reference 再层层跳转，过度嵌套。

## 10. `assets/` 规范

`assets/` 放的是“输出时要用的资源”，而不是“给模型读的长文档”。

适合放：

- 模板
- 图标
- 示例清单
- 样例输入输出
- 前端骨架

例如本仓库里的 [`skills/yuque-openapi/assets/manifests/`](../skills/yuque-openapi/assets/manifests/) 就是典型用途：放可复用的批量任务模板。

## 11. `agents/openai.yaml` 规范

推荐保留一个最小但可用的 `agents/openai.yaml`：

```yaml
interface:
  display_name: "Human-friendly name"
  short_description: "Short UI description"
  default_prompt: "Use $my-skill to do ..."
```

几个关键约束：

- 字符串值统一加引号。
- `default_prompt` 要显式提到 `$skill-name`。
- 只在确实需要时再补图标、品牌色、依赖等扩展字段。

当前 [`skills/yuque-openapi/agents/openai.yaml`](../skills/yuque-openapi/agents/openai.yaml) 可以作为一个简单参考。

## 12. 不要往 skill 目录里放什么

skill 目录内不建议放仓库式杂项文件，例如：

- `README.md`
- `CHANGELOG.md`
- `INSTALLATION_GUIDE.md`
- `QUICK_REFERENCE.md`

原因不是这些文件没价值，而是：

- 对 agent 执行帮助不大
- 会增加上下文噪音
- 会让 skill 目录边界变得模糊

如果你确实想写“给人看的说明”，更适合放在本仓库的 `docs/` 下，就像这篇文档这样。

## 13. 验证规范

新增或修改 skill 后，至少建议做两类验证：

1. 结构校验
2. 代表性运行验证

结构校验可以用 `skill-creator` 提供的校验脚本。

如果 skill 内有脚本，建议至少验证：

- 脚本能运行
- 关键参数没问题
- 输出格式稳定
- 报错信息可读

如果 skill 足够复杂，最好像当前 `yuque-openapi` 一样，再提供一个统一检查入口。

## 14. 本仓库内的推荐提交规范

在这个仓库里维护 skill 时，比较推荐：

- skill 功能改动和文档改动尽量一起提交。
- 新增脚本时同时补最小验证。
- 新增 `references/` 时同时更新 `SKILL.md` 路由。
- 新增 skill 时同时更新根目录 `README.md` 和 `docs/README.md`。

这样做的好处是：

- 仓库首页始终能反映真实能力。
- `docs/` 不会和 `skills/` 脱节。
- 后续维护者更容易理解每个 skill 的边界。

## 15. 一个可直接套用的检查清单

在提交前，可以快速自查：

- skill 名是否符合小写连字符规则？
- `SKILL.md` 是否包含且仅包含 `name`、`description` 两个 frontmatter 字段？
- `description` 是否写清“做什么”和“什么时候用”？
- `SKILL.md` 是否足够精简，没有把细节全堆进去？
- `references/` 是否按主题拆分？
- `scripts/` 是否真的跑过？
- `agents/openai.yaml` 是否和 skill 内容匹配？
- 仓库级文档是否同步更新？
