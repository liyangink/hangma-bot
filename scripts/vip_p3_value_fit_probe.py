"""P3 统一积分轴的离线可学性预检；不生成线上策略产物。

当前胡净分始终由规则精确给出；非胡的末端积分只用行动前可见
事实回归。按观察根中心化，避免把同一根的动作世界当独立样本。
这仍是冻结参考续打者的完整单局标签，不是新 VIP 自身价值。
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness, ValueAnalysisLimits, ValueCoverage
from hangma_bot.kernel.actions import Chi, Discard, Gang, Hu, Pass, Peng
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.serialization import observation_from_json


_SCOPE = "P3_offline_teacher_labels_only_not_candidate_policy_value"
_LIMITS = ValueAnalysisLimits(max_expansions=8192)
_RIDGE = 10.0  # 先验固定研究收缩；本预检不按留出结果调参。
_FEATURE_NAMES = (
    "non_hu", "chi", "peng", "gang", "pass", "wall_fraction",
    "shanten", "standard_shanten", "seven_shanten", "seven_available",
    "useful_capacity", "standard_capacity", "seven_capacity",
    "baotou", "baotou_unknown", "one_draw_witness",
    "one_draw_capacity", "one_draw_high_capacity", "one_draw_max_fan",
    "one_draw_capacity_net",
)
_BASE_COUNT = 6
_SHAPE_COUNT = 15


@dataclass(frozen=True)
class _Root:
    """一个行动前玩家观察；各动作共享相同编号的隐藏世界。"""

    seed: int
    root_id: str
    source: str
    phase: str
    keys: tuple[str, ...]
    features: tuple[tuple[float, ...], ...]
    exact_hu: tuple[float, ...]
    observed_net: tuple[float, ...]  # 每动作同隐藏世界平均本人单局净积分
    shape_key: str
    sample_count: int


def _one_draw_witness(candidate, seat: int) -> tuple[float, ...]:
    """一条一致后续弃牌／摸牌来源路径的公开容量特征，不当作概率。"""

    facts = candidate.value_facts
    if facts is None or facts.coverage is not ValueCoverage.COMPLETE:
        raise ValueError("候选一次摸牌分值见证不完整")
    paths: dict[tuple[str, str], dict[str, tuple[int, int, int]]] = {}
    for route in facts.routes:
        path = (route.conditions.draw_kind, route.followup_discard or "")
        tiles = paths.setdefault(path, {})
        net = route.conditional_settlement.score_delta[seat]
        fan = route.conditional_settlement.fan
        for tile in route.useful_tiles:
            old = tiles.get(tile.code)
            replacement = (fan, net, tile.remaining_estimate)
            if old is None or (fan, net) > old[:2]:
                tiles[tile.code] = replacement
    if not paths:
        return (0.0, 0.0, 0.0, 0.0, 0.0)
    summaries = []
    for path, tiles in paths.items():
        total = sum(row[2] for row in tiles.values())
        high = sum(row[2] for row in tiles.values() if row[0] >= 4)
        max_fan = max(row[0] for row in tiles.values())
        capacity_net = sum(row[1] * row[2] for row in tiles.values())
        summaries.append((capacity_net, total, high, max_fan, path))
    weighted, total, high, fan, _ = max(summaries)
    return (1.0, total / 100.0, high / 100.0,
            fan / 16.0, weighted / 1000.0)


def _features(candidate, observation) -> tuple[tuple[float, ...], float]:
    """只读本座观察与 HangmaRules 事实；当前胡不交给回归器估值。"""

    if isinstance(candidate.action, Hu):
        value = candidate.value_facts
        settlement = value.immediate_settlement if value is not None else None
        if settlement is None:
            raise ValueError("当前胡缺同源精确四座结算")
        return (0.0,) * len(_FEATURE_NAMES), float(
            settlement.score_delta[observation.seat])
    facts = candidate.facts
    if (facts is None or facts.completeness is not RuleCompleteness.COMPLETE
            or facts.fact_kind is not CandidateFactKind.HAND_PROGRESS
            or facts.shanten_after is None):
        raise ValueError("非胡动作缺完整牌效事实")
    if facts.standard_shanten_after is None:
        raise ValueError("非胡动作缺普通型向听")
    support = sum(item.remaining_estimate for item in facts.useful_tiles)
    standard = (sum(item.remaining_estimate for item in facts.standard_useful_tiles)
                if facts.standard_useful_tiles is not None else 0)
    seven = (sum(item.remaining_estimate for item in facts.seven_pairs_useful_tiles)
             if facts.seven_pairs_useful_tiles is not None else 0)
    wall = observation.remaining_tile_count
    action = candidate.action
    row = (
        1.0, float(isinstance(action, Chi)), float(isinstance(action, Peng)),
        float(isinstance(action, Gang)), float(isinstance(action, Pass)),
        0.0 if wall is None else wall / 80.0,
        facts.shanten_after / 4.0, facts.standard_shanten_after / 4.0,
        0.0 if facts.seven_pairs_shanten_after is None
        else facts.seven_pairs_shanten_after / 4.0,
        float(facts.seven_pairs_shanten_after is not None),
        support / 100.0, standard / 100.0, seven / 100.0,
        float(facts.baotou_after is True), float(facts.baotou_after is None),
        *_one_draw_witness(candidate, observation.seat),
    )
    if len(row) != len(_FEATURE_NAMES):
        raise ValueError("预检特征维度漂移")
    return row, 0.0


def _shape_key(analysis, phase: str) -> str:
    """复现冻结基础续打者的当前首选，仅用作离线比较基准。"""

    if phase.startswith("response_"):
        choices = [item for item in analysis.legal_candidates
                   if isinstance(item.action, Pass)]
        if len(choices) != 1:
            raise ValueError("响应窗缺唯一基础过牌")
        return choices[0].action_key
    win = [item for item in analysis.legal_candidates
           if isinstance(item.action, Hu)]
    if win:
        return win[0].action_key
    discards = [item for item in analysis.legal_candidates
                if isinstance(item.action, Discard)]
    if not discards:
        raise ValueError("基础续打者缺可选弃牌")
    return min(discards, key=lambda item: (
        item.facts.shanten_after,
        -sum(tile.remaining_estimate for tile in item.facts.useful_tiles),
        item.action_key,
    )).action_key


def _load(path: Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def _roots(paths: tuple[Path, ...]) -> tuple[_Root, ...]:
    """重建规则事实；教师隐藏世界只能出现在结果标签，不能入特征。"""

    rules = HangmaRules(RuleConfig("hangma-mvp-v10-public-counts", 1, False))
    roots = []
    seen = set()
    for path in paths:
        report = _load(path)
        if (report.get("scope") != _SCOPE
                or report.get("continuation_reference", "shape") != "shape"
                or report.get("rule_config") !=
                {"BaseScore": 1, "YouCaiBiKao": False}):
            raise ValueError("本预检只消费目标配置的冻结 shape 续打教师")
        for row in report["rows"]:
            root_id = row["root_id"]
            if root_id in seen:
                raise ValueError("教师文件之间重复观察根")
            seen.add(root_id)
            observation = observation_from_json(row["observation"])
            if hashlib.sha256(repr(observation).encode("utf-8")).hexdigest() != root_id:
                raise ValueError("教师观察摘要与玩家可见状态不一致")
            analysis = rules.analyze(observation, value_limits=_LIMITS)
            keys = tuple(candidate.action_key for candidate in analysis.legal_candidates)
            if (analysis.completeness is not RuleCompleteness.COMPLETE
                    or keys != tuple(row["legal_action_keys"])
                    or set(row["outcomes_by_action"]) != set(keys)):
                raise ValueError("同观察的规则合法动作与教师账不一致")
            scores = []
            features = []
            exact = []
            sample_count = row["sample_count"]
            if type(sample_count) is not int or sample_count < 1:
                raise ValueError("教师同根隐藏世界数无效")
            for candidate in analysis.legal_candidates:
                feat, hu = _features(candidate, observation)
                outcomes = row["outcomes_by_action"][candidate.action_key]
                if [item["sample"] for item in outcomes] != list(range(sample_count)):
                    raise ValueError("同根相关隐藏世界编号不守恒")
                values = []
                for item in outcomes:
                    terminal = item["terminal"]
                    delta = terminal["score_delta"]
                    if (len(delta) != 4 or any(type(v) is not int for v in delta)
                            or sum(delta) != 0):
                        raise ValueError("教师终局四座积分不守恒")
                    values.append(delta[observation.seat])
                if isinstance(candidate.action, Hu) and any(
                    value != hu for value in values
                ):
                    raise ValueError("教师当前胡结局与规则即时结算不一致")
                features.append(feat)
                exact.append(hu)
                scores.append(sum(values) / sample_count)
            roots.append(_Root(
                seed=row["seed"], root_id=root_id, source=path.name,
                phase=observation.phase, keys=keys,
                features=tuple(features), exact_hu=tuple(exact),
                observed_net=tuple(scores),
                shape_key=_shape_key(analysis, observation.phase),
                sample_count=sample_count,
            ))
    return tuple(roots)


def _solve(gram: list[list[float]], rhs: list[float]) -> tuple[float, ...]:
    """带部分选主元的岭回归正规方程；维度固定且正则保证非奇异。"""

    n = len(rhs)
    rows = [gram[i][:] + [rhs[i]] for i in range(n)]
    for pivot in range(n):
        best = max(range(pivot, n), key=lambda i: abs(rows[i][pivot]))
        rows[pivot], rows[best] = rows[best], rows[pivot]
        divisor = rows[pivot][pivot]
        if abs(divisor) < 1e-12:
            raise ValueError("岭回归矩阵数值奇异")
        for col in range(pivot, n + 1):
            rows[pivot][col] /= divisor
        for index in range(n):
            if index == pivot:
                continue
            factor = rows[index][pivot]
            for col in range(pivot, n + 1):
                rows[index][col] -= factor * rows[pivot][col]
    return tuple(row[-1] for row in rows)


def _fit(roots: tuple[_Root, ...], dimension: int) -> tuple[float, ...]:
    """每观察根总权重为一；精确胡项固定，不由样本回归。"""

    gram = [[_RIDGE if i == j else 0.0 for j in range(dimension)]
            for i in range(dimension)]
    rhs = [0.0] * dimension
    for root in roots:
        count = len(root.keys)
        means = [sum(row[i] for row in root.features) / count
                 for i in range(dimension)]
        residuals = [value - exact for value, exact in
                     zip(root.observed_net, root.exact_hu)]
        center = sum(residuals) / count
        for feature, residual in zip(root.features, residuals):
            x = [feature[i] - means[i] for i in range(dimension)]
            y = residual - center
            for i in range(dimension):
                rhs[i] += x[i] * y / count
                for j in range(dimension):
                    gram[i][j] += x[i] * x[j] / count
    return _solve(gram, rhs)


def _evaluate(roots: tuple[_Root, ...], beta: tuple[float, ...],
              dimension: int) -> dict:
    """统计模型首选与 shape 首选在同世界完整单局的根级配对差。"""

    deltas = []
    selected = []
    hu_wait = 0
    changed = 0
    for root in roots:
        estimates = [exact + sum(beta[i] * feature[i]
                                 for i in range(dimension))
                     for exact, feature in zip(root.exact_hu, root.features)]
        best = min(range(len(root.keys)), key=lambda i: (
            -round(estimates[i], 8),
            root.keys[i] != "hu", root.keys[i],
        ))
        shape = root.keys.index(root.shape_key)
        delta = root.observed_net[best] - root.observed_net[shape]
        deltas.append(delta)
        selected.append({"seed": root.seed, "root_id": root.root_id,
                         "source": root.source, "chosen": root.keys[best],
                         "shape": root.shape_key, "mean_net_delta": delta,
                         "sample_count": root.sample_count})
        changed += root.keys[best] != root.shape_key
        hu_wait += root.shape_key == "hu" and root.keys[best] != "hu"
    return {
        "root_count": len(roots), "mean_paired_net_delta": sum(deltas) / len(deltas),
        "positive_roots": sum(delta > 0 for delta in deltas),
        "negative_roots": sum(delta < 0 for delta in deltas),
        "zero_roots": sum(delta == 0 for delta in deltas),
        "changed_action_roots": changed,
        "worst_root_delta": min(deltas), "best_root_delta": max(deltas),
        "deferred_current_hu_roots": hu_wait,
        "rows": selected,
    }


def probe(training: tuple[Path, ...], external: tuple[Path, ...]) -> dict:
    """旧根逐根留出、新根整体留出；只诊断可学性，不产出部署模型。"""

    train_roots = _roots(training)
    external_roots = _roots(external)
    if not train_roots or not external_roots:
        raise ValueError("训练与外部留出教师根均须非空")
    if {root.root_id for root in train_roots} & {
        root.root_id for root in external_roots
    }:
        raise ValueError("训练与外部留出共享观察根")
    models = {}
    for name, dimension in (("wall_action", _BASE_COUNT),
                            ("shape", _SHAPE_COUNT),
                            ("conditional_route", len(_FEATURE_NAMES))):
        external_beta = _fit(train_roots, dimension)
        external_result = _evaluate(external_roots, external_beta, dimension)
        loo_rows = []
        for index, root in enumerate(train_roots):
            beta = _fit(train_roots[:index] + train_roots[index + 1:], dimension)
            loo_rows.append(_evaluate((root,), beta, dimension)["rows"][0])
        loo_deltas = [row["mean_net_delta"] for row in loo_rows]
        models[name] = {
            "feature_names": _FEATURE_NAMES[:dimension],
            "ridge": _RIDGE,
            "training_leave_one_root_out": {
                "root_count": len(loo_rows),
                "mean_paired_net_delta": sum(loo_deltas) / len(loo_deltas),
                "positive_roots": sum(value > 0 for value in loo_deltas),
                "negative_roots": sum(value < 0 for value in loo_deltas),
                "zero_roots": sum(value == 0 for value in loo_deltas),
                "changed_action_roots": sum(
                    row["chosen"] != row["shape"] for row in loo_rows),
                "deferred_current_hu_roots": sum(
                    row["shape"] == "hu" and row["chosen"] != "hu"
                    for row in loo_rows),
                "worst_root_delta": min(loo_deltas),
                "best_root_delta": max(loo_deltas),
            },
            "new_root_holdout": external_result,
            "coefficients_trained_on_old_roots": dict(
                zip(_FEATURE_NAMES[:dimension], external_beta)),
        }
    return {
        "scope": "offline_frozen_shape_tail_regression_feasibility_not_C_alg",
        "target": "focal_hand_net_points_under_shape_continuation",
        "training_sources": [str(path) for path in training],
        "external_sources": [str(path) for path in external],
        "old_root_count": len(train_roots),
        "new_root_count": len(external_roots),
        "exact_current_hu": True,
        "root_weighting": "one_per_PlayerObservation; action mean within root",
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
