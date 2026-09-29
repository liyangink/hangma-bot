# `policy` 模块实施规范

> **研究评分接缝：**`action_value_v1` 的历史设计见[完整评分合同](../../../review/llm-guided-heuristic-route-2026-09-15/SEARCH-SPACE-REDESIGN-2026-09-16.md)；2026-09-17 的骨架评审是当时快照，不作为当前完成度。V1/V2 的胡优先层和旧 delta 约束只约束旧实现。研究入口显式比较合法动作，不能据此改写规则合法性、紧急路径或冻结旧策略；生成代码只进入受限评分接缝。当前可配置策略和身份以[策略目录](../../../doc/implementation/strategy-catalog.md)为准。

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
- V1 使用 `heuristic_v1.py`、`evaluation_v1.py`、`weights_v1.py` 独立实现，配置名 `weighted_heuristic_v1`，开发验收后同样冻结。规则已提供响应 Pass 等待事实；V0/claim_if_legal 装配使用 `legacy_pass.py` 的显式旧视图，保留原始请求及异常事实。继续施工先读 `doc/implementation/policy-iteration-plan.md` 与接口协议 §4.3。
- V2 配置名 `weighted_heuristic_v2`，复用 V1 的非 Pass 评分与权重，仅增加可比过牌等待分项。缺基线时按接口协议 §4.4 执行合法胡、未拒过牌、其余候选的顺序。变更 V2 不修改冻结 V0/V1；完整桌赛评估通过前保持默认 V0。
- 可选 `weighted_heuristic_v2_white_guard` 以输入副本保护普通弃白，保留原 V2 评分。`baotou=True`、强制白及无可用非白退路不得硬禁白；共享紧急路径优先非财神。兼容旧白板紧急候选、审计与版本边界见接口协议 §4.5。
- `catch_play_probe` 是用户要求的测试房定向策略：在 V2 已有计划中优先合法弃白（可高于胡）、响应吃碰与明杠，不套普通弃白保护。只允许 `test_room`，保留紧急候选、拒绝过滤和原预算；实验数据不作为启发式强度样本，见接口协议 §4.7。
- 官方 v26 已确认圈主吃碰明杠及补杠，2026-09-09 接线通过同一 `RuleAnalysis` 生效，不在策略重复判圈主。规则修复不修改冻结评分；普通听牌分值、吃碰后无立即胡的续飘及杠补机会成本按[策略复核](../../../review/catch-owner-v26-2026-09-09/strategy-review.md)分阶段验证，不用单个条件番数案例推导弃胡或必吃碰。

## 验收标准

- 覆盖胡/过/吃/碰/杠/弃牌及候选耗尽的正反例。
- 规则分析为 `DEGRADED` 时仍可形成保守计划。
- 超时、异常、空计划和重复候选均有契约测试。
- 基准测试证明 1 秒窗口不运行复杂搜索，主启发式在保底截止时间前完成。
- 模块自身无网络或文件副作用。
