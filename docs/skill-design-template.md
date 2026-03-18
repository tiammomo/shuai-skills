# 从需求到 Skill 设计表：实战模板

这篇文档给“要新增/重构一个 skill”的同学用。目标不是解释概念，而是提供一份可以直接复制填写的设计表，帮助你把需求快速翻译成一个符合本仓库“渐进式 skill”规范的结构。

如果你还没看过整体学习路径，先读：

- [skill-learning-guide.md](./skill-learning-guide.md)
- [skill-spec.md](./skill-spec.md)
- [skill-authoring.md](./skill-authoring.md)

## Contents

- [怎么用这张表](#怎么用这张表)
- [设计表（模板）](#设计表模板)
- [示例（语雀）](#示例语雀)
- [示例（飞书）](#示例飞书)
- [提交前快速检查](#提交前快速检查)

## 怎么用这张表

推荐用法：

1. 把下面的“设计表（模板）”整段复制到你的需求文档、PR 描述或语雀/飞书的任务卡里。
2. 先填 1 到 3 张表：需求拆解、触发与边界、任务路由。
3. 再决定要不要建 `references/`、`scripts/`、`assets/`，并把文件规划写进表格。
4. 最后对照“提交前快速检查”跑脚本和补入口文档。

这张表刻意把内容拆成三层，避免把 `SKILL.md` 写成长文档：

- frontmatter：触发（做什么 + 什么时候用）
- `SKILL.md`：路由 + 安全边界 + 默认工作流
- `references/`、`scripts/`、`assets/`：按需加载与执行

## 设计表（模板）

把下面整段复制走，按你的需求填写即可。

### 0. 基本信息

| 字段 | 填写 |
| --- | --- |
| Skill 名称（目录名） | `<my-skill>` |
| 一句话目标 | `<用一句话描述最终交付的能力>` |
| 主要平台/系统 | `<飞书/语雀/内部系统/...>` |
| 使用者是谁 | `<谁会用这个 skill>` |
| 输出形态 | `<生成文件/更新目录/出报告/跑脚本/...>` |

### 1. 需求拆解（从“用户原话”到“任务类型”）

至少收集 5 到 10 条“用户可能怎么说”的原话，用它们反推路由和默认工作流。

| 用户原话示例 | 任务类型（动词） | 输入（最小） | 输出（验收） | 风险/不可逆点 | 建议承载（SKILL/ref/script） |
| --- | --- | --- | --- | --- | --- |
| `<例如：把目录 A 同步到 B>` | `<sync-dir>` | `<目录/空间>` | `<dry-run 计划或执行结果>` | `<覆盖/删除/权限>` | `<SKILL 路由 + script 执行 + ref 规则>` |

### 2. 触发与边界（frontmatter 设计）

这一段的产物是 `SKILL.md` 的 `description` 草稿：必须同时包含“做什么”和“Use when ...”触发场景。

| 项目 | 填写 |
| --- | --- |
| 触发关键词/场景（Use when ...） | `<列 5-10 个触发短语或典型请求>` |
| 明确不做（Out of scope） | `<列 3-5 个反例，防止 skill 变全能>` |
| 需要的凭据/环境变量 | `<token/app_id/app_secret/...>` |
| 安全边界（默认禁止） | `<删除/覆盖/批量更新/跨租户/...>` |
| “需要用户确认”的条件 | `<哪些情况下必须二次确认>` |

### 3. 路由设计（SKILL.md 只做入口）

目标：写完这张表，你基本就能写出 `## Task Router` 和 `## Default Workflow`。

| 场景（用户意图） | 建议入口命令/动作 | 只读哪一份 reference（按需） | 需要跑哪个 script（按需） | 风险控制（默认开关） |
| --- | --- | --- | --- | --- |
| `<同步单文件>` | `<push-markdown/pull-markdown>` | `references/<file-sync>.md` | `scripts/<cli>.py <subcmd>` | `<dry-run 默认开启>` |
| `<目录级批处理>` | `<plan-dir/sync-dir>` | `references/<dir-sync>.md` | `scripts/<cli>.py plan-dir` | `<require --yes>` |

### 4. Reference 设计（按主题拆分）

要求提醒：

- 单个 reference 超过 100 行必须在顶部放 `## Contents`，并覆盖后续所有二级标题（仓库 lint 会检查）。
- reference 尽量保持从 `SKILL.md` 一跳可达；最多允许两跳，不要堆成多层迷宫（仓库 lint 会检查）。

| reference 文件 | 主题/目的 | 谁会读它（触发条件） | 关键章节（拟定） | 预期长度 | 是否需要 `## Contents` |
| --- | --- | --- | --- | --- | --- |
| `references/<auth>.md` | `<鉴权与 token>` | `<第一次接入/排查 401>` | `<tenant/user 模式、刷新、权限>` | `<~120 行>` | `Yes` |

### 5. Scripts 设计（把易错流程脚本化）

脚本不要为了“看起来专业”而加，只有当它满足以下任一条件才值得加：

- 会反复重写
- 参数多且容易出错
- 需要稳定输出用于下游（manifest/diff/report）
- 需要可回归的最小自测

| script | 职责 | CLI 入口 | 输入/输出 | 失败模式（如何报错） | 最小自测/检查入口 |
| --- | --- | --- | --- | --- | --- |
| `scripts/<tool>.py` | `<核心执行>` | `<python scripts/<tool>.py --help>` | `<stdin/文件/目录 -> 报告/文件>` | `<明确 exit code + stderr>` | `scripts/check_<skill>.py` |

### 6. Assets 设计（模板与输出资源）

| asset | 用途 | 何时需要 | 备注 |
| --- | --- | --- | --- |
| `assets/<template>.md` | `<输出模板>` | `<生成报告>` | `<不加载进上下文，只用于复制/输出>` |

### 7. 校验与回归（必须可重复执行）

| 检查项 | 命令 | 通过标准 |
| --- | --- | --- |
| 结构校验（基础） | `python <CODEX_HOME>/skills/.system/skill-creator/scripts/quick_validate.py skills/<my-skill>` | frontmatter 合法、命名合法 |
| 仓库渐进式 lint | `python scripts/check_progressive_skills.py` | SKILL 结构、reference 导航、两跳可达都通过 |
| 业务 smoke/selftest | `python skills/<my-skill>/scripts/check_<my_skill>.py` | 自测通过、help smoke 通过 |

### 8. 需要同步更新的仓库入口

| 入口 | 是否需要更新 | 说明 |
| --- | --- | --- |
| `README.md` | `<Yes/No>` | 新增 skill 或能力变化时同步 |
| `docs/README.md` | `<Yes/No>` | 新增说明文档时同步 |
| `docs/<skill>.md` | `<Yes/No>` | 业务说明与推荐路径 |

## 示例（语雀）

下面用 `yuque-openapi` 举两个“表格应该怎么填”的片段，重点是路由和承载位置，不是复述全部能力。

### 触发与边界（片段）

| 项目 | 填写 |
| --- | --- |
| 触发关键词/场景（Use when ...） | 单文档 push/pull、目录同步规划、TOC 重建、snapshot restore、manifest 批处理 |
| 明确不做（Out of scope） | 把语雀当通用爬虫；批量覆盖但不做 diff/预览；绕过权限控制 |
| 需要的凭据/环境变量 | 语雀 token（按团队规范配置） |
| 安全边界（默认禁止） | 批量写入/覆盖默认必须先 plan/diff |

### 路由设计（片段）

| 场景（用户意图） | 建议入口命令/动作 | 只读哪一份 reference（按需） | 需要跑哪个 script（按需） | 风险控制（默认开关） |
| --- | --- | --- | --- | --- |
| 同步单文档 | push/pull | `references/single-doc.md` | `scripts/yuque_api.py` | 默认先 dry-run 或 diff 预览 |
| 目录级规划 | plan-dir | `references/dir-sync.md` | `scripts/yuque_api.py plan-dir` | manifest 输出可审阅 |

## 示例（飞书）

下面用 `feishu-doc-sync` 举两个片段，重点是“复杂 skill 如何仍然保持渐进式”。

### 需求拆解（片段）

| 用户原话示例 | 任务类型（动词） | 输入（最小） | 输出（验收） | 风险/不可逆点 | 建议承载（SKILL/ref/script） |
| --- | --- | --- | --- | --- | --- |
| 把 tenant A 的目录同步到本地，先给我 dry-run 计划 | `plan-dir` | tenant、folder token、本地根目录 | 变更清单 | 覆盖/删除/权限继承 | `SKILL 路由 + scripts/feishu_doc_sync.py` |
| 我需要搞清楚 OAuth/tenant/user 模式差异 | `auth` | 当前接入方式 | 正确的配置/排查路径 | 泄漏 token | `references/auth.md` |

### Reference 设计（片段）

| reference 文件 | 主题/目的 | 谁会读它（触发条件） | 关键章节（拟定） | 预期长度 | 是否需要 `## Contents` |
| --- | --- | --- | --- | --- | --- |
| `references/auth.md` | tenant/user/OAuth、token 与权限 | 接入与排查 401/403 | 模式选择、回调、本地存储、安全注意事项 | ~150 行 | Yes |
| `references/pull-export.md` | pull/export 与 markdown mapping | 导出/拉取失败排查 | 格式映射、媒体、注意事项 | ~120 行 | Yes |

## 提交前快速检查

提交前建议按这个顺序自查：

1. `SKILL.md` 是不是“入口”，而不是“总说明书”？
2. `description` 是否明确包含 “Use when ...” 的触发语句？
3. 每个 `references/*.md` 是否都能从 `SKILL.md` 一跳或两跳内到达，没有孤儿 reference？
4. 长 reference（>100 行）是否都有顶部 `## Contents`，并覆盖所有二级章节？
5. 是否已经能一键跑通：`quick_validate.py`、`check_progressive_skills.py`、`check_<skill>.py`？

