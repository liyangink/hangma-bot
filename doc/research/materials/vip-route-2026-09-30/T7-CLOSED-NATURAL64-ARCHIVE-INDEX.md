# T7自然64桌完整原件封包

**64桌全部原件已逐成员封包和读回验签。** 本地原目录保持原位、原字节，不搬移、不删除。Git保存四个分块、逐件清单、首封收据与独立审核，避免再提交389MB原目录；封包不是强度或发布证据。

| 项目 | 封存结果 |
| --- | --- |
| 原件 | 128文件、389303717字节，覆盖两池64完整桌、动作链、四座结算、配对费用和实际代码快照 |
| 压缩归档 | 115455112字节，SHA256 `eb400419dc2494bb8583cb66ab8d40eba202f23c82e522ff746a7759daca5625` |
| Git分块 | 4块，各块不超过33554432字节 |
| 分块索引 | [chunk-index.json](./evidence/t7-natural-purpose-scale-1/closed-natural64-evidence-archive/S01/chunk-index.json)，SHA256 `ef0f754d81601095c1880f8c020400cdc6ab1bb4031b0df7e7d24e4447d957fc` |
| 来源清单 | [archive-manifest.json](./evidence/t7-natural-purpose-scale-1/closed-natural64-evidence-archive/S01/archive-manifest.json)，SHA256 `6e695e55280b69055a5a1ab7e069c14268f446515b93af23a4f1efb3e4a0c981` |
| 原件首封 | [RAW-RESULT-SEAL.json](./evidence/t7-natural-purpose-scale-1/S01-research-600k/natural-development-raw-seal/RAW-RESULT-SEAL.json)，SHA256 `9ac07feaf40488e518d72004e07fd3df1997be537f750adc68beb65e62c48543` |

[独立全链审核](./evidence/t7-natural-purpose-scale-1/S01-research-600k/natural-independent-review/REVIEW.md)已经闭合。H/M平均桌差为−17.0625/−21.625，合并−19.34375；无新上线资格。正负桌、四换座、失败历史均保持原分母。封存过程模型、候选评分、规则、世界推进及新增桌实例调用均0。

## 在新检出中验签或恢复

仓库根运行以下命令。`verify`只读全块及每个原件；`restore`先核成员及现有冲突，仅恢复缺件，拒绝覆盖不同字节，不执行候选或模拟。

```bash
.venv/bin/python review/vip-route-2026-09-30/evidence/t6-absolute-route-credit-1/closed-opportunity-evaluation-archive/archive_chunks.py verify --index review/vip-route-2026-09-30/evidence/t7-natural-purpose-scale-1/closed-natural64-evidence-archive/S01/chunk-index.json --index-sha256 ef0f754d81601095c1880f8c020400cdc6ab1bb4031b0df7e7d24e4447d957fc --repo .
.venv/bin/python review/vip-route-2026-09-30/evidence/t6-absolute-route-credit-1/closed-opportunity-evaluation-archive/archive_chunks.py restore --index review/vip-route-2026-09-30/evidence/t7-natural-purpose-scale-1/closed-natural64-evidence-archive/S01/chunk-index.json --index-sha256 ef0f754d81601095c1880f8c020400cdc6ab1bb4031b0df7e7d24e4447d957fc --repo .
```

复用此前已封的分块/恢复工具；旧schema前缀不追改，实际T7来源以清单`source_relative_to_repo`为准。临时完整tar位于仓库外，Git只保存四块。全包首尾来源一致，首次build、split及独立的verify都已核完128成员；不删除集中负差，也不把归档成功写成算法成功。
