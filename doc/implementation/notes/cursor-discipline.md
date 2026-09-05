# 官方 /state 轮询游标纪律修复笔记

> 日期：2026-09-05（撰写）
> 归属：任务 2/4（官方 /state 轮询游标纪律修复），改动文件 `adapters/official/game.py`、
> `adapters/official/sync_state.py` + 回归测试 `tests/adapters/official/test_cursor_discipline.py`
> 官方依据：`doc/references/official-guide-v14-content.txt`（指南 v14 全文，2026-09-05 抓取核对）；
> 实测证据：2026-09-04 官方测试赛 `t_dee58824c308`（M=10、Rounds=16）完整审计
> `runs/runs/run-29a71a10ad12441eb15e0ac4cfb55c1d/`

## 1. 结论

1. **摸牌窗口改为增量直达**：本人摸牌（`tile_drawn`）事件成为事件流末条时，摸牌窗口直接由增量事实送达，
   不再逐批 `seq=0` 全量快照刷新——胡牌/出牌决策不再常态性依赖快照送达（官方依据：「客户端局面 = 快照 +
   后续增量事件」「事件流只含自己的摸牌」）。
2. **快照刷新改为触发制**：只在增量事件无法推导权威事实时刷新（弃牌/timeout/本人副露/缺牌码摸牌事件），
   正常事件流（连续摸牌、过牌）零重建。
3. **跨局边界退避**：v10 规则下新局首事件产生前，旧游标轮询会立即重复收到同 seq 的 `gap=true` 快照
   （实测同一边界重复 5~47 次）；修复后前 2 次原速、此后指数退避，重复数有界收敛。
4. **取消/重连不回退游标**：审计确认所有取消路径不写游标；新增回归测试锁定该纪律。
5. **POST 后游标不重置**：动作提交不改变游标（游标永远是本地已消费 seq），动作效果由下一次增量轮询送达；
   官方 demo 的「POST 后 seq=0 重建」是可选保守做法，不是语义要求。

## 2. 官方语义依据（指南 v14 原文核对）

`doc/references/official-guide-v14-content.txt` 的 /state 端点条目与 §2.1 协议要点：

- 「`/api/games/{id}/state?seq=N`：`seq=0` 返回全量快照（含你的手牌、座位 seat、窗口成员
  responding_seats 等自主决策字段）；`seq=N` 返回 N 之后的新事件；无新事件时挂起最多 30s 后返回
  `{"pending":true}`；**seq 落后当前局（round_ended 后新局已发牌、不产生事件）→ 立即返回全量快照（gap:true）**」
- 「快照规范：seq=S 的响应已包含全部 ≤S 的事件，快照是规范真相；**客户端局面 = 快照 + 后续增量事件**
  （事件带自身 seq，校验连续性）」
- 「跨局边界（v10 起）：每局结束（round_ended）后新局自动发牌不产生任何事件——事件流在新局首个动作前为空，
  庄家第 14 张为发牌直抽、无摸牌事件。此时继续用上一局末的 seq 轮询会立即收到新局全量快照（gap:true，
  含你的新局手牌 my_hand/round_no/phase）……新局手牌一律以快照为准。」
- 「游标纪律：/state 的 seq 参数语义 =『N 之后的事件』——**游标永远是本地已消费 seq**，初始帧的 seq 是
  包含式水位（服务器已发到 N），不可直接当轮询游标；游标未知请 seq=0 拿快照起步。」
- 「私有信息：**事件流只含自己的摸牌**；他人手牌绝不出现。」

推论（本修复的核心依据）：

- 全量快照的 `seq` 是包含式水位：消费完整快照后游标应设为该值（`apply_full_snapshot` 已如此实现）。
- 本人 `tile_drawn` 事件产生后，直到本人出牌/超时前不会有任何其他事件：**「事件流末条是本人 tile_drawn」
  等价于「当前处于本人摸牌窗口」**，且 `draw 且 turn==seat` 可出牌/胡/杠。
- v10 跨局规则在「新局首事件未产生」时对旧游标轮询立即回 gap 快照：这是**每局边界一次的正常行为**；
  同 seq 反复重收不是协议要求，而是本地无退避轮询造成的浪费（限速额度 + 审计刷爆）。

## 3. 实测证据（2026-09-04 测试赛审计）

`participants/u_13495c3d79c8/games/*.jsonl` 中 `protocol_recovered` 共 3063 条，按 trigger 分解：

| trigger | 条数 | 归属 | 说明 |
| --- | --- | --- | --- |
| （应用层，trigger 为空） | 1191 | 应用层 | `decision_window` 窗口结束簿记 814+360+3、decision_loop 6、场次重发现 8（dto_invalid/get_exhausted）——非快照重建 |
| `conflict_refresh` | 1338 | 动作提交 | 动作 POST 409 → seq=0 权威刷新（另一工作线：响应窗口身份/anchor_seq 稳定化） |
| `rebuild_snapshot_gap` | 531 | 本工作线 | v10 跨局 gap 快照；快照 seq 全为局边界水位，且**同一边界同 seq 重复 5~6 次、最严重 47 次** |
| `conflict_refresh_unavailable` | 3 | 动作提交 | 409 后刷新不可用（另一工作线） |

- 场均（每 game，共 10 场 × 16 局）≈ 306 条；`rebuild_snapshot_gap` 场均 ≈ 53 条、约每局边界 3.3 条。
- 120 次胡牌决策全部发生在重建后的快照路径上：摸牌送达依赖每增量批后的强制 `seq=0` 快照，
  被拒（409）后再次走 `conflict_refresh` 快照路径——「被拒组与重建的时间距中位数 0ms」。

## 4. 游标路径审计表（现状 vs 正确语义 vs 修复）

「正确语义」= 指南 v14 游标纪律（游标永远是本地已消费 seq；快照 seq 为包含式水位）。

| # | 路径 | 修复前游标值来源 | 与正确语义的差距 | 修复后 |
| --- | --- | --- | --- | --- |
| 1 | 增量事件消费后（apply_events ACCEPTED） | 游标推进到末事件 seq，**随后无条件强制 seq=0 快照**，游标再被快照水位覆盖 | 每增量批一次全量重建：摸牌送达常态性依赖快照（官方只要求「快照 + 后续增量」） | 按 `events_need_authoritative_refresh` 触发制：无触发时游标停在末事件 seq，摸牌窗口直接增量投递；触发时才 seq=0 |
| 2 | 动作 POST 完成后（accept/409） | 游标不变（保持本地已消费 seq）；409 路径 seq=0 刷新后 = 快照水位 | 无差距（官方 demo 的「POST 后 seq=0」是可选保守做法，非语义要求） | 保持并加回归测试锁定 |
| 3 | 阶段切换后（R1 边界定时器竞速刷新） | seq=0 快照 → 游标 = 快照水位（≥ 旧游标，单调） | 无差距 | 保持 |
| 4 | 长轮询取消/超时后重连 | 取消路径不写游标（`_long_poll_racing_boundary` 取消挂起轮询后游标不动）；重连（新会话）从 0 起步 seq=0 快照 | 无差距 | 保持并加回归测试锁定 |
| 5 | seq=0 重建消费完成后（apply_full_snapshot） | 游标 = 快照 seq（包含式水位） | 无差距（快照为规范真相；官方契约保证 seq=S 含全部 ≤S 事件，正常服务器下不回退） | 保持 |
| 6 | 跨局边界（v10 gap=true 快照） | 快照吸收后游标 = 快照水位；无进度时**立即重轮询** → 同 seq gap 快照反复重收（实测 5~47 次） | 差距：新局首事件产生前每次轮询都重收同 seq 快照，浪费 16/s 额度并刷爆恢复审计 | 无进度 gap 快照前 2 次原速（保响应窗口发现时延）、此后指数退避（0.5/1.0/2.0s 封顶）；快照水位前进即恢复增量 |

> 注：路径 5 的「序号回退也整体替换」是既有受测语义（`test_full_snapshot_replaces_state`，快照是规范真相），
> 本任务不改动；取消/重连路径不写游标，不存在回退。

## 5. 修复内容

### 5.1 增量直达摸牌窗口（`sync_state.py` + `game.py`）

- `ProtocolSyncState.incremental_draw_window()`：事件流末条是本人单牌 `tile_drawn` → 摸牌窗口
  （`WindowKey(trigger_seq=摸牌事件 seq, phase=DRAW)`；与快照路径同值，摸牌窗口期间无其他事件推进水位）。
- `ProtocolSyncState.incremental_draw_observation()`：快照观察 + 增量事实（`drawn_tile`=摸牌事件牌码、
  `phase="draw"`/`turn=seat`/`responding_seats=()` 由摸牌语义推导、最新弃牌取事件流事实、牌河追加增量弃牌）。
  `my_hand` 直接沿用快照——安全性论证：本人一切改牌动作（弃牌/副露/超时）都在刷新触发集内，摸牌事件成为
  事件流末条时本人自最后快照以来必然未改牌。
- `OfficialGameSession._maybe_deliver_incremental_draw_window()`：与快照窗口同享 exactly-once（
  `_delivered_windows` + `ActionGate`）与 AUTHORITATIVE_STATE 审计口径。
- `_submit_locked` 增加增量窗口复核分支：快照仍是旧相位时也能识别增量窗口身份并构造动作请求体，
  否则所有增量摸牌窗口都会被 `stale_window` 本地拒绝。

### 5.2 触发制权威刷新（`ProtocolSyncState.events_need_authoritative_refresh`）

| 增量事件 | 是否触发 seq=0 刷新 | 为什么 |
| --- | --- | --- |
| 任意 `tile_discarded` | 是 | 响应窗口（phase/responding_seats）随弃牌开启；本人爆头/动作链/抓打圈状态只在弃牌动作上变化，事件流无对应字段 |
| 任意 `timeout` | 是 | 官方自动代打（自动胡/自动出最右一张/自动弃权）改变的手牌与阶段无法从事件流推导 |
| 本人 `chi`/`peng`/`gang` | 是 | 副露消耗的本人手牌张数与牌面不进入事件流 |
| 本人 `tile_drawn` 缺牌码 | 是 | 畸形事件无法构造 drawn_tile，快照兜底 |
| 他家 `tile_drawn`、`pass`、`round_ended`、`game_ended`、他家副露 | 否 | 不改变本人窗口所需权威事实；round_ended 后的新局由 v10 边界快照覆盖 |

残留的估算级漂移（不影响动作合法性，仅影响牌效估算）：他家副露/摸牌不刷新的间隙内，
`melds`/`hand_counts`/`remaining_tile_count` 保持最后快照值，最多滞后一轮摸牌周期（下一次弃牌即刷新）；
抓打圈结束无事件，`catch_play` 会朝「保守方向」滞后（多限制、不越权），下一次弃牌刷新校正。

### 5.3 跨局边界退避（`game.py`）

- 常量 `_BOUNDARY_STALL_FAST_POLLS=2`、`_BOUNDARY_STALL_BACKOFF_SEC=(0.5, 1.0, 2.0)`。
- 判定：gap 快照吸收后游标未前进（`last_seq <= 吸收前水位`）且无窗口投递 → 计一次边界停滞。
- 前 2 次停滞原速轮询：覆盖庄家常规思考窗口（~1s），保证边界后他家弃牌所开启响应窗口的发现时延不回退；
  此后按表退避（0.5→1.0→2.0s 封顶），同 seq 重复从实测 5~47 次收敛到个位数；任何进度（事件流或快照水位
  前进）立即清零。sleep 走 `retry_sleep` 注入点：假时钟可测、aclose 可取消。
- 同款退避也用于 `pending+gap` 重建后无进度的分支（防御性一致）。

## 6. 量化对比口径（今晚基线 → 修复后预期）

**口径**：对 `participants/{id}/games/*.jsonl` 按 `kind == "protocol_recovered"` 逐场计数；
「重建」= 本表第 3 节中的 `rebuild_snapshot_gap`/`incremental`/`pending_gap`/`conflict_*` trigger。

| 指标 | 今晚基线（实测） | 修复后预期 | 依据 |
| --- | --- | --- | --- |
| 全场 protocol_recovered 总数 | 3063 | ~160-480（仅跨局边界，典型 ~320；有界退避收敛）+ 冲突路径行（另一工作线） | 边界快照每局 1~3 次 × 160 局 |
| 每场（game）均值 | ≈306 | 边界 ~16-48（典型 ~32）+ 冲突路径（另一工作线） | 每场 16 局 × 1~3 |
| 每局边界 `rebuild_snapshot_gap` | 均值 3.3（最严重单边界 47 次） | 1~3（典型 2~3：首事件已发生才首次轮询时恰好 1；首事件未产生时 1 次无进度 + 1 次水位前进；最严重停滞有界 ≤~6） | v10 规则：无进度重复被退避收敛 |
| 正常事件流（非边界）重建 | 每次增量批强制 1 次 seq=0 | **0**（摸牌/过牌增量直达；弃牌/副露为触发制定向刷新，不计入 protocol_recovered） | 5.2 触发表 |
| 胡牌决策路径 | 全部经快照重建路径 | 全部经增量直达（drawn_tile 来自本人摸牌事件） | 5.1 |
| 取消/重连游标回退 | 无（已核对） | 无（回归测试锁定） | 第 4 节路径 4 |

说明：

1. 「个位数」口径：每局边界快照 1~3 次是 v10 规则规定的正常协议行为（该场景的一次快照是正常的）。
   若把**预期内**的边界 gap 快照从 `PROTOCOL_RECOVERED` 改记 `AUTHORITATIVE_STATE`（审计埋点重分类，
   见 §8 建议），每场 `protocol_recovered` 即可降到个位数（仅剩真实异常）。本任务未动该埋点：
   契约词表（interface-contracts.md §7.1）已登记 `rebuild_snapshot_gap` 为恢复 trigger，改动属审计变更评审范畴。
2. `conflict_refresh`（1338）的消除依赖另一工作线（响应窗口身份/anchor_seq 稳定化），本任务不覆盖。

## 7. 回归测试

`tests/adapters/official/test_cursor_discipline.py`（14 例，全绿；整套件 1213 例通过）：

- N=5 次连续本人摸牌增量送达，重建数为 0（传输层零 seq=0、审计零 PROTOCOL_RECOVERED）；
- 轮内轮询取消后重连，游标不回退（轮询 seq 序列断言 + 内部游标断言）；
- v10 跨局边界恰好一次 gap 快照后恢复增量（含「无进度退避有界」变体：假时钟精确验证 0.5/1.0/2.0/2.0 退避）；
- 动作 POST 后游标语义（POST 后轮询沿用最后已消费 seq、不重置 0；本人弃牌事件触发定向刷新后按快照水位继续）；
- 增量摸牌窗口的提交复核（accept + 过期窗口 stale_window 同口径）；
- 本人弃牌触发刷新 → 下次增量摸牌送达时 my_hand 与官方快照一致；
- `events_need_authoritative_refresh` 触发表与 `incremental_draw_window/observation` 状态机单元回归。

## 8. 遗留风险与明确不在范围

- **响应窗口（peng/chi）仍走快照送达**：弃牌触发的定向刷新 + R1 边界定时器机制不变，其 409 风暴属
  另一工作线（响应窗口身份/anchor_seq 稳定化）；本任务只保证游标纪律不再加重该路径。
- **长轮询取消回收的有界化**（另一工作线）：与本次交集仅一处——边界退避 sleep 经 `retry_sleep` 注入，
  `aclose` 取消可穿透，不留悬挂任务；行为上未改动其回收策略。
- **审计埋点建议（未实施）**：预期内的跨局边界 gap 快照改记 `AUTHORITATIVE_STATE`（词表保留 `rebuild_snapshot_gap`
  供真实断链场景使用），可使 `protocol_recovered` 降到每场个位数——需审计契约评审。
- **估算级漂移**（§5.2 尾部）：不影响动作合法性的公开/神位估算字段最多滞后一轮摸牌周期，方向保守；
  已在触发表与代码 docstring 中标注，赛后对拍可复核。
- 快照 `seq` 回退时的「快照即真相」替换语义保持不变（既有受测行为，非本任务路径）。
