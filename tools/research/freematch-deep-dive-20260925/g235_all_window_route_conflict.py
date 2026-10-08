#!/usr/bin/env python3
"""G235：父代所有本人正常摸打的宽进张评分反转，只读同路径复算。"""

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
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

import g223_visible_multi_action_route as g223
import g232_base_width_inversion as g232


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G235-ALL-WINDOW-ROUTE-CONFLICT-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g235-all-window-route-conflict-20260929')
MIXES, ROOTS, SEATS = g223.MIXES, g223.ROOTS, g223.SEATS


def digest(path: Path) -> str:
    """绑定冻结来源和研究代码的原始字节。"""
    return sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    """原子写入结构证据；已存在的不同内容不得覆盖。"""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise FileExistsError(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(encoded, encoding="utf-8")
    temp.replace(path)


def stage_path(mix: str, root: int, seat: int) -> Path:
    """一个池、独立牌山根和起始座位对应唯一两桌阶段。"""
    return _project_file(_PROJECT_ROOT, OUT / "stages" / f"{mix}-r{root:04d}-s{seat}.json")


def _parts(entry: Any) -> dict[str, float] | None:
    """仅取生产评分的数值分项；不能把未知或布尔当作零。"""
    trace = entry.score_trace
    if not isinstance(trace, dict) or not isinstance(trace.get("detail"), dict):
        return None
    detail = trace["detail"]
    names = ("base_score", "wealth_part", "wealth_discard_part",
             "river_part", "style_part", "risk_units")
    if any(type(detail.get(name)) not in (int, float)
           or not math.isfinite(float(detail[name])) for name in names):
        return None
    if detail["risk_units"] < 0 or not math.isfinite(entry.total_score):
        return None
    values = {name: float(detail[name]) for name in names}
    values["risk_part"] = -6.0 * values["risk_units"]
    values["other"] = entry.total_score - sum(
        values[name] for name in names) - values["risk_part"]
    if not math.isfinite(values["other"]):
        return None
    return values


def _record(request: Any, plan: Any) -> dict | None:
    """只用该动作窗口可见观察、生产合法事实和父代评分核反转。"""
    observation = request.observation
    legal = {item.action_key: item for item in request.rules.legal_candidates}
    if (request.window_key.phase.value != "draw" or observation.drawn_tile is None
            or observation.gang_draw is True or "hu" in legal
            or not plan.candidates or request.rejected_attempts):
        return None
    parent_key = plan.candidates[0].action_key
    if (not parent_key.startswith("discard:") or parent_key == "discard:白"
            or parent_key not in legal):
        return None
    parent_fact = legal[parent_key].facts
    if (parent_fact is None or type(parent_fact.standard_shanten_after) is not int
            or parent_fact.standard_shanten_after not in (1, 2, 3)):
        return None
    parent_width = g232.width(parent_fact.standard_useful_tiles)
    parent_combined = g232.width(parent_fact.useful_tiles)
    parent_parts = _parts(plan.candidates[0])
    if parent_width is None:
        return None
    # 本人暗手只用于当前窗口的白板实持数，绝不读取模拟世界或未来事件。
    white = sum(tile.code == observation.rule_state.wealth_god.code
                for tile in g223._build_context(observation).full_hand())
    ranked = {entry.action_key: entry for entry in plan.candidates}
    if len(ranked) != len(plan.candidates) or len(legal) != len(request.rules.legal_candidates):
        raise ValueError("G235 合法动作或父代排序出现重复动作键")
    strict, guarded, inverted, unknown = 0, 0, [], 0
    for key, choice in legal.items():
        if (key == parent_key or not key.startswith("discard:")
                or key == "discard:白" or key not in ranked):
            continue
        facts = choice.facts
        if (facts is None or facts.standard_shanten_after != parent_fact.standard_shanten_after):
            continue
        width = g232.width(facts.standard_useful_tiles)
        if (width is None or width[0] <= parent_width[0]
                or width[1] <= parent_width[1]):
            continue
        strict += 1
        combined = g232.width(facts.useful_tiles)
        parts = _parts(ranked[key])
        if (parent_combined is None or combined is None
                or parent_parts is None or parts is None
                or type(parent_fact.shanten_after) is not int
                or type(facts.shanten_after) is not int
                or type(parent_fact.seven_pairs_shanten_after) is not int
                or type(facts.seven_pairs_shanten_after) is not int):
            unknown += 1
            continue
        protected = (facts.shanten_after <= parent_fact.shanten_after
                     and combined[1] >= parent_combined[1]
                     and facts.seven_pairs_shanten_after
                     <= parent_fact.seven_pairs_shanten_after
                     and parts["risk_units"] <= parent_parts["risk_units"] + 1e-8
                     and (parent_fact.baotou_after is not True
                          or facts.baotou_after is True))
        if not protected:
            continue
        guarded += 1
        delta = {name: parts[name] - parent_parts[name] for name in
                 ("base_score", "wealth_part", "wealth_discard_part",
                  "river_part", "style_part", "risk_part", "other")}
        total = ranked[key].total_score - plan.candidates[0].total_score
        if abs(sum(delta.values()) - total) > 1e-8:
            raise ValueError("G235 两动作父代评分分量不守恒")
        if (delta["base_score"] > 1e-8 and total <= 1e-8
                and total - delta["river_part"] - delta["style_part"] > 1e-8):
            inverted.append({
                "action": key, "standard_width": list(width),
                "width_gain": [width[0] - parent_width[0],
                               width[1] - parent_width[1]],
                "score_gap": round(-total, 8),
                "score_parts_delta": {name: round(value, 8)
                                      for name, value in delta.items()},
                "seven_pairs_shanten_after": facts.seven_pairs_shanten_after,
                "baotou_after": facts.baotou_after,
            })
    representative = min(inverted, key=lambda item: (
        -item["standard_width"][0], -item["standard_width"][1],
        item["score_gap"], item["action"])) if inverted else None
    return {
        "kind": "eligible", "strict": strict, "guarded": guarded,
        "unknown": unknown, "inversion": representative,
        "game_id": observation.game_id, "round_no": observation.round_no,
        "trigger_seq": request.trigger_seq, "decision_id": request.decision_id,
        "seat": observation.seat, "wall_remaining": observation.remaining_tile_count,
        "white_held": white,
        "standard_shanten_after": parent_fact.standard_shanten_after,
        "parent_action": parent_key, "parent_standard_width": list(parent_width),
        "parent_seven_pairs_shanten_after": parent_fact.seven_pairs_shanten_after,
        "parent_baotou_after": parent_fact.baotou_after,
        "inversion_count": len(inverted),
    }


class TracePolicy:
    """仅记录父代合法动作和每个本人摸打的行动前冲突，不修改计划。"""

    def __init__(self, baseline: Any, actions: list, windows: list) -> None:
        self.baseline, self.actions, self.windows = baseline, actions, windows
        self.policy_id = baseline.policy_id
        self.max_operations = getattr(baseline, "max_operations", None)

    async def choose(self, request: Any, budget: Any) -> Any:
        """先取得已经含合法保底的父代计划，再只读审计。"""
        plan = await self.baseline.choose(request, budget)
        if not plan.candidates:
            raise ValueError("G235 父代没有合法保底动作")
        key = plan.candidates[0].action_key
        if key not in {item.action_key for item in request.rules.legal_candidates}:
            raise ValueError("G235 父代首选不在生产合法动作中")
        self.actions.append((request.decision_id, key))
        row = _record(request, plan)
        if row is not None:
            self.windows.append(row)
        return plan


def run_unit(unit: tuple[str, int, int]) -> dict:
    """复跑一个固定阶段，并与 G223 全动作及完整桌结算核对。"""
    mix, root, seat = unit
    source_path = g223.stage_path(*unit)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    contract = json.loads(g223.panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = g223.panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=g223.SEED)
    actions, windows = [], []

    def factory(monotonic: Any) -> TracePolicy:
        return TracePolicy(g223.parent.parent_factory(monotonic), actions, windows)

    stage = g223.panel.accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=factory,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=g223.panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=g223.panel.paired.LIMITS)
    if stage["status"] != "complete" or len(stage["tables"]) != 2:
        raise ValueError("G235 父代阶段未完成两张完整桌")
    expected_actions = [(row["decision_id"], row["chosen_action"])
                        for row in source["captured_decisions"]]
    if actions != expected_actions:
        raise ValueError("G235 全部本人决策身份或父代动作与 G223 不同")
    for old, new in zip(source["stage"]["tables"], stage["tables"], strict=True):
        if (old["table_id"] != new["table_id"]
                or old["hand_records"] != new["hand_records"]
                or old["scores_by_seat"] != new["scores_by_seat"]
                or old["result"]["scores_after"] != new["result"]["scores_after"]):
            raise ValueError("G235 原父代八局或终分与 G223 不同")
    results = {}
    for table in stage["tables"]:
        results[table["table_id"]] = {
            hand["round_no"]: {
                "terminal": g223._terminal(hand, table["hand_account"]["focal_seat"]),
                "fan": hand["fan"],
                "focal_delta": hand["score_delta"][table["hand_account"]["focal_seat"]],
            } for hand in table["hand_records"]}
    for row in windows:
        if row["kind"] != "eligible":
            raise ValueError("G235 未知窗口种类")
        if row["inversion"] is not None:
            table_id = row["game_id"].removeprefix("sitin-stage:")
            row["terminal_diagnostic"] = results[table_id][row["round_no"]]
    return {
        "schema": "g235-all-window-route-conflict-stage/1",
        "mix": mix, "root_index": root, "start_seat": seat,
        "source_g223_stage_sha256": digest(source_path),
        "complete_tables_verified": 2,
        "decisions_verified": len(actions),
        "actions_sha256": sha256(json.dumps(actions, ensure_ascii=False).encode()).hexdigest(),
        "windows": windows,
    }


def manifest() -> dict:
    """在打开新增冲突计数前固定来源和规则身份。"""
    source = g223.OUT / "result.json"
    return {
        "schema": "g235-all-window-route-conflict-manifest/1",
        "panel_seed": g223.SEED, "mixes": list(MIXES),
        "roots": list(ROOTS), "start_seats": list(SEATS),
        "planned_complete_tables": len(MIXES) * len(ROOTS) * len(SEATS) * 2,
        "g223_result_sha256": digest(source),
        "input_sha256": {str(path.relative_to(ROOT)): digest(path) for path in (
            PLAN, Path(__file__), g223.panel.paired.CONTRACT,
            _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py"))},
        "boundary": "G223 已看牌山同路径全窗只读结构普查；后验结算不进入窗口触发，不能估计改弃收益。",
    }


def summarize(rows: list[dict]) -> dict:
    """窗口、整手与独立牌山根分别计数，重复状态不冒充独立样本。"""
    by_mix = {}
    for mix in MIXES:
        group = [row for row in rows if row["mix"] == mix]
        inversions = [row for row in group if row["inversion"] is not None]
        hands: dict[tuple, list[dict]] = defaultdict(list)
        for row in inversions:
            hands[(row["root_index"], row["game_id"], row["round_no"])].append(row)
        repeated = {key: sorted(value, key=lambda x: x["trigger_seq"])
                    for key, value in hands.items() if len(value) >= 2}
        by_mix[mix] = {
            "eligible_normal_draw_windows": len(group),
            "strict_wider_windows": sum(row["strict"] > 0 for row in group),
            "protected_wider_windows": sum(row["guarded"] > 0 for row in group),
            "inversion_windows": len(inversions),
            "inversion_hands": len(hands),
            "inversion_roots": len({row["root_index"] for row in inversions}),
            "repeated_inversion_hands": len(repeated),
            "repeated_inversion_roots": len({key[0] for key in repeated}),
            "repeat_window_gaps": [
                later["trigger_seq"] - earlier["trigger_seq"]
                for values in repeated.values()
                for earlier, later in zip(values, values[1:])],
            "wall_gt32": {"eligible": sum(row.get("wall_remaining", 0) > 32
                                           for row in group),
                          "inversion": sum(row["wall_remaining"] > 32
                                           for row in inversions)},
            "by_white_and_shanten": {
                f"white{white}_standard{shanten}": {
                    "eligible": sum(min(row.get("white_held", -1), 2) == white
                                    and row.get("standard_shanten_after") == shanten
                                    for row in group),
                    "inversion": sum(min(row["white_held"], 2) == white
                                     and row["standard_shanten_after"] == shanten
                                     for row in inversions),
                } for white in (0, 1, 2) for shanten in (1, 2, 3)},
        }
    return by_mix


def main() -> None:
    """阶段断点续跑；必须全部 128 桌核对后才公布整批结构判据。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-units", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers 必须在 1..4")
    write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest())
    units = [(mix, root, seat) for mix in MIXES for root in ROOTS for seat in SEATS]
    pending = [unit for unit in units if not stage_path(*unit).exists()]
    if args.max_new_units > 0:
        pending = pending[:args.max_new_units]
    if pending:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(run_unit, unit): unit for unit in pending}
            for count, future in enumerate(as_completed(futures), 1):
                unit = futures[future]
                result = future.result()
                if tuple(result[name] for name in ("mix", "root_index", "start_seat")) != unit:
                    raise ValueError("G235 阶段身份漂移")
                write_new(stage_path(*unit), result)
                if count % 8 == 0 or count == len(pending):
                    print(json.dumps({"new_stages": count,
                                      "planned_new_stages": len(pending)}), flush=True)
    if any(not stage_path(*unit).exists() for unit in units):
        print(json.dumps({"status": "in_progress", "stages_completed": sum(
            stage_path(*unit).exists() for unit in units)}), flush=True)
        return
    prior = json.loads((g223.OUT / "result.json").read_text(encoding="utf-8"))
    rows, hashes, decisions = [], {}, 0
    for unit in units:
        path = stage_path(*unit)
        value = json.loads(path.read_text(encoding="utf-8"))
        source_path = g223.stage_path(*unit)
        if (tuple(value[name] for name in ("mix", "root_index", "start_seat")) != unit
                or value["source_g223_stage_sha256"] != prior["stage_sha256"][source_path.name]
                or digest(source_path) != value["source_g223_stage_sha256"]
                or value["complete_tables_verified"] != 2):
            raise ValueError("G235 来源、阶段身份或桌数漂移")
        hashes[path.name] = digest(path)
        decisions += value["decisions_verified"]
        rows.extend({"mix": unit[0], "root_index": unit[1],
                     "start_seat": unit[2], **row}
                    for row in value["windows"])
    counts = summarize(rows)
    result = {
        "schema": "g235-all-window-route-conflict-result/1",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "stage_sha256": hashes, "complete_tables_verified": 128,
        "decisions_verified": decisions, "by_mix": counts,
        "stateful_inversion_gate_pass": all(
            counts[mix]["repeated_inversion_hands"] >= 8
            and counts[mix]["repeated_inversion_roots"] >= 3
            for mix in MIXES),
        "boundary": manifest()["boundary"],
    }
    write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"complete_tables_verified": 128,
                      "stateful_inversion_gate_pass": result["stateful_inversion_gate_pass"],
                      "by_mix": counts}, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
