#!/usr/bin/env python3
"""G96：按冻结 G95 选窗与双分支接口扩至新 H/M 根。"""

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

import hashlib
import json
from pathlib import Path

import g95_wider_discard_same_hand_preflight as g95


HERE = Path(__file__).resolve().parent
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G96-WIDER-DISCARD-BRANCH-EXPANSION-PREREG-2026-09-28.md')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g96-wider-discard-branch-expansion-20260928/result.json')
PANEL_SEED = 2026111001
SAMPLES = tuple(f"g96-{index:02d}" for index in range(1, 9))


def sha(path: Path) -> str:
    """绑定事前计划、执行器及父代面板合同。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """新根不按结果挑选；每张桌保留首个命中窗和全部配对分支。"""
    if OUT.exists():
        raise FileExistsError("G96 证据已存在，拒绝覆盖")
    g93 = g95.g93
    contract = json.loads(g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g93.natural.stage.contract_versions_block(contract)
    rows = []
    for mix in ("H", "M"):
        for root_index in range(1, 5):
            for seat in range(4):
                plan = g93.natural.build_seat_stage_plans(
                    contract=contract, opponent=mix, root_index=root_index,
                    focal_seat=seat, panel_seed=PANEL_SEED)[0]
                captured, runtime, rules, situation, hands, outcome = g95.run_full(
                    plan, contract, versions, mix)
                row = {"mix": mix, "root_index": root_index, "focal_seat": seat,
                       "table_id": plan.table_id, "seed": plan.seed,
                       "full_parent_final_scores": list(outcome.final_scores or ())}
                if captured.world is None:
                    row["status"] = "no_window"
                    rows.append(row)
                    print(json.dumps({"mix": mix, "root": root_index, "seat": seat,
                                      "status": "no_window"}), flush=True)
                    continue
                target = captured.request.window_key
                reference = runtime["engine"].frame(captured.world).decisions[0].observation
                observation = captured.request.observation
                row.update({
                    "status": "paired", "target_window": g93.window_key_to_json(target),
                    "parent_action": captured.parent_key,
                    "alternate_action": captured.alternate_key,
                    "visible_action_facts": captured.facts,
                    "white_before": sum(tile.code == "白" for tile in observation.my_hand)
                    + int(observation.drawn_tile is not None
                          and observation.drawn_tile.code == "白"),
                })
                worlds = [("historical", captured.world)]
                for sample_key in SAMPLES:
                    world = runtime["engine"].resample_public_consistent_hidden_world(
                        captured.world, focal_seat=target.seat, sample_key=sample_key)
                    if runtime["engine"].frame(world).decisions[0].observation != reference:
                        raise ValueError("G96 重采样改变焦点玩家观察")
                    worlds.append((sample_key, world))
                pairs = []
                for sample_key, world in worlds:
                    parent = g95.run_branch(
                        world=world, captured=captured, plan=plan, contract=contract,
                        versions=versions, runtime=runtime, rules=rules,
                        situation=situation, mix=mix, forced_key=None)
                    alternate = g95.run_branch(
                        world=world, captured=captured, plan=plan, contract=contract,
                        versions=versions, runtime=runtime, rules=rules,
                        situation=situation, mix=mix,
                        forced_key=captured.alternate_key)
                    p, a = parent["settlement"], alternate["settlement"]
                    if p["scores_before"] != a["scores_before"]:
                        raise ValueError("G96 配对分支起分不同")
                    if sample_key == "historical":
                        old = hands[target.round_no - 1]
                        for field in ("round_no", "scores_before", "scores_after",
                                      "score_delta", "winner_seat", "is_draw", "fan",
                                      "details"):
                            if p[field] != old[field]:
                                raise ValueError("G96 原历史父代恒等失败：" + field)
                    pairs.append({
                        "sample_key": sample_key,
                        "parent": parent, "alternate": alternate,
                        "focal_delta_alt_minus_parent":
                            a["score_delta"][target.seat] - p["score_delta"][target.seat],
                        "parent_class": g95.classify(p, target.seat),
                        "alternate_class": g95.classify(a, target.seat),
                    })
                row["world_pairs"] = pairs
                rows.append(row)
                print(json.dumps({"mix": mix, "root": root_index, "seat": seat,
                                  "status": "paired", "round": target.round_no,
                                  "resampled_deltas": [pair["focal_delta_alt_minus_parent"]
                                                       for pair in pairs[1:]]},
                                 ensure_ascii=False), flush=True)
    result = {
        "schema": "g96-wider-discard-branch-expansion/1",
        "panel_seed": PANEL_SEED, "sample_keys": list(SAMPLES),
        "input_sha256": {"prereg": sha(PREREG), "script": sha(Path(__file__)),
                         "g95_script": sha(Path(g95.__file__)),
                         "g93_script": sha(Path(g93.__file__)),
                         "contract": sha(g93.paired.CONTRACT)},
        "rows": rows,
        "boundary": "公开状态一致样本不是历史后验；同局分支只供机制诊断，"
                    "发布仍看新根完整桌及独立确认。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"tables": len(rows),
                      "paired": sum(row["status"] == "paired" for row in rows)},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
