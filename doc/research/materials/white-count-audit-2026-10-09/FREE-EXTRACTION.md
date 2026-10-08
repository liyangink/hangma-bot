# 本月自由赛四座原始事实提取

当前可核验样本是 **291 个房间、2,903 桌完整桌赛、23,224 个我方单局**。全部桌赛逐一完成官方四座结算对账；这份样本覆盖现存可读捕获，不代表平台本月全部记录。最早官方事件为北京时间 **2026-10-04 08:44:05**，最晚为 **2026-10-08 12:36:19**。未找到 10 月 1—3 日可用的自由赛四座原件，不能据此断言当时没有比赛。来源：[提取结果](../../.private/white-count-audit-2026-10-09/EXTRACTION.json)、[逐桌索引](../../.private/white-count-audit-2026-10-09/TABLES.json)。

## 样本和策略身份

按策略及接线身份分别保留样本，后续比较不得把不同身份视为同一稳定版本。官方场次（`Official Game`，以一个 `game_id` 标识的比赛单元）全局去重；本次完整样本中，每个场次均含八个单局（`Hand`，一次发牌至胡牌或流局的麻将牌局）。来源：[逐桌索引](../../.private/white-count-audit-2026-10-09/TABLES.json)、[提取脚本](./free_extract.py)。

| 身份 | 现存可核房间 | 完整桌赛 | 我方单局 | 四座单局 |
|---|---:|---:|---:|---:|
| S02 | 150 | 1,493 | 11,944 | 47,776 |
| S03 | 89 | 890 | 7,120 | 28,480 |
| P0 | 52 | 520 | 4,160 | 16,640 |
| 合计 | 291 | 2,903 | 23,224 | 92,896 |

S02 含 `free_v6` 的 1,130 桌、`free_v7` 的 350 桌，以及早期 `free_v3` 可读的 3 桌、`free_v4` 的 10 桌；S03 含 `free_v1` 的 310 桌、`free_v3` 的 580 桌。P0 为四个控制器系列保存的 520 桌。七种包身份均绑定现存清单，S02 公式摘要为 `2a59cbb18aefa3d24aadf0b3df70f5a4359c204b96a3f0dc208f77d53c196f30`；S03 与 P0 公式摘要同为 `bdd7d29736f1b2a00240648cbb8a837e29fbfb2b10434471272b8d8a84b190dd`，它们的规则与接线身份仍分别保存。来源：[逐桌索引](../../.private/white-count-audit-2026-10-09/TABLES.json)、[字节来源索引](../../.private/white-count-audit-2026-10-09/SOURCE-INDEX.json)。

## 完整性和覆盖缺口

全部 2,903 桌状态为 `finished`，八单局的 `round_ended` 四座分数分别零和，四座八单局累计分数分别等于唯一 `game_ended.final_scores`；官方事件 `seq` 从 1 连续至场终，无块截断、冲突重复或未解决的序号缺口。已有汇总可比较的 22,720 个我方单局，分数、庄家、胡家、白板起手数、终局序号和原件摘要逐字段相同。其余单局按原件纳入，不依赖汇总存在或成功。来源：[提取结果](../../.private/white-count-audit-2026-10-09/EXTRACTION.json)、[提取脚本](./free_extract.py)。

起手白板数及后摸白板信息在全部 92,896 个座次单局中完整；23,052 个赢家的胡牌时白板库存全部可由明示起手、摸牌、弃牌事件追踪。4,912 次杠补牌单列，不混入普通摸牌数；没有未知摸牌原因。官方指南版本在本次来源元数据中保留为抓取时的 `guide_version`，不以当前版本改写历史事实。来源：[四座事实](../../.private/white-count-audit-2026-10-09/SEAT-HANDS.jsonl)、[提取结果](../../.private/white-count-audit-2026-10-09/EXTRACTION.json)。

仍有以下原件缺口，因此不把本分析称为本月全量自由赛分析：

- T143 有十桌捕获映射，但对应原始报文当前不存在；全部列入缺口。
- T157 有十桌捕获映射，仅三桌 HTTP 重试保存的报文可读；另七桌列入缺口。三个可读场次照常纳入，房间统计单位仍是一个房间。
- T165 的五份自由赛计划、T170 保存的五份计划，以及 P0 `recovery-v2/batch-003` 计划，均没有现存可读自由赛捕获映射。计划数量不是这些历史系列的实际比赛总量，不据此填补或估计成绩。

这些缺口逐路径保存在 [coverage](../../.private/white-count-audit-2026-10-09/EXTRACTION.json)。额外检索当前 `review/`、`.private/`、`artifacts/` 的 1,580 个 `events.json`，全部与已纳入捕获字节摘要相同，没有带来新场次；未读取大审计压缩文件。来源：[替代原件库存](../../.private/white-count-audit-2026-10-09/ALTERNATE-SOURCE-COVERAGE.json)。

## 字段与比较口径

起手财神（`initial_white_count`，起手白板张数）由赛后 `start_hands` 提取，属于回顾信息。按 0、1、2 张及以上保存 `initial_white_bucket`；后摸白板张数由摸牌事件提取，另保留 `has_later_white`，用于后续检验起手分层结论是否受后摸白板影响。这些赛后字段不会进入线上策略输入。来源：[提取脚本](./free_extract.py)。

| 字段 | 用途与单位 |
|---|---|
| `net` | 官方该座位单局净积分，直接取 `round_ended.data.scores[seat]` |
| `ordinary_income` / `highfan_income` | 赢家积分按官方 `fan < 4` / `fan >= 4` 分账，未重算结算公式 |
| `payments` | 他家胡牌时本人的支付，保留官方负数 |
| `payment_dealer_to_non_dealer` | 本人庄家支付闲家 |
| `payment_non_dealer_to_dealer` | 本人闲家支付庄家 |
| `payment_non_dealer_to_non_dealer` | 本人闲家支付闲家；三类支付互斥且相加等于 `payments` |
| `draw_residual` | 流局时的官方积分，单独保留 |
| `ordinary_draws` | 该座位明确普通摸牌事件次数；杠补由明示 `gang_replenish=true` 单列 |
| `gang_replenishment_draws` | 该座位杠补牌事件次数 |
| `ordinary_draws_plus_dealer_initial` | 普通摸牌次数加庄家起手第 14 张的一个起始机会，便于庄闲比较；原始普通摸牌数不改写 |
| `white_draws` / `white_draws_ordinary` / `white_draws_gang` | 起手之后摸到白板的总数、普通摸数、杠补数 |
| `has_later_white` | 起手后是否摸到白板；原件缺信息时为空，不能填成否 |
| `whites_held_at_hu` | 胡牌时手内白板库存；无法完整追踪时为空，不能填成零 |
| `chi` / `peng` / `gang_*` | 该座位实际吃、碰、各类杠的事件次数 |
| `discard_timeouts` / `response_timeouts` | 官方自动弃牌与响应超时分别计数；响应超时不等于主动过牌 |
| `round_first_event_ts` / `round_ended_ts` | 官方 Unix 时间，单位秒；不用于推断本机决策耗时 |
| `source_path` / `source_sha256` | 实际读取的保存报文及原始字节摘要 |
| `seats` / `final_scores_seat0123` | 表级身份与最终积分，固定按座位 0、1、2、3 排列 |

赢家本人摸牌次数只能描述胡牌发生时的兑现快慢，不能替代整体听牌速度或首次听牌时间。全月提取不进行听牌复算；真正听牌指标另由测试赛事专项核验提供。所有工程告警样本保留：我方 16 次自动弃牌、16,656 个带工程 warning 标记的单局、9,304 个带 contamination 标记的单局均仍在事实表中；两个标记可重叠。来源：[四座事实](../../.private/white-count-audit-2026-10-09/SEAT-HANDS.jsonl)、[提取脚本](./free_extract.py)。
