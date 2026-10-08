# T8 两份自然64桌完整原件封包

**两份完整桌原件已逐成员封包、分块并读回验签。** 本地原目录保留原位原字节；Git只保存分块、清单、根首封及独立审计，避免直接提交约771MB原目录。封存通过不表示算法增强。

| 项目 | S01F | S02 |
| --- | --- | --- |
| 原件数量 | 129 | 129 |
| 原件字节 | 385984558 | 385335949 |
| 压缩归档字节 | 117793225 | 117778312 |
| 分块数量 | 4 | 4 |
| 分块索引SHA256 | `10ab71a6221997f83639479cff26a042659d3fe2d6645cbfb81e8e08243cc99b` | `aa57912b5626b2d6d708a0323d1c7b42e8db02af4629bceea3f09aed401873d6` |

每块不超过32MiB。[S01F索引](./evidence/t8-bounded-natural-geometry-1/closed-natural64-evidence-archive/S01F/chunk-index.json)和[S02索引](./evidence/t8-bounded-natural-geometry-1/closed-natural64-evidence-archive/S02/chunk-index.json)绑定压缩归档摘要和逐件来源清单。[根对账](./evidence/t8-bounded-natural-geometry-1/closed-natural64-evidence-archive/ROOT-FIRST-SEAL-EQUALITY.json)确认两个清单的成员及原字节恰等于各自效果首开前的129件首封；没有删除负桌、动作链、费用或源码快照。

## 新检出中验证或恢复

复用已封的分块工具。`verify`核全部块及每个归档成员；`restore`仅补缺件并拒绝覆盖不同字节，不评分或推进牌局。以下示例是S01F，S02换成上表的目录和索引摘要。

```bash
.venv/bin/python review/vip-route-2026-09-30/evidence/t6-absolute-route-credit-1/closed-opportunity-evaluation-archive/archive_chunks.py verify --index review/vip-route-2026-09-30/evidence/t8-bounded-natural-geometry-1/closed-natural64-evidence-archive/S01F/chunk-index.json --index-sha256 10ab71a6221997f83639479cff26a042659d3fe2d6645cbfb81e8e08243cc99b --repo .
.venv/bin/python review/vip-route-2026-09-30/evidence/t6-absolute-route-credit-1/closed-opportunity-evaluation-archive/archive_chunks.py restore --index review/vip-route-2026-09-30/evidence/t8-bounded-natural-geometry-1/closed-natural64-evidence-archive/S01F/chunk-index.json --index-sha256 10ab71a6221997f83639479cff26a042659d3fe2d6645cbfb81e8e08243cc99b --repo .
```

`build`、`split`和单独`verify`均已核各129件；候选、模型、规则、完整世界与新增桌实例调用全部0。工具的旧schema前缀不追改，实际T8源路径由清单`source_relative_to_repo`声明。研发结果和限制见[T8完整桌结果](./T8-NATURAL64-CLOSED-RESULT-AND-NEXT.md)。
