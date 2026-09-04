# ADR-0001：冻结第一阶段模块接缝与提交语义

> 状态：已接受  
> 日期：2026-09-03

## 背景

多个实施 Agent 将分别开发规则、策略、运行编排、官方协议和审计。如果官方适配器直接构造策略请求，或各模块分别理解 409、超时和重试，就会在 1 秒/3 秒窗口中产生不一致行为。另一方面，第一阶段只有一个月，不适合为尚未实现的训练和模拟系统预建通用框架。

## 决策

1. 第一阶段只实现 `kernel`、`hangma`、`policy`、`application`、`adapters/official` 和 `adapters/recording`。
2. 只冻结 `TournamentSessionPort`、`GameSessionPort`、`BotPolicy` 和 `AuditSink` 四个可替换接缝。
3. `HangmaRules` 是唯一具体深模块；第一阶段即覆盖完整动作族，内部允许显式降级并保留独立紧急路径。
4. 官方适配器输出 `ObservedActionWindow`，应用层组装 `RuleAnalysis`、`DecisionRequest` 和预算；适配器只接收 `ActionAttempt`。
5. 提交安全不变量是“同一场任意时刻最多一个在途 POST”。明确 409 且刷新确认同窗仍开放时，可以在原预算内排除已拒绝动作并尝试下一候选；结果不确定时封锁同窗。
6. 一个 Token 对应一个 `ParticipantRuntime` 和一套共享传输/限速资源；测试房间四 Token 使用四个隔离进程。
7. 审计路径包含 `participant_id`；关键动作信封缺失时必须标记 `audit_degraded`。

## 被否决方案

- 通用事件总线和工作流引擎：增加事件版本、投递和恢复复杂度，第一阶段没有第二个真实消费者。
- 让 `GameSessionPort` 返回 `DecisionRequest`：会把规则和策略输入组装职责泄漏给协议层。
- 整个窗口严格只尝试一次：无法在本地规则与官方存在差异、且官方明确拒绝时安全降级。
- 网络错误自动重试动作 POST：服务端可能已执行，存在重复动作风险。
- 同进程运行四个测试身份：会引入不必要的多租户隔离和共享资源问题；四进程更接近正式单身份路径。
- 第一阶段创建模拟、模型和复杂赛事效用接缝：没有两个真实实现，且会分散 P0 稳定性投入。

## 结果

模块 Agent 可以使用 Fake 独立测试；官方协议变化局限在适配器；规则差异通过封闭提交结果安全反馈给应用层。代价是第一阶段不提供统一事件存储、线上模型热切换或本地完整模拟，这些能力必须在 MVP 门禁通过后另行设计。

公开契约见[第一阶段接口协议](../implementation/interface-contracts.md)，验收见[第一阶段 MVP 验收标准](../implementation/mvp-acceptance.md)。

