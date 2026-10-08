"""防止历史“摸到的白板单列却漏计”错误污染公开风险特征。"""

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

import g8_public_response_training_rows as training


def _base_observation(hand, drawn):
    return {"seat": 0, "dealer_seat": 0, "my_hand": hand,
            "drawn_tile": drawn, "discards": [[], [], [], []],
            "melds": [[], [], [], []], "remaining_tile_count": 70,
            "rule_state": {"catch_play": False}}


def _white_count(observation):
    candidate = {"facts": {"shanten_after": 1}}
    scored = {"score_trace": {"detail": {"risk_units": 0.0}}}
    return training._feature_row(observation, candidate, scored, tile="西")["white_count"]


def test_drawn_white_counted_once_when_hand_omits_drawn_tile():
    assert _white_count(_base_observation(["白"] + ["1w"] * 12, "白")) == 2


def test_drawn_white_not_double_counted_when_hand_contains_drawn_tile():
    assert _white_count(_base_observation(["白", "白"] + ["1w"] * 12, "白")) == 2
