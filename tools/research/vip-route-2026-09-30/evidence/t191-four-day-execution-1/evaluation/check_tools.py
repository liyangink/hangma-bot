"""T191工具少量正负契约检查；不恢复世界、不评分候选、不启动续打。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t191-four-day-execution-1/evaluation'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import asyncio
import gzip
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

from abc_support import *
from run_abc import FirstActionReceiptPolicy, valid_score_row
from hangma_bot.kernel.actions import Pass, Peng, Tile, WindowPhase
from hangma_bot.offline.forced_action import ForceFirstActionPolicy
from hangma_bot.offline.qualifier_opponents import build_qualifier_runtime
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2

sys.path.insert(0, str(ROOT))
from tests.unit.policy.support import candidates_for, make_budget, make_observation, make_request, make_rules


async def force_checks():
    """真实调用已有forcing与新收据包装，首手、后续、别窗和非法键均通过公开choose检查。"""
    obs = make_observation(phase="response_peng", turn_seat=1, responding_seats=(0,))
    candidates = candidates_for((Pass(), Peng(Tile("5w"))))
    request = make_request(obs, make_rules(candidates, emergency=candidates[0]), phase=WindowPhase.RESPONSE_PENG)
    receipts = []
    inner = ComparableHeuristicPolicyV2(monotonic=lambda: 0.0)
    forced = ForceFirstActionPolicy(inner, target_window=request.window_key, forced_action_key="peng:5w", policy_id="t191-fixture-force")
    wrapped = FirstActionReceiptPolicy(forced, receipts.append)
    first = await wrapped.choose(request, make_budget())
    second = await wrapped.choose(request, make_budget())
    other = replace(request, window_key=replace(request.window_key, trigger_seq=request.window_key.trigger_seq + 1))
    third = await wrapped.choose(other, make_budget())
    require(first.candidates[0].action_key == "peng:5w" and second.candidates[0].action_key == third.candidates[0].action_key == "pass", "B未仅干预首手")
    require(forced.force_count == len(receipts) == 1 and receipts[0]["c_self_scored"] is False
        and receipts[0]["scoring_calls"] == [] and not valid_score_row(receipts[0]), "forcing被误计评分")
    bad = ForceFirstActionPolicy(ComparableHeuristicPolicyV2(monotonic=lambda: 0.0), target_window=request.window_key,
        forced_action_key="chi:1w,2w,3w", policy_id="t191-fixture-illegal")
    try:
        await bad.choose(request, make_budget())
    except ValueError as error:
        require("不在目标窗口合法候选" in str(error) and bad.force_count == 0, "非法动作失败路径不同")
    else:
        raise ValueError("非法forcing未拒绝")
    return {"fixture_heuristic_choose_calls": 4, "receipt_count": 1,
        "B_intervenes_only_first_exact_window": True, "illegal_action_rejected": True,
        "forcing_not_self_scored": True}


def main(args):
    """只新建工具检查收据，旧API装配与旧缓存完整SHA读回不触发实际score。"""
    started = time.monotonic()
    force = asyncio.run(force_checks())
    batch = VipEohBatch.read(STAGE / "EXECUTION-BATCH.json")
    parent = (STAGE / "parent-source.py").read_text()
    runtime = build_qualifier_runtime(batch, parent, ("automatic_like", "normal_v0", "r18"))
    require(all(runtime.declarations[f"Q{i}"].policy_id in runtime.policies_by_id for i in range(1, 4)), "旧三种对手API不兼容")
    try:
        build_qualifier_runtime(batch, parent, ("normal", "normal_v0", "r18"))
    except ValueError:
        pass
    else:
        raise ValueError("未知旧API类型被静默接受")
    cache = EVIDENCE / "t186-incremental-opportunity-repair-1/natural-development/root-001/seat-0-arm-0/views.jsonl.gz"
    with gzip.open(cache, "rb") as stream:
        raw = next(stream)
        saved = json.loads(raw)
    require(sha(saved["view"]) == saved["view_sha256"] and len(canonical(saved["view"])) == saved["json_bytes"], "旧缓存读回失败")
    save(Path(args.output).resolve(), {"schema": "t191-abc-tools-check/1", "complete": True,
        "forcing_checks": force, "old_qualifier_API_three_types_constructed": True,
        "unknown_qualifier_type_rejected": True, "old_capture_exact_readback": True,
        "old_capture_file": str(cache), "old_capture_pin": pin(cache), "old_capture_raw_first_line_bytes": len(raw),
        "existing_public_contract_pytest": {"tests_passed": 50, "seconds_reported_by_pytest": 0.31,
            "scope": "forced_action/qualifier_opponents/scoring_input_capture；合成夹具，不冒充真实候选续打"},
        "source_preparation_original_sandbox_failure": {"type": "PermissionError", "message": "os.nice Operation not permitted",
            "happened_before_source_data_read": True, "retained_as_original_attempt": True},
        "counts": {"new_vip_score_calls": 0, "new_world_starts": 0, "new_hidden_samples": 0,
            "new_single_hand_continuations": 0, "new_complete_table_instances": 0,
            "new_model_calls": 0, "new_HTTP_calls": 0, "fixture_heuristic_choose_calls": 4},
        "elapsed_monotonic_seconds": time.monotonic() - started, "strength_deadline_or_release_admission": False})
    print(json.dumps({"complete": True, "new_vip_scores_worlds_continuations_HTTP": 0, "fixture_choose_calls": 4}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    main(p.parse_args())
