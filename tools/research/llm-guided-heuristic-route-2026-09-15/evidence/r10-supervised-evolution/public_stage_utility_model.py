"""R12-SV1-U：检验完整公开状态能否增益预测阶段前二效用。"""

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
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import public_stage_value_natural as stage_value  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/public-stage-utility-model-01-20260921')
SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/public-stage-value-natural-01-20260921')
DATA = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/public-stage-value-natural-01-20260921/dataset.json')
SOURCE_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/public-stage-value-natural-01-20260921/result.json')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R12-PUBLIC-STAGE-VALUE-EVOLUTION-PLAN-2026-09-21.md')
REAUDIT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/R12-SV1-FAILURE-REAUDIT-2026-09-21.md')
PUBLIC_PREFIXES = ("progress.", "competition.", "public.", "score.relative.")
PANEL_SEEDS = stage_value.PANEL_SEEDS


def digest(path: Path) -> str:
    return stage_value.digest(path)


def _public_features(features: Mapping[str, float]) -> dict[str, float]:
    """只保留赛程、公开榜和桌内积分，作为同容量对照。"""

    return {name: float(value) for name, value in features.items()
            if name.startswith(PUBLIC_PREFIXES)}


def _utility_rows(dataset: Mapping[str, Any], view: str) -> list[dict[str, Any]]:
    """排除 U 识别区间未解析的完整阶段，并构造模型行。"""

    resolved = {row["stage_id"]: float(row["u_low"])
                for row in dataset["stages"] if row["u_low"] == row["u_high"]}
    rows = []
    for source in dataset["rows"]:
        if source["stage_id"] not in resolved:
            continue
        row = dict(source)
        row["features"] = (_public_features(source["features"])
                           if view == "public_score" else dict(source["features"]))
        # 复用已冻结低容量回归器的目标入口；此处标签是精确阶段前二 U。
        row["remaining_stage_score"] = resolved[source["stage_id"]]
        row["utility"] = resolved[source["stage_id"]]
        rows.append(row)
    return rows


def _clip(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _fit(spec: tuple[Any, ...], rows: Sequence[Mapping[str, Any]]) -> Any:
    return stage_value._fit(spec, rows)


def _predict(model: Any, row: Mapping[str, Any]) -> float:
    return _clip(model.predict(row["features"]))


def _brier(actual: Sequence[float], predicted: Sequence[float]) -> float:
    return statistics.fmean((left - right) ** 2 for left, right in zip(actual, predicted))


def _auc(actual: Sequence[float], predicted: Sequence[float]) -> float:
    positive = [value for label, value in zip(actual, predicted) if label == 1.0]
    negative = [value for label, value in zip(actual, predicted) if label == 0.0]
    if not positive or not negative:
        return 0.5
    wins = sum(1.0 if left > right else (0.5 if left == right else 0.0)
               for left in positive for right in negative)
    return wins / (len(positive) * len(negative))


def _ece(actual: Sequence[float], predicted: Sequence[float]) -> float:
    total = len(actual)
    error = 0.0
    for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
        upper = lower + 0.2
        indices = [index for index, value in enumerate(predicted)
                   if lower <= value < upper or (upper == 1.0 and value == 1.0)]
        if indices:
            observed = statistics.fmean(actual[index] for index in indices)
            forecast = statistics.fmean(predicted[index] for index in indices)
            error += len(indices) / total * abs(observed - forecast)
    return error


def _select(train: Sequence[Mapping[str, Any]], seeds: Sequence[int]) -> tuple[str, tuple[Any, ...], list[dict]]:
    scores = []
    for name, spec in stage_value._specs():
        actual_all, predicted_all = [], []
        for held in seeds:
            inner_train = [row for row in train if row["panel_seed"] != held]
            inner_test = [row for row in train if row["panel_seed"] == held]
            model = _fit(spec, inner_train)
            actual_all.extend(float(row["utility"]) for row in inner_test)
            predicted_all.extend(_predict(model, row) for row in inner_test)
        scores.append({"model_spec": name, "inner_brier": _brier(actual_all, predicted_all),
                       "inner_auc": _auc(actual_all, predicted_all), "spec": spec})
    scores.sort(key=lambda item: (item["inner_brier"], -item["inner_auc"], item["model_spec"]))
    winner = scores[0]
    report = [{key: value for key, value in row.items() if key != "spec"} for row in scores]
    return str(winner["model_spec"]), tuple(winner["spec"]), report


def prepare() -> None:
    """冻结目标对齐比较；不新增桌赛或模型调用。"""

    if OUT.exists():
        raise SystemExit("SV1-U 输出已存在，拒绝覆盖")
    source_result = json.loads(SOURCE_RESULT.read_text())
    if source_result.get("status") != "CLOSE_R12_SV1_NO_GENERALIZABLE_STAGE_VALUE_SIGNAL":
        raise ValueError("SV1 原始积分规格尚未按冻结状态结算")
    dataset = json.loads(DATA.read_text())
    resolved = sum(row["u_low"] == row["u_high"] for row in dataset["stages"])
    if resolved != 63:
        raise ValueError(f"预期 63 个精确 U 阶段，得到 {resolved}")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name, authorization_id="r12-sv1-utility-increment-01",
        accounts={}, issued_by="lead", issued_at_utc=batch.search.utc_now(),
        legacy_alias=False)
    authorization.update({
        "issuance_basis": "SV1连续失败后的强制文献复盘：Suphx以最终比赛奖励而非原始积分做全局奖励预测",
        "scope": "只读复用SV1语料；排除1个U=[0,1]来源；公开榜与完整公开状态同容量比较；不确认不发布",
        "max_model_calls": 0, "max_full_tables": 0, "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    manifest = {
        "schema": "r12-public-stage-utility-model/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": guard.capture(source_paths=[Path(__file__), Path(stage_value.__file__),
                                                PLAN, REAUDIT, DATA, SOURCE_RESULT,
                                                _project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "plan": str(PLAN), "plan_sha256": digest(PLAN),
        "failure_reaudit": str(REAUDIT), "failure_reaudit_sha256": digest(REAUDIT),
        "source_dataset": str(DATA), "source_dataset_sha256": digest(DATA),
        "source_result": str(SOURCE_RESULT), "source_result_sha256": digest(SOURCE_RESULT),
        "resolved_stage_count": 63, "excluded_unresolved_stage_count": 1,
        "validation": "leave-one-panel-seed-out；内层其余panel_seed整组选模；同阶段16边界不跨折",
        "target": "精确group_advance_v1前二效用U；u_low!=u_high的阶段整体排除，不补标签",
        "views": {
            "public_score": "赛程进度、CompetitionContext、当前公开阶段/桌积分和相对积分",
            "full_public": "public_score加PlayerObservation手牌/牌河/副露/历史和HangmaRules候选事实",
        },
        "models": {"ridge_lambdas": list(stage_value.RIDGE_LAMBDAS),
                   "tree_depth_min_leaf": [list(item) for item in stage_value.TREE_SPECS]},
        "continue_gate": {
            "brier_reduction_vs_public_score_min": 0.05,
            "heldout_seeds_nonworse_min": 3,
            "layer_brier_nonworse": ["mix:H", "mix:M", "table:1", "table:2"],
        },
        "primary": "边界级Brier；每阶段固定16行且按阶段整组留出",
        "auxiliary": ["ROC-AUC", "五等宽箱ECE", "每阶段最后边界Brier/AUC"],
        "model_calls": 0, "effect_tables": 0, "strength_claim": False,
        "confirmation_eligible": False, "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED_R12_SV1_U", "resolved_stages": resolved},
                     ensure_ascii=False))


def verify(manifest: Mapping[str, Any]) -> None:
    guard.verify(manifest["runtime"])
    for path_key, sha_key in (("plan", "plan_sha256"),
                              ("failure_reaudit", "failure_reaudit_sha256"),
                              ("source_dataset", "source_dataset_sha256"),
                              ("source_result", "source_result_sha256")):
        if digest(Path(str(manifest[path_key]))) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")


def run() -> None:
    """执行两种信息视图的同容量嵌套留出比较。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text())
    verify(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("SV1-U 已执行，拒绝覆盖")
    dataset = json.loads(DATA.read_text())
    view_rows = {view: _utility_rows(dataset, view)
                 for view in ("public_score", "full_public")}
    predictions: dict[str, list[dict[str, Any]]] = {view: [] for view in view_rows}
    folds = []
    for held in PANEL_SEEDS:
        fold: dict[str, Any] = {"held_panel_seed": held, "views": {}}
        for view, rows in view_rows.items():
            train = [row for row in rows if row["panel_seed"] != held]
            test = [row for row in rows if row["panel_seed"] == held]
            name, spec, inner = _select(train, [seed for seed in PANEL_SEEDS if seed != held])
            model = _fit(spec, train)
            actual = [float(row["utility"]) for row in test]
            predicted = [_predict(model, row) for row in test]
            fold["views"][view] = {
                "selected_model_spec": name, "inner_selection": inner,
                "test_count": len(test), "test_brier": _brier(actual, predicted),
                "test_auc": _auc(actual, predicted), "test_ece": _ece(actual, predicted),
            }
            for row, value in zip(test, predicted):
                predictions[view].append({
                    "stage_id": row["stage_id"], "panel_seed": held, "mix": row["mix"],
                    "table_no": row["table_no"], "round_no": row["round_no"],
                    "actual": row["utility"], "predicted": value, "model_spec": name,
                })
        fold["full_nonworse"] = (fold["views"]["full_public"]["test_brier"]
                                  <= fold["views"]["public_score"]["test_brier"])
        folds.append(fold)

    summaries = {}
    for view, rows in predictions.items():
        actual = [float(row["actual"]) for row in rows]
        predicted = [float(row["predicted"]) for row in rows]
        summaries[view] = {"count": len(rows), "brier": _brier(actual, predicted),
                           "auc": _auc(actual, predicted), "ece": _ece(actual, predicted)}
    layers = {}
    predicates = {
        "mix:H": lambda row: row["mix"] == "H", "mix:M": lambda row: row["mix"] == "M",
        "table:1": lambda row: row["table_no"] == 1,
        "table:2": lambda row: row["table_no"] == 2,
    }
    for layer, predicate in predicates.items():
        layers[layer] = {}
        for view, rows in predictions.items():
            selected = [row for row in rows if predicate(row)]
            layers[layer][view] = {
                "count": len(selected),
                "brier": _brier([float(row["actual"]) for row in selected],
                                 [float(row["predicted"]) for row in selected]),
                "auc": _auc([float(row["actual"]) for row in selected],
                             [float(row["predicted"]) for row in selected]),
            }
    endpoints = {}
    for view, rows in predictions.items():
        selected = [row for row in rows if row["table_no"] == 2 and row["round_no"] == 8]
        endpoints[view] = {"count": len(selected),
                           "brier": _brier([float(row["actual"]) for row in selected],
                                           [float(row["predicted"]) for row in selected]),
                           "auc": _auc([float(row["actual"]) for row in selected],
                                       [float(row["predicted"]) for row in selected])}
    public_brier = summaries["public_score"]["brier"]
    full_brier = summaries["full_public"]["brier"]
    checks = {
        "brier_reduction": 1.0 - full_brier / public_brier
                           >= manifest["continue_gate"]["brier_reduction_vs_public_score_min"],
        "heldout_seeds_nonworse": sum(bool(fold["full_nonworse"]) for fold in folds)
                                   >= manifest["continue_gate"]["heldout_seeds_nonworse_min"],
        "layers_nonworse": all(layer["full_public"]["brier"]
                               <= layer["public_score"]["brier"] for layer in layers.values()),
    }
    passed = all(checks.values())
    result = {
        "schema": "r12-public-stage-utility-model-result/1",
        "status": ("PASS_R12_SV1_U_INCREMENTAL_PUBLIC_UTILITY_SIGNAL" if passed
                   else "CLOSE_R12_PUBLIC_UTILITY_MODEL_NO_INCREMENTAL_SIGNAL"),
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "summaries": summaries,
        "brier_reduction": 1.0 - full_brier / public_brier,
        "folds": folds, "layers": layers, "stage_endpoint": endpoints,
        "gate_checks": checks, "predictions": predictions,
        "strength_claim": False, "confirmation_eligible": False, "release_eligible": False,
        "next": ("仅进入短截断预算分配验证，不作为候选强度或发布证据" if passed
                 else "关闭学习价值模型；执行MF0历史第一桌多保真回溯"),
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"status": result["status"], "summaries": summaries,
                      "brier_reduction": result["brier_reduction"],
                      "gate_checks": checks}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run}[args.command]()


if __name__ == "__main__":
    main()
