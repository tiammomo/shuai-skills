# Skills 快速上手

这篇文档面向“先做出一个最小可用 skill，再慢慢完善”的场景。

如果你想先通过现有飞书和语雀 skill 学会“怎么看 skill、怎么照着做”，先读 [skill-learning-guide.md](./skill-learning-guide.md)；如果你想看完整制作流程，请读 [skill-authoring.md](./skill-authoring.md)；如果你想核对结构规范，请读 [skill-spec.md](./skill-spec.md)。

## 5 分钟目标

完成后，你会得到一个最小但符合本仓库渐进式规范的 skill：

```text
skills/my-skill/
|- SKILL.md
`- agents/
   `- openai.yaml
```

## 步骤 1：确定 skill 名称

建议：

- 使用小写字母、数字和连字符
- 名称能直接反映动作或能力
- 目录名和 skill 名保持一致

例如：

- `my-skill`
- `api-sync-helper`
- `release-note-writer`

## 步骤 2：初始化 skill 目录

在仓库根目录执行：

```text
python <CODEX_HOME>/skills/.system/skill-creator/scripts/init_skill.py my-skill --path skills --interface display_name="My Skill" --interface short_description="Short UI summary." --interface default_prompt="Use $my-skill to handle the target workflow."
```

如果你已经知道后面会用到参考资料或脚本，也可以一次性把目录建出来：

```text
python <CODEX_HOME>/skills/.system/skill-creator/scripts/init_skill.py my-skill --path skills --resources scripts,references,assets --interface display_name="My Skill" --interface short_description="Short UI summary." --interface default_prompt="Use $my-skill to handle the target workflow."
```

## 步骤 3：把 `SKILL.md` 改成渐进式最小版本

把生成出来的 `skills/my-skill/SKILL.md` 至少整理成这样：

```markdown
---
name: my-skill
description: Describe what this skill does and when Codex should use it. Use when the task matches this workflow.
---

# My Skill

Use this skill for the target workflow.

## Task Router

- For the main workflow:
  Read `references/main.md` if needed.

## Progressive Loading

- Stay in this file for routing and safety.
- Read only the one `references/*.md` file that matches the task.
- Load only `scripts/my_tool.py` when execution or debugging is required.
- Do not preload every reference file.

## Default Workflow

1. Inspect the target context.
2. Choose the smallest safe action.
3. Execute the workflow.
4. Validate the result.
```

这个最小版本先保证三件事：

- `description` 写清“做什么”和“什么时候用”
- `SKILL.md` 能做最小路由
- skill 已经符合渐进式入口结构

## 步骤 4：检查 `agents/openai.yaml`

最小版本建议长这样：

```yaml
interface:
  display_name: "My Skill"
  short_description: "Short UI summary of the skill."
  default_prompt: "Use $my-skill to handle the target workflow."
```

快速检查这三点：

- 字符串是否都带引号
- `default_prompt` 是否显式包含 `$my-skill`
- UI 文案和 `SKILL.md` 是否一致

## 步骤 5：做最小校验

在仓库根目录执行：

```text
python <CODEX_HOME>/skills/.system/skill-creator/scripts/quick_validate.py skills/my-skill
python scripts/check_progressive_skills.py
```

这样至少能确认：

- 命名合法
- frontmatter 合法
- skill 符合仓库级渐进式结构要求

## 什么时候再加 `scripts/`、`references/`、`assets/`

不要一开始就把目录堆满，只在真的需要时再补：

- `scripts/`
  当一段逻辑会反复重写，或者需要稳定执行时再加。
- `references/`
  当说明很长、不是每次都要读时再加。
- `assets/`
  当需要模板、样例或输出资源时再加。

## 做完后别忘了同步仓库文档

如果这个 skill 准备留在仓库里，建议再补两处：

1. 在 [../README.md](../README.md) 里加入口和状态
2. 在相关 `docs/` 文档里补仓库级说明

## 提交前快速自查

- skill 名称是否符合小写连字符规则？
- `SKILL.md` frontmatter 是否只有 `name` 和 `description`？
- `description` 是否包含清晰触发场景？
- `SKILL.md` 是否已经包含 `Task Router`、`Progressive Loading`、`Default Workflow`？
- 如果加了 `scripts/`，是否真的跑过？

## 下一步读什么

- 想继续完善 skill：看 [skill-authoring.md](./skill-authoring.md)
- 想先通过现有 skill 学习如何构建：看 [skill-learning-guide.md](./skill-learning-guide.md)
- 想核对仓库规范：看 [skill-spec.md](./skill-spec.md)
