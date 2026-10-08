"""G13 胡/继续价值筛查：结算守恒、条件容量与未知事实不混淆。"""

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

from g13_hu_continue_value_screen import _band_ratio, _choice, _route_value, _settlement


def test_immediate_settlement_requires_exact_four_seat_conservation():
    raw = {"fan": 2, "score_delta": [-2, -2, 20, -16],
           "details": ["平胡", "爆头"]}
    assert _settlement(raw, 2)["focal_delta"] == 20
    with pytest.raises(ValueError, match="不守恒"):
        _settlement({**raw, "score_delta": [-2, -2, 20, -15]}, 2)
    assert _settlement({**raw, "fan": True}, 2) is None


def test_next_draw_route_is_conditional_not_probability():
    settlement = {"fan": 4, "score_delta": [-4, -4, 40, -32],
                  "details": ["平胡", "杠开", "爆头"]}
    route = {"conditional_settlement": settlement,
             "useful_tiles": [{"code": "3w", "remaining_estimate": 2},
                              {"code": "白", "remaining_estimate": 1}],
             "conditions": {"draw_kind": "replacement"},
             "followup_discard": None}
    parsed = _route_value(route, 2)
    assert parsed["public_capacity_upper"] == 3
    assert parsed["draw_kind"] == "replacement"
    assert _route_value({**route, "useful_tiles": [
        {"code": "3w", "remaining_estimate": 2},
        {"code": "3w", "remaining_estimate": 2}]}, 2) is None
    choice = _choice({"action_key": "gang:concealed:3w", "value_facts": {
        "coverage": "complete", "routes": [route]}}, 2, 20)
    assert choice["better_than_now_hu_public_capacity_upper"] == 3
    assert choice["best_one_draw_route"]["settlement"]["focal_delta"] == 40
    assert _band_ratio(20, 40) == "required_le_half"
    assert _band_ratio(20, 20) == "one_draw_max_le_immediate"
