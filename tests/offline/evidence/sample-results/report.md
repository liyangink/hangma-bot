# 评估结果汇总

统计单位：完整桌赛；聚类单位：同牌山根组（scenario_id）。

主指标：桌内积分差（桌内积分 口径，tie_method=strict）。

来源纪律：mock 结果只用于编排验证，不进入强度结论；作废/未完赛/未知分数逐条计数，不静默删除。

比较对象：稳定版本 stable 对候选版本 candidate。

## 样本与排除

| 指标 | 数值 |
| --- | --- |
| 总结果行数 | 16 |
| complete | 16 |
| partial | 0 |
| void（作废尝试，默认不作效果证据） | 0 |
| error | 0 |
| mock（只用于编排验证） | 16 |
| complete 但未完成/分数未确认 | 0 |
| 未知分数 | 0 |

## 来源分布

| source_kind | 行数 | 是否进入强度结论 |
| --- | --- | --- |
| mock | 16 | 否 |

## 未配对原因

r-b-0：source_kind=mock 不进入强度结论；r-c-0：source_kind=mock 不进入强度结论；r-b-1：source_kind=mock 不进入强度结论；r-c-1：source_kind=mock 不进入强度结论；r-b-2：source_kind=mock 不进入强度结论；r-c-2：source_kind=mock 不进入强度结论；r-b-3：source_kind=mock 不进入强度结论；r-c-3：source_kind=mock 不进入强度结论；r-b-4：source_kind=mock 不进入强度结论；r-c-4：source_kind=mock 不进入强度结论；r-b-5：source_kind=mock 不进入强度结论；r-c-5：source_kind=mock 不进入强度结论；r-b-6：source_kind=mock 不进入强度结论；r-c-6：source_kind=mock 不进入强度结论；r-b-7：source_kind=mock 不进入强度结论；r-c-7：source_kind=mock 不进入强度结论

## 配对统计（聚类 Bootstrap 置信区间）

配对差定义：候选值 − 基线值；配对只发生在同一 pair_id 内，同一 scenario 的换座变体先取组内均值，再以 scenario 为抽样单位重采样。n_resamples=2000，seed=7（进 manifest）。

| 指标 | 样本 | 配对差均值与 95% 置信区间 |
| --- | --- | --- |
| table_score_delta | 数据不足 | 没有可用于指标 table_score_delta 的配对差异（排除 0 对） |
| table_first_rate | 数据不足 | 没有可用于指标 table_first_rate 的配对差异（排除 0 对） |

## 结论

数据不足（可用 scenario 数 < 2 或指标缺失），未证明改进。

「未证明改进」不等于「无差异」，不构成候选上线依据。
