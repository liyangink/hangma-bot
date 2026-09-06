# 固定决策集比较报告

统计单位：单次决策（仅诊断与差异归因，不是强度结论的统计单位）。

归因纪律：recorded_request 与 recomputed_rules 分开报告，不混合归因；accepted 不当执行标签，不输出最优动作准确率或遗憾值。

## 样本与排除

| 指标 | 数值 |
| --- | --- |
| 输入决策行（比较成功） | 4 |
| 排除行 | 0 |
| mode | recorded_request |
| clock_mode | logical |
| 基线 policy_id | weighted_heuristic_v1 |
| 候选 policy_id | weighted_heuristic_v2 |

## 决策差异（相同历史候选与事实下的排序变化）

| 指标 | 数值 |
| --- | --- |
| 第一名动作键不同 | 4 |
| 基线动作不在合法候选 | 0 |
| 候选动作不在合法候选 | 0 |
| 基线使用保底 | 0 |
| 候选使用保底 | 0 |
| 任一侧无可用动作 | 0 |

## 第一名动作变化矩阵

| 基线动作键 | 候选动作键 | 行数 |
| --- | --- | --- |
| chi:1w,2w,3w | pass | 1 |
| pass | chi:1w,2w,3w | 1 |
| pass | peng:5w | 1 |
| peng:5w | pass | 1 |

## 耗时说明

clock_mode=logical：本实验不产生耗时结论（elapsed_ms 为 null），不能证明 1 秒窗口性能；硬件耗时基准另跑 real 时钟。
