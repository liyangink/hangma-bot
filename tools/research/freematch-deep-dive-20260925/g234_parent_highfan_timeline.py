#!/usr/bin/env python3
"""G234 事后诊断：复现两个 H 池高番反例的本人合法行动时间线。"""

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

from hashlib import sha256
import json
from pathlib import Path

import g182_full_table_branch_preflight as branch
import g223_visible_multi_action_route as g223
import g233_inversion_same_world_branch as g233
import g95_wider_discard_same_hand_preflight as g95


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g234-three-draw-route-discrimination-20260929/highfan-parent-timelines.json')
CASES = (("H", 3, "g233-08"), ("H", 6, "g233-14"))


def digest(path: Path) -> str:
    """绑定原分支窗口、当前执行器与结果。"""

    return sha256(path.read_bytes()).hexdigest()


def one(mix: str, root: int, sample: str, contract: dict, versions: dict) -> dict:
    """同世界复跑父代，核对 G233 保存结算后仅导出本人行动键。"""

    targets = g233.selected()
    selected = [(index, row) for index, row in enumerate(targets, 1)
                if (row["mix"], row["root_index"]) == (mix, root)]
    if len(selected) != 1:
        raise ValueError("G234 高番反例身份不唯一")
    index, target = selected[0]
    source_path = g233.OUT / "windows" / f"window-{index:02d}.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    matching = [row for row in source["paired_worlds"]
                if row["sample_key"] == sample]
    if len(matching) != 1:
        raise ValueError("G233 反例样本缺失")
    plan = g223.panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root,
        focal_seat=target["start_seat"], panel_seed=g223.SEED)[0]
    old_capture, old_policies = g95.CaptureWiderPolicy, g95.policies_for
    g95.CaptureWiderPolicy = lambda inner, engine: g233.CaptureExactPolicy(
        inner, engine, target)
    g95.policies_for = g233.parent_policies
    try:
        captured, runtime, rules, situation, hands, _ = g95.run_full(
            plan, contract, versions, mix)
        world = runtime["engine"].resample_public_consistent_hidden_world(
            captured.world, focal_seat=target["seat"], sample_key=sample)
        parent = branch.run_branch(
            world=world, record=captured, plan=plan, contract=contract,
            versions=versions, runtime=runtime, rules=rules,
            situation=situation, mix=mix, forced_key=None,
            prefix_hands=hands[:target["round_no"] - 1])
    finally:
        g95.CaptureWiderPolicy, g95.policies_for = old_capture, old_policies
    expected = matching[0]["parent"]
    actual_hand = {name: parent["hands"][target["round_no"] - 1][name]
                   for name in branch.SETTLEMENT_FIELDS}
    if (actual_hand != expected["target_hand"]
            or parent["final_scores"] != expected["final_scores"]
            or parent["account"] != expected["account"]):
        raise ValueError("G234 父代分支与 G233 保存结果不恒等")
    focal = [
        {"trigger_seq": key["trigger_seq"], "phase": key["phase"],
         "action_key": action}
        for key, action in parent["decisions"]
        if key["round_no"] == target["round_no"]
        and key["seat"] == target["seat"]
    ]
    return {
        "mix": mix, "root_index": root, "sample_key": sample,
        "table_id": target["table_id"], "round_no": target["round_no"],
        "parent_action": target["parent_action"],
        "first_trigger_seq": target["snapshot_seq"],
        "own_draw_windows_through_hu": sum(item["phase"] == "draw"
                                           for item in focal),
        "own_nonpass_response_actions": [item for item in focal
                                         if item["phase"] != "draw"
                                         and item["action_key"] != "pass"],
        "target_hand": actual_hand,
        "focal_actions": focal,
        "g233_window_sha256": digest(source_path),
    }


def main() -> None:
    """纯事后行动链复核，不重新选择窗口或修改 G234 判别。"""

    if OUT.exists():
        raise FileExistsError("G234 行动时间线已存在，拒绝覆盖")
    contract = json.loads(g95.g93.paired.CONTRACT.read_text(encoding="utf-8"))
    versions = g95.g93.natural.stage.contract_versions_block(contract)
    rows = [one(mix, root, sample, contract, versions)
            for mix, root, sample in CASES]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "schema": "g234-highfan-parent-timelines/1", "rows": rows,
        "source_sha256": {"script": digest(Path(__file__)),
                          "g233_manifest": digest(g233.OUT / "manifest.json"),
                          "g233_result": digest(g233.OUT / "result.json"),
                          "g182_branch": digest(Path(branch.__file__))},
        "boundary": "两条事后已知高番反例的父代真实行动链；不作为行动前特征或独立收益。",
    }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"roots": [row["root_index"] for row in rows],
                      "own_draw_windows": [row["own_draw_windows_through_hu"]
                                           for row in rows]},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
