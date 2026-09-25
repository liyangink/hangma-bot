# 数据评估体系设计：底层表结构与统计维度

> 2026-09-25 实现口径补充：新测试房战役通过 `offline.postgame` 把官方 `events.json` 提升到 `datasets/derived/<pool>/official/<room>/official/dl-*/`。`datamart/build.py` 现读取该目录的四席 `user_id`，对晚到身份只回填原先未知的座位；已结束的 `week.prev.top` 前四单列为“上周榜”，不与实时“周榜”混同。数据源摘要纳入官方座位、策略映射与排行榜标签，使 `--check` 发现归因变化。首轮证据见[四席 R18 v2 验收](../../review/r18-four-arm-evaluation-2026-09-23/LIVE-R18-V2-SSE-ACCEPTANCE-2026-09-25.md)。

- 状态：**设计草案（待评审）**；本文只定义结构、口径与可行性，不含实现代码。
- 范围：把测试房间、自由赛、测试/正式赛事的赛局数据统一入库，支撑「按时间、按赛事类型、按关联策略」的多维统计，并为远程实时观战预留接入点。
- 依据：2026-09-14 对仓库现状的实测盘点（§2、§3 的每条结论都有实测或代码位置支撑）。

---

## 1. 结论先行

1. **最小统计粒度是「单局（Hand）」，但事实表必须按「单局 × 座位」建**：四人同桌各自可能跑不同策略，只有座位粒度才能做「按策略聚合」——测试房间四身份混策略正是核心场景。
2. **官方牌谱下载是权威数据源，已确认对测试房间与自由赛都可用**，且本仓库已有 49 房 / 3,760 单局的成型数据池可直接回填。本地审计只补三类独有信息：决策耗时与降级、动作提交结果、我方私有观察。
3. **不要重造轮子**：番数与番型重算（`offline/replay_check.py`）、统计口径与置信区间（`offline/evaluation_statistics.py`）、单局契约（`offline/replay.py`）、观战器（`spectator/`）都已存在。新体系是**在这些之上加一层存储与查询**。
4. **数据库选 PostgreSQL**；量级极小（全历史约 7,000–10^5 单局），选型依据是 SQL 表达力、部署成本与后续远程观战接入，而非吞吐。
5. **决策流水不入库**：单会话 `decisions.jsonl` 实测 143 MB（49 房池另有 161,680 决策行）；入库只存按单局聚合的决策指标，原始流水留在磁盘并记录指针。
6. **有两处必须先拍板才能动工**：评估体系落在哪条分支、远程观战的安全边界（§10）。

---

## 2. 数据可得性（决定表能建多细）

### 2.1 三个数据平面

| 平面 | 位置 | 覆盖 | 特征 |
| --- | --- | --- | --- |
| **本地审计** | `artifacts/sessions/<session>/audit/runs/<run_id>/` | 全部模式，我方视角 | 事件是「轮询恰好收到」的，**不是完整牌谱**；单会话 `decisions.jsonl` 143 MB。另注：`RAW_PROTOCOL_STATE` 是**唯一低优先级、队列压力下可被计数丢弃**的种类，原始报文不保证齐全；而 `DECISION_PLANNED.observation_snapshot` 是**裁剪视图**，完整观察只在 `DECISION_INPUT`。入库数据不得假设任一处齐全 |
| **官方牌谱下载** | `datasets/official-test-room/<t_*>/official/dl-*/`、`datasets/official-auto-match/<a_*>/official/dl-*/` | **测试房间 ✓、自由赛 ✓** | `events.json` 含完整事件块；10 局 × 8 单局 = 80 个 `round_ended`，**完整无缺** |
| **成型数据池** | `datasets/derived/auto-match-rooms-20260910/`（49 房/3,760 局）、`auto-match-rooms-20260908/`（48 房/3,520 局） | 自由赛两段战役 | 每房 `hands.jsonl.gz`（单局全信息）+ 官方牌谱 + manifest 血缘；**可直接回填** |

### 2.2 官方牌谱 `events.json` 结构

```jsonc
// 非官方说明性示例；字段名保持官方原样
{
  "room_id": "a_cd5c88f494b2", "batch": 5, "status": "finished",
  "seats": [{"name": "李洋", "user_id": "u_13495c3d79c8"}],        // 四家身份，可归因
  "blocks": [{"dealer": 0, "round_no": 1, "seq_start": 0, "seq_end": 129,
              "truncated": false, "start_hands": [[…]], "events": [ … ]}],
  "rounds": [{"dealer": 0, "is_draw": 0, "multiplier": 1, "round_no": 1,
              "scores": [-8,-8,-8,24], "winner": 3}]                 // 部分条目，非全量
}
```

单局结论事件（`round_ended`）：

```jsonc
{"seq": 1193, "type": "round_ended", "seat": 3,
 "data": {"detail": ["平胡", "爆头"], "draw": false, "fan": 2, "round_no": 6,
          "scores": [-16, -2, -2, 20]}}
```

### 2.3 各平面能力边界

| 需要的事实 | 官方牌谱 | 本地审计 | 结论 |
| --- | :---: | :---: | --- |
| 单局四家得分、胜负、流局 | ✓ | △（`round_ended` 仅约 27% 被轮询捕获） | 以官方为准 |
| 番型 `detail`、番数 `fan` | ✓ | △（同样约 27%） | 以官方为准 |
| 庄家、单局序号 | ✓（block 级） | ✓ | 双源交叉校验 |
| 四家**起手牌**（白板分档必需） | ✓（`start_hands`） | ✗（`my_hand` 仅我方） | **只有官方能给** |
| 四家身份 `user_id` | ✓（`seats`） | ✗ | **只有官方能给** |
| 决策耗时、降级原因、保底触发 | ✗ | ✓ | **只有审计能给** |
| 动作提交结果（含被拒） | ✗ | ✓ | **只有审计能给** |
| **白板获取数 god_count** | ✗ | ✗ | **不可得**：术语表明确「不能仅靠实时事件准确复算」，代码只解析不计算 |

### 2.4 大样本可行性试算（设计前先跑通）

在 `auto-match-rooms-20260910` 池的 **3,760 单局 / 15,040 座位行**上按 §5 表结构做只读试算，用户要求的指标族全部可产出：

| 试算项 | 实测结果 |
| --- | --- |
| 数据完整度 | `coverage` 100% `full_history`；`result_consistency` 3,700 passed / 60 not_checked（均为流局） |
| 流局率 | 60/3,760 = **1.6%** |
| 庄胜率 | 1,016/3,700 = **27.5%** |
| 番数分布 | `{1: 2904, 2: 688, 4: 100, 8: 8}` |
| 番型分布 | 平胡 3,543、爆头 670、七对 149、杠开 42、财飘 27、豪华七对×1 8、4个白板 4、连杠×2 1、双财飘 1 |
| 爆头胡率 | 670/**18.1%** 的胡牌局 |
| 连庄长度 | `{1:2115, 2:492, 3:154, 4:39, 5:6, 6:1, 7:1}`，最大 **7** |
| 座位一位率 | 0:25.9% / 1:23.3% / 2:25.3% / 3:25.5% |
| **白板分档** | 0白 9,816 行（65.3%）胡牌率 16.0% 局均 −2.30；1白 4,489（29.8%）37.4% / +3.14；2白 692（4.6%）59.8% / +10.71；3白 42（0.3%）85.7% / +23.50；**4白 1 行（0.0%）** |

**两条必须写进设计的结论**：

1. **白板分档不能照搬「无白/单白/双白/三白/四白」五档**：实测 4 白仅 1 个座位行、3 白仅 42 行，做五档胜率表会大面积无统计支持。**建议分档为 `0白 / 1白 / 2白+`，并把 3白、4白 降级为「观测记录」而非可比较指标**，同时表结构必须携带样本量以便标注低支持格。
2. **`rule_config` 在成型池中 3,760 行全为 `null`**（该数据集未落该字段）。统计时必须显式处理缺失，**不能填默认值**——否则会把「未知规则」当成「v10 规则」而污染跨规则对比。

### 2.5 已知数据缺口（必须在表中显式表达）

| 缺口 | 范围 | 影响 |
| --- | --- | --- |
| `missing_fields = {draw_identity, wall}` | 池中 **全部** 3,760 局 | **庄家第 14 张牌未拆出身份** → 庄家座位的起手白板数可能是「13 张计数」，存在 off-by-one；牌墙顺序未知 → 无法做摸牌概率类推算 |
| `rule_config = null` | 池中全部 3,760 局 | **这是当前最大的可修复缺口**：实测它就是 `check_hand` 全部 `not_checked` 的唯一原因（`not_checked.rule_config_missing`）。`RUN_MANIFEST` 已记录 `ruleset_version/base_score/you_cai_bi_kao`，**从运行清单回填后即得 `passed 200 / not_checked 40`、零 conflict**。应列为 S1 的首要子任务 |
| 2 房无官方牌谱 | 池中 2 房 | 其 hands 来自审计事件重建，`coverage` 应标为部分 |
| **09-06 池口径错误、已废弃** | `datasets/derived/auto-match-2026-09-06/`（36 行） | 其 `validation.json` 自述口径错误，且终局对账不干净（33 conflict / 124 not_checked / 3 passed）。**禁止入池**，只用 repaired 版本 |
| `official_ranks` 恒为 null | `MatchResult` 契约 | **不存在现成「平均名次」口径**；用户要的位次指标须自建，且必须命名为「桌内本地名次」，不是官方全场排名 |

---

## 3. 必须复用、不要重造的现有资产

| 资产 | 位置 | 复用原因 |
| --- | --- | --- |
| **牌谱重算与一致性校验** | `offline/replay_check.py` 的 `check_hand(hand, rules)` | 已实现「事件流 → 重建四家手牌/副露/牌河/回合 + chain/baotou → 复核动作合法性 → 在胡牌处重算 fan/detail/scores 并与官方逐项比对」（冲突码 `fan_mismatch`/`detail_mismatch`/`score_mismatch`）。**离线重算番型不需要新造轮子** |
| **统计口径与置信区间（模拟/配对实验侧）** | `offline/evaluation_statistics.py` | 已定义 `table_score_delta`、`table_first_rate`（含 `inclusive/strict`）、`clustered_bootstrap_ci()`（按 scenario 聚类、先组内均值再重采样、10000 次、seed=0）、`pair_matches()`、以及 `summarize_results()` 的结论纪律。**注意其适用范围是模拟与配对实验**，见 §3.5 |
| **真实牌谱侧分层统计** | `review/heuristic-resource-gap-2026-09-11/analyze.py` | 已成型的「(庄/闲)×(开局白板 0/1/2+) 分层标准化 + 房聚类 bootstrap + 重采样内重新标准化」，正是本体系要的口径，应升级为生产版 |
| **净分口径与分解** | `review/heuristic-gap-audit-2026-09-10/recompute.py` | `mean_net_per_8_hands`、`hu_rate`、`mean_receipt_per_hu`、`mean_payment_per_paying_hand`、庄/闲拆分、以及「次数/每胡/支付」三段账面分解 |
| **机制度量与门禁** | `review/heuristic-balanced-2026-09-10/{gate_candidate.py,measure_mechanism_effect.py,measure_dealer_edge.py}` | 已有连庄代理 `stint_*`、`baotou_share`、`piao_share`、`dealer_advantage`、`big_hand_share_4/8/16`、功效与 ICC/MDE 度量 |
| **逐单局特征行** | `datasets/derived/auto-match-v10-2026-09-10/features-v10.jsonl`（3,760 行 / 19 键） | 已按单局产出 `seat_stats[0..3]{draws,whites_drawn,init_whites,init_tiles,chi,peng,gang_ming,gang_an,gang_bu,passes,timeouts}`，可直接作为回填输入 |
| **对手标注** | `datasets/leaderboard/game-annotations.jsonl`（440 行） | 已按 `game_id` 给出 `seats[{seat,user_id,name,tags,is_me}]` 与 `strong_opponent_count`，正是 `dim_opponent_tag` 的数据源 |
| **结果行契约** | `offline/evaluation_results.py` 的 `MatchResult` | 已含 `scenario_id/pair_id/policy_ids_by_seat/seat_permutation/scores_before/scores_after/runtime_counts/versions/source_refs`；§5 事实表与之对齐 |
| **单局契约** | `offline/replay.py` | 已产出 `hands.jsonl`。ETL 直接消费，不重新解析 |
| **下载与封存** | `scripts/audit_tool.py`（`collect-test-room`/`postgame`/`convert`/`import-history`/`catalog`） | 官方牌谱下载与证据包封存已有成熟命令 |
| **分层统计先例** | `review/heuristic-resource-gap-2026-09-11/analyze.py` | 已成型的「(庄/闲)×(开局白板 0/1/2+) 分层 + 房间聚类 bootstrap」实现，正是本体系要的口径，可直接升级为生产版 |
| **观战器** | `spectator/server.py`、`spectator/model.py`、`spectator/static/` | 已有观战页面与快照模型；**但强制回环绑定、不接受远程监听、无认证**。远程化是安全边界变更（§10） |
| **自由赛账本** | `runs/auto-match-watchdog/auto-match-watchdog-state.json`、`scripts/auto_match_watchdog.py` | 已有 47 房/470 场/累计 +1612 的账本（含每房 `room_subtotal`、每场 `final_score`），是 `fact_rank` 的回填来源 |
| **依赖现状** | `pyproject.toml` | 全仓**无数据库、无 ORM、无 pandas/numpy**（运行时依赖仅 `httpx`）。新依赖必须进 optional-dependencies，不污染线上极简依赖面 |

### 3.1 真实牌谱侧：口径现状与两个必须先处理的问题

§3 的表格是「可复用清单」；本小节单独说明真实牌谱侧的**口径现状**——它与模拟侧不同，**没有公共模块**，口径分散在 `review/` 各目录与 `datasets/derived/auto-match-v10-2026-09-10/*.py`。已成型可复用的口径：

| 口径 | 出处 | 定义 |
| --- | --- | --- |
| `mean_net_per_8_hands` | `review/heuristic-gap-audit-2026-09-10/recompute.py` | `(income − payment) / n` |
| `hu_rate` | 同上 | `hu / (n × 8)` |
| `mean_receipt_per_hu` / `mean_payment_per_paying_hand` | 同上 | 每胡入账 / 每放铳手支付 |
| 净分三段账面分解 | 同上 | `hu_frequency + receipt_per_hu + payment`（**账面分解，非因果**） |
| 房聚类 bootstrap | 同上 | 整房有放回重采样；`valid_uncertainty = 房数 ≥ 10` |
| 分层标准化 | `review/heuristic-resource-gap-2026-09-11/analyze.py` | (庄/闲) × (开局白板 0/1/2+)，房聚类 + 重采样内重新标准化 |
| `dealer_advantage` | `measure_dealer_edge.py` | 庄胡率 − 闲胡率 |
| `stint_mean` / `stint_share_ge2` | `measure_mechanism_effect.py` | **连庄的代理指标**（无原生连庄率定义） |
| `baotou_share` / `piao_share` | `capability_gap_scorecard.py` | 分母 = 胜局 |
| `big_hand_share_4/8/16` | `measure_mechanism_effect.py` | 番数门槛占比 |
| ICC / MDE / `se_clustered` | `measure_experiment_power.py` | 房间聚类功效分析（实测 ICC ≈ 0.53） |

**问题一：置信区间有 3 套不同语义并存**——`evaluation_statistics.py`（scenario 聚类、先组内均值）、`gate_candidate.py`（root 聚类、flatten）、`recompute.py`（房聚类、手写插值分位）；且 bootstrap 在全仓**至少 10 处各自独立实现**、读 `hands.jsonl.gz` **至少 8 处各自实现**。**本体系的一项核心工作就是把真实牌谱侧的口径收敛到唯一实现**，否则同一问题会得到不同区间。

**问题二：统计单位必须由粗到细逐级显式声明**（否则口径会悄悄漂移）：

| 单位 | 定义 | 出处 |
| --- | --- | --- |
| 单局 Hand | 一次 8 巡制起胡 | `auto-match-v10-2026-09-10/README.md` |
| 场 Game | 完整桌赛，8 单局 | 同上 |
| 房 Room | 10 场 = 80 单局 | `heuristic-balanced-2026-09-10/README.md`、`configs/auto-match.local.json` 的 `declared_max_games=10`/`declared_rounds=8` |
| 根组 scenario_id | 同牌山种子及其换座变体，**唯一合法聚类单位** | `evaluation_statistics.py` |
| 赛事/阶段 | AGENTS.md §7 要求覆盖，**当前无实现** | — |

> **`split_group_id`（真实牌谱行）与 `scenario_id`（模拟结果行）应作为 `fact_*` 的统一划分与聚类键**，不要另造。

---

## 4. 分层模型与术语红线

### 4.1 术语红线（照搬会直接踩文档冲突）

[统一术语表](../../UBIQUITOUS_LANGUAGE.md) 把「轮」「一桌」「局」**显式列为禁用别名**。因此：

- 层级正解：**赛事 Tournament → 赛事阶段 Stage → 桌赛 Table Match → 单局 Hand**。
- 单局唯一键用 `hand_id`；单局维度用 `round_no`。
- **不得用 `game_id` 当「一桌」**：术语表明确「官方场次与桌赛/八局的精确映射仍待官方确认」。本设计把 `game_id` 只称**官方场次（Official Game）**，其与桌赛的等价关系标注为待确认。
- 结算必须拆三词、**不得相加**：桌内积分（Table Score）/ 总得分（`total_score`）/ 名次分（`place_points`）。
- **以下术语在术语表中不存在**，建表前必须补词条并同步「已标记的歧义」：**番型**、**番数**、**连庄**、**连庄次数**、**听牌**、**白板档位**（单白/双白/三白/四白/无白）、**降级**。
- **不得混用**：`whites_held`（手留白板，可从牌谱算出）≠ `god_count`（白板获取数，赛事第三排序键，**官方明示不可实时复算**）。
- **「胜率」不得单独使用**（歧义条）：报告必须写明具体指标名与统计单位，例如「单局胡牌率」「桌内第一率」，不能只写「白板胜率」。

### 4.2 用户口语 → 本设计用词

| 用户口语 | 本设计用词 | 定位键 |
| --- | --- | --- |
| 一轮（最小单位） | **单局（Hand）** | `hand_id`；维度 `round_no` |
| 一桌（M 中的 1 个会话） | **官方场次（Official Game）** | `game_id`（与桌赛的映射待确认） |
| 一局（测试房整批 / 自由赛一次匹配 / 正式赛一个阶段） | **阶段尝试（Stage Attempt）** | `tournament_id` + `stage_attempt_id` |
| 全赛局 / 全历史 | **赛事（Tournament）** 及以上 | `tournament_id`、全局 |

### 4.3 聚合层级

```text
[全历史] ── 跨赛事、跨时间、跨赛事类型
   ↑
[赛事 Tournament] ── t_* / a_* 的完整表现
   ↑
[阶段尝试 StageAttempt] ── 用户所说「一局」
   ↑
[官方场次 Game] ── 用户所说「一桌」，含 Rounds 个单局
   ↑
[单局 Hand] ── 最小单位
   ↑
[动作 Action] ★不单独建事实表，仅按单局聚合后入库
```

统计单位承 AGENTS.md 第 7 节：比较类指标的分母是**完整桌赛/阶段尝试/赛事 seed**，不是单个决策。

---

## 5. 表结构设计

### 5.1 维表

| 表 | 主键 | 关键字段 | 说明 |
| --- | --- | --- | --- |
| `dim_strategy` | `strategy_key` | `strategy_name`、`strategy_kind`、`model_id`、`model_weights_sha256` | 「按关联策略」的落点；`strategy_kind` ∈ heuristic/model/shadow/fallback |
| `dim_ruleset` | `ruleset_key` | `ruleset_version`、`base_score`、`you_cai_bi_kao`、`rules_hash`、`guide_version` | 规则口径；`guide_version` 支撑平台升级前后对比。**允许「未知」取值**（对应 §2.5 全 null 情况） |
| `dim_participant` | `participant_key` | `user_id`、`display_name`、`is_self` | 四家身份 |
| `dim_contestant` | `contestant_key` | `participant_key`、`strategy_key` | **身份 × 策略**组合，一次运行内固定 |
| `dim_tournament` | `tournament_key` | `tournament_id`、`mode`、`source_namespace` | 「按赛事类型」的落点 |
| `dim_opponent_tag` | `tag_key` | `participant_key`、`tag`、`snapshot_at` | 对手强度标签 |

### 5.2 `fact_hand` —— 单局粒度（一行一单局）

| 字段 | 类型 | 来源 / 含义 |
| --- | --- | --- |
| `hand_key` | PK | 代理键 |
| `hand_id` | text | 复用 `offline/replay` 稳定 ID，保证可重放 |
| `game_key` / `round_no` | FK / int | 官方场次与单局序号 |
| `dealer_seat` | smallint | 源：`initial.dealer_seat` 或 block 级 `dealer` |
| `winner_seat` | smallint | 源：`winner_seat`；流局为 `-1` |
| `is_draw` | bool | 源：`is_draw` |
| `fan` | smallint | 源：**`events[round_ended].data.fan`**（不在顶层） |
| `fan_multiplier` | smallint | 源：`rounds[].multiplier`，可为空 |
| `fan_detail` | jsonb | 源：**`events[round_ended].data.detail`**，如 `["平胡","爆头"]` |
| `fan_types` | text[] | 由 `fan_detail` 展平，建 GIN 索引 |
| `scores_before` / `scores_after` / `score_delta` | smallint[4] | 座位序向量（顺序必须写入注释） |
| `seat_start_god` | smallint[4] | 由 `initial.hands` 数 `白` 得到；**庄家位受 `draw_identity` 缺口影响，须标记** |
| `wall_remaining` / `event_count` / `duration_ms` | int | 节奏指标 |
| `result_source` | text | 如 `round_ended` |
| `consistency_status` | text | 源：`result_consistency.status`（passed/not_checked/…） |
| `coverage` | text | `full_history` / 部分 |
| `missing_fields` | text[] | 复用 replay 契约的缺失声明 |

**结算契约（`fact_hand.scores_*` 的语义依据）**：

- 分数向量**固定按物理座位 0—3**（`ScoreVector`），不是按名次或身份顺序；列注释必须写明，否则聚合会静默错位。
- 庄家胡时庄家倍率**恒 ×8**（「直上三连庄，无递增」）；闲家胡时庄家按 ×8 支付、另两闲家各按 ×1 支付。
- 流局 → `fan = 0` → **全零向量**。
- **不变量：四家增量之和恒为 0**。ETL 必须把它作为断言校验（`sum(score_delta) == 0`），这是发现解析错位最廉价的一道门。

### 5.3 `fact_hand_seat` —— 单局 × 座位（分析主力，一行 4 条）

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `hand_key` + `seat` | PK | |
| `contestant_key` | FK | 该座位的身份 × 策略 |
| `score_delta` | smallint | 本局该座位得失分 |
| `is_winner` / `is_dealer` | bool | |
| `god_count` | smallint | 起手白板数（0–4），白板分档的落点 |
| `is_local_first` | bool | 桌内本地最高分（**非官方名次**） |
| `fan` / `fan_detail` | smallint / jsonb | 该座位胡牌时的番数番型 |
| `consecutive_dealer_len` | smallint | 由跨单局 `dealer_seat` 序列推导（引擎无此计数器） |
| **决策指标（仅本方座位非空）** | | 源：本地审计。**注意：不存在 `decide_ms` 单一总耗时字段**，只能 `rule_elapsed_ms + policy_elapsed_ms`（+ 复核 `elapsed_ms`）近似 |
| `n_decisions` / `latency_p50_ms` / `latency_p95_ms` | int | 源：**原始 `decisions.jsonl`**；`offline/replay` 的决策行**已丢弃** `policy_elapsed_ms`/`rule_elapsed_ms`/`budget_policy`/`window_deadline`，走 replay 行取不到耗时 |
| `degrade_reasons` | jsonb | 源：`returned_plan.degraded_reasons` |
| `n_fallback` | int | 源：候选 `is_emergency` |
| `end_reason_counts` | jsonb | 词表：`submitted/exhausted/deadline/cancelled/error/unknown` |
| `n_submit_rejected` | int | 源：`attempts[].execution_status` |

> 对手座位的决策指标**必然为空**，字段级显式 NULL 而非 0，否则污染均值。

### 5.4 `fact_rank` —— 阶段尝试 × 参与身份

| 字段 | 含义 |
| --- | --- |
| `stage_attempt_key` + `contestant_key` | PK |
| `final_score` | 阶段尝试终分 |
| `rank_in_official_game` | 桌内名次（1—4，本地口径） |
| `place_points` | 名次分 `+3/+1/-1/-3`；无晋级语义时为 NULL |
| `god_count_total` | **不可得**（§2.3），列保留但允许全 NULL |
| `qualified` | 是否达晋级目标；NULL = 该模式无晋级语义 |

### 5.5 血缘与幂等

`source_root` / `source_refs`（含 sha256）、`run_id`、`git_commit` / `git_dirty`、`policy_weights`、`etl_version`、`ingested_at`；对 `(hand_id, etl_version)` 建唯一约束实现幂等重导。

---

## 6. 统计维度清单

标注：**✓ 现有数据足够**、**△ 需扩展 ETL**、**✗ 当前不可得**。

### 6.1 积分维度 → ✓

单局得分、累计净分、平均/最高/最低/p95/p5、标准差与波动率、桌赛终分向量（四家）、名次分合计。派生指标一律走 `evaluation_statistics.py`。

### 6.2 位次维度 → ✓ / △

| 指标 | 可得性 |
| --- | :---: |
| 一位率 / 二位率 / 三位率 / 四位率 | ✓（本地分数口径，须声明 `tie_method`） |
| 平均位次、位次 p95、进前二率、避免末位率 | ✓ |
| 位次标准差（稳定性） | ✓ |
| 晋级率 | △（依赖阶段格式解析） |

> 术语警示：这些是**桌内本地名次**，不是官方全场排名（`official_ranks` 恒 null）。

### 6.3 白板（财神）维度 → ✓ 但须分档收敛

| 指标 | 可得性 |
| --- | :---: |
| 各档胜率、平均积分、最高积分、胡牌率 | ✓（**按 0白/1白/2白+ 三档**，见 §2.4） |
| 各档与位次交叉、与策略交互 | ✓ |
| 3白、4白 明细 | △ 仅作观测记录（样本 42 / 1 行，**不可作为比较指标**） |
| 抓打圈发生与结果 | △（`god.catch_play` 在快照中，按单局聚合） |
| **白板获取数 god_count** | **✗ 不可得**（官方明示不能仅靠实时事件复算，代码只解析不计算） |

代码用词提示：白板在代码中是 **`wealth`**（`WEALTH_CODE="白"`、`is_wealth()`、`whites_held`），**不存在 white/wildcard/joker 标识符**；「无白/单白/双白/三白/四白」**没有任何现成分档实现**，需新建。

### 6.4 庄家维度 → ✓ / △

| 指标 | 可得性 |
| --- | :---: |
| 坐庄率、庄胜率（实测 27.5%）、庄积分 最大/最小/平均/p95 | ✓ |
| 连庄率、最大连庄（实测最大 7） | △ 由 `dealer_seat` 序列自推；**引擎无连庄计数器** |
| 庄家 × 白板档位交叉 | ✓ |

庄家倍率恒 ×8（直上三连庄，无递增）；续庄规则：流局保庄、赢家坐庄（`progression.next_dealer`）。

> ⚠️ **P0 已知缺陷（直接影响本维度可信度）**：`review/heuristic-balanced-2026-09-10/README.md` 记录「真实 1088/1088 都是『赢家坐庄』，而代码只命中 24.6%」。**在修复前，任何庄家轮转/连庄类统计都必须标注该缺陷**，并优先用官方牌谱的 `dealer` 字段而非本地推断值。
> 另注：「连庄率」在仓库中**没有统一定义**，近似量是 `stint_mean` / `stint_share_ge2`；建指标前需先补术语定义。
> **未被利用的官方来源**：平台门户榜单（guide v27）已有 `lianzhuang`（庄胡把数）、`pinghu`、`baotou`、`big` 字段，但代码**完全未解析**（`scripts/fetch_leaderboard.py` 零命中）。这是补齐连庄/爆头口径的现成权威来源，建议纳入 S3。

### 6.5 番数与番型维度 → ✓ / ✗

| 指标 | 可得性 |
| --- | :---: |
| 番数分布、最大/最小/平均/p95 | ✓ |
| 倍数 `multiplier` 分布 | ✓ |
| **各类番型次数与占比** | ✓（源：官方 `detail`；实测穷举出 平胡/爆头/七对/豪华七对×N/杠开/连杠×N/财飘/双财飘/4个白板） |
| 番型组合频次、番型×得分相关性、番型×策略 | ✓ |
| **离线重算校验（正确性门禁）** | ✓ **已实测通过**：`replay_check.check_hand` 在注入 `rule_config` 后跑真实牌谱得 `passed 200 / not_checked 40`，**无任何 `conflict.*`** |
| **枚举一副牌的全部番型组合** | **✗ 无接口**：`win_split` 只产出**唯一一个**分解（七对优先于平胡），不是所有分解的集合 |
| 听牌「等哪些牌」 | ✓ `HandSummary.useful_tiles`、`CandidateFacts.{standard,seven_pairs}_useful_tiles` |
| 听牌**剩余枚数** | ✓ `UsefulTileFact.remaining_estimate`（0–4） |
| **胡牌概率 / 成胡概率** | **✗ 不存在**：源码与文档明写「有效牌数是未见张数，**不是成胡概率**」。唯一概率类数字是离线校准的生存率表，非引擎按手牌计算 |

> **设计红线**：用户要求的「胡牌概率」目前无法给出。“剩余枚数”只能作为**牌效事实**呈现，**不得命名为概率**，否则违反术语表与项目纪律。
> **离线重算的实现约束**：`WinDescription.observation` 必须是**胡家视角**的观察，且 `chain_count > 0` 时 `observation.chain_piao` 不可为空，否则引擎直接 `raise ValueError`——重算必须提供链内飘白的精确证据，不能猜。

### 6.6 胡牌与特殊状态 → ✓

胡牌率、流局率（实测 1.6%）、**爆头概率与爆头番数**（实测占胡牌局 18.1%）、杠开率、杠爆率、七对率、豪华七对率、有财必拷响下的合规分布。爆头在引擎中已完整实现（含 `you_cai_bi_kao_block` 资格过滤），不是缺失项。

> **⚠️ 不要统计「自摸率」**：本规则**只能自摸、不允许点炮、禁止抢杠胡**（胡候选只在本人摸牌窗口产生）。因此「自摸」不是可区分维度，自摸率恒为 100% 的胡牌局——列进报表只会是噪声。
> **同样不存在「点炮率 / 抢杠」维度**。若要刻画"放铳"，只能用**支付（payment）**口径，即本局为负分的座位，而非点炮方。

### 6.7 策略与执行维度 → ✓（**已落地**：见 `datamart/`）

> **实现状态（2026-09-15）**：本节指标已由 `datamart/` 落地，来源是**已入库**的
> `datasets/derived/*/validations/<房>.audit.json`（postgame 的审计聚合），
> 因此可在任意机器重建，不依赖本地 `artifacts/`。
> 已覆盖：提交尝试/官方拒绝/结果不确定、**HTTP 429 次数与占比**、**动作窗口超时次数与占比**、
> 决策时延 p50/p95/p99/max、规则降级数与降级率、审计记录种类直方图、审计完整性与 findings。
> **未覆盖**：保底动作触发次数（`is_emergency`）——它只在本地 `decisions.jsonl` 里，
> 不入库故无法跨机重建；如需精确保底率须在本机另跑一次解析。


决策次数、决策耗时 p50/p95/p99、降级原因分布、保底触发率、动作窗口超时、提交被拒率、吃碰杠过牌次数与率、429/限速异常。

**动作口径的三条实现约束**：

1. **杠种（暗杠/明杠/补杠）只能从事件流取**——官方动作请求体**不含杠种**（只有 `{"action":"gang","tile":…}`），须走 `public_history` 的 `detail_kind`（`an`/`ming`/`bu`）。这决定 `fact_hand_seat` 的 `gang_ming`/`gang_an` 计数必须解析事件而非提交记录。
2. **降级原因有稳定词表**可依赖：规则侧 `RuleCompleteness{complete,degraded}` + `RuleIssue.area`（如 `hand_analysis`、`action_families.<族>`、`special_rules.youcai`、`catch_play.owner`），候选级 `CandidateValueFacts.coverage{complete,partial,unavailable}`，策略级 `degraded_reasons`。不要按自由文本聚合。
3. **保底动作有固定证据串**：`emergency:response-pass` / `emergency:catch-play-drawn` / `emergency:rightmost-nonwealth-discard` / `emergency:only-wealth-discard`，可直接作为"降级到哪条保底路径"的枚举维度。

### 6.8 对手与座位 → ✓ / △

对手 user_id 池与同桌平均排名✓；座位（0—3）效应✓（实测 25.9/23.3/25.3/25.5）；对手强度分层表现 △（依赖榜单标签覆盖）。

> **换座样本已知缺陷**：四换座实测取值 `[[0,1,2,3],[1,2,3,0],[2,3,0,1],[3,0,1,2]]` 是同一 4-循环的幂，存在固定循环重复；移除 `(2,3,0,1)` 后开发积分差仍为 +7.622 [1.885, 13.401]。**按座位的统计必须标注该缺陷**；完整审计在 `codex/heuristic-evidence-repair` 分支，不在 main。

### 6.9 时间与版本切片 → ✓

按日/周趋势、按赛事类型、按策略与模型身份、按指南版本、按规则配置、按 `git_commit` 回归定位。

### 6.10 建议补充的维度（原清单未覆盖）

1. **样本量与功效标记**：每个聚合格必须带 n；n 低于阈值时前端显式标注「不支持结论」（白板 3白/4白 就是实例）。
2. **置信区间与显著性**：全部对比走 `clustered_bootstrap_ci()`，并按场景聚类。
3. **数据完整性覆盖率**：每层统计要能回答「覆盖了全历史的百分之多少」。
4. **作废阶段尝试标记**：平台中断产生的作废数据默认排除，只用于可靠性诊断。
5. **流局率、单局时长、事件数**作为独立健康指标。
6. **规则缺失显式化**：`rule_config` 缺失必须显示为「未知」，不得按默认值参与分组。

---

## 7. 技术栈选型

### 7.1 数据量

| 层级 | 预估行数 | 依据 |
| --- | ---: | --- |
| `fact_hand` | ~10^5 | 已有池 3,760（09-10）+ 3,520（09-08）= 7,280；后续累积 |
| `fact_hand_seat` | ~4×10^5 | 单局 × 4 座位（15,040 已实测） |
| `fact_rank` | ~10^3 | 阶段尝试 × 身份 |
| 决策流水 | 161,680 行/49 房，单会话 143 MB | **不进库** |

**这是小数据量；选型决定因素是 SQL 表达力、部署成本与实时接入，不是吞吐。** 实测量级见 §7.3：全历史统计库单文件仅 **6.61 MB**。

### 7.2 选型

| 层 | 选型 | 理由 |
| --- | --- | --- |
| 主库 | **PostgreSQL 16**（仅在需要多写方或常驻服务时启用；纯查看场景见 §7.3 的单文件方案） | 窗口函数、`percentile_cont`、`FILTER`、`GROUPING SETS`、`jsonb`+GIN 一次性覆盖全部统计需求；2C4G 足够 |
| 实时扩展 | 可选 TimescaleDB | 后续观战事件流按时间分区时再加，不提前引入 |
| 服务端 | **FastAPI + asyncpg + Pydantic** | 与现有 Python 同栈，无需跨语言；自带 OpenAPI |
| ETL | Python 标准库 + `psycopg`，复用 `offline/replay`、`replay_check` | 已有成熟契约与一致性校验 |
| 离线重算 | 可选 DuckDB | 听牌重建等重计算本地跑，不压主库 |
| 观战 | 扩展现有 `spectator/`（远程化需安全评审）+ SSE/WebSocket | 已有页面与快照模型 |
| 依赖纪律 | 新增依赖只进 optional-dependencies | 线上运行时依赖保持仅 `httpx` |

> **部署形态是一次形态变更**：现状是「命令行进程 + 文件系统审计目录」，全仓**无 Dockerfile / docker-compose / Makefile，也无任何服务端后端**（唯一服务端组件是回环绑定的 `spectator/server.py`）。引入 PostgreSQL + FastAPI 意味着新增一套需要运维的长运行服务，因此 §8 的 S1 必须同时产出**部署与备份方案**（含 `pg_dump` 定期备份），而不能只交付建表脚本。

**不选 ClickHouse**：10^5 行量级上运维成本远超收益。**不把 DuckDB 当服务端**：与并发观战不匹配。

### 7.3 部署形态与跨机器访问（实测结论：**不需要云数据库**）

**先把两件事分开**：官方平台是**内网地址**（`https://10.240.169.190:18080`，需为它设代理例外）。因此——

> **数据库放在哪里，都不影响「跑 Bot 的机器必须能到达官方内网」这个事实。** 云数据库只决定「你从哪里查看结果」，解决不了 Bot 的连通性。

**再看来数据量**（2026-09-14 实测，两个自由赛池全量 97 个分片）：

| 项 | 实测值 |
| --- | ---: |
| `fact_hand` 行数 | 7,280 |
| `fact_hand_seat` 行数 | 29,120 |
| **单文件 SQLite 体积** | **6.61 MB** |
| 外推到 10 万单局 | ≈ 91 MB |
| `sum(scores_after) == 0` 不变量校验 | 0 行违反 |

**全历史统计库不到 7 MB —— 比一张照片还小。** 这直接说明：跨机器查看需求**不需要**常驻数据库服务。

#### 三种需求对应三种答案

| 需求 | 数据量 | 方案 | 服务器 |
| --- | --- | --- | --- |
| 跨机器**查看统计** | ~7 MB 单文件 | 单文件产物 + 任意同步（rsync / 对象存储 / Syncthing） | **不需要** |
| 多台机器**同时写** | 小 | 中心库（Postgres） | 需要 |
| **实时观战** | 流式 | 常驻服务端 + SSE/WebSocket | 需要 |

#### 推荐路径

**起步（零成本、立刻可用）**：ETL 产出**单文件分析产物**，同步到任意机器。
- 优先 **DuckDB 单文件**（列存，可直接查 Parquet，分析性能远超行存）；
- 或 **SQLite**（兼容性最好，任何客户端可打开）。
- 查询侧**不需要任何服务**——DuckDB 是单个二进制，`duckdb hangma.db "SELECT …"` 即可。

**要「随时随地、手机也能看」**：用 **Tailscale / WireGuard 组网**，把 Postgres 只监听内网与组网地址。
- **不暴露公网端口**，比云主机更安全；
- 不需要公网 IP、端口转发或内网穿透；
- 成本 0（免费档对个人用量足够）。

**只有这些情况才需要云主机**：多写方并发入库；要做实时观战；有他人查看且不便都装组网客户端。

#### 敏感性与上云红线

官方牌谱 `seats` 含**真实对手的 `user_id` 与昵称**，且仓库运维约定已写明「**房间 id 即凭证，勿公网分享**」。因此：

- **禁止**把原始牌谱/审计目录整体上传到公网对象存储或第三方云；
- 若确需上云，**只放聚合后的统计结果**，或先对 `user_id`、`room_id` 做哈希脱敏；
- 这与 §10.2 的远程观战安全评审是同一类问题，应合并处理。

### 7.4 目标架构

```text
   测试房间            自由赛              测试/正式赛事
      │                  │                     │
      ▼                  ▼                     ▼
 本地审计目录      官方牌谱下载          本地审计目录
      │                  │                     │
      └────────┬─────────┴─────────────────────┘
               ▼
        ETL（幂等，复用 offline/replay + replay_check）
               │  单局/座位/排名事实 + 维表（决策指标按单局聚合）
               ▼
        PostgreSQL 16
          │              │
          │              └──> FastAPI 分析 API（时间×赛事类型×策略）
          └──> 实时观战：官方事件流 ──> SSE/WebSocket ──> 浏览器
```

---

## 8. 实施路径

| 步骤 | 内容 | 交付物 |
| --- | --- | --- |
| **S0** | **口径收敛**：把真实牌谱侧的 bootstrap / 房间聚类 / 净分口径收敛为唯一公共实现，明确 3 套区间语义各自适用场景 | 唯一统计模块 + 对拍用例 |
| **S1** | 补术语词条（番型/连庄/听牌/白板档位/平均名次）；建库与 DDL；ETL 打通自由赛 + 测试房，含 `(hand_id, etl_version)` 幂等；**产出部署与备份方案** | 空库 + 可重复导入的 ETL + 运维说明 |
| **S2** | 回填现有 7,280 单局池与历史测试房；**排除 09-06 废弃池**；产出覆盖率与低支持格报告 | 带完整性声明的数据库 |
| **S3** | 统计 API + 首批维度（积分/位次/白板三档/庄家/番型/爆头），全部带 CI 与样本量 | 可按三维筛选的分析接口 |
| **S4** | 远程观战接入 + 听牌牌效深度指标（**措辞不得称概率**） | 观战页与牌效指标 |

---

## 9. 风险与待确认

1. **正式赛事牌谱可得性未验证**：测试房间与自由赛已实测可下载，正式赛事是否有等价接口**未确认**，需在第一次正式赛后立即验证。
2. **官方 `round_ended` 字段与审计版本不一致**：官方版缺 `dealer`/`round_no`，须用 block 元数据补齐；`rounds` 数组是部分条目。ETL 必须带交叉核对用例，否则静默错位。
3. **`rule_config` 全 null**：跨规则对比在补字段前不可信。
4. **`draw_identity` 缺口**：庄家起手白板计数存在 off-by-one 风险，白板分档需标注该不确定性。
5. **白板高档次样本不足**：3白 42 行、4白 1 行；分档必须收敛为 0/1/2+。
6. **「胡牌概率」不可得**：只能用有效牌数/剩余枚数表达，命名受术语纪律约束。
7. **换座位样本已知缺陷**（§6.8）：按座位统计必须标注。
8. **两平面 hand_id 对齐**：本地审计与官方牌谱必须能对上，否则决策指标无法贴到单局；S1 须先做对齐验证。
9. **评估体系落在哪条分支未定**：`main` 与 `codex/model-outcomes-v1` 自 `f596cb02` 分叉——main 领先 4 个提交（**三个序列模型接入，即本次要评估的对象**），该分支领先 144 个提交且多约 64 个 review 目录与 `numpy` 训练依赖。见 §10。

---

## 10. 待评审决策点

1. **评估体系落在 `main` 还是 `codex/model-outcomes-v1`**：在 main 上可直接复用 seq 模型接线（评估对象就在这条线），但需先把分支的评估资产并过来；反之要重新接线模型。**动工前必须先拍板。**
2. **远程观战的安全边界**：现有观战器强制回环绑定是刻意设计。是否对外开放、用什么鉴权、是否严格只读不落 Token，需要一次明确的安全评审，**不能顺手改绑定地址**。
3. `fact_hand_seat` 是否为对手座位保留决策指标占位列（当前设计为 NULL）。
4. `fan_types` 是否拆出独立 `fact_hand_fan`（一行一番型）以支持更灵活的番型组合分析。
5. 实时观战数据源：复用**官方事件流**（权威但需重新接协议）还是**本地 `raw_protocol` 留痕**（现成但仅我方视角）。
6. 数据库部署形态：单实例 PostgreSQL，还是 PG + 只读物化视图分离在线分析与回填压力。
7. **`split_group_id` / `scenario_id` 是否直接复用为 `fact_*` 的划分与聚类键**（建议是），以及聚类单位在真实牌谱侧统一取「房」还是「根组」。
8. **「平均名次」口径需先定义再落地**：仓库零实现，且 `official_ranks` 恒为 null。必须先明确它是「桌内本地名次」还是别的，**不得用 `first_rate` 冒充**。
9. **换座集合需重设计**：现有 4 个排列是同一 4-循环的幂，只覆盖 2 种相对座位关系（§6.8）。
