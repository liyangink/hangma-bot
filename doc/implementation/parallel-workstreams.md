# MVP 后并行施工导航

> 2026-09-05；代码事实基线 `c17ce0618d17476526bfe8b2f69a19f11b19fb82`。
> 当前产物是契约与开工文档，新增模块尚未实现。用户自行委派实施 Agent；主审负责契约、集成与启发式策略迭代。

2026-09-08 海选公共接入增补（提案）：旧工作包的历史状态不代表当前实现进度。赛事目标、收益模型、基础启发式与比赛策略并行时，新增共享改动按[公共冻结清单与冲突图](./qualifier-utility-v1.md#86-公共接入冻结清单与并行冲突图)协调；沿用下文既有文件归属，逐共享文件指定最终集成人。新算法文件可独立开发，公共类型、编解码、预算、装配与离线驱动统一合入；未验证的路线和模型载荷不冒充已冻结契约。此增补不创建任务、分支或共同提交。

## 1. 分工与阅读入口

可以同时开工，但文件归属和少量共享类型需要集中集成；“并行”不表示没有交接依赖。

| 工作线 | 必读实施文档 | 第一份可独立交付的结果 |
| --- | --- | --- |
| 审计 | [审计增强](./audit-enhancement.md) | 完整决策 codec/采集，以及三个真实分块样本的统一牌谱 |
| 模拟 | [模拟开工指南](./simulation-start.md) | 规则推进、可见观察、完整桌赛和导出导入 |
| 评估 | [评估开工指南](./evaluation-start.md) | 固定决策集比较、结果汇总；随后接模拟器 |
| 自由赛 | [自动匹配接入指南](./free-match-start.md) | `/api/match` 单自动房生命周期和归档；默认完赛后退出 |
| 策略与集成 | [策略迭代计划](./policy-iteration-plan.md) | 基于源码的候选问题分析、评分审查集；候选完成后等模拟评估 |

每线同时读取[共享契约 parallel-v1](./parallel-contracts.md)、[版本清单](./contracts/parallel-v1.json)、[验收向量](./contracts/contract-vectors.json)及自己触及目录的 AGENTS.md。详细字段只在共同契约或其明确指定的 codec 文档定义，其他指南不复制同名模型。

本批已完成[设计交叉审查](./reviews/parallel-v1-design-review-2026-09-05.md)。报告区分已修正文档与实施时仍须执行的测试。

## 2. 依赖与集成顺序

先共享一个真实提交，再分支。契约冻结的是标识、文件字段、权限和调用结果；不冻结尚无消费者的内部类、文件拆分或规则推进细节。

| 顺序 | 集成内容 | 其他线此时可以做什么 |
| --- | --- | --- |
| C0 文档契约 | 把本批文档/向量提交一次，记录真实 SHA；源码基线 SHA 与契约提交 SHA 分开 | 各机器从同一契约提交开工；不得把 c17ce06 误认为已经包含本批文档 |
| C1 最小代码接触面 | 审计交付 codec、AuditKind/schema 配套及 raw match_response；自由赛的模式/初始化语义扩展由主审统一集成 | 各线内部工作继续；评估可接真实 codec，自由赛可保留匹配原文；不要求先完成全部审计 |
| A/E | 审计文件读写 + 评估固定决策集/汇总 | 自由赛产生标准运行目录，评估逐个消费实际数据；模拟继续推进 |
| S/E | 模拟规则一致性与完整桌赛通过，评估接公开接口 | 执行同牌山/换座实验，仍不能声称完整赛事晋级模拟 |
| 集成验收 | 目标 M 的采集/监控开销、SSE/截止/恢复、自动匹配单会话 | 对比候选策略，保留原稳定策略可切回 |
| 后续 | 通过数据/规则/环境/评估门禁后再建 learning 和所需 competition 实现 | 两个模型训练的具体标签与阶段模拟另按数据事实设计 |

工作线不互相 cherry-pick 未发布的内部提交。C1 只包含能导入、生产方和校验方匹配且通过相关测试的实际实现，不建临时空模块让其他线“先能 import”。需等待的跨模块测试明确标 pending，不能用 mock 结果当作通过。

## 3. 文件所有权

每个现有共享文件只有一名最终编辑/集成人。Agent 在自己分支实现专属文件，共享文件所需改动写入 handoff，由主审按顺序落入集成分支；无需为每个内部实现选择询问用户。

| 路径 | 所有者 | 其他线处理方式 |
| --- | --- | --- |
| adapters/recording/*；application/audit.py、audit_codec.py、decision_loop.py | 审计 | 不把自由赛状态机塞进 decision_loop，不重写已修复的提交路径 |
| adapters/official/replay.py；offline/replay.py；scripts/audit_tool.py | 审计 | 模拟/评估消费公开文件与 codec，不导入转换器私有函数 |
| simulation/*；hangma/progression.py；offline/replay_check.py | 模拟 | 评估只依赖 SimulationEngine 及 check_hand |
| hangma/engine.py、internal_types.py 的推进扩展 | 模拟起草、主审集成 | 旧规则行为改动单列；同期策略线不改这些文件 |
| offline/evaluate.py、evaluation_results.py、evaluation_statistics.py；scripts/evaluate.py | 评估 | 审计/模拟不实现统计报告的第二套算法 |
| adapters/official/auto_match.py；application/auto_match_runtime.py；scripts/run_auto_match.py | 自由赛 | 保持官方 game/transport/scheduler/notify 的已验收安全路径复用 |
| policy/*；后续确有逻辑的 competition/* | 主审策略线 | 其他 Agent 报案例，不顺手调权重 |
| application/contracts.py、kernel/*、hangma/interface.py、policy/interface.py | 主审 | 审计提出 AuditKind 小节，自由赛提出 mode/target/terminal 小节；不得并发修改同一文件 |
| bootstrap.py、共享父目录 __init__.py、pyproject.toml、既有运行脚本、官方既有公共文件 | 主审 | 在 handoff 给出所需装配/导出差异，避免整份复制组合根 |
| 各线新增测试文件、handoffs/<line>.md | 各线 | 共享契约测试由主审集中；本线新增消费测试不得改另一线的预期 |
| 本批契约、架构、主方案、术语与顶层导航 | 主审 | 各线提出变更案例，由主审更新一次 |

“主审集成”不阻断内部实现：各线可在测试组合中注入现有类型和 Fake，并交付准确的共享补丁。需要依赖新 AuditKind/模式的生产测试，应在收到 C1 提交后运行；不能把没运行的测试写为通过。若同一机器使用 worktree，各目录独立；不得多个 Agent 同时写同一 checkout。

## 4. 多机器与分支约定

建议分支为 `codex/audit-plus-v1`、`codex/simulation-v1`、`codex/evaluation-v1`、`codex/auto-match-v1`；策略使用 `codex/policy-iteration-v1`。本方案不自动创建或切换用户分支。

开工记录 `contract_commit`、`git rev-parse HEAD`、本地是否 dirty、Python 版本和本线。共享仓库通过正常 Git fetch 取得提交；离线节点可用 Git bundle 转移代码。统一规则是以真实 SHA 验证来源，不要求相同绝对目录、虚拟环境名或机器名。

每次交付使用已提交的模块变更和 handoff；集成人先核对契约版本，按 C1→模块→组合根顺序合入。若分支基线偏旧，先合公共契约提交；不复制另一个节点的整棵源码目录来“同步”。遇到字段/语义冲突，保留旧接口直到明确迁移，不能让两个同义版本静默共存。

数据用审计方案的不可变 bundle + SHA-256 转移，代码走 Git，模型以后走独立版本产物。Token 留在各节点专用运行配置，不放入 handoff/夹具/归档。运行目录一个 run_id 对应一个进程；自动匹配 Token 一个节点独占，四身份测试房间用四个隔离进程。

## 5. 交接报告和契约变更

每线创建 `doc/implementation/handoffs/<line>.md`，以下是报告字段，不是未经执行的验收承诺：

```text
工作线 / contract_id / contract_commit / code_commit
实际改动文件及公开导出
完成阶段及支持范围
测试命令、退出状态、结果摘要与证据路径
未通过或未验证事项（含环境/资料限制）
样例产物路径、SHA-256、来源与缺失
需要主审集成的共享文件差异（具体符号/调用点）
受控变更请求（如有）：触发案例、旧/新语义、兼容方式、调用方和回归用例
```

共享变更由主审评审并发出新共同提交；可选字段与内部实现改动不要求所有线停工。修改字段类型、单位、信息权限、初始化副作用或身份算法必须登记版本和迁移。实现若证明契约不合理，带可复现案例回报，不让模块独自发明 parallel-v2。

## 6. 可直接委派的任务文本

把下面对应段落和**实际 C0 提交 SHA**交给每个实施 Agent，即可在不同节点开工。每条任务都只授权自己的工作线；真实比赛运行按现有授权配置执行并留证据。

**审计 Agent：** 从团队发布的 parallel-v1 契约提交建立独立分支，阅读根/目录规范、parallel-contracts.md、audit-enhancement.md 和契约向量。复用已合入的 raw/SSE，完成 A1→A2→A3，保留 v1 信封，补完整决策、生产端失败持久化、跨进程身份映射、可迁移证据包和只读 watch。先交付供其他线使用的 codec/raw 扩展。只编辑认领文件；共享类型/组合根给主审精确差异。提交 handoffs/audit.md 和实际测试/样例哈希。

**模拟 Agent：** 从相同契约提交建立独立分支，按 simulation-start.md 实现冻结的具体接口。WorldState 归 simulation，规则推进归 hangma；不复制第二套规则，不把缺墙 full_history 变成 full_world。实现完整 Rounds、观察隔离、不可变分叉、同牌山和世界导入导出，并提供 check_hand 历史核对。先用真实 fixture 和现有核心独立推进，不等待审计全部完成。提交 handoffs/simulation.md、支持矩阵与证据。

**评估 Agent：** 从相同契约提交建立独立分支，按 evaluation-start.md 先做固定决策比较和结果汇总，再用测试 Fake 验证编排，模拟就绪后接公开 SimulationEngine。区分历史规则和重算规则、逻辑时钟和性能测试、诊断指标和完整桌赛效果；按同牌山/换座聚类统计。不得修改策略或模拟私有实现，不输出 mock 强度结论。提交 handoffs/evaluation.md 和可阅读实际报告。

**自由赛 Agent：** 从相同契约提交建立独立分支，按 free-match-start.md 接入全局 Token `/api/match`，默认只完成一个自动房。实现专用生命周期，复用已有 GameTask/GameSession/SSE/ActionGate，禁止调用 auto 房 register/ready，区分声明上限与平台配置，处理 10 次/分钟、容量、结果不确定入席和关闭前结果留存。先交受控 mode/initialize 语义差异给主审；不改审计/规则/策略协议。提交 handoffs/free-match.md 和实际验收证据，未知下载能力保持未知。

主审继续按 policy-iteration-plan.md 做分析与候选实现，模块交付后组织评估和集成，不把尚未验证的策略设为稳定默认值。

## 2026-09-11 模型与赛事两线的共同起点

共享接入现已有实际实现和契约测试，入口为 [outcome-v1](./model-competition-contract-v1.md)。模型线独立开发 `learning` 编码/网络/制品与 `offline` 标签/训练；赛事线独立开发 `competition` 排名事实/目标与人工情景评估。两线复用 `OutcomeQuery`、结果类型和单局目标，经 `bootstrap.build_outcome_policy` 接入同一 `choose`。

公共类型、codec、策略共享入口、组合根与公共评测驱动由集成人维护。各线基于包含本说明的共同提交创建独立工作区；共享契约通过不等于模型或赛事目标已具备完整生产能力，具体剩余工作见 [启动计划](./model-competition-kickoff-2026-09-11.md)。
