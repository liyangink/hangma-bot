#!/usr/bin/env python3
"""G224：不改父代动作，复跑 G223 同种子并补齐备选进张逐码向量。"""

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

import argparse
from collections import Counter
import concurrent.futures
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import g223_visible_multi_action_route as g223
from hangma_bot.kernel.serialization import observation_to_json


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G224-G223-VECTOR-REPLAY-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g224-g223-vector-replay-20260929')
SOURCE = g223.OUT


def digest(path: Path) -> str:
    """绑定原始 G223 证据和本次复跑源码。"""
    return sha256(path.read_bytes()).hexdigest()


def _json_clone(value: Any) -> Any:
    """与 G223 阶段文件使用相同 JSON 语义比较 tuple/list 等容器。"""
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


class CompleteTracePolicy(g223.TracePolicy):
    """仅为 G223 已锁的根窗补玩家可见观察和逐码备选事实。"""

    def __init__(self, baseline: Any, sink: list[dict], roots: list[dict]) -> None:
        super().__init__(baseline, sink)
        self.roots = roots

    async def choose(self, request: Any, budget: Any) -> Any:
        """父代和 G223 包装器先完成选择，补证不影响排序。"""
        plan = await super().choose(request, budget)
        record = self.sink[-1]
        if not record["probe_root"]:
            return plan
        legal = {item.action_key: item for item in request.rules.legal_candidates}
        for option in record["same_layer_options"]:
            shape = g223._shape(request, option["action"], legal)
            if shape is None or shape["standard_width"] != option["standard_width"]:
                raise ValueError("G224 逐码事实与 G223 宽度不一致")
            vector = shape["standard_useful_tiles"]
            if vector is None:
                raise ValueError("G224 同层备选逐码事实未知")
            if (sum(row["public_capacity"] > 0 for row in vector),
                    sum(row["public_capacity"] for row in vector)) != tuple(option["standard_width"]):
                raise ValueError("G224 逐码向量与码数、容量不守恒")
            option["standard_useful_tiles"] = vector
        self.roots.append({
            "root_decision_id": record["decision_id"],
            "observation": observation_to_json(request.observation),
        })
        return plan


def _remove_new_fields(row: dict) -> dict:
    """删除唯一新增的备选向量后，应与 G223 原始决策逐项相同。"""
    value = dict(row)
    value["same_layer_options"] = [
        {key: item for key, item in option.items() if key != "standard_useful_tiles"}
        for option in row["same_layer_options"]]
    return value


def run_unit(unit: tuple[str, int, int]) -> dict:
    """每阶段同牌山复跑并在保存补证前验证行为、结算、路线恒等。"""
    mix, root, seat = unit
    source_path = g223.stage_path(*unit)
    old = json.loads(source_path.read_text(encoding="utf-8"))
    contract = json.loads(g223.panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = g223.panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=g223.SEED)
    captured: list[dict] = []
    root_observations: list[dict] = []

    def factory(monotonic: Any) -> CompleteTracePolicy:
        return CompleteTracePolicy(g223.parent.parent_factory(monotonic),
                                   captured, root_observations)

    stage = g223.panel.accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=factory,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=g223.panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=g223.panel.paired.LIMITS)
    if stage["status"] != "complete" or len(stage["tables"]) != 2:
        raise ValueError("G224 复跑阶段不完整")
    for current, former in zip(_json_clone(stage["tables"]), old["stage"]["tables"]):
        if any(current[key] != former[key] for key in
               ("table_id", "seed", "hand_records", "scores_by_seat",
                "policy_execution", "hand_account")):
            raise ValueError("G224 同源桌身份、结算或执行审计漂移")
    normalized_stage = _json_clone(stage)
    if any(normalized_stage[key] != old["stage"][key] for key in
           ("focal_stage_score", "stage_totals_by_participant", "execution_review")):
        raise ValueError("G224 阶段积分或执行审计漂移")
    if [_remove_new_fields(row) for row in _json_clone(captured)] != old["captured_decisions"]:
        raise ValueError("G224 父代每次动作或 G223 根选样漂移")
    route = g223.annotate(stage, captured)
    if len(route) != len(old["probe_routes"]):
        raise ValueError("G224 根路线数量漂移")
    if [_remove_new_fields(row) for row in _json_clone(route)] != old["probe_routes"]:
        raise ValueError("G224 删除新增向量后的三次行动路线漂移")
    by_observation = {row["root_decision_id"]: row["observation"]
                      for row in root_observations}
    if len(by_observation) != len(route):
        raise ValueError("G224 根观察与三次行动路线未一一对应")
    roots = [{"root_decision_id": row["root_decision_id"],
              "observation": by_observation[row["root_decision_id"]],
              "table_id": row["table_id"], "round_no": row["round_no"],
              "root_action": row["root_action"], "root_shape": row["root_shape"],
              "white_bucket": row["white_bucket"],
              "same_layer_options": row["same_layer_options"],
              "later_normal_draw_decisions_reached": row[
                  "later_normal_draw_decisions_reached"]}
             for row in route]
    return {"schema": "g224-g223-vector-replay-stage/1",
            "mix": mix, "root_index": root, "start_seat": seat,
            "source_g223_stage_sha256": digest(source_path),
            "complete_tables_verified": 2,
            "captured_decisions_verified": len(captured),
            "root_routes_verified": len(route),
            "roots": roots}


def manifest() -> dict:
    """在打开复跑结果前锁原始 G223 和新增补证身份。"""
    return {
        "schema": "g224-g223-vector-replay-manifest/1",
        "panel_seed": g223.SEED, "mixes": list(g223.MIXES),
        "roots": list(g223.ROOTS), "seats": list(g223.SEATS),
        "planned_complete_tables": 128,
        "source_sha256": {str(path.relative_to(ROOT)): digest(path) for path in (
            PREREG, Path(__file__), SOURCE / "manifest.json", SOURCE / "result.json",
            _project_file(_PROJECT_ROOT, HERE / "g223_visible_multi_action_route.py"),
            _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py"))},
        "boundary": "同种子原样复跑只补玩家可见根观察和合法备选逐码容量，不是新独立收益样本。",
    }


def stage_path(mix: str, root: int, seat: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "stages" / f"{mix}-r{root:04d}-s{seat}.json")


def _vector(option: dict) -> tuple[tuple[str, int], ...]:
    """仅保留正公开容量的牌码；零容量不算进张来源。"""
    return tuple(sorted((item["code"], item["public_capacity"])
                        for item in option["standard_useful_tiles"]
                        if item["public_capacity"] > 0))


def _concentration(vector: tuple[tuple[str, int], ...]) -> float | None:
    """公开容量的 Herfindahl 比例；仅作分布描述，不作收益分。"""
    total = sum(value for _, value in vector)
    if total == 0:
        return None
    return sum((value / total) ** 2 for _, value in vector)


def summarize(rows: list[dict]) -> dict:
    """按池和牌形格计逐码差异，根窗仍为相关观察。"""
    by_mix = {}
    for mix in g223.MIXES:
        group = [row for row in rows if row["mix"] == mix]
        strata = {}
        for white in (0, 1, 2):
            for shanten in (1, 2, 3):
                scope = [row for row in group if row["white_bucket"] == white
                         and row["root_shape"]["standard_shanten_after"] == shanten]
                counts = Counter()
                for row in scope:
                    options = row["same_layer_options"]
                    parent = next(item for item in options
                                  if item["action"] == row["root_action"])
                    vector = _vector(parent)
                    parent_width = tuple(parent["standard_width"])
                    parent_concentration = _concentration(vector)
                    counts["windows"] += 1
                    counts["has_strict_wider"] += any(
                        tuple(item["standard_width"])[0] > parent_width[0]
                        and tuple(item["standard_width"])[1] > parent_width[1]
                        for item in options)
                    equal_width_different = [item for item in options
                        if item["action"] != parent["action"]
                        and tuple(item["standard_width"]) == parent_width
                        and _vector(item) != vector]
                    counts["has_equal_width_different_vector"] += bool(equal_width_different)
                    counts["has_equal_width_lower_concentration"] += (
                        parent_concentration is not None and any(
                            _concentration(_vector(item)) is not None
                            and _concentration(_vector(item)) < parent_concentration - 1e-12
                            for item in equal_width_different))
                    counts["reached_third_after_equal_width_vector_conflict"] += (
                        bool(equal_width_different)
                        and row["later_normal_draw_decisions_reached"] >= 3)
                strata[f"white{white}_standard{shanten}"] = {
                    "independent_roots": len({row["root_index"] for row in scope}),
                    **dict(sorted(counts.items()))}
        by_mix[mix] = {"roots": len({row["root_index"] for row in group}),
                       "windows": len(group), "strata": strata}
    return by_mix


def main() -> None:
    """可续跑固定 64 阶段；只在逐项恒等时保存补证。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-units", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers 必须在 1..4")
    g223.write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest())
    units = [(mix, root, seat) for mix in g223.MIXES
             for root in g223.ROOTS for seat in g223.SEATS]
    pending = [unit for unit in units if not stage_path(*unit).exists()]
    if args.max_new_units > 0:
        pending = pending[:args.max_new_units]
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(run_unit, unit): unit for unit in pending}
            for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
                unit = futures[future]
                value = future.result()
                if (value["mix"], value["root_index"], value["start_seat"]) != unit:
                    raise ValueError("G224 完整复跑阶段身份不符")
                g223.write_new(stage_path(*unit), value)
                if completed % 8 == 0 or completed == len(pending):
                    print(json.dumps({"new_stages": completed,
                                      "planned_new_stages": len(pending)}), flush=True)
    if any(not stage_path(*unit).exists() for unit in units):
        print(json.dumps({"status": "in_progress",
                          "stages_completed": sum(stage_path(*unit).exists()
                                                  for unit in units)}), flush=True)
        return
    rows = []
    stage_hashes = {}
    for unit in units:
        path = stage_path(*unit)
        value = json.loads(path.read_text(encoding="utf-8"))
        if (value["mix"], value["root_index"], value["start_seat"]) != unit:
            raise ValueError("G224 已存阶段身份不符")
        if value["complete_tables_verified"] != 2:
            raise ValueError("G224 补证未核两张完整桌")
        stage_hashes[path.name] = digest(path)
        for row in value["roots"]:
            rows.append({"mix": unit[0], "root_index": unit[1],
                         "start_seat": unit[2], **row})
    g223_source = json.loads((SOURCE / "result.json").read_text(encoding="utf-8"))
    if len(rows) != g223_source["probe_windows"]:
        raise ValueError("G224 补齐逐码向量的根窗数与 G223 不同")
    result = {
        "schema": "g224-g223-vector-replay-result/1",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "stage_sha256": stage_hashes,
        "complete_stages": len(units), "complete_tables_verified": len(units) * 2,
        "probe_windows": len(rows), "by_mix": summarize(rows),
        "boundary": manifest()["boundary"],
    }
    g223.write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"complete_tables_verified": result["complete_tables_verified"],
                      "probe_windows": result["probe_windows"],
                      "by_mix": result["by_mix"]}, ensure_ascii=False,
                     sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
