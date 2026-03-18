# Skills 学习指南

这篇文档面向两类读者：

- 想快速理解“一个渐进式 skill 到底该怎么看”的人
- 想结合现有飞书和语雀 skill，学会自己构建新 skill 的人

如果你只想先照着模板做一个最小版本，先看 [skill-quickstart.md](./skill-quickstart.md)。如果你想核对仓库级硬约束，再看 [skill-spec.md](./skill-spec.md)。

## Contents

- [先建立一个正确心智模型](#先建立一个正确心智模型)
- [推荐学习顺序](#推荐学习顺序)
- [先从语雀 skill 学什么](#先从语雀-skill-学什么)
- [再从飞书 skill 学什么](#再从飞书-skill-学什么)
- [把两个 skill 放在一起看](#把两个-skill-放在一起看)
- [如何从 0 到 1 构建一个新 skill](#如何从-0-到-1-构建一个新-skill)
- [把需求翻译成 skill 结构](#把需求翻译成-skill-结构)
- [构建时最容易踩的坑](#构建时最容易踩的坑)
- [交付前检查](#交付前检查)

## 先建立一个正确心智模型

在这个仓库里，skill 不是“写一篇很长的说明文档”。

它更像一个给 agent 用的能力包，通常分三层：

1. frontmatter
   只负责触发，说明“做什么”和“什么时候用”
2. `SKILL.md`
   只负责最小路由、安全边界和默认工作流
3. `references/`、`scripts/`、`assets/`
   只在任务需要时再进入

先记住一句话：

- `SKILL.md` 是入口，不是总说明书

## 推荐学习顺序

推荐按下面顺序读：

1. 先看仓库首页 [../README.md](../README.md)，理解为什么这里强调“渐进式 skill”
2. 再看 [skill-spec.md](./skill-spec.md)，先建立结构约束
3. 然后看 [yuque-openapi.md](./yuque-openapi.md) 和对应 `skills/yuque-openapi/`
4. 再看 [feishu-doc-sync.md](./feishu-doc-sync.md) 和对应 `skills/feishu-doc-sync/`
5. 最后回到 [skill-authoring.md](./skill-authoring.md) 和 [skill-quickstart.md](./skill-quickstart.md)，把观察到的模式抽象成自己的制作方法

这个顺序的重点是：

- 先学“怎么看 skill”
- 再学“怎么做 skill”

## 先从语雀 skill 学什么

`yuque-openapi` 更适合当第一个学习样本，因为它的结构已经比较收口。

重点看这些东西：

- `skills/yuque-openapi/SKILL.md`
  看它如何把单文档同步、目录同步、TOC、manifest、troubleshooting 路由到不同 reference
- `skills/yuque-openapi/references/`
  看它如何按主题拆分，而且每份 reference 都尽量只讲一类问题
- `skills/yuque-openapi/scripts/yuque_api.py`
  看什么叫“把容易重复写的流程沉到脚本里”
- `skills/yuque-openapi/scripts/selftest_yuque_api.py`
  看什么叫“复杂 skill 要有自己的最小回归”

从语雀 skill 最该学到的，不是某个命令，而是这三个设计动作：

- 把能力拆成稳定命令族
- 把说明拆成任务主题
- 给复杂行为补离线自测

## 再从飞书 skill 学什么

`feishu-doc-sync` 更适合当第二个样本，因为它能看到一个复杂 skill 是怎么继续演进的。

重点看这些东西：

- `skills/feishu-doc-sync/SKILL.md`
  看它如何处理 tenant / user 两条工作流，同时仍然保持路由清晰
- `skills/feishu-doc-sync/references/`
  看它如何把 auth、token、sync、pull/export、markdown mapping、conflict 分开
- `skills/feishu-doc-sync/scripts/feishu_doc_sync.py`
  看一个高复杂度 CLI 如何逐步吸收真实业务能力
- `skills/feishu-doc-sync/scripts/check_feishu_skill.py`
  看如何用 mock selftest 和 help smoke 把复杂脚本保护住

从飞书 skill 最该学到的是：

- 一个 skill 可以先把主链路做通，再逐步增强
- 复杂 skill 更需要明确的安全边界和默认关闭的危险开关
- 当 reference 变长时，必须补导航和 lint，而不是继续放任增长

## 把两个 skill 放在一起看

把它们放在一起，你会更容易看清楚什么叫“可复用的 skill 模式”。

共同点：

- 都把 `SKILL.md` 写成任务入口
- 都把细节放进 `references/`
- 都用 Python CLI 承接重复逻辑
- 都提供 `check_*.py` 作为统一检查入口

差异点：

- `yuque-openapi` 更像成熟产品型 skill，结构更规整
- `feishu-doc-sync` 更像持续迭代中的复杂 skill，能看到能力扩张时怎样补 safety、router、lint 和自测

所以最适合的学习方式不是“选一个模仿”，而是：

- 用语雀学“怎么收口”
- 用飞书学“怎么演进”

## 如何从 0 到 1 构建一个新 skill

建议按这条路径做：

1. 先写清任务边界
   用户会怎么提这个需求，skill 到底要解决哪一类问题
2. 再决定哪些内容留在 `SKILL.md`
   一般只留路由、安全约束、默认工作流
3. 决定哪些内容拆进 `references/`
   任何长说明、专题规则、接口细节都优先拆出去
4. 决定哪些逻辑进 `scripts/`
   任何会反复重写、参数复杂、容易出错的实现都尽量脚本化
5. 给复杂 skill 补 `check_*.py`
   至少要能一键跑自测、结构校验和 help smoke

新建时可以直接从这里起步：

```text
python <CODEX_HOME>/skills/.system/skill-creator/scripts/init_skill.py my-skill --path skills --resources scripts,references,assets --interface display_name="My Skill" --interface short_description="Short UI summary." --interface default_prompt="Use $my-skill to handle the target workflow."
```

然后至少跑这些检查：

```text
python <CODEX_HOME>/skills/.system/skill-creator/scripts/quick_validate.py skills/my-skill
python scripts/check_progressive_skills.py
python skills/my-skill/scripts/check_my_skill.py
```

## 把需求翻译成 skill 结构

一个很好用的方法，是把需求先翻译成下面这张表：

| 需求内容 | 应该放哪里 |
| --- | --- |
| skill 做什么、什么时候触发 | `SKILL.md` frontmatter |
| 任务入口、默认工作流、安全边界 | `SKILL.md` |
| 长说明、接口、专题策略 | `references/*.md` |
| 稳定执行逻辑、CLI、自测 | `scripts/` |
| 模板、样例、批处理清单 | `assets/` |

如果你发现某段内容同时想放进 `SKILL.md` 和 `references/`，通常说明边界还没分清。

默认判断原则：

- 短而常用：留在 `SKILL.md`
- 长而按需：放进 `references/`
- 稳定执行：放进 `scripts/`

## 构建时最容易踩的坑

最常见的坑基本就这几类：

- `description` 写太泛
  结果 skill 不容易被正确触发
- `SKILL.md` 写太长
  最后真正需要的任务入口反而不明显
- `references/` 没有路由关系
  文件虽然拆了，但 agent 不知道先看哪一份
- 让 reference 再继续深层跳转
  现在仓库已经明确限制在两跳内可达
- 有复杂脚本但没有统一 checker
  一旦能力继续扩展，很容易回归

如果不确定自己有没有踩坑，直接对照这两个问题检查：

- 当前任务触发 skill 后，agent 能不能很快选到最窄入口？
- 复杂行为改动后，仓库有没有办法一键回归？

## 交付前检查

在这个仓库里，一个新的或更新后的 skill，至少要满足：

- `SKILL.md` frontmatter 只包含 `name` 和 `description`
- `description` 明确包含 “Use when ...”
- `SKILL.md` 包含 `Task Router`、`Progressive Loading`、`Default Workflow`
- 长 reference 顶部带 `## Contents`
- 所有 reference 能从 `SKILL.md` 在两跳内到达
- 复杂脚本带 `check_*.py`
- README 和 `docs/` 索引同步更新

如果你已经把这篇读完，下一步建议直接配合这三篇继续用：

- [skill-quickstart.md](./skill-quickstart.md)
- [skill-authoring.md](./skill-authoring.md)
- [skill-spec.md](./skill-spec.md)
