"""AV1-2：按面板种子分组交叉验证低容量吃碰动作价值模型。"""

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-value-model-01-20260921')
DATA_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-value-dataset-01-20260921')
DATA = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-value-dataset-01-20260921/dataset.json')
DATA_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-value-dataset-01-20260921/result.json')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R10-CLAIM-COUNTERFACTUAL-CLOSE-AND-VALUE-PIVOT-2026-09-21.md')
RIDGE_LAMBDAS = (0.1, 1.0, 10.0)
TREE_CONFIGS = ((1, 12), (2, 12), (3, 12), (2, 16), (3, 16))
EVENT_KINDS = ("pass", "tile_discarded", "tile_drawn", "chi", "peng", "gang")
MELD_KINDS = ("chi", "peng", "gang")
FAMILIES = ("branch", "chain", "four_white", "baotou")
PROGRESS = ("advance", "same", "retreat", "close", "unknown")
ROUTE_STATUS = ("witnessed", "open_uncertain", "closed_proven", "unanalyzed")


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _put(features: dict[str, float], name: str, value: Any) -> None:
    """写入有限实数特征。"""

    number = float(value)
    if not math.isfinite(number):
        raise ValueError("非有限特征：" + name)
    features[name] = number


def _optional(features: dict[str, float], prefix: str, value: dict) -> None:
    """把显式可空字段拆为已知位和值。"""

    known = bool(value["known"])
    _put(features, prefix + ".known", known)
    if known and isinstance(value["value"], (int, float, bool)):
        _put(features, prefix + ".value", value["value"])


def _one_hot(features: dict[str, float], prefix: str, value: Any, choices: tuple) -> None:
    """按冻结类别表写独热特征，额外记录未知类别。"""

    matched = False
    for choice in choices:
        hit = value == choice
        _put(features, f"{prefix}.{choice}", hit)
        matched = matched or hit
    _put(features, prefix + ".other", not matched)


def _vector(features: dict[str, float], prefix: str, values: list) -> None:
    """按固定下标展开数值向量。"""

    for index, value in enumerate(values):
        _put(features, f"{prefix}.{index}", value)


def _optional_tile(features: dict[str, float], prefix: str, value: dict) -> None:
    """编码可空规范牌下标。"""

    known = bool(value["known"])
    _put(features, prefix + ".known", known)
    if known:
        index = int(value["value"])
        _put(features, f"{prefix}.tile.{index}", 1)


def flatten_features(encoded: dict) -> dict[str, float]:
    """把 AV1 完整公开状态压成固定、可审计的数值字典。

    牌河、副露、历史事件和合法后继均从完整编码汇总；不读取标签、来源根、
    面板种子或对手实现。历史事件保留类别×相对座位计数及最近八条顺序。
    """

    if encoded.get("schema") != "r10-claim-value-features/1":
        raise ValueError("未知 AV1 特征 schema")
    out: dict[str, float] = {}
    observation = encoded["observation"]
    _one_hot(out, "phase", observation["phase"], ("response_peng", "response_chi"))
    for name in ("round_no", "snapshot_seq"):
        _put(out, "observation." + name, observation[name])
    for name in ("dealer_relative_seat", "turn_relative_seat"):
        _one_hot(out, name, observation[name], (0, 1, 2, 3))
    for seat in observation["responding_relative_seats"]:
        _put(out, f"responding.{seat}", 1)
    _vector(out, "hand", observation["my_hand_counts"])
    _optional_tile(out, "drawn", observation["drawn_tile"])
    for seat, river in enumerate(observation["discards"]):
        _vector(out, f"discard.{seat}.count", river["counts"])
        _put(out, f"discard.{seat}.length", len(river["sequence"]))
        for offset, tile in enumerate(reversed(river["sequence"][-3:]), start=1):
            _put(out, f"discard.{seat}.recent{offset}.tile.{tile}", 1)
    for seat, melds in enumerate(observation["melds"]):
        aggregate = [0] * 34
        _put(out, f"meld.{seat}.count", len(melds))
        for meld in melds:
            kind = meld["kind"] if meld["kind"] in MELD_KINDS else "other"
            _put(out, f"meld.{seat}.kind.{kind}", out.get(f"meld.{seat}.kind.{kind}", 0) + 1)
            for index, count in enumerate(meld["tile_counts"]):
                aggregate[index] += int(count)
        _vector(out, f"meld.{seat}.tiles", aggregate)
    _vector(out, "hand_counts", observation["hand_counts"])
    _vector(out, "scores", observation["scores"])
    for seat in range(1, 4):
        _put(out, f"score_delta_to.{seat}", observation["scores"][0] - observation["scores"][seat])
    _put(out, "last_discard.known", observation["last_discard"]["known"])
    if observation["last_discard"]["known"]:
        last = observation["last_discard"]["value"]
        _one_hot(out, "last_discard.seat", last["relative_seat"], (0, 1, 2, 3))
        _put(out, f"last_discard.tile.{last['tile']}", 1)
        _put(out, "last_discard.seq_age", observation["snapshot_seq"] - last["seq"])
    _optional(out, "wall", observation["remaining_tile_count"])
    state = observation["rule_state"]
    _put(out, f"wealth.tile.{state['wealth_god']}", 1)
    for name in ("baotou", "chain_count", "catch_play"):
        _put(out, "rule_state." + name, state[name])
    _optional(out, "rule_state.catch_owner", state["catch_play_owner_relative_seat"])
    _optional(out, "chain_piao", observation["chain_piao"])
    _optional(out, "gang_draw", observation["gang_draw"])
    _put(out, "history.complete", observation["history_complete"])
    _put(out, "history.length", len(observation["public_history"]))
    for event in observation["public_history"]:
        kind = event["kind"] if event["kind"] in EVENT_KINDS else "other"
        seat = event["relative_seat"]["value"] if event["relative_seat"]["known"] else "none"
        key = f"history.count.{kind}.seat.{seat}"
        _put(out, key, out.get(key, 0) + 1)
    for offset, event in enumerate(reversed(observation["public_history"][-8:]), start=1):
        kind = event["kind"] if event["kind"] in EVENT_KINDS else "other"
        _put(out, f"history.recent{offset}.kind.{kind}", 1)
        if event["relative_seat"]["known"]:
            _put(out, f"history.recent{offset}.seat.{event['relative_seat']['value']}", 1)
        for tile in event["tiles"]:
            _put(out, f"history.recent{offset}.tile.{tile}", 1)

    competition = encoded["competition"]
    for name in ("stage_no", "stage_total", "participant_rank"):
        _optional(out, "competition." + name, competition[name])
    role = competition["stage_role"]
    _put(out, "competition.stage_role.known", role["known"])
    if role["known"]:
        _one_hot(out, "competition.stage_role", role["value"], ("qualifier", "final"))
    _put(out, "competition.ranking_count", len(competition["ranking"]))
    for name in ("total_score", "place_points", "god_count", "games_played"):
        values = [float(item[name]) for item in competition["ranking"]]
        if values:
            _put(out, f"competition.ranking.{name}.mean", statistics.fmean(values))
            _put(out, f"competition.ranking.{name}.min", min(values))
            _put(out, f"competition.ranking.{name}.max", max(values))

    claim = encoded["claim"]
    _one_hot(out, "claim.kind", claim["kind"], ("chi", "peng"))
    claim_tiles = [0] * 34
    for tile in claim["tiles"]:
        claim_tiles[int(tile)] += 1
    _vector(out, "claim.tiles", claim_tiles)
    facts = claim["facts"]
    _put(out, "facts.known", facts["known"])
    if facts["known"]:
        _one_hot(out, "facts.kind", facts["fact_kind"], ("hand_progress", "win", "not_applicable", "analysis_failed"))
        for name in ("shanten", "standard_shanten", "seven_pairs_shanten"):
            _optional(out, "facts." + name, facts[name])
        for name in ("useful_tiles", "standard_useful_tiles", "seven_pairs_useful_tiles"):
            _put(out, f"facts.{name}.known", facts[name]["known"])
            if facts[name]["known"]:
                _vector(out, f"facts.{name}", facts[name]["remaining_by_tile"])
        _optional_tile(out, "facts.best_followup", facts["best_followup_discard"])
        _put(out, "facts.replacement_unknown", facts["replacement_draw_unknown"])
        _one_hot(out, "facts.completeness", facts["completeness"], ("complete", "degraded"))
        branches = facts["followup_branches"]
        _put(out, "followup.known", branches["known"])
        if branches["known"]:
            _put(out, "followup.count", len(branches["value"]))
            for branch in branches["value"]:
                prefix = f"followup.discard.{branch['discard']}"
                _put(out, prefix + ".present", 1)
                for name in ("combined_shanten", "standard_shanten", "seven_pairs_shanten", "support_remaining"):
                    _optional(out, prefix + "." + name, branch[name])
                if branch["useful_tiles"]["known"]:
                    _vector(out, prefix + ".useful", branch["useful_tiles"]["remaining_by_tile"])
        by_family = {item["family"]: item for item in facts["family_progress"]}
        for family in FAMILIES:
            item = by_family.get(family)
            _put(out, f"family.{family}.known", item is not None)
            if item is not None:
                _one_hot(out, f"family.{family}.progress", item["progress"], PROGRESS)
                _one_hot(out, f"family.{family}.status", item["route_status"], ROUTE_STATUS)

    value = claim["value_facts"]
    _put(out, "value.known", value["known"])
    if value["known"]:
        _one_hot(out, "value.coverage", value["coverage"], ("complete", "partial", "unavailable"))
        routes = value["routes"]
        _put(out, "value.route_count", len(routes))
        if routes:
            fans = [float(item["settlement"]["fan"]) for item in routes]
            own = [float(item["settlement"]["score_delta"][0]) for item in routes]
            support = [
                sum(item["useful_tiles"]["remaining_by_tile"])
                for item in routes
            ]
            for name, values in (("fan", fans), ("own_delta", own), ("support", support)):
                _put(out, f"value.{name}.min", min(values))
                _put(out, f"value.{name}.max", max(values))
                _put(out, f"value.{name}.mean", statistics.fmean(values))
                _put(out, f"value.{name}.sum", sum(values))
    return out


def _cholesky_solve(matrix: list[list[float]], values: list[float]) -> list[float]:
    """求解对称正定线性系统；岭项保证主对角正定。"""

    size = len(matrix)
    lower = [[0.0] * size for _ in range(size)]
    for row in range(size):
        for column in range(row + 1):
            residual = matrix[row][column] - sum(
                lower[row][k] * lower[column][k] for k in range(column)
            )
            if row == column:
                if residual <= 1e-12:
                    raise ValueError("岭回归矩阵不是正定")
                lower[row][column] = math.sqrt(residual)
            else:
                lower[row][column] = residual / lower[column][column]
    forward = [0.0] * size
    for row in range(size):
        forward[row] = (
            values[row] - sum(lower[row][k] * forward[k] for k in range(row))
        ) / lower[row][row]
    solution = [0.0] * size
    for row in range(size - 1, -1, -1):
        solution[row] = (
            forward[row]
            - sum(lower[k][row] * solution[k] for k in range(row + 1, size))
        ) / lower[row][row]
    return solution


@dataclass
class RidgeModel:
    """原始特征空间中的线性岭模型。"""

    intercept: float
    coefficients: dict[str, float]

    def predict(self, row: dict[str, float]) -> float:
        return self.intercept + sum(
            weight * row.get(name, 0.0) for name, weight in self.coefficients.items()
        )

    def artifact(self) -> dict:
        return {
            "kind": "linear_ridge",
            "intercept": self.intercept,
            "coefficients": dict(sorted(self.coefficients.items())),
        }


def fit_ridge(rows: list[dict[str, float]], labels: list[float], lam: float) -> RidgeModel:
    """在样本对偶空间拟合岭回归，再转换为原始特征系数。"""

    names = sorted({name for row in rows for name in row})
    means: dict[str, float] = {}
    scales: dict[str, float] = {}
    active = []
    for name in names:
        values = [row.get(name, 0.0) for row in rows]
        mean = statistics.fmean(values)
        variance = statistics.fmean((value - mean) ** 2 for value in values)
        if variance > 1e-12:
            active.append(name)
            means[name] = mean
            scales[name] = math.sqrt(variance)
    if not active:
        return RidgeModel(statistics.fmean(labels), {})
    matrix = [
        [(row.get(name, 0.0) - means[name]) / scales[name] for name in active]
        for row in rows
    ]
    label_mean = statistics.fmean(labels)
    centered = [value - label_mean for value in labels]
    width = float(len(active))
    kernel = []
    for left, x in enumerate(matrix):
        kernel.append([
            sum(a * b for a, b in zip(x, y)) / width + (lam if left == right else 0.0)
            for right, y in enumerate(matrix)
        ])
    alpha = _cholesky_solve(kernel, centered)
    standardized_weights = [
        sum(alpha[row] * matrix[row][column] for row in range(len(rows))) / width
        for column in range(len(active))
    ]
    coefficients = {
        name: standardized_weights[index] / scales[name]
        for index, name in enumerate(active)
        if abs(standardized_weights[index] / scales[name]) > 1e-12
    }
    intercept = label_mean - sum(coefficients[name] * means[name] for name in coefficients)
    return RidgeModel(intercept, coefficients)


@dataclass
class TreeNode:
    """深度受限回归树节点。"""

    value: float
    feature: str | None = None
    threshold: float | None = None
    left: "TreeNode | None" = None
    right: "TreeNode | None" = None

    def predict(self, row: dict[str, float]) -> float:
        if self.feature is None:
            return self.value
        branch = self.left if row.get(self.feature, 0.0) <= self.threshold else self.right
        assert branch is not None
        return branch.predict(row)

    def artifact(self) -> dict:
        if self.feature is None:
            return {"value": self.value}
        assert self.left is not None and self.right is not None
        return {
            "value": self.value,
            "feature": self.feature,
            "threshold": self.threshold,
            "left": self.left.artifact(),
            "right": self.right.artifact(),
        }


def fit_tree(
    rows: list[dict[str, float]], labels: list[float], max_depth: int, min_leaf: int
) -> TreeNode:
    """以平方误差和稳定字典序拟合浅层回归树。"""

    names = sorted({name for row in rows for name in row})

    def build(indices: list[int], depth: int) -> TreeNode:
        values = [labels[index] for index in indices]
        node = TreeNode(statistics.fmean(values))
        if depth >= max_depth or len(indices) < 2 * min_leaf:
            return node
        best: tuple[float, str, float, list[int], list[int]] | None = None
        for name in names:
            ordered = sorted((rows[index].get(name, 0.0), index) for index in indices)
            left_sum = 0.0
            left_sq = 0.0
            total_sum = sum(labels[index] for index in indices)
            total_sq = sum(labels[index] ** 2 for index in indices)
            for position in range(len(ordered) - 1):
                value, index = ordered[position]
                label = labels[index]
                left_sum += label
                left_sq += label * label
                left_count = position + 1
                right_count = len(ordered) - left_count
                next_value = ordered[position + 1][0]
                if left_count < min_leaf or right_count < min_leaf or value == next_value:
                    continue
                right_sum = total_sum - left_sum
                right_sq = total_sq - left_sq
                loss = (
                    left_sq - left_sum * left_sum / left_count
                    + right_sq - right_sum * right_sum / right_count
                )
                threshold = (value + next_value) / 2.0
                key = (loss, name, threshold)
                if best is None or key < best[:3]:
                    left = [item_index for _, item_index in ordered[:left_count]]
                    right = [item_index for _, item_index in ordered[left_count:]]
                    best = (loss, name, threshold, left, right)
        if best is None:
            return node
        _, node.feature, node.threshold, left_indices, right_indices = best
        node.left = build(left_indices, depth + 1)
        node.right = build(right_indices, depth + 1)
        return node

    return build(list(range(len(rows))), 0)


def _training_targets(values: list[float]) -> tuple[list[float], float]:
    """用训练折非零绝对值中位数缩放并作 asinh 稳健变换。"""

    nonzero = [abs(value) for value in values if value != 0]
    scale = statistics.median(nonzero) if nonzero else 1.0
    return [math.asinh(value / scale) for value in values], float(scale)


def metrics(rows: list[dict], decisions: list[bool]) -> dict:
    """按未选动作记零，计算门控策略的配对效用和分类读数。"""

    auxiliary = [
        float(row["labels"]["focal_stage_score_delta"]) if decision else 0.0
        for row, decision in zip(rows, decisions)
    ]
    primary = [
        float(row["labels"]["u_low_delta"]) if decision else 0.0
        for row, decision in zip(rows, decisions)
    ]
    positives = [float(row["labels"]["focal_stage_score_delta"]) > 0 for row in rows]
    positive_total = sum(positives)
    negative_total = len(rows) - positive_total
    true_positive = sum(decision and positive for decision, positive in zip(decisions, positives))
    true_negative = sum(not decision and not positive for decision, positive in zip(decisions, positives))
    balanced = 0.5 * (
        (true_positive / positive_total if positive_total else 0.0)
        + (true_negative / negative_total if negative_total else 0.0)
    )
    result = {
        "rows": len(rows),
        "claim_count": sum(decisions),
        "auxiliary_policy_mean": statistics.fmean(auxiliary),
        "primary_policy_mean": statistics.fmean(primary),
        "balanced_accuracy": balanced,
    }
    by_mix = {}
    for mix in ("H", "M"):
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
    """每次留出一个完整 panel_seed，训练过程看不到该来源。"""

    predictions = [0.0] * len(rows)
    folds = []
    seeds = sorted({row["group"]["panel_seed"] for row in rows})
    for seed in seeds:
        train = [index for index, row in enumerate(rows) if row["group"]["panel_seed"] != seed]
        valid = [index for index, row in enumerate(rows) if row["group"]["panel_seed"] == seed]
        raw_targets = [float(rows[index]["labels"]["focal_stage_score_delta"]) for index in train]
        targets, scale = _training_targets(raw_targets)
        model = fit([vectors[index] for index in train], targets)
        fold_predictions = [model.predict(vectors[index]) for index in valid]
        for index, prediction in zip(valid, fold_predictions):
            predictions[index] = prediction
        fold_decisions = [prediction > 0 for prediction in fold_predictions]
        folds.append({
            "held_out_panel_seed": seed,
            "training_rows": len(train),
            "validation_rows": len(valid),
            "target_scale": scale,
            "metrics": metrics([rows[index] for index in valid], fold_decisions),
        })
    return predictions, folds


def prepare() -> None:
    """冻结数据、候选模型、交叉验证分组和继续门槛。"""

    if OUT.exists():
        raise SystemExit("AV1-2 目录已存在；拒绝覆盖")
    data_result = batch.read(DATA_RESULT)
    if data_result["status"] != "PASS_AV1_1_DATASET_FOR_GROUPED_MODELING":
        raise ValueError("AV1-1 未授权建模")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r10-av1-action-value-model",
        authorization_id="r10-av1-action-value-model-20260921",
        accounts={"tables_full": 0, "model_fits": len(RIDGE_LAMBDAS) * 2 + len(TREE_CONFIGS) * 2},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "AV1-1取得128个机械有效、来源分层且动作族覆盖的数据行",
        "scope": "只在AV1-1训练池按panel_seed两折交叉验证；零新桌赛；不接触未来冻结验证来源",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=[Path(__file__), DATA, DATA_RESULT, PLAN, _project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r10-av1-action-value-model/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "data": str(DATA),
        "data_sha256": digest(DATA),
        "data_result": str(DATA_RESULT),
        "data_result_sha256": digest(DATA_RESULT),
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "feature_projection": "固定公开状态数值投影：手牌34维、相对座位牌河/副露、最近公开事件、阶段处境、具体动作、规则事实、全部后继分支和条件路线摘要；无标签/来源身份",
        "target": "每个训练折以非零绝对辅助标签中位数缩放，asinh稳健变换；决策阈值固定为预测值>0",
        "folds": "leave-one-panel-seed-out，两折各64个未见来源行；同一来源根永不跨折",
        "candidates": {
            "linear_ridge_lambda": list(RIDGE_LAMBDAS),
            "regression_tree_depth_min_leaf": [list(item) for item in TREE_CONFIGS],
        },
        "selection_gate": {
            "nondegenerate": "16<=交叉验证claim_count<=112且balanced_accuracy>0.5",
            "overall": "辅助策略均值严格大于0且严格大于always-claim；主晋级下界策略均值>=0",
            "source_stability": "两个留出panel_seed的辅助策略均值均>0",
            "mix_stability": "H/M辅助和主晋级下界策略均值分别>=0",
            "tie_break": "先最大化min(H,M辅助均值)，再整体辅助均值，再平衡准确率，最后按candidate_id字典序",
            "meaning": "通过只授权冻结全新动作级验证，不是完整阶段或赛事强度证据",
        },
        "llm_calls": 0,
        "effect_tables": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED_AV1_2", "candidate_count": len(RIDGE_LAMBDAS) + len(TREE_CONFIGS)}, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """核对冻结训练池、计划和建模代码。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (
        ("data", "data_sha256"),
        ("data_result", "data_result_sha256"),
        ("plan", "plan_sha256"),
    ):
        if digest(Path(manifest[path_key])) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")


def run() -> None:
    """执行预登记模型族并一次性裁定是否值得全新来源验证。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("AV1-2 已执行；拒绝覆盖")
    rows = batch.read(DATA)["rows"]
    vectors = [flatten_features(row["features"]) for row in rows]
    candidate_specs: list[tuple[str, Callable]] = []
    for lam in RIDGE_LAMBDAS:
        candidate_specs.append((
            f"ridge:lambda={lam:g}",
            lambda x, y, lam=lam: fit_ridge(x, y, lam),
        ))
    for depth, min_leaf in TREE_CONFIGS:
        candidate_specs.append((
            f"tree:depth={depth}:min_leaf={min_leaf}",
            lambda x, y, depth=depth, min_leaf=min_leaf: fit_tree(x, y, depth, min_leaf),
        ))
    all_results = []
    always_claim = metrics(rows, [True] * len(rows))
    always_pass = metrics(rows, [False] * len(rows))
    for candidate_id, fitter in candidate_specs:
        predictions, folds = _cross_validate(rows, vectors, fitter)
        decisions = [value > 0 for value in predictions]
        score = metrics(rows, decisions)
        fold_aux = [fold["metrics"]["auxiliary_policy_mean"] for fold in folds]
        passes = bool(
            16 <= score["claim_count"] <= 112
            and score["balanced_accuracy"] > 0.5
            and score["auxiliary_policy_mean"] > 0
            and score["auxiliary_policy_mean"] > always_claim["auxiliary_policy_mean"]
            and score["primary_policy_mean"] >= 0
            and all(value > 0 for value in fold_aux)
            and all(score["by_mix"][mix]["auxiliary_policy_mean"] >= 0 for mix in ("H", "M"))
            and all(score["by_mix"][mix]["primary_policy_mean"] >= 0 for mix in ("H", "M"))
        )
        all_results.append({
            "candidate_id": candidate_id,
            "folds": folds,
            "metrics": score,
            "passes_selection_gate": passes,
        })
    eligible = [item for item in all_results if item["passes_selection_gate"]]
    eligible.sort(key=lambda item: (
        -min(item["metrics"]["by_mix"][mix]["auxiliary_policy_mean"] for mix in ("H", "M")),
        -item["metrics"]["auxiliary_policy_mean"],
        -item["metrics"]["balanced_accuracy"],
        item["candidate_id"],
    ))
    selected = eligible[0] if eligible else None
    final_model = None
    if selected is not None:
        candidate_id = selected["candidate_id"]
        fitter = dict(candidate_specs)[candidate_id]
        raw_targets = [float(row["labels"]["focal_stage_score_delta"]) for row in rows]
        targets, scale = _training_targets(raw_targets)
        model = fitter(vectors, targets)
        final_model = {
            "candidate_id": candidate_id,
            "target_scale": scale,
            "decision_threshold": 0.0,
            "feature_count": len({name for row in vectors for name in row}),
            "model": model.artifact(),
        }
    status = (
        "PASS_AV1_2_MODEL_FOR_NEW_SOURCE_ACTION_VALIDATION"
        if selected is not None
        else "CLOSE_AV1_2_AND_REVIEW_VALUE_TEACHER"
    )
    result = {
        "schema": "r10-av1-action-value-model-result/1",
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
            "冻结该模型和零阈值，在第三个全新panel_seed上采集H/M各32个顺序机会；验证前不得改特征、模型或阈值"
            if selected is not None
            else "停止扩大同类阈值/浅层模型；复盘Suphx奖励预测、rollout信息集条件和杭麻公开状态可预测性，决定是否构建多隐藏世界教师"
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
            {"candidate_id": item["candidate_id"], "metrics": item["metrics"], "passes": item["passes_selection_gate"]}
            for item in all_results
        ],
        "selected": None if selected is None else selected["candidate_id"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
