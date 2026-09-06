# `hangma` 实施说明

## 交付结果

实现绑定 `RuleConfig` 的唯一杭麻规则深模块，在线上窗口内生成完整合法候选，同时保证复杂分支出错时仍能给出安全紧急动作。

## 建议内部结构

```text
hangma/
  interface.py        # 受控公开契约（含 CandidateFacts 候选牌效事实，2026-09-04）
  engine.py           # HangmaRules 受控签名与公开实现
  emergency.py        # 不依赖复杂搜索的紧急路径
  internal_types.py   # 必要时放内部不可变结果，不对外暴露（牌序引用 kernel 权威常量）
  hand_analysis.py    # 普通型、七对、向听和有效牌
  candidate_facts.py  # 为八类动作族候选生产 CandidateFacts（2026-09-04 新增）
  action_families.py  # 吃碰杠胡各动作族
  special_rules.py    # 财神、抓打圈、爆头和动作链约束
  settlement.py       # 财神链和四家结算
```

牌效事实生产规则（接口协议 §4.1）：弃牌按打出后余牌、吃/碰按合法最佳后续弃牌后的等待状态（`best_followup_discard`）、杠按补牌前余牌口径（`replacement_draw_unknown=True`）、胡牌 `fact_kind=WIN` 且 `shanten_after=-1`、不适用或分析失败不伪造数值；紧急路径按设计不生产事实（`facts=None`）。

内部可以继续拆分，但调用方只看 `HangmaRules`。不要为了每个算法文件增加端口。

2026-09-06：响应 Pass 已补充当前等待牌效，复用 `hand_analysis`，异常沿用事实降级；本地分析语义与旧版消费边界见[接口协议 §4.3](../interface-contracts.md#43-响应过牌的等待事实与冻结策略兼容2026-09-06)。不改变胡牌、动作合法性或结算。

## 主 Agent 的并行实施方案

规则主 Agent 负责整体交付，并应主动派发子 Agent，无需用户逐项拆分：

1. 子 Agent A：`hand_analysis.py`，实现普通型、七对、向听、有效牌和确定性分解；
2. 子 Agent B：`action_families.py`，实现出牌、吃、碰、杠、胡、过的候选生成；
3. 子 Agent C：`special_rules.py + settlement.py`，实现财神特殊状态、动作链和结算。

主 Agent 自己负责 `engine.py`、`emergency.py`、内部类型、公开契约适配、故障隔离和官方对拍。开始并行前先建立内部数据契约和文件所有权；共享工作区中不得让两个 Agent 同时修改同一文件。

子模块关系：

```text
hand_analysis ──→ action_families ──┐
special_rules ──────────────────────┼─→ engine → RuleAnalysis
settlement ← special_rules          │
emergency ──────────────────────────┘
```

箭头表示右侧可以调用左侧；`emergency` 不调用其他复杂分支。`action_families` 不复制手牌分解，`special_rules` 不复制通用合法性，`settlement` 不重新推导完整行动状态。

每个子 Agent 交付时必须附带测试、未覆盖项、规则依据和假设。主 Agent 在集成后统一运行官方金例、性质测试、故障隔离和性能基准，并对最终结果负责。

## 算法与故障隔离

- 普通型使用花色分解、动态规划或记忆化搜索；七对单独计算后取合法最优。
- 财神数量、公开组合限制、抓打圈、爆头/飘/杠链必须由同一规则状态解释。
- 吃、碰、杠、胡、弃牌/过分别在故障边界中计算；分支异常形成 `RuleIssue`，不能让整个 `analyze()` 崩溃。
- 紧急路径不调用向听、有效牌、番数网络服务或 `fan-calc`。

## 完成定义

- 第一阶段列出的动作族和特殊规则都有正反例。
- 本地胡牌/计分与官方金例、`fan-calc` 随机对拍；差异必须先保守降级再修复。
- `RuleAnalysis` 满足接口不变量，且每次降级可审计。
- 基准覆盖最差合法手牌和并发窗口，报告 P95/P99。
- 子 Agent 的所有产物已经由规则主 Agent 集成审查；不存在重复规则源或跨模块依赖。
