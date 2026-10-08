"""AV2-2：按完整面板留出选择多未来顺序平均教师的低容量模型。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import claim_value_model as av1_model  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-value-averaged-model-01-20260921')
DATA_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-value-averaged-02-20260921')
DATA = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-value-averaged-02-20260921/dataset.json')
DATA_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-value-averaged-02-20260921/result.json')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R10-AVERAGED-TEACHER-EVOLUTION-PLAN-2026-09-21.md')
RIDGE_LAMBDAS = (0.1, 1.0, 10.0)
TREE_CONFIGS = ((1, 8), (2, 8), (3, 8), (2, 12), (3, 12))
MIXES = ("H", "M")


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _put(out: dict[str, float], name: str, value: Any) -> None:
    """写入有限数值；沿用 AV1 投影的数值校验。"""

    av1_model._put(out, name, value)


def _known_value(value: dict) -> float | None:
    """只返回规则模块明确给出的数值。"""

    raw = value.get("value") if value.get("known") else None
    return float(raw) if isinstance(raw, (int, float, bool)) else None


def _summary(out: dict[str, float], prefix: str, values: list[float]) -> None:
    """为规则事实数组增加浅层模型可直接使用的自然聚合。"""

    _put(out, prefix + ".count", len(values))
    if not values:
        return
    _put(out, prefix + ".min", min(values))
    _put(out, prefix + ".max", max(values))
    _put(out, prefix + ".mean", statistics.fmean(values))
    _put(out, prefix + ".sum", sum(values))
    _put(out, prefix + ".range", max(values) - min(values))


def flatten_features(encoded: dict) -> dict[str, float]:
    """沿用完整 AV1 投影，并补充不重算规则的自然聚合。

    聚合只求和或统计 ``HangmaRules`` 已给出的有效牌、后继分支、条件路线
    和公开牌计数，便于浅树直接使用；不读取来源、对手池或标签。
    """

    out = av1_model.flatten_features(encoded)
    observation = encoded["observation"]
    hand = [float(value) for value in observation["my_hand_counts"]]
    _put(out, "aggregate.hand.unique", sum(value > 0 for value in hand))
    _put(out, "aggregate.hand.pairs", sum(value == 2 for value in hand))
    _put(out, "aggregate.hand.triplets", sum(value == 3 for value in hand))
    _put(out, "aggregate.hand.quads", sum(value == 4 for value in hand))
    _put(out, "aggregate.hand.concentration", sum(value * value for value in hand))
    discard_totals = [sum(float(value) for value in item["counts"]) for item in observation["discards"]]
    _summary(out, "aggregate.discards_by_seat", discard_totals)
    meld_counts = [float(len(items)) for items in observation["melds"]]
    _summary(out, "aggregate.melds_by_seat", meld_counts)
    _put(out, "aggregate.opponent_open_melds", sum(meld_counts[1:]))

    claim = encoded["claim"]
    claim_tile_indices = [int(value) for value in claim["tiles"]]
    _put(out, "aggregate.claim.hand_multiplicity", sum(hand[index] for index in claim_tile_indices))
    facts = claim["facts"]
    if facts.get("known"):
        for name in ("useful_tiles", "standard_useful_tiles", "seven_pairs_useful_tiles"):
            item = facts[name]
            if item.get("known"):
                remaining = [float(value) for value in item["remaining_by_tile"]]
                _put(out, f"aggregate.{name}.support", sum(remaining))
                _put(out, f"aggregate.{name}.kinds", sum(value > 0 for value in remaining))
        branches = facts["followup_branches"]
        if branches.get("known"):
            values = branches["value"]
            supports = [
                value
                for item in values
                for value in [_known_value(item["support_remaining"])]
                if value is not None
            ]
            combined = [
                value
                for item in values
                for value in [_known_value(item["combined_shanten"])]
                if value is not None
            ]
            standard = [
                value
                for item in values
                for value in [_known_value(item["standard_shanten"])]
                if value is not None
            ]
            seven_pairs = [
                value
                for item in values
                for value in [_known_value(item["seven_pairs_shanten"])]
                if value is not None
            ]
            _summary(out, "aggregate.followup.support", supports)
            _summary(out, "aggregate.followup.combined_shanten", combined)
            _summary(out, "aggregate.followup.standard_shanten", standard)
            _summary(out, "aggregate.followup.seven_pairs_shanten", seven_pairs)
            _put(out, "aggregate.followup.positive_support", sum(value > 0 for value in supports))

    value_facts = claim["value_facts"]
    if value_facts.get("known"):
        routes = value_facts["routes"]
        route_shanten = [float(item["shanten"]) for item in routes]
        route_support = [
            float(sum(item["useful_tiles"]["remaining_by_tile"]))
            for item in routes if item["useful_tiles"].get("known")
        ]
        route_fan = [float(item["settlement"]["fan"]) for item in routes]
        route_own_delta = [float(item["settlement"]["score_delta"][0]) for item in routes]
        _summary(out, "aggregate.routes.shanten", route_shanten)
        _summary(out, "aggregate.routes.support", route_support)
        _summary(out, "aggregate.routes.fan", route_fan)
        _summary(out, "aggregate.routes.own_delta", route_own_delta)
    return out


def metrics(rows: list[dict], decisions: list[bool]) -> dict:
    """以未鸣牌收益为零，汇总平均教师下的策略、域和动作覆盖。"""

    auxiliary = [
        float(row["labels"]["focal_stage_score_delta_mean"]) if decision else 0.0
        for row, decision in zip(rows, decisions)
    ]
    primary = [
        float(row["labels"]["u_low_delta_mean"]) if decision else 0.0
        for row, decision in zip(rows, decisions)
    ]
    positives = [float(row["labels"]["focal_stage_score_delta_mean"]) > 0 for row in rows]
    positive_total = sum(positives)
    negative_total = len(rows) - positive_total
    true_positive = sum(decision and positive for decision, positive in zip(decisions, positives))
    true_negative = sum(not decision and not positive for decision, positive in zip(decisions, positives))
    action_types = Counter(
        str(row["claim_action_key"]).split(":", 1)[0]
        for row, decision in zip(rows, decisions) if decision
    )
    result = {
        "rows": len(rows),
        "claim_count": sum(decisions),
        "pass_count": len(rows) - sum(decisions),
        "claimed_action_types": dict(sorted(action_types.items())),
        "auxiliary_policy_mean": statistics.fmean(auxiliary),
        "primary_policy_mean": statistics.fmean(primary),
        "balanced_accuracy": 0.5 * (
            (true_positive / positive_total if positive_total else 0.0)
            + (true_negative / negative_total if negative_total else 0.0)
        ),
    }
    by_mix = {}
    for mix in MIXES:
        indices = [index for index, row in enumerate(rows) if row["group"]["mix"] == mix]
        by_mix[mix] = {
            "rows": len(indices),
            "claim_count": sum(decisions[index] for index in indices),
            "auxiliary_policy_mean": statistics.fmean(auxiliary[index] for index in indices),
            "primary_policy_mean": statistics.fmean(primary[index] for index in indices),
        }
    result["by_mix"] = by_mix
    return result


def _cross_validate(
    rows: list[dict], vectors: list[dict[str, float]], fit: Callable
) -> tuple[list[float], list[dict]]:
    """每折完整留出一个面板种子，训练过程不读取 H/M。"""

    predictions = [0.0] * len(rows)
    folds = []
    seeds = sorted({row["group"]["panel_seed"] for row in rows})
    for seed in seeds:
        train = [index for index, row in enumerate(rows) if row["group"]["panel_seed"] != seed]
        valid = [index for index, row in enumerate(rows) if row["group"]["panel_seed"] == seed]
        raw_targets = [
            float(rows[index]["labels"]["focal_stage_score_delta_mean"])
            for index in train
        ]
        targets, scale = av1_model._training_targets(raw_targets)
        model = fit([vectors[index] for index in train], targets)
        fold_predictions = [model.predict(vectors[index]) for index in valid]
        for index, prediction in zip(valid, fold_predictions):
            predictions[index] = prediction
        decisions = [value > 0 for value in fold_predictions]
        folds.append({
            "held_out_panel_seed": seed,
            "training_rows": len(train),
            "validation_rows": len(valid),
            "target_scale": scale,
            "metrics": metrics([rows[index] for index in valid], decisions),
        })
    return predictions, folds


def prepare() -> None:
    """冻结平均教师数据、自然聚合、候选模型和稳健选择门。"""

    if OUT.exists():
        raise SystemExit("AV2-2 目录已存在；拒绝覆盖")
    data_result = batch.read(DATA_RESULT)
    if data_result["status"] != "PASS_AV2_1_FOR_GROUPED_MODELING":
        raise ValueError("AV2-1 未授权建模")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-av2-averaged-action-value-model",
        authorization_id="r10-av2-averaged-action-value-model-20260921",
        accounts={"tables_full": 0, "model_fits": len(RIDGE_LAMBDAS) * 2 + len(TREE_CONFIGS) * 2},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "AV2-1取得64个全新来源、八未来顺序平均且机械全绿的动作价值样本",
        "scope": "只在AV2-1按完整panel_seed两折留出；H/M只作结果分层，不进入训练特征；零新桌赛",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=[
        Path(__file__), Path(av1_model.__file__), DATA, DATA_RESULT, PLAN,
        _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
    ])
    manifest = {
        "schema": "r10-av2-averaged-action-value-model/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "data": str(DATA),
        "data_sha256": digest(DATA),
        "data_result": str(DATA_RESULT),
        "data_result_sha256": digest(DATA_RESULT),
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "feature_projection": "完整AV1公开状态投影，加规则有效牌、后继分支、条件路线和公开牌计数的sum/min/max/mean自然聚合；不重算麻将规则；无标签、来源、面板种子或对手池",
        "target": "八未来顺序辅助积分均值；训练折非零绝对值中位数缩放并asinh；决策阈值固定为预测值>0",
        "folds": "leave-one-panel-seed-out；两折各32个未见快照；同一快照八条轨迹已先聚合且永不跨折",
        "candidates": {
            "linear_ridge_lambda": list(RIDGE_LAMBDAS),
            "regression_tree_depth_min_leaf": [list(item) for item in TREE_CONFIGS],
        },
        "selection_gate": {
            "overall": "辅助策略均值>0",
            "mix_stability": "H/M辅助策略均值和主晋级下界策略均值均>=0",
            "source_stability": "两个完整留出panel_seed的辅助策略均值均>0",
            "nondegenerate": "同时选择pass和claim，且被选claim覆盖chi和peng",
            "baseline": "min(H,M辅助策略均值)严格大于always-claim的对应最差层",
            "tie_break": "依次最大化最差H/M辅助、最差留出seed辅助、总体辅助、平衡准确率，再按candidate_id",
            "meaning": "通过只授权第三个全新面板上的八顺序动作验证，不是完整阶段或赛事强度证据",
        },
        "llm_calls": 0,
        "effect_tables": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({
        "status": "PREPARED_AV2_2",
        "candidate_count": len(RIDGE_LAMBDAS) + len(TREE_CONFIGS),
    }, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """核对平均教师数据、计划和建模代码。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (
        ("data", "data_sha256"),
        ("data_result", "data_result_sha256"),
        ("plan", "plan_sha256"),
    ):
        if digest(Path(manifest[path_key])) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")


def run() -> None:
    """执行预登记低容量模型并裁定是否进入独立动作验证。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("AV2-2 已执行；拒绝覆盖")
    rows = batch.read(DATA)["rows"]
    vectors = [flatten_features(row["features"]) for row in rows]
    candidate_specs: list[tuple[str, Callable]] = []
    for lam in RIDGE_LAMBDAS:
        candidate_specs.append((
            f"ridge:lambda={lam:g}",
            lambda x, y, lam=lam: av1_model.fit_ridge(x, y, lam),
        ))
    for depth, min_leaf in TREE_CONFIGS:
        candidate_specs.append((
            f"tree:depth={depth}:min_leaf={min_leaf}",
            lambda x, y, depth=depth, min_leaf=min_leaf: av1_model.fit_tree(
                x, y, depth, min_leaf
            ),
        ))

    always_pass = metrics(rows, [False] * len(rows))
    always_claim = metrics(rows, [True] * len(rows))
    always_claim_worst = min(
        always_claim["by_mix"][mix]["auxiliary_policy_mean"] for mix in MIXES
    )
    all_results = []
    for candidate_id, fitter in candidate_specs:
        predictions, folds = _cross_validate(rows, vectors, fitter)
        decisions = [value > 0 for value in predictions]
        score = metrics(rows, decisions)
        fold_aux = [fold["metrics"]["auxiliary_policy_mean"] for fold in folds]
        action_types = score["claimed_action_types"]
        worst_mix = min(
            score["by_mix"][mix]["auxiliary_policy_mean"] for mix in MIXES
        )
        passes = bool(
            score["auxiliary_policy_mean"] > 0
            and all(score["by_mix"][mix]["auxiliary_policy_mean"] >= 0 for mix in MIXES)
            and all(score["by_mix"][mix]["primary_policy_mean"] >= 0 for mix in MIXES)
            and all(value > 0 for value in fold_aux)
            and 0 < score["claim_count"] < len(rows)
            and action_types.get("chi", 0) > 0
            and action_types.get("peng", 0) > 0
            and worst_mix > always_claim_worst
        )
        all_results.append({
            "candidate_id": candidate_id,
            "folds": folds,
            "metrics": score,
            "worst_mix_auxiliary": worst_mix,
            "worst_held_out_seed_auxiliary": min(fold_aux),
            "passes_selection_gate": passes,
        })

    eligible = [item for item in all_results if item["passes_selection_gate"]]
    eligible.sort(key=lambda item: (
        -item["worst_mix_auxiliary"],
        -item["worst_held_out_seed_auxiliary"],
        -item["metrics"]["auxiliary_policy_mean"],
        -item["metrics"]["balanced_accuracy"],
        item["candidate_id"],
    ))
    selected = eligible[0] if eligible else None
    final_model = None
    if selected is not None:
        fitter = dict(candidate_specs)[selected["candidate_id"]]
        raw_targets = [
            float(row["labels"]["focal_stage_score_delta_mean"]) for row in rows
        ]
        targets, scale = av1_model._training_targets(raw_targets)
        model = fitter(vectors, targets)
        final_model = {
            "candidate_id": selected["candidate_id"],
            "target_scale": scale,
            "decision_threshold": 0.0,
            "feature_count": len({name for row in vectors for name in row}),
            "model": model.artifact(),
        }

    status = (
        "PASS_AV2_2_MODEL_FOR_INDEPENDENT_ACTION_VALIDATION"
        if selected is not None
        else "CLOSE_AV2_2_AND_REVIEW_AVERAGED_TEACHER"
    )
    result = {
        "schema": "r10-av2-averaged-action-value-model-result/1",
        "status": status,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "dataset": {
            "rows": len(rows),
            "projected_feature_count": len({name for row in vectors for name in row}),
            "panel_seeds": sorted({row["group"]["panel_seed"] for row in rows}),
        },
        "baselines": {"always_pass": always_pass, "always_claim": always_claim},
        "candidates": all_results,
        "selected": selected,
        "final_model": final_model,
        "next": (
            "冻结特征、模型和零阈值，在第三个全新panel_seed上按H/M各16个自然机会、每机会八未来顺序独立验证"
            if selected is not None
            else "停止在本批追加阈值或模型；回读Suphx、rollout/POMDP、Lexicase/MEoH与杭麻动作事实，判断是否需要历史一致隐藏世界教师或转动作族"
        ),
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    verify_inputs(manifest)
    print(json.dumps({
        "status": status,
        "baselines": result["baselines"],
        "candidates": [
            {
                "candidate_id": item["candidate_id"],
                "metrics": item["metrics"],
                "worst_held_out_seed_auxiliary": item["worst_held_out_seed_auxiliary"],
                "passes": item["passes_selection_gate"],
            }
            for item in all_results
        ],
        "selected": None if selected is None else selected["candidate_id"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
