# `adapters/recording` 实施说明

## 交付结果

实现不阻塞动作路径的 JSONL 审计、运行汇总和离线验证命令，真实反映记录是否完整。

## MVP 后审计增强（待实施）

实施本次增强时以[审计增强实施方案](../audit-enhancement.md)为准：沿用 `AuditSink`、v1 信封和现有 raw 留存，以 audit-plus-v1 profile 补齐完整决策输入、评分、复核与终结证据；增加共用读取器和证据包归档。线上不增加订阅端口或数据库。

下文是已实现 v1 基线。独有原文继续通过低优先级 `RAW_PROTOCOL_STATE` 全量留存，背压丢失如实计数；本批不增加第二套协议记录。记录器不负责官方下载、规则检查或统一牌谱转换：下载和官方格式映射在 `adapters/official`，具体转换任务在 `offline`；监控只读同一份记录。

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
- 低：`RAW_PROTOCOL_STATE`（2026-09-05 语义修订，F-20）：不再是"可由权威状态替代的重复快照"，而是 adapter 层协议原文的**全量保留存证**（/state 响应、动作提交响应与 409/429 拒绝体，含坏报文），路由到按场分文件的 `raw/*.jsonl`（可选 gzip 分段，只分段不抽样）；它是背压下的最后一层（可计数丢弃并以 `raw_retention` 汇总诚实声明），规范权威信息仍须以 `AUTHORITATIVE_STATE` 高优先级另存。严格对账检查（`raw_state_gap`/`raw_state_stream_empty`/`raw_action_missing`）在收到新形态原始事件后才启用（auto-evidence 门控）。

优先级由记录器按种类确定，调用方不能自行降级。队列满时优先移除低优先级记录；若无法接收高优先级记录，立刻返回 `audit_degraded=true` 并增加缺失计数。不要为“100% 不丢”阻塞 1 秒动作窗口。

## 完成定义

- 路径包含 `participant_id`，四身份并发无冲突。
- 关闭汇总能区分已写、低优先级丢弃、高优先级缺失和序列化失败。
- 验证器能找到悬空动作尝试、重复键、阶段尝试混用和损坏行。
- 所有故障注入不向调用方抛出写盘异常；认证原文扫描为零。

## 2026-09-07 汇总口径修正

`validate_run` 将动作尝试数与原始记录条数分开，规则降级以当时决策输入为准。修正依据是测试房 `t_b684d5c3eea4` 的真实双层记录：一次成功动作曾统计为两次，完整规则输入中的旧策略兼容提示曾被统计为规则降级。原始信封和已封存报告不变；重新生成的报告以 `submissions.counting_basis="attempt-v2"` 标识新口径。

### 提交统计

动作尝试按 `run_id/tournament_id/participant_id/game_id/decision_id/attempt_no` 归并。`stage_attempt_id` 为空是适配器的正常生产形态，不参与归并键；同场不同非空阶段尝试仍由既有混用检查报告。旧日志缺 `game_id` 时使用空作用域，不能与明确场次配对。分位时延仍取同次尝试的最早意图到最晚结果，单位为毫秒，基准为信封中的 Unix 时间。

| 输出字段（均位于 `submissions`） | 口径与可空条件 |
| --- | --- |
| `intents` / `outcomes` | 成功解析的原始意图/结果记录条数，包含无法关联的记录；双层记录各占一条 |
| `distinct_attempts` | 意图与结果关联键的并集大小，包括只有意图或只有结果的尝试；旧实现只数有意图的键 |
| `attempts_with_intent` / `attempts_with_outcome` / `paired_attempts` | 分别为有意图、有结果、两者齐备的尝试数，不因双层记录翻倍 |
| `uncorrelatable_intent_records` / `uncorrelatable_outcome_records` | 缺合法决策号或尝试号的条数；对应违规仍然报告，不将这些记录计入尝试直方图 |
| `outcome_histogram` | 按尝试归并的规范结果词表；未知结果值保留，缺结果字段为 `missing_outcome`，矛盾结果单列 `conflicting_outcome` |
| `outcome_record_histogram` | 按原始记录统计同一规范词表；用于核对双层记录及历史旧口径 |
| `official_code_histogram` / `official_code_record_histogram` | 分别按无冲突尝试、原始记录统计有明确字符串值的 `official_code`；未提供不计数 |
| `rejected_total` / `ambiguous` / `not_sent` / `not_sent_timeouts` | 按无冲突尝试计数；拒绝含三类 `rejected_*`，未发送超时仍依据原因中的 `deadline` / `timeout`，不把网络结果不确定算成未发送 |
| `conflicting_attempts` / `conflicts` | 矛盾尝试总数及全部定位；每项含稳定 `context`、矛盾 `fields` 和所有结果 `records` 的文件/行号、来源、分类与官方码 |
| `latency_ms` | 配对尝试的 P50/P95/P99/max；没有非负时延样本时分位数和最大值为 `null` |

同次尝试的规范结果、官方码、原因、拒绝动作或共同序号不一致时，报告 `submission_outcome_conflict` 违规，该尝试不进入成功/拒绝等常规结果或官方码统计。可选字段仅一层提供不算矛盾；历史序号整数 `12` 与字符串 `"12"` 视作相同事实。单条记录同时提供互相冲突的 `outcome` / `outcome_type` 也会被检出，不按字段优先级任选结果。原始记录条数和定位始终保留。

### 规则输入与计划提示

规则统计按上述决策作用域去掉 `attempt_no` 后归并；同一决策的多个重规划版本只计一次。任一输入明确 `completeness="degraded"` 时记一次受规则降级影响的决策，即使后续版本恢复完整。否则，所有输入都具备一致、合法的规则完整性和问题列表才记完整；缺输入或输入无效均为未知。输入只用于统计已记录事实，不在验证器内重新运行规则算法。

| 输出字段（均位于 `coverage`） | 口径 |
| --- | --- |
| `decisions_planned` | 按运行、赛事、身份、场次、决策号去重的计划数 |
| `rule_degradations` / `rule_degradation_decisions` | 由真实规则输入确认的降级决策数 / 最多20个决策号兼容样本；完整定位用下方 examples |
| `rule_analysis.basis` | 固定为 `decision_input.request.rules`，声明证据来源 |
| `rule_analysis.input_records` / `input_decisions` / `uncorrelatable_input_records` | 原始输入条数 / 可关联的输入决策数 / 缺决策号的原始输入条数 |
| `rule_analysis.complete_decisions` / `degraded_decisions` / `unknown_decisions` | 输入或计划覆盖到的可关联决策划分，三项互斥；缺输入决策不能作为已知完整或降级 |
| `rule_analysis.missing_input_decisions` / `invalid_input_decisions` | 缺输入 / 存在无效输入的决策数。明确降级与其他无效重规划输入可以共存，因此后者可能与 `degraded_decisions` 重叠 |
| `rule_analysis.issue_area_histogram` | 规则输入 `issues` 中各 `area` 涉及的决策数，同一决策内同类问题及重复输入只计一次 |
| `rule_analysis.degradation_examples` / `unknown_examples` | 各最多20项稳定上下文；降级样本含去重问题清单与输入原文位置，未知样本说明缺输入或输入无效 |
| `plan_diagnostics.legacy_degraded_reason_records` | 原旧实现按非空 `decision_planned.degraded_reasons` 累计的原始条数，仅用于历史口径对照 |
| `plan_diagnostics.hint_decisions` / `compatibility_hint_decisions` / `other_hint_decisions` | 有计划提示 / 含已知 `legacy-pass-neutral` 兼容说明 / 含其他提示的决策数；后两者可以重叠 |
| `plan_diagnostics.legacy_hint_decisions` / `legacy_rule_completeness_histogram` | 缺规则输入时仍有提示的决策数 / 旧计划中明确声明的 `rule_completeness` 值；直方图按决策与值去重，多版本值不同会进入多个桶，缺字段记 `unknown` |

`degraded_reasons` 是混合文案字段，其他提示不必然证明策略失败，不能再把它当成规则降级或凭文案追认旧运行。旧日志的完整性判定维持原门控；这里只诚实披露未知覆盖，不因历史没有增强输入而新增违规。
