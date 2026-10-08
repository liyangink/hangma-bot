#!/usr/bin/env python3
"""G14 结果盲弃牌进张面基线：只数真实父代动作前的合法牌形事实。"""

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
import hashlib
import json
from pathlib import Path

import g11_cross_family_action_atlas as atlas
import g11_longitudinal_route_audit as g11


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g14-discard-width-baseline-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _shape(facts: dict) -> dict:
    """未知按未知保留；容量是公开未见数，不是墙内成功概率。"""

    return {"standard_shanten": atlas._int(facts, "standard_shanten_after"),
            "combined_shanten": atlas._int(facts, "shanten_after"),
            "seven_shanten": atlas._int(facts, "seven_pairs_shanten_after"),
            "standard": g11._support_shape(facts, "standard_useful_tiles"),
            "combined": g11._support_shape(facts, "useful_tiles"),
            "seven": g11._support_shape(facts, "seven_pairs_useful_tiles")}


def _safe_wider(parent: dict, other: dict, *, allowed_capacity_loss: int) -> bool:
    """同普通/综合进度、七对不退的局部宽面；它不是净收益标签。"""

    ps, os = parent["standard"], other["standard"]
    pc, oc = parent["combined"], other["combined"]
    if any(value is None for value in (ps, os, pc, oc)):
        return False
    if (parent["standard_shanten"] is None or parent["combined_shanten"] is None
            or other["standard_shanten"] != parent["standard_shanten"]
            or other["combined_shanten"] != parent["combined_shanten"]):
        return False
    if parent["seven_shanten"] is not None:
        if other["seven_shanten"] is None or other["seven_shanten"] > parent["seven_shanten"]:
            return False
    return (os[1] > ps[1] and os[0] >= ps[0] - allowed_capacity_loss
            and oc[0] >= pc[0] - allowed_capacity_loss)


def main() -> None:
    """扫描固定 91 间父代房，不读取终局积分或未来墙。"""

    if OUT.exists():
        raise SystemExit("G14 弃牌宽面基线已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    if len(complete) != 909:
        raise ValueError("核验完整桌母体漂移")
    rows, coverage = g11._draw_rows(complete, frozen)
    counts = Counter()
    scopes = defaultdict(set)
    stratified = defaultdict(Counter)
    examples = defaultdict(list)
    for row in rows:
        parent = _shape(row["legal"][row["parent_action"]])
        if parent["standard"] is None or parent["combined"] is None:
            counts["parent_shape_unknown"] += 1
            continue
        counts["normal_parent_discards"] += 1
        shanten = parent["standard_shanten"]
        width = parent["standard"][1]
        cap = parent["standard"][0]
        white = row["white_count"]
        stratum = "shanten_%s_white_%s" % (shanten, "3plus" if white >= 3 else white)
        stratified[stratum]["windows"] += 1
        for bound in (1, 2, 3, 4):
            if width <= bound:
                stratified[stratum][f"standard_types_le_{bound}"] += 1
                counts[f"standard_types_le_{bound}"] += 1
                scopes[f"standard_types_le_{bound}"].add(row["game_id"])
        for loss in (0, 2):
            alternatives = []
            for action, facts in row["legal"].items():
                if action == row["parent_action"] or not action.startswith("discard:"):
                    continue
                shape = _shape(facts)
                if _safe_wider(parent, shape, allowed_capacity_loss=loss):
                    alternatives.append((action, shape))
            if alternatives:
                key = f"wider_safe_capacity_loss_le_{loss}"
                counts[key] += 1
                scopes[key].add(row["game_id"])
                stratified[stratum][key] += 1
                if width <= 3:
                    counts[key + "_parent_types_le_3"] += 1
                    scopes[key + "_parent_types_le_3"].add(row["game_id"])
                if len(examples[key]) < 8:
                    best_action, best = max(alternatives, key=lambda pair: (
                        pair[1]["standard"][1], pair[1]["standard"][0], pair[0]))
                    examples[key].append({
                        "room_id": row["room_id"], "game_id": row["game_id"],
                        "round_no": row["round_no"], "seat": row["seat"],
                        "trigger_seq": row["trigger_seq"], "white_count": white,
                        "parent_action": row["parent_action"], "parent_standard_types": width,
                        "parent_standard_capacity_upper": cap,
                        "alternative_action": best_action,
                        "alternative_standard_types": best["standard"][1],
                        "alternative_standard_capacity_upper": best["standard"][0],
                        "parent_minus_alternative_policy_score":
                            row["scores"][row["parent_action"]] - row["scores"][best_action],
                    })
    result = {"schema": "g14-discard-width-baseline/1", "outcome_blind": True,
              "source_frozen_rooms_sha256": _sha(atlas.FROZEN),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "analysis_script_sha256": _sha(Path(__file__)),
              "complete_official_tables": len(complete),
              "accepted_normal_draw_discards": coverage["accepted_normal_draw_discards"],
              "counts": dict(sorted(counts.items())),
              "scopes": {key: len(ids) for key, ids in sorted(scopes.items())},
              "strata": {key: dict(sorted(value.items()))
                         for key, value in sorted(stratified.items())},
              "examples": dict(examples),
              "boundary": "仅行动前规则事实和父代接受动作。宽面条件不是收益标签；公开容量含他家暗手；不读未来牌墙、终局积分。"}
    OUT.parent.mkdir(parents=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"counts": result["counts"], "scopes": result["scopes"]},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
