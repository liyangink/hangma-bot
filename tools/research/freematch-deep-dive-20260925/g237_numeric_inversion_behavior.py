#!/usr/bin/env python3
"""G237：在冻结 G224 行动前观察上核合法触达、旧算子去重与压力题。"""

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

import asyncio
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import g193_early_shape_policy as g193
import g224_g223_vector_replay as g224
import g233_inversion_same_world_branch as g233
import g237_numeric_inversion_policy as candidate
import g87_post_claim_score_trace as g87
from hangma_bot.kernel.serialization import observation_from_json
from hangma_bot.policy.interface import DecisionBudget


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
PLAN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G237-NUMERIC-INVERSION-CANDIDATE-PREREG-2026-09-29.md')
SOURCE = g224.OUT / "result.json"
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g237-numeric-inversion-behavior-20260929/result.json')
BUDGET = DecisionBudget(1000, 1001, 1002)


def digest(path: Path) -> str:
    """绑定预登记、候选源码和已看行动前来源。"""
    return sha256(path.read_bytes()).hexdigest()


async def main() -> None:
    """按全部冻结根窗原身份重算，未看结果挑窗。"""
    if OUT.exists():
        raise FileExistsError("G237 行为证据已存在，拒绝覆盖")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if (source.get("schema") != "g224-g223-vector-replay-result/1"
            or source.get("probe_windows") != 2191
            or source.get("complete_tables_verified") != 128):
        raise ValueError("G237 G224 冻结来源漂移")
    parent = candidate.research_parent_factory(lambda: 0)
    rows = []
    for mix in g224.g223.MIXES:
        for root in g224.g223.ROOTS:
            for seat in g224.g223.SEATS:
                path = g224.stage_path(mix, root, seat)
                if digest(path) != source["stage_sha256"].get(path.name):
                    raise ValueError("G237 G224 阶段摘要漂移")
                stage = json.loads(path.read_text(encoding="utf-8"))
                if (stage["mix"], stage["root_index"], stage["start_seat"]) != (
                        mix, root, seat):
                    raise ValueError("G237 阶段身份漂移")
                for raw in stage["roots"]:
                    observation = observation_from_json(raw["observation"])
                    request = g87.request_for(observation)
                    plan = await parent.choose(request, BUDGET)
                    if not plan.candidates or plan.candidates[0].action_key != raw["root_action"]:
                        raise ValueError("G237 同窗父代首选漂移")
                    key, evidence = candidate.select(request, plan)
                    old, _, _ = g193.select(request, plan)
                    if key is not None and key not in {
                            item.action_key for item in request.rules.legal_candidates}:
                        raise ValueError("G237 改选不在生产合法集合")
                    if key is not None:
                        rows.append({
                            "mix": mix, "root_index": root, "start_seat": seat,
                            "game_id": observation.game_id,
                            "round_no": observation.round_no,
                            "trigger_seq": request.trigger_seq,
                            "parent_action": plan.candidates[0].action_key,
                            "candidate_action": key,
                            "g193_local_action": old,
                            "evidence": evidence,
                        })
    if not all(row["candidate_action"] != row["parent_action"] for row in rows):
        raise ValueError("G237 改选包含父代动作")
    pressure = []
    for target in g233.selected():
        if (target["mix"], target["root_index"]) not in {
                ("H", 3), ("H", 6), ("M", 1)}:
            continue
        _, raw = g233.archived_root(target)
        request = g87.request_for(observation_from_json(raw["observation"]))
        plan = await parent.choose(request, BUDGET)
        if plan.candidates[0].action_key != target["parent_action"]:
            raise ValueError("G237 压力窗父代漂移")
        action, detail = candidate.select(request, plan)
        pressure.append({
            "mix": target["mix"], "root_index": target["root_index"],
            "parent_action": target["parent_action"],
            "expected_candidate_action": (None if target["mix"] == "H" else
                                          target["representative_inversion"]["action"]),
            "candidate_action": action, "reason": detail["reason"],
        })
    if len(pressure) != 3:
        raise ValueError("G237 压力窗数量漂移")
    by_mix = {}
    for mix in g224.g223.MIXES:
        group = [row for row in rows if row["mix"] == mix]
        by_mix[mix] = {
            "changed_windows": len(group),
            "changed_roots": len({row["root_index"] for row in group}),
            "changed_tables": len({row["game_id"] for row in group}),
            "changed_hands": len({(row["game_id"], row["round_no"])
                                  for row in group}),
            "same_as_g193_local_action": sum(row["g193_local_action"] ==
                                              row["candidate_action"]
                                              for row in group),
            "shanten": dict(sorted(Counter(
                row["evidence"]["parent_standard_shanten"] for row in group
            ).items())),
        }
    gate = (all(by_mix[mix]["changed_windows"] >= 10
                and by_mix[mix]["changed_roots"] >= 4
                for mix in g224.g223.MIXES)
            and sum(row["g193_local_action"] != row["candidate_action"]
                    for row in rows) >= 20
            and all(row["candidate_action"] == row["expected_candidate_action"]
                    for row in pressure))
    payload = {
        "schema": "g237-numeric-inversion-behavior/1",
        "source_sha256": digest(SOURCE),
        "input_sha256": {str(path.relative_to(ROOT)): digest(path)
                         for path in (PLAN, Path(__file__),
                                      _project_file(_PROJECT_ROOT, HERE / "g237_numeric_inversion_policy.py"))},
        "root_windows_checked": 2191, "by_mix": by_mix,
        "old_local_selector_unique_changes": sum(
            row["g193_local_action"] != row["candidate_action"] for row in rows),
        "pressure": sorted(pressure, key=lambda row: (row["mix"], row["root_index"])),
        "behavior_gate_pass": gate,
        "changes": rows,
        "boundary": "G224 已看父代首窗的行动前行为；不估计赛事收益。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"by_mix": by_mix, "pressure": pressure,
                      "behavior_gate_pass": gate}, ensure_ascii=False,
                     sort_keys=True), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
