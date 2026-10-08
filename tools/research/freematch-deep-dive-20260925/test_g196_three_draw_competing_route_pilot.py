"""G196 条件路线与已核官方金例的一摸／二摸结算对账。"""

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

from g196_three_draw_competing_route_pilot import RouteSearch, _capacity_after, _drop
from test_g18_two_self_draw_joint import _rules, _target
from hangma_bot.hangma import progression
from hangma_bot.kernel.actions import Tile


def test_first_and_second_hu_match_official_observation_gold():
    """当前规则在官方 seq788 的条件胡净分与 G18 金例相同。"""

    observation, _ = _target()
    search = RouteSearch(observation, _rules(), "discard:1b")
    first_mass = 0
    for index, capacity in enumerate(search.unseen):
        if capacity == 0:
            continue
        from hangma_bot.hangma.internal_types import TILE_ORDER
        terminal = search._win(search.root, TILE_ORDER[index],
                               baotou=search.root_baotou,
                               chain=search.root_chain,
                               piao=search.root_piao, depth=1)
        first_mass += capacity * (terminal.total if terminal else 0)
    assert first_mass == 120

    draw = Tile("1w")
    waiting = _drop(search.root + (draw,), "1w")
    drawn_baotou = progression.baotou_after_draw(
        search.root_baotou, search.root, search.meld_count, draw,
        replacement=False,
    )
    chain, piao = progression.chain_after_discard(
        search.root_chain, search.root_piao, drawn_baotou, draw,
    )
    second = search._win(waiting, "2b",
                         baotou=progression.baotou_after_discard(waiting, search.meld_count),
                         chain=chain, piao=piao, depth=2)
    assert second is not None and second.total == second.depth2 == 10
    assert sum(_capacity_after(search.unseen, "1w")) == sum(search.unseen) - 1
