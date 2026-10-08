# T5 S01 新完整32桌自然开发独立审核

结论：仅恢复后的新32桌来源、身份、全动作自身评分、结算与费用通过独立复核，未发现阻止本批开发测量完整性信用的缺陷。C相对冻结R18基线A的H池均差为−7.25、M池−13，合并−10.125。母种子0501为−1、0502为−19.25。本轮保留一次目标题卡实际宽面改选的机制进展，不作强度确认或上线判断。

旧中断运行只核费用，不读其效果、不合并其已结算8桌。旧10个收费实例仍保留，新32加旧10共42；独立统计单位仍为两个开发母种子，不是42桌、16映射配对或44,559个动作窗口。

## 1. 原件冻结与恢复依据

先读[恢复说明](T5-S01-TARGET-BEHAVIOR-AND-CONTROLLER-RECOVERY.md)、[恢复前登记](evidence/t5-joint-formula-batch-1/S01-natural-controller-recovery-2-prereg.json)和[六槽登记](T5-JOINT-FORMULA-SIX-SLOT-PREREG.md)，再新写[原字节清单](evidence/t5-joint-formula-batch-1/S01-natural-independent-audit/SOURCE-RAW-SHA256-BEFORE.json)。首清单298件、211,813,314字节，SHA为 `78b8518ce7862962e3077751dd5c276bcfcc21666940abf5222b31efcbd6431e`。本审核已收到根任务的待核均差摘要，不是结局盲审；封存发生于读取新32桌完整结局和审计文件内容之前。

另对实时绑定来源、归一化说明和恢复依据补封存；最终314件唯一来源前后原字节一致。旧目录只读取 `costs.json`，另读取目录外停止回执，没有读取旧结果、结算或动作。`INDEX/PROGRESS` 不在本次冻结范围，后续更新现状入口不等于本批历史来源漂移。

|身份锚点|原字节SHA256|
|---|---|
|新批计划|`2bdae187f531d013625068ef00faa06b1d8347ed2f68dde158046f5729b2b2a1`|
|作者原源码，14,411字节|`6ad1247f849302851d194c8330ee75e9dbac48602a745cb1d160c13b3f089756`|
|实际摄入/评测源码，14,410字节|`c2e018be1fe15f87bc1dfbf5791aacb13b0074c9e72a5a21299ec7aa0cd33dd6`|
|摄入generation|`7069e71bad62a1a329c719e267f8d85f743ec6e0708279032976aab5e649a972`|
|新32桌manifest|`25033a93c359bfd81f6a82c6cd5f5e9cd5b541eb72692fb63e1a923a9d1a7ede`|
|末端冻结|`547664e5e9fddb611bba83217ba67f4477387365c2c2182fa89775c096f104cd`|
|新费用账|`0c341469d99639156d07e6d1edeaebf9c002d3faaeaa1256e4906bade7409572`|
|一次开封所绑定摘要|`8b3dd7da2bf6bc63f33e4c55cf2d0ce1a3d7ca83c3c2025bf1689461e4498e0e`|

作者源码比实际摄入源码仅多一个末尾换行，语法树相同；两者原字节身份不可混写。`generation.source_raw_sha256` 指摄入载荷源码，故与摄入canonical同为c2e018，而非作者文件6ad124。候选ID由源码、合同、依赖、预算及语义版本独立重算为 `3532521cf66fad4dfeba22745c0db79809384a5cad16166ff0523c20e53e6cc1`；72件执行快照、66件实时冻结绑定、末端身份与原生数学后端均匹配。冻结R18的实际源码SHA `a2d9b8af93beabdba75716fccae56b0668a6fd84f0bdce558d2ff3e569443618` 也匹配。

恢复登记的 `mechanical_original_report_sha256` 未写路径，存在引用歧义。本审核最初错误地按JSON路径核对；根任务及报告作者澄清后，按原字节SHA明确绑定：[中文机械报告](T5-FROZEN-REGRESSION-RESULT.md)为 `f62b6e0a6d618f847a92f0e55fb12db87e9be7dde1b553c2963e07a96f75e7b3`，配套[机械JSON](evidence/t5-joint-formula-batch-1/frozen-regression/T5-FROZEN-REGRESSION-RESULT.json)为 `490cd9bd14e9ab1c7b618c429c137aea58452daa860bb0f98742e218fe81f213`。两份来源未改；这是路径歧义，不是新32来源漂移。[明确路径映射](evidence/t5-joint-formula-batch-1/S01-natural-independent-audit/authority-audit.json)还核对了题卡摘要、机制结论和配对来源核验的登记SHA，四项全部匹配；没有改登记或重新评分。

## 2. 完整桌赛与同牌山比较

新分母完整覆盖2026100501/0502 × H/M池 × 四循环映射 × A/C两臂，32桌均完成配置8单局，共256单局。焦点固定为映射中逻辑第一身份所在物理座位 `permutation[0]`；初庄始终物理0，物理0—3初分均0。16桌组的实验声明、32张结果、引擎副本、对手身份以及四座实际策略映射一一对应，无缺组、删根、重复或排除。

A是登记的 `r18_integrated_positive_v2`，不是S01的直接Sol父代。题卡上的“父代改选”与这里的“相对R18桌分”是两种比较，不能互换。H为冻结R18三对手池，M为冻结混合池，两个池及所有映射均保留。

同一母seed的实验声明共用场景ID和seed；[发牌派生](../../src/hangma_bot/simulation/shuffle.py:45)只依赖场景、seed和单局号，换策略映射不改牌山键。实验的逻辑初庄经映射恰为物理0，[开发装配](../../src/hangma_bot/offline/vip_route_development.py:569)对A/C使用同一登记输入。此结论依据冻结实现、完整输入和记录一致性；本审核不读取隐藏世界、不重新启动或推进世界，不能把观察相同单独当作同牌山证明。

所有桌末积分与8单局结算链一致，所有推进记录在8,000步骤内。每池及每桌的超时、非法选择、回退、自动动作、缺失审计计数均0；`strict_challenger` 保持启用，没有R18替补C评分。这里只核本地模拟的动作选择/合法执行，不涉及官方HTTP动作成功或网络时限。

## 3. 全合法评分、生产规则与未知边界

[全流复算](evidence/t5-joint-formula-batch-1/S01-natural-independent-audit/full-flow-check.py)适配旧cash参考脚本后逐项改写来源、种子、候选身份、摄入费用及恢复依据；没有套用旧计数、旧效果或旧“均差≥5”门。最终436,545项断言零差异。

H池22,460条、M池22,099条，共44,559条审计动作全部与引擎实际选择一一对应，完整合法候选、有限分数、连续排名、动作身份和观察分数一致。C仅在C臂焦点座位被标为自身评分：H2,768窗、M2,721窗，合计5,489窗均 `SCORED`，完整独立评分15,654个合法根，不以对手评分、部分补零或回退替代。弃牌、吃、碰、杠、胡、过六族全部在真实评分原件中覆盖。

[纯生产规则查询](evidence/t5-joint-formula-batch-1/S01-natural-independent-audit/production-observation-rule-check.py)对全部44,559条玩家观察（`PlayerObservation`，当前座位依法可见信息）重新调用正式 `HangmaRules.analyze`，合法根集合和所选动作全部一致，规则完整且无问题。316个当前合法胡窗口的即时番数由 `HangmaRules.score` 重核；256次实际胡的番数、明细、赢家、庄家及四座结算全部一致，256个结算向量再次由 `settle_scores` 重核。共10,209,005项断言零差异，无世界推进、候选装载或候选重评分。

全部观察严格序列化往返一致，不含他家手牌或未来牌墙。4,686,538条被检查公开事件中，523,187条他家摸牌事件牌值为空，没有未来序号或桌末结果进入当前行动输入。[公开投影](../../src/hangma_bot/simulation/projection.py:35)隐藏他家暗摸；[受限候选视图](../../src/hangma_bot/policy/route_heuristic_view.py:346)不传积分、阶段和名次。审计原件里的公共积分供结算交叉复核，不代表候选获得积分压力输入。

C原局部图声明368个窗口含未知：1,682个等待节点、8个未知补牌节点；未知补牌没有删除相容码或把最佳补牌当必然。未来资格一直保持“局部条件见证以外未知”。评分成功不表示未来资格全知；本审核未重新生成未来支付图，信用限于原完整输出、冻结接线和已发生规则事实，不能用结局反填当前资格。

[资源复算](evidence/t5-joint-formula-batch-1/S01-natural-independent-audit/resource-check.py)核完整稳定排序、有限分数和原 `ScoreBatch` 序列化口径：最大C操作144,027，小于300,000；整批解释最大14,640字节，小于32,768。原 `choose` 计算审计最大304.54毫秒；逻辑时钟和该局部耗时不能替代官方1秒/3秒完整动作门。

## 4. 费用与审核失败留证

新费用16条桌组均为已结算，各预留、实际启动、收费2实例，合计32。桌组原墙钟合计514.564秒，批次521.169秒，均在登记3,600秒内。预留与结算是同一实例的账目阶段，不重复相加。

旧误启动只核[原费用账](evidence/t5-joint-formula-batch-1/S01-natural-development-1/costs.json)及[停止回执](evidence/t5-joint-formula-batch-1/S01-natural-mistart-stop-receipt.json)：4条已结算桌组为8实例，1条预留未结算为2实例；未结算实际启动数保持 `None`/未知，不能填0或退款。总收费10，退出143、非完整队列，根控制器原因不记为候选BUG。旧效果仍未读取，不增加比较分母。

S01费用为旧10+新32=42。恢复登记事前最大可能总收费为10+32+剩余三槽96=138，小于原六槽192上限；登记中的S02/S03不跑桌。本审核只核S01及该登记等式，没有审计其余槽的后来全部费用，不将138写成当前整体实际花费，也不修改预算。

本次摄入为replay，新增摄入模型调用/输入/输出token/桌实例均0。这不等于真实Sol作者委派免费；其底层调用/token成本未由摄入工具披露，继续记未知。

本审核自己的范围错误也保留：最初把摄入rawSHA误当作者文件SHA，留存[初版脚本/结果](evidence/t5-joint-formula-batch-1/S01-natural-independent-audit/full-flow-audit.initial-identity-scope-error.json)；扩查四座映射时漏计结果DTO的 `schema_version=1`，留存[配置范围错误](evidence/t5-joint-formula-batch-1/S01-natural-independent-audit/full-flow-audit.config-schema-scope-error.json)；机械报告未写路径导致[初次错误路径检查](evidence/t5-joint-formula-batch-1/S01-natural-independent-audit/authority-audit.initial-ambiguous-reference.json)。只修审核断言或来源映射，没有修改原候选、原件、登记或重打桌。最终全部通过，不能将审核错误当作新32候选失败。

## 5. 开发分差、普通出口与高番账

独立[结局复算](evidence/t5-joint-formula-batch-1/S01-natural-independent-audit/outcome-recompute.py)从256条实际选胡记录、单局起分、结算及桌末结果重新计算，逐桌、逐映射、分组账与原摘要一致。这里只计新32桌，两个母种子是开发样本，不是未见确认根。

|母seed|H四映射C−A|H均差|M四映射C−A|M均差|H/M合并均差|
|---|---|---:|---|---:|---:|
|2026100501|−9、+23、+1、−1|+3.5|−49、−8、−8、+43|−5.5|−1|
|2026100502|−14、+10、−7、−61|−18|−22、−3、−15、−42|−20.5|−19.25|

映射顺序为0123、1230、2301、3012。H均差−7.25，M−13，合并−10.125；16映射配对正4/负12/平0。这些只是两个母seed的描述，不把16对、两个池或换座当独立样本，也不报告伪大样本置信区间。

每臂各128个焦点单局，以下“自胡”均指该臂焦点身份，不是全桌四家胡牌次数。

|结局账|H A|H C|M A|M C|合计A/C|
|---|---:|---:|---:|---:|---|
|普通自胡，<4番|15|14|13|13|28/27|
|4—7番自胡|1|1|1|1|2/2|
|≥8番自胡|0|0|0|0|0/0|
|他家先胡|48|49|50|50|98/99|
|流局/未知|0/0|0/0|0/0|0/0|0/0|

没有新增高番计数，普通自胡总数少1；这不等于已定位一个同观察的普通出口因果损失。C三次当前胡继续：母0501/0123在H、M各一次1番继续后最终4番自胡，母0501/H3012一次1番继续后遇他家1番。两次4番来自同一母seed不同池，不能写成两个独立升级来源或专长效果；高番和全部普通出口损失保持分账，不能用局部兑现抵消完整桌负差。

目标题卡中从19码/67公开未见张改选23码/76张的事实仍成立；它与这次负向自然开发结果并存。不能将局部宽面改选直接写成后续自然成型、长期积分增强或家族专长。本轮不作上线判定，候选身份与后续研究取舍由原登记另行处理。

## 6. 可复算产物与限制

[总机器结论](evidence/t5-joint-formula-batch-1/S01-natural-independent-audit/independent-review.json)记录前后来源、各脚本SHA、完整分母、费用、规则与资源验证、歧义来源映射及分组结果。[最终原字节检查](evidence/t5-joint-formula-batch-1/S01-natural-independent-audit/SOURCE-RAW-SHA256-AFTER.json)保留314件唯一来源的前后值。

纯规则脚本使用 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python`；其他脚本只用标准库。此次新增候选装载/评分、模型、网络、世界启动/推进和桌实例均0，无私有目录访问、Git操作或原件修改。生产规则重核证明记录与当前冻结的唯一规则源一致，不等于第二套规则实现或官方对拍；同牌山和访问次数依据本地冻结接线/回执，未重建完整隐藏世界或历史全部读取记录。所有结论限定为这份新32桌开发测量。
