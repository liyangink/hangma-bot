# P2 条件状态转移独立审查

日期：2026-09-30。结论：本轮发现并复现了三类会接受不可能公开序列的机械缺口；并行实施已补上对应守卫，独立回归文件当前 6 项通过。此结果只覆盖下表反例，不等于 P2 机械完成门通过。

## 依据和范围

- [P2 条件状态合同](./P2-CONDITIONAL-STATE-CONTRACT.md)：待裁决动作不得提前生效；待补牌要有已执行杠的证据；碰/明杠窗先于吃窗；与公开物理上限矛盾的给定边须拒绝。
- [官方指南 v34 正文](../../doc/references/official-guide-v34-content.txt)（2026-09-15 抓取）§1.1、§2：一牌四张、碰/明杠窗口先于吃窗口，杠成功后才有杠补牌。此处没有引用未取得全文的 v35 来补规则。
- 对照生产 `HangmaRules` 同次合法候选、`progression.resolve_public_response` 及当前 `route_transition.py`。只读生产代码；仅新增[独立回归测试](../../tests/unit/hangma/test_route_transition_audit.py)。

## 已复现反例与状态

| 优先级 | 最小反例与原行为 | 归类 | 当前状态 |
| --- | --- | --- | --- |
| P1 | 本人暗牌已有三张 `1w`，他座刚弃第四张 `1w`；本人过牌，给定另一座碰 `1w`。最初 `advance_given_response` 返回 `resolved` 并写入三张同码副露，容量只标 `unknown`。公开事实已证明他座不可能持有碰所需两张。 | 机械；给定的他座暗牌无需验证，但公开四张上限必须验证。 | 并行实施加入获裁决他座鸣牌的逐码容量守卫；独立测试现通过。 |
| P1 | 明杠根尚未收到完整响应选择，预列成功态 `structural_only=True`、`claim_awarded=False`；直接把该态传给 `apply_given_draw(..., replacement=True)`。原实现进入本人 `DRAW_ACTION`，使未执行杠取得补牌与后续资格。 | 机械；不是缺少未来牌值，给定牌值也不能代替杠获执行的证据。 | 并行实施加入待补牌执行证据门禁；独立测试现通过。 |
| P1 | 本人普通弃 `3b` 后，直接以 `response_chi` 和下家 `Pass` 调 `advance_given_response`，完全跳过 `response_peng`。原实现返回 `resolved`。 | 机械；窗口顺序由官方规则和同源 `progression` 确定。 | 并行实施加入普通弃牌后的碰窗顺序门禁；独立测试现通过。 |

明杠根另有一个并发修复：初读版本只保存已移三张暗牌的待补态；未齐选择或多人鸣牌阻断时会把它当作当前态。复测时已增加未提交的 `proposal_state`，独立测试确认这些未裁决路径保留原暗牌、链与副露数。原反例不再列为未解决问题。

## 验证边界

执行 `.venv/bin/python -m pytest -q tests/unit/hangma/test_route_transition_audit.py`：6 passed。审查没有验证全事件身份/官方 `seq` 连续性、所有他座暗牌合法性或完整结算终点；这些仍须按合同和[机械矩阵](./P2-MECHANICAL-MATRIX.md)继续验收。特别是条件状态目前没有完整受控的给定事件身份与单局根配置绑定，不能从本次六个用例推断全量公开序列已闭合。
