"""CF3-A：用根级隔离的反事实标签校准低自由度玩家可见鸣牌门控器。"""

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
import math
import statistics
import sys
from pathlib import Path
from typing import Iterable


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import claim_counterfactual_variance as cf2  # noqa: E402
import claim_counterfactual_topup as cf2b  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-gate-calibration-01-20260921')
CF2_RESULT = cf2.OUT / "result.json"
CF2B_RESULT = cf2b.OUT / "result.json"
VALIDATION_ROWS = 8
LAMBDAS = (0.1, 1.0, 10.0, 100.0)
FEATURE_SETS = {
    "route": ("route_raw", "route_margin"),
    "progress": ("shanten_delta", "support_delta", "wall_remaining", "is_peng"),
    "compact": ("route_raw", "support_delta", "is_peng"),
    "combined": (
        "route_raw",
        "route_margin",
        "shanten_delta",
        "support_delta",
        "wall_remaining",
        "is_peng",
    ),
}


def digest(path: Path) -> str:
    """返回冻结文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def useful_support(facts: dict | None) -> int | None:
    """求规则候选一步有效牌的公开未见张数总和。"""

    if not facts:
        return None
    useful = facts.get("useful_tiles")
    if useful is None:
        return None
    values = [item.get("remaining_estimate") for item in useful]
    if any(type(value) is not int for value in values):
        return None
    return sum(values)


def extract_row(hit: dict) -> dict:
    """把一个反事实样本压成冻结的小型公开特征向量。"""

    visible = hit["witness"]["observable_features"]
    pass_facts = visible["pass"]["facts"]
    claim_facts = visible["claim"]["facts"]
    detail = visible["claim"]["route_score_trace"]["detail"]
    pass_support = useful_support(pass_facts)
    claim_support = useful_support(claim_facts)
    if pass_support is None or claim_support is None:
        raise ValueError("CF3-A 只接受有效牌支持量已知的样本")
    pass_shanten = pass_facts.get("shanten_after")
    claim_shanten = claim_facts.get("shanten_after")
    if type(pass_shanten) is not int or type(claim_shanten) is not int:
        raise ValueError("CF3-A 只接受吃碰与过牌向听均已知的样本")
    route_raw = detail.get("route_raw")
    route_low = detail.get("route_low")
    if not isinstance(route_raw, (int, float)) or not isinstance(route_low, (int, float)):
        raise ValueError("CF3-A 只接受路线原值和同窗下界均已知的样本")
    claim_key = str(hit["witness"]["claim_action_key"])
    row_id = "{0}:{1}".format(hit["mix"], hit["source_root_id"])
    features = {
        "route_raw": float(route_raw),
        "route_margin": float(route_raw) - float(route_low),
        "shanten_delta": float(claim_shanten - pass_shanten),
        "support_delta": float(claim_support - pass_support),
        "wall_remaining": float(visible["remaining_tile_count"]),
        "is_peng": float(claim_key.startswith("peng:")),
    }
    auxiliary = float(hit["label"]["focal_stage_score_delta"])
    return {
        "row_id": row_id,
        "source_root_id": hit["source_root_id"],
        "mix": hit["mix"],
        "root_index": hit["root_index"],
        "claim_action_key": claim_key,
        "features": features,
        "labels": {
            "primary_u_low_delta": float(hit["label"]["u_low_delta"]),
            "auxiliary_stage_score_delta": auxiliary,
            "auxiliary_sign": 1 if auxiliary > 0 else -1 if auxiliary < 0 else 0,
        },
    }


def prepare() -> None:
    """冻结特征、根级切分、模型族和校准选择规则。"""

    if OUT.exists():
        raise SystemExit("CF3-A 目录已存在；拒绝覆盖")
    cf2_result = batch.read(CF2_RESULT)
    cf2b_result = batch.read(CF2B_RESULT)
    if cf2b_result["combined_summary"]["disposition"] != (
        "PROCEED_OBSERVABLE_AUXILIARY_GATE_WITH_PRIMARY_STAGE_VALIDATION"
    ):
        raise ValueError("CF2 合并裁定未允许进入门控器校准")
    hits = list(cf2_result["hits"]) + list(cf2b_result["hits"])
    rows = [extract_row(hit) for hit in hits]
    if len(rows) != 32 or len({row["row_id"] for row in rows}) != 32:
        raise ValueError("CF3-A 需要32个唯一来源根样本")
    ordered = sorted(
        rows,
        key=lambda row: hashlib.sha256(row["row_id"].encode("utf-8")).hexdigest(),
    )
    validation_ids = {row["row_id"] for row in ordered[:VALIDATION_ROWS]}
    for row in rows:
        row["split"] = "validation" if row["row_id"] in validation_ids else "train"
    OUT.mkdir(parents=True)
    batch.write(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), {
        "schema": "r10-claim-gate-dataset/1",
        "rows": rows,
        "split_rule": "按sha256(row_id)升序取前8为validation，其余24为train；不读取标签分层",
        "feature_schema": list(next(iter(rows))["features"]),
        "label_scope": "同快照首动作干预后完整剩余阶段；辅助积分只用于信用，主晋级差用于验证",
    })
    authorization = batch.unified_document(
        batch_label="r10-claim-gate-calibration-cf3a",
        authorization_id="r10-claim-gate-calibration-cf3a-20260921",
        accounts={},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "CF2合并32样本的机械、动作族覆盖和辅助标签丰富度通过",
        "scope": "24训练根做留一法选择低自由度ridge门控器，8个根级隔离验证；不运行新桌、不调用模型、不确认、不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=[
        Path(__file__), CF2_RESULT, CF2B_RESULT, _project_file(_PROJECT_ROOT, OUT / "dataset.json"), _project_file(_PROJECT_ROOT, OUT / "authorization.json")
    ])
    manifest = {
        "schema": "r10-claim-gate-calibration-cf3a/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "cf2_result": str(CF2_RESULT),
        "cf2_result_sha256": digest(CF2_RESULT),
        "cf2b_result": str(CF2B_RESULT),
        "cf2b_result_sha256": digest(CF2B_RESULT),
        "dataset": str(_project_file(_PROJECT_ROOT, OUT / "dataset.json")),
        "dataset_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "dataset.json")),
        "train_rows": 24,
        "validation_rows": VALIDATION_ROWS,
        "feature_sets": {key: list(value) for key, value in FEATURE_SETS.items()},
        "lambdas": list(LAMBDAS),
        "target": "sign(auxiliary_stage_score_delta)：正=1、零=0、负=-1；ridge输出>0才允许鸣牌",
        "model_selection": (
            "只在24训练根做leave-one-root-out；先最大化正类/非正类balanced accuracy，"
            "再最大化实际辅助积分差的门控均值，再依次偏好更少特征、更大lambda、配置名"
        ),
        "validation_gate": (
            "验证集同时含辅助正/非正；候选改选数在1..7；门控辅助积分均值>0且不低于always-claim；"
            "门控主晋级差均值>=0。否则不装配完整阶段候选。"
        ),
        "llm_calls": 0,
        "tables": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({
        "status": "PREPARED_CF3A",
        "train_rows": 24,
        "validation_rows": VALIDATION_ROWS,
    }, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """核对校准冻结输入。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (
        ("cf2_result", "cf2_result_sha256"),
        ("cf2b_result", "cf2b_result_sha256"),
        ("dataset", "dataset_sha256"),
    ):
        if digest(Path(manifest[path_key])) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")


def solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """用部分主元高斯消元求小型线性方程；奇异时 fail-closed。"""

    size = len(vector)
    aug = [list(matrix[i]) + [vector[i]] for i in range(size)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda row: abs(aug[row][col]))
        if abs(aug[pivot][col]) < 1e-12:
            raise ValueError("ridge正规方程仍奇异")
        aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        aug[col] = [value / scale for value in aug[col]]
        for row in range(size):
            if row == col:
                continue
            factor = aug[row][col]
            aug[row] = [
                aug[row][index] - factor * aug[col][index]
                for index in range(size + 1)
            ]
    return [aug[row][-1] for row in range(size)]


def fit(rows: list[dict], features: tuple[str, ...], ridge_lambda: float) -> dict:
    """拟合带截距、仅惩罚斜率的标准化 ridge。"""

    means = {name: statistics.fmean(row["features"][name] for row in rows) for name in features}
    scales = {}
    for name in features:
        variance = statistics.fmean(
            (row["features"][name] - means[name]) ** 2 for row in rows
        )
        scales[name] = math.sqrt(variance) if variance > 1e-12 else 1.0
    design = [
        [1.0] + [
            (row["features"][name] - means[name]) / scales[name]
            for name in features
        ]
        for row in rows
    ]
    target = [float(row["labels"]["auxiliary_sign"]) for row in rows]
    width = len(features) + 1
    xtx = [[0.0] * width for _ in range(width)]
    xty = [0.0] * width
    for values, label in zip(design, target, strict=True):
        for i in range(width):
            xty[i] += values[i] * label
            for j in range(width):
                xtx[i][j] += values[i] * values[j]
    for index in range(1, width):
        xtx[index][index] += ridge_lambda
    return {
        "features": list(features),
        "lambda": ridge_lambda,
        "means": means,
        "scales": scales,
        "coefficients": solve(xtx, xty),
    }


def predict(model: dict, row: dict) -> float:
    """计算冻结线性门控输出；正数才鸣牌。"""

    values = [1.0] + [
        (row["features"][name] - model["means"][name]) / model["scales"][name]
        for name in model["features"]
    ]
    return sum(a * b for a, b in zip(model["coefficients"], values, strict=True))


def metrics(rows: list[dict], scores: Iterable[float]) -> dict:
    """计算门控分类与实际配对结果；不把辅助指标冒充赛事强度。"""

    scores = list(scores)
    claims = [score > 0 for score in scores]
    positives = [row["labels"]["auxiliary_sign"] > 0 for row in rows]
    pos_total = sum(positives)
    neg_total = len(rows) - pos_total
    tpr = (sum(claim and positive for claim, positive in zip(claims, positives, strict=True))
           / pos_total if pos_total else None)
    tnr = (sum((not claim) and (not positive)
               for claim, positive in zip(claims, positives, strict=True))
           / neg_total if neg_total else None)
    balanced = None if tpr is None or tnr is None else (tpr + tnr) / 2.0
    selected_aux = [
        row["labels"]["auxiliary_stage_score_delta"] if claim else 0.0
        for row, claim in zip(rows, claims, strict=True)
    ]
    selected_primary = [
        row["labels"]["primary_u_low_delta"] if claim else 0.0
        for row, claim in zip(rows, claims, strict=True)
    ]
    return {
        "rows": len(rows),
        "positive_rows": pos_total,
        "nonpositive_rows": neg_total,
        "claim_count": sum(claims),
        "balanced_accuracy": balanced,
        "auxiliary_gate_mean": statistics.fmean(selected_aux),
        "primary_gate_mean": statistics.fmean(selected_primary),
        "always_claim_auxiliary_mean": statistics.fmean(
            row["labels"]["auxiliary_stage_score_delta"] for row in rows
        ),
        "always_claim_primary_mean": statistics.fmean(
            row["labels"]["primary_u_low_delta"] for row in rows
        ),
        "scores": scores,
        "decisions": ["claim" if claim else "pass" for claim in claims],
    }


def loo_metrics(rows: list[dict], features: tuple[str, ...], ridge_lambda: float) -> dict:
    """逐来源根留一预测训练集。"""

    scores = []
    for index, row in enumerate(rows):
        train = rows[:index] + rows[index + 1:]
        scores.append(predict(fit(train, features, ridge_lambda), row))
    return metrics(rows, scores)


def run() -> None:
    """只用训练根选模型，再一次性读取根级隔离验证结果。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    result_path = _project_file(_PROJECT_ROOT, OUT / "result.json")
    if result_path.exists():
        raise SystemExit("CF3-A 已执行；拒绝覆盖")
    rows = batch.read(Path(manifest["dataset"]))["rows"]
    train = [row for row in rows if row["split"] == "train"]
    validation = [row for row in rows if row["split"] == "validation"]
    candidates = []
    for name, features in FEATURE_SETS.items():
        for ridge_lambda in LAMBDAS:
            candidates.append({
                "config_id": "{0}:lambda={1:g}".format(name, ridge_lambda),
                "feature_set": name,
                "features": list(features),
                "lambda": ridge_lambda,
                "loo": loo_metrics(train, features, ridge_lambda),
            })
    eligible = [
        item for item in candidates if item["loo"]["balanced_accuracy"] is not None
    ]
    selected = sorted(
        eligible,
        key=lambda item: (
            -float(item["loo"]["balanced_accuracy"]),
            -float(item["loo"]["auxiliary_gate_mean"]),
            len(item["features"]),
            -float(item["lambda"]),
            item["config_id"],
        ),
    )[0]
    model = fit(train, tuple(selected["features"]), float(selected["lambda"]))
    validation_metrics = metrics(validation, [predict(model, row) for row in validation])
    labels_covered = (
        validation_metrics["positive_rows"] > 0
        and validation_metrics["nonpositive_rows"] > 0
    )
    gate_pass = (
        labels_covered
        and 1 <= validation_metrics["claim_count"] <= len(validation) - 1
        and validation_metrics["auxiliary_gate_mean"] > 0
        and validation_metrics["auxiliary_gate_mean"]
        >= validation_metrics["always_claim_auxiliary_mean"]
        and validation_metrics["primary_gate_mean"] >= 0
    )
    result = {
        "schema": "r10-claim-gate-calibration-cf3a-result/1",
        "status": "PASS_CF3A_GATE_FOR_IMPLEMENTATION" if gate_pass
        else "CLOSE_CF3A_GATE_AND_REVIEW_FEATURES",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "selection_candidates": candidates,
        "selected": selected,
        "model": model,
        "train_row_ids": [row["row_id"] for row in train],
        "validation_row_ids": [row["row_id"] for row in validation],
        "validation": validation_metrics,
        "validation_labels_covered": labels_covered,
        "gate_pass": gate_pass,
        "interpretation": (
            "通过只授权把冻结低自由度门控器接成离线候选并做新来源完整阶段开发；"
            "不证明动作级因果可外推、赛事强度、独立确认或发布资格。"
        ),
        "llm_calls": 0,
        "tables": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(result_path, result)
    verify_inputs(manifest)
    print(json.dumps({
        "status": result["status"],
        "selected": selected["config_id"],
        "loo": selected["loo"],
        "validation": validation_metrics,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
