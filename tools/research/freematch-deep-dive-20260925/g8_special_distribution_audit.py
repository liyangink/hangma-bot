#!/usr/bin/env python3
"""结果盲核对官方自由赛与 H/M 对手池的双白胡番/时序分布。"""

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
import json
from pathlib import Path

import g8_two_white_next_draw_census as census
import g8_two_white_natural_probe as probe
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927')


def _bucket(wall: int) -> str:
    if wall <= 24:
        return "wall_0_24"
    if wall <= 40:
        return "wall_25_40"
    if wall <= 56:
        return "wall_41_56"
    return "wall_57_plus"


def _add(counts: Counter, request: dict) -> None:
    """同一口径投影父代会收胡的双白摸牌窗。"""

    observation = request["observation"]
    hand, meld_count = census._complete_hand(observation)
    if hand.count("白") != 2:
        return
    wall = observation.get("remaining_tile_count")
    if type(wall) is not int:
        raise ValueError("墙余量缺失")
    hu = next(item for item in request["rules"]["legal_candidates"]
              if item["action_key"] == "hu")
    fan = hu["value_facts"]["immediate_settlement"]["fan"]
    baotou = (observation.get("rule_state") or {}).get("baotou") is True
    counts["two_white_parent_hu"] += 1
    counts["fan_" + str(fan)] += 1
    counts[_bucket(wall)] += 1
    counts[f"fan_{fan}|{_bucket(wall)}"] += 1
    counts[f"fan_{fan}|meld_{meld_count}"] += 1
    counts[f"fan_{fan}|baotou_{baotou}"] += 1
    counts[f"fan_{fan}|round_{observation['round_no']}"] += 1


def _official() -> dict:
    frozen = json.loads((_project_file(_PROJECT_ROOT, EVIDENCE / "frozen_rooms.json")).read_text(encoding="utf-8"))
    counts = Counter()
    by_room = defaultdict(Counter)
    for room in frozen["rooms"]:
        audit = _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"])
        path = audit / "participants" / census.PARTICIPANT / "decisions.jsonl"
        if path.stat().st_size != room["decision_bytes"]:
            raise ValueError("官方冻结审计文件大小漂移")
        for _, request in census._iter_parent_hu(audit):
            if (request.get("observation") or {}).get("phase") != "draw":
                continue
            _add(counts, request)
            _add(by_room[room["room_id"]], request)
    return {"full_tables": sum(room["games"] for room in frozen["rooms"]),
            "rooms": len(frozen["rooms"]), "counts": dict(sorted(counts.items())),
            "room_counts": {room: dict(sorted(row.items())) for room, row in by_room.items()}}


def _natural() -> dict:
    sources = json.loads((_project_file(_PROJECT_ROOT, EVIDENCE / "natural-probe-corrected/sources.json")).read_text(encoding="utf-8"))["sources"]
    contract = json.loads(probe.p85.CONTRACT.read_text(encoding="utf-8"))
    parent = probe.p85.parent_source()
    counts = Counter()
    by_mix = defaultdict(Counter)
    by_root = defaultdict(Counter)
    for index, source in enumerate(sources, 1):
        plans = probe.p85.natural.build_seat_stage_plans(
            contract=contract, opponent=source["mix"], root_index=source["root_index"],
            focal_seat=source["focal_seat"], panel_seed=probe.PANEL_SEED)
        requests = []
        stage = probe.p85.natural.run_arm_stage(
            arm="candidate", plans=plans,
            candidate_scorer=ActionValueScorer("g8-dist-" + source["source_id"], parent),
            opponent_policies=contract["panel"]["opponent_scenarios"][source["mix"]]["opponent_policies"],
            versions_block=probe.p85.natural.stage.contract_versions_block(contract),
            step_limit=int(contract["stop"]["step_limit"]), value_limits=probe.p85.LIMITS,
            decision_observer=requests.append)
        if stage.get("status") != "complete" or len(stage.get("tables") or []) != probe.TABLES_PER_SOURCE:
            raise RuntimeError("自然分布重放不完整")
        scorer = ActionValueScorer("g8-dist-rescore-" + source["source_id"], parent)
        local = Counter()
        for request in requests:
            if request.observation.phase != "draw":
                continue
            if not any(item.action_key == "hu" for item in request.rules.legal_candidates):
                continue
            view = build_scoring_view(request)
            scored = scorer.score(view)
            if scored.status != "SCORED":
                raise ValueError("父代评分未完成")
            entries = sorted(scored.entries, key=lambda item: (-item.score, item.action_key))
            if not entries or entries[0].action_key != "hu":
                continue
            _add(local, probe.decision_request_to_json(request))
        counts.update(local)
        by_mix[source["mix"]].update(local)
        by_root[source["source_root_id"]].update(local)
        if index % 8 == 0:
            print(json.dumps({"completed_sources": index, "planned_sources": len(sources)}), flush=True)
    return {"full_tables": len(sources) * probe.TABLES_PER_SOURCE,
            "independent_roots": len(by_root), "counts": dict(sorted(counts.items())),
            "by_mix": {mix: dict(sorted(row.items())) for mix, row in by_mix.items()},
            "root_counts": {root: dict(sorted(row.items())) for root, row in by_root.items()}}


def main() -> None:
    """保存按房/根的结果盲类别频数，供评测池保真度审查。"""

    output = {"schema": "g8-special-distribution-audit/1", "outcome_blind": True,
              "official": _official(), "natural": _natural(),
              "boundary": "只核对动作前公开状态和父代排序；不同对手/牌山采样框，不能从比率差直接归因规则或对手"}
    path = _project_file(_PROJECT_ROOT, EVIDENCE / "special_distribution_audit.json")
    path.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"official": output["official"]["counts"],
                      "natural": output["natural"]["counts"],
                      "by_mix": output["natural"]["by_mix"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
