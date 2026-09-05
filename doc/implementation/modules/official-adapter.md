# `adapters/official` 实施说明

## 交付结果

实现官方赛事与场次端口（已审查指南 v14，2026-09-05；v8 fixture 历史快照保留）。模块隐藏 Bearer 认证、DTO 转换、限速（state 轮询 16/s 每用户聚合、并发挂起 ≤32）、长轮询、序号恢复（含 v10 跨局 gap=true 快照权威吸收）和动作提交确认（含 `SubmitRejectedNoRefresh`：POST 429 与 409 刷新失败），不参与策略决策。v13 分桌在线过滤对玩家 API 无破坏（`register→ready` 不变、空转期 2s 轮询满足 90s 在线要求），`OnlineConfirm` 键解析后进启动审计；v12 SSE 通知流为可选能力，本阶段不采纳（评审见 `doc/official-platform-api-v2.md` §2.3）。

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

## 完成定义

- 保存的 v8 fixture、v14 指南快照和官方测试房间通过。
- 一个 Token 的赛事/场次共享连接池和限速器，四 Token 完全隔离。
- 非幂等提交所有分支符合封闭结果契约。
- 关闭能取消长轮询；401、版本不兼容和目标错配形成永久终态。
- TLS 关闭仅限显式允许的固定内网主机，所有输出完成认证信息脱敏。

