# `adapters/official` 实施说明

## 交付结果

实现官方赛事与场次端口（已审查指南 v15，2026-09-05；v8 fixture 历史快照保留）。模块隐藏 Bearer 认证、DTO 转换、限速（state 轮询 16/s 每用户聚合、并发挂起 ≤32）、长轮询、序号恢复（含 v10 跨局 gap=true 快照权威吸收）和动作提交确认（含 `SubmitRejectedNoRefresh`：POST 429 与 409 刷新失败），不参与策略决策。v13 分桌在线过滤对原赛事流程无破坏，OnlineConfirm 进入启动审计。SSE 已随 631c85b 接入运行链路，开关默认关闭，见[集成笔记](../notes/sse-runtime-integration.md)。MVP 后另按[自由赛指南](../free-match-start.md)开发 `/api/match` 入口；该新增模式不能沿用 register/ready，v15 M=10/Rounds=8 对它是实际容量约束，旧入口保持不变。

**响应窗口同步（2026-09-04 实测裁定）**：官方响应阶段固定走满且 peng→chi 切换不产生增量事件——轮询循环在 response 阶段挂边界定时器（窗口秒数+50ms，POLL 优先级）与长轮询竞速捕获切换。响应窗口 `trigger_seq` 必须取**触发弃牌事件**的序号（四级解析：事件流 tile_discarded → 结构化 last_discard.seq → 跨重建触发记忆 → 快照 seq+审计提示退化），不得使用被 pass 推进的快照 seq，否则同一物理窗口分裂为多窗口引发重复提交 409 级联。`pass` 属已知事件类型。实测证据：修复后首次提交的 chi/peng/gang/hu 全部 2xx 接受，409 率从 ~45% 降至 ~3%。

## 建议内部结构

```text
adapters/official/
  participant.py   # TournamentSessionPort
  game.py          # GameSessionPort
  transport.py     # 每 Token 共享 HTTP 连接池
  scheduler.py     # 动作优先的每 Token 调度与限速
  dto.py           # 官方 JSON 解析
  projector.py     # DTO → 内部规范类型的纯转换
  sync_state.py    # 每 game_id 的 seq/快照状态
  action_gate.py   # 每场一个在途 POST 与模糊状态封锁
  errors.py        # 官方错误分类
```

## 请求优先级和恢复

优先级为：动作 POST > 409/缺口/模糊状态确认 > 场次长轮询 > 排名刷新。GET 可在预算内有界重试；POST 不做传输层自动重放。

409 流程固定为：记录明确拒绝 → `GET state?seq=0` 整体替换 → 比较 `WindowKey` 和动作权 → 返回 retryable 或 closed。不得把未经刷新确认的 409 直接变成“请试下一候选”。

未知事件先按版本化分类表判断：确认不影响关键状态的兼容事件可记录并继续；未知关键事件标记同步无效并重建，避免每个无关新增事件触发恢复风暴。

## 2026-09-05 增补语义（E1–E3 接线与游标纪律）

- **原始事件全量保留（E1/E2/E3）**：`_get_state` 每次 HTTP 成功（含坏报文与非 2xx 错误体）发射 `RAW_PROTOCOL_STATE` 原文记录（非 2xx 分支 request_no 不递增）；动作提交全部分支（成功/409/429/4xx/5xx/结果不确定）经 `errors.raw_text`（传输层已脱敏原文）发射，POST 结果不确定时省略 `http_status`、`raw` 为空串。词表与对账检查见接口协议 §7.1。
- **游标纪律**：游标恒为"本地已消费的最后一个事件 seq"；本人摸牌窗口由增量事件直达（不再逐批 seq=0 刷新），快照刷新仅在弃牌/timeout/本人副露/缺牌码摸牌/跨局边界/失步重建时触发；跨局边界无进度 gap 快照按 2 次原速 + 指数退避（封顶 1.0s）轮询。量化口径见 doc/implementation/notes/cursor-discipline.md。
- **Retry-After 防冻**：传输层 429 解析只接受有限非负秒数（inf/nan/负值按未提供处理），调度器 `note_rate_limited` 第二道 isfinite 防御——畸形头不再冻结整个 Token（W2-1）。
- **SSE notify 运行链路**已接入：水位通知唤醒 /state，静默短拉与有界长轮询降级共存，复用原窗口预算。实际验收和仍缺 closed:true 终态样本的边界见[后续验收](../reviews/adapter-wave-verification-2026-09-05.md)。

## 完成定义

- 保存的 v8 fixture、v15 指南快照和官方测试房间通过。
- 一个 Token 的赛事/场次共享连接池和限速器，四 Token 完全隔离。
- 非幂等提交所有分支符合封闭结果契约。
- 关闭能取消长轮询；401、版本不兼容和目标错配形成永久终态。
- TLS 关闭仅限显式允许的固定内网主机，所有输出完成认证信息脱敏。

## 2026-09-06 观察完整性修订

当前两个生产组合根固定 state-only；先前 SSE 可选运行说明保留为历史，低层 notify 客户端不参与本次生产路径。同步与提交共用 `current_observation`，保留当前单局已收到的可见历史；增量只应用快照之后的事件。未知关键事件每次都需恢复，同序号载荷冲突不当幂等重复；恢复后的缺史状态明确保留。

活动态 god 必须按真实类型提供；空值不能默认关闭。事件保留吃组合、杠/超时类别，无牌 pass/终局正常解析。所有人的副露及无法完整推出的响应事实仍查询快照；本人摸牌在前态完整时由 hangma 按旧爆头和补牌来源推进，来源未知且影响结果时恢复权威快照。简单 god 转移核验输出审计，抓打圈范围仍 not_checked。窗口缓存单调截止并只收紧；poll 与 timer 同时完成时优先保留已返回权威数据。

同日 v18 限流核对：`RequestKind.STATE` 在同 Token 下严格共享滚动 16 次/秒，长轮询、快照恢复、补史都计次；`OTHER` 不扣 state 额度。资源可用的请求按优先级及先后顺序授予；动作不被 state 额度等待者阻塞。全部请求共享并发槽和 429 冷却，无有效 Retry-After 时至少等待 1 秒再加抖动。`match` 保留独立 10 次/分钟限制，SSE 保留独立连接预算。依据及现场五次超频证据见[限流评审](../../../review/official-adapter/chain-rate-alignment/rate-runtime-review.md)。

验收策略、独立评审和剩余官方验证事项见 [修复策略](../../../review/official-adapter/repair-plan-2026-09-06.md)；新增字段和未知值语义见 [接口增补](../interface-contracts.md#观察完整性与截止契约增补2026-09-06)。

### 同日实测补充：事件不能被快照水位吞掉

旧“游标恒为最后逐条消费事件”的描述不足以代表实现：权威快照也会推进状态水位，但不提供相同序号范围的全部原事件。现在同单局快照超前时，先按旧水位有界补领一次（100 毫秒、保留 350 毫秒动作余量、跨度最多 256）；失败不循环追赶，标记历史不完整。附带事件与快照一起处理，快照前事件仅补历史，收到的更晚事件缓冲后优先处理；409 恢复遇到这种缓冲则不允许旧窗口重试。

实测他家 `tile_drawn` 的牌值为空，这是正常脱敏，保留事件并更新公开张数和摸牌阶段。`catch_play/gang_replenish/timeout.window` 与终局公开结算进入规范字段。碰阶段 `Pass` 返回未发送，等待真实吃阶段；不是本地强行切换阶段。牌谱摘要与对应终局冲突时拒绝转换。上述修改的字段权限、兼容性及待实测边界统一见[接口契约](../interface-contracts.md#实测事件与恢复契约增补2026-09-06)。

## 延后补史执行约束（2026-09-06）

`ProtocolSyncState.history_missing_ranges()` 按已证明起点与快照水位计算缺失闭区间；`merge_history(events, round_no=...)` 只补同手旧历史，整批校验后提交。未知前缀独立表示。空牌值他家摸牌合法，非空私有牌不允许通过补史进入观察。

`OfficialGameSession` 在next_item原循环中协调有界补领和三次退避，复用调度器，不创建独立任务。未提交、可重试和模糊动作优先；未来权威响应优先正常推进；同点快照不销账。收尾使用现有AUTHORITATIVE_STATE高优先级记录，旧手封存不依赖后续策略动作。字段、预算和不可恢复边界统一见[接口契约](../interface-contracts.md#延后补史与单局收尾契约2026-09-06)。


### 单局封存完整性补充（2026-09-06）

`history_closure.closure_issues` 记录附带旧尾中的未知事件、关键字段缺失、违规他家摸牌，以及未收到 `round_ended` / 场次终态未收到 `game_ended` 的原因。封存 `history_complete=true` 除要求起点、序号及原有观察完整外，还要求这些原因为空。`missing_ranges` 仅覆盖已知 `history_through_seq`，缺少更晚的尾事件不能只靠此区间表判断；不从积分或新快照捏造终局事件。该检查只影响赛后封存，不重新推进牌面、创建动作窗口或改变策略输入。

## M=4 实测修订（2026-09-07，覆盖此前共享冷却说明）

state 429现在只冷却STATE，其他端点429保守全局冷却；正式赛事、测试房与自由赛生产入口均采用14次/秒、burst=1，保持官方16次/秒以内的余量。未获许可的补史不消耗三次网络尝试，终态同单局快照也进行一次有界尾事件补领，终态不可重开。不新增后台任务或外部端口。

原始响应中的可选request_timing记录排队、许可、传输开始与完成时间，以及state 429有效Retry-After。时间均为进程内单调时钟秒。详见[契约增补](../interface-contracts.md#m4-调度与审计兼容增补2026-09-07)和[修复证据](../../../review/official-adapter/m4-live-2026-09-07/repair.md)。
