# `adapters/recording` 实施说明

## 交付结果

实现不阻塞动作路径的 JSONL 审计、运行汇总和离线验证命令，真实反映记录是否完整。

## MVP 后审计增强（待实施）

实施本次增强时以[审计增强实施方案](../audit-enhancement.md)为准：沿用 `AuditSink`，升级 v2 记录词表，补齐原始协议、实际决策输入、评分、复核与结果；增加共用读取器和证据包归档。线上不增加订阅端口或数据库。

现有下文是 v1 基线。v2 的独有原文通过高优先级 `PROTOCOL_MESSAGE` 保存，不能使用可丢弃的 `RAW_PROTOCOL_STATE`。记录器不负责官方下载、规则检查或统一牌谱转换：下载和官方格式映射在 `adapters/official`，具体转换任务在 `offline`；监控只读同一份记录。

完成目标是跨目录/跨节点检查证据、恢复真实决策输入，并向后续训练和模拟提供数据能力明确的统一牌谱。方案 §3 定义字段，§4 定义归档，§7 定义文件和测试，§8 定义实施顺序；详细结构不在此重复。

## 建议内部结构

```text
adapters/recording/
  jsonl_sink.py  # 有界队列、后台写入和关闭刷新
  schema.py      # 各 AuditKind 的 payload 版本与校验
  redact.py      # Token、Authorization、Cookie 防御性脱敏
  summary.py     # 运行与身份汇总
  validator.py   # intent/outcome、关联键和 JSONL 完整性检查
```

## 优先级

- 高：除 `RAW_PROTOCOL_STATE` 外的第一阶段审计种类，包括规范权威观察、决策计划、提交 intent/outcome、同步恢复和终局。
- 低：`RAW_PROTOCOL_STATE`，即可以由规范权威状态替代的重复原始快照。

优先级由记录器按种类确定，调用方不能自行降级。队列满时优先移除低优先级记录；若无法接收高优先级记录，立刻返回 `audit_degraded=true` 并增加缺失计数。不要为“100% 不丢”阻塞 1 秒动作窗口。

## 完成定义

- 路径包含 `participant_id`，四身份并发无冲突。
- 关闭汇总能区分已写、低优先级丢弃、高优先级缺失和序列化失败。
- 验证器能找到悬空动作尝试、重复键、阶段尝试混用和损坏行。
- 所有故障注入不向调用方抛出写盘异常；认证原文扫描为零。
