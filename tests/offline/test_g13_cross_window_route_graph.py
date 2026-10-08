"""G13 路线图谱：未知事实不晋级，暗牌链路只在机械一致时成立。"""

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

from collections import Counter
from pathlib import Path
import sys


sys.path.insert(0, str(_project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[2] /
                       "review/freematch-deep-dive-20260925")))

from g13_cross_window_route_graph import _hand_projection, _markers, _matched


def _route(*, standard=None, combined=None, seven=None, support=None,
           baotou_after=None):
    return {"standard": standard, "combined": combined, "seven": seven,
            "standard_support": support, "baotou_after": baotou_after}


def test_unknown_route_does_not_masquerade_as_improvement():
    parent = _route(standard=1, combined=0, seven=1, support=(8, 2),
                    baotou_after=False)
    unknown = _route(standard=None, combined=0, seven=None, support=None,
                     baotou_after=None)
    assert _markers("discard:西", "discard:4w", parent, unknown,
                    current_baotou=False) == []
    broad = _route(standard=1, combined=0, seven=2, support=(8, 3),
                   baotou_after=False)
    # 宽面标签只是观察性机会，不能偷换成七对也受保护的安全动作。
    assert _markers("discard:西", "discard:4w", parent, broad,
                    current_baotou=False) == ["discard_broader_standard"]
    boom = _route(standard=1, combined=0, seven=1, support=(8, 2),
                  baotou_after=True)
    assert _markers("discard:西", "discard:4w", parent, boom,
                    current_baotou=False) == ["enter_baotou"]


def test_normal_draw_and_response_pass_link_only_same_concealed_hand():
    hand = ["1w", "1w", "2w", "2w", "3w", "3w", "4w", "4w", "5w",
            "5w", "6w", "6w", "白", "东"]
    before, after = _hand_projection({"my_hand": hand, "drawn_tile": "东"},
                                     "draw", "discard:东", 0)
    assert before == after == Counter(hand[:-1])
    response_before, response_after = _hand_projection(
        {"my_hand": hand[:-1]}, "response_chi", "pass", 0)
    assert response_before == response_after == after
    draw = {"own_melds": 0, "_after": after}
    response = {"own_melds": 0, "_before": response_before}
    assert _matched(draw, response)
    assert not _matched(draw, {"own_melds": 1, "_before": response_before})
    assert not _matched({"own_melds": 0, "_after": None}, response)
