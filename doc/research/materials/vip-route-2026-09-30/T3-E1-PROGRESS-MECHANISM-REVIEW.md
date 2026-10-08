# e1 进张机制静态复核（2026-09-30）

结论：数学结构事实本身未见错误。e1 的主锚点确实改为综合最优向听进张；“有效张数”和“补牌容量加权”的声明有确定实现偏差，已有探针还有六窗超额。以下属于候选用法、可解释性和工作量问题，不能把可调公式判作规则错误，也没有强度结论。

本次只读 [candidate.py](evidence/t3-development-batch-2/e1-01/candidate.py)、[generation.json](evidence/t3-development-batch-2/e1-01/generation.json)、[只读附录](evidence/t3-development-batch-2/e1-01/readonly-appendix.json) 和已完成行为探针，不重新 score、调用模型或运行桌赛。依据 [固定合同](FIXED-FRAMEWORK-CONTRACT.md) §2—4。作者此前参与结构数学及局部胡入口实现，本报告不自称对该数学的独立审查。

## 确定实现事实

1. **综合锚点成立，容量张数声明不成立。**候选第28—39行取真实普通／七对向听最小值，用 `combined_useful_codes`，没有继续以跨牌型并集作速度主项。但第1—23行 `codeweight` 为 exact0→0.30、exact1→0.72、其余→1；exact2／3／4完全不区分，conservative／unknown也为1。`mass` 是证据加权码数，最多等于码宽，不是未见实体张数。因此 generation 中“同12码、36／38有效张数由张数主导”的预期，在仅2／3／4容量发生变化时不会实现；名为 mass 不改变这个事实。

2. **raw码集没有相容过滤。**[投影](../../src/hangma_bot/policy/route_vip_heuristic.py) 第209—214／258—263行保留普通、七对、综合及逐目标原数学码集，另提供过滤后的宽度。e1第36／43／47／65行直接扫描raw集合：exact0仍计0.30，`breadth`仍加1，也未使用 `target_improvement_code_widths`。封存历史 [1454视图](evidence/t3-opportunity-diagnostic-1/a0525-seq1454.view.json) 的 `discard:白` 节点，综合进张含白且白容量exact0；1480同样存在。合法胡码来自相容集合内的正容量规则见证，因而该集合自身已排exact0；不能把它与raw结构推进集合混说。

3. **补牌码对齐正确，权重来源常退化。**候选第167—192行按 `condition_codes` 与 `children` 同位置配对；附录及生产节点校验保证同长度、唯一码。生产投影第311—324行却让精确补牌直接孩子为 `choices`，其 `waiting=None`；只有非精确 `unknown_draw` 孩子携带补牌前的等待容量。因此全精确时 `rcaps=None`，全部等权，trace却称 `capacity_weighted_replacement`；混合证据时使用首个 unknown孩子的共同**补牌前**容量。不是 generation 反例声称的“补牌后容量系统性少算已补码”，也不能从某个任意弃后叶拿容量反推补牌前权重。

4. **白用途已支付条件代价，仍是经验软价。**第62—71行 `surplus=D-(k-1)` 恰等于前驱自然弃牌下界，故 `work=1.45+0.85*自然弃下界+0.35*白弃下界`（此阶段必需终点摸牌为True）；没有直接按D全额定价，但白弃成本非零。同族取最大、两族取最好，另有两个小转换奖励。宽0仍因match底0.15获得正价，晚墙也不硬归零；支持度第108行有0.25底。这些是可测试的盲等／拒胡风险，不授予实际胡资格、概率或必达高番。

## 已有探针事实与待测假设

[既有87窗探针](evidence/t3-development-batch-2/behavior-e1-01/summary.json) 为 `probe_unfinished_not_admitted`：e1成功81／87，六失败均 `WorkloadExceeded`（100001或100005，限额100000），最大成功计数89950。两比较基准各有11个首选变化，但配对仅81／87、`comparison_complete=false`、`observed_behavior_difference=false`，不授完整行为信用，更不推断强度或普通均分变化的因果。

源码第134—218行只按拓扑次序计算每个节点一次，无递归重评整树；负担在每个wait／unknown_draw重复扫综合、胡、普通、七对及各白用途码集，并重复调用 `codeweight`。共享补牌前waiting的多个unknown孩子仍会各重算。具体六窗超额贡献比例未剖析，不把上述静态成本形状当实测归因。容量加权修正、末墙收缩或转换奖励削减是否改善首选与完整桌赛，均待新身份下验证。

## 下一轮精确建议

- 先统一声明与单位：若保留当前函数，改称“证据加权码数”；若要实体容量代理，区分exact1—4，明确保守／未知的有限代理，禁止除墙当概率。exact0从mass和breadth同时排除；仍保留保守零／未知相容性，使用真实结构实持计数排除物理第五张。
- 补牌先使用真实共同补牌前容量；当前图若不能可靠取到，明确等权，并把trace改成实际聚合口径。不得借任意弃后叶或把未知强填精确；任何必要新框架字段另走合同和冻结流程，当前候选修订不改核心。
- 优先在100000额度内做等价开销削减：每wait先建一次逐码权重表，码集求和复用；核规范去重约束后去掉冗余seen遍历，保持集合顺序和全叶。不要删根／孩子或默认升额度。新版本先补齐87／87，再核五个历史多白窗的完整评分；盲等、D0必需摸牌、晚墙和可胡继续另保留负控，不能以目的性开发题替代完整桌赛。

固定源 SHA256：candidate `f638dd1ee4b886f67b80e4d769628b360e41021b5264f9d1de691355d9a565ae`；generation `de07f3bc51cfb333eac80139e3be6b393f18fa1c83b82bf7c6c8c6eaab69f8f6`；附录 `0822ecb9696b60958b60579868bd1708200bbe76541d8d9dd66580b07a3079ac`。候选身份 `21972092ab069e364ce2d80a4d12a0f1010c600d3c9bcaa26e0675ab916c14af`。原包、生成记录、既有评分和核心文件均未修改。
