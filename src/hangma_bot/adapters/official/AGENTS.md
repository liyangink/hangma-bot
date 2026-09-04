# `adapters/official` 模块实施规范

## 目标与边界

本模块实现 `TournamentSessionPort` 与 `GameSessionPort`，隐藏官方 HTTP、DTO、长轮询、序号恢复和非幂等动作状态。先阅读根规范、官方 API v8 记录、接口协议和 `doc/implementation/modules/official-adapter.md`。

- 每 Token 恰好创建一个 `OfficialTransport`、连接池、请求调度器和限速器；该 Token 的赛事及最多 `M` 个场次共享它们。
- 四个测试 Token 之间不得共享认证头、限速状态、动作门或审计身份。
- 适配器只输出 `ObservedActionWindow`，只接收 `ActionAttempt`；禁止导入 `DecisionRequest`、`DecisionPlan` 或启发式评分类型。
- `StageIdentity.observed_revision` 只用于防止陈旧 `ready` 调用；应用层审计使用的 `stage_attempt_id` 不由适配器生成。
- `ActionGate` 和 `ProtocolSyncState` 是每场内部状态机，不暴露给应用层。
- 只支持配置中固定的官方内网主机关闭 TLS 校验，禁止全局关闭。
- Token 可由私有运行配置集中加载，但不得进入源码、fixture、异常文本或日志；所有 `Authorization` 必须脱敏。

## 同步和提交语义

- 重复 `seq` 幂等忽略；缺口、`gap=true`、未知关键事件和 409 使用 `seq=0` 权威快照整体重建。
- 未知但确认可忽略的兼容事件只记录，不触发重建风暴；未知关键事件才阻断并重建。
- GET 超时、可恢复 5xx 和 429 允许有界重试；动作 POST 不自动重放。
- 409 先确认官方已拒绝，再全量刷新：同一 `WindowKey` 仍需行动才返回 `SubmitRejectedRetryable`；窗口关闭则返回 `SubmitRejectedClosed`。
- POST 超时、断连或无法确定是否执行的响应返回 `SubmitAmbiguous`。相同 `WindowKey` 不得再次变为可提交状态，直到权威事件证明窗口已经迁移。
- POST 发出前检查 `latest_send_at_monotonic`；超过即返回 `SubmitNotSent`。
- 认证、授权或不可恢复协议错误返回 `ParticipantTerminal`/`SubmitFatal`，不得伪装成可重试网络故障。

## 验收标准

- 官方 v8 保存响应 fixture 全部解析；允许兼容新增字段但拒绝未知破坏性指南版本。
- 每 Token 请求共享与四 Token 隔离均有并发测试。
- 覆盖 `seq` 重复/缺口、`gap=true`、兼容未知事件、关键未知事件、409、429、401、超时和断连。
- 任意时刻每场最多一个在途 POST；模糊结果后同窗零次追加提交。
- `aclose()` 能取消最长 30 秒长轮询且不误关同 Token 的其他场次。
- 状态投影测试证明官方 DTO 不泄漏他家手牌或未来信息。
