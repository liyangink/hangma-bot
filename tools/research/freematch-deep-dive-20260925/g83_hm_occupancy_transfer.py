#!/usr/bin/env python3
"""G83：新 H/M 根上只跑 R18 v2，诊断 G79B 隐藏占用预测的迁移。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter, defaultdict
import concurrent.futures
import hashlib
import json
import math
from pathlib import Path
import random

import g14_accounted_paired_panel as panel
import g81_posterior_wall_policy as posterior
from hangma_bot.hangma.engine import _build_context
from hangma_bot.hangma.interface import RuleCompleteness
from hangma_bot.simulation._research_hidden_labels import hidden_partition_counts


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g83-hm-occupancy-transfer-20260928')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G83-HM-OCCUPANCY-TRANSFER-PREREG-2026-09-28.md')
SEED = 2026122901
ROOTS = tuple(range(1, 13))
POSITIONS = (1, 4, 7)
ORDER = posterior.ORDER


def digest(path: Path) -> str:
    """冻结研究输入的字节身份。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def window_id(window_key) -> tuple[str, int, int, str, int]:
    """官方式动作窗口键；不借决策 ID 推测世界位置。"""

    return (window_key.game_id, window_key.round_no, window_key.trigger_seq,
            window_key.phase.value, window_key.seat)


def _direct_trace(item) -> dict | None:
    """只接受 R18 v2 原始直接评分且没有专项覆盖的动作。"""

    detail = ((item.score_trace or {}).get("detail") or {})
    if detail.get("basis") != "direct_v2" or any(
        isinstance(value, dict) and value.get("triggered") is True
        for value in detail.values()
    ):
        return None
    return detail


def _pair(request, plan, unknown: tuple[int, ...]) -> dict | None:
    """仅按父代原排名和生产规则事实选择 A/B，不读取后验或真墙。"""

    if (request.rules.completeness is not RuleCompleteness.COMPLETE
            or len(plan.candidates) < 2):
        return None
    parent = plan.candidates[0]
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    if (not parent.action_key.startswith("discard:")
            or parent.action_key not in legal or not posterior._usable(legal[parent.action_key])
            or _direct_trace(parent) is None):
        return None
    parent_facts = legal[parent.action_key].facts
    parent_codes = posterior._useful(parent_facts, unknown)
    if parent_codes is None:
        return None
    own_white = sum(tile.code == "白" for tile in _build_context(request.observation).full_hand())
    parent_white = own_white - int(parent.action_key == "discard:白")
    for alt in plan.candidates[1:]:
        key = alt.action_key
        if (not key.startswith("discard:") or key not in legal
                or not posterior._usable(legal[key]) or _direct_trace(alt) is None):
            continue
        facts = legal[key].facts
        if (facts.shanten_after != parent_facts.shanten_after
                or facts.standard_shanten_after != parent_facts.standard_shanten_after
                or (parent_facts.seven_pairs_shanten_after is None) !=
                   (facts.seven_pairs_shanten_after is None)
                or (parent_facts.seven_pairs_shanten_after is not None
                    and facts.seven_pairs_shanten_after > parent_facts.seven_pairs_shanten_after)
                or (parent_facts.baotou_after is True and facts.baotou_after is not True)
                or own_white - int(key == "discard:白") < parent_white):
            continue
        alt_codes = posterior._useful(facts, unknown)
        if alt_codes is None:
            continue
        a = tuple(posterior.INDEX[code] for code in parent_codes)
        b = tuple(posterior.INDEX[code] for code in alt_codes)
        return {"parent_action": parent.action_key, "alternative_action": key,
                "parent_useful_indices": a, "alternative_useful_indices": b,
                "public_difference": sum(unknown[index] for index in b)
                                     - sum(unknown[index] for index in a),
                "parent_score_gap": parent.total_score - alt.total_score}
    return None


def _visible(request, plan) -> dict | None:
    """研究行只含 PlayerObservation、规则和父代计划导出的事实。"""

    if request.window_key.phase.value != "draw":
        return None
    obs = request.observation
    position = len(obs.discards[obs.seat]) + 1
    if position not in POSITIONS:
        return None
    forecast = posterior.predict_wall_counts(obs)
    if forecast is None:
        return {"key": window_id(request.window_key), "position": position,
                "exclude": "forecast_unavailable"}
    unknown, model_wall, H, W = forecast
    if (not math.isclose(sum(model_wall), W, abs_tol=1e-6)
            or any(not math.isfinite(value) for value in model_wall)):
        raise ValueError("模型墙余预测不守恒或非有限")
    pair = _pair(request, plan, unknown)
    return {"key": window_id(request.window_key), "position": position,
            "unknown": unknown, "model_wall": model_wall, "H": H, "W": W,
            "pair": pair}


class PlanTap:
    """原样转发冻结父代；只在返回计划后采集可见测量输入。"""

    def __init__(self, base, rows: dict):
        self.base = base
        self.rows = rows
        self.policy_id = base.policy_id
        self.max_operations = getattr(base, "max_operations", None)

    async def choose(self, request, budget):
        """与父代相同地选动作；额外计算不可进入父代的研究特征。"""

        plan = await self.base.choose(request, budget)
        row = _visible(request, plan)
        if row is not None:
            key = tuple(row["key"])
            if key in self.rows:
                raise ValueError("同一焦点窗口重复进入父代策略")
            self.rows[key] = row
        return plan


def _measured_rows(visible: dict, labels: dict, *, mix: str, root: int,
                   seat: int) -> tuple[list[dict], dict]:
    """模拟隐藏标签只在父代完全结束后与可见预测相连，绝不回传策略。"""

    counts = Counter()
    rows = []
    for key, source in sorted(visible.items()):
        counts["sampled_visible"] += 1
        if source.get("exclude"):
            counts[source["exclude"]] += 1
            continue
        if key not in labels:
            raise ValueError("可见动作窗口缺模拟完整世界标签")
        true_hand, true_wall = labels[key]
        unknown, model_wall, H, W = (source[name] for name in
                                     ("unknown", "model_wall", "H", "W"))
        if (sum(true_hand) != H or sum(true_wall) != W
                or any(true_hand[index] + true_wall[index] != unknown[index]
                       for index in range(34))):
            counts["partition_mismatch"] += 1
            continue
        baseline_wall = tuple(value * W / (H + W) for value in unknown)
        tile_base = sum((unknown[index] - baseline_wall[index] - true_hand[index])**2
                        for index in range(34))
        tile_model = sum((unknown[index] - model_wall[index] - true_hand[index])**2
                         for index in range(34))
        row = {"key": list(key), "mix": mix, "root_index": root,
               "focal_seat": seat, "position": source["position"],
               "tile_baseline_sse": tile_base, "tile_model_sse": tile_model,
               "tile_sse_difference": tile_model - tile_base}
        pair = source["pair"]
        if pair is not None:
            a, b = pair["parent_useful_indices"], pair["alternative_useful_indices"]
            value = lambda xs: sum(xs[index] for index in b) - sum(xs[index] for index in a)
            actual = value(true_wall)
            base = value(baseline_wall)
            model = value(model_wall)
            row["pair"] = {"parent_action": pair["parent_action"],
                           "alternative_action": pair["alternative_action"],
                           "public_difference": pair["public_difference"],
                           "parent_score_gap": pair["parent_score_gap"],
                           "actual_difference": actual,
                           "baseline_difference": base,
                           "model_difference": model,
                           "baseline_squared_error": (base-actual)**2,
                           "model_squared_error": (model-actual)**2,
                           "squared_error_difference": (model-actual)**2-(base-actual)**2}
            counts["comparable_pair"] += 1
            if source["position"] in (4, 7) and pair["public_difference"] == 0:
                counts["primary_pair"] += 1
        rows.append(row)
        counts["measured"] += 1
    return rows, dict(sorted(counts.items()))


def run_unit(unit: tuple[str, int, int]) -> dict:
    """单进程运行一阶段两桌；研究旁路只在本进程暂时安装。"""

    mix, root, seat = unit
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=SEED)
    focal_by_game = {plan.match_id: plan.seats().index(panel.natural.FOCAL_PARTICIPANT)
                     for plan in plans}
    labels = {}
    visible = {}
    original = panel.accounted.HandAccountingEngine

    class DiagnosticEngine(original):
        """只在 simulation 内部提取完整世界标签，驱动帧原样返回。"""

        def frame(self, world):
            frame = super().frame(world)
            for decision in frame.decisions:
                if (decision.window_key.phase.value != "draw"
                        or decision.window_key.seat != focal_by_game.get(decision.window_key.game_id)):
                    continue
                key = window_id(decision.window_key)
                if key not in labels:
                    labels[key] = hidden_partition_counts(world, focal_seat=key[-1])
            return frame

    def factory(clock):
        return PlanTap(panel.paired.policy_factory("r18_v2")(clock), visible)

    panel.accounted.HandAccountingEngine = DiagnosticEngine
    try:
        stage = panel.accounted.run_accounted_stage(
            plans=plans, candidate_policy_factory=factory,
            opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
            versions_block=panel.natural.stage.contract_versions_block(contract),
            step_limit=int(contract["stop"]["step_limit"]),
            value_limits=panel.paired.LIMITS)
    finally:
        panel.accounted.HandAccountingEngine = original
    panel.verify_unit({"mix": mix, "root_index": root, "focal_seat": seat,
                       "arm": "r18_v2", "stage": stage},
                      unit=(mix, root, seat, "r18_v2", SEED),
                      tables_per_stage=int(contract["group"]["tables_per_group"]))
    rows, counts = _measured_rows(visible, labels, mix=mix, root=root, seat=seat)
    return {"schema": "g83-hm-occupancy-transfer-unit/1", "mix": mix,
            "root_index": root, "focal_seat": seat, "panel_seed": SEED,
            "tables": [{"table_id": table["table_id"],
                        "match_status": table["match_status"],
                        "scores_by_seat": table["scores_by_seat"],
                        "hand_account": table["hand_account"]}
                       for table in stage["tables"]],
            "focal_stage_score": stage["focal_stage_score"],
            "window_counts": counts, "rows": rows}


def _summary(rows: list[dict], *, field: str, seed: int) -> dict:
    """先按池×根求均值，再固定种子做 20,000 次根级重采样。"""

    if not rows:
        return {"windows": 0, "roots": 0}
    by_root = defaultdict(list)
    for row in rows:
        by_root[row["root_index"]].append(row[field])
    roots = sorted(by_root)
    means = [sum(by_root[root])/len(by_root[root]) for root in roots]
    point = sum(means)/len(means)
    rng = random.Random(seed)
    bootstrap = sorted(sum(means[rng.randrange(len(means))] for _ in means)/len(means)
                       for _ in range(20_000))
    return {"windows": len(rows), "roots": len(roots),
            "root_equal_mean_difference": point,
            "root_bootstrap_95": [bootstrap[500], bootstrap[19499]],
            "negative_roots": sum(value < 0 for value in means),
            "root_means": {str(root): means[index] for index, root in enumerate(roots)}}


def aggregate(units: list[dict], manifest_hash: str) -> dict:
    """预登记主切片与逐码／位置次切片，保持池别。"""

    rows = [row for unit in units for row in unit["rows"]]
    result = {"schema": "g83-hm-occupancy-transfer-result/1",
              "manifest_sha256": manifest_hash,
              "complete_tables": sum(len(unit["tables"]) for unit in units),
              "window_counts": dict(sum((Counter(unit["window_counts"]) for unit in units), Counter())),
              "by_mix": {}}
    for mix in panel.MIXES:
        group = [row for row in rows if row["mix"] == mix]
        per_position = {
            str(pos): _summary([row for row in group if row["position"] == pos],
                               field="tile_sse_difference", seed=SEED+pos)
            for pos in POSITIONS}
        primary = [row["pair"] | {"root_index": row["root_index"]}
                   for row in group if "pair" in row and row["position"] in (4, 7)
                   and row["pair"]["public_difference"] == 0]
        p = _summary(primary, field="squared_error_difference", seed=SEED+10)
        nonzero = [row for row in primary if row["actual_difference"] != 0]
        p["nonzero_true_differences"] = len(nonzero)
        p["model_direction_correct"] = sum(
            (1 if row["model_difference"] > 1e-9 else
             -1 if row["model_difference"] < -1e-9 else 0)
            == (1 if row["actual_difference"] > 0 else -1)
            for row in nonzero)
        p["baseline_direction_correct"] = sum(
            (1 if row["baseline_difference"] > 1e-9 else
             -1 if row["baseline_difference"] < -1e-9 else 0)
            == (1 if row["actual_difference"] > 0 else -1)
            for row in nonzero)
        result["by_mix"][mix] = {
            "tile_all": _summary(group, field="tile_sse_difference", seed=SEED),
            "tile_by_position": per_position, "primary_action_pair": p,
            "all_comparable_pairs": _summary(
                [row["pair"] | {"root_index": row["root_index"]}
                 for row in group if "pair" in row],
                field="squared_error_difference", seed=SEED+11)}
    result["preregistered_transfer_supported"] = all(
        (entry["primary_action_pair"]["windows"] >= 100
         and entry["primary_action_pair"]["roots"] >= 6
         and entry["primary_action_pair"]["root_bootstrap_95"][1] < 0
         and entry["tile_all"]["root_bootstrap_95"][1] < 0)
        for entry in result["by_mix"].values())
    return result


def manifest() -> dict:
    """绑定未见根、模型、父代、规则和诊断实现，先于世界标签落盘。"""

    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    model = json.loads((_project_file(_PROJECT_ROOT, HERE / "evidence/g79b-corrected-occupancy-transfer-20260928/result.json"))
                       .read_text(encoding="utf-8"))["model"]["coefficients"]
    names = ("honor", "terminal", "edge", "unknown_minus_two", "opponent_same_river",
             "own_same_river", "opponent_neighbor_river", "opponent_same_suit_melds")
    if tuple(model[name] for name in names) != posterior.COEFFICIENTS:
        raise ValueError("G83 内嵌的 G79B 系数与冻结结果不一致")
    paths = (PREREG, _project_file(_PROJECT_ROOT, HERE / "g83_hm_occupancy_transfer.py"),
             _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/simulation/_research_hidden_labels.py"),
             _project_file(_PROJECT_ROOT, HERE / "g81_posterior_wall_policy.py"),
             _project_file(_PROJECT_ROOT, HERE / "evidence/g79b-corrected-occupancy-transfer-20260928/result.json"),
             panel.paired.CONTRACT)
    return {"schema": "g83-hm-occupancy-transfer-manifest/1",
            "panel_seed": SEED, "roots_per_mix": len(ROOTS),
            "mixes": list(panel.MIXES), "seats": list(panel.SEATS),
            "tables_per_stage": int(contract["group"]["tables_per_group"]),
            "planned_complete_tables": 192,
            "rules_source_hash": panel.natural.compute_rules_hash(ROOT),
            "source_sha256": {str(path.relative_to(ROOT)): digest(path) for path in paths},
            "boundary": "仅测量父代可见预测对模拟隐藏标签的误差；不改策略、不评候选净分。"}


def main() -> None:
    """证据文件一旦产生不可覆盖；已完成阶段只可按身份复用。"""

    frozen = manifest()
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    panel._write_new(manifest_path, frozen)
    units = [(mix, root, seat) for mix in panel.MIXES for root in ROOTS
             for seat in panel.SEATS]
    data = []
    pending = []
    for mix, root, seat in units:
        path = _project_file(_PROJECT_ROOT, OUT / "units" / f"{mix}-r{root:04d}-s{seat}.json")
        if path.exists():
            row = json.loads(path.read_text(encoding="utf-8"))
            if (row.get("mix"), row.get("root_index"), row.get("focal_seat"),
                row.get("panel_seed")) != (mix, root, seat, SEED):
                raise ValueError("现有阶段身份不符")
            data.append(row)
        else:
            pending.append((mix, root, seat))
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as workers:
            futures = {workers.submit(run_unit, unit): unit for unit in pending}
            for index, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                unit = futures[future]
                row = future.result()
                path = _project_file(_PROJECT_ROOT, OUT / "units" / f"{unit[0]}-r{unit[1]:04d}-s{unit[2]}.json")
                panel._write_new(path, row)
                data.append(row)
                if index % 8 == 0 or index == len(pending):
                    print(json.dumps({"completed_units": index,
                                      "total_units": len(pending)}), flush=True)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise FileExistsError("已有 G83 汇总结果，拒绝覆盖")
    result = aggregate(data, digest(manifest_path))
    panel._write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"complete_tables": result["complete_tables"],
                      "by_mix": {mix: {"tile": v["tile_all"],
                                       "primary": v["primary_action_pair"]}
                                 for mix, v in result["by_mix"].items()},
                      "transfer_supported": result["preregistered_transfer_supported"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
