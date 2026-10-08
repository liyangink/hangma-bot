# 坐隐 3.0 效果层 / 预算层（**不是**覆盖判定）

> 本节只用于**效果层与预算分配**（把桌赛的钱花在哪）；不得回改、不得支撑任何覆盖判定；覆盖仍按规则可枚举度量、与语料频率无关。
> 本节数字只用于效果层与预算分配：不得回改、不得支撑任何覆盖判定。coverage_ledger 不接受本节数据作参数（代码层保证）。

## 1. 逐类出现率（真实语料分布）

| 类 | 出现窗口（分子） | 计分窗口（分母） | 出现率 | 不可判定 | 有改选的候选 |
| --- | --- | --- | --- | --- | --- |
| `branch.chiitoi_live` | 197541 | 338018 | 58.4410% | 0 | chain_path_value, four_component_path_value, meld_opportunity_cost, meld_waiting_conditional, multiplier_path_potential, seven_pairs_path_value |
| `branch.luxury_locked` | 859 | 338018 | 0.2541% | 0 | chain_path_value, four_component_path_value, meld_waiting_conditional |
| `branch.closer_seven_pairs` | 25665 | 338018 | 7.5928% | 41083 | chain_path_value, four_component_path_value, meld_opportunity_cost, meld_waiting_conditional, multiplier_path_potential, seven_pairs_path_value |
| `chain.open` | 492 | 338018 | 0.1456% | 0 | multiplier_path_potential |
| `chain.gang_step` | 929 | 338018 | 0.2748% | 0 | chain_path_value, four_component_path_value, meld_opportunity_cost, meld_waiting_conditional, multiplier_path_potential |
| `chain.gang_draw_open` | 273 | 338018 | 0.0808% | 0 | chain_path_value, four_component_path_value, meld_opportunity_cost, meld_waiting_conditional |
| `chain.piao_discard` | 248 | 338018 | 0.0734% | 0 | — |
| `chain.break_discard` | 478 | 338018 | 0.1414% | 0 | — |
| `chain.claim_repiao_circle` | 0 | 338018 | 0.0000% | 0 | — |
| `four_white.at_four` | 1 | 338018 | 0.0003% | 0 | — |
| `four_white.derivable_held4` | 0 | 338018 | 0.0000% | 0 | — |
| `four_white.unknown_piao` | 0 | 338018 | 0.0000% | 0 | — |
| `baotou.active` | 1198 | 338018 | 0.3544% | 0 | multiplier_path_potential |
| `baotou.discard_recheck` | 248 | 338018 | 0.0734% | 0 | — |
| `baotou.meld_inherit` | 55 | 338018 | 0.0163% | 0 | multiplier_path_potential |
| `baotou.decline_win_for_piao` | 246 | 338018 | 0.0728% | 0 | — |
| `overlay.four_white_baotou` | 0 | 338018 | 0.0000% | 0 | — |
| `overlay.chiitoi_baotou` | 281 | 338018 | 0.0831% | 0 | — |
| `overlay.gang_piao_mix` | 0 | 338018 | 0.0000% | 0 | — |
| `overlay.plain_branch_max` | 0 | 338018 | 0.0000% | 0 | — |
| `overlay.global_max` | 0 | 338018 | 0.0000% | 0 | — |
| `payrole.self_dealer` | 100446 | 338018 | 29.7162% | 0 | chain_path_value, four_component_path_value, meld_opportunity_cost, meld_waiting_conditional, multiplier_path_potential, seven_pairs_path_value |
| `payrole.self_nondealer` | 237572 | 338018 | 70.2838% | 0 | chain_path_value, four_component_path_value, meld_opportunity_cost, meld_waiting_conditional, multiplier_path_potential, seven_pairs_path_value |
| `meld.claim_window` | 15794 | 338018 | 4.6725% | 0 | chain_path_value, four_component_path_value, meld_opportunity_cost, meld_waiting_conditional, multiplier_path_potential, seven_pairs_path_value |
| `meld.waiting_facts_available` | 265154 | 338018 | 78.4438% | 0 | chain_path_value, four_component_path_value, meld_opportunity_cost, meld_waiting_conditional, multiplier_path_potential, seven_pairs_path_value |
| `gate.you_cai_bi_kao` | 0 | 338018 | 0.0000% | 0 | — |
| `gate.wall_end_gang_ban` | 258 | 338018 | 0.0763% | 0 | meld_waiting_conditional |
| `gate.catch_play_owner` | 238 | 338018 | 0.0704% | 209 | four_component_path_value, meld_opportunity_cost, meld_waiting_conditional, multiplier_path_potential |

## 2. 活跃分量分布（普通局 vs 特殊局）

| 活跃分量 | 窗口 | 占比 |
| --- | --- | --- |
| branch | 196864 | 58.2407% |
| （无） | 138563 | 40.9928% |
| chain | 996 | 0.2947% |
| baotou | 718 | 0.2124% |
| branch+chain | 396 | 0.1172% |
| branch+baotou | 217 | 0.0642% |
| chain+baotou | 199 | 0.0589% |
| branch+chain+baotou | 64 | 0.0189% |
| four_white | 1 | 0.0003% |

**普通局**（只有分支分量活跃（链 / 四白 / 爆头三个分量在本窗口都没有翻转余地））：196864 / 338018（58.2407%）

## 3. 信息量预判（可复算）

判据：判据是**可复算的**：本语料上该类里六个静态注册候选的改选数是否全为 0；全为 0 的类对现有候选是**无差别类**（提供的是噪声，不是强度证据）。

- **可分辨类**：branch.chiitoi_live, branch.luxury_locked, branch.closer_seven_pairs, chain.open, chain.gang_step, chain.gang_draw_open, baotou.active, baotou.meld_inherit, payrole.self_dealer, payrole.self_nondealer, meld.claim_window, meld.waiting_facts_available, gate.wall_end_gang_ban, gate.catch_play_owner
- **无差别类**：chain.piao_discard, chain.break_discard, four_white.at_four, baotou.discard_recheck, baotou.decline_win_for_piao, overlay.chiitoi_baotou

## 4. 用途结论

- **普通局可以评强度、特殊局多半只能评行为**：特殊类出现太少、在有限桌数内攒不够样本 ⇒ 其强度无法分辨。
- 特殊局的强度只能做**条件化评估**：
  - 预先冻结采样规则与种子（不得按候选表现挑局面）；
  - 局面选取规则与候选身份一起落盘，先冻结后运行；
  - 结论只落在**条件效应**上，不外推整体积分；
  - 样本不足时输出未分辨，而不是用点估计宣称强弱。
- 本节的低出现率**只**说明效果层样本不足，**不**构成「机制稀有」的判断，也不得据此做预算规划（记录缺口 ≠ 机制稀有）。
