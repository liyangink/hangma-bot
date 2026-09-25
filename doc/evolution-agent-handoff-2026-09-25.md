# 杭麻启发式进化：接手指南（2026-09-25）

## 当前结论和任务边界

当前最值得保留的机会父代是 `OPTY-R18-C02`，运行名 `r18_integrated_positive_v2`；可直接比较的牌效等胡基线是 `PAIEFF-B02-HU01`，运行名 `v2_hu_upgrade_v1`。[算法命名与血缘](algorithm-lineage-names.md)记录了源文件和发布包摘要，切勿把小写源码版本号与大写牌效基线混同。旧 H/M 同墙面板上 R18 v2 有正向结果；近期自由赛 7 房/70 桌的 R18 v2 合计 `−114`，两者属于不同对手和时间分布，不能互相抵消或据此发布。[冻结四臂确认](../review/r18-four-arm-evaluation-2026-09-23/CONFIRMATION.md)、[自由赛复核](../review/r18-four-arm-evaluation-2026-09-23/RANKED-OPPONENTS-2026-09-25.md)。

接手者的目标是持续生成、检验并保留在杭麻规则下真正增加**完整桌赛和赛事晋级效用**的窄域策略，同时保持官方协议、动作时限、合法性和审计。大语言模型（`LLM`，离线提出算法与解释的工具）不能进入线上动作闭环。没有根级盲测正证据的提案可作为材料归档，不能宣称“有效进化”；测试房全为自家 Bot 的总净分恒为零，只验接线和对局机制。发布仍需完整测试赛事、可靠性、规则和人工审核。

自然面板的[策略身份审计](../review/llm-guided-heuristic-route-2026-09-15/NATURAL-ARM-IDENTITY-AUDIT-2026-09-25.md)发现 9 个历史暴露脚本把描述性 `arm` 字符串静默当成稳定 V2。旧报告中的 P5/P47/R18 v2 **自然轨迹频率与抽样身份**要按审计表降级；独立完整桌效果与实网接线证据另行判定。新批次必须逐桌保存并核对焦点策略 ID。

2026-09-25 的最新实网状态：[四席 R18 v2 SSE 房](../review/r18-four-arm-evaluation-2026-09-23/LIVE-R18-V2-SSE-ACCEPTANCE-2026-09-25.md)自然完赛 80/80 单局、规则确认的合法吃碰漏窗 0、SSE 错帧 0、R18 显式评分回退 0；`/state` 有 1 次 429，容量风险未归零。[两房两臂换位测试](../review/r18-four-arm-evaluation-2026-09-23/LIVE-R18-VS-HUUP-2026-09-25.md)各自然完赛 80/80 单局，R18 合计 −670，但同一观察重放显示 22,949 个动作窗口只发生 9 次首选差异，均为立即胡与弃牌；随机房总分不能判强度。第二房的指南版本端点有三次开局 429，`/state` 429 为零。测试赛事的 SSE 配置模板已准备，但独立赛事 Token、赛程与正式终态还未验收。[执行清单](../review/r18-four-arm-evaluation-2026-09-23/NEXT-STAGE-2026-09-25.md)。

## 科学依据与项目改编

以下一手来源只支持**搜索方法**，没有任何一篇证明它在杭州麻将必然增分。规则和结算只能以官方指南与本仓库 `hangma` 的对拍为准，不能照搬日麻和组合优化指标。

| 一手来源 | 可采纳的具体机制 | 本项目的证据边界 |
| --- | --- | --- |
| [EoH，ICML 2024](https://proceedings.mlr.press/v235/liu24bs.html) | 同时保存自然语言“思路”和可执行启发式，在外部评价中演化两者 | 只让模型改有界 `score_actions`；源码通过合同、行为改变、盲测收益分别判定 |
| [ReEvo，NeurIPS 2024](https://arxiv.org/abs/2402.01145) | 对可重复评价的成功与失败做语言反思，引导下一批提案 | 反馈包含事实、置信度和反例；模型的归因属于待检假设 |
| [FunSearch，DeepMind 官方说明](https://deepmind.google/blog/funsearch-making-new-discoveries-in-mathematical-sciences-using-large-language-models/) | 固定程序骨架、自动评价并保留有用候选 | 规则、合法性和在线调度不开放给生成模型；保存行为不同的专长 |
| [AlphaEvolve，技术报告](https://arxiv.org/abs/2506.13131) | 从廉价检查到昂贵评价的级联，以及多指标程序档案 | 本项目按静态合同→规则金例→自然触发→反事实→完整桌→实网顺序花预算 |
| [Suphx，原论文](https://arxiv.org/abs/2003.13590) | Mahjong 决策需要前瞻和长期回报视角 | 仅借鉴问题分解；其日麻规则、训练规模和胜负数字不能移植到杭麻 |

[本仓库文献与模型投入复核](../review/llm-guided-heuristic-route-2026-09-15/MODEL-EVOLUTION-RESEARCH-2026-09-17.md)、[失败后的文献与规则复盘](../review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/R14-G1-FAILURE-LITERATURE-REAUDIT-2026-09-21.md)给出进一步来源。尤其记住 P9/P10 七对教师的反例：成功胡时番数提高，却因本人先胡减少而总体退化；番值代理不能替代到达概率与他家抢先胡风险。[机制证据](../review/llm-guided-heuristic-route-2026-09-15/R18-P10-MULTISTEP-SURVIVAL-TRACE-RESULT-2026-09-22.md)。

## 自由赛与离线进化并行运行

两条工作流应同时推进，**不必等候一轮候选完成才开自由赛**。自由赛持续由当前冻结最强发布包参加，赛前保存官方榜单快照、源码/规则摘要和对手身份；离线研究同时运行结果盲暴露、配对反事实和新候选验证。每间自由赛房完赛后立即独立核查官方牌谱、审计、动作截止、SSE/429 与计分，再按房、对手、真实首选分歧和杭麻机会家族深入分析。它产生下一批研究问题，也可揭示当前研究假设偏移。

新自由赛发现的**协议、规则或策略身份错误**会使受影响证据失效，应立即修复和重新冻结；普通输赢或新机制线索不得中途改写已经冻结的来源、谓词、门槛或盲验切分，只进入下一批提案。离线候选通过同墙完整桌门后，才冻结新身份送入后续自由赛作外部验证。自由赛仍按房聚类，随机遇敌总分不能代替因果配对；强手标签必须来自开赛前快照。

| 持续自由赛轨 | 同时运行的离线进化轨 | 汇合点 |
| --- | --- | --- |
| 冻结当前版本开赛，赛前抓榜，完赛即核官方牌谱与审计 | 从已完成的自由赛问题池选择一项机制，预登记来源、门与预算 | 每房完成后更新问题池、反例和对手画像；事实错误立即更正 |
| 对新负分房、正分房、榜前强手房做同观察动作重放与规则核对 | 新牌山自然暴露、共同隐藏世界配对、未见根和同墙完整桌 | 新发现只指导**下一批**实验，除非证据失效，不改当前盲测 |
| 保留当前版本继续积累真实对手样本 | 合格候选另立发布包并通过测试房、测试赛事门 | 新包再进入新自由赛；真实失利回流下一轮问题池 |

## 一次离线进化迭代怎么跑

并行研究用独立 `codex/` 分支与 `.team-work/<任务名>/` worktree：自由赛差距、规则机会、风险表示和教师实现可以各写自己的报告与代码，主审复核后再逐个合入主线。隔离工作区只隔离文件、分支和中间结果，**不隔离**同机 CPU/内存/磁盘、全局自由赛 Token 的官方请求额度、LLM 额度或盲验标签。每条线须有唯一输出目录、牌山种子、预算账本和明确的主审；未经主审不得同时向同一官方 Token 加挂探针，不得让两个 agent 打开同一组自然盲验收益。大型完整桌模拟错峰或限制 worker，自由赛运行期间的其他 agent 优先做只读牌谱分析和静态设计；是否继续加并行度以实际 CPU、内存、请求队列和错误率决定。

1. **读取持续更新的自由赛问题池。** 从已完成的房间按房与对手身份拆本人先胡、条件番数、鸣牌与弃胡时点，重放每个实际观察下父代与牌效基线的首选分歧。把负分房、正分房、榜前强手房都纳入问题池；仅用牌局前可见事实提出机制，不能按事后胜负挑状态。[榜单和实战示例](../review/r18-four-arm-evaluation-2026-09-23/RANKED-OPPONENTS-2026-09-25.md)、[七次弃胡示例](../review/r18-four-arm-evaluation-2026-09-23/FREE-R18-HU-DEFERRAL-2026-09-25.md)。
2. **冻结问题。** 写明机会家族的玩家可见触发谓词、决策窗口、基线首选、拟改变动作、为什么可能改善、最强反例、杭麻规则依据。固定父代源码摘要、规则哈希、指南版本、对手池、来源房、牌山根、预算和停机条件。一个提案只动一个机制；R18 v2 发布包绝不原地改名覆盖。自由赛现象是提出问题的入口，不是因果标签；本地同墙实验要解释它，不能只在旧 H/M 池里找正分。
3. **先查事实是否存在。** `hangma` 是合法动作、胡牌、番数、爆头、财神、抓打圈的唯一来源。用自然牌谱和机会题库确认触发率、事实完备率、真实改选率；`score_parts` 非零不等于首选动作改变。公开未见张数是容量，不是下一摸概率；玩家观察（`PlayerObservation`）不能读取模拟完整世界（`WorldState`）的暗牌或未来牌墙。
4. **生成与准入。** 用 GLM 5.3 的禁工具 headless 通道生成思想、代码、反例；冻结原始输入、输出、用量、模型标识和请求头。每份最多一次合同修复，失败分类为传输、语法、合同、规则、无行为改变或真实负效。`action_value_executor.py`、评分视图 `action_value.py` 和策略接缝 `action_value_policy.py` 是正式边界；不得让生成代码提交 HTTP、读取文件/时间或拓宽信息权限。
5. **廉价机制验证。** 用规则金例和真实观察重放检查算术与动作身份，再取同一来源状态的共同隐藏世界，强制比较候选与父代的具体动作。分别报告本人先胡率、成功时番数、他家先胡/流局、当局积分和阶段/完整桌积分。若只是胡时分高而先胡率显著降，机制应关闭或改写，不继续补阈值。
6. **昂贵独立验证。** 来源房/牌山根先分开发和未见盲测；同一对手组合、同牌山、四座换位、整桌完成。根而非动作、单局或换位桌是统计单位。预先冻结主指标、机会指标、分层退化上限和置信区间；未知/作废结果单列，不补零。结果不显著则保留父代，并把该家族与失败机制归档。
7. **新候选接入下一批自由赛与发布。** 用冻结新候选参加新的自由赛，赛前留榜单快照，按房核实它在真实对手面前是否确实改变预期动作、有没有被抢先胡或平台接入退化；与父代的随机房净分只作外部警报，不能代替同墙强度判据。测试房检查 M=10/SSE/429/漏窗/非法与审计；测试赛事验报名、阶段、终态与晋级。候选通过完整门禁才冻结新包，人工审核发布。新自由赛的失败案例立即进入下一次问题池，形成持续循环。

每个迭代文件夹最少保存：`proposal.md`（思想、触发、反例、官方规则核对）、`source.py`/SHA、`lineage.json`、`call-ledger.json`、`preflight.json`、`behavior-diff.json`、`development.json`、`blind-confirmation.json`、`reliability.json`、`decision.md`。日志只放脱敏身份和哈希，不写 Token、Cookie 或授权头。失败提案也写 `decision.md`，这使中等模型可以从结构化反例继续，而不靠会话记忆。

## 立即可用的工具与证据

| 目的 | 入口与用法 | 使用边界 |
| --- | --- | --- |
| 官方榜单刷新 | `scripts/fetch_leaderboard.py --insecure --out datasets/leaderboard/snapshots` | 门户会话只从 `.private/` 读取；周榜 `prev.top` 是已结束上周，`top` 是本周未结算快照；保存抓取时间 |
| 榜单对手与自由赛联表 | `review/r18-four-arm-evaluation-2026-09-23/analyze_ranked_opponents.py --snapshot <快照目录> --out <结果.json>` | 身份用 `user_id`，9/25 标签晚于 9/23 对局，只能回顾描述 |
| 同墙四臂研究 | `review/r18-four-arm-evaluation-2026-09-23/paired_study.py --out <新目录> --panel-seed <新种子> --roots-per-mix 2`；之后 `analyze_paired.py --study-dir <目录>` | 小批只测执行和方差；正式独立根数与对比先冻结；H/M 旧池不等于近期强池 |
| 测试房 | `scripts/test_room_campaign_watchdog.py open/preflight/round/status --campaign runs/<战役>` | 新建房默认 SSE；所有身份同接线；房有时效，建好立即跑，启动后让进程自然完赛 |
| 实网动作机会核对 | `review/r18-four-arm-evaluation-2026-09-23/audit_claim_opportunities.py <审计根> <官方事件根>`、`verify_sse_live.py`、`analyze_state_runtime.py` | 先用官方手牌/事件找牌形，再正式规则复核；未知窗不当作通过 |
| 同观察动作分歧与弃胡结果 | `review/r18-four-arm-evaluation-2026-09-23/replay_cross_policy_actions.py --audit-root <审计根> --out <结果.json>`；`analyze_hu_deferral_outcomes.py` 接审计根、官方原文根和前项结果 | 先核原策略重放与发布包摘要；即时胡对实际续打只是同局描述，不能当完整桌因果效果 |
| 自然机会行为密度 | `review/r18-four-arm-evaluation-2026-09-23/analyze_opportunity_density.py --audit-root <自由赛审计根> --out <结果.json>` | 按玩家可见事实和规则候选分层；窗口数不是独立单局数，专项 trace 触发不是首选改选 |
| 赛后库 | `datamart/build.py` 与 `datamart/build.py --check` | 身份来自官方 `seats`，本方策略来自冻结归因映射；全自家房不能算自由赛净收益 |

强对手池当前事实：[9 月 25 日官方榜快照](../datasets/leaderboard/snapshots/20260925T004627Z/leaderboard-week.json)的上周前四已与 R18 31 房/310 桌赛后原文对齐。R18 v2 遇榜前四的 2 房合计 +155，其余 5 房 −269；这无法证明榜前较弱，却足以否定“仅模仿榜前选手就能解释负分”的简单方向。[七间自由赛房的同观察重放](../review/r18-four-arm-evaluation-2026-09-23/FREE-R18-HU-DEFERRAL-2026-09-25.md)进一步发现 11,063 个 R18 动作窗口只有 7 次相对牌效等胡改选，全部为弃胡；其中 4 次事后增分、3 次被抢胡。优先在新自由赛开赛**之前**冻结榜单标签，查四间负分房的本人先胡时点及可复现的自然动作分歧，不能从总分猜普通牌效弱点。[房级数据](../review/r18-four-arm-evaluation-2026-09-23/RANKED-OPPONENTS-2026-09-25.md)。

## 下一代候选和预算分配

**当前新进度：**自由赛实见的“合法立即胡或继续追爆头”已进入[P85 结果盲自然暴露](../review/llm-guided-heuristic-route-2026-09-15/R18-P85-HU-DEFERRAL-NATURAL-EXPOSURE-RESULT-2026-09-25.md)：真正 R18 v2 在 512 桌出现 197 个目标窗口、62 个独立根，四座与身份复核通过；已冻结开发 16 根、自然复验 16 根，**尚无收益标签或新候选**。下一步只在开发根按[风险表示与配对教师方案](../review/llm-guided-heuristic-route-2026-09-15/R18-P85-RISK-REPRESENTATION-AND-TEACHER-DESIGN-2026-09-25.md)比较立即胡与原弃牌；同时持续自由赛与赛后强手差距复盘。[实战机制初筛](../review/r18-four-arm-evaluation-2026-09-23/R18-FREE-MATCH-MECHANISM-TRIAGE-2026-09-25.md)给出两条后续机制线索，其中[公开对手高副露压力下积极鸣牌](../review/llm-guided-heuristic-route-2026-09-15/R18-OPPONENT-PRESSURE-CLAIM-ROUTE-FEASIBILITY-2026-09-25.md)经综合向听反例复核后暂停独立投入。另一条杠后补牌可胡机制在现有七房 36 个杠补牌窗口中合法立即胡为 0，暂不投入作者预算。

下一项应先复用[两房真实分歧](../review/r18-four-arm-evaluation-2026-09-23/LIVE-R18-VS-HUUP-ACTION-DIFF-20260925.json)与[自由赛七个真实弃胡](../review/r18-four-arm-evaluation-2026-09-23/FREE-R18-HU-DEFERRAL-2026-09-25.md)。测试房 R18 实际五次弃胡落在四局，后续都由本人胡且本局积分更高；自由赛七局只有四次成功、三次被他家抢先胡，事后增益 +54 与损失 −55 几乎抵消。把这些自然状态归为“立即胡还是继续”的共同隐藏世界续打试验，同时报告本人先胡、他家抢先胡、连庄和完整桌赛结果。原定“可立即平胡、两财神、早巡、下次摸后再弃牌建爆头”的[自然个案](../review/llm-guided-heuristic-route-2026-09-15/R18-P76-TWO-WHITE-LIVE-CASE-2026-09-23.md)仍是待证家族，**没有证明一般弃胡有利**。若因生存风险或盲测失败，就关闭该家族；当前真实观察相对牌效等胡几乎无非胡改选，应测量更常见杭麻专长家族的自然触发与改选密度。不得沿一个已看过结果不断加财神数、巡数等补丁。

[自然行为密度盘点](../review/r18-four-arm-evaluation-2026-09-23/R18-NATURAL-OPPORTUNITY-DENSITY-2026-09-25.md)显示七房有 1,080 个合法吃碰响应窗、实际选鸣 587 次；无副露、至少两财神且能鸣牌的 39 次中，11 次过牌仍有七对向听 ≤1，基线其中 6 次选鸣关闭该路线，其中 5 次鸣牌改善普通型向听。这不是错误判定。[P30/P31](../review/llm-guided-heuristic-route-2026-09-15/R18-P31-CLOSED-ROUTE-CLAIM-DEVELOPMENT-RESULT-2026-09-22.md)已在所选状态内否定宽泛的过牌保门清规则，旧自然抽样身份按系统审计限定。**P80 原报 512 桌、30 根的 R18 v2 暴露结论已撤销**：焦点实际跑的是稳定 V2，P81 也不得继续消费其切分。[失配裁定](../review/llm-guided-heuristic-route-2026-09-15/R18-P80-P81-TRAJECTORY-IDENTITY-INVALIDATION-2026-09-25.md)。[P83 更正批次](../review/llm-guided-heuristic-route-2026-09-15/R18-P83-CORRECTED-HIGH-WEALTH-NEAR-SEVEN-EXPOSURE-2026-09-25.md)让真正 R18 v2 完成 512 桌，28 个独立根通过暴露门。随后[P84 开发教师](../review/llm-guided-heuristic-route-2026-09-15/R18-P84-HIGH-WEALTH-NEAR-SEVEN-DEVELOPMENT-RESULT-2026-09-25.md)完成 832 张双臂当前桌，但前半选出的 4 个过牌状态仅 1 个在后半两指标同为正，目标局与当前桌策略均值为负；该窄支线关闭，13 个自然盲验状态封存，不得继续补阈值。不能由 GLM 文本或题库成绩替代自然触发与整桌增益。

模型投入按**每有效新行为的成本**，不按模型品牌或生成字数决定。GLM 5.3 可承担常规 I1/M1 作者与失败反思；小修可用较低推理档，难机制设计可用 `max` 与更大输出上限，但必须把请求实际 `provider/model/reasoningEffort/maxTokens` 和 token/耗时记账。能力较低模型只负责可机械验证的整理、报告和小范围候选。Sol/Astra 仅对经过反例归纳、能明确写出待解难点的少量困难种子尝试；比较合法率、行为差分率、盲测正效和时间成本后再决定是否常用。运行已有 `dsh` 包装器与账本格式可参照[GLM 接管与证据](../review/llm-guided-heuristic-route-2026-09-15/R9-TAKEOVER-REPAIR-AND-SEARCH-2026-09-19.md)及[候选搜索工具](../review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route_microfunction_search_b.py)。

如再次停滞，按顺序复盘：官方杭麻规则和实际事件链是否被读错；评估器是否漏掉改选与生存风险；对手池与排行榜标签是否时间错配；候选是否只有语法通过而没有新行为；统计是否把同根换位当独立样本；最后再决定增大 LLM 预算或换结构。每次复盘都要提出下一项可证伪实验或明确关闭家族，不能只写“继续优化”。
