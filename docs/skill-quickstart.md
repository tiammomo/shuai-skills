# Skills 快速上手

这篇文档面向“想先快速做出一个可用 skill，再慢慢完善”的场景。

如果你想看完整制作流程，请读 [skill-authoring.md](./skill-authoring.md)；如果你想核对结构和规范，请读 [skill-spec.md](./skill-spec.md)。

## 5 分钟目标

完成后，你会得到一个最小可用的 skill 目录：

```text
skills/my-skill/
|- SKILL.md
`- agents/
   `- openai.yaml
```

## 步骤 1：确定 skill 名称

先定一个简短、明确、可触发的名字。

建议：

- 用小写字母、数字和连字符。
- 名称直接反映动作或能力。
- 目录名和 skill 名保持一致。

例子：

- `my-skill`
- `api-sync-helper`
- `release-note-writer`

## 步骤 2：初始化 skill 目录

在本仓库根目录执行：

```text
python <CODEX_HOME>/skills/.system/skill-creator/scripts/init_skill.py my-skill --path skills --interface display_name="My Skill" --interface short_description="Short UI summary." --interface default_prompt="Use $my-skill to handle the target workflow."
```

如果你已经知道后面会用到额外资源，也可以直接把目录一起建出来：

```text
python <CODEX_HOME>/skills/.system/skill-creator/scripts/init_skill.py my-skill --path skills --resources scripts,references,assets --interface display_name="My Skill" --interface short_description="Short UI summary." --interface default_prompt="Use $my-skill to handle the target workflow."
```

执行后，重点看新生成的：

- `skills/my-skill/SKILL.md`
- `skills/my-skill/agents/openai.yaml`

## 步骤 3：把 `SKILL.md` 改成最小可用版本

把 `skills/my-skill/SKILL.md` 至少整理成下面这个骨架：

```markdown
---
name: my-skill
description: Describe what this skill does and when Codex should use it. Include the task, file type, tool, or user request patterns that should trigger it.
---

# My Skill

Use this skill for the target workflow.

## Task Router

- For the main workflow:
  Read `references/main.md` if needed.

## Default Workflow

1. Inspect the target context.
2. Choose the smallest safe action.
3. Execute the workflow.
4. Validate the result.
```

这里只要先保证两件事：

- `description` 写清楚“做什么 + 什么时候用”。
- 正文能告诉 agent 最小执行路径。

## 步骤 4：检查 `agents/openai.yaml`

最小版本建议长这样：

```yaml
interface:
  display_name: "My Skill"
  short_description: "Short UI summary of the skill."
  default_prompt: "Use $my-skill to handle the target workflow."
```

快速检查这三点：

- 字符串值是否都带引号。
- `default_prompt` 是否显式提到 `$my-skill`。
- UI 名称和 `SKILL.md` 的能力描述是否一致。

## 步骤 5：验证结构

在仓库根目录执行：

```text
python <CODEX_HOME>/skills/.system/skill-creator/scripts/quick_validate.py skills/my-skill
```

如果通过，说明至少这些基础结构是对的：

- 命名合法
- frontmatter 合法
- `SKILL.md` 关键字段齐全

## 可选步骤：什么时候再补 `scripts/`、`references/`、`assets/`

先别急着全建满。只有在真的需要时再补：

- `scripts/`
  当一段代码会反复写，或者执行过程很脆弱时再加。
- `references/`
  当说明很长、不是每次都要读时再加。
- `assets/`
  当需要模板、图标、样例资源时再加。

## 做完后，别忘了同步仓库文档

如果你准备把 skill 留在这个仓库里，建议再补两处：

1. 在 [../README.md](../README.md) 里加一行 skill 简介和文档入口。
2. 在 [README.md](./README.md) 里补文档索引或阅读顺序。

## 一份最小检查清单

提交前快速自查：

- skill 名是否是小写连字符形式？
- `SKILL.md` frontmatter 是否只有 `name` 和 `description`？
- `description` 是否写清楚触发场景？
- `agents/openai.yaml` 是否包含 `$skill-name` 形式的 `default_prompt`？
- 如果加了 `scripts/`，是否实际跑过？

## 下一步读什么

- 想继续完善 skill 内容：看 [skill-authoring.md](./skill-authoring.md)
- 想核对仓库规范：看 [skill-spec.md](./skill-spec.md)
