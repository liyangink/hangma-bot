#!/usr/bin/env python3
"""G241：在全新父代根记录三次本人摸牌前的互斥竞争事件。"""

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
from pathlib import Path
import random
from statistics import mean
from typing import Any

import g13_accounted_panel as accounted
import g14_accounted_paired_panel as panel
import g210_post_claim_guarded_familiar_policy as parent
import g216_visible_reach_calibration as g216
from hangma_bot.hangma.engine import _build_context


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G241-MULTI-ACTION-COMPETING-REACH-PREREG-2026-09-29.md')
AMENDMENT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G241-NO-DRAW-GANG-MEASUREMENT-AMENDMENT-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g241-multi-action-competing-reach-amended-20260929')
SEED = 20261229241
ROOTS = tuple(range(1, 17))
MIXES = ("H", "M")
SEATS = tuple(range(4))
BOOTSTRAP_SEED = 20261229242


def digest(path: Path) -> str:
    """以字节摘要绑定预登记、规则和逐阶段证据。"""
    return sha256(path.read_bytes()).hexdigest()


class CapturingPolicy(g216.CapturingPolicy):
    """只增记当前可见规则事实；父代首选计划逐字返回。"""

    async def choose(self, request: Any, budget: Any) -> Any:
        """保存行动前状态与选中动作事实，供赛后合法路径分析。"""
        plan = await super().choose(request, budget)
        row = self.sink[-1]
        observation = request.observation
        selected = next(item for item in request.rules.legal_candidates
                        if item.action_key == row["chosen_action"])
        facts = selected.facts
        seven = None if facts is None or facts.seven_pairs_useful_tiles is None else [
            {"code": item.code, "remaining_estimate": item.remaining_estimate}
            for item in facts.seven_pairs_useful_tiles]
        white_code = observation.rule_state.wealth_god.code
        actual_white = sum(tile.code == white_code
                           for tile in _build_context(observation).full_hand())
        row.update({
            "g216_white_before": row["white_before"],
            "white_before": actual_white,
            "seven_pairs_shanten_after": None if facts is None
                                          else facts.seven_pairs_shanten_after,
            "seven_pairs_useful_tiles": seven,
            "baotou_before": observation.rule_state.baotou,
            "chain_count_before": observation.rule_state.chain_count,
            "chain_piao_before": observation.chain_piao,
            "catch_play_before": observation.rule_state.catch_play,
            "catch_play_owner_seat_before":
                observation.rule_state.catch_play_owner_seat,
        })
        return plan


def _table_id(decision: dict) -> str:
    """官方式模拟 game_id 前缀回连对应完整桌。"""
    return decision["game_id"].removeprefix("sitin-stage:")


def _future_events(timeline: list[dict], start: int, terminal: str) -> dict:
    """只沿已执行父代路径，至第三次本人摸牌或本局终止。"""
    events = []
    draws = 0
    claims = 0
    followups = 0
    no_draw_gangs = 0
    pending_claim = False
    for later in timeline[start + 1:]:
        key = later["chosen_action"]
        if later["phase"] == "draw":
            if later["drawn_tile"] is None:
                # 官方式接口吃碰后的无摸跟打仍使用 phase=draw；仅凭 phase
                # 会把未摸牌的窗口误计成一次本人再摸。无摸窗口可直接加杠，
                # 然后先补摸而不是紧接弃牌。
                if not pending_claim:
                    raise ValueError("G241 无摸 draw 窗口缺吃碰前驱")
                pending_claim = False
                if key.startswith("discard:"):
                    followups += 1
                    events.append({"kind": "no_draw_followup_discard",
                                   "decision_id": later["decision_id"],
                                   "trigger_seq": later["trigger_seq"],
                                   "chosen_action": key,
                                   "standard_shanten_after": later[
                                       "standard_shanten_after"],
                                   "baotou_after": later["baotou_after"]})
                elif key.startswith("gang:"):
                    claims += 1
                    no_draw_gangs += 1
                    events.append({"kind": "own_claim",
                                   "decision_id": later["decision_id"],
                                   "trigger_seq": later["trigger_seq"],
                                   "chosen_action": key,
                                   "on_no_draw_followup": True,
                                   "baotou_before": later["baotou_before"],
                                   "chain_count_before": later["chain_count_before"]})
                else:
                    raise ValueError("G241 无摸 draw 窗口非弃牌或杠")
            else:
                if pending_claim:
                    raise ValueError("G241 鸣后未见无摸跟打便出现本人摸牌")
                draws += 1
                events.append({
                    "kind": "own_draw",
                    "decision_id": later["decision_id"],
                    "trigger_seq": later["trigger_seq"],
                    "gang_draw": later["gang_draw"],
                    "chosen_action": key,
                    "white_before": later["white_before"],
                    "standard_shanten_after": later["standard_shanten_after"],
                    "seven_pairs_shanten_after": later["seven_pairs_shanten_after"],
                    "baotou_before": later["baotou_before"],
                    "chain_count_before": later["chain_count_before"],
                    "chain_piao_before": later["chain_piao_before"],
                    "remaining_tile_count": later["remaining_tile_count"],
                })
                if key == "hu" or draws == 3:
                    break
        elif key.startswith(("chi:", "peng:", "gang:")):
            if pending_claim:
                raise ValueError("G241 连续鸣牌之间缺无摸跟打")
            claims += 1
            # 吃碰后无摸跟打；明杠先补摸，不能强求立即弃牌。
            pending_claim = key.startswith(("chi:", "peng:"))
            events.append({"kind": "own_claim", "decision_id": later["decision_id"],
                           "trigger_seq": later["trigger_seq"],
                           "chosen_action": key,
                           "baotou_before": later["baotou_before"],
                           "chain_count_before": later["chain_count_before"]})
        elif key.startswith("discard:"):
            if not pending_claim:
                raise ValueError("G241 非摸牌弃牌前没有已记录鸣牌")
            followups += 1
            pending_claim = False
            events.append({"kind": "no_draw_followup_discard",
                           "decision_id": later["decision_id"],
                           "trigger_seq": later["trigger_seq"],
                           "chosen_action": key,
                           "standard_shanten_after": later[
                               "standard_shanten_after"],
                           "baotou_after": later["baotou_after"]})
        elif key == "hu":
            raise ValueError("G241 非本人摸牌窗口出现胡动作")
    if pending_claim:
        raise ValueError("G241 本局结束前鸣牌缺无摸跟打")
    if draws < 3:
        events.append({"kind": terminal})
    if any(a["trigger_seq"] >= b["trigger_seq"]
           for a, b in zip(events, events[1:])
           if "trigger_seq" in a and "trigger_seq" in b):
        raise ValueError("G241 后继官方事件序号非严格递增")
    return {
        "events": events,
        "future_own_draws_reached": draws,
        "third_own_draw_reached": draws == 3,
        "own_claims_before_horizon": claims,
        "no_draw_followups_before_horizon": followups,
        "no_draw_gangs_before_horizon": no_draw_gangs,
        "terminal_within_horizon": (draws < 3 or
                                    (bool(events) and events[-1]["kind"] == "own_draw"
                                     and events[-1]["chosen_action"] == "hu")),
    }


def annotate(stage: dict, captured: list[dict]) -> list[dict]:
    """复用 G216 首后继权威分类，再增记三摸前同手事件顺序。"""
    base = g216.annotate(stage, captured)
    by_decision = {row["decision_id"]: row for row in base}
    by_hand: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for row in captured:
        by_hand[(_table_id(row), row["round_no"])].append(row)
    tables = {table["table_id"]: table for table in stage["tables"]}
    output = []
    for (table_id, round_no), timeline in by_hand.items():
        table = tables.get(table_id)
        if table is None:
            raise ValueError("G241 决策找不到对应完整桌")
        hand = next((item for item in table["hand_records"]
                     if item["round_no"] == round_no), None)
        if hand is None:
            raise ValueError("G241 决策找不到对应完整单局")
        focal = table["hand_account"]["focal_seat"]
        terminal = g216._terminal(hand, focal)
        timeline.sort(key=lambda item: item["order"])
        for index, current in enumerate(timeline):
            row = by_decision.get(current["decision_id"])
            if (row is None or current["gang_draw"]
                    or current["drawn_tile"] is None):
                continue
            future = _future_events(timeline, index, terminal)
            first = next((event["kind"] for event in future["events"]
                          if event["kind"] != "no_draw_followup_discard"), None)
            expected = {"own_draw": "next_own_draw", "own_claim": "own_claim",
                        "own_win": "own_win", "other_win": "other_win",
                        "draw": "draw"}.get(first)
            if row["first_successor"] != expected:
                raise ValueError("G241 三摸轨迹首事件与 G216 首后继不一致")
            output.append({**row,
                           "seven_pairs_shanten_after": current[
                               "seven_pairs_shanten_after"],
                           "baotou_before": current["baotou_before"],
                           "chain_count_before": current["chain_count_before"],
                           "chain_piao_before": current["chain_piao_before"],
                           "catch_play_before": current["catch_play_before"],
                           "catch_play_owner_seat_before": current[
                               "catch_play_owner_seat_before"],
                           "hand_fan": hand["fan"], **future})
    if len({row["decision_id"] for row in output}) != len(output):
        raise ValueError("G241 根窗口重复")
    return output


def run_unit(unit: tuple[str, int, int]) -> dict:
    """每阶段观察臂与未包装父代同牌山完整复跑并逐桌对账。"""
    mix, root, seat = unit
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=SEED)
    kwargs = dict(
        plans=plans,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=panel.paired.LIMITS)
    captured: list[dict] = []

    def factory(monotonic: Any) -> CapturingPolicy:
        return CapturingPolicy(parent.parent_factory(monotonic), captured)

    observed = accounted.run_accounted_stage(
        candidate_policy_factory=factory, **kwargs)
    plain = accounted.run_accounted_stage(
        candidate_policy_factory=parent.parent_factory, **kwargs)
    if (observed["status"] != "complete" or plain["status"] != "complete"
            or len(observed["tables"]) != 2 or len(plain["tables"]) != 2
            or observed["focal_stage_score"] != plain["focal_stage_score"]):
        raise ValueError("G241 阶段未完整或记录器改变父代积分")
    for left, right in zip(observed["tables"], plain["tables"]):
        for key in ("table_id", "seed", "scores_by_seat", "policy_execution",
                    "hand_account", "hand_records"):
            if left[key] != right[key]:
                raise ValueError("G241 记录器改变父代 " + key)
        if left["result"]["runtime_counts"] != right["result"]["runtime_counts"]:
            raise ValueError("G241 记录器改变运行计数")
        if any(left["result"]["runtime_counts"].get(key, 0)
               for key in ("timeouts", "illegal_choices", "fallbacks")):
            raise ValueError("G241 父代出现超时、非法或保底")
    labels = annotate(observed, captured)
    return {"schema": "g241-multi-action-competing-reach-stage/1",
            "mix": mix, "root_index": root, "start_seat": seat,
            "stage": observed, "captured_decisions": len(captured),
            "g216_white_count_differences": sum(
                row["white_before"] != row["g216_white_before"]
                for row in captured),
            "normal_discard_labels": labels,
            "plain_parent_parity_tables": 2}


def manifest() -> dict:
    """固定全新根、父代／规则、脚本与训练/留根身份。"""
    return {
        "schema": "g241-multi-action-competing-reach-manifest/1",
        "panel_seed": SEED, "mixes": list(MIXES), "roots": list(ROOTS),
        "seats": list(SEATS), "tables_per_stage": 2,
        "planned_parent_tables": 256,
        "train_roots": list(range(1, 13)),
        "holdout_roots": list(range(13, 17)),
        "rules_source_hash": panel.natural.compute_rules_hash(ROOT),
        "input_sha256": {str(path.relative_to(ROOT)): digest(path) for path in (
            PLAN, AMENDMENT, Path(__file__), Path(g216.__file__), panel.paired.CONTRACT,
            _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py"))},
        "boundary": "父代已执行路径的三摸前竞争事件；不是备选弃牌因果概率或收益。",
    }


def _stage_path(unit: tuple[str, int, int]) -> Path:
    """H/M×根×起始座位唯一阶段路径。"""
    mix, root, seat = unit
    return _project_file(_PROJECT_ROOT, OUT / "stages" / f"{mix}-r{root:04d}-s{seat}.json")


def _write_new(path: Path, value: dict) -> None:
    """原子落盘；已有证据只允许逐字相同。"""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise FileExistsError("G241 已有证据不同：" + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(encoded, encoding="utf-8")
    tmp.replace(path)


def _interval(values: list[float], rng: random.Random) -> list[float]:
    """只重采样独立牌山根，相关窗口留在根内。"""
    samples = sorted(mean(rng.choice(values) for _ in values)
                     for _ in range(20_000))
    return [samples[500], samples[19_499]]


def summarize(rows: list[dict]) -> dict:
    """描述根级三摸到达与先鸣；不把父代经验频率冒充动作因果率。"""
    rng = random.Random(BOOTSTRAP_SEED)
    result = {}
    for mix in MIXES:
        group = [row for row in rows if row["mix"] == mix]
        by_root = defaultdict(list)
        for row in group:
            by_root[row["root_index"]].append(row)
        if set(by_root) != set(ROOTS):
            raise ValueError("G241 独立牌山根没有完整覆盖")
        rates = [mean(row["third_own_draw_reached"] for row in by_root[root])
                 for root in ROOTS]
        result[mix] = {
            "independent_roots": len(by_root),
            "normal_discard_windows": len(group),
            "first_successor": dict(sorted(Counter(
                row["first_successor"] for row in group).items())),
            "third_own_draw_reached": sum(row["third_own_draw_reached"] for row in group),
            "own_claim_before_horizon": sum(
                row["own_claims_before_horizon"] > 0 for row in group),
            "no_draw_followup_events": sum(
                row["no_draw_followups_before_horizon"] for row in group),
            "no_draw_gang_events": sum(
                row["no_draw_gangs_before_horizon"] for row in group),
            "terminal_before_third": dict(sorted(Counter(
                row["hand_terminal"] for row in group
                if not row["third_own_draw_reached"]).items())),
            "root_equal_third_draw_rate": mean(rates),
            "root_bootstrap_95_percentile": _interval(rates, rng),
            "train_root_windows": sum(row["root_index"] <= 12 for row in group),
            "holdout_root_windows": sum(row["root_index"] >= 13 for row in group),
        }
    return result


def main() -> None:
    """可断点续跑；所有阶段完整且逐项对账后才汇总。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-units", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers 必须在 1..4")
    frozen = manifest()
    _write_new(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), frozen)
    units = [(mix, root, seat) for mix in MIXES for root in ROOTS for seat in SEATS]
    pending = [unit for unit in units if not _stage_path(unit).exists()]
    if args.max_new_units > 0:
        pending = pending[:args.max_new_units]
    if pending:
        with ProcessPoolExecutor(max_workers=args.workers) as workers:
            futures = {workers.submit(run_unit, unit): unit for unit in pending}
            for count, future in enumerate(as_completed(futures), 1):
                unit = futures[future]
                try:
                    row = future.result()
                except Exception as exc:
                    raise RuntimeError(f"G241 stage failed: {unit}") from exc
                if (row["mix"], row["root_index"], row["start_seat"]) != unit:
                    raise ValueError("G241 阶段身份漂移")
                _write_new(_stage_path(unit), row)
                if count % 8 == 0 or count == len(pending):
                    print(json.dumps({"new_stages": count,
                                      "planned_new_stages": len(pending)}), flush=True)
    if any(not _stage_path(unit).exists() for unit in units):
        print(json.dumps({"status": "in_progress",
                          "stages_complete": sum(_stage_path(unit).exists()
                                                 for unit in units)}), flush=True)
        return
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise FileExistsError("G241 汇总已存在，拒绝覆盖")
    rows = []
    stage_hashes = {}
    for unit in units:
        path = _stage_path(unit)
        row = json.loads(path.read_text(encoding="utf-8"))
        if (row["mix"], row["root_index"], row["start_seat"]) != unit:
            raise ValueError("G241 已存阶段身份不同")
        if row["stage"]["status"] != "complete" or len(row["stage"]["tables"]) != 2:
            raise ValueError("G241 已存阶段不完整")
        if row["plain_parent_parity_tables"] != 2:
            raise ValueError("G241 未包装父代行为恒等缺失")
        stage_hashes[path.name] = digest(path)
        rows.extend({"mix": unit[0], "root_index": unit[1],
                     "start_seat": unit[2], **item}
                    for item in row["normal_discard_labels"])
    if len(stage_hashes) * 2 != frozen["planned_parent_tables"]:
        raise ValueError("G241 桌数不等于预登记")
    result = {
        "schema": "g241-multi-action-competing-reach-result/1",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "stage_sha256": stage_hashes,
        "complete_stages": len(units),
        "complete_parent_tables": len(units) * 2,
        "plain_parent_parity_tables": len(units) * 2,
        "normal_discard_windows": len(rows),
        "g216_white_count_differences": sum(
            json.loads(_stage_path(unit).read_text(encoding="utf-8"))[
                "g216_white_count_differences"] for unit in units),
        "by_mix": summarize(rows),
        "boundary": frozen["boundary"],
    }
    _write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"complete_parent_tables": result["complete_parent_tables"],
                      "normal_discard_windows": result["normal_discard_windows"],
                      "by_mix": result["by_mix"]},
                     ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
