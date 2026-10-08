# T6 两份完整开发桌的封包索引

**两份32桌自然开发已闭合；完整原件以可逐成员复核的封包保存。**本地原目录保持原位、原字节，不搬移、不删除；Git保存封包、清单、首开收据、复算程序和报告，避免再次同时提交大体积原目录及其封包。当前结果见[T6阶段取舍](./T6-FOUR-SLOT-MECHANICAL-RESULT-AND-NEXT.md)，封包不是强度或发布证明。

| 候选 | 完整原件 | 封包字节数 | 封包SHA256 |
| --- | --- | ---: | --- |
| S01 | 112文件、206107112字节 | 66099283 | `0bcd7fcd1844b9a62a9e10716e20e6dfaffe370b3fd9fb88bc9529eb48113eda` |
| S02 | 112文件、217976894字节 | 71687538 | `a591f77d9187f3c76b7ac52a189fea3911bbb8df3d4184d654d1909381227e43` |

[总索引](./evidence/t6-absolute-route-credit-1/closed-natural-evidence-archive/ROOT-ARCHIVE-INDEX.json)绑定两份清单及复核程序；[S01清单](./evidence/t6-absolute-route-credit-1/closed-natural-evidence-archive/S01/archive-manifest.json)、[S02清单](./evidence/t6-absolute-route-credit-1/closed-natural-evidence-archive/S02/archive-manifest.json)记录每个原路径、长度和摘要。封包包含两池全部动作链、观察、结算、配对结果、费用和实际运行代码快照；没有删除负桌、失败分母或换座映射。两包均已逐成员读回核验，封存期间来源前后完全一致，新增候选评分、模型、世界推进和桌实例均0。

## 在新检出中复核与恢复

在仓库根运行以下命令。`verify`只检查封包和已有原件；缺件数允许非零。`restore`先检查全部成员及已有目标，再恢复缺件，拒绝覆盖不同字节；不会执行候选或模拟。

```bash
.venv/bin/python review/vip-route-2026-09-30/evidence/t6-absolute-route-credit-1/closed-natural-evidence-archive/restore_or_verify.py verify S01 --repo .
.venv/bin/python review/vip-route-2026-09-30/evidence/t6-absolute-route-credit-1/closed-natural-evidence-archive/restore_or_verify.py restore S01 --repo .
.venv/bin/python review/vip-route-2026-09-30/evidence/t6-absolute-route-credit-1/closed-natural-evidence-archive/restore_or_verify.py restore S02 --repo .
```

封存复用[上一批已核验的工具](./evidence/t5-joint-formula-batch-1/closed-evidence-archive/seal_directory.py)，其历史schema前缀保持不变，实际本批来源由每份`source_relative_to_repo`明确标识。[恢复程序](./evidence/t6-absolute-route-credit-1/closed-natural-evidence-archive/restore_or_verify.py)不追改冻结计划中的原运行路径。复算报告及原运行绑定保留各自原身份，不能通过换路径或改变规则把历史成绩赋给新候选。
