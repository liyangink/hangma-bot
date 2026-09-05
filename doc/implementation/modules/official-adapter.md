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
