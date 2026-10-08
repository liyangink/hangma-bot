#!/usr/bin/env python3
"""在冻结 R18 v2 房的已副露吃/过窗口复算旧 C27/C32 行为，结果盲去重。"""

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
from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.policy.action_value_policy import build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.research_candidates import build_research_candidate_scorer


HERE = Path(__file__).resolve().parent
FROZEN = atlas.FROZEN
R6 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/OPTY-R18-C27-CELL-R6.py')
C32 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/candidates/OPTY-R18-C32-DOSE-C6K6.py')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-claim-overlap-20260927/result.json')


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _top(scorer: ActionValueScorer, view) -> str:
    scored = scorer.score(view)
    if scored.status != "SCORED" or not scored.entries:
        raise ValueError(f"{scorer.name} 在冻结父代合法窗口未能评分")
    return min(scored.entries, key=lambda item: (-item.score, item.action_key)).action_key


def _eligible(legal: dict[str, dict], observation: dict) -> list[str]:
    """与 G11 图谱相同的已副露、综合/普通型不退且双容量局部支配谓词。"""

    seat, melds = observation.get("seat"), observation.get("melds")
    if (type(seat) is not int or not isinstance(melds, list) or not 0 <= seat < len(melds)
            or not isinstance(melds[seat], list) or not melds[seat]):
        return []
    parent = legal["pass"]
    p_std = atlas._int(parent, "standard_shanten_after")
    p_combined = atlas._int(parent, "shanten_after")
    p_std_cap = atlas._capacity(parent, "standard_useful_tiles")
    p_cap = atlas._capacity(parent, "useful_tiles")
    if None in (p_std, p_combined, p_std_cap, p_cap):
        return []
    return [key for key, facts in legal.items()
            if key.startswith("chi:")
            and atlas._int(facts, "standard_shanten_after") == p_std
            and atlas._int(facts, "shanten_after") == p_combined
            and atlas._capacity(facts, "standard_useful_tiles") is not None
            and atlas._capacity(facts, "standard_useful_tiles") > p_std_cap
            and atlas._capacity(facts, "useful_tiles") is not None
            and atlas._capacity(facts, "useful_tiles") >= p_cap]


def main() -> None:
    """仅比较相同动作前视图的程序行为；不读取官方后续或桌分。"""

    if OUT.exists():
        raise SystemExit("G11 旧方案行为重合证据已存在，拒绝覆盖")
    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    parent = build_research_candidate_scorer("r18_integrated_positive_v2")
    r6 = ActionValueScorer("g11-c27-cell-r6", R6.read_text(encoding="utf-8"))
    c32 = ActionValueScorer("g11-c32-c6k6", C32.read_text(encoding="utf-8"))
    rows = []
    counts = Counter()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结父代决策文件漂移")
        accepted = atlas.source._accepted(decision_file)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            if context.get("game_id") not in complete_ids:
                continue
            if (raw.get("window_key") or {}).get("phase") != "response_chi":
                continue
            ranked = sorted(plan.get("candidates") or [],
                            key=lambda item: item.get("rank", 10**9))
            if not ranked or ranked[0].get("action_key") != "pass":
                continue
            if accepted.get(context.get("decision_id")) != "pass":
                continue
            candidates = (raw.get("rules") or {}).get("legal_candidates") or []
            legal = {item["action_key"]: item.get("facts") or {} for item in candidates}
            if len(legal) != len(candidates) or "pass" not in legal:
                raise ValueError("已接受过牌的规则合法表不完整")
            eligible = _eligible(legal, raw["observation"])
            if not eligible:
                continue
            view = build_scoring_view(decision_request_from_json(raw))
            top_parent, top_r6, top_c32 = (_top(parent, view), _top(r6, view), _top(c32, view))
            if top_parent != "pass":
                raise ValueError("冻结父代重新评分与已接受的首选不一致")
            p_std = atlas._int(legal["pass"], "standard_shanten_after")
            p_combined = atlas._int(legal["pass"], "shanten_after")
            row = {"room_id": room["room_id"], "game_id": context["game_id"],
                   "round_no": context["round_no"], "trigger_seq": context["trigger_seq"],
                   "eligible_chi": sorted(eligible), "parent_standard_shanten": p_std,
                   "parent_combined_shanten": p_combined,
                   "g2_double_tenpai_surface": p_combined == 0,
                   "r6_action": top_r6, "c32_action": top_c32,
                   "r6_selects_eligible": top_r6 in eligible,
                   "c32_selects_eligible": top_c32 in eligible,
                   "wall_remaining": raw["observation"].get("remaining_tile_count"),
                   "white_count": (raw["observation"].get("my_hand") or []).count("白")}
            rows.append(row)
            counts["windows"] += 1
            counts["g2_double_tenpai_surface" if p_combined == 0 else "not_g2_double_tenpai_surface"] += 1
            counts["r6_selects_claim" if top_r6 != "pass" else "r6_keeps_pass"] += 1
            counts["c32_selects_claim" if top_c32 != "pass" else "c32_keeps_pass"] += 1
            if top_r6 in eligible:
                counts["r6_selects_eligible"] += 1
            if top_c32 in eligible:
                counts["c32_selects_eligible"] += 1
    ids = {row["game_id"] for row in rows}
    if len(rows) != 562 or len(ids) != 389:
        raise ValueError("与 G11 先前结果盲图谱的严格谓词覆盖不一致")
    groups = {
        "r6_unchanged": [row for row in rows if row["r6_action"] == "pass"],
        "c32_unchanged": [row for row in rows if row["c32_action"] == "pass"],
        "both_unchanged": [row for row in rows if row["r6_action"] == "pass"
                           and row["c32_action"] == "pass"],
        "outside_g2_surface": [row for row in rows if not row["g2_double_tenpai_surface"]],
    }
    result = {"schema": "g11-claim-old-behavior-overlap/1", "outcome_blind": True,
              "frozen_rooms_sha256": _sha(FROZEN),
              "parent_source_sha256": frozen["parent_source_sha256"],
              "r6_source_sha256": _sha(R6), "c32_source_sha256": _sha(C32),
              "complete_official_tables": len(complete_ids),
              "counts": dict(sorted(counts.items())),
              "groups": {name: {"windows": len(group),
                                "complete_tables": len({row["game_id"] for row in group})}
                         for name, group in groups.items()},
              "rows": rows,
              "boundary": "只审旧候选在父代已接受过牌窗口的动作选择；无未来墙/终局，G2 仅比较表面双听牌谓词，不能推出新策略价值。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "rows"},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
