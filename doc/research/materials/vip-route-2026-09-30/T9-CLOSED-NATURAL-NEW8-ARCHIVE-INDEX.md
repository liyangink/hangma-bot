# T9 S02 新八根自然桌完整原件封存

161件原始证据、816,808,814字节已封包，分成8块，每块最多32MiB，逐成员读回验签。原始目录保留原位；Git保存分块、清单和首封，封存不表示算法更强。

源首封：[ROOT-RAW-NATURAL-NEW8-FIRST-SEAL.json](./evidence/t9-joint-author-execution-preparation-1/S02-m1-author/ROOT-RAW-NATURAL-NEW8-FIRST-SEAL.json)，SHA `87ebb0620d7e392c324d3e98ef2a4d2f1db5e041c16472bb552f2314f2317ca3`。压缩包252,437,767字节，包含全部正负结果、动作记录、费用及源码快照。[封存对账](./evidence/t9-closed-natural-new8-archive-1/ROOT-FIRST-SEAL-EQUALITY.json)确认清单恰等于首开摘要之前的161件源首封；没有删掉不利桌或缺口。

## 新检出验证与恢复

[分块索引](./evidence/t9-closed-natural-new8-archive-1/S02/chunk-index.json) SHA `b04e4e3dedebd1e2275d6af5b0ceec72d8613c79f7329a05749e11ff76bdbeb8`。以下工具已跟踪保存；verify会读取所有块与全部原件成员，restore仅补缺件并拒绝覆盖不同字节。

```sh
.venv/bin/python review/vip-route-2026-09-30/evidence/t6-absolute-route-credit-1/closed-opportunity-evaluation-archive/archive_chunks.py verify --index review/vip-route-2026-09-30/evidence/t9-closed-natural-new8-archive-1/S02/chunk-index.json --index-sha256 b04e4e3dedebd1e2275d6af5b0ceec72d8613c79f7329a05749e11ff76bdbeb8 --repo .
.venv/bin/python review/vip-route-2026-09-30/evidence/t6-absolute-route-credit-1/closed-opportunity-evaluation-archive/archive_chunks.py restore --index review/vip-route-2026-09-30/evidence/t9-closed-natural-new8-archive-1/S02/chunk-index.json --index-sha256 b04e4e3dedebd1e2275d6af5b0ceec72d8613c79f7329a05749e11ff76bdbeb8 --repo .
```

本批128实例是8个随机母根×2对手池×4换座×A/C，按8母根解释统计。自然日志保存真实动作、全部合法根分数/trace及运行收据，但没有逐窗完整candidate_view图与条件支付原列表；封包不会补造这些缺失项。动作/积分全链独立审核与数学事实审核须注明不同范围。后续新批应在实际评分前录制完整公开DTO，不回填本批。

build、split和独立verify均已实际完成；候选评分、规则、模型、世界推进、新桌实例全部0。旧封包schema名称保持原样，实际源由manifest的source_relative_to_repo精确声明。
