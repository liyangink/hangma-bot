# `adapters/official` 实施说明

## 交付结果

实现官方 v8 的赛事与场次端口。模块隐藏 Bearer 认证、DTO 转换、限速、长轮询、序号恢复和动作提交确认，不参与策略决策。

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

- 保存的 v8 fixture 和官方测试房间通过。
- 一个 Token 的赛事/场次共享连接池和限速器，四 Token 完全隔离。
- 非幂等提交所有分支符合封闭结果契约。
- 关闭能取消长轮询；401、版本不兼容和目标错配形成永久终态。
- TLS 关闭仅限显式允许的固定内网主机，所有输出完成认证信息脱敏。

