"""统一积分预检的同源胡结算与互斥路径特征。"""

from types import SimpleNamespace

from hangma_bot.hangma.interface import ValueCoverage
from hangma_bot.kernel.actions import Hu
from scripts.vip_p3_value_fit_probe import (
    _FEATURE_NAMES, _features, _one_draw_witness, _solve,
)


def _route(path: str | None, tile: str, capacity: int, fan: int,
           net: int):
    """一条只供特征数学测试的条件胡见证。"""

    return SimpleNamespace(
        conditions=SimpleNamespace(draw_kind="normal"),
        followup_discard=path,
        conditional_settlement=SimpleNamespace(
            fan=fan, score_delta=(net, -net, 0, 0)),
        useful_tiles=(SimpleNamespace(code=tile,
                                      remaining_estimate=capacity),),
    )


def test_alternative_followup_discards_do_not_add_public_capacities():
    candidate = SimpleNamespace(value_facts=SimpleNamespace(
        coverage=ValueCoverage.COMPLETE,
        routes=(_route(None, "1w", 3, 2, 10),
                _route(None, "2w", 2, 2, 10),
                _route("3w", "1w", 4, 4, 20)),
    ))
    assert _one_draw_witness(candidate, 0) == (1.0, .04, .04, .25, .08)


def test_current_hu_is_exact_not_regressed():
    candidate = SimpleNamespace(
        action=Hu(), value_facts=SimpleNamespace(
            immediate_settlement=SimpleNamespace(score_delta=(48, -16, -16, -16))),
    )
    features, exact = _features(candidate, SimpleNamespace(seat=0))
    assert features == (0.0,) * len(_FEATURE_NAMES)
    assert exact == 48.0


def test_small_ridge_normal_equation_solver():
    assert _solve([[2.0, 0.0], [0.0, 4.0]], [4.0, 8.0]) == (2.0, 2.0)
