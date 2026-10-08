"""回归：模拟器的摸牌可另存于 drawn_tile，双白筛查必须补全暗手。"""

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

import json

import g8_two_white_natural_probe as probe
from hangma_bot.policy.action_value_seeds import ActionValueScorer


def test_drawn_white_counts_for_natural_entry() -> None:
    """用固定自然桌的真实请求重现旧版漏掉第二张白板的问题。"""

    source = next(row for row in probe.sources()
                  if row["mix"] == "H" and row["root_index"] == 2 and row["focal_seat"] == 0)
    contract = json.loads(probe.p85.CONTRACT.read_text(encoding="utf-8"))
    plans = probe.p85.natural.build_seat_stage_plans(
        contract=contract, opponent="H", root_index=2, focal_seat=0,
        panel_seed=probe.PANEL_SEED)
    requests = []
    parent = probe.p85.parent_source()
    stage = probe.p85.natural.run_arm_stage(
        arm="candidate", plans=plans,
        candidate_scorer=ActionValueScorer("g8p76-trajectory-" + source["source_id"], parent),
        opponent_policies=contract["panel"]["opponent_scenarios"]["H"]["opponent_policies"],
        versions_block=probe.p85.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]), value_limits=probe.p85.LIMITS,
        decision_observer=requests.append)
    assert stage["status"] == "complete"
    target = next(request for request in requests
                  if request.observation.game_id == "sitin-stage:np-H-2026102709-r02-s0-t1"
                  and request.trigger_seq == 1355)
    assert sum(tile.code == "白" for tile in target.observation.my_hand) == 1
    assert target.observation.drawn_tile.code == "白"
    row, status = probe._candidate(
        target, source, ActionValueScorer("g8p76-repro", parent))
    assert status == "eligible"
    assert row is not None and row["features"]["white_count"] == 2
