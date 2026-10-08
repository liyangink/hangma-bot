# 坐隐 3.0 逐类覆盖账（构造触发集）

> 由 [tools/sitin_scenario_classes.py](../../tools/sitin_scenario_classes.py) 生成。
> **逐类出账，不得合并成单一总分**；汇总只供阅读，**不得作为准入依据**。

## 1. 输入与面板

| 项 | 值 |
| --- | --- |
| 输入 | `/Users/liyang/Projects/Opensource/hangma-bot/review/llm-guided-heuristic-route-2026-09-15/evidence/3.6b-perclass/corpus-manifest-canonical.json` |
| 行数 / 计分窗口 | 359262 / 338018 |
| 构造集 | False |
| 证据类别 | admission |
| 对账（总行 = 排除 + 失败 + 计分） | True |
| 覆盖下限 | 8 |
| 门控事实接线（跨包） | 全部已接线 |

## 2. 逐类覆盖（四态）

| 类 | 四态 | 类内窗口 | 不可判定 | 类外窗口 | 候选（触发/改选） |
| --- | --- | --- | --- | --- | --- |
| `branch.chiitoi_live` | **sufficient** | 197541 | 0 | 140477 | chain_path_value 456/49 (undeclared), four_component_path_value 10636/997 (changed), meld_opportunity_cost 10212/1224 (undeclared), meld_waiting_conditional 9936/3996 (undeclared), multiplier_path_potential 10212/171 (changed), seven_pairs_path_value 10212/66 (changed) |
| `branch.luxury_locked` | **sufficient** | 859 | 0 | 337159 | chain_path_value 215/36 (undeclared), four_component_path_value 248/30 (changed), meld_opportunity_cost 33/0 (undeclared), meld_waiting_conditional 33/14 (undeclared), multiplier_path_potential 33/0 (undeclared), seven_pairs_path_value 33/0 (undeclared) |
| `branch.closer_seven_pairs` | **sufficient** | 25665 | 41083 | 271270 | chain_path_value 7/3 (undeclared), four_component_path_value 1617/316 (undeclared), meld_opportunity_cost 1617/105 (undeclared), meld_waiting_conditional 1534/281 (undeclared), multiplier_path_potential 1617/24 (changed), seven_pairs_path_value 1617/20 (changed) |
| `chain.open` | **sufficient** | 492 | 0 | 337526 | chain_path_value 478/0 (fired_no_change), four_component_path_value 478/0 (fired_no_change), meld_opportunity_cost 1/0 (undeclared), meld_waiting_conditional 1/0 (undeclared), multiplier_path_potential 1/1 (changed), seven_pairs_path_value 0/0 (undeclared) |
| `chain.gang_step` | **sufficient** | 929 | 0 | 337089 | chain_path_value 929/81 (changed), four_component_path_value 929/66 (changed), meld_opportunity_cost 315/19 (undeclared), meld_waiting_conditional 312/28 (undeclared), multiplier_path_potential 182/1 (undeclared), seven_pairs_path_value 182/0 (undeclared) |
| `chain.gang_draw_open` | **sufficient** | 273 | 0 | 337745 | chain_path_value 273/7 (undeclared), four_component_path_value 273/9 (undeclared), meld_opportunity_cost 119/3 (undeclared), meld_waiting_conditional 119/3 (undeclared), multiplier_path_potential 44/0 (fired_no_change), seven_pairs_path_value 44/0 (fired_no_change) |
| `chain.piao_discard` | **sufficient** | 248 | 0 | 337770 | chain_path_value 248/0 (fired_no_change), four_component_path_value 244/0 (fired_no_change), meld_opportunity_cost 0/0 (undeclared), meld_waiting_conditional 0/0 (undeclared), multiplier_path_potential 0/0 (undeclared), seven_pairs_path_value 0/0 (undeclared) |
| `chain.break_discard` | **sufficient** | 478 | 0 | 337540 | chain_path_value 478/0 (fired_no_change), four_component_path_value 478/0 (fired_no_change), meld_opportunity_cost 0/0 (undeclared), meld_waiting_conditional 0/0 (undeclared), multiplier_path_potential 0/0 (undeclared), seven_pairs_path_value 0/0 (undeclared) |
| `chain.claim_repiao_circle` | **not_applicable** | 0 | 0 | 338018 | chain_path_value 0/0 (undeclared), four_component_path_value 0/0 (undeclared), meld_opportunity_cost 0/0 (undeclared), meld_waiting_conditional 0/0 (undeclared), multiplier_path_potential 0/0 (undeclared), seven_pairs_path_value 0/0 (undeclared) |
| `four_white.at_four` | **insufficient** | 1 | 0 | 338017 | chain_path_value 0/0 (undeclared), four_component_path_value 1/0 (fired_no_change), meld_opportunity_cost 0/0 (undeclared), meld_waiting_conditional 0/0 (undeclared), multiplier_path_potential 0/0 (undeclared), seven_pairs_path_value 0/0 (undeclared) |
| `four_white.derivable_held4` | **not_applicable** | 0 | 0 | 338018 | chain_path_value 0/0 (undeclared), four_component_path_value 0/0 (no_window), meld_opportunity_cost 0/0 (undeclared), meld_waiting_conditional 0/0 (undeclared), multiplier_path_potential 0/0 (undeclared), seven_pairs_path_value 0/0 (undeclared) |
| `four_white.unknown_piao` | **not_applicable** | 0 | 0 | 338018 | chain_path_value 0/0 (no_window), four_component_path_value 0/0 (no_window), meld_opportunity_cost 0/0 (undeclared), meld_waiting_conditional 0/0 (undeclared), multiplier_path_potential 0/0 (no_window), seven_pairs_path_value 0/0 (undeclared) |
| `baotou.active` | **sufficient** | 1198 | 0 | 336820 | chain_path_value 249/0 (fired_no_change), four_component_path_value 264/0 (fired_no_change), meld_opportunity_cost 47/0 (undeclared), meld_waiting_conditional 47/0 (undeclared), multiplier_path_potential 20/1 (changed), seven_pairs_path_value 19/0 (undeclared) |
| `baotou.discard_recheck` | **sufficient** | 248 | 0 | 337770 | chain_path_value 248/0 (undeclared), four_component_path_value 244/0 (fired_no_change), meld_opportunity_cost 0/0 (undeclared), meld_waiting_conditional 0/0 (undeclared), multiplier_path_potential 0/0 (undeclared), seven_pairs_path_value 0/0 (undeclared) |
| `baotou.meld_inherit` | **sufficient** | 55 | 0 | 337963 | chain_path_value 9/0 (undeclared), four_component_path_value 28/0 (fired_no_change), meld_opportunity_cost 47/0 (undeclared), meld_waiting_conditional 47/0 (undeclared), multiplier_path_potential 20/1 (undeclared), seven_pairs_path_value 19/0 (undeclared) |
| `baotou.decline_win_for_piao` | **sufficient** | 246 | 0 | 337772 | chain_path_value 246/0 (fired_no_change), four_component_path_value 242/0 (fired_no_change), meld_opportunity_cost 0/0 (undeclared), meld_waiting_conditional 0/0 (undeclared), multiplier_path_potential 0/0 (undeclared), seven_pairs_path_value 0/0 (undeclared) |
| `overlay.four_white_baotou` | **not_applicable** | 0 | 0 | 338018 | chain_path_value 0/0 (no_window), four_component_path_value 0/0 (no_window), meld_opportunity_cost 0/0 (undeclared), meld_waiting_conditional 0/0 (undeclared), multiplier_path_potential 0/0 (undeclared), seven_pairs_path_value 0/0 (undeclared) |
| `overlay.chiitoi_baotou` | **sufficient** | 281 | 0 | 337737 | chain_path_value 60/0 (fired_no_change), four_component_path_value 79/0 (fired_no_change), meld_opportunity_cost 19/0 (undeclared), meld_waiting_conditional 19/0 (undeclared), multiplier_path_potential 19/0 (fired_no_change), seven_pairs_path_value 19/0 (fired_no_change) |
| `overlay.gang_piao_mix` | **not_applicable** | 0 | 0 | 338018 | chain_path_value 0/0 (no_window), four_component_path_value 0/0 (no_window), meld_opportunity_cost 0/0 (undeclared), meld_waiting_conditional 0/0 (undeclared), multiplier_path_potential 0/0 (no_window), seven_pairs_path_value 0/0 (undeclared) |
| `overlay.plain_branch_max` | **not_applicable** | 0 | 0 | 338018 | chain_path_value 0/0 (no_window), four_component_path_value 0/0 (no_window), meld_opportunity_cost 0/0 (undeclared), meld_waiting_conditional 0/0 (undeclared), multiplier_path_potential 0/0 (no_window), seven_pairs_path_value 0/0 (undeclared) |
| `overlay.global_max` | **not_applicable** | 0 | 0 | 338018 | chain_path_value 0/0 (no_window), four_component_path_value 0/0 (no_window), meld_opportunity_cost 0/0 (undeclared), meld_waiting_conditional 0/0 (undeclared), multiplier_path_potential 0/0 (no_window), seven_pairs_path_value 0/0 (undeclared) |
| `payrole.self_dealer` | **sufficient** | 100446 | 0 | 237572 | chain_path_value 505/22 (undeclared), four_component_path_value 3636/280 (undeclared), meld_opportunity_cost 4646/465 (undeclared), meld_waiting_conditional 4530/2027 (undeclared), multiplier_path_potential 3051/42 (undeclared), seven_pairs_path_value 3051/17 (undeclared) |
| `payrole.self_nondealer` | **sufficient** | 237572 | 0 | 100446 | chain_path_value 1136/59 (undeclared), four_component_path_value 8525/745 (undeclared), meld_opportunity_cost 11148/1213 (undeclared), meld_waiting_conditional 10875/4765 (undeclared), multiplier_path_potential 7162/130 (undeclared), seven_pairs_path_value 7161/49 (undeclared) |
| `meld.claim_window` | **sufficient** | 15794 | 0 | 322224 | chain_path_value 315/18 (undeclared), four_component_path_value 10345/976 (changed), meld_opportunity_cost 15794/1678 (changed), meld_waiting_conditional 15405/6792 (changed), multiplier_path_potential 10213/172 (undeclared), seven_pairs_path_value 10212/66 (undeclared) |
| `meld.waiting_facts_available` | **sufficient** | 265154 | 0 | 72864 | chain_path_value 315/18 (undeclared), four_component_path_value 10345/976 (undeclared), meld_opportunity_cost 15794/1678 (changed), meld_waiting_conditional 15405/6792 (changed), multiplier_path_potential 10213/172 (changed), seven_pairs_path_value 10212/66 (undeclared) |
| `gate.you_cai_bi_kao` | **not_applicable** | 0 | 0 | 338018 | chain_path_value 0/0 (undeclared), four_component_path_value 0/0 (undeclared), meld_opportunity_cost 0/0 (undeclared), meld_waiting_conditional 0/0 (undeclared), multiplier_path_potential 0/0 (undeclared), seven_pairs_path_value 0/0 (undeclared) |
| `gate.wall_end_gang_ban` | **sufficient** | 258 | 0 | 337760 | chain_path_value 0/0 (undeclared), four_component_path_value 3/0 (undeclared), meld_opportunity_cost 10/0 (undeclared), meld_waiting_conditional 10/10 (undeclared), multiplier_path_potential 3/0 (undeclared), seven_pairs_path_value 3/0 (undeclared) |
| `gate.catch_play_owner` | **sufficient** | 238 | 209 | 337571 | chain_path_value 3/0 (undeclared), four_component_path_value 12/1 (undeclared), meld_opportunity_cost 13/3 (undeclared), meld_waiting_conditional 13/10 (undeclared), multiplier_path_potential 10/1 (undeclared), seven_pairs_path_value 9/0 (undeclared) |

## 3. 类外零增量核对

| 候选 | 声明类数 | 改选窗口 | 类外改选 | 归属未知 |
| --- | --- | --- | --- | --- |
| chain_path_value | 12 | 81 | 0 | 0 |
| four_component_path_value | 19 | 1025 | 0 | 0 |
| meld_opportunity_cost | 2 | 1678 | 0 | 0 |
| meld_waiting_conditional | 2 | 6792 | 0 | 0 |
| multiplier_path_potential | 11 | 172 | 0 | 0 |
| seven_pairs_path_value | 4 | 66 | 0 | 0 |

## 4. 缺口清单

| 类型 | 缺口 | 涉及类 | 所需事实是否已接线 |
| --- | --- | --- | --- |
| 类缺口 | 抓打圈内吃碰后再打财神（财飘链 +1 位点）（undeclared_by_all） | `chain.claim_repiao_circle` | True |
| 类缺口 | 手留 4 张 ⇒ 链内飘出必为 0（可推导）（declared_but_no_fire_on_panel） | `four_white.derivable_held4` | True |
| 类缺口 | 链内飘出不可判定（未知态）（declared_but_no_fire_on_panel） | `four_white.unknown_piao` | True |
| 类缺口 | 四白 × 爆头 叠加（declared_but_no_fire_on_panel） | `overlay.four_white_baotou` | True |
| 类缺口 | 杠飘混合链（declared_but_no_fire_on_panel） | `overlay.gang_piao_mix` | True |
| 类缺口 | 平胡分支上界组合（3 连杠 + 三财飘 + 爆头 + 四白板）（declared_but_no_fire_on_panel） | `overlay.plain_branch_max` | True |
| 类缺口 | 全局上界组合（三豪华七对 + 三财飘 + 四白 + 爆头）（declared_but_no_fire_on_panel） | `overlay.global_max` | True |
| 类缺口 | 本人坐庄（付方恒为 ×8）（undeclared_by_all） | `payrole.self_dealer` | True |
| 类缺口 | 本人闲家（本人胡 +10；庄家胡付 8；闲家胡付 1）（undeclared_by_all） | `payrole.self_nondealer` | True |
| 类缺口 | 有财必拷响（手上有财神时不允许平胡）（undeclared_by_all） | `gate.you_cai_bi_kao` | True |
| 类缺口 | 末局禁杠（牌墙最后 10 墩内禁止杠）（undeclared_by_all） | `gate.wall_end_gang_ban` | True |
| 类缺口 | 抓打圈主身份（圈内本人是否为新打财神者）（undeclared_by_all） | `gate.catch_play_owner` | True |
| 已知缺口 | 庄闲在评分层缺席（且已有一次被判定为结构性空操作的尝试） | payrole.self_dealer, payrole.self_nondealer | True |
| 已知缺口 | 风险项不随番值 / 支付倍率缩放（固定常数） | payrole.self_dealer, payrole.self_nondealer, meld.claim_window | True |

## 5. 边界（必须与账一起引用）

1. 触发集是构造集：只证明接线与提供可触发作用面；不得用于效应估计、排序、淘汰或晋级声明。
2. unknown 表示「该类一个窗口都没判定出来且有窗口不可判定」，**不是**「无影响」，也不得填零。
3. 记录缺口 ≠ 机制稀有：不得用语料频率给机制下稀缺性判断，不得据此做预算规划。
4. 逐类账不得合并成单一总分；汇总字段只供阅读，不得作为准入依据。
5. 庄闲/支付倍率是一等场景维度，但不是番型分量：它不改变同一手内的番型排序。
