# 模拟线交付 handoff（parallel-v1 / simulation）

> 2026-09-05；本文件记录模拟线的实施交付、支持矩阵、证据与共享文件差异，
> 供主审按 C1→模块→组合根顺序集成。

## 1. 开工记录

| 字段 | 值 |
| --- | --- |
| 工作线 | 模拟线（simulation） |
| contract_id | parallel-v1 |
| contract_commit | cb1f0b759fcf0202bc34760f66858adc026eca1f（已含 C0 契约文档/向量提交 2539573） |
| git rev-parse HEAD | cb1f0b759fcf0202bc34760f66858adc026eca1f（与契约提交一致） |
| 本地 dirty | 是：本线新文件未提交（共享 checkout 纪律：不建分支、不 commit，由主审集成） |
| Python 版本 | 3.11.15（.venv） |
| 本线名 | simulation |
| 官方依据 | 指南 v15/2026-09-05 快照优先；v14 夹具差异保留来源并注明 |

## 2. 实际改动文件及公开导出

新增（全部为本线认领路径，未修改任何既有文件）：

| 文件 | 内容 |
| --- | --- |
| src/hangma_bot/hangma/progression.py | 唯一规则推进：窗口、裁决、链/爆头/抓打圈状态转移、精确结算、庄家轮转 |
| src/hangma_bot/simulation/interface.py | 冻结值对象 MatchSpec/SimulationDecision/SimulationFrame/SimulationChoice |
| src/hangma_bot/simulation/state.py | 不可变 WorldState、RoundRecord |
| src/hangma_bot/simulation/shuffle.py | 确定性发牌 deal-v1（scenario/seed/round_no 独立派生） |
| src/hangma_bot/simulation/projection.py | 世界 → PlayerObservation 纯投影（信息权限边界） |
| src/hangma_bot/simulation/engine.py | SimulationEngine 实现（start/frame/advance/export_hand/from_replay） |
| src/hangma_bot/simulation/identity.py | 契约 §4.1 冻结标识算法（与契约向量逐例对拍） |
| src/hangma_bot/simulation/artifacts.py | 指南版本常量、rules_hash 离线计算（组合根调用，engine 不读文件） |
| src/hangma_bot/offline/replay_check.py | check_hand 历史核对公开入口（契约 §6 冻结） |
| tests/simulation/*、tests/unit/hangma/test_progression_rules.py | 本线测试（68 例） |

公开导出：

- hangma_bot.simulation：SimulationEngine、MatchSpec、SimulationDecision、
  SimulationFrame、SimulationChoice、WorldState、RoundRecord、hand_id、
  split_group_id、simulation_hand_id、simulation_split_group_id、
  compute_rules_hash、GUIDE_VERSION、GUIDE_CAPTURED_AT、DEAL_ALGORITHM、RESERVE_TILES。
- hangma_bot.hangma.progression（hangma 内部，不对评估线冻结）：deal_state、
  attach_draw、end_as_draw、resolve、next_dealer、recompute_baotou、
  chain_after_discard、chain_after_gang 及内部值对象（ProgressionState /
  SeatProgression / MeldRecord / DrawRequest / HandResult / EventRecord / Transition）。
- hangma_bot.offline.replay_check：check_hand(hand, rules) -> dict。

## 3. 完成阶段及支持范围（simulation-start.md §3 切片对照）

- S1 不可变 WorldState、确定发牌、四座独立观察、牌张守恒、序号：完成。
- S2 规则推进（出/摸/响应/结算，含吃碰杠、补牌、财神、抓打圈、链、爆头）：完成；
  全部动作族有脚本化金例（tests/simulation/test_crafted_actions.py）。
- S3 同期响应同一推进前观察、统一裁决、输入顺序不改变结果：完成（不模拟毫秒竞速）。
- S4 连庄/换庄、牌墙耗尽流局、Rounds 完整桌赛、逐局随机源隔离：完成。
- S5 导出 hands 行 + simulation-world/1 world_payload、导入行为一致、反事实
  match_id 保留 parent_hand_id：完成（含进行中局结果为空、冗余字段一致性校验）。
- S6 offline/replay_check.check_hand：完成；三份真实分块资料按能力核对。

规则支持矩阵（动作裁决逐项引用官方证据；未确认项显式 blocked/待确认）：

| 行为 | 依据 | 状态 |
| --- | --- | --- |
| 六动作族窗口与候选 | 复用 HangmaRules.analyze（单一规则源，advance 复核） | 支持 |
| 碰窗口先于吃窗口；吃仅弃牌者下家 | v15 1.1；v14 夹具 3 房间实测（chi 响应者恒为下家） | 支持 |
| 两家及以上同时碰/明杠同一弃牌 | 官方指南未定义优先级 | blocked（不默认先到先得，契约 §6） |
| 弃白本身不开响应窗口 | v14 夹具 4/4 例（弃白后下一事件直接是下家摸牌） | 支持 |
| 圈内普通弃牌仍开窗口、吃碰明杠被拦 | v15 1.1（其余玩家不能吃、碰、明杠）；夹具圈内全员 timeout/pass | 支持（投影按窗口阶段置 catch_play） |
| 圈主出牌只能打刚摸的牌 | v15 1.1；圈主旗标持续到其下次弃牌（那一圈） | 支持 |
| 圈内他家摸牌窗口不受出牌限制 | 指南未述他家限制；按圈主语义只限圈主 | 支持（推断，待测试房验证） |
| 杠上补牌 | v15 1.3；补牌端=可摸区尾端（world_schema 自有语义，入 payload） | 支持 |
| 最后 10 墩（20 张）内禁杠 | v15 1.1；remaining≤20 无杠候选 | 支持 |
| 牌墙保留 20 张不摸、摸完流局 | v15 1.1 | 支持 |
| 连庄/换庄 | v15 1.1（流局庄家连庄；直上三连庄）→ 庄家胡连庄、闲家胡换庄 | 支持（流局连庄明文；庄家胡连庄为连庄语义推断） |
| 碰/吃/杠后、摸牌前禁胡 | 指南变更日志 v1；复用既有 action_families 门禁 | 支持 |
| 有财必拷响 | 复用 analyze 过滤；模拟世界 rule_state.baotou 为静态权威值 | 支持 |
| 副露（碰/吃/杠）后爆头状态 | 无官方证据 | 保守置 False（宁低番不虚高）【待确认】 |
| 番数/明细/四家结算 | 复用 settlement.compute_fan/settle_scores，精确链/piao（非历史推断） | 支持；对拍 t_714a 官方 fan=1、[平胡]、增量 [-8,-1,10,-1] 全通过 |
| 事件时间戳 | 模拟无墙上时钟：事件 ts=null（逻辑时间） | 口径说明 |
| round_ended.data.scores | 官方语义 = 四家增量（夹具 t_714a 实测 [-8,-1,10,-1]）；累计积分在 game_ended.final_scores | 支持（修订轮修复） |
| 事件 data 值序列化 | 导出统一为 JSON 数组语义（list）；进程内 check_hand 与 JSON 落盘后一致 | 支持（修订轮修复） |
| 导入单局导出上限 | max(rounds_per_game, round_no)；反事实另存对 from_replay 单局同样可用 | 支持（修订轮修复） |
| 杠上补牌与牌墙游标 | 补牌只移动补牌端游标（不占用 front）；杠+流局无滞留/无摸保留区 | 支持（修订轮修复） |
| 末局 game_ended 事件 | 末局 record.events 与导出行均含 game_ended（累计积分 final_scores 唯一载体，官方夹具末块口径） | 支持（修订轮修复） |
| 事件 seat 的 -1 语义 | 流局 round_ended 与 game_ended 导出 seat=-1（官方无获胜者语义，夹具 t_714a seq345/346）；单局行 winner_seat 字段仍按契约规范为 null | 支持（修订轮对齐） |
| 导出记录定位 | 按 round_no 查记录（from_replay 单局世界下标与局号不对齐）；无记录旧局号拒绝导出 | 支持（修订轮修复） |

## 4. 测试命令、退出状态、结果摘要与证据路径

    .venv/bin/python -m pytest tests/simulation tests/unit/hangma -q
    -> 671 passed（首轮 68 + 两轮修订回归；tests/simulation/test_rework_regressions.py 10 例）

    .venv/bin/python -m pytest tests/unit tests/contracts -q   -> 862 passed
    .venv/bin/python -m pytest tests/integration -q            -> 74 passed
    .venv/bin/python -m pytest tests/adapters -q               -> 364 passed, 1 skipped

全部测试实际运行（未运行不标通过、无 mock 冒充真实结论）。既有测试零修改。

三份真实分块资料按能力核对（check_hand，tests/simulation/test_replay_check.py）：

| 资料 | 事件数 | 结果 | 说明 |
| --- | --- | --- | --- |
| t_714a42392cba_b0（官方自摸胡，座位 2） | 346 | passed | 引擎胡候选、fan=1、detail=[平胡]、增量 [-8,-1,10,-1] 全部重算一致 |
| t_6c121bfda7e8_b0（官方流局） | 448 | not_checked | 缺墙：流局成因不可核对（not_checked.wall_unknown_draw_cause）；重放零冲突 |
| t_cee1db65a074_b0（官方流局） | 408 | not_checked | 同上 |

身份哈希与归档分块形态的契约向量逐例对拍：tests/simulation/test_identity_vectors.py
（13 例全过），含 hand-769903c4…/split-a831f13e… 等冻结值与三份夹具 SHA-256、块数、seq 范围。

## 5. 未通过或未验证事项（含环境/资料限制）

- 两家同时响应的平台优先级（blocked 口径，见支持矩阵）——需测试房验证。
- 副露后爆头状态、圈内他家出牌限制——需测试房验证（保守口径已按宁低番方向实现）。
- 完整阶段/多阶段赛事模拟、M>1 并发、真实窗口性能：首版不承诺（simulation-start.md §1）。
- 与评估线 S/E 集成、审计线真实统一牌谱文件的联调：等各线交付后由主审组织；本线测试使用
  测试侧映射器（tests/simulation/_helpers.py，测试专用，不冒充生产转换器）。
- 三份真实资料为 v14 夹具、无 gang 事件：杠分支靠脚本化金例覆盖，缺真实杠对拍样本。

## 6. 样例产物路径、SHA-256、来源与缺失

- 规则源哈希（本机此刻，唯一实现 simulation/artifacts.compute_rules_hash，
  契约 §4.2 仓库相对 POSIX 路径口径）：
  78d9ac7ef014d5bdc1076571ff7741fa616e827a2c01d4f6022a8c6f5ae1b53f。
  主审集成记录（2026-09-05）：哈希口径由「包内相对路径」改为契约字面的
  「仓库相对路径」，并收敛为全仓唯一实现（评估线 manifest 同用此值）。
- 样例导出（仓库内可追溯，生成命令：.venv/bin/python tests/simulation/make_evidence.py）：
  tests/simulation/evidence/sample-hand-20260905.json
  （seed=20260905、scenario=sample-scenario、match=sample-match，1 局流局、385 事件，
  末事件 game_ended），SHA-256：
  9a26b5a929e43b0df213008e2a1f2e8c3dbb9ecf9dc24f0c68c75c90fae7673a。
  主审修正记录（2026-09-05）：①生成器原对 sort_keys 变体算摘要、写未排序
  变体落盘，声明哈希与产物不符；已改为对实际落盘字节算摘要并加读回自校验。
  ②rules_hash 口径收敛为契约字面的仓库相对路径后重新生成，本哈希为更新后的实测值。
- 来源：本机模拟生成（origin=simulated、coverage=full_world、world_schema=simulation-world/1）；
  round_ended.data.scores 为增量、game_ended.final_scores 为累计、末局含 game_ended。
- 缺失：事件 ts=null（逻辑时间）；评估线可直接 from_replay 该行复现。

## 7. 需要主审集成的共享文件差异（具体符号/调用点）

本线未修改任何共享文件（hangma/engine.py、internal_types.py、kernel/*、
application/contracts.py、hangma/interface.py、policy/interface.py、既有 scripts 均未动）。
主审需要做的最小集成：

1. bootstrap.py（组合根，装配一处）：
       from hangma_bot.simulation import SimulationEngine, compute_rules_hash
       rules = HangmaRules(config.rules)  # 既有
       engine = SimulationEngine(rules, rules_hash=compute_rules_hash(Path(SRC_HANGMA)))
2. src/hangma_bot/offline/__init__.py：offline 包由审计/评估/模拟三线共建，本线只创建
   offline/replay_check.py；主审创建包 __init__.py（当前 Python 3.11 命名空间包语义下
   hangma_bot.offline.replay_check 已可直接导入，测试验证过）。
3. 其余共享父目录 __init__.py：无改动需求（simulation/__init__.py 为本线自有文件）。
4. 与审计线的交叉点：identity 算法本线实现于 simulation/identity.py（与契约文本逐字对应、
   向量对拍通过）；审计线读写入如需复用可提升到共享位置，或保留双实现（算法已冻结，两处
   必须逐例对拍，见 tests/simulation/test_identity_vectors.py）。
5. 模拟 hands 行口径（供审计/评估消费）：attempt_status 在 result_confirmed=true 时为
   valid、未完成局为 unknown（模拟无 attempt 身份）；事件 ts=null；round_ended.data.scores
   为四家增量。若主审统一口径，只需改 engine 导出处。
6. 推进与历史核对直接 import hangma.progression（见 §8.2 受控设计变更登记）：主审合入
   progression.py 时无需在 HangmaRules 上新增任何委派方法，也不改 engine.py。

## 8. 受控变更请求

- SimulationEngine.__init__(rules, *, rules_hash=None)：相对契约 §6 的签名新增可选
  keyword（默认 None，旧调用方不变）。理由：导出行的 rules_hash 必须由离线计算注入
  （engine 不读文件）。组合根差异见 §7.1。
- 【受控设计变更，主审已认可】规则推进能力没有挂在 HangmaRules 公开方法上委派，而是
  hangma 包内新增文件 hangma/progression.py，由 simulation.engine 与 offline.replay_check
  直接 import 其纯函数（窗口/裁决/链/结算）。理由：(a) HangmaRules 冻结公开签名
  （analyze/validate/emergency_action/score）零改动；(b) 合法性复核仍经 rules.analyze
  单一规则源（advance 与 check_hand 都先 analyze 后执行）；(c) progression 与线上决策
  路径完全隔离，hangma 依旧无网络/文件/时钟/随机依赖；(d) hangma/engine.py、internal_types.py
  等共享文件零改动。progression 的内部接口不对评估线冻结（契约 §6 口径）。
- 无线上接口、kernel、hangma 公开契约、policy 接口的任何变更。

## 9. 主审集成完成记录（2026-09-05）

- 身份哈希唯一落点：hand_id/split_group_id/identity_digest 已提升到
  kernel.identity（全仓唯一实现）；simulation/identity.py 改为转导出 +
  模拟专用包装，offline/replay.py 与 offline/evaluation_results.py 改为
  转导出/委托。三线同值经集成冒烟实测一致。
- rules_hash 唯一落点：simulation/artifacts.compute_rules_hash 为全仓唯一
  实现，口径改为契约字面的「仓库相对 POSIX 路径」（78d9ac7e…）；评估线
  manifest 改 re-export，与模拟导出行同源同值。
- 组合根装配：bootstrap.py 提供 build_evaluation_runtime(kind="matches")
  （真实 SimulationEngine + MatchSpec/SimulationChoice 工厂）与
  build_decision_codec()（审计 C1 codec 注入）；本线 handoff §7.1 的
  装配建议已落盘，engine.py 保持零改动。
- 证据链修正：tests/simulation/make_evidence.py 摘要改为对实际落盘字节
  计算并加读回自校验；样例产物随 rules_hash 口径更新重新生成，§6 哈希
  为实测值（9a26b5a9…）。
- 集成验证：全套测试 1648 passed, 1 skipped；E3 真实 matches 实验经
  scripts/evaluate.py 跑通（真实引擎 + 换座聚类）。
