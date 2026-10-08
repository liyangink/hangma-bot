# E 批次（最小真实闭环）收口总结

日期：2026-09-16/17。验收依据：v4 合同 §9.3"至少取得一条真实『条件结果→反馈→M1→同合同重评』即最小进化闭环完成；后代未提高也可完成工具验收"。

## 闭环证据链（全部真实执行）

| 环节 | 候选 | candidate_id | 证据 |
| --- | --- | --- | --- |
| 种子准入 | efficiency_seed / route_value_seed | 6d9c1d59… / 1108e4be… | admission/（五层门禁全过） |
| I1 真实生成 | triax-v1（三轴对照） | 766712b6… | gen/i1/（delegate 通道、glm-5.3、prompt_sha 641296497a9b；解析/静态预检/隔离装载/门禁全过） |
| 条件评估（真实 v2_behavior 前缀） | I1 | — | eval/i1-…/conditional（branch_open/H，3 尝试命中 1，双臂 valid，tables_partial=3） |
| 自然评估（真实双臂） | I1 + efficiency_seed | — | eval/（各 H/M 1 根 ×4 座位 ×2 臂 ×2 桌=32 桌/候选，全 complete） |
| 根级统计 + 三段反馈 | I1 vs V2 | — | 反馈文件 feedback-i1.md（H +0.25 / M 0.00 / 混合 +0.125；eff 对照 −0.5；8 窗口配对差异事实/区间/机制假设三段） |
| M1 真实修订 | triax-v2（墙后段潜力门控+庄家衰减+统一结算偏置，三处有界修订逐条对应反馈） | ab9b409e… | gen/m1/（父代 766712b6 血缘完整；门禁全过） |
| M1 同合同重评 | M1 | — | eval/m1-…/（条件 branch_open/H 双臂 valid；自然 H +0.25 / M 0.00——与父代同根集持平，修订未在该根集触发排序差异，如实记录） |

## 费用总账（v4 §11 口径）

- LLM 调用：2 次（I1 + M1，delegate 文件式通道，zai-coding-cn/glm-5.3）。API usage 无计量（delegate 模式），字符量级：prompt 9.1k+26.6k、reply 10.8k+17.4k，合计约 64k 字符（≈3-4 万 token 量级），距 1 亿授权上限极远
- 桌赛实例：tables_full 正式 96（I1 32 + eff 32 + M1 32）+ 管线验证 smoke 8（单列 smoke-costs.json）；tables_partial 6（前缀生成 3+3，按被启动桌实例计）
- 墙钟：正式约 190 秒 + smoke 13 秒

## 诚实边界（不冒充）

- 自然面板每情景 1 根（min-closure 规模），interval_95=None（无根间标准误）；结果不构成效果结论，仅闭环证据
- v2_behavior 前缀 = V2 行为站立策略 + 规则引擎真实分析（非完整 V2 自对弈前缀），evaluation.json 已如实标注
- M1 与 I1 同根集结果持平：修订的触发条件（墙后段/非庄家）在该根集未产生可见排序差异；结论是"未分辨"不是"无改进"
- 识别区间全部已分辨（0 unresolved）；god_count 缺失未影响本批根的 U 判定
