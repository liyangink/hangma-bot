#!/usr/bin/env python3
"""G74：冻结 R18 v2 官方轨迹的结果盲合法改选与旧 G58A 行为去重。"""

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
import g74_single_honor_policy as candidate
from hangma_bot.application.audit_codec import decision_plan_from_json, decision_request_from_json


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g74-single-honor-behavior-20260928/result.json')
G58A = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g58-executable-search-wave-20260927/official_behavior_diagnostic.json')
G30 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g30-edge-behavior-20260927/result.json')


def sha(path: Path) -> str:
    """绑定已冻结输入和候选源码。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise SystemExit("G74 行为结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    prior58 = json.loads(G58A.read_text(encoding="utf-8"))
    prior30 = json.loads(G30.read_text(encoding="utf-8"))
    if not prior58["outcome_blind"] or not prior30["outcome_blind"]:
        raise ValueError("旧候选行为对照含成绩信息")
    old58 = {(row["game_id"], row["round_no"], row["trigger_seq"]): row["candidate_action"]
             for row in prior58["cards"]["a_contextual_width"]["changes"]}
    old30 = {(row["game_id"], row["round_no"], row["trigger_seq"]): row["candidate_action"]
             for row in prior30["changed"]}
    counts = Counter()
    changed = []
    rooms, tables = set(), set()
    elapsed = []
    seen = set()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结官方动作审计字节数漂移")
        accepted = atlas.source._accepted(decisions)
        for identity, raw, plan in atlas.source.screen._iter_decisions(audit):
            if identity.get("game_id") not in complete:
                continue
            if (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if not ranked or not isinstance(ranked[0].get("action_key"), str):
                continue
            parent = ranked[0]["action_key"]
            if not parent.startswith("discard:") or accepted.get(identity.get("decision_id")) != parent:
                continue
            key = identity["game_id"], identity["round_no"], identity["trigger_seq"]
            if key in seen:
                raise ValueError("冻结官方已接受动作窗口重复")
            seen.add(key)
            request = decision_request_from_json(raw)
            original = decision_plan_from_json(plan)
            start = time.perf_counter()
            action, evidence = candidate.select(request, original)
            elapsed.append((time.perf_counter() - start) * 1000)
            counts["parent_accepted_draw_discards"] += 1
            counts["reason|" + evidence["reason"]] += 1
            if action is None:
                continue
            legal = {item.action_key for item in request.rules.legal_candidates}
            if action not in legal or action == parent or evidence["reason"] != "strict_honor_pareto":
                raise ValueError("G74 改选不是独有合法弃牌")
            if request.observation.my_hand.count(next(
                    tile for tile in request.observation.my_hand if tile.code == action.split(":", 1)[1])) != 1:
                raise ValueError("G74 非单张字牌改选")
            room_id = room["room_id"]
            rooms.add(room_id)
            tables.add(identity["game_id"])
            counts["changed"] += 1
            counts["same_g58a_action"] += old58.get(key) == action
            counts["same_g30_action"] += old30.get(key) == action
            changed.append({"room_id": room_id, "game_id": key[0], "round_no": key[1],
                            "trigger_seq": key[2], "parent_action": parent,
                            "candidate_action": action,
                            "same_g58a_action": old58.get(key) == action,
                            "same_g30_action": old30.get(key) == action,
                            **evidence})
    elapsed.sort()
    result = {"schema": "g74-single-honor-behavior/1", "outcome_blind": True,
              "source_sha256": {"frozen_rooms": sha(atlas.FROZEN),
                                "g58a_behavior": sha(G58A), "g30_behavior": sha(G30),
                                "candidate": sha(_project_file(_PROJECT_ROOT, HERE / "g74_single_honor_policy.py"))},
              "script_sha256": sha(Path(__file__)), "complete_official_tables": len(complete),
              "counts": dict(sorted(counts.items())), "changed_rooms": len(rooms),
              "changed_tables": len(tables),
              "elapsed_ms_p95": elapsed[int((len(elapsed)-1)*.95)] if elapsed else None,
              "elapsed_ms_max": elapsed[-1] if elapsed else None,
              "changed": sorted(changed, key=lambda row: (row["game_id"], row["round_no"],
                                                        row["trigger_seq"])),
              "boundary": "只核冻结父代已接受动作与依法可见规则事实，不读取赛后积分；动作覆盖不是完整桌收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"complete_official_tables": len(complete),
                      "changed_rooms": len(rooms), "changed_tables": len(tables),
                      "counts": result["counts"], "elapsed_ms_p95": result["elapsed_ms_p95"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
