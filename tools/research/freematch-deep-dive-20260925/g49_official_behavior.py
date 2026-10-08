#!/usr/bin/env python3
"""G49：在冻结官方父代观察上结果盲重判保白普通型候选的独有行为。"""

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
import g49_natural_route_policy as candidate
from hangma_bot.application.audit_codec import decision_plan_from_json, decision_request_from_json


HERE = Path(__file__).resolve().parent
G48 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g48-cross-layer-natural-gap-reach-20260927/result.json')
G10 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g10-route-option-screen-20260927/result.json')
G11 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-behavior-20260927/result.json')
G30 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g30-edge-behavior-20260927/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g49-official-behavior-20260927/result.json')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_key(row: dict) -> tuple[str, int, int]:
    return row["game_id"], row["round_no"], row["trigger_seq"]


def main() -> None:
    """只重判 G48 已证明存在缺口下降的窗口，并核实父代身份和已接受动作。"""

    if OUT.exists():
        raise SystemExit("G49 结果已存在，拒绝覆盖")
    frozen = json.loads(atlas.FROZEN.read_text(encoding="utf-8"))
    complete = atlas._complete_ids()
    g48 = json.loads(G48.read_text(encoding="utf-8"))
    if (len(complete) != 909 or len(g48["rows"]) != 318
            or g48.get("outcome_blind") is not True
            or frozen.get("parent_source_sha256") != g48.get("parent_source_sha256")):
        raise ValueError("G49 父代、完整桌或 G48 入口身份不符")
    g48_by_key = {row_key(row): row for row in g48["rows"]}
    if len(g48_by_key) != 318:
        raise ValueError("G48 入口窗口重复")
    g10 = {row_key(row) for row in json.loads(G10.read_text(encoding="utf-8"))["rows"]}
    g11 = {row_key(row): row["candidate_action"]
           for row in json.loads(G11.read_text(encoding="utf-8"))["changed"]}
    g30 = {row_key(row): row["candidate_action"]
           for row in json.loads(G30.read_text(encoding="utf-8"))["changed"]}
    counts = Counter()
    rows = []
    durations = []
    seen = set()
    for room in frozen["rooms"]:
        audit = atlas.source.ROOT / room["audit_dir"]
        decision_file = audit / "participants" / atlas.source.ACTOR / "decisions.jsonl"
        if decision_file.stat().st_size != room["decision_bytes"]:
            raise ValueError("G49 冻结官方动作审计字节数漂移")
        release = ((json.loads((audit / "manifest.json").read_text(encoding="utf-8"))
                    .get("payload") or {}).get("policy_release") or {})
        if release.get("candidate_source_sha256") != frozen["parent_source_sha256"]:
            raise ValueError("G49 房间父代源码漂移")
        accepted = atlas.source._accepted(decision_file)
        for context, raw, plan in atlas.source.screen._iter_decisions(audit):
            window = context.get("game_id"), context.get("round_no"), context.get("trigger_seq")
            if window not in g48_by_key:
                continue
            if window in seen:
                raise ValueError("G49 冻结窗口重复")
            seen.add(window)
            parent = g48_by_key[window]["parent_action"]
            if accepted.get(context.get("decision_id")) != parent:
                raise ValueError("G49 入口已接受动作改变")
            request = decision_request_from_json(raw)
            original = decision_plan_from_json(plan)
            if original.candidates[0].action_key != parent:
                raise ValueError("G49 入口父代排序改变")
            started = time.perf_counter()
            action, evidence = candidate.select(request, original)
            durations.append((time.perf_counter() - started) * 1000)
            counts["screened_windows"] += 1
            counts["reason|" + evidence["reason"]] += 1
            if evidence["reason"] in ("parent_rule_math_mismatch", "alternate_rule_math_mismatch",
                                      "duplicate_plan_action"):
                raise ValueError(f"G49 规则/计划事实异常：{window} {evidence}")
            if action is None:
                continue
            source = g48_by_key[window]
            selected = next((item for item in source["alternatives"] if item["action"] == action), None)
            if selected is None or action == parent or action == "discard:白":
                raise ValueError("G49 改选不在 G48 生产数学合法备选")
            if window in g10:
                raise ValueError("G49 新入口与 G10 旧入口重合")
            counts["changed_windows"] += 1
            counts["changed|white_count|" + str(source["white_count"])] += 1
            counts["changed|parent_seven_pairs_shanten|" + str(source["parent_seven_pairs_shanten"])] += 1
            counts["g11_same_action"] += int(g11.get(window) == action)
            counts["g30_same_action"] += int(g30.get(window) == action)
            rows.append({"room_id": room["room_id"], "game_id": window[0],
                         "round_no": window[1], "trigger_seq": window[2],
                         "parent_action": parent, "candidate_action": action,
                         "wall_remaining": source["wall_remaining"], **evidence,
                         "g11_same_action": g11.get(window) == action,
                         "g30_same_action": g30.get(window) == action})
    if seen != set(g48_by_key):
        raise ValueError(f"G49 漏读 G48 冻结窗口：{len(set(g48_by_key) - seen)}")
    durations.sort()
    result = {"schema": "g49-official-behavior/1", "outcome_blind": True,
              "parent_source_sha256": frozen["parent_source_sha256"],
              "candidate_source_sha256": sha(_project_file(_PROJECT_ROOT, HERE / "g49_natural_route_policy.py")),
              "g48_result_sha256": sha(G48), "g10_result_sha256": sha(G10),
              "g11_result_sha256": sha(G11), "g30_result_sha256": sha(G30),
              "script_sha256": sha(Path(__file__)),
              "complete_official_tables": len(complete),
              "counts": dict(sorted(counts.items())),
              "changed_complete_tables": len({row["game_id"] for row in rows}),
              "changed_rooms": len({row["room_id"] for row in rows}),
              "elapsed_ms_p50": round(durations[len(durations) // 2], 3),
              "elapsed_ms_p95": round(durations[int(len(durations) * .95)], 3),
              "elapsed_ms_p99": round(durations[int(len(durations) * .99)], 3),
              "elapsed_ms_max": round(durations[-1], 3),
              "changed": rows,
              "boundary": "结果盲官方父代单窗行为；不含改选后续轨迹、完整桌收益或线上时限证明。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "changed"},
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
