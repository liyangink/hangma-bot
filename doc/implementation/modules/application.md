# `application` 实施说明

## 交付结果

实现一个 Token 对应的 `ParticipantRuntime`，监督跨阶段生命周期和最多 `config.M` 个独立场次任务，并在一个动作窗口内完成规则分析、候选排序、复核、提交和审计。

## 建议内部结构

```text
application/
  contracts.py          # 受控端口和消息基线
  participant_runtime.py
  tournament_supervisor.py
  game_task.py
  deadline.py
  decision_loop.py
```

## 核心循环

1. 初始化并核对版本、身份、目标赛事和规则配置。
2. 由赛事状态决定幂等报名/到位；用观察修订号防止陈旧到位命令；以 `active_games` 动态启动或关闭场次任务。
3. 收到 `ObservedActionWindow` 后创建一次预算和 `decision_id`。
4. 先准备紧急候选，再完成完整规则分析和策略排序。
5. 写提交 intent，发送一个 `ActionAttempt`，写 outcome。
6. 仅 `SubmitRejectedRetryable` 进入“排除已拒绝动作 → 原预算重新规划”；其他结果结束旧窗口。
7. 身份淘汰或赛事终态时取消场次并尽力刷新审计。

## 资源和恢复

- 每场一个可取消任务；任务异常只影响该场。HTTP 资源属于端口实现，应用层只管任务和截止时间。
- 简单监督策略使用有限退避和权威重新发现；禁止无上限快速重启。
- `stage_crashed` 关闭旧尝试任务并记录作废；不能把旧提交判断带到新尝试。
- `stage_attempt_id` 由本模块在阶段实际运行尝试开始时生成；不是官方 DTO 字段。
- 排名刷新和非关键工作在资源紧张时让位于动作窗口。

## 完成定义

- Fake 状态机矩阵、明确拒绝循环、模糊提交、刷新不延时和候选耗尽均通过。
- 多场同时窗口没有串行饥饿；单场崩溃不取消其他场。
- 参赛者终态与赛事终态有独立测试。
- 每个动作尝试具备完整审计链。
