"""R11-DV1-2：按面板整组留出比较低容量弃牌成对排序模型。"""

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
from typing import Any, Protocol


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import claim_value_model as common  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/discard-value-grouped-model-01-20260921')
DATA_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/discard-value-scaled-teacher-01-20260921')
DATA = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/discard-value-scaled-teacher-01-20260921/dataset.json')
DATA_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/discard-value-scaled-teacher-01-20260921/result.json')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R11-DISCARD-ACTION-VALUE-EVOLUTION-PLAN-2026-09-21.md')
FEATURE_SCHEMA = "r11-discard-value-features/1"
RIDGE_LAMBDAS = (0.001, 0.01, 0.1)
TREE_CONFIGS = ((1, 48), (2, 48), (3, 48), (2, 64), (3, 64))
GAM_CONFIGS = ((8, 2, 0.25), (12, 2, 0.20), (16, 3, 0.15))
EVENT_KINDS = ("pass", "tile_discarded", "tile_drawn", "chi", "peng", "gang")
MELD_KINDS = ("chi", "peng", "gang")
FAMILIES = ("branch", "chain", "four_white", "baotou")
PROGRESS = ("advance", "same", "retreat", "close", "unknown")
ROUTE_STATUS = ("witnessed", "open_uncertain", "closed_proven", "unanalyzed")


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def flatten_features(encoded: dict) -> dict[str, float]:
    """把玩家可见状态与一个合法弃牌压成固定数值字典。"""

    if encoded.get("schema") != FEATURE_SCHEMA:
        raise ValueError("未知弃牌价值特征 schema")
    out: dict[str, float] = {}
    observation = encoded["observation"]
    common._one_hot(out, "phase", observation["phase"], ("draw",))
    for name in ("round_no", "snapshot_seq"):
        common._put(out, "observation." + name, observation[name])
    for name in ("dealer_relative_seat", "turn_relative_seat"):
        common._one_hot(out, name, observation[name], (0, 1, 2, 3))
    common._vector(out, "hand", observation["my_hand_counts"])
    common._optional_tile(out, "drawn", observation["drawn_tile"])
    for seat, river in enumerate(observation["discards"]):
        common._vector(out, f"discard.{seat}.count", river["counts"])
        common._put(out, f"discard.{seat}.length", len(river["sequence"]))
        for offset, tile in enumerate(reversed(river["sequence"][-3:]), start=1):
            common._put(out, f"discard.{seat}.recent{offset}.tile.{tile}", 1)
    for seat, melds in enumerate(observation["melds"]):
        aggregate = [0] * 34
        common._put(out, f"meld.{seat}.count", len(melds))
        for meld in melds:
            kind = meld["kind"] if meld["kind"] in MELD_KINDS else "other"
            key = f"meld.{seat}.kind.{kind}"
            common._put(out, key, out.get(key, 0) + 1)
            for index, count in enumerate(meld["tile_counts"]):
                aggregate[index] += int(count)
        common._vector(out, f"meld.{seat}.tiles", aggregate)
    common._vector(out, "hand_counts", observation["hand_counts"])
    common._vector(out, "scores", observation["scores"])
    for seat in range(1, 4):
        common._put(
            out, f"score_delta_to.{seat}",
            observation["scores"][0] - observation["scores"][seat],
        )
    common._put(out, "last_discard.known", observation["last_discard"]["known"])
    if observation["last_discard"]["known"]:
        last = observation["last_discard"]["value"]
        common._one_hot(out, "last_discard.seat", last["relative_seat"], (0, 1, 2, 3))
        common._put(out, f"last_discard.tile.{last['tile']}", 1)
    common._optional(out, "wall", observation["remaining_tile_count"])
    state = observation["rule_state"]
    common._put(out, f"wealth.tile.{state['wealth_god']}", 1)
    for name in ("baotou", "chain_count", "catch_play"):
        common._put(out, "rule_state." + name, state[name])
    common._optional(out, "rule_state.catch_owner", state["catch_play_owner_relative_seat"])
    common._optional(out, "chain_piao", observation["chain_piao"])
    common._optional(out, "gang_draw", observation["gang_draw"])
    common._put(out, "history.complete", observation["history_complete"])
    common._put(out, "history.length", len(observation["public_history"]))
    for event in observation["public_history"]:
        kind = event["kind"] if event["kind"] in EVENT_KINDS else "other"
        seat = event["relative_seat"]["value"] if event["relative_seat"]["known"] else "none"
        key = f"history.count.{kind}.seat.{seat}"
        common._put(out, key, out.get(key, 0) + 1)
    for offset, event in enumerate(reversed(observation["public_history"][-8:]), start=1):
        kind = event["kind"] if event["kind"] in EVENT_KINDS else "other"
        common._put(out, f"history.recent{offset}.kind.{kind}", 1)
        if event["relative_seat"]["known"]:
            common._put(out, f"history.recent{offset}.seat.{event['relative_seat']['value']}", 1)
        for tile in event["tiles"]:
            common._put(out, f"history.recent{offset}.tile.{tile}", 1)

    competition = encoded["competition"]
    for name in ("stage_no", "stage_total", "participant_rank"):
        common._optional(out, "competition." + name, competition[name])
    role = competition["stage_role"]
    common._put(out, "competition.stage_role.known", role["known"])
    if role["known"]:
        common._one_hot(out, "competition.stage_role", role["value"], ("qualifier", "final"))

    discard = encoded["discard"]
    tile = int(discard["tile"])
    common._put(out, f"action.tile.{tile}", 1)
    common._put(out, "action.is_honor", tile >= 27)
    common._put(out, "action.is_terminal", tile < 27 and tile % 9 in (0, 8))
    common._put(out, "action.hand_count", observation["my_hand_counts"][tile])
    common._put(out, "action.is_drawn", observation["drawn_tile"]["known"] and observation["drawn_tile"]["value"] == tile)
    common._put(out, "action.is_wealth", state["wealth_god"] == tile)
    if tile < 27:
        common._one_hot(out, "action.suit", tile // 9, (0, 1, 2))
        common._one_hot(out, "action.rank", tile % 9 + 1, tuple(range(1, 10)))

    facts = discard["facts"]
    common._put(out, "facts.known", facts["known"])
    if facts["known"]:
        common._one_hot(
            out, "facts.kind", facts["fact_kind"],
            ("hand_progress", "win", "not_applicable", "analysis_failed"),
        )
        for name in ("shanten", "standard_shanten", "seven_pairs_shanten"):
            common._optional(out, "facts." + name, facts[name])
        for name in ("useful_tiles", "standard_useful_tiles", "seven_pairs_useful_tiles"):
            item = facts[name]
            common._put(out, f"facts.{name}.known", item["known"])
            if item["known"]:
                common._vector(out, f"facts.{name}", item["remaining_by_tile"])
                common._put(out, f"facts.{name}.sum", sum(item["remaining_by_tile"]))
        common._put(out, "facts.replacement_unknown", facts["replacement_draw_unknown"])
        common._one_hot(out, "facts.completeness", facts["completeness"], ("complete", "degraded"))
        by_family = {item["family"]: item for item in facts["family_progress"]}
        for family in FAMILIES:
            item = by_family.get(family)
            common._put(out, f"family.{family}.known", item is not None)
            if item is not None:
                common._one_hot(out, f"family.{family}.progress", item["progress"], PROGRESS)
                common._one_hot(out, f"family.{family}.status", item["route_status"], ROUTE_STATUS)

    value = discard["value_facts"]
    common._put(out, "value.known", value["known"])
    if value["known"]:
        common._one_hot(out, "value.coverage", value["coverage"], ("complete", "partial", "unavailable"))
        common._put(out, "value.route_count", len(value["routes"]))
        if value["routes"]:
            fans = [float(item["settlement"]["fan"]) for item in value["routes"]]
            own = [float(item["settlement"]["score_delta"][0]) for item in value["routes"]]
            support = [sum(item["useful_tiles"]["remaining_by_tile"]) for item in value["routes"]]
            for name, values in (("fan", fans), ("own_delta", own), ("support", support)):
                common._put(out, f"value.{name}.min", min(values))
                common._put(out, f"value.{name}.max", max(values))
                common._put(out, f"value.{name}.mean", statistics.fmean(values))
    return out


def difference(left: dict[str, float], right: dict[str, float]) -> dict[str, float]:
    """返回同一观察下两个动作特征的稀疏差。"""

    return {
        name: value
        for name in set(left) | set(right)
        if abs(value := left.get(name, 0.0) - right.get(name, 0.0)) > 1e-12
    }


def pair_features(action: dict[str, float], baseline: dict[str, float]) -> dict[str, float]:
    """组合公共观察上下文与动作相对 V2 的差分。

    公共上下文使树和加性模型能够按轮次、积分、手牌与公开历史决定是否偏离
    V2；差分部分负责区分同窗替代弃牌。H/M、来源和未来顺序从未进入字典。
    """

    action_prefixes = ("action.", "facts.", "family.", "value.")
    result = {
        "context." + name: value
        for name, value in baseline.items()
        if not name.startswith(action_prefixes)
    }
    result.update({"delta." + name: value for name, value in difference(action, baseline).items()})
    return result


def label_weight(values: list[float]) -> float:
    """按有效轨迹数与配对标准误生成有界训练权重。"""

    stdev = statistics.stdev(values)
    standard_error = stdev / math.sqrt(len(values))
    return min(2.0, max(0.25, math.sqrt(len(values)) / (1.0 + standard_error / 10.0)))


def examples(rows: list[dict]) -> list[dict]:
    """按预登记阶段构造相互独立的成对训练样本。

    首四条对全部动作成立；被追加预算的动作把 5–8、9–16 分别作为新样本，
    不把触发晋级的高读数与后续确认轨迹平均成一个带赢家诅咒的标签。
    """

    result = []
    for row in rows:
        actions = {item["action_key"]: item for item in row["actions"]}
        baseline = actions[row["baseline_action_key"]]
        baseline_features = flatten_features(baseline["features"])
        for action_key in sorted(actions):
            action = actions[action_key]
            if action["is_v2_baseline"]:
                continue
            values = [float(value) for value in action["labels"]["auxiliary_values"]]
            blocks = [("stage1", values[:4])]
            if len(values) >= 8:
                blocks.append(("stage2", values[4:8]))
            if len(values) >= 16:
                blocks.append(("stage3", values[8:16]))
            features = pair_features(flatten_features(action["features"]), baseline_features)
            for block, block_values in blocks:
                result.append({
                    "row_id": row["row_id"],
                    "panel_seed": int(row["group"]["panel_seed"]),
                    "mix": str(row["group"]["mix"]),
                    "action_key": action_key,
                    "sample_block": block,
                    "features": features,
                    "label": statistics.fmean(block_values),
                    "weight": label_weight(block_values),
                    "rollout_count": len(block_values),
                })
    return result


class Model(Protocol):
    """成对优势模型的最小预测接口。"""

    def predict(self, row: dict[str, float]) -> float: ...
    def artifact(self) -> dict: ...


@dataclass
class SgdRidge:
    """零截距、按特征均方缩放的确定性岭回归。"""

    scales: dict[str, float]
    weights: dict[str, float]
    target_scale: float
    lam: float

    def _normalized(self, row: dict[str, float]) -> dict[str, float]:
        values = {name: value / self.scales[name] for name, value in row.items() if name in self.scales}
        norm = math.sqrt(sum(value * value for value in values.values())) or 1.0
        return {name: value / norm for name, value in values.items()}

    def predict(self, row: dict[str, float]) -> float:
        values = self._normalized(row)
        return sum(self.weights.get(name, 0.0) * value for name, value in values.items())

    def artifact(self) -> dict:
        return {
            "kind": "paired_sgd_ridge",
            "lambda": self.lam,
            "target_scale": self.target_scale,
            "scales": dict(sorted(self.scales.items())),
            "weights": dict(sorted(self.weights.items())),
        }


def fit_sgd_ridge(rows: list[dict], lam: float) -> SgdRidge:
    """用冻结顺序的加权 SGD 拟合成对优势。"""

    names = sorted({name for row in rows for name in row["features"]})
    scales = {}
    for name in names:
        mean_square = statistics.fmean(row["features"].get(name, 0.0) ** 2 for row in rows)
        if mean_square > 1e-12:
            scales[name] = math.sqrt(mean_square)
    nonzero = [abs(float(row["label"])) for row in rows if row["label"] != 0]
    target_scale = statistics.median(nonzero) if nonzero else 1.0
    model = SgdRidge(scales=scales, weights={}, target_scale=target_scale, lam=lam)
    normalized = [model._normalized(row["features"]) for row in rows]
    targets = [math.asinh(float(row["label"]) / target_scale) for row in rows]
    sample_weights = [float(row["weight"]) for row in rows]
    for epoch in range(80):
        learning_rate = 0.08 / math.sqrt(epoch + 1.0)
        order = range(len(rows)) if epoch % 2 == 0 else range(len(rows) - 1, -1, -1)
        for index in order:
            values = normalized[index]
            prediction = sum(model.weights.get(name, 0.0) * value for name, value in values.items())
            error = (prediction - targets[index]) * sample_weights[index]
            for name, value in values.items():
                old = model.weights.get(name, 0.0)
                model.weights[name] = old - learning_rate * (
                    error * value + lam * old / max(1, len(rows))
                )
    return model


@dataclass
class CenteredTree:
    """以零差特征为 V2 基准的浅层回归树。"""

    root: common.TreeNode
    target_scale: float
    depth: int
    min_leaf: int

    def predict(self, row: dict[str, float]) -> float:
        return self.root.predict(row) - self.root.predict({})

    def artifact(self) -> dict:
        return {
            "kind": "centered_regression_tree",
            "target_scale": self.target_scale,
            "max_depth": self.depth,
            "min_leaf": self.min_leaf,
            "tree": self.root.artifact(),
        }


def fit_centered_tree(rows: list[dict], depth: int, min_leaf: int) -> CenteredTree:
    """拟合受限树；目标作训练折内稳健变换。"""

    expanded = [
        row for row in rows
        for _ in range(max(1, round(float(row["weight"]) * 4)))
    ]
    raw = [float(row["label"]) for row in expanded]
    transformed, scale = common._training_targets(raw)
    root = common.fit_tree([row["features"] for row in expanded], transformed, depth, min_leaf)
    return CenteredTree(root=root, target_scale=scale, depth=depth, min_leaf=min_leaf)


@dataclass
class GamTerm:
    """一个数值特征上的分段常数加性项。"""

    feature: str
    thresholds: list[float]
    values: list[float]

    def predict(self, row: dict[str, float]) -> float:
        value = row.get(self.feature, 0.0)
        index = sum(value > threshold for threshold in self.thresholds)
        return self.values[index]


@dataclass
class AdditiveGam:
    """有限特征、有限分箱的低容量广义加性近似。"""

    intercept: float
    terms: list[GamTerm]
    target_scale: float
    feature_limit: int
    passes: int
    shrinkage: float

    def _raw(self, row: dict[str, float]) -> float:
        return self.intercept + sum(term.predict(row) for term in self.terms)

    def predict(self, row: dict[str, float]) -> float:
        return self._raw(row) - self._raw({})

    def artifact(self) -> dict:
        return {
            "kind": "centered_binned_gam",
            "target_scale": self.target_scale,
            "feature_limit": self.feature_limit,
            "passes": self.passes,
            "shrinkage": self.shrinkage,
            "intercept": self.intercept,
            "terms": [term.__dict__ for term in self.terms],
        }


def _tree_from_artifact(data: dict) -> common.TreeNode:
    """从冻结 JSON 重建受限树。"""

    node = common.TreeNode(value=float(data["value"]))
    if "feature" in data:
        node.feature = str(data["feature"])
        node.threshold = float(data["threshold"])
        node.left = _tree_from_artifact(data["left"])
        node.right = _tree_from_artifact(data["right"])
    return node


def model_from_artifact(artifact: dict) -> Model:
    """重建冻结模型，供独立动作验证和后续确定性编译复用。"""

    kind = artifact.get("kind")
    if kind == "paired_sgd_ridge":
        return SgdRidge(
            scales={str(key): float(value) for key, value in artifact["scales"].items()},
            weights={str(key): float(value) for key, value in artifact["weights"].items()},
            target_scale=float(artifact["target_scale"]),
            lam=float(artifact["lambda"]),
        )
    if kind == "centered_regression_tree":
        return CenteredTree(
            root=_tree_from_artifact(artifact["tree"]),
            target_scale=float(artifact["target_scale"]),
            depth=int(artifact["max_depth"]),
            min_leaf=int(artifact["min_leaf"]),
        )
    if kind == "centered_binned_gam":
        return AdditiveGam(
            intercept=float(artifact["intercept"]),
            terms=[GamTerm(
                feature=str(item["feature"]),
                thresholds=[float(value) for value in item["thresholds"]],
                values=[float(value) for value in item["values"]],
            ) for item in artifact["terms"]],
            target_scale=float(artifact["target_scale"]),
            feature_limit=int(artifact["feature_limit"]),
            passes=int(artifact["passes"]),
            shrinkage=float(artifact["shrinkage"]),
        )
    raise ValueError("未知弃牌成对模型 artifact：" + str(kind))


def decision_from_artifact(artifact: dict) -> tuple[Model, float]:
    """重建冻结的动作模型与偏离 V2 阈值。"""

    if artifact.get("schema") != "r11-dv1-discard-decision-artifact/1":
        raise ValueError("未知弃牌决策 artifact schema")
    return model_from_artifact(artifact["model"]), float(artifact["decision_threshold"])


def fit_gam(rows: list[dict], feature_limit: int, passes: int, shrinkage: float) -> AdditiveGam:
    """按训练折加权协方差选特征并作确定性回拟合。"""

    raw = [float(row["label"]) for row in rows]
    targets, scale = common._training_targets(raw)
    weights = [float(row["weight"]) for row in rows]
    names = sorted({name for row in rows for name in row["features"]})
    mean_target = sum(w * y for w, y in zip(weights, targets)) / sum(weights)
    covariance = {}
    for name in names:
        values = [row["features"].get(name, 0.0) for row in rows]
        mean_value = sum(w * x for w, x in zip(weights, values)) / sum(weights)
        covariance[name] = abs(sum(
            w * (x - mean_value) * (y - mean_target)
            for w, x, y in zip(weights, values, targets)
        ))
    selected = sorted(names, key=lambda name: (-covariance[name], name))[:feature_limit]
    predictions = [mean_target] * len(rows)
    terms: list[GamTerm] = []
    for _ in range(passes):
        for name in selected:
            unique = sorted({row["features"].get(name, 0.0) for row in rows})
            if len(unique) < 2:
                continue
            thresholds = []
            for numerator in (1, 2, 3):
                index = min(len(unique) - 2, max(0, len(unique) * numerator // 4 - 1))
                threshold = (unique[index] + unique[index + 1]) / 2.0
                if not thresholds or threshold != thresholds[-1]:
                    thresholds.append(threshold)
            bin_count = len(thresholds) + 1
            sums = [0.0] * bin_count
            totals = [0.0] * bin_count
            for index, row in enumerate(rows):
                value = row["features"].get(name, 0.0)
                bin_index = sum(value > threshold for threshold in thresholds)
                residual = targets[index] - predictions[index]
                sums[bin_index] += weights[index] * residual
                totals[bin_index] += weights[index]
            values = [shrinkage * sums[index] / totals[index] if totals[index] else 0.0 for index in range(bin_count)]
            term = GamTerm(name, thresholds, values)
            terms.append(term)
            for index, row in enumerate(rows):
                predictions[index] += term.predict(row)
    return AdditiveGam(mean_target, terms, scale, feature_limit, passes, shrinkage)


def source_paths() -> list[Path]:
    """列出模型批次冻结的代码和计划。"""

    return [Path(__file__), Path(common.__file__), PLAN]


def prepare() -> None:
    """冻结数据、完整面板留出、模型族和继续判据。"""

    if OUT.exists():
        raise SystemExit("DV1-2 模型目录已存在；拒绝覆盖")
    if not DATA.exists() or not DATA_RESULT.exists():
        raise SystemExit("规模化教师尚未形成不可变数据和结果")
    teacher_result = batch.read(DATA_RESULT)
    if teacher_result.get("status") != "PASS_DV1_2_SCALED_TEACHER_FOR_GROUPED_MODELING":
        raise SystemExit("规模化教师未通过分组建模入口")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label="r11-dv1-grouped-discard-model-v1",
        authorization_id="r11-dv1-grouped-discard-model-v1-20260921",
        accounts={},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "DV1-2规模化教师机械完整后，按计划比较低容量成对排序器、受限树和广义加性模型",
        "scope": "四个panel_seed逐一完整留出；H/M不作输入；留出评价统一使用每动作前4个共同未来顺序，避免分级采样选择偏差",
        "max_model_calls": 0,
        "max_model_fits_per_fold": len(RIDGE_LAMBDAS) + len(TREE_CONFIGS) + len(GAM_CONFIGS),
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    manifest = {
        "schema": "r11-dv1-grouped-discard-model/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "data": str(DATA),
        "data_sha256": digest(DATA),
        "data_result": str(DATA_RESULT),
        "data_result_sha256": digest(DATA_RESULT),
        "feature_schema": FEATURE_SCHEMA,
        "validation": "leave-one-panel-seed-out；同一快照全部动作永不拆分；H/M只作域读数",
        "training_target": "动作相对同窗V2的配对辅助积分；1–4、5–8、9–16轨迹分为独立stage1/2/3样本，不把触发晋级的读数与后续确认轨迹合并；训练折内asinh稳健缩放",
        "training_weight": "每个独立阶段块使用min(2,max(0.25,sqrt(n)/(1+paired_standard_error/10)))；树用weight×4确定性复制近似",
        "threshold_calibration": "每个训练折只在0及训练预测正边际的25/50/75/90分位和全跟随V2上限中选择；先要求训练u_low与H/M非负，再按最差训练面板、最差H/M、总体辅助增益排序；留出面板不参与",
        "heldout_evaluation": "模型选择动作相对V2在首4个共同未来顺序的辅助积分和u_low均值；追加轨迹不进入留出效果读数",
        "ridge_lambdas": list(RIDGE_LAMBDAS),
        "tree_configs": [list(item) for item in TREE_CONFIGS],
        "gam_configs": [list(item) for item in GAM_CONFIGS],
        "continue_gate": "每个留出panel_seed辅助均值>0；H/M辅助均值>=0；整体u_low均值>=0；改动率在5%到95%；改动动作不由单一action_key占80%以上",
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({"status": "PREPARED_DV1_2_GROUPED_MODEL"}, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """确认代码、计划和教师数据未漂移。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (
        ("plan", "plan_sha256"),
        ("data", "data_sha256"),
        ("data_result", "data_result_sha256"),
    ):
        if digest(Path(manifest[path_key])) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")


def model_specs() -> list[tuple[str, Any]]:
    """返回冻结模型规格和拟合函数。"""

    specs = []
    for lam in RIDGE_LAMBDAS:
        specs.append((f"ridge:lambda={lam}", lambda rows, value=lam: fit_sgd_ridge(rows, value)))
    for depth, min_leaf in TREE_CONFIGS:
        specs.append((
            f"tree:depth={depth}:min_leaf={min_leaf}",
            lambda rows, d=depth, leaf=min_leaf: fit_centered_tree(rows, d, leaf),
        ))
    for feature_limit, passes, shrinkage in GAM_CONFIGS:
        specs.append((
            f"gam:features={feature_limit}:passes={passes}:shrinkage={shrinkage}",
            lambda rows, f=feature_limit, p=passes, s=shrinkage: fit_gam(rows, f, p, s),
        ))
    return specs


def choose(model: Model, row: dict, threshold: float = 0.0) -> tuple[str, dict[str, float]]:
    """在一个完整合法弃牌集合内按预测优势选择动作。"""

    actions = {item["action_key"]: item for item in row["actions"]}
    baseline_key = str(row["baseline_action_key"])
    baseline_features = flatten_features(actions[baseline_key]["features"])
    scores = {baseline_key: 0.0}
    for action_key in sorted(actions):
        if action_key == baseline_key:
            continue
        scores[action_key] = model.predict(pair_features(
            flatten_features(actions[action_key]["features"]), baseline_features
        ))
    alternative_best = max(value for key, value in scores.items() if key != baseline_key)
    if alternative_best <= threshold:
        return baseline_key, scores
    return min(
        key for key, value in scores.items()
        if key != baseline_key and abs(value - alternative_best) <= 1e-12
    ), scores


def heldout_decision(
    model: Model, row: dict, model_id: str, heldout_seed: int,
    threshold: float = 0.0,
) -> dict:
    """用所有动作共有的前四条未来顺序评价一个留出决定。"""

    selected, scores = choose(model, row, threshold)
    actions = {item["action_key"]: item for item in row["actions"]}
    baseline = str(row["baseline_action_key"])
    action = actions[selected]
    auxiliary_values = [float(value) for value in action["labels"]["auxiliary_values"][:4]]
    primary_values = [float(value) for value in action["labels"]["u_low_values"][:4]]
    return {
        "model_id": model_id,
        "heldout_panel_seed": heldout_seed,
        "row_id": row["row_id"],
        "mix": row["group"]["mix"],
        "baseline_action_key": baseline,
        "selected_action_key": selected,
        "changed": selected != baseline,
        "auxiliary_mean_first4": statistics.fmean(auxiliary_values),
        "u_low_mean_first4": statistics.fmean(primary_values),
        "selected_score": scores[selected],
        "decision_threshold": threshold,
    }


def calibrate_threshold(model: Model, rows: list[dict]) -> tuple[float, dict]:
    """只用训练面板选择保守偏离阈值。"""

    margins = []
    for row in rows:
        _, scores = choose(model, row, threshold=-1.0e300)
        baseline = str(row["baseline_action_key"])
        margins.append(max(value for key, value in scores.items() if key != baseline))
    positive = sorted(value for value in margins if value > 0)
    candidates = {0.0}
    for quantile in (0.25, 0.50, 0.75, 0.90):
        if positive:
            candidates.add(positive[round((len(positive) - 1) * quantile)])
    candidates.add((max(positive) + 1.0) if positive else 1.0)
    readings = []
    for threshold in sorted(candidates):
        decisions = [
            heldout_decision(
                model, row, "threshold-calibration",
                int(row["group"]["panel_seed"]), threshold,
            )
            for row in rows
        ]
        summary = aggregate(decisions)
        feasible = bool(
            summary["overall"]["u_low_mean_first4"] >= 0
            and all(item["auxiliary_mean_first4"] >= 0 for item in summary["by_mix"].values())
            and summary["overall"]["changed_rate"] <= 0.95
        )
        readings.append({"threshold": threshold, "feasible": feasible, "metrics": summary})
    feasible = [item for item in readings if item["feasible"]]
    selected = max(feasible or readings, key=lambda item: (
        item["feasible"],
        min(value["auxiliary_mean_first4"] for value in item["metrics"]["by_panel_seed"].values()),
        min(value["auxiliary_mean_first4"] for value in item["metrics"]["by_mix"].values()),
        item["metrics"]["overall"]["auxiliary_mean_first4"],
        -item["metrics"]["overall"]["changed_rate"],
        item["threshold"],
    ))
    return float(selected["threshold"]), {
        "candidates": readings,
        "selected_threshold": selected["threshold"],
    }


def aggregate(decisions: list[dict]) -> dict:
    """汇总留出决策的面板、H/M 与行为读数。"""

    def metrics(items: list[dict]) -> dict:
        return {
            "count": len(items),
            "auxiliary_mean_first4": statistics.fmean(item["auxiliary_mean_first4"] for item in items),
            "u_low_mean_first4": statistics.fmean(item["u_low_mean_first4"] for item in items),
            "changed_rate": statistics.fmean(float(item["changed"]) for item in items),
        }

    seeds = sorted({int(item["heldout_panel_seed"]) for item in decisions})
    mixes = sorted({str(item["mix"]) for item in decisions})
    changed = [item for item in decisions if item["changed"]]
    counts: dict[str, int] = {}
    for item in changed:
        key = str(item["selected_action_key"])
        counts[key] = counts.get(key, 0) + 1
    fixed_fraction = max(counts.values()) / len(changed) if changed else 1.0
    return {
        "overall": metrics(decisions),
        "by_panel_seed": {
            str(seed): metrics([item for item in decisions if item["heldout_panel_seed"] == seed])
            for seed in seeds
        },
        "by_mix": {
            mix: metrics([item for item in decisions if item["mix"] == mix])
            for mix in mixes
        },
        "changed_action_counts": dict(sorted(counts.items())),
        "max_changed_action_fraction": fixed_fraction,
    }


def passes_gate(summary: dict) -> bool:
    """应用预登记的 DV1-2 继续门。"""

    overall = summary["overall"]
    return bool(
        all(item["auxiliary_mean_first4"] > 0 for item in summary["by_panel_seed"].values())
        and all(item["auxiliary_mean_first4"] >= 0 for item in summary["by_mix"].values())
        and overall["u_low_mean_first4"] >= 0
        and 0.05 <= overall["changed_rate"] <= 0.95
        and summary["max_changed_action_fraction"] < 0.80
    )


def run() -> None:
    """执行逐面板留出，冻结最佳通过模型或关闭本轮。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("DV1-2 模型结果已存在；拒绝覆盖")
    dataset = batch.read(DATA)
    rows = list(dataset["rows"])
    all_examples = examples(rows)
    panel_seeds = sorted({int(row["group"]["panel_seed"]) for row in rows})
    by_model: dict[str, list[dict]] = {model_id: [] for model_id, _ in model_specs()}
    fold_artifacts = []
    for heldout_seed in panel_seeds:
        training = [item for item in all_examples if item["panel_seed"] != heldout_seed]
        training_rows = [
            row for row in rows
            if int(row["group"]["panel_seed"]) != heldout_seed
        ]
        heldout = [row for row in rows if int(row["group"]["panel_seed"]) == heldout_seed]
        for model_id, fitter in model_specs():
            model = fitter(training)
            threshold, calibration = calibrate_threshold(model, training_rows)
            decisions = [
                heldout_decision(model, row, model_id, heldout_seed, threshold)
                for row in heldout
            ]
            by_model[model_id].extend(decisions)
            fold_artifacts.append({
                "heldout_panel_seed": heldout_seed,
                "model_id": model_id,
                "training_examples": len(training),
                "heldout_snapshots": len(heldout),
                "decision_threshold": threshold,
                "threshold_calibration": calibration,
                "artifact": model.artifact(),
            })
    comparisons = []
    for model_id, decisions in by_model.items():
        summary = aggregate(decisions)
        comparisons.append({
            "model_id": model_id,
            "passes_continue_gate": passes_gate(summary),
            "metrics": summary,
        })
    comparisons.sort(key=lambda item: item["model_id"])
    passing = [item for item in comparisons if item["passes_continue_gate"]]
    if passing:
        best = max(passing, key=lambda item: (
            min(value["auxiliary_mean_first4"] for value in item["metrics"]["by_panel_seed"].values()),
            min(value["auxiliary_mean_first4"] for value in item["metrics"]["by_mix"].values()),
            item["metrics"]["overall"]["auxiliary_mean_first4"],
            item["model_id"],
        ))
        selected_id = best["model_id"]
        fitter = dict(model_specs())[selected_id]
        final_model = fitter(all_examples)
        final_threshold, final_calibration = calibrate_threshold(final_model, rows)
        status = "PASS_DV1_2_GROUPED_MODEL_FOR_INDEPENDENT_ACTION_VALIDATION"
        next_step = "冻结模型与阈值，在全新面板上执行独立动作验证；当前数据不得回流"
        artifact = {
            "schema": "r11-dv1-discard-decision-artifact/1",
            "decision_threshold": final_threshold,
            "threshold_calibration": final_calibration,
            "model": final_model.artifact(),
        }
    else:
        selected_id = None
        status = "CLOSE_DV1_2_GROUPED_MODELS_NO_GENERALIZATION"
        next_step = "按计划复盘全局奖励预测、目标/动作分解和隐藏状态平均；不得邻近调参补跑"
        artifact = None
    batch.write(_project_file(_PROJECT_ROOT, OUT / "decisions.json"), {
        "schema": "r11-dv1-grouped-discard-decisions/1",
        "decisions_by_model": by_model,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "fold-artifacts.json"), {
        "schema": "r11-dv1-grouped-discard-fold-artifacts/1",
        "folds": fold_artifacts,
    })
    result = {
        "schema": "r11-dv1-grouped-discard-model-result/1",
        "status": status,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "data_sha256": digest(DATA),
        "snapshots": len(rows),
        "training_examples": len(all_examples),
        "panel_seeds": panel_seeds,
        "comparisons": comparisons,
        "selected_model_id": selected_id,
        "selected_model_artifact": artifact,
        "next": next_step,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    verify_inputs(manifest)
    print(json.dumps({
        "status": status,
        "snapshots": len(rows),
        "training_examples": len(all_examples),
        "selected_model_id": selected_id,
        "passing_models": [item["model_id"] for item in passing],
        "next": next_step,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
