# `adapters/recording` 模块实施规范

## 目标与边界

本模块实现 `AuditSink`、运行汇总与审计验证器。先阅读根规范、`doc/implementation/interface-contracts.md`、`doc/implementation/mvp-acceptance.md` 和 `doc/implementation/modules/recording.md`。

- `emit()` 必须立即返回且永不向动作路径抛异常；磁盘写入在有界后台队列完成。
- `emit()` 返回前把只含 JSON 值的信封同步复制/编码到队列所有权，调用方后续修改对象不能改变已入队记录。
- 记录优先级由本模块按 `AuditKind` 固定，调用方不能自行降级。除 `RAW_PROTOCOL_STATE` 外的第一阶段种类均为高优先级；提交 intent/outcome 不得被设计为正常丢弃，任何缺失必须标记 `audit_degraded`。
- 低优先级 `RAW_PROTOCOL_STATE` 可在队列压力下计数丢弃；动作窗口使用的规范权威状态仍必须以 `AUTHORITATIVE_STATE` 高优先级保存。
- 路径必须包含参赛身份：`runs/{run_id}/participants/{participant_id}/games/{game_id}.jsonl`。
- Token、`Authorization` 和可还原 Token 的原文不得写入任何文件，记录端还要做第二次防御性脱敏。
- 本模块只记录事实，不决定动作、重试、退出或晋级。

## 验收标准

- 四身份出现相同 `game_id` 时无文件冲突或串写。
- `decision_id + attempt_no` 唯一定位每次动作尝试；intent/outcome 成对，进程中断时明确标悬空。
- 队列满、磁盘慢/满、序列化失败和关闭超时均不阻塞动作，且进入汇总计数。
- 验证器报告覆盖率、规则降级、409、模糊提交、动作超时和 P50/P95/P99 时延。
- 脱敏性质测试和损坏 JSONL 恢复测试通过。
