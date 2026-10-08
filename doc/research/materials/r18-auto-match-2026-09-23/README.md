> **状态：历史自由赛/watchdog 账本快照（2026-09-23），不是当前 watchdog 恢复或续开指令。** 房号、账本数值、停止状态及命令可能过期；当前资料从 [`review/INDEX.md`](../INDEX.md) 进入并按现行运行状态核实。

# R18 冻结包首轮自由赛采集与分析（2026-09-23）

> 会话：`artifacts/sessions/r18-integrated-positive-v1-auto-match/`；房间 `a_55f18ee75775`；
> run `run-e678414cdcbd4829874e55c95dae5361`；postgame job `20260922T171338Z-4be16fcc`。
> 配置：`configs/r18-integrated-positive-v1.auto-match.example.json`（副本 `.private/r18-integrated-positive-v1-auto-match.json`）。

## 八房阶段汇总（同日续采）

截至第 8 房，审计完整口径为 **80 场累计 +136**，八个房间小计依次为
`+46 / -147 / -34 / +47 / +150 / +57 / +91 / -74`，正房 5、负房 3。全部房间正常
`tournament_finished`，各房 `decision_planned` 与 R18 评分完成数相等，未观察到评分层降级。
这些自由赛没有与 V2 做同牌山、换座配对，且房间波动很大，因此只能证明 R18 可稳定运行并提供真实机会样本，
不能把累计正分直接解释为优于 V2。

## 十一房检查点

截至第 11 房，审计完整口径为 **110 场累计 -138**，房级小计依次为
`+46 / -147 / -34 / +47 / +150 / +57 / +91 / -74 / -13 / -234 / -27`。第 11 房
`a_de5aed954f2f` 的 1719/1719 个决策均由 R18 评分层完成，审计零丢失、零降级；完整摘要见
`rooms/a_de5aed954f2f.md`。累计成绩仍不是与 V2 同牌山、换座配对的强度证据。

脚本现行止损合同是累计分低于 -1500；代码注释记录用户已取消连败限制。因此此前文档中的“连续 3 房”为旧参考口径，
不再用于自动停止。自由赛继续只承担运行可靠性与自然状态采集，不替代本地配对强度门。

第 6 房最初账本只记 9 场、漏掉审计已完成的 b9 `+39`，导致当时累计少记 39 分。根因有两处：下载完整性
错误地把“任一批次已下载”当成“全房已下载”，结算又使用 `table or finals` 而不是两者并集。现已改为逐批次
完整性核对、下载与审计场次取并集、从权威状态读取本人座位，并在每次持锁巡检时用审计补齐历史漏场；账本已
重算为 +210。该修复只改变战役测量与止损账本，不改变策略或线上动作。

## 结论

1. **运行与规则匹配全部正常**：房间 `BaseScore=1`、`YouCaiBiKao=false`、M=10/Rounds=8、`Kind=auto`，与 r18 冻结包适用范围一致；1380/1380 个决策全部由 r18 评分层完成，**零次规则不符退回 V2**。
2. **可靠性达标**：审计 69063 条零丢失；955 次动作提交全部 HTTP 200（1 次 409 已按窗口规则处理，未重发非幂等动作）；无服务器代打损失；80/80 局终局结算与本地唯一规则引擎逐项一致（庄家/赢家/流局/积分/番）。
3. **成绩偏低但不构成统计判定**：10 场总净分 **-60**（场均 -6.0），排名分布 1/2/3/4 名 = 2/4/2/2，净分为正 5 场。对照 2026-09-07/08 的 V2 自由赛账本（40 房 400 场，房级场均 +11.0、sd 12.9），本场场均位于历史分布约 **第 10 百分位**；单房 10 场的抽样 sd 约 12 分/场，-6.0 对 +11.0 的差约 1.4 个抽样 sd，**无法区分运气与实力因素**。
4. **r18 两个窄域特有能力层（P3 加杠支配、P5 七对价值）本轮零触发**——80 局中未出现其触发域；核心动作价值评分层在 22.4% 的被选动作上带非零增量（河牌项 286 次、风险项 23 次、胡牌排序层 19 次），**不是空操作**。

## 运行事实（官方已确认）

| 项 | 值 | 来源 |
| --- | --- | --- |
| 房间 / 批次 | `a_55f18ee75775`，batch 0–9 各一场、全部 finished | 官方 games 列表（2026-09-23 下载） |
| 房间规则 | `BaseScore=1`、`YouCaiBiKao=false`、`DiscardTimeoutSec=3`、`Peng/ChiTimeoutSec=1` | `POST /api/match` 响应原文（raw `match_response`） |
| 我方身份 | `u_13495c3d79c8`（四局 0 号位、三局 1 号位、三局 3 号位） | 审计决策窗口座位 |
| 终态 | `tournament_finished`，10 场全部 `game_ended` | lifecycle.jsonl |
| 审计 | written 69063，dropped/missing/serialization 均为 0 | RESULT 行 |

## r18 参与度（当前观察）

- `decision_planned` 1380 条的 `degraded_reasons` 全部含「action_value: r18_integrated_positive_v1 评分完成」；候选 `basis` 全部为 `direct_v2`，`score_parts` 全部含 `action_value_v1`。
- 被选动作（rank-1 候选）含非零 r18 增量项的决策 309/1380（22.4%）：`river_part` 286、`risk_units` 23、`hu_sorting_layer=True` 19；`wealth_part`/`style_part` 无非零样本。
- `r18_gang_dominance_overlay`（P3）与 `r18_seven_pairs_value_overlay`（P5）在审计 reasons/候选 JSON 中零出现。两层的触发域本身极窄（P5 限「庄家起手首次摸牌；83 张公开余量；四家空牌河且无副露」），80 局零触发不能证明实现缺陷；后续采集继续观察。

## 成绩与画像

| 场次 | 我方座位 | 终局四家分 | 我方 | 名次 |
| --- | --- | --- | --- | --- |
| b0 | 0 | [-45,-30,30,45] | -45 | 4 |
| b1 | 3 | [-10,43,-22,-11] | -11 | 3 |
| b2 | 0 | [-29,-37,-37,103] | -29 | 2 |
| b3 | 3 | [-80,30,45,5] | 5 | 3 |
| b4 | 0 | [-23,-5,-2,30] | -23 | 4 |
| b5 | 3 | [18,-2,-35,19] | 19 | 1（并列） |
| b6 | 1 | [-12,9,-6,9] | 9 | 1（并列） |
| b7 | 1 | [-32,-14,-25,71] | -14 | 2 |
| b8 | 1 | [30,12,-12,-30] | 12 | 2 |
| b9 | 3 | [-43,44,-18,17] | 17 | 2 |

- 80 局终局方式：**全部自摸胡**（我方 19、他家 61），零荣胡、零流局。本平台结算无“放炮”概念——胡牌收入由其余三家分摊（如 `round_ended.scores=[-8,24,-8,-8]`），与哪张打出的牌无关；分析不得引入点炮统计。
- 我方胡牌番分布：1 番 15 次、2 番 4 次；我方胡牌率 19/80 = 23.8%，四家均势期望 25%。
- 历史对照（弱参考，对手池与日期均不同）：V2 账本 `review/auto-match-value-2026-09-08/ledger-snapshot.json`，40 房场均 +11.0、正场率 53.5%；其账本末期 10 场均值也曾到 -11.4。

## 可靠性细节

- 提交结果（observation-status.json）：`SubmitAccepted` 955、`SubmitNotSent`（本地延后 Pass）423、`SubmitRejectedNoRefresh` 1；无超时失败类别。
- HTTP：state 轮询 429 限流 45 次均由调度退避恢复；`state_response:None` 11 次未影响任何决策窗口；match 请求 1 次成功。
- 官方事件流中我方座位 `timeout` 记号：`response` 2243 次（吃碰响应窗口不显式发 Pass 时的平台记账；全桌四家合计 4823 次，同模式）、`discard` 2 次。两次 `discard` 均核查为**压线提交后动作实际生效**（例：b5 seq 1217 摸牌 → 我方 6.7ms 完成决策提交 `discard:3t` → 官方 seq 1218 执行 → 同秒记窗口到期），不是服务器代打。
- 决策完整性：1380/1513 完整，133 条 `missing_decision_input` 排除——与历史自动房会话（426/3715）同模式，属紧急路径已知形态，不新增风险。

## 发现的问题

1. **RUN_MANIFEST 身份摘要被通用脱敏误伤**：`policy_release` 中 `candidate_id`、`candidate_source_sha256`、`release_package_id` 落盘为 `[REDACTED]`（`adapters/recording/redact.py` 的 40+ 字符长串规则命中 sha256 形态）。P54 验收声明“RUN_MANIFEST.policy_release 保存完整候选身份”与实际落盘不符。**本次以代码常量独立核验发布包 ID 等于批准值** `4c086e2e…681b8`，证据链未断，但建议审计线为 manifest 的身份摘要字段增加豁免（与 endpoint 豁免同类）后再继续依赖 manifest 内字段做包身份核验。
2. 单房样本不构成对 r18 的统计判定（见结论 3）；后续按 P54 计划继续采集，累计多房后再做房级汇总与止损检查（参考账本止损规则：连续 3 房小计为负）。

## 复算入口

```bash
.venv/bin/python scripts/audit_tool.py postgame artifacts/sessions/r18-integrated-positive-v1-auto-match --rule-config .private/rule-config.json
```

牌谱原文：`artifacts/sessions/r18-integrated-positive-v1-auto-match/official/dl-*/events.json`（batch 0–9）。

## 战役终局汇总（31 房，2026-09-23 收工）

盯守战役 `runs/auto-match-watchdog/auto-match-watchdog-state.json` 于第 31 房结算后按用户指示收工
（`stopped=true`），全部 31 房 `tournament_finished`，共 310 场。

| 策略段 | 房号 | 房数 | 小计 | 场均/房 |
| --- | --- | --- | --- | --- |
| v1 原冻结包（4c086e2e…，timeout 修复前代码） | 1 | 1 | +46 | +46.0 |
| v1 修订版（timeout 修复 + P55 价值分析层） | 2–24 | 23 | -501 | -21.8 |
| **v2（e82f904c…）** | 25–31 | 7 | -114 | -16.3 |
| 合计 | 1–31 | 31 | **-569** | -18.4 |

- 分段身份以各房 audit manifest `policy_version` 逐房核验为准（房 24 及以前 v1、房 25 起 v2）；
  v2 段为 7 房小样本，与 v1 修订段 -21.8/房 的差异不具统计显著性，仅方向参考。
- 23 房时点的全量体检结论（见上文与主会话记录）：API 面无事故（无 5xx/认证失败，409×16、
  429×441、state 无响应 0.73% 全部按设计自愈）；策略降级 34/36584 窗口（0.09%）——其中
  catch_play 修复验证（房 2 起 22 房零复发）、其余三类（chain_piao 链历史不足、candidate_facts
  牌效重叠缺、房 13 的 action_value_failed×1）为 v1 修订版价值分析层的显式降级，移交
  P55/P56 线跟进。
- 逐房明细：`rooms/` 目录 31 份房级摘要（每份含策略身份与 r18 覆盖计数）。
- 复盘入口：账本与官方牌谱随各房会话保存在
  `artifacts/sessions/r18-auto-match-campaign-20260923/`（audit + official/dl-*）。
