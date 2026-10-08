# 3.6b 逐类判定（G-2C）：逐候选 × 四面板（canonical 在前）

> 机读同源：[perclass-summary.json](./perclass-summary.json)。三态读法见
> [tools/sitin_gates.py](../../tools/sitin_gates.py) 的 CLASS_VERDICT_NOTES。

| 候选 | 面板 | 汇总 | 已声明 | reliable | insufficient | not_verified | 类外溢出 | 归属未知 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| chain_path_value | canonical | INSUFFICIENT | 12 | 1 | 6 | 5 | 0 | 0 |
| chain_path_value | new-baseline | INSUFFICIENT | 12 | 1 | 6 | 5 | 0 | 0 |
| chain_path_value | old-corpus-control | INSUFFICIENT | 12 | 0 | 1 | 11 | 0 | 0 |
| chain_path_value | trigger | INSUFFICIENT | 12 | 5 | 3 | 4 | 0 | 0 |
| four_component_path_value | canonical | INSUFFICIENT | 19 | 4 | 9 | 6 | 0 | 0 |
| four_component_path_value | new-baseline | INSUFFICIENT | 19 | 4 | 8 | 7 | 0 | 0 |
| four_component_path_value | old-corpus-control | INSUFFICIENT | 19 | 2 | 2 | 15 | 0 | 0 |
| four_component_path_value | trigger | INSUFFICIENT | 19 | 7 | 4 | 8 | 0 | 0 |
| meld_opportunity_cost | canonical | PASS | 2 | 2 | 0 | 0 | 0 | 0 |
| meld_opportunity_cost | new-baseline | PASS | 2 | 2 | 0 | 0 | 0 | 0 |
| meld_opportunity_cost | old-corpus-control | PASS | 2 | 2 | 0 | 0 | 0 | 0 |
| meld_opportunity_cost | trigger | INSUFFICIENT | 2 | 0 | 0 | 2 | 0 | 0 |
| meld_waiting_conditional | canonical | PASS | 2 | 2 | 0 | 0 | 0 | 0 |
| meld_waiting_conditional | new-baseline | PASS | 2 | 2 | 0 | 0 | 0 | 0 |
| meld_waiting_conditional | old-corpus-control | PASS | 2 | 2 | 0 | 0 | 0 | 0 |
| meld_waiting_conditional | trigger | INSUFFICIENT | 2 | 0 | 0 | 2 | 0 | 0 |
| multiplier_path_potential | canonical | INSUFFICIENT | 11 | 4 | 3 | 4 | 0 | 0 |
| multiplier_path_potential | new-baseline | INSUFFICIENT | 11 | 3 | 4 | 4 | 0 | 0 |
| multiplier_path_potential | old-corpus-control | INSUFFICIENT | 11 | 3 | 1 | 7 | 0 | 0 |
| multiplier_path_potential | trigger | INSUFFICIENT | 11 | 0 | 6 | 5 | 0 | 0 |
| seven_pairs_path_value | canonical | INSUFFICIENT | 4 | 2 | 2 | 0 | 0 | 0 |
| seven_pairs_path_value | new-baseline | INSUFFICIENT | 4 | 2 | 2 | 0 | 0 | 0 |
| seven_pairs_path_value | old-corpus-control | INSUFFICIENT | 4 | 2 | 1 | 1 | 0 | 0 |
| seven_pairs_path_value | trigger | INSUFFICIENT | 4 | 0 | 2 | 2 | 0 | 0 |

> 面板口径（F7）：**canonical 面板是唯一分母口径**；new-baseline 是诊断子集，
> 只用于自检，**不得**与 canonical 的数字相加或混用。

| 面板 | 口径 |
| --- | --- |
| canonical | panel-canonical-20260910（105 份 / 359,262 行，record_layer_filled=true） |
| new-baseline | subset-perclass-frozen（5 份 / 16,851 行，raw；**诊断子集**，不得当分母） |
| old-corpus-control | auto-match-2026-09-06（3,343 行；历史对照） |
| trigger | 构造触发集 48 窗口（**非效果证据**） |

**读法**：汇总只取最弱环节（任一已声明类未达 reliable 即不给通过）；
reliable 只说明「该类在本面板上被验证过」，不是效果结论。

## 未达 reliable 的已声明类（逐候选，新基线）

**chain_path_value**（INSUFFICIENT）：
- chain.open — insufficient（fired_no_change）
- chain.piao_discard — insufficient（fired_no_change）
- chain.break_discard — insufficient（fired_no_change）
- four_white.unknown_piao — not_verified（no_position_on_panel）
- baotou.active — insufficient（fired_no_change）
- baotou.decline_win_for_piao — insufficient（fired_no_change）
- overlay.four_white_baotou — not_verified（no_position_on_panel）
- overlay.chiitoi_baotou — insufficient（fired_no_change）
- overlay.gang_piao_mix — not_verified（no_position_on_panel）
- overlay.plain_branch_max — not_verified（no_position_on_panel）
- overlay.global_max — not_verified（no_position_on_panel）

**four_component_path_value**（INSUFFICIENT）：
- chain.open — insufficient（fired_no_change）
- chain.piao_discard — insufficient（fired_no_change）
- chain.break_discard — insufficient（fired_no_change）
- four_white.at_four — not_verified（no_position_on_panel）
- four_white.derivable_held4 — not_verified（no_position_on_panel）
- four_white.unknown_piao — not_verified（no_position_on_panel）
- baotou.active — insufficient（fired_no_change）
- baotou.discard_recheck — insufficient（fired_no_change）
- baotou.meld_inherit — insufficient（fired_below_floor）
- baotou.decline_win_for_piao — insufficient（fired_no_change）
- overlay.four_white_baotou — not_verified（no_position_on_panel）
- overlay.chiitoi_baotou — insufficient（fired_no_change）
- overlay.gang_piao_mix — not_verified（no_position_on_panel）
- overlay.plain_branch_max — not_verified（no_position_on_panel）
- overlay.global_max — not_verified（no_position_on_panel）

**meld_opportunity_cost**（PASS）：

**meld_waiting_conditional**（PASS）：

**multiplier_path_potential**（INSUFFICIENT）：
- chain.open — insufficient（fired_below_floor）
- chain.gang_draw_open — insufficient（fired_below_floor）
- four_white.unknown_piao — not_verified（no_position_on_panel）
- baotou.active — insufficient（fired_below_floor）
- overlay.chiitoi_baotou — insufficient（fired_below_floor）
- overlay.gang_piao_mix — not_verified（no_position_on_panel）
- overlay.plain_branch_max — not_verified（no_position_on_panel）
- overlay.global_max — not_verified（no_position_on_panel）

**seven_pairs_path_value**（INSUFFICIENT）：
- chain.gang_draw_open — insufficient（fired_below_floor）
- overlay.chiitoi_baotou — insufficient（fired_below_floor）

