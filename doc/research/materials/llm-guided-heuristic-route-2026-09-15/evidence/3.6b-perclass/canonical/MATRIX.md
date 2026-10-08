# 坐隐 3.0 分量—场景类矩阵（逐候选 × 逐类）

> 由 [tools/sitin_scenario_classes.py](../../tools/sitin_scenario_classes.py) 生成，
> 与 coverage.json 同一份数据；单元格 = 证据状态（触发/改选）。
> **只描述现状与缺口，不给效果结论。**

## 1. 候选汇总

| 候选 | 声明覆盖类数 | 未声明类数 | 证据状态分布 |
| --- | --- | --- | --- |
| chain_path_value | 12 | 16 | changed=1, fired_no_change=6, no_window=5, undeclared=16 |
| four_component_path_value | 19 | 9 | changed=4, fired_no_change=9, no_window=6, undeclared=9 |
| meld_opportunity_cost | 2 | 26 | changed=2, undeclared=26 |
| meld_waiting_conditional | 2 | 26 | changed=2, undeclared=26 |
| multiplier_path_potential | 11 | 17 | changed=5, fired_no_change=2, no_window=4, undeclared=17 |
| seven_pairs_path_value | 4 | 24 | changed=2, fired_no_change=2, undeclared=24 |

## 2. 逐类单元格（undeclared 用 — 表示）

| 候选 | bran.chiitoi_li | bran.luxury_loc | bran.closer_sev | chai.open | chai.gang_step | chai.gang_draw_ | chai.piao_disca | chai.break_disc | chai.claim_repi | four.at_four | four.derivable_ | four.unknown_pi | baot.active | baot.discard_re | baot.meld_inher | baot.decline_wi | over.four_white | over.chiitoi_ba | over.gang_piao_ | over.plain_bran | over.global_max | payr.self_deale | payr.self_nonde | meld.claim_wind | meld.waiting_fa | gate.you_cai_bi | gate.wall_end_g | gate.catch_play |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| chain_path_value | — | — | — | 478/0 fired_no_change | 929/81 changed | — | 248/0 fired_no_change | 478/0 fired_no_change | — | — | — | 0/0 no_window | 249/0 fired_no_change | — | — | 246/0 fired_no_change | 0/0 no_window | 60/0 fired_no_change | 0/0 no_window | 0/0 no_window | 0/0 no_window | — | — | — | — | — | — | — |
| four_component_path_value | 10636/997 changed | 248/30 changed | — | 478/0 fired_no_change | 929/66 changed | — | 244/0 fired_no_change | 478/0 fired_no_change | — | 1/0 fired_no_change | 0/0 no_window | 0/0 no_window | 264/0 fired_no_change | 244/0 fired_no_change | 28/0 fired_no_change | 242/0 fired_no_change | 0/0 no_window | 79/0 fired_no_change | 0/0 no_window | 0/0 no_window | 0/0 no_window | — | — | 10345/976 changed | — | — | — | — |
| meld_opportunity_cost | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | 15794/1678 changed | 15794/1678 changed | — | — | — |
| meld_waiting_conditional | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | 15405/6792 changed | 15405/6792 changed | — | — | — |
| multiplier_path_potential | 10212/171 changed | — | 1617/24 changed | 1/1 changed | — | 44/0 fired_no_change | — | — | — | — | — | 0/0 no_window | 20/1 changed | — | — | — | — | 19/0 fired_no_change | 0/0 no_window | 0/0 no_window | 0/0 no_window | — | — | — | 10213/172 changed | — | — | — |
| seven_pairs_path_value | 10212/66 changed | — | 1617/20 changed | — | — | 44/0 fired_no_change | — | — | — | — | — | — | — | — | — | — | — | 19/0 fired_no_change | — | — | — | — | — | — | — | — | — | — |

## 3. 列名对照

| 简写 | 完整类 id |
| --- | --- |
| bran.chiitoi_li | `branch.chiitoi_live` |
| bran.luxury_loc | `branch.luxury_locked` |
| bran.closer_sev | `branch.closer_seven_pairs` |
| chai.open | `chain.open` |
| chai.gang_step | `chain.gang_step` |
| chai.gang_draw_ | `chain.gang_draw_open` |
| chai.piao_disca | `chain.piao_discard` |
| chai.break_disc | `chain.break_discard` |
| chai.claim_repi | `chain.claim_repiao_circle` |
| four.at_four | `four_white.at_four` |
| four.derivable_ | `four_white.derivable_held4` |
| four.unknown_pi | `four_white.unknown_piao` |
| baot.active | `baotou.active` |
| baot.discard_re | `baotou.discard_recheck` |
| baot.meld_inher | `baotou.meld_inherit` |
| baot.decline_wi | `baotou.decline_win_for_piao` |
| over.four_white | `overlay.four_white_baotou` |
| over.chiitoi_ba | `overlay.chiitoi_baotou` |
| over.gang_piao_ | `overlay.gang_piao_mix` |
| over.plain_bran | `overlay.plain_branch_max` |
| over.global_max | `overlay.global_max` |
| payr.self_deale | `payrole.self_dealer` |
| payr.self_nonde | `payrole.self_nondealer` |
| meld.claim_wind | `meld.claim_window` |
| meld.waiting_fa | `meld.waiting_facts_available` |
| gate.you_cai_bi | `gate.you_cai_bi_kao` |
| gate.wall_end_g | `gate.wall_end_gang_ban` |
| gate.catch_play | `gate.catch_play_owner` |

## 4. 证据状态定义

| 状态 | 含义 |
| --- | --- |
| changed | 触发且改变了首选 |
| fired_no_change | 触发过但没改变首选 |
| no_fire | 类内有窗口但候选一次都没给出非零调整 |
| no_window | 本面板该类一个窗口都没有（**不是**机制稀有的结论） |
| undeclared | 候选没有声明覆盖该类（派单口径：无声明即标 undeclared） |

矩阵只描述**现状与缺口**，不给任何效果结论；数字由 coverage.json 同一份逐窗口记录聚合而来，可用 --coverage 复算。
