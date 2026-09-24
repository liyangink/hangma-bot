# SSE 帧驱动运行链路集成（2026-09-05）

> 以下是 2026-09-05 初次接入时的历史设计，含当时的短拉增量、5 秒静默钟与长轮询降级，均非现行行为。现行 SSE 验证模式对需读取的帧和本人动作自唤醒直接取一笔 `seq=0` 权威快照，使用 2 秒静默／5 秒权威状态双保底、局间 5.25 秒探针；流失败上交故障，不在同场回退长轮询。见[当前适配器说明](../modules/official-adapter.md)。

> 状态：已接入，**配置默认关闭**（`sse_enabled: false`）；默认关闭时运行行为与接入前逐字节一致（既有全套件回归保证）。

## 集成契约

- **配置开关**：`RuntimeConfig.sse_enabled`（run config JSON 键 `sse_enabled`，布尔，默认 false）；测试房间配置同名键经 `run_test_room.py` 透传至每身份子进程。
- **预算模型**：每 Token 一个 `StreamBudget`（组合根创建，默认 24 / 官方上限 32），M 场各持 1 流共享该预算；预算不足时客户端返回 `BUDGET_UNAVAILABLE` → 按降级处理。
- **帧驱动路径**（开关开启且流健康）：
  - 帧到达 → `asyncio.Event` 唤醒 → **短拉增量**（`GET /state?seq=本地已消费游标`，游标纪律与长轮询路径完全一致）；
  - 静默超时（无帧 `_SSE_IDLE_POLL_SEC=5s`）→ 短拉对齐水位（防帧丢失漂移）；
  - 响应阶段边界超时（官方 `window_deadline_ms` 绝对截止推导）→ 对齐边界定时器语义：主动 `seq=0` 权威刷新（普通优先级，不挤占动作/紧急通道）。
- **回退梯子（有界）**：SSE 流终局（`RECONNECTS_EXHAUSTED`/`BUDGET_UNAVAILABLE`/`TERMINAL`/客户端异常）→ 本会话**永久降级**回既有长轮询路径 + `PROTOCOL_RECOVERED{trigger: sse_degraded}` 审计；不自动重开（重开交给监督层重建会话的自然路径）。等待中的帧通道被立即唤醒并走降级回退。
- **生命周期**：SSE 任务懒启动（首次 `next_item`），登记 `_active_tasks` → `aclose()` 统一取消；预算槽归还由 notify 客户端全出口保证（S1 测试锁定）。SSE 任务任何异常不得传播进 `next_item` 主流程。

## 与既有机制的协同

- 边界定时器保留（权威 deadline 驱动）作为帧通道静默时的兜底；
- 重复提交根治（F1–F4）与帧驱动正交：投递守卫/已表态抑制/409 吸收在两条拉取路径下同样生效。

## 已知取舍与遗留

- **帧粒度唤醒**：帧只携带全局水位（含他家私有事件如摸牌的推进）→ 每帧一次短拉可能出现"拉回 pending"（无我方事件）；M=2 实测流量可忽略，M=10+ 如需优化可加最小唤醒间隔或按游标差过滤。
- `closed:true` 终止帧的活场样本待补（接入后首个场终随手捕获，验证 `STREAM_ENDED` 路径）。
- 官方 `Retry-After` 畸形值防护（W2-1 双层）在 SSE 路径同样生效（传输层共用分类）。

## 测试

`tests/adapters/official/test_sse_runtime.py`：帧驱动短拉投递、流终局降级回长轮询 + `sse_degraded` 审计、aclose 无悬挂任务；默认关闭的行为一致性由既有全套件保证。
