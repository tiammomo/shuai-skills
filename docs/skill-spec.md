# Skills 规范说明

这篇文档定义的是“本仓库里的 skill 应该长成什么样”。它不是业务说明，而是结构和写法约束。

如果你想快速做出一个最小 skill，先看 [skill-quickstart.md](./skill-quickstart.md)；如果你想看从 0 到 1 的完整制作流程，再看 [skill-authoring.md](./skill-authoring.md)。

## 1. 目录结构

一个 skill 目录建议按下面的方式组织：

```text
skills/<skill-name>/
|- SKILL.md
|- agents/
|  `- openai.yaml
|- scripts/
|- references/
`- assets/
```

约束如下：

- `SKILL.md` 必须存在。
- `agents/openai.yaml` 推荐存在。
- `scripts/`、`references/`、`assets/` 按需创建，不要为了“看起来完整”放空目录。

## 2. 命名规范

- 目录名只用小写字母、数字和连字符。
- 目录名和 frontmatter 里的 `name` 保持一致。
- 名称尽量短、清晰、可触发，优先描述动作或能力，而不是宽泛名词。

推荐：

- `yuque-openapi`
- `feishu-doc-sync`
- `gh-fix-ci`

不推荐：

- `MySkill`
- `tools_for_docs`
- `all-in-one-helper`

## 3. Frontmatter 规范

`SKILL.md` 顶部必须包含 YAML frontmatter，并且只保留两个字段：

```yaml
---
name: my-skill
description: Describe what the skill does and when Codex should use it. Use when ...
---
```

要求：

- `name` 必须等于目录名。
- `description` 必须同时写清“做什么”和“什么时候用”。
- `description` 里建议显式出现 `Use when ...` 触发短语，方便路由和校验。
- 不要在 frontmatter 里继续堆自定义字段。

## 4. 渐进式 skill 约束

本仓库默认把 skill 设计成“渐进式加载”能力包。

加载顺序应当是：

1. frontmatter 决定是否触发。
2. `SKILL.md` 提供最小执行导航。
3. `references/`、`scripts/`、`assets/` 只在当前任务需要时再进入。

这不是建议语气，而是推荐落成明确结构：

- `SKILL.md` 默认控制在 500 行以内。
- `SKILL.md` 至少包含 `## Task Router`、`## Progressive Loading`、`## Default Workflow`。
- `## Progressive Loading` 必须明确说明：
  - 只按需读取匹配主题的 `references/*.md`
  - 只在执行、调试或补丁时打开 `scripts/`
  - 不要预加载所有参考资料
- 如果 skill 下存在非空 `references/`，就在 `## Task Router` 和 `## Reference Files` 里显式暴露入口。
- 如果 skill 下存在 `scripts/`、`references/` 或 `assets/`，就在 `## Bundled Resources` 里说明它们的角色。
- reference 导航尽量保持从 `SKILL.md` 一跳可达，不要设计成层层继续找下一份 reference。
- 单个 `references/*.md` 超过 100 行时，必须把 `## Contents` 放成第一个二级标题，并覆盖后续所有二级章节，方便按需跳转到最窄段落。
- 每个 `references/*.md` 都必须能从 `SKILL.md` 直达，或通过一个已在 `SKILL.md` 暴露的 reference 路由页在两跳内到达；不要把 reference 链接继续嵌套成三跳以上。

## 5. `SKILL.md` 正文规范

`SKILL.md` 不是 README，它的目标是让 agent 快速、安全地进入正确路径。

推荐保留这些部分：

- 一句目标说明
- `## Safety First`
- `## Task Router`
- `## Progressive Loading`
- `## Default Workflow`
- `## Reference Files`
- `## Bundled Resources`

其中：

- 核心路由和默认动作留在 `SKILL.md`
- 细节规则、接口说明和专题策略拆到 `references/`
- 可重复执行的实现放进 `scripts/`

## 6. Task Router 写法

`## Task Router` 的目标不是“把所有能力都写一遍”，而是把当前任务送到最窄的入口。

推荐写法：

- 用场景来分，而不是按文件名硬堆列表。
- 每一条 router 都说明“什么时候看哪个 reference / 什么时候跑哪个 script”。
- 一条 router 优先只指向一个主入口。

示例：

```markdown
## Task Router

- Sync one markdown file:
  Use `push-markdown` or `pull-markdown`, then read `references/file-sync.md`.
- Plan a directory run:
  Use `plan-dir`, then read `references/dir-sync.md`.
```

## 7. Progressive Loading 写法

`## Progressive Loading` 要写成可以直接执行的约束，而不是抽象原则。

推荐包含：

- 留在当前文件的内容范围
- 什么时候才去读 `references/`
- 什么时候才去读或执行 `scripts/`
- 不要一次性预读所有资料

示例：

```markdown
## Progressive Loading

- Stay in this file for routing, safety, and command selection.
- Read only the single `references/*.md` file that matches the current task.
- Load only `scripts/foo.py` when you need to execute, debug, or patch the implementation.
- Do not preload every reference file just because the skill triggered.
```

## 8. `scripts/` 规范

适合放进 `scripts/` 的内容：

- 会被反复执行的逻辑
- 容易出错、需要稳定参数和输出的逻辑
- 希望通过本地或 CI 检查重复回归的逻辑

脚本要求：

- 输入输出清晰
- 报错能定位问题
- 至少有一条代表性的验证路径

## 9. `references/` 规范

适合放进 `references/` 的内容：

- 接口说明
- 规则说明
- 专题工作流
- 故障排查
- 领域知识

推荐做法：

- 按主题拆文件
- 在 `SKILL.md` 里明确写出什么场景看哪一份
- 超过 100 行的 reference 文件，把 `## Contents` 放在顶部，并为后续每个 `##` 章节提供锚点链接
- 如果某个 reference 只是“索引页”，就在 `SKILL.md` 里直接暴露它，并确保它指向的 reference 仍然保持两跳内可达
- 不要让 reference 再变成新的总目录说明书

## 10. `assets/` 规范

`assets/` 放的是输出资源，不是上下文说明。

适合放：

- 模板
- 样例输入输出
- 图标
- 可复用资源文件

## 11. `agents/openai.yaml` 规范

推荐保留一个最小可用版本：

```yaml
interface:
  display_name: "Human-friendly name"
  short_description: "Short UI description"
  default_prompt: "Use $my-skill to do ..."
```

要求：

- 字符串统一加引号
- `default_prompt` 显式包含 `$skill-name`
- UI 文案和 `SKILL.md` 的能力边界保持一致

## 12. 最小模板

### 最小 `SKILL.md`

```markdown
---
name: my-skill
description: Describe what the skill does and when Codex should use it. Use when the task matches this workflow.
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

### 最小 `agents/openai.yaml`

```yaml
interface:
  display_name: "My Skill"
  short_description: "Short UI summary of the skill."
  default_prompt: "Use $my-skill to handle the target workflow."
```

## 13. 验证规范

新增或修改 skill 后，至少建议做两层验证：

1. 结构校验
2. 代表性运行验证

本仓库当前推荐：

- 结构校验：`python <CODEX_HOME>/skills/.system/skill-creator/scripts/quick_validate.py skills/<skill-name>`
- 渐进式结构校验：`python scripts/check_progressive_skills.py`，同时检查长 reference 的 `## Contents` 导航是否完整，以及每个 reference 是否能从 `SKILL.md` 在两跳内到达
- 业务 smoke / selftest：为复杂 skill 提供自己的 `check_*.py`

## 14. 提交前检查清单

- skill 名称是否符合小写连字符规则？
- `SKILL.md` frontmatter 是否只包含 `name` 和 `description`？
- `description` 是否写清“做什么”和“Use when ...”？
- `SKILL.md` 是否已经写成渐进式入口？
- `SKILL.md` 是否包含 `Task Router`、`Progressive Loading`、`Default Workflow`？
- 如果存在 `references/`，是否在 router 和 reference section 中暴露入口？
- 如果存在长 reference，是否已经补了顶部 `## Contents`，并覆盖后续所有二级章节？
- 如果存在多个 reference，它们是否都能从 `SKILL.md` 在两跳内到达，没有孤儿 reference？
- 如果存在 `scripts/`，是否真的跑过？
- `agents/openai.yaml` 是否和 skill 能力匹配？
- 仓库级 README 和对应 docs 是否已经同步？
