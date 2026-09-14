"""公开事件供牌投影：模拟事件的已公开字段不受未来暗牌影响。"""

from hangma_bot.hangma.progression import EventRecord
from hangma_bot.kernel.actions import Tile
from hangma_bot.simulation.projection import public_history_for


def test_simulation_missing_chi_tile_is_not_inferred_from_combination():
    events = (EventRecord(1, "chi", 1, None, (("tiles", ("7t", "9t", "8t")),)),)
    public = public_history_for(events, 0)[0]
    assert public.tiles == (Tile("7t"), Tile("9t"), Tile("8t"))
    assert public.claimed_tile is None


def test_simulation_draw_never_exposes_claimed_tile():
    events = (EventRecord(1, "tile_drawn", 1, Tile("9t")),)
    assert public_history_for(events, 1)[0].tiles == (Tile("9t"),)
    for seat in range(4):
        public = public_history_for(events, seat)[0]
        assert public.claimed_tile is None
        if seat != 1:
            assert public.tiles == ()
