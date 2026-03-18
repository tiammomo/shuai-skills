# Skills 制作指南

这篇文档面向“想在本仓库继续新增或升级 skill 的人”。重点不是解释什么是 skill，而是给出一条可落地、可维护、符合渐进式设计的制作路径。

如果你只想先做出一个最小版本，先看 [skill-quickstart.md](./skill-quickstart.md)；如果你想核对规则边界，再看 [skill-spec.md](./skill-spec.md)。

## 制作目标

一个成熟 skill 至少应该满足这几件事：

- 能被正确触发
- `SKILL.md` 足够短，能做路由而不是堆文档
- 复杂说明拆到了 `references/`
- 可重复执行的逻辑沉淀到了 `scripts/`
- 有最小可回归的检查入口

## 推荐制作流程

### 1. 先收窄边界

开工前先回答四个问题：

1. 这个 skill 解决哪一类任务？
2. 用户通常会怎么描述这个需求？
3. 哪些知识是模型记忆不稳定、必须显式提供的？
4. 哪些步骤适合做成脚本，而不是每次重写？

如果这一步没想清楚，最常见的问题就是：

- `description` 写得太泛，触发不准
- `SKILL.md` 越写越长，最后变成总说明

### 2. 先设计渐进式结构

在写任何文档之前，先确定三层内容怎么分：

- frontmatter：只负责触发
- `SKILL.md`：只负责路由、安全约束和默认工作流
- `references/`、`scripts/`、`assets/`：按需进入

一个很实用的判断标准：

- 需要稳定执行、会反复复用：放 `scripts/`
- 很长、不是每次都要读：放 `references/`
- 用于输出，不是用于加载到上下文：放 `assets/`

如果 reference 文件会长到难以快速扫读，默认在顶部补一个 `## Contents`。本仓库当前把“超过 100 行的 reference 必须带 `## Contents`，而且要覆盖后续所有二级章节”作为渐进式导航基线。

同时把 reference 的可达性也当成结构约束：每个 `references/*.md` 都应该能从 `SKILL.md` 直达，或者通过一个已经在 `SKILL.md` 暴露的 reference 路由页在两跳内到达。不要让 reference 再继续套 reference，最后只有深层链路才能找到。

### 3. 初始化 skill 目录

建议用 `skill-creator` 初始化骨架：

```text
python <CODEX_HOME>/skills/.system/skill-creator/scripts/init_skill.py my-skill --path skills --resources scripts,references,assets --interface display_name="My Skill" --interface short_description="Short UI summary." --interface default_prompt="Use $my-skill to handle the target workflow."
```

如果 skill 很轻，也可以不一次性建全所有目录。

### 4. 先放资源，再写 `SKILL.md`

比较稳妥的顺序是：

1. 把脚本、参考资料、模板放到位
2. 再写 `SKILL.md`

这样做的好处：

- `SKILL.md` 更容易保持精简
- 路由写法会更贴近真实资源
- 后续维护时更容易判断是该改 router 还是该改实现

### 5. 把 `SKILL.md` 写成入口，而不是总文档

推荐结构：

```markdown
---
name: my-skill
description: Describe what the skill does and when Codex should use it. Use when the task matches this workflow.
---

# My Skill

Use this skill for the target workflow.

## Safety First

- List any irreversible, destructive, or secret-related constraints.

## Task Router

- For the main workflow:
  Read `references/main.md`.
- For deterministic execution:
  Run `scripts/my_tool.py`.

## Progressive Loading

- Stay in this file for routing, safety, and command selection.
- Read only the one `references/*.md` file that matches the task.
- Load only `scripts/my_tool.py` when execution, debugging, or patching is required.
- Do not preload every reference file.

## Default Workflow

1. Inspect the target context.
2. Choose the smallest safe action.
3. Execute the workflow.
4. Validate the result.
```

这一步最重要的不是文风，而是边界：

- 把核心流程留在 `SKILL.md`
- 把细节拆去 `references/`
- 把实现沉到 `scripts/`

### 6. 补 `agents/openai.yaml`

最小版本通常就够了：

```yaml
interface:
  display_name: "My Skill"
  short_description: "Short human-facing summary of the skill."
  default_prompt: "Use $my-skill to handle the target workflow."
```

要求：

- 文案和 `SKILL.md` 一致
- `default_prompt` 显式提到 `$my-skill`

### 7. 给 skill 留下可回归入口

如果 skill 复杂到已经带脚本，建议同步补一个统一检查入口。

建议至少覆盖：

- `quick_validate.py` 结构校验
- 渐进式结构校验，包括长 reference 的顶部目录导航和 reference 可达性
- 一条真实可跑的 smoke / selftest

本仓库当前推荐命令：

```text
python <CODEX_HOME>/skills/.system/skill-creator/scripts/quick_validate.py skills/my-skill
python scripts/check_progressive_skills.py
```

如果 skill 带业务脚本，再补类似下面的入口：

```text
python skills/my-skill/scripts/check_my_skill.py
```

推荐把 `check_my_skill.py` 的命令行接口统一成：

- `--validator`
- `--skip-selftest`
- `--skip-validate`
- `--skip-help-smoke`

这样 GitHub Actions、人工排查和后续新增 skill 都能复用同一套调用方式。

### 8. 同步仓库级文档

只改 skill 目录还不够。新增或重构 skill 时，建议同步更新：

- 仓库根目录 [README.md](../README.md)
- 对应的业务文档或入口文档
- 如有需要，`docs/README.md`

## 常见反模式

以下写法通常会让 skill 变得难维护：

- 把大量背景介绍直接堆进 `SKILL.md`
- `Task Router` 同时指向很多 reference，但没有说明触发条件
- 让 reference 再去导航下一层 reference
- 有脚本却没有任何 smoke check
- `description` 只写“这是一个有用的 skill”，没有写触发条件

## 迭代建议

skill 第一次做完通常只是“能用”，不是“好用”。后续优化优先级建议是：

1. 先修正触发和路由是否准确
2. 再把重复逻辑沉到脚本
3. 再把长说明拆去 `references/`
4. 最后补检查和仓库级文档

## 提交前快速自查

- `description` 是否包含清晰触发语句？
- `SKILL.md` 是否还保持在渐进式入口的范围内？
- `Task Router` 是否能把人送到最窄入口？
- `Progressive Loading` 是否写清楚按需加载规则？
- 所有脚本是否真实跑过？
- 仓库级文档是否同步？
