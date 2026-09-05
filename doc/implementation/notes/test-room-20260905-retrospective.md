# 测试房 t_9779c892550e 最终复盘（2026-09-05，自唤醒修复版代码）

> 数据源：4 个收尾 run 目录（baihu/qinglong/xuanwu/zhuque 各 1，r6 双桌 b0/b1）。本篇同时是牌谱导出（`scripts/export_game_records.py`）的字段说明。

## 一、会话终局

| 场次 | 终局分（按座位 0-3） | 座位→身份 | 合计 |
| --- | --- | --- | --- |
| r6_b0 | [-4, 50, 11, -57] | 0=zhuque 1=qinglong 2=baihu 3=xuanwu | zhuque -4 / qinglong +50 / baihu +11 / xuanwu -57 |
| r6_b1 | [23, 69, -42, -50] | 0=xuanwu 1=qinglong 2=baihu 3=zhuque | xuanwu +23 / qinglong +69 / baihu -42 / zhuque -50 |

- 双桌合计：qinglong +119、baihu -31、xuanwu -34、zhuque -54（测试房积分仅用于验证，不作策略结论）。
- 4 身份均 `participant_finished(tournament_finished)`；审计零丢失（write_failures=0、dropped=0、audit_degraded=false）。

## 二、修复验证结论（对照 09-04 基线）

- 提交 4829 次全部接受 + 11 次拒绝（见 §三，均为良性窗口竞态）：**0 非法动作、0 重复提交、0 hu 误判、0 限速非 2xx**；
- 决策时延（事件 ts → decision_planned，n=3510）：p50=0.47s / p90=0.86s / p95=0.90s / p99=0.94s / max=3.93s；
- SSE 帧驱动全程生效（全会话轮询间隔 99.7% < 1.5s），无 `sse_degraded`、无重连风暴；
- 自唤醒（SubmitAccepted 后主动唤醒）路径正常：无双桌争用导致的迟到。

## 三、新问题

### N1（P1）：SSE 服务端通知静默停摆不可检测

- **现象**：墙钟 1788608719-8795（约 76 秒）内，4 个进程同步退化为 5 秒批量短拉（各 19-21 次"一次响应携带 ≥3 事件"，而全会话其余时段为 0）；该窗口产生 14 条 >2.2s 的迟到决策（全部 draw 相位）。
- **证据链**：迟到决策的**规划耗时仅 27-91ms**（收到即决策），送达滞后 2.5-3.9s —— 我方不慢，事件没送到；连接未断（无 sse_degraded/重连记录），即连接活着、帧没来，服务端 notify 单方面停摆后自愈。
- **影响**：3 秒出牌窗口内 8 次 POST 落在服务端超时代打之后被拒（`cannot discard in phase 2`）；**服务器代打规则 = 打刚摸的牌**（9 例中 7 例实锤=摸牌、1 例采样噪声、1 例与意图同牌）。响应窗口迟到表现为 timeout 自动 pass，本次无认领损失。另 3 次 pass 拒绝（`cannot pass in phase 1`，seq 2899/2975/3065）发生在停摆窗口**之外**，属他家先认领的普通窗口抢占竞态，F 系修复的吸收路径正常工作。
- **修复建议**：
  1. notify 客户端加**静默看门狗**：活跃对局中若 ~10s 无任何字节（帧或 30s keepalive），主动断开重连并立即短拉对齐；
  2. `_SSE_IDLE_POLL_SEC` 5.0 → 1.5s（< 3s 出牌窗口）作纵深兜底，评估限速预算后启用；
  3. SSE 帧与 keepalive 间隔写入审计（当前 raw 仅有 state/submit 两类 source，静默不可归因）。

### N2（P3）：submission_outcome 双写

同一次提交在 decisions.jsonl 落两条：adapter 视角（payload 含 `outcome/window`，`game.py:1083,1277`）+ 应用层规范视角（含 `outcome_type/action_key`，`decision_loop.py:560,581`）。两边结果 0 不一致，但记录量 ×2、统计口径易混（本复盘计数均以应用层视角为准）。建议二选一或拆分为两个 kind。

### N3（P3）：rebuild_snapshot_gap 成对出现

每场 ~28-30 次 `rebuild_snapshot_gap`，几乎全部连号成对（seq N 与 N+1 相隔 ~80ms 双重建）。事件流稀疏（摸牌大多不附事件、认领不附事件、代打仅附 timeout 事件）导致游标跳空本属正常，但"一次空隙两次重建"疑似重建后未消费新水位即复检，多花一次全量快照。建议调查重建路径的水位消费时机。

### 观察记录（非问题）

- 一次 `state_response` 的 raw 为空串（wall=1788608719040，恰为 N1 停摆起点），疑为停摆首发响应异常被吸收，无后续影响；
- `god` 机制实战出现：baotou=True（b0 33 快照 / b1 12 快照）、chain_count=1（7/3 快照）；catch_play 全程 false；
- 事件词表实测（去重）：tile_discarded 4778 / timeout 392（response.peng 272、response.chi 89、discard 31）/ pass 141 / tile_drawn 109 / gang 20（bu 16、an 4）/ peng 2 —— 全部在 `KNOWN_EVENT_TYPES` 内，无未知事件；
- timeout(kind=discard) 共 31 次 = 服务端出牌超时代打总数（含 N1 窗口 9 次）。

## 四、规则核对结论

- `rule_completeness=complete` 覆盖 **4829/4829** 已接受提交的计划，规则层无降级、无 RuleIssue 拦截；
- 27 个含 hu 候选窗口全部选择 hu（27/27），0 漏胡；
- 97 个含认领候选（peng/chi/明杠）的响应窗口全部认领（peng 88 / gang 6 / chi 3），0 漏认领（claim_if_legal 策略生效，58 条 degraded_reasons 均为该策略的说明性标注）；
- 11 次拒绝全部是窗口关闭竞态（他家先认领 3 / 我方迟到代打 8），无一例"非法牌型/非法动作"类拒绝 —— 规则引擎在 4840 次提交中零非法输出。

## 五、牌谱导出（数据流）

`scripts/export_game_records.py`（纯标准库、只读审计、无 Token）：

```bash
python3 scripts/export_game_records.py \
  --run baihu=runs/slot-baihu/runs/run-XXX --run qinglong=... \
  --game t_9779c892550e_r6_b0_t0 --game t_9779c892550e_r6_b1_t0
```

输出 `exports/game-records/<game_id>.json`（exports/ 不入库），顶层字段：

- `meta`：game_id、tournament_id、source_runs（slot→run_id）、participants（slot→participant_id）、seat_of_slot / slot_of_seat（座位↔身份，逐表从快照 `seat` 读取）、final_scores（座位 0-3 顺序）、final_seq、finished_wall_ms（Unix 毫秒）；
- `events`：官方事件流按 seq 去重合并，字段为官方原样（seq/type/seat/tile/data/ts，ts 为服务端秒）。**事件流稀疏**（见 §三 N3 上方观察），分析以快照为权威；
- `snapshots`：按 (seq, 观察座位) 去重的官方快照，外层为 seq / wall_ms（本机 Unix 毫秒）/ observed_by_seat / gap，`snapshot` 内为官方字段原样；`my_hand` 是观察权限字段（仅观察者本人手牌），牌效分析以各座位 my_hand 演进 + 全桌 discards/melds 重建；
- `submissions`：我方全部提交按墙钟排序；应用层结果记录（含 action_key/outcome_type/official_code）与 adapter 原始响应记录（含服务端返回原文）各一条。

本次导出：b0（events 799 / snapshots 7874 / submissions 5068，7.5MB）、b1（721 / 7181 / 4612，6.6MB）。

### 牌效分析与策略复盘的后续入口

- 得失归因（放铳/小番胡/漏杠漏飘）需要本牌谱 + 各窗口候选/向听数据（decisions.jsonl 的 candidates 已含"动作后向听数、有效牌种数与剩余估计"）联合离线回放，属于 P2 策略回放管线（未开工）；
- 测试房 4 身份互打只验证协议与规则正确性，策略强度结论以正式测试赛事为准（09-04 赛事复盘口径不变：分差量级为策略尺度，归因需回放管线）。
