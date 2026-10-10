# 首候选解释的直接字段核验

本目录公开实际首trace／生产日志补充使用的纯字段检查与十项回归。它比较同一次策略内层返回和审计封装返回的生产codec字典，只允许首候选新增受控摘要与实验身份，其余计划和解释保持原值。[实际十次核验](../../../../doc/research/astra-evolution-20261010/WHITE-CIRCLE.md)已覆盖冻结470b／613e的编码、脱敏、写出和关闭；本目录不启动策略、世界、日志线程或平台任务。

`RankedCandidate.score_trace`不参与dataclass相等比较。计划相等只能说明既定核心字段，不能证明解释存在或日志已写出。`checks.inspect`直接检查首候选的`bounded_runtime_audit`、`policy_release`、实际候选／执行摘要、原发布字段及其他trace；返回`trace_ok`和具体缺失／差异清单。`checks.core`只移除逐候选trace，其余完整codec字段逐值比较。

调用方必须先按生产codec验证输入，候选和执行摘要来自实际组合根装配核验，不能只传回期望字符串。本工具不替代规则、合法动作、预算、日志写出或完整应用回归；字段通过也不构成强度或发布资格。当前摘要schema对应冻结开圈候选，复用到其他候选前须明确其解释契约。

```bash
.venv/bin/python -m unittest discover -s tools/research/astra-evolution-2026-10-10/trace_stage160 -p fake_tests.py -v
```

回归包括合法增量、compare=False歧义、缺失、错误身份、丢失原发布字段、核心变化、错误原因、范围外trace变化和布尔类型误用。它们只使用标准库假字段，不代替真实选择或生产日志证据。两份源码与已动态验证的私有方法逐字节相等；私有输入、身份清单及实际JSONL不入Git，当前效果评估的冻结来源保持原字节。
