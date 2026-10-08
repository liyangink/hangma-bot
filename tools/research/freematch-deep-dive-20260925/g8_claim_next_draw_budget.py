#!/usr/bin/env python3
"""结果盲筛查同向听鸣/过对本人下一次普通自摸的名义墙余预算。

只计算“无人再鸣、无人先胡、无杠”的座位循环基线，非真实后续概率。
规则事实来自冻结 `RuleAnalysis`；对手暗手和未来牌墙均不可见。
"""

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

import natural_shape_loss_screen as screen


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
FROZEN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-two-white-next-draw-20260927/frozen_rooms.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g8-claim-next-draw-budget-20260927/result.json')
RESERVED_WALL = 20  # 官方指南 v34：最后 10 墩不可摸；模拟推进 ProgressionState.wall_total 同口径。


def _shanten(candidate: dict) -> int | None:
    value = (candidate.get("facts") or {}).get("shanten_after")
    return value if type(value) is int else None


def _classify(request: dict, plan: dict) -> dict | None:
    window = request.get("window_key") or {}
    phase = window.get("phase")
    if phase not in ("response_peng", "response_chi"):
        return None
    observation = request.get("observation") or {}
    seat = observation.get("seat")
    discarder = (observation.get("last_discard") or {}).get("seat")
    wall = observation.get("remaining_tile_count")
    if any(type(item) is not int for item in (seat, discarder, wall)):
        raise ValueError("鸣/过名义时序缺座位或墙余事实")
    if observation.get("turn_seat") != discarder:
        raise ValueError("弃牌座位与响应窗不符")
    distance = (seat - discarder) % 4
    if distance not in (1, 2, 3) or (phase == "response_chi" and distance != 1):
        raise ValueError("相对座位不符")
    legal = (request.get("rules") or {}).get("legal_candidates") or []
    passes = [item for item in legal if (item.get("action") or {}).get("kind") == "pass"]
    claims = [item for item in legal if (item.get("action") or {}).get("kind") ==
              ("chi" if phase == "response_chi" else "peng")]
    if not claims:
        return None
    if len(passes) != 1:
        raise ValueError("有鸣牌却缺唯一过牌")
    pass_shanten = _shanten(passes[0])
    claim_shantens = [_shanten(item) for item in claims]
    if pass_shanten is None or any(value is None for value in claim_shantens):
        raise ValueError("鸣/过向听事实不完整")
    best_claim_shanten = min(claim_shantens)
    ranked = (plan.get("candidates") or [])
    if not ranked:
        raise ValueError("父代决策计划为空")
    top = min(ranked, key=lambda item: item.get("rank", 10**9))["action_key"]
    claim_keys = {item["action_key"] for item in claims}
    choice = "claim" if top in claim_keys else "pass" if top == "pass" else "other"
    # 当前弃牌者打完牌后，过牌基线在第 distance 次普通摸牌轮到我；
    # 我鸣牌并跟打后，名义上在第 4 次普通摸牌才重新轮到我。
    # 后续他家鸣/杠/胡均可改写这个次序，所以这里只能作结果盲暴露上界。
    drawable = max(0, wall - RESERVED_WALL)
    return {"phase": phase, "pass_shanten": pass_shanten,
            "best_claim_shanten": best_claim_shanten, "distance": distance,
            "wall": wall, "drawable_upper": drawable, "choice": choice,
            "pass_nominal_next_draw": drawable >= distance,
            "claim_nominal_next_draw": drawable >= 4,
            "skipped_draw_slots_if_claim": 4 - distance}


def main() -> None:
    """按冻结 91 房逐窗计数，独立房数单列，不把动作窗充当收益样本。"""

    frozen = json.loads(FROZEN.read_text(encoding="utf-8"))
    counts = Counter()
    rooms = defaultdict(set)
    examples = []
    seen = set()
    for room in frozen["rooms"]:
        audit = _project_file(_PROJECT_ROOT, ROOT / room["audit_dir"])
        decisions = audit / "participants" / screen.PARTICIPANT / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结房审计大小漂移")
        release = (json.loads((audit / "manifest.json").read_text(encoding="utf-8")).get("payload") or {}).get("policy_release") or {}
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代身份漂移")
        for context, request, plan in screen._iter_decisions(audit):
            key = (context.get("game_id"), context.get("round_no"),
                   context.get("trigger_seq"), (request.get("window_key") or {}).get("phase"))
            if key in seen:
                counts["duplicate_windows"] += 1
                continue
            seen.add(key)
            row = _classify(request, plan)
            if row is None:
                continue
            counts["legal_claim_pass"] += 1
            if row["pass_shanten"] != row["best_claim_shanten"]:
                continue
            counts["same_shanten"] += 1
            rooms["same_shanten"].add(room["room_id"])
            counts[f"same_shanten_{row['pass_shanten']}"] += 1
            counts[f"same_shanten_choice_{row['choice']}"] += 1
            counts[f"distance_{row['distance']}_choice_{row['choice']}"] += 1
            counts[f"wall_{'reserve_edge' if row['wall'] <= 23 else 'middle' if row['wall'] <= 40 else 'early'}"] += 1
            if row["pass_nominal_next_draw"] and not row["claim_nominal_next_draw"]:
                counts["pass_keeps_nominal_last_draw_claim_loses"] += 1
                counts[f"reserve_edge_choice_{row['choice']}"] += 1
                counts[f"reserve_edge_shanten_{row['pass_shanten']}"] += 1
                rooms["reserve_edge"].add(room["room_id"])
                if len(examples) < 20:
                    examples.append({"room_id": room["room_id"], "game_id": key[0],
                                     "round_no": key[1], "trigger_seq": key[2], **row})
    edge = counts["pass_keeps_nominal_last_draw_claim_loses"]
    passes = (edge >= 30 and len(rooms["reserve_edge"]) >= 10
              and counts["reserve_edge_choice_claim"] >= 10)
    result = {"schema": "g8-claim-next-draw-budget/1", "outcome_blind": True,
              "source_official_rooms": len(frozen["rooms"]), "parent_source_sha256": frozen["parent_source_sha256"],
              "counts": dict(sorted(counts.items())),
              "rooms_with_same_shanten": len(rooms["same_shanten"]),
              "rooms_with_reserve_edge": len(rooms["reserve_edge"]),
              "examples": examples,
              "reserve_edge_exposure_gate": {"minimum_windows": 30, "minimum_rooms": 10,
                                             "minimum_parent_claims": 10, "passed": passes},
              "decision": ("OPEN_RULE_TIMING_CAUSAL_DESIGN" if passes else
                           "CLOSE_NARROW_RESERVE_EDGE_RETAIN_GENERAL_TIMING_AUDIT"),
              "boundary": "座位循环为无人再鸣/杠/胡时的名义基线；不能声称保证下次自摸或真实失胡概率，且未读取比赛结果"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "examples"},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
