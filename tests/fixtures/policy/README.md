# V0 固定决策输入

`v0-decisions.jsonl` 是 2026-09-05 从未修改的 `WeightedHeuristicPolicy` 捕获的八个测试案例：普通弃牌、摸牌已在手中、碰响应、吃响应、七对胡、暗杠、抓打圈和财神。

数据来源是本地构造的公开观察，经当时 HangmaRules 生成候选，不是官方牌谱或比赛标签。每行保存 observation、当时 rules、窗口 phase 和 V0 的完整 expected_plan。测试恢复原 facts，不调用当前规则重算；测试 codec 仅用于公开类型夹具，不可作为生产牌谱实现。

V0 回归比较完整输出，V1 对这些完整事实案例比较动作顺序和数值分数；V1 的理由文本允许变化。故障注入、未知事实及强制胡优先属于另列的行为差异测试。源码指纹和完整默认权重见 `doc/implementation/baselines/heuristic-v0.json`。
