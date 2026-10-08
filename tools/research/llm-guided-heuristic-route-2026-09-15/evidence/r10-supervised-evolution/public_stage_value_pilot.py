"""R12-SV0：用既有 R11 轨迹检验玩家可见阶段价值是否可跨来源预测。"""

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
import glob
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import discard_value_grouped_model as grouped  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/public-stage-value-pilot-01-20260921')
SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/discard-value-scaled-teacher-01-20260921')
SOURCE_DATA = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/discard-value-scaled-teacher-01-20260921/dataset.json')
SOURCE_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/discard-value-scaled-teacher-01-20260921/result.json')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R12-PUBLIC-STAGE-VALUE-EVOLUTION-PLAN-2026-09-21.md')

RIDGE = (("ridge-l0.001", 0.001), ("ridge-l0.01", 0.01), ("ridge-l0.1", 0.1))
TREES = (("tree-d1-l12", 1, 12), ("tree-d2-l12", 2, 12),
         ("tree-d3-l12", 3, 12), ("tree-d2-l24", 2, 24))
GAMS = (("gam-f8-p2-s0.25", 8, 2, 0.25),
        ("gam-f12-p2-s0.20", 12, 2, 0.20),
        ("gam-f16-p3-s0.15", 16, 3, 0.15))


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rmse(actual: list[float], predicted: list[float]) -> float:
    """计算均方根误差；空输入拒绝关闭。"""

    if not actual or len(actual) != len(predicted):
        raise ValueError("RMSE 输入为空或长度不一致")
    return math.sqrt(statistics.fmean((a - p) ** 2 for a, p in zip(actual, predicted)))


def _ranks(values: list[float]) -> list[float]:
    """生成并列取平均的秩，用于 Spearman 相关。"""

    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        rank = (cursor + 1 + end) / 2.0
        for offset in range(cursor, end):
            ranks[order[offset]] = rank
        cursor = end
    return ranks


def _correlation(left: list[float], right: list[float]) -> float:
    """计算 Pearson 相关；任一侧零方差时返回 0。"""

    if not left or len(left) != len(right):
        raise ValueError("相关输入为空或长度不一致")
    mean_left = statistics.fmean(left)
    mean_right = statistics.fmean(right)
    numerator = sum((x - mean_left) * (y - mean_right) for x, y in zip(left, right))
    denominator = math.sqrt(
        sum((x - mean_left) ** 2 for x in left)
        * sum((y - mean_right) ** 2 for y in right)
    )
    return numerator / denominator if denominator > 0 else 0.0


def _spearman(actual: list[float], predicted: list[float]) -> float:
    """计算含并列修正的 Spearman 秩相关。"""

    return _correlation(_ranks(actual), _ranks(predicted))


def _inverse(transformed: float, scale: float) -> float:
    """把训练时的 asinh 稳健目标变换还原为阶段积分。"""

    return math.sinh(max(-20.0, min(20.0, transformed))) * scale


def _model_specs() -> list[tuple[str, Callable[[list[dict]], Any], Callable[[Any, dict], float]]]:
    """返回冻结的十个低容量规格及其原尺度预测器。"""

    specs: list[tuple[str, Callable[[list[dict]], Any], Callable[[Any, dict], float]]] = []
    for name, lam in RIDGE:
        def fit(rows: list[dict], lam: float = lam) -> Any:
            copied = [{**row, "features": {**row["features"], "__bias__": 1.0}}
                      for row in rows]
            return grouped.fit_sgd_ridge(copied, lam)

        def predict(model: Any, features: dict, _name: str = name) -> float:
            del _name
            transformed = model.predict({**features, "__bias__": 1.0})
            return _inverse(transformed, model.target_scale)

        specs.append((name, fit, predict))
    for name, depth, min_leaf in TREES:
        def fit(rows: list[dict], depth: int = depth, min_leaf: int = min_leaf) -> Any:
            return grouped.fit_centered_tree(rows, depth, min_leaf)

        def predict(model: Any, features: dict, _name: str = name) -> float:
            del _name
            return _inverse(model.root.predict(features), model.target_scale)

        specs.append((name, fit, predict))
    for name, limit, passes, shrinkage in GAMS:
        def fit(rows: list[dict], limit: int = limit, passes: int = passes,
                shrinkage: float = shrinkage) -> Any:
            return grouped.fit_gam(rows, limit, passes, shrinkage)

        def predict(model: Any, features: dict, _name: str = name) -> float:
            del _name
            return _inverse(model._raw(features), model.target_scale)

        specs.append((name, fit, predict))
    return specs


def _raw_index() -> dict[tuple[int, str, int, str], list[dict]]:
    """索引 R11 原始续局；只接受机械全绿且有绝对阶段积分的记录。"""

    result: dict[tuple[int, str, int, str], list[dict]] = {}
    for name in glob.glob(str(_project_file(_PROJECT_ROOT, SOURCE / "raw" / "*.json"))):
        record = batch.read(Path(name))
        if not record.get("mechanical_ok") or record.get("error") is not None:
            raise ValueError("R11 原始续局存在机械失败：" + name)
        outcome = record.get("outcome") or {}
        if type(outcome.get("focal_stage_score")) not in (int, float):
            raise ValueError("R11 原始续局缺绝对阶段积分：" + name)
        key = (
            int(record["panel_seed"]), str(record["mix"]),
            int(record["root_index"]), str(record["action_key"]),
        )
        result.setdefault(key, []).append(record)
    return result


def build_rows() -> list[dict]:
    """把 128 个快照压成公开特征与稳定 V2 的 16 轨迹绝对价值。"""

    source = batch.read(SOURCE_DATA)
    if source.get("schema") != "r11-dv1-scaled-discard-teacher-rows/1":
        raise ValueError("R11 规模化教师数据 schema 漂移")
    raw = _raw_index()
    rows = []
    for source_row in source["rows"]:
        seed = int(source_row["group"]["panel_seed"])
        mix = str(source_row["group"]["mix"])
        root = int(source_row["group"]["root_index"])
        baseline_key = str(source_row["baseline_action_key"])
        baseline = next(
            item for item in source_row["actions"]
            if item["action_key"] == baseline_key and item["is_v2_baseline"]
        )
        rollouts = sorted(
            raw[(seed, mix, root, baseline_key)],
            key=lambda item: str(item["sample_key"]),
        )
        if len(rollouts) != 16 or len({item["sample_key"] for item in rollouts}) != 16:
            raise ValueError("稳定 V2 基准必须恰有 16 个不同未来顺序")
        scores = [float(item["outcome"]["focal_stage_score"]) for item in rollouts]
        u_low = [float(item["outcome"]["u_low"]) for item in rollouts]
        u_high = [float(item["outcome"]["u_high"]) for item in rollouts]
        features = grouped.flatten_features(baseline["features"])
        forbidden = [name for name in features if any(
            token in name.lower() for token in ("seed", "source_root", "future", "mix")
        )]
        if forbidden:
            raise ValueError("公开价值特征含禁止身份字段：" + str(forbidden[:5]))
        rows.append({
            "row_id": source_row["row_id"],
            "panel_seed": seed,
            "mix": mix,
            "root_index": root,
            "baseline_action_key": baseline_key,
            "features": features,
            "label": statistics.fmean(scores),
            "label_standard_error": (
                statistics.stdev(scores) / math.sqrt(len(scores)) if len(scores) > 1 else 0.0
            ),
            "u_low_mean": statistics.fmean(u_low),
            "u_high_mean": statistics.fmean(u_high),
            "rollout_count": 16,
            "weight": 1.0,
        })
    if len(rows) != 128:
        raise ValueError("SV0 必须恰有 128 个快照")
    return sorted(rows, key=lambda row: (row["panel_seed"], row["mix"], row["root_index"]))


def prepare() -> None:
    """冻结来源、模型规格、嵌套分组选择和继续门。"""

    if OUT.exists():
        raise SystemExit("SV0 目录已存在；拒绝覆盖")
    if batch.read(SOURCE_RESULT).get("status") != "PASS_DV1_2_SCALED_TEACHER_FOR_GROUPED_MODELING":
        raise ValueError("R11 规模化教师未通过机械门")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r12-public-stage-value-sv0",
        accounts={"tables_full": 0},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "用户取消旧目标并要求按文献复盘后的新方向推进；复用既有R11轨迹，零新增桌赛",
        "scope": "只做玩家可见阶段价值可行性反演；不选动作、不生成候选、不确认、不发布",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    manifest = {
        "schema": "r12-public-stage-value-pilot-manifest/1",
        "created_at_utc": batch.search.utc_now(),
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "source_dataset": str(SOURCE_DATA),
        "source_dataset_sha256": digest(SOURCE_DATA),
        "source_result": str(SOURCE_RESULT),
        "source_result_sha256": digest(SOURCE_RESULT),
        "source_raw": str(_project_file(_PROJECT_ROOT, SOURCE / "raw")),
        "source_raw_note": "原始续局已在本地冻结；本批另存公开特征和绝对标签的紧凑数据集",
        "panel_seeds": [2026092340, 2026092341, 2026092342, 2026092343],
        "mixes": ["H", "M"],
        "rows": 128,
        "rollouts_per_row": 16,
        "label": "稳定V2首选动作在16个预登记未来顺序下的焦点剩余阶段积分均值",
        "features": "PlayerObservation+赛事公开处境+HangmaRules事实+V2首选动作；不含seed/mix/来源/未来/隐藏世界",
        "outer_split": "leave-one-panel-seed-out",
        "selection": "每个外折在其三个训练seed上再做leave-one-seed-out；按合并RMSE比常数基线最低选择，完全同分按规格名",
        "model_specs": [name for name, _, _ in _model_specs()],
        "continue_gate": {
            "pooled_rmse_reduction_min": 0.10,
            "pooled_spearman_min": 0.20,
            "spearman_by_mix_min": 0.0,
            "seeds_nonworse_than_constant_min": 3,
        },
        "tables_full_new": 0,
        "llm_calls": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED_R12_SV0", "model_specs": manifest["model_specs"]},
                     ensure_ascii=False, indent=2))


def _fit_predict(spec: tuple[str, Callable, Callable], train: list[dict], test: list[dict]) -> list[float]:
    """拟合一个冻结规格并返回原尺度预测。"""

    _, fit, predict = spec
    model = fit(train)
    return [float(predict(model, row["features"])) for row in test]


def _select_spec(train_rows: list[dict], specs: list[tuple]) -> tuple[tuple, list[dict]]:
    """只用外折训练种子做内层整组选择。"""

    seeds = sorted({int(row["panel_seed"]) for row in train_rows})
    if len(seeds) != 3:
        raise ValueError("每个外折训练集必须恰有三个面板种子")
    reports = []
    for spec in specs:
        actual_all: list[float] = []
        predicted_all: list[float] = []
        constant_all: list[float] = []
        for held in seeds:
            inner_train = [row for row in train_rows if row["panel_seed"] != held]
            inner_test = [row for row in train_rows if row["panel_seed"] == held]
            train_mean = statistics.fmean(float(row["label"]) for row in inner_train)
            actual = [float(row["label"]) for row in inner_test]
            predicted = _fit_predict(spec, inner_train, inner_test)
            actual_all.extend(actual)
            predicted_all.extend(predicted)
            constant_all.extend([train_mean] * len(actual))
        model_rmse = _rmse(actual_all, predicted_all)
        constant_rmse = _rmse(actual_all, constant_all)
        reports.append({
            "model_spec": spec[0],
            "inner_rmse": model_rmse,
            "inner_constant_rmse": constant_rmse,
            "inner_rmse_ratio": model_rmse / constant_rmse if constant_rmse else math.inf,
        })
    reports.sort(key=lambda row: (row["inner_rmse_ratio"], row["model_spec"]))
    chosen = next(spec for spec in specs if spec[0] == reports[0]["model_spec"])
    return chosen, reports


def run() -> None:
    """执行四折嵌套分组评价并按预登记门结案。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    if digest(PLAN) != manifest["plan_sha256"]:
        raise ValueError("R12 计划在准备后漂移")
    if digest(SOURCE_DATA) != manifest["source_dataset_sha256"]:
        raise ValueError("R11 数据在准备后漂移")
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("SV0 结果已存在；拒绝覆盖")
    rows = build_rows()
    batch.write(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), {
        "schema": "r12-public-stage-value-pilot-dataset/1",
        "source_dataset_sha256": digest(SOURCE_DATA),
        "rows": rows,
    })
    specs = _model_specs()
    predictions = []
    folds = []
    for held_seed in manifest["panel_seeds"]:
        train = [row for row in rows if row["panel_seed"] != held_seed]
        test = [row for row in rows if row["panel_seed"] == held_seed]
        chosen, inner = _select_spec(train, specs)
        predicted = _fit_predict(chosen, train, test)
        train_mean = statistics.fmean(float(row["label"]) for row in train)
        actual = [float(row["label"]) for row in test]
        fold_rows = []
        for row, value in zip(test, predicted):
            item = {
                "row_id": row["row_id"],
                "panel_seed": held_seed,
                "mix": row["mix"],
                "actual": float(row["label"]),
                "predicted": value,
                "constant": train_mean,
                "model_spec": chosen[0],
            }
            predictions.append(item)
            fold_rows.append(item)
        model_rmse = _rmse(actual, predicted)
        constant_rmse = _rmse(actual, [train_mean] * len(test))
        folds.append({
            "held_panel_seed": held_seed,
            "selected_model_spec": chosen[0],
            "inner_selection": inner,
            "test_count": len(test),
            "test_rmse": model_rmse,
            "test_constant_rmse": constant_rmse,
            "test_rmse_ratio": model_rmse / constant_rmse if constant_rmse else math.inf,
            "test_spearman": _spearman(actual, predicted),
            "nonworse_than_constant": model_rmse <= constant_rmse,
        })

    actual = [row["actual"] for row in predictions]
    predicted = [row["predicted"] for row in predictions]
    constant = [row["constant"] for row in predictions]
    model_rmse = _rmse(actual, predicted)
    constant_rmse = _rmse(actual, constant)
    reduction = 1.0 - model_rmse / constant_rmse if constant_rmse else -math.inf
    by_mix = {}
    for mix in manifest["mixes"]:
        selected = [row for row in predictions if row["mix"] == mix]
        by_mix[mix] = {
            "count": len(selected),
            "rmse": _rmse([row["actual"] for row in selected],
                            [row["predicted"] for row in selected]),
            "constant_rmse": _rmse([row["actual"] for row in selected],
                                     [row["constant"] for row in selected]),
            "spearman": _spearman([row["actual"] for row in selected],
                                    [row["predicted"] for row in selected]),
        }
    nonworse = sum(bool(row["nonworse_than_constant"]) for row in folds)
    gate = manifest["continue_gate"]
    passed = bool(
        reduction >= gate["pooled_rmse_reduction_min"]
        and _spearman(actual, predicted) >= gate["pooled_spearman_min"]
        and all(item["spearman"] >= gate["spearman_by_mix_min"] for item in by_mix.values())
        and nonworse >= gate["seeds_nonworse_than_constant_min"]
    )
    status = ("PASS_R12_SV0_PUBLIC_VALUE_SIGNAL" if passed
              else "CLOSE_R12_SV0_NO_GENERALIZABLE_PUBLIC_VALUE_SIGNAL")
    result = {
        "schema": "r12-public-stage-value-pilot-result/1",
        "status": status,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "dataset_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "dataset.json")),
        "folds": folds,
        "pooled": {
            "count": len(predictions),
            "rmse": model_rmse,
            "constant_rmse": constant_rmse,
            "rmse_reduction": reduction,
            "spearman": _spearman(actual, predicted),
            "seeds_nonworse_than_constant": nonworse,
        },
        "by_mix": by_mix,
        "label_distribution": {
            "mean": statistics.fmean(actual),
            "stdev": statistics.stdev(actual),
            "median_label_standard_error": statistics.median(
                float(row["label_standard_error"]) for row in rows
            ),
        },
        "predictions": predictions,
        "continue_gate": gate,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
        "next": (
            "冻结公开价值特征版本，另建新自然来源语料并验证预测与筛选效率"
            if passed else
            "按R12§6复盘标签噪声、样本覆盖和长程价值建模；不得增加同批模型复杂度"
        ),
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    arguments = parser.parse_args()
    globals()[arguments.operation]()
