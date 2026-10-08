# C35 预登记：带机制/赛事指标的第二级门禁（`CELL-R6` vs 冻结 v2，全新牌山）

实验 ID：**C35-LEVEL2-MECHANICS**。落盘时间：**2026-09-26 13:17 (+0800)**，**在本批任何阶段文件落盘之前**。
依据：[C35 任务书](./C35-TASK-LEVEL2-MECHANICS.md)、[C31 方法评审第 4 条](./C31-METHOD-REVIEW-AND-EVOLUTION-GUIDE-2026-09-26.md)、[C30 第三批](./C30-RESULT-THIRD-BATCH.md)。
本文件冻结后**不得修改**；任何口径变更只能写进结果文档的「偏离」一节，不得回头改判据。

## 一、批设计（冻结）

| 项 | 值 |
| --- | --- |
| 臂（首个为差值基准） | `r18_v2`、`candidate@review/freematch-deep-dive-20260925/candidates/OPTY-R18-C27-CELL-R6.py` |
| 候选源码 SHA-256 | `d8d2b5ba8f30465e2c272fa40c72577af48e0404f1266ca68321849de717281b`（与 C30 冻结批逐字节一致） |
| **panel seed** | **2026110101**（全新：全仓库仅本次 `c35_probe.py`/`c35_mechanics_gate.py` 出现；**未复用** 2026102311/2026102312） |
| 根 | 1–99（全量，每 mix 99 根） |
| 焦点座位 | 逻辑位 0–3 全轮换（同墙换座；计划与臂无关） |
| 规模 | 2 臂 × 99 根 × 2 mix × 4 座 = **1,584 个阶段单元**；每单元 2 桌 ⇒ **3,168 张完整桌**；每桌 8 局 ⇒ **25,344 局** |
| 合同 | `review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json`（未改；H = 三家 V2，M = V2/V2_white_guard/V1） |
| 输出 | `.team-work/c35-level2/`（`manifest.json`、`stages/`、`result.json`、`mechanics.json`） |

配对与合同**沿用** `review/r18-four-arm-evaluation-2026-09-23/paired_study.py`：同一 `build_seat_stage_plans`（table_id/seed/permutation 不含臂标识）、同一驱动 `offline.evaluate.drive_match`、同一阶段积分与名次分口径。

## 二、机制计数器怎样取（口径来源，冻结）

**不改 `src/`、`policy/`、`hangma/`。** 计数器走两个**运行期只读钩子**（只包装、不改写生产对象）：

1. **引擎钩子**：把 `sitin_natural_panel.execute_natural_table` 换成薄包装（原函数原样调用），在包装内临时把
   组合根钩子 `bootstrap.build_evaluation_runtime` 的返回字典里 `engine` 换成**只读转发代理**
   （`start/frame/advance` 原样转发，其余键逐字不变）。代理只记录**已经到达决策边界**的公开事实：
   * `frame`：焦点座位在该窗口的 `PlayerObservation`（依法可见；不含他家暗牌与未来牌墙）；
   * `advance`：该帧的 `choices`（座位 + 动作类型）；
   * `advance` 之后世界的**公开单局记录** `RoundRecord`（庄家/胡家/流局/番/增量——即牌谱口径的赛后公开结果，不是他家暗牌）。
   代理不改变任何策略输入与任何裁决；`focal_stage_score` 仍由**未被改动的** `run_arm_stage` 计算。
2. **策略钩子**：`candidate_policy_factory` 返回的对象外包一层**只读记录器**，转发 `choose` 并原样抛出异常；
   用驱动传入的 `request.rules.legal_candidates` 复核首选动作（与驱动同一判据），统计异常/超时/非法。

**同源核对**：`PlayerObservation.rule_state.baotou` 由 `simulation/projection.py` 从
`hangma.progression` 的 `SeatProgression.baotou` 逐字投影；后者只由 `progression.baotou_after_draw` /
`baotou_after_discard` / `recompute_baotou` 更新，与 C31/C34 用的是同一个 `hand_analysis.any_tile_win` 核。
本批另外在每个**摸牌窗口**独立调用 `hand_analysis.any_tile_win(摸前暗牌, 副露数)` 做静态对拍
（`baotou_static_entry`），并**要求 `静态为真 ⇒ 观察标记为真`**（持续态可由吃碰杠继承，反向不要求）。

### 计数器定义（冻结）

| 计数器 | 口径 |
| --- | --- |
| `baotou_entry` | 焦点座位在本局**任一**决策窗口 `rule_state.baotou == True`（含吃碰杠继承的持续态） |
| `baotou_static_entry` | 本局任一**摸牌窗口**上 `any_tile_win(my_hand, 副露数)` 为真（同源静态核对，非主口径） |
| 本巡听牌 | 在**出牌权窗口**（`phase == "draw"`）上 `analyse_hand(full_hand, 副露数).shanten == 0`；`full_hand` = `my_hand` ∪ {`drawn_tile`}，恒为 (14 − 3×副露数) 张（普通摸牌窗口的摸前暗牌由 `my_hand` 单独承载，吃碰杠后待弃牌窗口 `drawn_tile` 为空）。「多余暗牌视为可弃」是 `hand_analysis` 的既有口径 |
| `first_tenpai_turn` | 本局第一个本巡听牌的窗口的**巡目** = 该窗口前焦点座位自己的弃牌数 + 1 |
| `first_tenpai_wait_kinds` / `first_tenpai_wait_tiles` | 在该窗口取所有满足 `analyse_hand(full_hand − d, 副露数).shanten == 0` 的弃牌 d，选 `useful_tiles` **种数最大**者，并列时取规范牌序（`TILE_ORDER`）最小者；种数 = 该等待手牌 `useful_tiles` 的去重牌种数，牌集 = 其牌码（按 `TILE_ORDER` 排序） |
| `wins` / `dealer_rounds` / `dealer_wins` | 公开单局记录：`winner_seat` == 焦点物理座位 的局数；`dealer_seat` == 焦点物理座位 的局数；两者同时成立 |
| `fan_sum` | 焦点座位胡牌局的 `fan` 之和 |
| `claims_made` | 焦点座位实际执行的**吃/碰/杠**次数（按 `SimulationChoice.action` 类型分类） |
| `claim_opportunities` | 焦点座位**响应窗口**中有合法吃/碰/杠候选的窗口数（对该窗口观察调 `HangmaRules.analyze(obs)` 读 `legal_candidates`） |
| `runner_illegal` | 焦点策略首选动作键不在该窗口 `request.rules.legal_candidates` 内的次数（与驱动复核同判据） |
| `runner_timeout` | 焦点策略 `choose` 被 `asyncio.wait_for` 取消（`CancelledError`）的次数 |
| `policy_exceptions` | 焦点策略 `choose` 抛出的非取消异常次数（计数后原样抛出） |
| `counter_anomalies` | 焦点出牌权窗口上 `len(my_hand) + (drawn_tile 非空) ≠ 14 − 3×副露数` 的次数（口径自检，须为 0） |

**聚合（冻结）**：单元 = （mix, 根, 焦点逻辑座位, 臂）；先把 2 桌 16 局的计数累加 / 率取均值；
「根 × mix」= **4 个焦点座位先在根内平均**（与 `paired_study` 一致）。
CI = **根级聚类**：对 198 个（mix × 根）单元的 Δ 取 均值 ± 1.96 ×（样本 SD / √198），与 `c29_verdict.py` 同一算式。
率的**分母** = 该单元完成局数（16）；`dealer_wins/dealer_rounds` 为按局池化比例。

## 三、判定（冻结，运行前落盘）

| 项 | 通过条件 |
| --- | --- |
| ① 积分复现 | `CELL-R6` 相对 `r18_v2` 的**分/桌**根聚类 95% CI **下界 > 0** |
| ② 机制同向 | `baotou_entry` 率**上升**且其根聚类 95% CI **下界 > 0**（预测方向：候选多吃碰 → 多进爆头） |
| ③ 辅助不退步 | `runner_illegal = runner_timeout = policy_exceptions = 0`（**两臂**全批，且 `counter_anomalies = 0`）；`dealer_wins/dealer_rounds` 点估计**不低于基准 − 1pp** |
| ④ 池一致 | H/M 两池在 **①②** 上**同号** |

**合成规则（冻结）**：四项全过 ⇒ 判定「**第二级通过**」；①过而②不过 ⇒ 「**增益机制不明**」（**不通过**）；
其余 ⇒ 「不通过」并写明缺哪一项。

## 四、边界与停止线

* 多重比较：本批只有 **1** 个候选臂（单假设），不设 Bonferroni 修正；H/M 分池是 C26 纪律的**报告项**，不另设显著门槛。
* panel 仍是**自博弈家族**（H/M），**不等于真实对手池**；本批不构成发布决定，官方新房只作真实池外部校验。
* 若 ① 不过：按 C30 §3 停止线处理（不继续加大同一常数，先回到分歧卡检查规则与对手分布）。
* 若 ① 过而 ② 不过：保留机制发现、**拒绝候选晋级**。

## 五、硬约束

不修改 `src/`、`policy/`、`hangma/`、`configs/auto-match.local.json`；不开官方房；不发网络请求；不 `git commit`；
只新增 `review/freematch-deep-dive-20260925/c35_*.py` 与 `.team-work/c35-level2/`。
