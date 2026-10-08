# T5 S06 独立静态与冻结回归审核

S06 通过原登记的机械条件和真实行为差异要求，可在[六槽原登记](T5-JOINT-FORMULA-SIX-SLOT-PREREG.md)范围内开展 32 完整桌的开发评估。此结论只支持两个开发母种子、H/M 两池、四循环换座、每桌 8 单局的既定范围，不是准入、确认、强度或发布结论。本审核没有启动桌赛。

完整人工对照来自精确绑定的既有评分复用：S06 本次正式面板实际执行的是 **cash 直接父代 87 次＋S06 87 次**，与[共同计划](evidence/t5-joint-formula-batch-1/evaluation-plan.json)写的人工种子控制有执行差异。随后只读复用了已经计费的 S02 人工种子 87 次。两批合同、生产闭包、原生模块、参数、面板和输入顺序完全一致，逐根复算人工比较完整。因此原范围内的人工参考与真实行为要求有了证据，但不能把本次写成“一轮统一人工 174 次运行”，缓存也不增加预算或独立样本。

## 精确身份与费用

[S06](evidence/t5-joint-formula-batch-1/S06-glm-m2-cash/generation.json) 是 `m2` 数值字面值对照，状态 `loaded_not_admitted`，唯一直接父代为 GLM cash。独立原文比对确认只有三处数值不同，其余源码，包括控制流、注释与 trace，逐字不变；与既有 AST（抽象语法树，代码的语法结构）门记录一致。

|位置|父代→S06|单位及实际作用|
|---|---|---|
|candidate.py:20|`WHITECREDIT 0.5→0.75`|排序评分点／保留白张数，受 3 张封顶|
|candidate.py:23|`WHITEDROPCOST 0.55→0.45`|排序评分点／前驱待弃白动作次数|
|candidate.py:25|`BACKWIDTHCREDIT 0.05→0.09`|排序评分点／锚集外条件改进码的精确公开未见张数|

源码 SHA-256：`0c7001986006e7eaddeb90894919333a03e3089c9c64c751114014434e62b297`；候选身份：`b5b73723e85676a4b6a0cf52595c8bc37eb87a80aa7b0a1892e064e98ccb2dcd`。父代源码 SHA：`33e71d021397873dc303796dcc5315e6b66a62eb81184994469366948755a590`。两者均使用独立 v2 合同及 300,000 操作额度；不继承父代桌分。

原生成费用保留为模型调用 1 次、输入 114,560 token、输出 18,456 token、墙钟持续 168.834494 秒，reasoning 包含在输出内，不重复相加。本次机械验证实际新增 **11＋3＝14 次 S06 评分**；面板原执行另为 174 次，其中候选 87、直接父代 87。人工缓存 87 次、题卡旧父代 3 次均为原已计费记录，复用新增评分为 0。本审核没有模型、网络或新桌赛调用，也没有改候选、生产、预算、旧证据、INDEX 或 PROGRESS。

## 11 冻结观察：原登记通过，额外墙 23 断言失败保留

原[通用程序](evidence/t5-joint-formula-batch-1/frozen-regression/run_frozen_regression.py)未经修改：先在新目录 `prepare` 冻结计划与全部输入，再 `execute`。使用 `.venv/bin/python` 3.11.15、正式 `HangmaRules`、`build_vip_route_scoring_view` 和 `ActionValueExecutor`；全部合法根、完整条件图均由生产接口生成，三经典 DTO（数据传输对象，候选可读公共事实）与旧冻结版本精确匹配。实际 11 次、143 根完整有限，无回退；最高 55,153 操作，源及输入首尾稳定。

|观察|首选|当前胡分|最高继续分|结果|
|---|---|---:|---:|---|
|3704 大牌正控制|discard:6w|28.461538|31.599600|原登记通过|
|1815 首次双白|discard:9w|无合法当前胡|19.750556|完整评分；无金动作要求|
|2298 末墙当前胡|hu|18.571429|15.613530|通过|
|普通支付，墙余 20|hu|18.571429|12.708268|通过|
|普通支付，墙余 23|discard:东|18.571429|19.989334|**额外一律胡诊断失败；有严格升级**|
|普通支付，墙余 24|discard:东|18.571429|20.736833|通过|
|普通支付，墙余 32|discard:东|18.571429|22.096566|通过|
|普通支付，墙余 42／60|discard:东|18.571429|22.247233|通过|
|同价爆头，墙余 42／60|hu|23.333333|22.633333|通过|

3704 当前同源座位净支付除底分为 96，最高继续根的局部条件支付为 192–384，继续优势 **+3.1380612009183437**。同价爆头 42/60 当前支付和条件支付均为 48，当前胡领先最高继续 **0.7**，没有错误继续。

原 helper 名为 `hu_late_wall_without_upgrade` 的分支实际对墙余 20/23 一律要求胡，故原摘要仍为 10/11、`mechanical_scope_passed=false`。墙余 23 弃东有 24→48 的严格升级，原登记并未规定这一观察一律胡。保留原 plan/raw/summary 的失败，独立审核将其单列为额外保守出口诊断，不改旧程序或摘要，也不把它归为无升级继续。局部见证没有推进其他座位，不能保证能等到本人下一次摸牌；末墙等待风险仍在，开发评估必须保留其出口与结局。

## 三固定题卡：新增三次真评分与旧父代同图比较

在新 [S06-target-cards](evidence/t5-joint-formula-batch-1/frozen-regression/S06-target-cards/plan.json) 先冻结 3 次计划，再以原行动前 `PlayerObservation`（玩家观察，只含该座位依法可见信息）重建同当前公共 v2 图。三图 SHA 与旧 12 次诊断逐项完全一致，原源行 SHA 和积分仅恢复为正常观察；没有读取卡片结局或后续完整世界。旧 GLM cash 父代全部根分可据同一精确图复用，父代新增评分为 0。

|固定卡片|父代首选|S06 首选|计费操作数|结果|
|---|---|---|---:|---|
|finite-upgrade-positive|discard:5w|discard:5w|4,478|全部 7 根相同；继续 16.232143＞胡 14.285714|
|two-white-outlet-counterexample|discard:3w|discard:6w|12,386|真实改选；全部 11 根保留|
|unknown-payment-unresolved|chi:7t,8t,9t|chi:7t,8t,9t|1,254|全部 2 根相同；5 个未知等待节点逐码保留|

双白卡的 S06 `discard:6w` 分为 11.884444444444444，父代首选 `discard:3w` 在 S06 下仍为 10.324786324786324。6w 普通／七对向听为 3／2、最优推进宽度 8、精确公开未见容量 22；3w 为 2／2、宽度 23、容量 77；8b 为 2／2、宽度 23、容量 76。6w trace 的备用奖励为 3.44，3w/8b 为 0。因此这次改变是**窄出口与更高备用支持之间的新取舍**，不能说是扩大普通推进面或修复了旧宽度反例。它也不自动违反规则；三题预登记要求机制解释和完整未知事实，不按动作 ID 设硬答案。

未知卡原来的五个等待节点保留未知码 `[2b,4t]`、`[3b,4t]`、`[4t]`、`[1b,4t]`、`[4t]`；末节点同时有 4 条已知支付行。它们仍是部分未知，未补零、未排除未知码。该卡没有支付表为 None 的等待节点，因此 None 支路只获得静态检查信用，不冒充实测覆盖。

## 静态复核与剩余风险

以下行号指[未修改候选](evidence/t5-joint-formula-batch-1/S06-glm-m2-cash/candidate.py)。没有确认新增机械或生产规则事实缺陷；风险是未校准排序公式的取舍，不是未来兑现保证。

|位置|判断|
|---|---|
|42–95、137–151、199–224|当前胡与条件支付都取座位同源净支付、除同一底分，再经同一 `paypoints` 变换。锚定支使用同尺度增量，低支付当前胡没有混入真实积分与代理点的异单位加法。|
|67–95|同码互斥抓打假设取较大变换支付、按码只计一次容量；跨码容量加权平均是条件评分包络，不能当作真实牌墙概率或精确期望。取较高假设有乐观风险，稀少高支付码也可能被平均稀释。真实图中同码行连续，逐码折叠正确。|
|46–64、98–127、181–195|公开容量作锚集速度和备用支持，未除墙余。保守或未知容量得到固定代理，不能将这些代理解释为已知库存。`survival` 是手设折扣，未校准为存活概率；末墙局部升级不能保证尚有本人摸牌机会。|
|136–160、207–209|None 与已分析空支付行保持输入区别。锚定支仅对已知条件包络给增量、刻意不使用未知资格代理；未锚定已分析行集另给有界未知代理。未制造零结算，但未分析支付的数值信用不等于已知零事实。|
|227–256|可自行选择的 choices 取最大值；condition 取子区间 20% 信用；replacement 取下界加有界改进，未挑最好未来补牌。全部 14 张本次图完整；不完整图如何保守只获静态观察，不能据此宣称额外覆盖。|
|20、23、25、118–124|三个新参数只改变未锚定备用项，可强化保白与锚集外宽度，确实使题卡窄根反超；存在囤白、备用信用压住普通出口和过拟合风险。锚定可胡分支未改，因此不能声称修复父代所有兑现问题。|
|267–275|trace 保留评分点单位、选中公共节点、条件、分量、折扣和风险；不能把 `surv` 或 `gn` 读成事实概率／未来积分。公式标签沿用父代，实际源码和候选身份已单独绑定。|

## 完整面板控制与开发门结论

独立从 [S06 原 174 行](evidence/t5-joint-formula-batch-1/S06-behavior-probe/results.jsonl)复算，直接父代首选变化 3/87，分数变化 31/87，首选不变而其他次序变化 1/87；现金父代与 S06 最高操作数均为 191,192。真实改选为来源行 754：`discard:2t→discard:中`，319：`chi:2b,3b,4b→pass`，1489：`discard:5w→discard:9t`。

独立核 [缓存比较程序](evidence/t5-joint-formula-batch-1/compare_s06_cached_manual.py)及[缓存比较原件](evidence/t5-joint-formula-batch-1/S06-cached-manual-reference-comparison.json)，再直接逐根重排 [S02 人工参考原评分](evidence/t5-joint-formula-batch-1/S02-manual-seed-probe/results.jsonl)，得到相对人工首选变化 **13/87**。人工 source SHA 为 `961ce1445cebde624dba80c6748bb524d16616662605a2f1b53ec9931c7962c5`，身份、合同、生产闭包、原生模块、额度、完整参数、87 输入顺序及逐观察 SHA 均绑定一致；原操作数最高 25,363。两个比较均为真实首选比较，不用分数变化冒充行为变化，也没有执行缓存程序再次评分。

原登记 11 观察条件、三字面值范围、三题卡检查、全根有限与 300,000 上限均有实际原件；完整人工参考和直接父代比较都有真实改选。**在显式保留本次控制对象差异、缓存来源与全部额外墙 23 失败的前提下，支持按原预算继续 S06 的 32 完整桌开发评估。**此次没有新增或放松动作金标准，没有重建缺失历史图冒充旧证据，没有授予研究席、稳定改进或发布信用。若监督执行，应将本报告、独立 JSON、缓存来源及三题卡封签一起冻结进启动凭据。

只读核对待启动 [S06 batch](evidence/t5-joint-formula-batch-1/S06-natural-development-1.batch.json)，原字节 SHA `934a7b14532114fedf8de13d462bc89e1833dc4d82bbbfc123c2a443fed72d4b`：源码、生成记录、原面板摘要绑定吻合，开发母种子 2026100501/0502、H/M、四映射、8 单局、物理起庄 0、初分 0、32 桌／3600 秒／8000 推进上限均与原登记一致。核对该配置不启动任何执行。

## 输出原件及 SHA-256

113 件独立只读审核来源首尾稳定。正式 11 次回归与三题卡各有不可覆盖计划、完整原评分、摘要和封签；独立复算新增评分为 0。

|文件|SHA-256|
|---|---|
|[S06 plan](evidence/t5-joint-formula-batch-1/frozen-regression/S06/plan.json)|`2d2b8bb5b3da3a658b36a020a59e6dffea0f6292579a58aa6109bca125797de6`|
|[S06 raw](evidence/t5-joint-formula-batch-1/frozen-regression/S06/raw-scores.json)|`cf1582f3f8da85584bec6d029fca08ceacccce6b698f74e77d88dd1ad90e94f9`|
|[S06 summary](evidence/t5-joint-formula-batch-1/frozen-regression/S06/summary.json)|`84fdf1d3068898e41c31e1744002693d7f15ae905226bd87919ccf5567f210f7`|
|[S06 seal](evidence/t5-joint-formula-batch-1/frozen-regression/S06/seal.json)|`835d85100a620fb9a075080d4d83a715418b5fa451d635db8847827e8719eb52`|
|[三题卡 plan](evidence/t5-joint-formula-batch-1/frozen-regression/S06-target-cards/plan.json)|`6af0b38d4527bd8792dac824bbd9978265dd0e999765552bea3ac86aa0281ee1`|
|[三题卡 raw](evidence/t5-joint-formula-batch-1/frozen-regression/S06-target-cards/raw-scores.json)|`e785de139af5aff8878bc38bef0c189021b22c932fd40fd892088f77bd122ef7`|
|[三题卡 seal](evidence/t5-joint-formula-batch-1/frozen-regression/S06-target-cards/seal.json)|`4783d67358c739ed1bb795d63e124773eaf8dae47841ab9efcce604c26c0304b`|
|[独立审核 JSON](evidence/t5-joint-formula-batch-1/frozen-regression/S06/independent-audit.json)|`289a9ae97ee35414a4f07a0e8a0bf3e3958c660b99c4f46afd4f99ff8a4907c9`|
|[缓存人工比较](evidence/t5-joint-formula-batch-1/S06-cached-manual-reference-comparison.json)|`dcc6b16fa9cb3b107a98ebba717b6dec56432df0909929aac7984cfb36e8e817`|
