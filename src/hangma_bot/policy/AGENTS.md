# `policy` 模块实施规范

## 目标与边界

本模块只对规则引擎已经确认的候选排序，是线上唯一决策接缝。先阅读根规范、接口协议和 `doc/implementation/modules/policy.md`。

- 第一阶段需要两个真实实现：加权启发式策略 `WeightedHeuristicPolicy` 和紧急保底策略 `SafeFallbackPolicy`。
- 只消费 `DecisionRequest` 与 `DecisionBudget`；禁止读取官方 DTO、Token、HTTP、磁盘、`WorldState` 或赛后隐藏信息。
- 不得声明一个动作合法。候选必须来自 `RuleAnalysis`，提交前仍由应用层请求规则模块复核。
- 在主策略启动前，应用层必须已经得到紧急保底；策略异常、超时、空计划或非法计划不能阻止提交保底。
- 第一阶段不创建模型注册表、模拟器、通用插件系统或线上 LLM 接缝。

## 计划不变量

- 候选按 `rank` 升序执行。V0 按总分、同分按 `action_key` 排序；V1 先合法胡、再可信评分、最后未知，同层同分按 `action_key`，全部未知时紧急候选优先。消费方保持 `rank`，不得只按总分重排。
- 不重复动作，不包含 `rejected_attempts` 中已经明确拒绝的动作。
- 紧急候选存在且未被明确拒绝时必须保留在计划中。
- 同输入、同配置输出完全确定；完整评分分解和降级原因可审计。

## V0 冻结与 V1 候选

- 保留原 `weighted_heuristic.py`、`evaluation.py`、`weights.py` 和默认策略名；冻结指纹见 `doc/implementation/baselines/heuristic-v0.json`，固定历史输入见 `tests/fixtures/policy/`。
- V1 使用 `heuristic_v1.py`、`evaluation_v1.py`、`weights_v1.py` 独立实现，配置名 `weighted_heuristic_v1`。规则接口及 V2 Pass 事实尚未修改；继续施工先读 `doc/implementation/policy-iteration-plan.md`。

## 验收标准

- 覆盖胡/过/吃/碰/杠/弃牌及候选耗尽的正反例。
- 规则分析为 `DEGRADED` 时仍可形成保守计划。
- 超时、异常、空计划和重复候选均有契约测试。
- 基准测试证明 1 秒窗口不运行复杂搜索，主启发式在保底截止时间前完成。
- 模块自身无网络或文件副作用。
