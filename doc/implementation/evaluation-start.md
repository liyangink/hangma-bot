# 评估模块开工指南

> 负责人：评估线；分支建议 `codex/evaluation-v1`。依赖 [parallel-v1](./parallel-contracts.md) 的文件和模拟方法，不依赖审计或模拟私有实现。

## 1. 交付目标

先能回答“新旧策略在哪些真实决策上不同，是否合法、是否按时、原因是什么”，模拟器稳定后再回答“完整桌赛表现是否提高”。第一项可以现在并行开发，不能用它代替第二项。

首读[统一术语](../../UBIQUITOUS_LANGUAGE.md)、[policy 接口](../../src/hangma_bot/policy/interface.py)、[共同契约 §5—7](./parallel-contracts.md#5-统一牌谱文件-v1)及现有 policy 测试。不要引入训练框架、在线服务或独立规则算法。

## 2. 输入、输出与两种决策实验

输入为统一牌谱目录，使用 `application.audit_codec` 恢复真实请求。审计线未完成时使用由现有公开类型构造的固定 fixture；在 tests 内保留构造辅助，不复制生产 codec，也不预建虚假的审计包。

| 模式 | 输入处理 | 回答的问题 |
| --- | --- | --- |
| recorded_request | 保留当时完整 request.rules；只换策略/权重，平移预算 | 在相同历史候选与事实下，策略排序改变了什么 |
| recomputed_rules | 用同一 observation 重新调用指定版本 HangmaRules，另存原/新规则差异 | 规则版本变化后，候选和策略共同发生什么变化 |

两种报告不能混合归因。旧记录缺完整 request 时排除并计数，不从修复后的算法补算后仍标 recorded_request。accepted 不当作执行标签，未胡不作“官方不能胡”标签；没有可靠反事实标签时不输出最优动作准确率或遗憾值。

首版结果目录：`manifest.json + decisions.jsonl + results.jsonl + report.json + report.md`。decisions 行保存原身份、实验模式、旧新动作键、完整评分、合法性、保底/错误和耗时；results 严格使用共同契约的 MatchResult。manifest 保存输入哈希、配置、代码/规则/策略版本、对手池及随机源版本；没有的数据为 null。

## 3. 完整桌赛驱动

评估器只调用 SimulationEngine 的公开方法，按当前 frame 的所有窗口生成选择后一次 advance；不能读取 WorldState 字段或让四个策略分享隐藏信息。

1. 根据 MatchSpec 创建世界。MatchSpec 的 seed 与每座位策略随机源独立；装配由 bootstrap 完成。
2. 获取 frame，为每个窗口用 observation 调用 HangmaRules.analyze，先准备紧急动作，再构造 DecisionRequest 和 DecisionBudget。
3. 调用策略，复核选择；异常/超预算按相同保底规则降级并计数。不能把选择不到动作静默换成 Pass。
4. 同期响应全部使用推进前数据；advance 后继续，直到 final_scores 或 blocked。blocked、异常、步数上限结束均不能记 complete 或合成流局。
5. 完整桌赛按运行时 rounds_per_game 统计。from_replay 的单局实验单独标 hand scope，不拼成原完整桌赛结果。

逻辑时钟用于可重复排序实验，wall-clock 用于部署机器耗时测量，报告 `clock_mode=logical/real`。时间预算构造复用 deadline.py 的公开逻辑；不得复制一套不同预算比例。原 budget 平移保持三个截止时间间距，以窗口接收基准建立新时钟；不可跨进程相减旧单调时钟。

CompetitionContext 只使用实验输入的可见事实；桌赛模拟无真实阶段榜单时传现有类型允许的空上下文。不要靠桌内分数假造海选晋级线。

## 4. 比较设计与结论标准

把完整桌赛或独立牌山根组作为统计单位，先声明主指标和样本计划，再看结果。首版提供桌内积分差和桌赛第一率；后者同分按预先声明的分析方法计入，不伪称官方排名。胡牌率、杠率、弃牌变化是诊断指标。

建议首个受控实验：固定对手池，稳定策略与候选策略分别占同一座位，使用相同完整牌序，然后做四种座位轮换。其他座位策略版本和参数不变。每个 scenario_id 下所有候选/换座变体聚类，报告配对差值及按 scenario 聚类的 95% Bootstrap 置信区间。重采样次数和随机种子进 manifest。

平台自动匹配无法控制同牌山和对手，不当作上述配对实验。报告来源、时间、对手身份已知度、完整桌赛数及运行故障，可以发现协议/规则问题；其表面分差不能单独证明策略改进。作废尝试排除效果统计和训练标签，保留恢复诊断；未知/未完赛不得静默删去，报告数量和原因。

首版不承诺晋级率估计器。完整阶段格式、名次分/白板数和权威晋级证据齐备后再增加赛事层指标；缺字段就输出“无法评估”。多次调参用训练/调参集，最终留出集按 split_group_id 固定且不反复挑选版本。

候选上线至少要求：规则门禁通过；真实时间预算/恢复可靠性无退步；预声明完整桌赛主指标及置信区间支持改进；目标赛事指标有对应证据。未证明改进保留稳定版本，不自动上线。

## 5. 文件与命令

| 路径 | 本线职责 |
| --- | --- |
| src/hangma_bot/offline/evaluate.py | 真实决策比较与完整桌赛驱动 |
| src/hangma_bot/offline/evaluation_results.py、evaluation_statistics.py | MatchResult、汇总、聚类区间；可按复杂度合并，不建泛化插件框架 |
| scripts/evaluate.py | 参数解析；调用主审合入的组合根入口 |
| tests/offline/test_evaluation*.py | 独立结果文件、Fake 模拟器、真实模块集成测试 |
| bootstrap.py、父目录 __init__.py | 给主审提供装配差异；不编辑 policy/hangma/simulation 实现 |

拟交付命令（尚未实现）：

```text
python scripts/evaluate.py decisions DATASET --experiment EXPERIMENT_JSON --out DIR
python scripts/evaluate.py matches --experiment EXPERIMENT_JSON --out DIR
python scripts/evaluate.py summarize RESULTS_JSONL --out DIR
```

EXPERIMENT_JSON 至少保存 `experiment_schema_version=1`、模式、输入哈希、候选/基线的策略名及完整权重、规则版本、clock_mode、主指标、seed 列表、实际 TournamentConfig、座位置换、对手池和排除规则。数据来源已确认后才生成最终配置；不能从另一个机器的默认配置继承未知权重。

## 6. 并行阶段与验收

E1 先交付结果文件校验、汇总、固定决策比较及人工可读差异。E2 在测试中用最小 Fake 验证循环编排，报告 source_kind=mock，不做强度结论。E3 模拟线交付后接真实 SimulationEngine，执行完整同牌山换座实验。E4 汇总测试房间/自动匹配的实际运行证据。

验收必须覆盖：相同 request 重跑稳定；规则重算明确分离；异常和超时保底可计数；原样读取审计线交付文件；不完整桌赛/作废/未知分数不进入 complete；座位换算不颠倒；同一 scenario 不被当成多个独立样本；mock 数据不能升级成真实指标。

建议本地命令 `python -m pytest tests/offline/test_evaluation*.py tests/unit/policy tests/contracts`（新增目录后）。交付 `handoffs/evaluation.md` 与一份实际运行生成的 report，写明当前是 E1、E2 还是 E3，不把等待模拟器描述为整个评估模块无法开工。
