# 多白机会诊断独立核对

结论：本次窄范围核对未发现确定缺陷。五个历史规范化窗口可追溯，公共信息边界、摸牌实体去重、失败保留和评分分母符合交付说明。独立仅以人工种子包评分五次，5/5 成功；完整分数、trace、首选及操作计数与作者对应规范化记录一致。没有模型调用、桌赛或核心修改，没有读取或修改在研 GPT6.1Sol 候选。

## Standards

通过本次范围检查。[README](evidence/t3-opportunity-diagnostic-1/README.md) 明确区分历史观察、构造夹具、当前配置重评和效果证据。原封条 44 个文件、交付封条 49 个文件逐项字节数与 SHA256 匹配；原封条身份未改。源码与 CLI 采用生产公共入口，候选通过 `load_vip_parents` 与受控评分执行器，不另造规则。

五个历史源行及源审计整文件摘要独立复核。只有五个 `decision_input` 的本人可见观察，以及四条当前本座公开事件被语义解析；其他源字节仅用于摘要，没有读取他家暗牌、起手全信息或未来墙作为输入。原件与规范化副本完整实体多重集相同，都是本手 14 张。

| seq | 原含摸牌手牌长度 → 单列摸牌后长度 | 完整本手白数 | 补证与旧失败 |
|---|---|---:|---|
| 1274 | 14 → 13 | 2 | 无补证 |
| 1350 | 14 → 13 | 2 | 无补证 |
| 1428 | 14 → 13 | 3 | 摸白不重复加成4白 |
| 1454 | 14 → 13 | 4 | 本座公开 timeout 1453 → 摸白1454；原未知失败保留 |
| 1480 | 14 → 13 | 4 | 本座公开 pass 1479 → 摸4万1480；原未知失败保留 |

两对补证事件逐项匹配原官方事件文件，座位均为2，序列连续且结束于当前已消费水位。生产 `infer_gang_draw` 推得 False；两原件仍为 None、历史仍不完整，成功副本也保持 `history_complete=False`。五窗存档的两表示图节点与合法根完全相同。没有把未知直接伪造为 False，也没有用成功副本覆盖旧失败。

## Spec

通过本次范围检查。独立 CLI 只消费五个历史规范化观察，不评分四个构造夹具。实际配置为 `hangma-mvp-v10-public-counts`、`BaseScore=1`、`YouCaiBiKao=false`、规则展开8192、操作100000；历史官方 BaseScore 仍未知，当前番数与结算没有被冒充原官方结果。

| 执行来源 | 评分分母 | 成功数 |
|---|---:|---:|
| 作者生成：3包 × 5窗 × 2表示 | 30 | 30 |
| 作者 CLI：3包 × 5规范化窗 | 15 | 15 |
| 本审核 CLI：1人工种子包 × 5规范化窗 | 5 | 5 |

本审核首选依次为弃6万、弃9饼、弃6万、胡、胡，操作计数最大1558。作者30/15次与本审核5次分开；仍仅有五个目的性历史窗口，不是50个独立机会样本。新结果见 [scores.json](evidence/t3-opportunity-diagnostic-1/independent-review-cli-1/scores.json)；摘要、身份与完整核对结果见 [checks.json](evidence/t3-opportunity-diagnostic-1/independent-review-cli-1/checks.json)。

CLI 在评分前创建必须不存在的新目录；已存在目录会在评分前失败。代码前后核材料原封条、批次字节及成功装载包的当前完整源码/依赖身份；装载、建图和评分失败留在包×五窗分母，身份漂移使结果失效。本次 `valid=True`、漂移错误为空。运行入口核的是原材料封条；交付封条及 CLI 自身摘要由本审核另行核验，不能把这次核验扩称为 CLI 自动校验了全部交付说明。CLI SHA256 为 `15b508e8738c2131366a16feb01e7d3b0a036f28d98cacd3363057bf1d71f4f8`。

实际独立评分命令：

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python review/vip-route-2026-09-30/evidence/t3-opportunity-diagnostic-1/score_scenarios.py --batch review/vip-route-2026-09-30/evidence/t3-development-batch-1/batch.json --packages review/vip-route-2026-09-30/evidence/t3-development-batch-1/manual-seed --output review/vip-route-2026-09-30/evidence/t3-opportunity-diagnostic-1/independent-review-cli-1
```

限制：没有重跑构造夹具、原未知失败规则分析、其他包或完整桌赛；没有破坏性漂移注入测试。新目录和漂移拒绝分支依据代码检查，五窗成功路径有实际执行证据。耗时不是动作时限门禁，首选变化不是增强、确认、准入或发布证据。
