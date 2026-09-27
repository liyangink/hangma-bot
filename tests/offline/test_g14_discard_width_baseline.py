"""G14 窄面量具：同向听、多路线保护与公开容量边界。"""

from __future__ import annotations

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                       "review/freematch-deep-dive-20260925"))

from g14_discard_width_baseline import _safe_wider, _shape


def test_wider_requires_progress_and_capacity_protection():
    parent = _shape({"standard_shanten_after": 1, "shanten_after": 1,
                     "seven_pairs_shanten_after": 2,
                     "standard_useful_tiles": [
                         {"code": "1w", "remaining_estimate": 2},
                         {"code": "2w", "remaining_estimate": 2}],
                     "useful_tiles": [{"code": "1w", "remaining_estimate": 4}]})
    wider = _shape({"standard_shanten_after": 1, "shanten_after": 1,
                    "seven_pairs_shanten_after": 2,
                    "standard_useful_tiles": [
                        {"code": "3w", "remaining_estimate": 1},
                        {"code": "4w", "remaining_estimate": 1},
                        {"code": "5w", "remaining_estimate": 2}],
                    "useful_tiles": [{"code": "3w", "remaining_estimate": 4}]})
    assert _safe_wider(parent, wider, allowed_capacity_loss=0)
    assert not _safe_wider(parent, {**wider, "seven_shanten": 3},
                           allowed_capacity_loss=0)
    assert not _safe_wider(parent, {**wider, "standard_shanten": 2},
                           allowed_capacity_loss=0)
    lower = {**wider, "standard": (2, 3), "combined": (2, 3)}
    assert not _safe_wider(parent, lower, allowed_capacity_loss=0)
    assert _safe_wider(parent, lower, allowed_capacity_loss=2)
