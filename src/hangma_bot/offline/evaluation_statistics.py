"""复式评估统计：按 scenario 聚类的配对差与聚类 Bootstrap 置信区间。

统计口径（契约 §7、术语表「聚类 Bootstrap 置信区间」）：
- 统计单位是完整桌赛与同牌山根组（scenario_id），不是单次决策；
  同一 scenario 下的换座变体是同一抽样单位，不会被当成多个独立样本。
- 配对只发生在同一 pair_id（同一复式配对）内：基线稳定版本与候选版本
  各占同一测试座位、相同对手与完整牌序，其他配置逐座位一致。
- 主指标预先声明后计算：桌内积分差（table_score_delta）与桌赛第一率
  （table_first_rate，同分按预先声明的 tie_method 计入，本地分数口径，
  不生成官方名次分）。
- mock 来源只用于编排验证，永不进入强度结论；数据不足输出「未证明
  改进」，不把无显著差异写成等效。

本模块不实现规则算法，不读取 WorldState 字段。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .evaluation_results import (
    MatchResult,
    check_complete_consistency,
    count_by_source_kind,
    count_by_status,
    excluded_summary,
)

# 可声明的主指标名；报告必须写出具体指标名称和统计单位，不单独用「胜率」。
METRIC_TABLE_SCORE_DELTA = "table_score_delta"  # 桌内积分差：scores_after - scores_before
METRIC_TABLE_FIRST_RATE = "table_first_rate"  # 桌赛第一率：本地分数口径，非官方名次

# 同分处理方式（预先声明后不可事后更换）：
# inclusive：并列最高都计第一；strict：只有唯一最高计第一。
TIE_METHODS = ("inclusive", "strict")

# 强度结论只允许来自这些来源；mock 永不进入（契约 §7）。
STRENGTH_SOURCE_KINDS = ("simulation", "test_room", "auto_match", "test_tournament")

# 指标函数签名：(MatchResult, policy_id) -> Optional[float]；None 表示该行
# 缺少该指标所需事实，配对时计数排除而不是当作 0。
MetricFn = Callable[[MatchResult, str], Optional[float]]


def policy_seat(result: MatchResult, policy_id: str) -> int:
    """返回策略在 policy_ids_by_seat 中的座位；不在场抛 ValueError。"""
    try:
        seat = result.policy_ids_by_seat.index(policy_id)
    except ValueError as error:
        raise ValueError(
            "策略 {0} 不在结果 {1} 的座位上".format(policy_id, result.result_id)
        ) from error
    return seat


def table_score_delta(result: MatchResult, policy_id: str) -> Optional[float]:
    """桌内积分差（座位口径）：scores_after - scores_before；缺任一端为 None。"""
    if result.scores_after is None or result.scores_before is None:
        return None
    seat = policy_seat(result, policy_id)
    return float(result.scores_after[seat] - result.scores_before[seat])


def table_first_indicator(
    result: MatchResult, policy_id: str, *, tie_method: str = "strict"
) -> Optional[float]:
    """桌赛第一率指示（本地分数口径）：第一为 1，否则 0。

    同分处理由 tie_method 预先声明：inclusive 并列最高都计第一；
    strict 只有唯一最高计第一。官方排名分不在本函数内产生。
    """
    if tie_method not in TIE_METHODS:
        raise ValueError("tie_method 必须是 {0} 之一，得到 {1!r}".format(TIE_METHODS, tie_method))
    if result.scores_after is None:
        return None
    seat = policy_seat(result, policy_id)
    own = result.scores_after[seat]
    others = [value for index, value in enumerate(result.scores_after) if index != seat]
    if tie_method == "inclusive":
        return 1.0 if own >= max(others) else 0.0
    return 1.0 if own > max(others) else 0.0


def metric_fn_for(name: str, *, tie_method: str = "strict") -> MetricFn:
    """把声明的主指标名解析为指标函数；未知指标立即失败。"""
    if name == METRIC_TABLE_SCORE_DELTA:
        return table_score_delta
    if name == METRIC_TABLE_FIRST_RATE:
        return lambda result, policy_id: table_first_indicator(
            result, policy_id, tie_method=tie_method
        )
    raise ValueError(
        "未知主指标 {0!r}；可声明指标：{1}".format(
            name, (METRIC_TABLE_SCORE_DELTA, METRIC_TABLE_FIRST_RATE)
        )
    )


# ---------------------------------------------------------------------------
# 配对：同一 pair_id 内的基线/候选结果对
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairedMatch:
    """一对复式结果：同一 pair_id、相同换座配置，仅测试座位策略不同。"""

    pair_id: str
    scenario_id: str
    baseline: MatchResult  # 测试座位为稳定版本
    challenger: MatchResult  # 测试座位为候选版本


@dataclass(frozen=True)
class PairingOutcome:
    """配对结果：可用对 + 未配对原因（不静默丢弃）。"""

    pairs: Tuple[PairedMatch, ...]
    unpaired_reasons: Tuple[str, ...]


def _pair_consistency(baseline: MatchResult, challenger: MatchResult) -> Optional[str]:
    """检查两个结果是否构成有效配对；问题返回原因，合法返回 None。"""
    if baseline.scenario_id is None or challenger.scenario_id is None:
        return "缺少 scenario_id，无法确认同牌山配对"
    if baseline.scenario_id != challenger.scenario_id:
        return "scenario_id 不一致"
    if baseline.seat_permutation != challenger.seat_permutation:
        return "seat_permutation 不一致"
    differing_seats = [
        index
        for index in range(4)
        if baseline.policy_ids_by_seat[index] != challenger.policy_ids_by_seat[index]
    ]
    if len(differing_seats) != 1:
        return "测试座位差异数不是 1（{0} 处）".format(len(differing_seats))
    return None


def pair_matches(
    results: Sequence[MatchResult],
    *,
    baseline_policy_id: str,
    challenger_policy_id: str,
) -> PairingOutcome:
    """把完整桌赛结果按 pair_id 配成基线/候选对；其余逐条记录原因。

    - 只使用 status=complete 且来源允许强度结论的行；mock/partial/void/
      error 不进配对也不静默消失，进入 unpaired_reasons。
    - 每个 pair_id 必须恰好一行含 baseline、一行含 challenger，
      座位配置逐座一致且仅测试座位策略不同，否则整体不配对。
    """
    pairs: List[PairedMatch] = []
    reasons: List[str] = []
    grouped: Dict[str, List[MatchResult]] = {}
    for result in results:
        if result.pair_id is None:
            reasons.append("{0}：无 pair_id，不进入配对统计".format(result.result_id))
            continue
        if result.status != "complete":
            reasons.append(
                "{0}：status={1}，不进入配对统计".format(result.result_id, result.status)
            )
            continue
        if result.source_kind not in STRENGTH_SOURCE_KINDS:
            reasons.append(
                "{0}：source_kind={1} 不进入强度结论".format(result.result_id, result.source_kind)
            )
            continue
        problems = check_complete_consistency(result)
        if problems:
            reasons.append("{0}：{1}".format(result.result_id, "; ".join(problems)))
            continue
        grouped.setdefault(result.pair_id, []).append(result)

    for pair_id, members in sorted(grouped.items()):
        baseline_members = [item for item in members if baseline_policy_id in item.policy_ids_by_seat]
        challenger_members = [item for item in members if challenger_policy_id in item.policy_ids_by_seat]
        if len(baseline_members) != 1 or len(challenger_members) != 1:
            reasons.append(
                "pair_id={0}：基线 {1} 行/候选 {2} 行，无法唯一配对".format(
                    pair_id, len(baseline_members), len(challenger_members)
                )
            )
            continue
        baseline, challenger = baseline_members[0], challenger_members[0]
        problem = _pair_consistency(baseline, challenger)
        if problem is not None:
            reasons.append("pair_id={0}：{1}".format(pair_id, problem))
            continue
        pairs.append(
            PairedMatch(
                pair_id=pair_id,
                scenario_id=baseline.scenario_id,
                baseline=baseline,
                challenger=challenger,
            )
        )
    return PairingOutcome(pairs=tuple(pairs), unpaired_reasons=tuple(reasons))


# ---------------------------------------------------------------------------
# 聚类 Bootstrap 置信区间（抽样单位 = scenario）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BootstrapResult:
    """一次聚类 Bootstrap 估计；点估计与重采样分布都用 scenario 均值。"""

    metric_name: str
    point_estimate: float  # scenario 均值的均值（每 scenario 等权）
    ci_low: float
    ci_high: float
    alpha: float
    n_scenarios: int
    n_pairs: int  # 参与指标计算的配对总数
    n_pairs_excluded: int  # 指标所需事实缺失而排除的配对数
    n_resamples: int
    seed: int
    method: str = "cluster-percentile"


def _paired_diffs_by_scenario(
    pairs: Sequence[PairedMatch],
    baseline_policy_id: str,
    challenger_policy_id: str,
    metric: MetricFn,
) -> Tuple[Dict[str, List[float]], int]:
    """按 scenario 汇总配对差；指标缺失的对只计数不冒充 0。"""
    by_scenario: Dict[str, List[float]] = {}
    excluded = 0
    for pair in pairs:
        baseline_value = metric(pair.baseline, baseline_policy_id)
        challenger_value = metric(pair.challenger, challenger_policy_id)
        if baseline_value is None or challenger_value is None:
            excluded += 1
            continue
        by_scenario.setdefault(pair.scenario_id, []).append(challenger_value - baseline_value)
    return by_scenario, excluded


def clustered_bootstrap_ci(
    pairs: Sequence[PairedMatch],
    baseline_policy_id: str,
    challenger_policy_id: str,
    metric: MetricFn,
    *,
    metric_name: str,
    n_resamples: int = 10000,
    seed: int = 0,
    alpha: float = 0.05,
) -> BootstrapResult:
    """以 scenario 为抽样单位估计配对差均值的百分位置信区间。

    - 每个 scenario 先取组内配对差均值，再对 scenario 均值做
      n_resamples 次有放回重采样；区间为 Bootstrap 分布的
      alpha/2 与 1-alpha/2 百分位。
    - 抽样单位是 scenario：同一 scenario 的换座变体不会被当成独立
      样本；配对数不等时每 scenario 仍等权。
    - 重采样用 random.Random(seed) 确定性实现；n_resamples 与 seed
      必须进入 manifest（契约 §4）。
    """
    if n_resamples <= 0:
        raise ValueError("n_resamples 必须是正整数，得到 {0!r}".format(n_resamples))
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha 必须在 (0,1) 内，得到 {0!r}".format(alpha))
    by_scenario, excluded = _paired_diffs_by_scenario(
        pairs, baseline_policy_id, challenger_policy_id, metric
    )
    if not by_scenario:
        raise ValueError("没有可用于指标 {0} 的配对差异（排除 {1} 对）".format(metric_name, excluded))
    scenario_means = [sum(values) / len(values) for values in by_scenario.values()]
    point_estimate = sum(scenario_means) / len(scenario_means)
    rng = random.Random(seed)
    distribution = [
        sum(rng.choice(scenario_means) for _ in scenario_means) / len(scenario_means)
        for _ in range(n_resamples)
    ]
    distribution.sort()
    low_index = int(n_resamples * alpha / 2.0)
    high_index = int(n_resamples * (1.0 - alpha / 2.0)) - 1
    total_pairs = sum(len(values) for values in by_scenario.values())
    return BootstrapResult(
        metric_name=metric_name,
        point_estimate=point_estimate,
        ci_low=distribution[low_index],
        ci_high=distribution[high_index],
        alpha=alpha,
        n_scenarios=len(scenario_means),
        n_pairs=total_pairs,
        n_pairs_excluded=excluded,
        n_resamples=n_resamples,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# 汇总报告：样本/排除/配对/结论
# ---------------------------------------------------------------------------


def summarize_results(
    results: Sequence[MatchResult],
    *,
    baseline_policy_id: Optional[str] = None,
    challenger_policy_id: Optional[str] = None,
    primary_metric: str = METRIC_TABLE_SCORE_DELTA,
    tie_method: str = "strict",
    n_resamples: int = 10000,
    resample_seed: int = 0,
    min_scenarios_for_ci: int = 2,
) -> dict:
    """生成结构化汇总报告（结构化字典，渲染见 render_report_md）。

    结论纪律：
    - mock 行只计数，不进入配对与结论；
    - 没有足够非 mock 完整桌赛配对时写「数据不足，未证明改进」，
      不写等效；
    - 置信区间跨 0 时写「未证明改进（不等同于无差异）」；
    - 任何统计结论都注明统计单位、指标口径与后续门禁（规则/可靠性/
      人工审核），不自动发布候选。
    """
    primary_fn = metric_fn_for(primary_metric, tie_method=tie_method)
    sections: List[dict] = []
    intro: List[str] = [
        "统计单位：完整桌赛；聚类单位：同牌山根组（scenario_id）。",
        "主指标：{0}（{1} 口径，tie_method={2}）。".format(
            "桌内积分差" if primary_metric == METRIC_TABLE_SCORE_DELTA else "桌赛第一率",
            "本地分数" if primary_metric == METRIC_TABLE_FIRST_RATE else "桌内积分",
            tie_method,
        ),
        "来源纪律：mock 结果只用于编排验证，不进入强度结论；"
        "作废/未完赛/未知分数逐条计数，不静默删除。",
    ]
    if baseline_policy_id and challenger_policy_id:
        intro.append(
            "比较对象：稳定版本 {0} 对候选版本 {1}。".format(baseline_policy_id, challenger_policy_id)
        )

    status_counts = count_by_status(results)
    source_counts = count_by_source_kind(results)
    excluded = excluded_summary(results)
    inconsistent = [
        item for item in results if item.status == "complete" and check_complete_consistency(item)
    ]
    mock_count = source_counts.get("mock", 0)

    sections.append(
        {
            "heading": "样本与排除",
            "table": {
                "columns": ["指标", "数值"],
                "rows": [
                    ["总结果行数", len(results)],
                    ["complete", status_counts.get("complete", 0)],
                    ["partial", status_counts.get("partial", 0)],
                    ["void（作废尝试，默认不作效果证据）", status_counts.get("void", 0)],
                    ["error", status_counts.get("error", 0)],
                    ["mock（只用于编排验证）", mock_count],
                    ["complete 但未完成/分数未确认", excluded.get("incomplete", 0)],
                    ["未知分数", excluded.get("unknown_score", 0)],
                ],
            },
        }
    )
    if inconsistent:
        sections.append(
            {
                "heading": "一致性告警",
                "paragraphs": [
                    "{0} 行 complete 未通过完整性校验（completed_hands/expected_hands/"
                    "scores_after/invalid_reasons），不计入配对统计：{1}".format(
                        len(inconsistent),
                        "; ".join(
                            "{0}({1})".format(item.result_id, "; ".join(check_complete_consistency(item)))
                            for item in inconsistent
                        ),
                    )
                ],
            }
        )

    sections.append(
        {
            "heading": "来源分布",
            "table": {
                "columns": ["source_kind", "行数", "是否进入强度结论"],
                "rows": [
                    [kind, source_counts.get(kind, 0), "否" if kind == "mock" else "是"]
                    for kind in sorted(source_counts)
                ],
            },
        }
    )

    # 完整桌赛可以由异常保底撑完；不能把完赛率误读为策略正常执行率。
    runtime_fields = ("timeouts", "illegal_choices", "fallbacks", "auto_actions", "audit_missing")
    runtime_totals = {name: sum(getattr(r.runtime_counts, name) for r in results) for name in runtime_fields}
    sections.append({
        "heading": "运行可靠性（全部结果行）",
        "paragraphs": [
            "计数覆盖全部结果行及四个座位，不是仅待测策略。timeouts、illegal_choices 与 fallbacks "
            "按驱动现有互斥分类分别统计。不能仅凭 complete 或零排除认定策略正常执行；"
            "非零项须核对故障来源及实验装配，再判断能否用于策略强度归因。"
        ],
        "table": {"columns": ["计数", "次数"], "rows": [[name, runtime_totals[name]] for name in runtime_fields]},
    })

    conclusion: List[str] = []
    pairing_outcome = None
    if baseline_policy_id and challenger_policy_id:
        pairing_outcome = pair_matches(
            results,
            baseline_policy_id=baseline_policy_id,
            challenger_policy_id=challenger_policy_id,
        )
        if pairing_outcome.unpaired_reasons:
            sections.append(
                {
                    "heading": "未配对原因",
                    "paragraphs": ["；".join(pairing_outcome.unpaired_reasons)],
                }
            )
        metric_rows = []
        for metric_name in (METRIC_TABLE_SCORE_DELTA, METRIC_TABLE_FIRST_RATE):
            metric_fn = metric_fn_for(metric_name, tie_method=tie_method)
            try:
                result = clustered_bootstrap_ci(
                    pairing_outcome.pairs,
                    baseline_policy_id,
                    challenger_policy_id,
                    metric_fn,
                    metric_name=metric_name,
                    n_resamples=n_resamples,
                    seed=resample_seed,
                )
            except ValueError as error:
                metric_rows.append([metric_name, "数据不足", str(error)])
                continue
            metric_rows.append(
                [
                    metric_name,
                    "{0} scenario / {1} 对（排除 {2} 对）".format(
                        result.n_scenarios, result.n_pairs, result.n_pairs_excluded
                    ),
                    "{0:+.3f} [{1:+.3f}, {2:+.3f}] (95%)".format(
                        result.point_estimate, result.ci_low, result.ci_high
                    ),
                ]
            )
        sections.append(
            {
                "heading": "配对统计（聚类 Bootstrap 置信区间）",
                "paragraphs": [
                    "配对差定义：候选值 − 基线值；配对只发生在同一 pair_id 内，"
                    "同一 scenario 的换座变体先取组内均值，再以 scenario 为抽样单位重采样。"
                    "n_resamples={0}，seed={1}（进 manifest）。".format(n_resamples, resample_seed),
                ],
                "table": {
                    "columns": ["指标", "样本", "配对差均值与 95% 置信区间"],
                    "rows": metric_rows,
                },
            }
        )

        try:
            primary_result = clustered_bootstrap_ci(
                pairing_outcome.pairs,
                baseline_policy_id,
                challenger_policy_id,
                primary_fn,
                metric_name=primary_metric,
                n_resamples=n_resamples,
                seed=resample_seed,
            )
        except ValueError:
            primary_result = None

        if primary_result is None or primary_result.n_scenarios < min_scenarios_for_ci:
            conclusion.append(
                "数据不足（可用 scenario 数 < {0} 或指标缺失），未证明改进。".format(
                    min_scenarios_for_ci
                )
            )
            conclusion.append("「未证明改进」不等于「无差异」，不构成候选上线依据。")
        elif primary_result.ci_low > 0:
            conclusion.append(
                "主指标 {0} 的配对差均值 {1:+.3f}，95% 聚类 Bootstrap 置信区间 "
                "[{2:+.3f}, {3:+.3f}] 不含 0，方向支持候选版本。".format(
                    primary_metric, primary_result.point_estimate, primary_result.ci_low, primary_result.ci_high
                )
            )
            conclusion.append(
                "统计结果不等于发布决定：仍需规则门禁、真实时间预算/恢复可靠性无退步"
                "与人工审核（契约 §4）。"
            )
        elif primary_result.ci_high < 0:
            conclusion.append(
                "主指标 {0} 的配对差均值 {1:+.3f}，置信区间 [{2:+.3f}, {3:+.3f}] 不含 0，"
                "方向为负。".format(
                    primary_metric, primary_result.point_estimate, primary_result.ci_low, primary_result.ci_high
                )
            )
        else:
            conclusion.append(
                "主指标 {0} 的配对差均值 {1:+.3f}，95% 聚类 Bootstrap 置信区间 "
                "[{2:+.3f}, {3:+.3f}] 包含 0：未证明改进（不等同于无差异）。".format(
                    primary_metric, primary_result.point_estimate, primary_result.ci_low, primary_result.ci_high
                )
            )
    else:
        sections.append(
            {
                "heading": "配对统计",
                "paragraphs": ["未声明 baseline/challenger 策略，只做描述性汇总，不输出强度结论。"],
            }
        )
        conclusion.append("未声明比较对象：无法评估（只做描述性汇总）。")

    if conclusion:
        if any(runtime_totals.values()):
            conclusion.append("本批存在运行故障或降级计数；统计值包含这些影响，尚不能直接归因于策略评分优劣。")
        sections.append({"heading": "结论", "paragraphs": conclusion})

    return {
        "title": "评估结果汇总",
        "intro": intro,
        "sections": sections,
    }
