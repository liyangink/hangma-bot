#!/usr/bin/env python3
"""G238：新 H/M 根父代全窗口 G237 影子建议，不改变任何动作。"""

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
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import g223_visible_multi_action_route as g223
import g237_numeric_inversion_policy as candidate
from hangma_bot.hangma.engine import _build_context


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G238-ALL-WINDOW-NUMERIC-EXPOSURE-PREREG-2026-09-29.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g238-all-window-numeric-exposure-20260929')
SEED = 20261229338
MIXES = ("H", "M")
ROOTS = tuple(range(1, 9))
SEATS = tuple(range(4))
STATUS_KEYS = ("illegal_choices", "timeouts", "fallbacks")


def digest(path: Path) -> str:
    """清单与逐阶段文件使用原始字节 SHA-256。"""
    return sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    """只允许相同结果续跑，拒绝覆盖不同证据。"""
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
    """一个池、根、起始座位唯一阶段。"""
    return _project_file(_PROJECT_ROOT, OUT / "stages" / f"{mix}-r{root:04d}-s{seat}.json")


class ShadowPolicy:
    """G237 只读建议；始终返回父代完整合法计划。"""

    def __init__(self, baseline: Any, sink: list[dict], counters: Counter) -> None:
        self.baseline, self.sink, self.counters = baseline, sink, counters
        self.policy_id = baseline.policy_id
        self.max_operations = getattr(baseline, "max_operations", None)
        self.normal_by_hand = Counter()

    async def choose(self, request: Any, budget: Any) -> Any:
        """只在父代已有保底后读取生产规则事实，绝不提交建议动作。"""
        plan = await self.baseline.choose(request, budget)
        if not plan.candidates:
            raise ValueError("G238 父代无合法保底")
        observation = request.observation
        is_normal = (request.window_key.phase.value == "draw"
                     and observation.drawn_tile is not None
                     and observation.gang_draw is not True)
        self.counters["all_decisions"] += 1
        hand_key = (observation.game_id, observation.round_no)
        if is_normal:
            self.counters["normal_draw_decisions"] += 1
            self.normal_by_hand[hand_key] += 1
        key, evidence = candidate.select(request, plan)
        self.counters["selector_" + evidence["reason"]] += 1
        if key is not None:
            if not is_normal or key == plan.candidates[0].action_key or key not in {
                    item.action_key for item in request.rules.legal_candidates}:
                raise ValueError("G238 影子建议不合法或未改变动作")
            held = _build_context(observation).full_hand()
            white = sum(tile.code == observation.rule_state.wealth_god.code
                        for tile in held)
            self.sink.append({
                "game_id": observation.game_id, "round_no": observation.round_no,
                "seat": observation.seat, "trigger_seq": request.trigger_seq,
                "decision_id": request.decision_id,
                "normal_draw_index_in_hand": self.normal_by_hand[hand_key],
                "parent_action": plan.candidates[0].action_key,
                "suggested_action": key,
                "white_held": white,
                "wall_remaining": observation.remaining_tile_count,
                "standard_shanten_after": evidence["parent_standard_shanten"],
                "parent_width": evidence["parent_standard_width"],
                "candidate_width": evidence["candidate_standard_width"],
                "score_gap": evidence["score_gap"],
            })
        return plan


def run_unit(unit: tuple[str, int, int]) -> dict:
    """同种子分别跑直接父代与影子父代，逐局结算完全一致才保存。"""
    mix, root, seat = unit
    contract = json.loads(g223.panel.paired.CONTRACT.read_text(encoding="utf-8"))

    def plans():
        return g223.panel.natural.build_seat_stage_plans(
            contract=contract, opponent=mix, root_index=root,
            focal_seat=seat, panel_seed=SEED)

    def stage(factory):
        return g223.panel.accounted.run_accounted_stage(
            plans=plans(), candidate_policy_factory=factory,
            opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
            versions_block=g223.panel.natural.stage.contract_versions_block(contract),
            step_limit=int(contract["stop"]["step_limit"]),
            value_limits=g223.panel.paired.LIMITS)

    direct = stage(candidate.research_parent_factory)
    sink: list[dict] = []
    counters = Counter()

    def shadow_factory(monotonic):
        return ShadowPolicy(candidate.research_parent_factory(monotonic), sink, counters)

    shadow = stage(shadow_factory)
    if (direct["status"] != "complete" or shadow["status"] != "complete"
            or len(direct["tables"]) != 2 or len(shadow["tables"]) != 2):
        raise ValueError("G238 双父代阶段不完整")
    table_hashes = {}
    for old, new in zip(direct["tables"], shadow["tables"], strict=True):
        if (old["table_id"] != new["table_id"]
                or old["match_status"] != new["match_status"]
                or old["hand_records"] != new["hand_records"]
                or old["scores_by_seat"] != new["scores_by_seat"]
                or old["result"]["runtime_counts"] != new["result"]["runtime_counts"]):
            raise ValueError("G238 影子干扰父代动作或结算")
        if any(new["result"]["runtime_counts"].get(name, 0) != 0
               for name in STATUS_KEYS):
            raise ValueError("G238 父代存在非法、超时或保底")
        table_hashes[new["table_id"]] = sha256(json.dumps(
            new["hand_records"], ensure_ascii=False,
            sort_keys=True).encode()).hexdigest()
    return {
        "schema": "g238-all-window-numeric-exposure-stage/1",
        "mix": mix, "root_index": root, "start_seat": seat,
        "table_hand_sha256": table_hashes,
        "complete_tables_verified": 2,
        "counters": dict(sorted(counters.items())),
        "suggestions": sink,
    }


def manifest() -> dict:
    """在运行新根前绑定身份与源码。"""
    return {
        "schema": "g238-all-window-numeric-exposure-manifest/1",
        "panel_seed": SEED, "mixes": list(MIXES), "roots": list(ROOTS),
        "start_seats": list(SEATS), "planned_complete_tables": 128,
        "rules_source_hash": g223.panel.natural.compute_rules_hash(ROOT),
        "input_sha256": {str(path.relative_to(ROOT)): digest(path) for path in (
            PLAN, Path(__file__), _project_file(_PROJECT_ROOT, HERE / "g237_numeric_inversion_policy.py"),
            g223.panel.paired.CONTRACT,
            _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v2.py"))},
        "boundary": "全新父代牌山只作影子行为覆盖；建议动作从未提交，结算不估计改弃收益。",
    }


def summarize(rows: list[dict]) -> dict:
    """按动作窗、手、桌和根分别计数，严格区分相关单位。"""
    out = {}
    for mix in MIXES:
        group = [row for row in rows if row["mix"] == mix]
        first_by_hand = {}
        for row in sorted(group, key=lambda item: (
                item["game_id"], item["round_no"], item["trigger_seq"])):
            first_by_hand.setdefault((row["game_id"], row["round_no"]), row)
        out[mix] = {
            "suggestions": len(group),
            "tables": len({row["game_id"] for row in group}),
            "hands": len(first_by_hand),
            "independent_roots": len({row["root_index"] for row in group}),
            "first_suggestion_by_hand": len(first_by_hand),
            "later_suggestions_same_hand": len(group) - len(first_by_hand),
            "normal_draw_index": dict(sorted(Counter(
                min(row["normal_draw_index_in_hand"], 6) for row in group
            ).items())),
            "white_held": dict(sorted(Counter(row["white_held"] for row in group).items())),
        }
    return out


def main() -> None:
    """64 阶段可断点续跑，全部完成后才裁定预登记材料门。"""
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
        with ProcessPoolExecutor(max_workers=args.workers) as workers:
            futures = {workers.submit(run_unit, unit): unit for unit in pending}
            for count, future in enumerate(as_completed(futures), 1):
                unit = futures[future]
                value = future.result()
                if tuple(value[name] for name in ("mix", "root_index", "start_seat")) != unit:
                    raise ValueError("G238 阶段身份漂移")
                write_new(stage_path(*unit), value)
                if count % 8 == 0 or count == len(pending):
                    print(json.dumps({"new_stages": count,
                                      "planned_new_stages": len(pending)}), flush=True)
    if any(not stage_path(*unit).exists() for unit in units):
        print(json.dumps({"status": "in_progress", "stages_complete": sum(
            stage_path(*unit).exists() for unit in units)}), flush=True)
        return
    rows, stage_hashes, totals = [], {}, Counter()
    for unit in units:
        path = stage_path(*unit)
        value = json.loads(path.read_text(encoding="utf-8"))
        if (tuple(value[name] for name in ("mix", "root_index", "start_seat")) != unit
                or value["complete_tables_verified"] != 2
                or len(value["table_hand_sha256"]) != 2):
            raise ValueError("G238 已存阶段不完整或身份漂移")
        stage_hashes[path.name] = digest(path)
        totals.update(value["counters"])
        rows.extend({"mix": unit[0], "root_index": unit[1],
                     "start_seat": unit[2], **row} for row in value["suggestions"])
    by_mix = summarize(rows)
    gate = all(by_mix[mix]["suggestions"] >= 20
               and by_mix[mix]["tables"] >= 15
               and by_mix[mix]["independent_roots"] >= 6 for mix in MIXES)
    result = {
        "schema": "g238-all-window-numeric-exposure-result/1",
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "stage_sha256": stage_hashes,
        "complete_tables_verified": 128,
        "shadow_parent_exact": True,
        "counters": dict(sorted(totals.items())),
        "by_mix": by_mix,
        "material_gate_pass": gate,
        "suggestions": rows,
        "boundary": manifest()["boundary"],
    }
    write_new(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"complete_tables_verified": 128,
                      "material_gate_pass": gate,
                      "by_mix": by_mix}, ensure_ascii=False,
                     sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
