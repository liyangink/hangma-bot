#!/usr/bin/env python3
"""G223：新根父代实际合法行动链上的三次本人摸牌与自然成面图谱。"""

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
import concurrent.futures
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import g14_accounted_paired_panel as panel
import g210_post_claim_guarded_familiar_policy as parent
import g40_official_natural_gap_reach as natural_gap
from hangma_bot.hangma.engine import _build_context


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G223-VISIBLE-MULTI-ACTION-ROUTE-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g223-visible-multi-action-route-20260929')
SEED = 20261229223
MIXES = ("H", "M")
ROOTS = tuple(range(1, 9))
SEATS = tuple(range(4))
STATUS_KEYS = ("illegal_choices", "timeouts", "fallbacks")


def digest(path: Path) -> str:
    """绑定预登记、规则、合同和研究执行器原始字节。"""
    return sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    """原子写入且拒绝不同内容覆盖既存证据。"""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise FileExistsError(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)


def stage_path(mix: str, root: int, seat: int) -> Path:
    """每个池×牌山根×起始座位固定唯一阶段。"""
    return _project_file(_PROJECT_ROOT, OUT / "stages" / f"{mix}-r{root:04d}-s{seat}.json")


def _width(entries: Any) -> tuple[int, int] | None:
    """从生产规则逐码公开容量计算码数和容量；未知不补零。"""
    if entries is None:
        return None
    counts = [item.remaining_estimate for item in entries]
    if any(type(value) is not int or value < 0 for value in counts):
        return None
    return sum(value > 0 for value in counts), sum(counts)


def _shape(request: Any, action: str, legal: dict[str, Any]) -> dict | None:
    """只用当前玩家手牌和生产普通型求解器算弃后自然牌形。"""
    if not action.startswith("discard:") or action not in legal:
        return None
    fact = legal[action].facts
    if fact is None or type(fact.standard_shanten_after) is not int:
        return None
    observation = request.observation
    held = Counter(tile.code for tile in _build_context(observation).full_hand())
    code = action.split(":", 1)[1]
    if held[code] <= 0:
        raise ValueError("父代弃牌不在本人完整暗手")
    held[code] -= 1
    if held[code] == 0:
        del held[code]
    melds = len(observation.melds[observation.seat])
    standard = natural_gap.standard(held, melds)
    if standard != fact.standard_shanten_after:
        raise ValueError("G223 自然牌形求解与生产普通型向听不一致")
    width = _width(fact.standard_useful_tiles)
    return {
        "standard_shanten_after": standard,
        "seven_pairs_shanten_after": fact.seven_pairs_shanten_after,
        "natural_need_after": natural_gap.gap(held, melds),
        "white_after": held[observation.rule_state.wealth_god.code],
        "baotou_after": fact.baotou_after,
        "standard_width": width,
        "standard_useful_tiles": None if fact.standard_useful_tiles is None else [
            {"code": item.code, "public_capacity": item.remaining_estimate}
            for item in fact.standard_useful_tiles],
    }


class TracePolicy:
    """研究包装器只观察父代实际首选；不重排动作或修改规则事实。"""

    def __init__(self, baseline: Any, sink: list[dict]) -> None:
        self.baseline = baseline
        self.sink = sink
        self.policy_id = baseline.policy_id
        self.max_operations = getattr(baseline, "max_operations", None)
        self.seen_roots: set[tuple[str, int, int, int]] = set()

    async def choose(self, request: Any, budget: Any) -> Any:
        """父代先产出合法保底，再只读记录行动前牌形和选择。"""
        plan = await self.baseline.choose(request, budget)
        if not plan.candidates:
            raise ValueError("G223 父代无保底动作")
        action = plan.candidates[0].action_key
        legal = {item.action_key: item for item in request.rules.legal_candidates}
        if action not in legal:
            raise ValueError("G223 父代首选不在生产合法集合")
        observation = request.observation
        is_normal_draw = (request.window_key.phase.value == "draw"
                          and observation.drawn_tile is not None
                          and observation.gang_draw is not True)
        shape = _shape(request, action, legal)
        probe_root = False
        options: list[dict] = []
        if (is_normal_draw and shape is not None
                and shape["standard_shanten_after"] in (1, 2, 3)
                and type(observation.remaining_tile_count) is int
                and observation.remaining_tile_count > 32 and "hu" not in legal):
            white_bucket = min(shape["white_after"], 2)
            key = (observation.game_id, observation.round_no,
                   white_bucket, shape["standard_shanten_after"])
            if key not in self.seen_roots:
                probe_root = True
                self.seen_roots.add(key)
                ranked = {item.action_key: item for item in plan.candidates}
                parent_score = plan.candidates[0].total_score
                if len(ranked) != len(plan.candidates):
                    raise ValueError("G223 父代排名动作重复")
                for choice in request.rules.legal_candidates:
                    alt_action = choice.action_key
                    if not alt_action.startswith("discard:") or alt_action not in ranked:
                        continue
                    alternative = _shape(request, alt_action, legal)
                    if (alternative is None
                            or alternative["standard_shanten_after"]
                               != shape["standard_shanten_after"]
                            or alternative["white_after"] != shape["white_after"]):
                        continue
                    options.append({
                        "action": alt_action,
                        "parent_score_gap": parent_score - ranked[alt_action].total_score,
                        "standard_shanten_after": alternative["standard_shanten_after"],
                        "seven_pairs_shanten_after": alternative["seven_pairs_shanten_after"],
                        "natural_need_after": alternative["natural_need_after"],
                        "white_after": alternative["white_after"],
                        "baotou_after": alternative["baotou_after"],
                        "standard_width": alternative["standard_width"],
                    })
                if action not in {item["action"] for item in options}:
                    raise ValueError("G223 行动前同层备选未包含父代")
        self.sink.append({
            "order": len(self.sink), "decision_id": request.decision_id,
            "game_id": observation.game_id, "round_no": observation.round_no,
            "trigger_seq": request.trigger_seq, "seat": observation.seat,
            "phase": request.window_key.phase.value,
            "drawn_tile": None if observation.drawn_tile is None
                          else observation.drawn_tile.code,
            "gang_draw": observation.gang_draw,
            "is_normal_draw": is_normal_draw, "chosen_action": action,
            "hu_available": "hu" in legal,
            "remaining_tile_count": observation.remaining_tile_count,
            "meld_count": len(observation.melds[observation.seat]),
            "shape_after": shape,
            "probe_root": probe_root, "same_layer_options": options,
        })
        return plan


def _terminal(hand: dict, seat: int) -> str:
    """按权威逐局结算给本座胡、他家胡或流局互斥标签。"""
    if hand["is_draw"]:
        return "draw"
    if hand["winner_seat"] == seat:
        return "plain_self" if hand["fan"] == 1 else "special_self"
    return "other_win"


def annotate(stage: dict, captured: list[dict]) -> list[dict]:
    """对每个事前根窗沿父代实际路径读至多三个后续正常摸牌决策。"""
    tables = {table["table_id"]: table for table in stage["tables"]}
    by_hand: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in captured:
        table_id = row["game_id"].removeprefix("sitin-stage:")
        if table_id not in tables:
            raise ValueError("G223 决策无法绑定完整桌")
        by_hand[(table_id, row["round_no"])].append(row)
    routes = []
    for table_id, table in tables.items():
        if table["match_status"] != "complete":
            raise ValueError("G223 不完整桌不可生成路线")
        seat = table["hand_account"]["focal_seat"]
        if table["stage_situation"]["participant_ids_by_seat"][seat] != "focal":
            raise ValueError("G223 换座后的本座身份不同")
        if any(table["result"]["runtime_counts"].get(key, 0) != 0
               for key in STATUS_KEYS):
            raise ValueError("G223 父代表存在非法、超时或保底回退")
        hands = {hand["round_no"]: hand for hand in table["hand_records"]}
        if len(hands) != 8:
            raise ValueError("G223 完整桌缺八局结算")
        for round_no, hand in hands.items():
            timeline = sorted(by_hand.pop((table_id, round_no), []),
                              key=lambda item: item["order"])
            if any(row["seat"] != seat for row in timeline):
                raise ValueError("G223 可见链混入他座")
            for index, root in enumerate(timeline):
                if not root["probe_root"]:
                    continue
                root_shape = root["shape_after"]
                later = timeline[index + 1:]
                later_normal = [row for row in later if row["is_normal_draw"]]
                first_three = later_normal[:3]
                route = []
                for depth, row in enumerate(first_three, 1):
                    shape = row["shape_after"]
                    route.append({
                        "depth": depth, "decision_id": row["decision_id"],
                        "trigger_seq": row["trigger_seq"],
                        "chosen_action": row["chosen_action"],
                        "hu_available": row["hu_available"],
                        "shape_after": shape,
                        "natural_need_delta_vs_root": None if shape is None else
                            shape["natural_need_after"] - root_shape["natural_need_after"],
                        "white_delta_vs_root": None if shape is None else
                            shape["white_after"] - root_shape["white_after"],
                    })
                limit_order = (first_three[-1]["order"] if len(first_three) == 3
                               else float("inf"))
                claims = sum(row["chosen_action"].startswith(("chi:", "peng:", "gang:"))
                             for row in later if row["order"] <= limit_order)
                options = root["same_layer_options"]
                parent_option = next(item for item in options
                                     if item["action"] == root["chosen_action"])
                routes.append({
                    "table_id": table_id, "round_no": round_no,
                    "root_decision_id": root["decision_id"],
                    "root_trigger_seq": root["trigger_seq"],
                    "seat": seat, "root_action": root["chosen_action"],
                    "root_wall_remaining": root["remaining_tile_count"],
                    "root_shape": root_shape,
                    "white_bucket": min(root_shape["white_after"], 2),
                    "same_layer_options": options,
                    "same_layer_natural_better_count": sum(
                        item["natural_need_after"] < parent_option["natural_need_after"]
                        for item in options),
                    "later_normal_draw_decisions_reached": min(3, len(later_normal)),
                    "first_three_normal_draws": route,
                    "own_claims_before_third_or_terminal": claims,
                    "terminal": _terminal(hand, seat),
                    "terminal_fan": hand["fan"] if hand["winner_seat"] == seat else None,
                    "terminal_focal_delta": hand["score_delta"][seat],
                })
    if by_hand:
        raise ValueError("G223 留下无法绑定结算单局的决策记录")
    if len({row["root_decision_id"] for row in routes}) != len(routes):
        raise ValueError("G223 同一根决策重复记录")
    return routes


def run_unit(unit: tuple[str, int, int]) -> dict:
    """一进程只执行一个 H/M×根×座位阶段，并记录同一路径。"""
    mix, root, seat = unit
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=SEED)
    captured: list[dict] = []

    def factory(monotonic: Any) -> TracePolicy:
        return TracePolicy(parent.parent_factory(monotonic), captured)

    stage = panel.accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=factory,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=panel.paired.LIMITS)
    if stage["status"] != "complete" or len(stage["tables"]) != 2:
        raise ValueError("G223 父代阶段未完成两张完整桌")
    return {"schema": "g223-visible-multi-action-stage/1",
            "mix": mix, "root_index": root, "start_seat": seat,
            "stage": stage, "captured_decisions": captured,
            "probe_routes": annotate(stage, captured)}


def manifest() -> dict:
    """在读取任一新完整桌结果前冻结身份和事实来源。"""
    contract = panel.paired.CONTRACT
    return {
        "schema": "g223-visible-multi-action-manifest/1",
        "panel_seed": SEED, "mixes": list(MIXES), "roots": list(ROOTS),
        "start_seats": list(SEATS), "tables_per_stage": 2,
        "planned_complete_tables": len(MIXES) * len(ROOTS) * len(SEATS) * 2,
        "rules_source_hash": panel.natural.compute_rules_hash(ROOT),
        "input_sha256": {str(path.relative_to(ROOT)): digest(path) for path in (
            PREREG, Path(__file__), panel.paired.CONTRACT,
            _project_file(_PROJECT_ROOT, HERE / "g40_official_natural_gap_reach.py"),
            _project_file(_PROJECT_ROOT, HERE / "g13_accounted_panel.py"),
            _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py"))},
        "statistical_unit": "H/M×独立牌山根；根内四座与两桌相关",
        "boundary": "只读父代实际路径；公开未知容量不是实墙概率，未执行备选没有因果后继。",
    }


def summarize(rows: list[dict]) -> dict:
    """根窗相关且可能同局重叠，只报告描述性到达与牌形分布。"""
    result = {}
    for mix in MIXES:
        group = [row for row in rows if row["mix"] == mix]
        strata = {}
        for white in (0, 1, 2):
            for shanten in (1, 2, 3):
                scope = [row for row in group if row["white_bucket"] == white
                         and row["root_shape"]["standard_shanten_after"] == shanten]
                strata[f"white{white}_standard{shanten}"] = {
                    "roots": len({row["root_index"] for row in scope}),
                    "windows": len(scope),
                    "has_better_natural_same_layer_option": sum(
                        row["same_layer_natural_better_count"] > 0 for row in scope),
                    "reach_next_1_2_3_normal_draw_decisions": [
                        sum(row["later_normal_draw_decisions_reached"] >= depth
                            for row in scope) for depth in (1, 2, 3)],
                    "terminal": dict(sorted(Counter(
                        row["terminal"] for row in scope).items())),
                    "natural_need_lower_at_reached_depth_1_2_3": [
                        sum(len(row["first_three_normal_draws"]) >= depth
                            and row["first_three_normal_draws"][depth - 1]
                                ["natural_need_delta_vs_root"] is not None
                            and row["first_three_normal_draws"][depth - 1]
                                ["natural_need_delta_vs_root"] < 0
                            for row in scope) for depth in (1, 2, 3)],
                    "white_retained_at_reached_depth_1_2_3": [
                        sum(len(row["first_three_normal_draws"]) >= depth
                            and row["first_three_normal_draws"][depth - 1]
                                ["white_delta_vs_root"] == 0
                            for row in scope) for depth in (1, 2, 3)],
                }
        result[mix] = {"windows": len(group), "roots": len({row["root_index"] for row in group}),
                       "strata": strata}
    return result


def main() -> None:
    """阶段可续跑；完整 128 桌齐备后才生成分层路线汇总。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-units", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers 必须在 1..4")
    frozen = manifest()
    write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), frozen)
    units = [(mix, root, seat) for mix in MIXES for root in ROOTS for seat in SEATS]
    pending = [unit for unit in units if not stage_path(*unit).exists()]
    if args.max_new_units > 0:
        pending = pending[:args.max_new_units]
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(run_unit, unit): unit for unit in pending}
            for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
                unit = futures[future]
                row = future.result()
                if (row["mix"], row["root_index"], row["start_seat"]) != unit:
                    raise ValueError("G223 阶段身份与调度不符")
                write_new(stage_path(*unit), row)
                if completed % 8 == 0 or completed == len(pending):
                    print(json.dumps({"new_stages": completed,
                                      "planned_new_stages": len(pending)}), flush=True)
    if any(not stage_path(*unit).exists() for unit in units):
        print(json.dumps({"status": "in_progress",
                          "stages_completed": sum(stage_path(*unit).exists()
                                                  for unit in units)}), flush=True)
        return
    all_rows = []
    stage_hashes = {}
    for unit in units:
        path = stage_path(*unit)
        data = json.loads(path.read_text(encoding="utf-8"))
        if (data["mix"], data["root_index"], data["start_seat"]) != unit:
            raise ValueError("G223 已存阶段身份不符")
        if data["stage"]["status"] != "complete" or len(data["stage"]["tables"]) != 2:
            raise ValueError("G223 已存阶段不完整")
        stage_hashes[path.name] = digest(path)
        for row in data["probe_routes"]:
            all_rows.append({"mix": unit[0], "root_index": unit[1],
                             "start_seat": unit[2], **row})
    result = {
        "schema": "g223-visible-multi-action-result/1",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "stage_sha256": stage_hashes,
        "complete_stages": len(units), "complete_tables": len(units) * 2,
        "probe_windows": len(all_rows), "by_mix": summarize(all_rows),
        "rows": all_rows, "boundary": frozen["boundary"],
    }
    write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"complete_tables": result["complete_tables"],
                      "probe_windows": result["probe_windows"],
                      "by_mix": result["by_mix"]}, ensure_ascii=False,
                     sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
