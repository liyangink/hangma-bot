"""CF3-B：按麻将前瞻/目标分解文献校准单特征可解释鸣牌门控器。"""

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
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import claim_counterfactual_variance as cf2  # noqa: E402
import claim_counterfactual_topup as cf2b  # noqa: E402
import claim_gate_calibration as cf3a  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-gate-stump-01-20260921')
CF2_RESULT = cf2.OUT / "result.json"
CF2B_RESULT = cf2b.OUT / "result.json"
CF3A_RESULT = cf3a.OUT / "result.json"
FEATURES = (
    "route_raw",
    "route_margin",
    "base_score",
    "route_valid_count",
    "wealth_part",
    "wall_remaining",
    "round_no",
    "is_peng",
    "is_dealer",
    "score_to_leader",
    "score_to_opponent_mean",
    "pass_support",
    "claim_support",
    "support_delta",
    "followup_count",
    "best_followup_count",
    "best_followup_min_support",
    "best_followup_max_support",
    "all_followup_max_support",
    "all_followup_spread",
    "claim_route_count",
    "route_count_delta",
)


def digest(path: Path) -> str:
    """返回冻结文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def support(facts: dict) -> float:
    """求候选一步有效牌的公开未见张数总和。"""

    return float(sum(item["remaining_estimate"] for item in facts.get("useful_tiles") or []))


def route_summary(value_facts: dict | None, seat: int) -> tuple[int, int]:
    """返回条件路线数和其中最大已公开副露数。"""

    routes = (value_facts or {}).get("routes") or []
    melds = [int(item["conditions"]["meld_count"]) for item in routes]
    return len(routes), max(melds, default=0)


def extract_row(hit: dict) -> dict:
    """从已捕获玩家可见事实抽取文献驱动的低维候选特征。"""

    visible = hit["witness"]["observable_features"]
    pass_facts = visible["pass"]["facts"]
    claim_facts = visible["claim"]["facts"]
    trace = visible["claim"]["route_score_trace"]["detail"]
    branches = claim_facts.get("followup_branches") or []
    best_shanten = claim_facts["shanten_after"]
    best = [item for item in branches if item.get("combined_shanten") == best_shanten]
    all_support = [int(item["support_remaining"]) for item in branches]
    best_support = [int(item["support_remaining"]) for item in best]
    seat = int(visible["my_seat"])
    scores = [int(value) for value in visible["scores_by_seat"]]
    own_score = scores[seat]
    opponent_scores = [value for index, value in enumerate(scores) if index != seat]
    pass_routes, pass_melds = route_summary(visible["pass"]["value_facts"], seat)
    claim_routes, claim_melds = route_summary(visible["claim"]["value_facts"], seat)
    if not branches or not best or not all_support or not best_support:
        raise ValueError("CF3-B 只接受吃碰后弃牌分支事实完整的样本")
    features = {
        "route_raw": float(trace["route_raw"]),
        "route_margin": float(trace["route_raw"]) - float(trace["route_low"]),
        "base_score": float(trace["base_score"]),
        "route_valid_count": float(trace["route_valid_count"]),
        "wealth_part": float(trace["wealth_part"]),
        "wall_remaining": float(visible["remaining_tile_count"]),
        "round_no": float(visible["round_no"]),
        "is_peng": float(str(hit["witness"]["claim_action_key"]).startswith("peng:")),
        "is_dealer": float(visible["dealer_seat"] == seat),
        "score_to_leader": float(own_score - max(scores)),
        "score_to_opponent_mean": float(own_score - statistics.fmean(opponent_scores)),
        "pass_support": support(pass_facts),
        "claim_support": support(claim_facts),
        "support_delta": support(claim_facts) - support(pass_facts),
        "followup_count": float(len(branches)),
        "best_followup_count": float(len(best)),
        "best_followup_min_support": float(min(best_support)),
        "best_followup_max_support": float(max(best_support)),
        "all_followup_max_support": float(max(all_support)),
        "all_followup_spread": float(max(all_support) - min(all_support)),
        "claim_route_count": float(claim_routes),
        "route_count_delta": float(claim_routes - pass_routes),
    }
    if set(features) != set(FEATURES):
        raise ValueError("CF3-B 特征集合漂移")
    auxiliary = float(hit["label"]["focal_stage_score_delta"])
    return {
        "row_id": "{0}:{1}".format(hit["mix"], hit["source_root_id"]),
        "features": features,
        "labels": {
            "auxiliary_stage_score_delta": auxiliary,
            "auxiliary_positive": auxiliary > 0,
            "primary_u_low_delta": float(hit["label"]["u_low_delta"]),
        },
    }


def prepare() -> None:
    """冻结文献驱动特征、单阈值模型族、留一选择和外部验证门槛。"""

    if OUT.exists():
        raise SystemExit("CF3-B 目录已存在；拒绝覆盖")
    if batch.read(CF3A_RESULT)["status"] != "CLOSE_CF3A_GATE_AND_REVIEW_FEATURES":
        raise ValueError("CF3-A 未形成需复盘的关闭裁定")
    hits = list(batch.read(CF2_RESULT)["hits"]) + list(batch.read(CF2B_RESULT)["hits"])
    rows = [extract_row(hit) for hit in hits]
    if len(rows) != 32 or len({row["row_id"] for row in rows}) != 32:
        raise ValueError("CF3-B 需要32个唯一开发来源根")
    OUT.mkdir(parents=True)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), {
        "schema": "r10-claim-gate-stump-dataset/1",
        "rows": rows,
        "feature_names": list(FEATURES),
        "sources": [str(CF2_RESULT), str(CF2B_RESULT)],
        "note": "32根全部是开发数据；CF3-A已看验证根也并入训练，CF3-B必须使用新panel_seed外部验证",
    })
    authorization = batch.unified_document(
        batch_label="r10-claim-gate-stump-cf3b",
        authorization_id="r10-claim-gate-stump-cf3b-20260921",
        accounts={},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "CF3-A线性压缩门控退化为总鸣；按Suphx前瞻特征、Mxplainer/Tjong目标-动作分解补充后继自由度、条件路线和处境事实",
        "scope": "32个开发根逐根留一选择一个特征、一个阈值和一个方向的决策桩；不运行新桌、不调用模型；通过后只能进入全新来源验证",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=[
        Path(__file__), CF2_RESULT, CF2B_RESULT, CF3A_RESULT,
        _project_file(_PROJECT_ROOT, OUT / "dataset.json"), _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
    ])
    manifest = {
        "schema": "r10-claim-gate-stump-cf3b/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "dataset": str(_project_file(_PROJECT_ROOT, OUT / "dataset.json")),
        "dataset_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "dataset.json")),
        "cf3a_result": str(CF3A_RESULT),
        "cf3a_result_sha256": digest(CF3A_RESULT),
        "features": list(FEATURES),
        "model": "单特征决策桩；阈值只取相邻开发值中点；方向为>或<=；输出claim/pass",
        "training_selection": (
            "逐来源根leave-one-out；只保留claim_count在4..28、balanced_accuracy>=0.60、"
            "辅助门控均值>0、主晋级门控均值>=0；依次最大化balanced_accuracy、辅助均值、主均值，"
            "再最小化|claim_count-16|并按feature/threshold/direction稳定打破并列"
        ),
        "external_validation_required": "新panel_seed的H/M各8个行为命中；开发32根不再充当验证",
        "llm_calls": 0,
        "tables": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED_CF3B", "rows": len(rows)}, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """核对 CF3-B 冻结输入。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (
        ("dataset", "dataset_sha256"),
        ("cf3a_result", "cf3a_result_sha256"),
    ):
        if digest(Path(manifest[path_key])) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")


def metrics(rows: list[dict], decisions: list[bool]) -> dict:
    """计算单桩的分类与配对效用读数。"""

    positives = [bool(row["labels"]["auxiliary_positive"]) for row in rows]
    pos_total = sum(positives)
    nonpos_total = len(rows) - pos_total
    balanced = (
        sum(claim and positive for claim, positive in zip(decisions, positives, strict=True)) / pos_total
        + sum((not claim) and (not positive)
              for claim, positive in zip(decisions, positives, strict=True)) / nonpos_total
    ) / 2.0
    return {
        "rows": len(rows),
        "claim_count": sum(decisions),
        "balanced_accuracy": balanced,
        "auxiliary_gate_mean": statistics.fmean(
            row["labels"]["auxiliary_stage_score_delta"] if claim else 0.0
            for row, claim in zip(rows, decisions, strict=True)
        ),
        "primary_gate_mean": statistics.fmean(
            row["labels"]["primary_u_low_delta"] if claim else 0.0
            for row, claim in zip(rows, decisions, strict=True)
        ),
    }


def fit(rows: list[dict], feature: str) -> dict | None:
    """在给定行上选择一个特征的最佳阈值与方向。"""

    values = sorted({float(row["features"][feature]) for row in rows})
    thresholds = [(left + right) / 2.0 for left, right in zip(values, values[1:])]
    candidates = []
    for threshold in thresholds:
        for direction in ("gt", "le"):
            decisions = [
                float(row["features"][feature]) > threshold
                if direction == "gt"
                else float(row["features"][feature]) <= threshold
                for row in rows
            ]
            result = metrics(rows, decisions)
            candidates.append({
                "feature": feature,
                "threshold": threshold,
                "direction": direction,
                "training": result,
            })
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (
        -item["training"]["balanced_accuracy"],
        -item["training"]["auxiliary_gate_mean"],
        -item["training"]["primary_gate_mean"],
        abs(item["training"]["claim_count"] - len(rows) / 2.0),
        item["threshold"],
        item["direction"],
    ))[0]


def decide(model: dict, row: dict) -> bool:
    """应用冻结单桩。"""

    value = float(row["features"][model["feature"]])
    return value > model["threshold"] if model["direction"] == "gt" else value <= model["threshold"]


def loo(rows: list[dict], feature: str) -> dict | None:
    """逐来源根留一拟合并预测一个特征。"""

    decisions = []
    for index, row in enumerate(rows):
        model = fit(rows[:index] + rows[index + 1:], feature)
        if model is None:
            return None
        decisions.append(decide(model, row))
    return metrics(rows, decisions)


def run() -> None:
    """选择开发留一通过的单桩并冻结供新来源验证。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    result_path = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if result_path.exists():
        raise SystemExit("CF3-B 已执行；拒绝覆盖")
    rows = batch.read(Path(manifest["dataset"]))["rows"]
    candidates = []
    for feature in FEATURES:
        loo_result = loo(rows, feature)
        final_model = fit(rows, feature)
        if loo_result is not None and final_model is not None:
            candidates.append({
                "feature": feature,
                "loo": loo_result,
                "final_model": final_model,
            })
    eligible = [
        item for item in candidates
        if 4 <= item["loo"]["claim_count"] <= 28
        and item["loo"]["balanced_accuracy"] >= 0.60
        and item["loo"]["auxiliary_gate_mean"] > 0
        and item["loo"]["primary_gate_mean"] >= 0
    ]
    selected = None if not eligible else sorted(eligible, key=lambda item: (
        -item["loo"]["balanced_accuracy"],
        -item["loo"]["auxiliary_gate_mean"],
        -item["loo"]["primary_gate_mean"],
        abs(item["loo"]["claim_count"] - 16),
        item["feature"],
        item["final_model"]["threshold"],
        item["final_model"]["direction"],
    ))[0]
    status = (
        "PASS_CF3B_STUMP_FOR_NEW_SOURCE_VALIDATION"
        if selected is not None else "CLOSE_CF3B_NO_TRAINING_SIGNAL"
    )
    result = {
        "schema": "r10-claim-gate-stump-cf3b-result/1",
        "status": status,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "candidates": candidates,
        "eligible_features": [item["feature"] for item in eligible],
        "selected": selected,
        "next": (
            "冻结selected.final_model，用全新panel_seed的H/M各8个行为机会验证"
            if selected is not None
            else "回顾奖励终点和更丰富公开特征；不得使用已看开发根冒充验证"
        ),
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(result_path, result)
    verify_inputs(manifest)
    print(json.dumps({
        "status": status,
        "eligible_features": result["eligible_features"],
        "selected": selected,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
