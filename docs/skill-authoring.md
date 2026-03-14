# Skills 制作指南

这篇文档面向“想在本仓库继续新增 skill 的人”，重点回答两个问题：

- 一个 skill 应该怎么从 0 到 1 做出来。
- 在这个仓库里，推荐按什么顺序推进，才能让 skill 可复用、可维护、可验证。

如果你想先看规则和约束，再回来看操作步骤，可以搭配 [skill-spec.md](./skill-spec.md) 一起读；如果你只想先快速做出一个最小版本，可以先看 [skill-quickstart.md](./skill-quickstart.md)。

## 先理解：skill 不是普通文档

一个 skill 本质上是给另一个 Codex 实例使用的“任务说明 + 资源包”。它不是面向终端用户的产品文档，而是面向 agent 的可复用能力单元。

在这个仓库里，一个成熟 skill 通常会包含这些内容：

- `SKILL.md`：必须存在，是 skill 的入口。
- `agents/openai.yaml`：推荐存在，用于 UI 展示和默认 prompt。
- `scripts/`：需要稳定执行、反复复用时放脚本。
- `references/`：需要按需加载的说明、规则、接口文档。
- `assets/`：模板、示例文件、图标、输出资源等。

本仓库当前的 [`skills/yuque-openapi/`](../skills/yuque-openapi/) 就是一个完整例子：

- `SKILL.md` 负责告诉 agent 什么时候该用这个 skill。
- `scripts/` 里放了可直接执行的 Yuque CLI 和检查脚本。
- `references/` 里拆分了目录同步、TOC、manifest 等主题说明。
- `assets/` 里放了批量任务 manifest 模板。
- `agents/openai.yaml` 里放了 UI 展示信息。

## 推荐制作流程

### 1. 先定义清楚它解决什么任务

在动手建目录之前，先把 skill 的触发边界想清楚：

- 用户会说什么，触发这个 skill？
- 这个 skill 解决的是单一任务，还是一类相近任务？
- 哪些知识是模型本身不稳定、需要被显式教会的？
- 哪些步骤会反复重写，值得沉淀为脚本或模板？

如果这里没有想清楚，后面最容易出现两个问题：

- skill 描述过泛，导致触发不准。
- skill 内容过杂，变成一个什么都想包进去的大杂烩。

### 2. 把可复用资源先规划出来

建议先按下面三类去想：

- `scripts/`
  适合放可重复执行、容易写错、需要稳定输出的逻辑。
- `references/`
  适合放详细说明、接口文档、领域规则、公司内部约束。
- `assets/`
  适合放模板、样例、图标、输出资源，而不是给模型读的长文档。

可以用一个很直接的判断标准：

- 同样的代码会不会反复写？
  会，就考虑放进 `scripts/`。
- 说明内容会不会很长，而且不是每次都要读？
  会，就考虑放进 `references/`。
- 这个文件主要是被复制、渲染、引用，而不是被读进上下文？
  是，就考虑放进 `assets/`。

### 3. 初始化 skill 目录

如果是新 skill，推荐直接使用 `skill-creator` 的初始化脚本生成骨架，再手工完善。

示例：

```text
python <CODEX_HOME>/skills/.system/skill-creator/scripts/init_skill.py my-skill --path skills --resources scripts,references,assets
```

常见参数含义：

- `my-skill`
  skill 名称，会被规范化成小写连字符形式。
- `--path skills`
  把 skill 创建在本仓库的 `skills/` 下。
- `--resources scripts,references,assets`
  一次性把常见资源目录建出来。

如果只是一个很轻量的 skill，也可以只建需要的目录，不必把所有资源都生成出来。

### 4. 优先写资源，再写 `SKILL.md`

一个常见误区是先把 `SKILL.md` 写得很长，结果后面真正的脚本、模板、参考资料又散落在别处。更稳妥的做法是：

1. 先把要复用的脚本、参考资料、模板放到位。
2. 再写 `SKILL.md`，让它成为“导航和执行说明”。

这样做的好处是：

- `SKILL.md` 不会臃肿。
- 资源边界更清楚。
- 后续维护时更容易判断该改指令还是改脚本。

### 5. 写好 `SKILL.md`

`SKILL.md` 是 skill 的核心入口，建议重点写好这几部分：

- YAML frontmatter
  只放 `name` 和 `description`。
- 简短的总说明
  说明这个 skill 的目标和使用方式。
- 任务路由
  告诉 agent 在什么场景该看哪份 `references/` 或跑哪个 `scripts/`。
- 默认工作流
  给出一个最小、稳定、可重复的执行顺序。
- 资源说明
  说明各目录下文件的角色。

这里最重要的是 `description`。

因为对 agent 来说，它不只是介绍文字，还是 skill 的主要触发条件之一。所以描述里要明确写出：

- skill 做什么。
- 什么时候应该用它。
- 哪些用户请求会触发它。

### 6. 补 `agents/openai.yaml`

如果这个 skill 需要更好的 UI 展示，建议补上 `agents/openai.yaml`。

最常用的字段有：

- `display_name`
- `short_description`
- `default_prompt`

这个仓库里的 [`skills/yuque-openapi/agents/openai.yaml`](../skills/yuque-openapi/agents/openai.yaml) 就是一个参考：

- `display_name` 给出人类可读名称。
- `short_description` 用一句话说明核心能力。
- `default_prompt` 会直接引导用户如何调用 skill，而且要显式提到 `$skill-name`。

## 一个最小可复制模板

如果你想先快速起一个可用骨架，再慢慢补细节，可以直接复制下面这两段。

### `SKILL.md` 最小模板

```markdown
---
name: my-skill
description: Briefly describe what this skill does and when Codex should use it. Mention the task type, files, tools, or user requests that should trigger it.
---

# My Skill

Use this skill to handle the target workflow in a repeatable way.

## Safety First

- State any important safety or confirmation rules here.
- Mention any secrets, destructive actions, or irreversible changes that need extra care.

## Task Router

- For the main workflow:
  Read `references/main-workflow.md` if it exists.
- For deterministic execution:
  Run `scripts/my_tool.py` if it exists.

## Default Workflow

1. Check the target input, environment, or files.
2. Choose the smallest safe action.
3. Run the main workflow.
4. Validate the result before finishing.

## Bundled Resources

- `scripts/`: executable helpers for repeated or fragile tasks.
- `references/`: detailed materials that should be loaded only when needed.
- `assets/`: templates or output resources.
```

### `agents/openai.yaml` 最小模板

```yaml
interface:
  display_name: "My Skill"
  short_description: "Short human-facing summary of the skill."
  default_prompt: "Use $my-skill to handle the target workflow in a safe, repeatable way."
```

### 使用这个模板时，至少替换这些占位内容

- 把 `my-skill` 换成真实 skill 名，保持和目录名一致。
- 把 `description` 改成“做什么 + 什么时候用”的明确描述，不要留成泛话。
- 把标题、默认工作流和资源说明改成真实任务。
- 如果没有 `references/` 或 `scripts/`，就把对应说明删掉，不要保留空导航。
- 把 `default_prompt` 改成真实调用语句，并显式包含 `$skill-name`。

### 7. 验证 skill 结构

完成初稿后，建议至少做两类检查：

1. 结构校验
2. 真实运行验证

结构校验示例：

```text
python <CODEX_HOME>/skills/.system/skill-creator/scripts/quick_validate.py skills/my-skill
```

这个步骤主要用来发现：

- frontmatter 缺字段
- skill 命名不符合规则
- 基本目录结构有问题

### 8. 运行并测试脚本

如果 skill 带了 `scripts/`，不要只写完不跑。至少要做一轮代表性验证，确认：

- 能正常执行
- 参数设计合理
- 报错信息可读
- 输出结构稳定

这个仓库里的 [`skills/yuque-openapi/scripts/check_yuque_skill.py`](../skills/yuque-openapi/scripts/check_yuque_skill.py) 就是一个很好的实践：它把自测、帮助命令 smoke test 和结构校验串成了一套统一入口。

### 9. 用真实任务迭代

skill 第一次写完通常只是“能用”，还不是“好用”。更实际的做法是：

1. 先在真实任务里用起来。
2. 观察 agent 卡在哪些地方。
3. 决定该补脚本、补参考文档，还是改 `SKILL.md` 的路由方式。

最值得优先优化的，通常是这些问题：

- 经常走错参考文件。
- 关键保护规则没有写清楚。
- 重复写同一段脚本。
- 输出格式不稳定，难以接自动化。

## 制作 skill 的一个简化清单

在本仓库里新增 skill 时，可以按下面的清单走：

1. 明确 skill 名称、能力边界和触发场景。
2. 决定是否需要 `scripts/`、`references/`、`assets/`。
3. 初始化 skill 目录。
4. 先放资源文件，再写 `SKILL.md`。
5. 补 `agents/openai.yaml`。
6. 跑结构校验。
7. 跑脚本测试或最小可行验证。
8. 在真实任务里迭代。

## 和本仓库配套的实践建议

结合当前仓库现状，比较推荐的做法是：

- 把“给人看的仓库级教程”放在 `docs/`，不要塞进 skill 文件夹内部。
- 把“给 agent 执行的具体说明”放在 `SKILL.md` 和 `references/`。
- 把“重复执行、需要稳定性”的逻辑放到 `scripts/`。
- 把“只在输出时使用”的模板或资源放到 `assets/`。
- 尽量让每个 skill 都有至少一个可运行的检查入口，降低后续回归成本。
