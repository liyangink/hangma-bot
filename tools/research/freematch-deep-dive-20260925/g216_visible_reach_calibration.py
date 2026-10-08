#!/usr/bin/env python3
"""G216：新根父代完整桌中，记录普通弃牌后下一次本人行动能否先于结算到达。"""

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

import g13_accounted_panel as accounted
import g14_accounted_paired_panel as panel
import g210_post_claim_guarded_familiar_policy as parent


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G216-VISIBLE-REACH-CALIBRATION-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g216-visible-reach-calibration-20260929')
SEED = 20261229216
ROOTS = tuple(range(1, 5))
MIXES = ("H", "M")
SEATS = tuple(range(4))
EVENTS = ("next_own_draw", "own_claim", "own_win", "other_win", "draw")


def digest(path: Path) -> str:
    """内容摘要锁定预登记、合同、规则与执行器。"""
    return sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: Any) -> None:
    """原子写一次证据；不覆盖已完成阶段。"""
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def stage_path(mix: str, root: int, seat: int) -> Path:
    """对手池、独立牌山根和起始座位的唯一阶段文件。"""
    return _project_file(_PROJECT_ROOT, OUT / "stages" / f"{mix}-r{root:04d}-s{seat}.json")


class CapturingPolicy:
    """只读记录父代所见合法候选及其原样选择。"""

    def __init__(self, policy: Any, sink: list[dict]) -> None:
        self.policy = policy
        self.sink = sink
        self.policy_id = getattr(policy, "policy_id", type(policy).__name__)
        self.max_operations = getattr(policy, "max_operations", None)

    async def choose(self, request: Any, budget: Any) -> Any:
        """消费规则事实，不自行计算杭麻合法动作或有效牌。"""
        plan = await self.policy.choose(request, budget)
        action = None if not plan.candidates else plan.candidates[0].action_key
        candidates = {item.action_key: item for item in request.rules.legal_candidates}
        if action is None or action not in candidates:
            raise ValueError("父代未给当前规则合法动作")
        observation = request.observation
        selected = candidates[action]
        facts = selected.facts
        useful = None if facts is None or facts.standard_useful_tiles is None else [
            {"code": item.code, "remaining_estimate": item.remaining_estimate}
            for item in facts.standard_useful_tiles]
        self.sink.append({
            "order": len(self.sink),
            "decision_id": request.decision_id,
            "game_id": observation.game_id,
            "round_no": observation.round_no,
            "trigger_seq": request.trigger_seq,
            "phase": request.window_key.phase.value,
            "seat": observation.seat,
            "chosen_action": action,
            "drawn_tile": None if observation.drawn_tile is None
                          else observation.drawn_tile.code,
            "gang_draw": observation.gang_draw,
            "remaining_tile_count": observation.remaining_tile_count,
            "white_before": sum(tile.code == observation.rule_state.wealth_god.code
                                for tile in observation.my_hand),
            "meld_count": len(observation.melds[observation.seat]),
            "standard_shanten_after": None if facts is None
                                      else facts.standard_shanten_after,
            "standard_useful_tiles": useful,
            "baotou_after": None if facts is None else facts.baotou_after,
            "rules_completeness": request.rules.completeness.value,
        })
        return plan


def _terminal(hand: dict, seat: int) -> str:
    """用同桌同局权威结算唯一标注本座胡、他家胡或流局。"""
    if hand["is_draw"]:
        return "draw"
    if hand["winner_seat"] == seat:
        return "own_win"
    return "other_win"


def first_successor(later_decisions: list[dict], hand: dict, seat: int) -> str:
    """按到达顺序选首次后继；摸牌窗口到达先于窗口内选择。"""
    for later in later_decisions:
        key = later["chosen_action"]
        if later["phase"] == "draw":
            return "next_own_draw"
        if key == "hu":
            return "own_win"
        if key.startswith(("chi:", "peng:", "gang:")):
            return "own_claim"
    return _terminal(hand, seat)


def annotate(stage: dict, captured: list[dict]) -> list[dict]:
    """仅在完整对账桌上为每次普通弃牌给出互斥的最先后继事件。"""
    tables = {table["table_id"]: table for table in stage["tables"]}
    by_hand: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for record in captured:
        table_id = record["game_id"].removeprefix("sitin-stage:")
        if table_id not in tables:
            raise ValueError("可见决策没有对应完整桌")
        by_hand[(table_id, record["round_no"])].append(record)
    labeled = []
    for table_id, table in tables.items():
        if table["match_status"] != "complete":
            raise ValueError("校准阶段有未完成桌")
        focal = table["hand_account"]["focal_seat"]
        if table["stage_situation"]["participant_ids_by_seat"][focal] != "focal":
            raise ValueError("换座后的本座身份不同")
        if any(table["result"]["runtime_counts"].get(key, 0) != 0
               for key in ("timeouts", "illegal_choices", "fallbacks")):
            raise ValueError("父代桌有时限、非法或保底回退")
        hands = {hand["round_no"]: hand for hand in table["hand_records"]}
        if len(hands) != 8:
            raise ValueError("缺八个完整单局结算")
        for round_no, hand in hands.items():
            timeline = sorted(by_hand.pop((table_id, round_no), []),
                              key=lambda row: row["order"])
            if any(row["seat"] != focal for row in timeline):
                raise ValueError("决策记录混入他座")
            for index, current in enumerate(timeline):
                if (current["phase"] != "draw"
                        or not current["chosen_action"].startswith("discard:")):
                    continue
                if (type(current["standard_shanten_after"]) is not int
                        or current["standard_useful_tiles"] is None):
                    raise ValueError("正常摸打缺普通型向听或进张规则事实")
                event = first_successor(timeline[index + 1:], hand, focal)
                if event not in EVENTS:
                    raise ValueError("后继事件不互斥或未知")
                useful = current["standard_useful_tiles"]
                if any(type(item["remaining_estimate"]) is not int
                       or item["remaining_estimate"] < 0 for item in useful):
                    raise ValueError("公开有效牌容量不合法")
                labeled.append({
                    "table_id": table_id,
                    "round_no": round_no,
                    "decision_id": current["decision_id"],
                    "trigger_seq": current["trigger_seq"],
                    "seat": focal,
                    "chosen_action": current["chosen_action"],
                    "remaining_tile_count": current["remaining_tile_count"],
                    "gang_draw": current["gang_draw"],
                    "white_before": current["white_before"],
                    "meld_count": current["meld_count"],
                    "standard_shanten_after": current["standard_shanten_after"],
                    "standard_useful_type_count": sum(
                        item["remaining_estimate"] > 0 for item in useful),
                    "standard_useful_public_capacity": sum(
                        item["remaining_estimate"] for item in useful),
                    "baotou_after": current["baotou_after"],
                    "first_successor": event,
                    "hand_terminal": _terminal(hand, focal),
                })
    if by_hand:
        raise ValueError("存在无法绑定逐局结算的可见决策")
    if len({row["decision_id"] for row in labeled}) != len(labeled):
        raise ValueError("同一正常摸打窗口重复计数")
    return labeled


def run_unit(unit: tuple[str, int, int]) -> dict:
    """每个 H/M×根×换位座次在独立进程执行完整 R18 v2 阶段。"""
    mix, root, seat = unit
    contract = json.loads(panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=seat, panel_seed=SEED)
    captured: list[dict] = []

    def factory(monotonic: Any) -> CapturingPolicy:
        return CapturingPolicy(parent.parent_factory(monotonic), captured)

    stage = accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=factory,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=panel.paired.LIMITS)
    if stage["status"] != "complete" or len(stage["tables"]) != 2:
        raise ValueError("G216 阶段未完成两桌")
    labels = annotate(stage, captured)
    return {
        "schema": "g216-visible-reach-stage/1",
        "mix": mix, "root_index": root, "start_seat": seat,
        "stage": stage,
        "captured_decisions": len(captured),
        "normal_discard_labels": labels,
    }


def manifest() -> dict:
    """在打开新根结果前固定输入、运行规模和父代装配。"""
    contract = panel.paired.CONTRACT
    return {
        "schema": "g216-visible-reach-manifest/1",
        "panel_seed": SEED,
        "mixes": list(MIXES), "roots": list(ROOTS), "start_seats": list(SEATS),
        "tables_per_stage": 2,
        "planned_complete_tables": 64,
        "rules_source_hash": panel.natural.compute_rules_hash(ROOT),
        "input_sha256": {
            "prereg": digest(PREREG),
            "script": digest(Path(__file__)),
            "contract": digest(contract),
            "parent_source": digest(_project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py")),
            "accounted_runner": digest(_project_file(_PROJECT_ROOT, HERE / "g13_accounted_panel.py")),
        },
        "statistical_unit": "H/M×牌山根；四座及每阶段两桌相关",
        "boundary": "父代观察性可达性先导，不能估计备选动作因果收益或代替候选完整桌门。",
    }


def _wall_bin(value: int | None) -> str:
    """按预登记固定可见牌墙余量分层，未知值保持 unknown。"""
    if value is None:
        return "unknown"
    for upper in (32, 48, 64, 80, 96):
        if value <= upper:
            return f"<= {upper}"
    return "> 96"


def summarize(rows: list[dict]) -> dict:
    """只描述相关窗口的首后继，不把比例写成动作因果概率。"""
    by_mix = {}
    for mix in MIXES:
        scope = [row for row in rows if row["mix"] == mix]
        by_mix[mix] = {
            "normal_discard_windows": len(scope),
            "roots": len({row["root_index"] for row in scope}),
            "first_successor": dict(sorted(Counter(
                row["first_successor"] for row in scope).items())),
            "by_wall_bin": {bucket: dict(sorted(Counter(
                row["first_successor"] for row in scope
                if _wall_bin(row["remaining_tile_count"]) == bucket).items()))
                for bucket in ("<= 32", "<= 48", "<= 64", "<= 80", "<= 96", "> 96", "unknown")},
            "by_standard_shanten": {str(shanten): dict(sorted(Counter(
                row["first_successor"] for row in scope
                if row["standard_shanten_after"] == shanten).items()))
                for shanten in sorted({row["standard_shanten_after"] for row in scope})},
        }
    return by_mix


def main() -> None:
    """可续跑固定新根；完整阶段齐备后才生成汇总。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-new-units", type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers 必须在 1..4")
    frozen = manifest()
    manifest_path = _project_file(_PROJECT_ROOT, OUT / "manifest.json")
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != frozen:
            raise ValueError("G216 已冻结清单与当前输入不符")
    else:
        write_new(manifest_path, frozen)
    units = [(mix, root, seat) for mix in MIXES for root in ROOTS for seat in SEATS]
    pending = [unit for unit in units if not stage_path(*unit).exists()]
    if args.max_new_units > 0:
        pending = pending[:args.max_new_units]
    if pending:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(run_unit, unit): unit for unit in pending}
            for completed, future in enumerate(concurrent.futures.as_completed(futures), 1):
                unit = futures[future]
                result = future.result()
                if (result["mix"], result["root_index"], result["start_seat"]) != unit:
                    raise ValueError("并行阶段身份错配")
                write_new(stage_path(*unit), result)
                if completed % 4 == 0 or completed == len(pending):
                    print(json.dumps({"new_stages": completed,
                                      "planned_new_stages": len(pending)}), flush=True)
    if any(not stage_path(*unit).exists() for unit in units):
        print(json.dumps({"status": "in_progress"}), flush=True)
        return
    all_rows = []
    stage_hashes = {}
    for unit in units:
        path = stage_path(*unit)
        result = json.loads(path.read_text(encoding="utf-8"))
        if (result["mix"], result["root_index"], result["start_seat"]) != unit:
            raise ValueError("已存阶段身份不符")
        if result["stage"]["status"] != "complete" or len(result["stage"]["tables"]) != 2:
            raise ValueError("已存阶段未完成两桌")
        stage_hashes[path.name] = digest(path)
        for row in result["normal_discard_labels"]:
            all_rows.append({"mix": unit[0], "root_index": unit[1],
                             "start_seat": unit[2], **row})
    if len(stage_hashes) * 2 != frozen["planned_complete_tables"]:
        raise ValueError("完整桌总数不等于预登记")
    write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "g216-visible-reach-result/1",
        "manifest_sha256": digest(manifest_path),
        "stage_sha256": stage_hashes,
        "complete_stages": len(units),
        "complete_tables": len(units) * 2,
        "normal_discard_windows": len(all_rows),
        "by_mix": summarize(all_rows),
        "rows": all_rows,
        "boundary": frozen["boundary"],
    })
    print(json.dumps({"complete_tables": len(units) * 2,
                      "normal_discard_windows": len(all_rows),
                      "by_mix": summarize(all_rows)}, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
