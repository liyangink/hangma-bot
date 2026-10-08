#!/usr/bin/env python3
"""G81：仅用冻结父代真实动作前事实筛查后验墙进张校正的行为。"""

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

from collections import Counter
import hashlib
import json
from pathlib import Path
import time

import g11_cross_family_action_atlas as atlas
import g81_posterior_wall_policy as candidate
from hangma_bot.application.audit_codec import decision_plan_from_json, decision_request_from_json
from hangma_bot.hangma.engine import _build_context


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g81-posterior-wall-behavior-20260928/result.json')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G81-POSTERIOR-WALL-CANDIDATE-PREREG-2026-09-28.md')
MODEL = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g79b-corrected-occupancy-transfer-20260928/result.json')
G58A = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g58-executable-search-wave-20260927/official_behavior_diagnostic.json')
G74 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g74-single-honor-behavior-20260928/result.json')


def sha(path: Path) -> str:
    """绑定结果所用冻结源码与证据。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _old_actions() -> tuple[dict, dict]:
    """已关闭候选的动作指纹只用于行为去重，不读桌分。"""

    old58 = json.loads(G58A.read_text(encoding="utf-8"))
    old74 = json.loads(G74.read_text(encoding="utf-8"))
    if not old58["outcome_blind"] or not old74["outcome_blind"]:
        raise ValueError("旧候选行为对照不是结果盲数据")
    g58 = {(row["game_id"], row["round_no"], row["trigger_seq"]): row["candidate_action"]
           for row in old58["cards"]["a_contextual_width"]["changes"]}
    g74 = {(row["game_id"], row["round_no"], row["trigger_seq"]): row["candidate_action"]
           for row in old74["changed"]}
    return g58, g74


def main() -> None:
    """只观察是否有合法、可归因、独有的父代改选；不读取赛后收益。"""

    if OUT.exists():
        raise SystemExit("G81 行为结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    old58, old74 = _old_actions()
    model = json.loads(MODEL.read_text(encoding="utf-8"))["model"]["coefficients"]
    names = ("honor", "terminal", "edge", "unknown_minus_two", "opponent_same_river",
             "own_same_river", "opponent_neighbor_river", "opponent_same_suit_melds")
    if tuple(model[name] for name in names) != candidate.COEFFICIENTS:
        raise ValueError("G81 内嵌系数偏离 G79B 冻结参数")
    counts = Counter()
    changes = []
    all_rooms, all_tables = set(), set()
    elapsed = []
    seen = set()
    for room_number, room in enumerate(frozen["rooms"], start=1):
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结动作审计字节数漂移")
        release = (json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                   .get("payload") or {}).get("policy_release") or {}
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("冻结父代源码身份漂移")
        accepted = atlas.source._accepted(decisions)
        for identity, raw, plan in atlas.source.screen._iter_decisions(audit):
            if identity.get("game_id") not in complete:
                continue
            if (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if not ranked:
                continue
            parent = ranked[0].get("action_key")
            if not isinstance(parent, str) or not parent.startswith("discard:"):
                continue
            if accepted.get(identity.get("decision_id")) != parent:
                continue
            key = identity["game_id"], identity["round_no"], identity["trigger_seq"]
            if key in seen:
                raise ValueError("冻结官方已接受动作窗口重复")
            seen.add(key)
            request = decision_request_from_json(raw)
            original = decision_plan_from_json(plan)
            start = time.perf_counter()
            try:
                action, evidence = candidate.select(request, original)
            except Exception as error:
                action, evidence = None, {"reason": "selector_exception",
                                          "error_type": type(error).__name__}
            elapsed.append((time.perf_counter() - start) * 1000)
            counts["parent_accepted_draw_discards"] += 1
            counts["reason|" + evidence["reason"]] += 1
            if action is None:
                continue
            legal = {item.action_key: item for item in request.rules.legal_candidates}
            if action not in legal or action == parent or evidence["reason"] != "posterior_recalibration":
                raise ValueError("G81 产生非独有或非法弃牌")
            p = legal[parent].facts
            b = legal[action].facts
            if (b.shanten_after != p.shanten_after
                    or b.standard_shanten_after != p.standard_shanten_after
                    or (p.seven_pairs_shanten_after is not None
                        and b.seven_pairs_shanten_after > p.seven_pairs_shanten_after)
                    or (p.baotou_after is True and b.baotou_after is not True)):
                raise ValueError("G81 牌型路线守卫失效")
            full = Counter(tile.code for tile in _build_context(request.observation).full_hand())
            if full["白"] - (action == "discard:白") < full["白"] - (parent == "discard:白"):
                raise ValueError("G81 白板保留守卫失效")
            room_id = room["room_id"]
            all_rooms.add(room_id)
            all_tables.add(identity["game_id"])
            counts["changed"] += 1
            counts["same_g58a_action"] += old58.get(key) == action
            counts["same_g74_action"] += old74.get(key) == action
            counts["same_any_old_action"] += old58.get(key) == action or old74.get(key) == action
            wall = request.observation.remaining_tile_count
            bucket = "20-39" if wall < 40 else "40-79" if wall < 80 else "80+"
            counts["changed_wall|" + bucket] += 1
            counts[f"changed_white|{full['白']}"] += 1
            counts[f"changed_own_melds|{len(request.observation.melds[request.observation.seat])}"] += 1
            changes.append({"room_id": room_id, "game_id": key[0], "round_no": key[1],
                            "trigger_seq": key[2], "parent_action": parent,
                            "candidate_action": action, "same_g58a_action": old58.get(key) == action,
                            "same_g74_action": old74.get(key) == action, **evidence})
        if room_number % 10 == 0:
            print(json.dumps({"rooms_processed": room_number,
                              "draw_discards": counts["parent_accepted_draw_discards"],
                              "changed": counts["changed"]}, ensure_ascii=False), flush=True)
    elapsed.sort()
    qualify = (counts["changed"] >= 100 and len(all_tables) >= 50 and len(all_rooms) >= 30
               and counts["reason|selector_exception"] == 0
               and counts["same_any_old_action"] < counts["changed"])
    result = {"schema": "g81-posterior-wall-behavior/1", "outcome_blind": True,
              "source_sha256": {"prereg": sha(PREREG), "candidate": sha(_project_file(_PROJECT_ROOT, HERE / "g81_posterior_wall_policy.py")),
                                "script": sha(Path(__file__)), "frozen_rooms": sha(atlas.FROZEN),
                                "model": sha(MODEL), "g58a_behavior": sha(G58A),
                                "g74_behavior": sha(G74)},
              "complete_official_tables": len(complete),
              "changed_rooms": len(all_rooms), "changed_tables": len(all_tables),
              "counts": dict(sorted(counts.items())), "behavior_gate_passed": qualify,
              "elapsed_ms": {} if not elapsed else {
                  "p50": elapsed[int((len(elapsed)-1)*.5)],
                  "p95": elapsed[int((len(elapsed)-1)*.95)], "max": elapsed[-1]},
              "changed": sorted(changes, key=lambda row: (row["game_id"], row["round_no"],
                                                        row["trigger_seq"])),
              "boundary": "只核已接受父代动作和玩家可见规则事实；不读取赛后积分或墙。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "changed"},
                     ensure_ascii=False, sort_keys=True, indent=2), flush=True)


if __name__ == "__main__":
    main()
