#!/usr/bin/env python3
"""G58A 派生策略 typed 接口与冻结官方 JSON 行为逐窗对账。"""

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
import g58a_contextual_width_policy as candidate
import g58_executable_search_wave as wave
from hangma_bot.application.audit_codec import decision_plan_from_json, decision_request_from_json


HERE = Path(__file__).resolve().parent
BEHAVIOR = wave.OUT / "official_behavior_diagnostic.json"
OUT = wave.OUT / "g58a_typed_equivalence.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """仅对父代已接受正常摸打重判，不打开终局积分。"""

    if OUT.exists():
        raise SystemExit("G58A typed 对账结果已存在，拒绝覆盖")
    source = json.loads(BEHAVIOR.read_text(encoding="utf-8"))
    expected = {(row["game_id"], row["round_no"], row["trigger_seq"]): row["candidate_action"]
                for row in source["cards"]["a_contextual_width"]["changes"]}
    if len(expected) != source["cards"]["a_contextual_width"]["counts"]["changed"]:
        raise ValueError("G58A 原程序诊断改选窗口重复")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete_ids = atlas._complete_ids()
    counts = Counter()
    observed = {}
    elapsed = []
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decisions = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decisions.stat().st_size != room["decision_bytes"]:
            raise ValueError("冻结决策文件字节数漂移")
        accepted = atlas.source._accepted(decisions)
        for identity, raw, plan in atlas.source.screen._iter_decisions(audit):
            if identity.get("game_id") not in complete_ids or (raw.get("window_key") or {}).get("phase") != "draw":
                continue
            ranked = sorted(plan.get("candidates") or [], key=lambda item: item.get("rank", 10**9))
            if not ranked or not isinstance(ranked[0].get("action_key"), str):
                continue
            parent = ranked[0]["action_key"]
            if not parent.startswith("discard:") or accepted.get(identity.get("decision_id")) != parent:
                continue
            if any(item.get("action_key", "").startswith("hu") for item in
                   (raw.get("rules") or {}).get("legal_candidates") or []):
                continue
            obs = raw.get("observation") or {}
            seat, melds, hand, drawn = (obs.get("seat"), obs.get("melds"),
                                         obs.get("my_hand"), obs.get("drawn_tile"))
            if (type(seat) is not int or not isinstance(melds, list)
                    or not 0 <= seat < len(melds) or not isinstance(melds[seat], list)
                    or not isinstance(hand, list) or not isinstance(drawn, str)
                    or len(hand) != 14 - 3 * len(melds[seat]) or drawn not in hand):
                continue
            request = decision_request_from_json(raw)
            original = decision_plan_from_json(plan)
            start = time.perf_counter()
            action, evidence = candidate.select(request, original)
            elapsed.append((time.perf_counter() - start) * 1000)
            key = identity["game_id"], identity["round_no"], identity["trigger_seq"]
            counts["screened"] += 1
            counts["reason|" + evidence["reason"]] += 1
            if action is not None:
                observed[key] = action
    if counts["screened"] != source["counts"]["eligible_parent_draw_discard"]:
        raise ValueError("typed 与原 JSON 诊断母体不一致")
    if observed != expected:
        extra = set(observed) - set(expected)
        missing = set(expected) - set(observed)
        different = {key for key in set(observed) & set(expected) if observed[key] != expected[key]}
        raise ValueError(f"typed 策略与原程序行为不等价：额外{len(extra)}、缺失{len(missing)}、异动作{len(different)}")
    elapsed.sort()
    output = {"schema": "g58a-typed-equivalence/1", "outcome_blind": True,
              "parent_source_sha256": frozen["parent_source_sha256"],
              "behavior_sha256": sha(BEHAVIOR),
              "author_program_sha256": sha(_project_file(_PROJECT_ROOT, HERE / "g58a_author_program.py")),
              "wrapper_sha256": sha(_project_file(_PROJECT_ROOT, HERE / "g58a_contextual_width_policy.py")),
              "script_sha256": sha(Path(__file__)),
              "complete_official_tables": len(complete_ids),
              "counts": dict(counts), "changed": len(observed),
              "elapsed_ms_p95": elapsed[int((len(elapsed)-1)*.95)] if elapsed else None,
              "elapsed_ms_max": elapsed[-1] if elapsed else None,
              "boundary": "只证明 typed 包装在冻结父代官方动作前事实与原程序诊断逐窗一致；不证明候选完整桌收益或线上时限。"}
    OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
