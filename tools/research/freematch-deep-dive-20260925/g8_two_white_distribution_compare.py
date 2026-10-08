#!/usr/bin/env python3
"""结果盲比较官方房与新 H/M 自然根的双白收胡入口分布。"""

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


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927')


def main() -> None:
    """只读取冻结的动作前请求和父代首选，不读取任一比赛结局。"""

    frozen = json.loads((_project_file(_PROJECT_ROOT, EVIDENCE / "frozen_rooms.json")).read_text(encoding="utf-8"))
    official = Counter()
    official_rooms = defaultdict(Counter)
    for room in frozen["rooms"]:
        audit = _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"])
        path = audit / "participants" / census.PARTICIPANT / "decisions.jsonl"
        if path.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结审计大小漂移")
        for _, request in census._iter_parent_hu(audit):
            observation = request.get("observation") or {}
            if observation.get("phase") != "draw":
                continue
            official["parent_hu_draw"] += 1
            official_rooms[room["room_id"]]["parent_hu_draw"] += 1
            hand, _ = census._complete_hand(observation)
            if hand.count("白") != 2:
                continue
            official["parent_hu_two_white"] += 1
            official_rooms[room["room_id"]]["parent_hu_two_white"] += 1
            if type(observation.get("remaining_tile_count")) is not int or observation["remaining_tile_count"] <= 24:
                continue
            official["two_white_wall_gt24"] += 1
            official_rooms[room["room_id"]]["two_white_wall_gt24"] += 1
            hu = next((item for item in (request.get("rules") or {}).get("legal_candidates") or []
                       if item.get("action_key") == "hu"), None)
            if hu is None:
                raise ValueError("父代选胡但规则无合法胡")
            settlement = (hu.get("value_facts") or {}).get("immediate_settlement") or {}
            fan = settlement.get("fan")
            if type(fan) is not int:
                raise ValueError("合法胡缺立即结算番")
            official["two_white_wall_gt24_fan_" + str(fan)] += 1
            official_rooms[room["room_id"]]["two_white_wall_gt24_fan_" + str(fan)] += 1
    manifest = json.loads((_project_file(_PROJECT_ROOT, EVIDENCE / "natural-probe-corrected/manifest.json")).read_text(encoding="utf-8"))
    result = json.loads((_project_file(_PROJECT_ROOT, EVIDENCE / "natural-probe-corrected/result.json")).read_text(encoding="utf-8"))
    if not manifest["outcome_blind"] or not result["outcome_blind"]:
        raise ValueError("自然探针结果盲标志缺失")
    natural = Counter(result["raw_counts"])
    # 探针筛查次序保证：exactly_two_white→parent_top_hu→fan1→静态路径；
    # 本批的 no_public_next_draw_route、immediate_target_present、no_next_draw_wall_budget 均为零。
    for key in ("no_public_next_draw_route", "immediate_target_present"):
        if natural[key]:
            raise ValueError("存在未按当前口径归类的窄入口：" + key)
    natural_parent_hu_two_white = natural["eligible"] + natural["hu_fan_not_one"]
    output = {
        "schema": "g8-two-white-distribution-compare/1", "outcome_blind": True,
        "official": {"rooms": len(frozen["rooms"]),
                     "full_tables": sum(room["games"] for room in frozen["rooms"]),
                     "counts": dict(official),
                     "room_count_histogram_wall_gt24_fan1": dict(sorted(Counter(
                         row["two_white_wall_gt24_fan_1"] for row in official_rooms.values()).items()))},
        "natural": {"independent_roots": len({row["source_root_id"] for row in
                                                json.loads((_project_file(_PROJECT_ROOT, EVIDENCE / "natural-probe-corrected/sources.json")).read_text(encoding="utf-8"))["sources"]}),
                    "full_tables": result["full_tables"],
                    "parent_hu_two_white": natural_parent_hu_two_white,
                    "two_white_fan_1": natural["eligible"],
                    "two_white_fan_not_1": natural["hu_fan_not_one"],
                    "parent_not_hu_two_white": natural["parent_not_hu"],
                    "independent_eligible_roots_by_mix": result["independent_roots_by_mix"]},
        "caveat": "官方连续已完房与新 H/M 自然根的对手和采样框不同；比率仅作表示/评测池校验，不是策略效果或显著性证明",
    }
    path = _project_file(_PROJECT_ROOT, EVIDENCE / "distribution_compare.json")
    path.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
