# T4 已闭合原件封存入口

本页用于从评审结论定位可复核原件。封存不改变成绩、候选身份或准入状态。Sol 新根复测未复制初期优势；GLM 现金修订只有两个开发根，未达到前登记继续工程信号。后续机会开发已闭合15条件根、30臂续打，结果为负；它不是自然积分或确认。机械验证不能充当算法增强成绩。

|证据|结论入口|封存和恢复入口|
|---|---|---|
|Sol 8 个新根、128 完整桌赛|[结果](T4-SOL-I1-NEW-ROOT-RESULT.md)、[独立审核](T4-SOL-I1-NEW-ROOT-INDEPENDENT-REVIEW.md)|[两批封存目录与分片校验](evidence/t4-conditional-payment-batch-1/sol-i1-new-root-validation-1/new-root-archive-summary.json)|
|GLM 现金修订、32 完整桌赛|[结果](T4-GLM-M1-CASH-NATURAL-RESULT.md)、[独立审核](T4-GLM-M1-CASH-NATURAL-INDEPENDENT-REVIEW.md)|[恢复说明](evidence/t4-conditional-payment-batch-1/glm-m1-cash-natural-development-1/ARCHIVE-README.md)、[封存清单](evidence/t4-conditional-payment-batch-1/glm-m1-cash-natural-development-1/cash-archive-summary.json)|
|机会入口旧版缺陷与新版守门验证|[旧版缺陷](T4-OPPORTUNITY-TOOL-INDEPENDENT-REVIEW.md)、[新版独立审核](T4-OPPORTUNITY-V2-INDEPENDENT-REVIEW.md)|[修订记录](T4-OPPORTUNITY-VALIDATION-REPAIR-1.md)|
|机会入口非零完整消费者机械06|[最终独立审核](T4-OPPORTUNITY-V2-FULL-ENTRY-INDEPENDENT-REVIEW.md)|[完整原件恢复说明](evidence/t4-conditional-payment-batch-1/opportunity-plan-tool/mechanical-fixture-06-archive/README.md)；10根20臂仅验证量具机械路径，正式机会样本0|
|Sol机会开发pilot1，4母种子、15选中根、30完整续打臂|[预登记](T4-SOL-OPPORTUNITY-PILOT-1-PREREG.md)、[独立审核](T4-SOL-OPPORTUNITY-PILOT-1-INDEPENDENT-REVIEW.md)|[完整259件原件恢复说明](evidence/t4-conditional-payment-batch-1/opportunity-sol-pilot-1-archive/README.md)；当前/剩余桌差−2.7333/−5.6667，直接高番家族无命中仍未知|

压缩包和分片由机器封存清单记录 SHA256、字节数与成员清单；恢复后按原相对路径核对每个成员。大压缩包只保存分片，小源码快照直接保存压缩包。展开源码目录留在本地，避免默认搜索重复扫描历史实现。旧版机械失败原件仍保留，不能用新版通过结果覆盖旧记录。GLM 封存工具曾在摘要写入时失败，失败原件及最终只读复核均保留，详见恢复说明；它不是算法运行失败，也没有模型或桌赛信用退款。写入中断的摘要原样保存，包括末尾空白；不为通过格式检查改写失败原件。

## 冻结合同副本中的相对链接

候选包和桌赛封存目录中的 `contract.md` 是调用或评测当时的逐字节合同副本，其 SHA256 已绑定候选身份及封存成员。因此不改写副本里的旧相对链接。阅读正文中这四个链接时，请从本页进入对应原文：

|合同副本中的链接|原文入口|
|---|---|
|`./FIXED-FRAMEWORK-CONTRACT.md`|[固定框架合同](FIXED-FRAMEWORK-CONTRACT.md)|
|`./VIP-FIXED-FRAMEWORK-EOH-IMPLEMENTATION-REVISION-ASTRA.md`|[Astra 实施修订](VIP-FIXED-FRAMEWORK-EOH-IMPLEMENTATION-REVISION-ASTRA.md)|
|`./EOH-FIXED-FRAMEWORK-ALIGNMENT.md`|[EoH 流程对齐](EOH-FIXED-FRAMEWORK-ALIGNMENT.md)|
|`./EVALUATION-CONTRACT.md`|[评估合同](EVALUATION-CONTRACT.md)|

条件支付使用[合同 v2](FIXED-FRAMEWORK-CONTRACT-V2-CONDITIONAL-PAYMENT.md)。后续结论以[研究索引](../INDEX.md)和[当前进展](PROGRESS.md)为入口，不把本页的阶段快照视为持续更新的候选排名。
