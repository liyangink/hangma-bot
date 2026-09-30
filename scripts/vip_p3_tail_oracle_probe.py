"""以真实首次事件作上界，检验后继观察价值是否能辨别动作。

留出批的首次事件由隐藏世界产生，只供离线诊断；线上策略不能
读取这条未来事件。若此上界也无稳定动作增益，应先补状态特征
或教师分布，而不是拟合更复杂的事件概率。
"""

from __future__ import annotations

import argparse
import gzip
import json
from dataclasses import dataclass
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import RuleCompleteness, ValueAnalysisLimits
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json

from scripts.vip_p3_value_fit_probe import (
    _FEATURE_NAMES, _RIDGE, _features, _roots, _shape_key, _solve,
)


_EXTRA = (
    "own_white", "own_melds", "other_melds", "public_events",
    "response_peng", "response_chi", "gang_replacement",
)
_FEATURES = _FEATURE_NAMES + _EXTRA
_LIMITS = ValueAnalysisLimits(max_expansions=8192)


@dataclass(frozen=True)
class _Event:
    """首次终点的可见后态或精确终局；value 仍是整单局本座积分。"""

    features: tuple[float, ...]
    exact: float | None
    value: float


@dataclass(frozen=True)
class _EventRoot:
    """每根全部合法动作共享同编号隐藏世界。"""

    seed: int
    root_id: str
    keys: tuple[str, ...]
    shape_key: str
    arms: tuple[tuple[_Event, ...], ...]


def _load(path: Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def _next_state_feature(rules: HangmaRules, payload: dict) -> tuple[tuple[float, ...], float | None]:
    """下一本人观察才可见的牌和规则事实；当前动作窗口不能直接读取。"""

    observation = observation_from_json(payload)
    analysis = rules.analyze(observation, value_limits=_LIMITS)
    if analysis.completeness is not RuleCompleteness.COMPLETE:
        raise ValueError("给定首次事件后的本人规则分析不完整")
    key = _shape_key(analysis, observation.phase)
    candidate = next(item for item in analysis.legal_candidates
                     if item.action_key == key)
    base, hu = _features(candidate, observation)
    if key == "hu":
        return (0.0,) * len(_FEATURES), hu
    white = sum(tile.code == "白" for tile in observation.my_hand)
    if observation.drawn_tile is not None:
        white += observation.drawn_tile.code == "白"
    extra = (
        white / 4.0,
        len(observation.melds[observation.seat]) / 4.0,
        sum(len(melds) for seat, melds in enumerate(observation.melds)
            if seat != observation.seat) / 12.0,
        len(observation.public_history) / 100.0,
        float(observation.phase == "response_peng"),
        float(observation.phase == "response_chi"),
        float(observation.gang_draw is True),
    )
    return base + extra, None


def _extract(paths: tuple[Path, ...]) -> tuple[_EventRoot, ...]:
    """教师完整世界只供标签，后态特征从其玩家观察重新分析。"""

    ordinary = {root.root_id: root for root in _roots(paths)}
    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    cache = {}
    event_roots = []
    for path in paths:
        report = _load(path)
        for row in report["rows"]:
            root = ordinary[row["root_id"]]
            arms = []
            for key in root.keys:
                samples = []
                for item in row["outcomes_by_action"][key]:
                    event = item["first_event"]
                    value = item["terminal"]["score_delta"][
                        row["observation"]["seat"]]
                    if event["kind"] in ("self_win", "other_win", "draw"):
                        if ("next_observation" in event
                                or event["score_delta"][row["observation"]["seat"]]
                                != value):
                            raise ValueError("首次终局事件与完整单局结算不一致")
                        features, exact = (0.0,) * len(_FEATURES), float(value)
                    else:
                        payload = event.get("next_observation")
                        if payload is None:
                            raise ValueError("非终局首次事件缺下一本人观察")
                        frozen = json.dumps(payload, ensure_ascii=False,
                                            sort_keys=True, separators=(",", ":"))
                        if frozen not in cache:
                            cache[frozen] = _next_state_feature(rules, payload)
                        features, exact = cache[frozen]
                        if exact is not None and exact != value:
                            raise ValueError("参考者下一窗口胡与完整单局结算不一致")
                    samples.append(_Event(features, exact, float(value)))
                arms.append(tuple(samples))
            event_roots.append(_EventRoot(
                seed=root.seed, root_id=root.root_id, keys=root.keys,
                shape_key=root.shape_key, arms=tuple(arms),
            ))
    return tuple(event_roots)


def _fit(roots: tuple[_EventRoot, ...], dimension: int) -> tuple[float, ...]:
    """绝对后态积分岭回归；每个原始观察根总权重为一。"""

    gram = [[_RIDGE if i == j else 0.0 for j in range(dimension)]
            for i in range(dimension)]
    rhs = [0.0] * dimension
    for root in roots:
        weight = 1.0 / sum(len(arm) for arm in root.arms)
        for arm in root.arms:
            for event in arm:
                if event.exact is not None:
                    continue
                x = event.features[:dimension]
                for i in range(dimension):
                    rhs[i] += weight * x[i] * event.value
                    for j in range(dimension):
                        gram[i][j] += weight * x[i] * x[j]
    return _solve(gram, rhs)


def _evaluate(roots: tuple[_EventRoot, ...], beta: tuple[float, ...],
              dimension: int) -> dict:
    """真实首次事件给定时的行动排序上界；非可部署预测。"""

    deltas = []
    rows = []
    abs_error = 0.0
    sample_count = 0
    for root in roots:
        estimates = []
        outcomes = []
        for arm in root.arms:
            predicted = []
            for event in arm:
                estimate = (event.exact if event.exact is not None else
                            sum(beta[i] * event.features[i]
                                for i in range(dimension)))
                predicted.append(estimate)
                abs_error += abs(estimate - event.value)
                sample_count += 1
            estimates.append(sum(predicted) / len(predicted))
            outcomes.append(sum(event.value for event in arm) / len(arm))
        best = min(range(len(root.keys)), key=lambda i: (
            -round(estimates[i], 8), root.keys[i] != "hu", root.keys[i],
        ))
        shape = root.keys.index(root.shape_key)
        delta = outcomes[best] - outcomes[shape]
        deltas.append(delta)
        rows.append({"seed": root.seed, "root_id": root.root_id,
                     "chosen": root.keys[best], "shape": root.shape_key,
                     "mean_net_delta": delta})
    return {
        "root_count": len(roots),
        "event_action_worlds": sample_count,
        "mean_absolute_terminal_error": abs_error / sample_count,
        "mean_paired_net_delta": sum(deltas) / len(deltas),
        "positive_roots": sum(x > 0 for x in deltas),
        "negative_roots": sum(x < 0 for x in deltas),
        "zero_roots": sum(x == 0 for x in deltas),
        "changed_action_roots": sum(row["chosen"] != row["shape"] for row in rows),
        "deferred_current_hu_roots": sum(
            row["shape"] == "hu" and row["chosen"] != "hu" for row in rows),
        "rows": rows,
    }


def probe(training: tuple[Path, ...], external: tuple[Path, ...]) -> dict:
    train = _extract(training)
    hold = _extract(external)
    if not train or not hold or ({row.root_id for row in train} &
                                  {row.root_id for row in hold}):
        raise ValueError("首次事件训练与留出根必须非空且不重叠")
    models = {}
    for name, dimension in (("wall_action", 6), ("shape", 15),
                            ("conditional_route", len(_FEATURE_NAMES)),
                            ("route_plus_public_context", len(_FEATURES))):
        beta = _fit(train, dimension)
        models[name] = {
            "feature_names": _FEATURES[:dimension],
            "ridge": _RIDGE,
            "external_oracle_event": _evaluate(hold, beta, dimension),
            "training_apparent_fit": _evaluate(train, beta, dimension),
        }
    return {
        "scope": "offline_oracle_first_event_tail_upper_bound_not_C_alg",
        "training_root_count": len(train),
        "external_root_count": len(hold),
        "warning": "external first event and next observation are future hidden-world results; no deployable event probability or policy produced",
        "models": models,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", type=Path, nargs="+", required=True)
    parser.add_argument("--external", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    print(json.dumps(probe(tuple(args.training), tuple(args.external)),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
