# E3 负向结果诊断与复跑（2026-09-06）

## 1. 结论

首次 E3 的 −75 不能解释为 V1 正常策略更弱：评估工厂没有给 V1 注入逻辑时钟，导致其动作请求触发异常保底。只修复工厂、保持原实验配置与 V0/V1 算法不变后，16 个完整桌赛的保底次数从 10,812 降为 0，配对桌内积分差从 −75 变为 0。

旧证据保留在 [e3-smoke-2026-09-05](../../../tests/offline/evidence/e3-smoke-2026-09-05/report.md)，用途改为集成故障诊断；修复后结果见 [e3-clock-fixed-2026-09-06](../../../tests/offline/evidence/e3-clock-fixed-2026-09-06/report.md)。本次不发布 V1，也不证明两版总体等效。

## 2. 因果证据

1. 原 experiment 的 `clock_mode=logical`，实验时钟为 800 秒。`scripts/evaluate.py` 给 V0 注入 monotonic，却以无参数方式构造 V1，使 V1 读取主机单调时钟。
2. 同一固定历史请求，经真实 CLI 工厂装配：V0 正常选择 `discard:1w`；V1 报 `PolicyTimeoutError`，真实时钟约 213750 秒大于实验截止 801.5 秒。
3. 原 16 行 results 的 `fallbacks` 合计 10,812，`timeouts=0`。原因是驱动只将 asyncio.TimeoutError 分类为 timeout，策略自己抛出的 PolicyTimeoutError 被记为普通策略异常保底。对手池中的 `opp-v0` 实际也使用 V1，因此两侧对手行为同样受影响。
4. 先添加工厂回归，V0 通过、V1 时钟和未知权重用例失败；修复后全部通过。按原配置复跑后保底归零、积分差归零，支持本次异常结果来自装配错误。
5. 同时发现 V1 声明权重被静默忽略。修复为构造 `HeuristicWeightsV1` 并传入策略，未知参数明确拒绝。本次原配置权重为空，实际使用默认值，故该问题不是 −75 的成因。

## 3. 原配置复跑结果

| 项目 | 原实验 | 修复后 |
| --- | --- | --- |
| 配置 | 2 scenario × 4 换座，每桌 8 单局 | 相同配置字节与哈希 |
| 完整桌赛 / 排除 | 16 / 0 | 16 / 0 |
| fallbacks 合计（四座位） | 10,812 | 0 |
| timeouts / illegal_choices | 0 / 0（超时分类失真） | 0 / 0 |
| 桌内积分配对差均值 | −75 | 0 |
| 桌内积分 95% 聚类区间 | [−90, −60] | [0, 0] |
| 桌赛第一率配对差均值 | −0.5 | 0 |

这些区间仅描述两个 scenario 上的结果，不能外推总体等效。V1 的可靠性差异继续由故障回归检验；正常完整事实样本上两版可以作出相同决策。

## 4. 修复范围

- `scripts/evaluate.py`：V1 与 V0 一样注入实验时钟；使用 V1 独立权重类消费声明参数。
- `offline/evaluate.py`：决策比较与完整桌赛驱动都将 PolicyTimeoutError 归为 timeout，不再藏入普通异常。
- `offline/evaluation_statistics.py`：汇总增加运行故障计数，明确覆盖全部结果行及四座位；非零时提示统计包含故障/降级影响。保持原始 complete 状态和配对数据，不静默排除问题样本。
- 增加工厂时钟/权重、两条评估路径超时分类、complete 但存在运行故障时的报告回归。

超时分类和报告展示在比赛复跑结束后修改；修复后的 report 使用新汇总器从同一 results.jsonl 重新生成。实验目录的 diagnosis.json 保存说明、完整有效默认权重和文件哈希；match-run-fix.patch 保存复跑时实际应用的工厂差异，manifest 的 dirty=true 如实保留。

## 5. 验证与后续

```bash
.venv/bin/python -m pytest -q tests/offline tests/unit/policy tests/contracts tests/integration/test_bootstrap_assembly.py
.venv/bin/python scripts/evaluate.py matches --experiment tests/offline/evidence/e3-clock-fixed-2026-09-06/experiment.json --out NEW_OUTPUT_DIRECTORY
```

回归结果：288 passed。V0/V1 策略源码、默认权重、规则与模拟器实现均未修改。下一步以修复后的评估装配为基准，继续真实决策检查及 V2 候选开发；扩大样本前先查看实际策略调用与运行故障计数，不能用“完赛、零排除”替代策略执行验收。
