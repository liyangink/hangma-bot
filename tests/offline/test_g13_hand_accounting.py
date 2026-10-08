"""G13 逐单局收益拆账：完整桌终分守恒与真实模拟引擎公开导出对账。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'tests/offline'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(_project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[2] /
                       "review/freematch-deep-dive-20260925")))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[1] / "simulation")))

from g13_hand_accounting import HandAccountingEngine, summarize_hands
from hangma_bot.simulation import SimulationEngine
from _helpers import drive, make_rules, make_spec, simple_chooser


def _hand(number, before, delta, winner, fan, details):
    return {"round_no": number, "hand_id": f"h-{number}", "result_confirmed": True,
            "scores_before": before,
            "scores_after": [left + right for left, right in zip(before, delta)],
            "score_delta": delta, "winner_seat": winner,
            "is_draw": winner is None, "fan": fan, "details": details}


def test_income_components_reconcile_exactly_and_reject_corruption():
    first = _hand(1, [0, 0, 0, 0], [24, -8, -8, -8], 0, 1, ["平胡"])
    second = _hand(2, first["scores_after"], [48, -16, -16, -16], 0, 2,
                   ["平胡", "爆头"])
    third = _hand(3, second["scores_after"], [-8, 10, -1, -1], 1, 1,
                  ["平胡"])
    result = summarize_hands([first, second, third], focal_seat=0,
                             initial_scores=[0] * 4,
                             final_scores=third["scores_after"], expected_hands=3)
    assert (result["plain_self_win_delta"], result["special_self_win_delta"],
            result["other_win_delta"], result["focal_table_delta"]) == (24, 48, -8, 64)
    broken = dict(second, score_delta=[48, -15, -16, -16])
    with pytest.raises(ValueError, match="不守恒"):
        summarize_hands([first, broken, third], focal_seat=0,
                        initial_scores=[0] * 4,
                        final_scores=third["scores_after"], expected_hands=3)


def test_real_eight_hand_simulation_accounts_without_hidden_state_in_policy():
    rules = make_rules()
    engine = HandAccountingEngine(SimulationEngine(rules))
    world = drive(engine, engine.start(make_spec(rules, rounds=8, seed=42)),
                  simple_chooser(rules))
    result = summarize_hands(engine.hands, focal_seat=0, initial_scores=[0] * 4,
                             final_scores=world.scores, expected_hands=8)
    assert result["complete_hands"] == world.completed_hands == 8
    assert result["focal_table_delta"] == world.scores[0]
    assert sum(result[key] for key in ("plain_self_wins", "special_self_wins",
                                       "other_wins", "draws")) == 8
