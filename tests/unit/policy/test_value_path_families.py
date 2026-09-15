"""价值族①② 的 potential-based 契约测试（划分设计 §6 的自动验收项）。

设计 §6 明写：「自动验收项：**沿任意闭环求和是否为 0**（Ng §3 的环判据）。
这可以直接做成评分器的契约测试。」本文件就是那条契约，另加四类性质：

  P1 势差形状：term 只由"动作前后的状态"决定，不由动作标签决定；
  P2 环判据：沿任意闭环求和为 0；
  P3 分层修正：吃碰本身不改动作链，故不受罚（M4 把吃碰当纯机会成本，此处纠正）；
  P4 不猜：事实缺失时返回 0，且空与 0 必须区分。
"""

from dataclasses import replace

import pytest

from hangma_bot.hangma.interface import CandidateFactKind, CandidateFacts, RuleCandidate
from hangma_bot.kernel.actions import (
    Chi,
    Discard,
    Gang,
    GangKind,
    Hu,
    Pass,
    Peng,
    Tile,
    action_key,
)
from hangma_bot.policy.evaluation_v1 import build_context
from hangma_bot.policy.heuristics import chain_path_value as chain
from hangma_bot.policy.heuristics import seven_pairs_path_value as pairs

from .support import WEALTH_CODE, make_observation

SCALE = 40.0
PARAMS = chain.ChainPathParams(scale=SCALE)


def _ctx(**overrides):
    """从最小观察构造上下文；只覆盖链状态字段，其余保持真实构建结果。"""

    return replace(build_context(make_observation()), **overrides)


def _cand(action, facts=None) -> RuleCandidate:
    return RuleCandidate(action=action, action_key=action_key(action), evidence=(),
                         facts=facts)


WEALTH = Tile(WEALTH_CODE)
OTHER = Tile("1w")
GANG = Gang(Tile("2b"), GangKind.EXPOSED)


# --- 价值族②：链路径价值 -----------------------------------------------

def test_gang_advances_the_chain_by_one_step() -> None:
    """杠（任意种类）每个动作 ×2 ⇒ log2 +1，链前进一步。"""

    for kind in GangKind:
        term = chain.path_term(_cand(Gang(Tile("2b"), kind)), _ctx(), PARAMS)
        assert term == pytest.approx(SCALE)


def test_piao_advances_the_chain_by_one_step() -> None:
    """爆头态打出财神 = 飘（官方 §8）⇒ 链 +1。"""

    ctx = _ctx(baotou=True, chain_count=0, chain_piao=0)
    assert chain.path_term(_cand(Discard(WEALTH)), ctx, PARAMS) == pytest.approx(SCALE)


def test_non_baotou_wealth_discard_breaks_the_chain() -> None:
    """非爆头态打白板不是飘，且会断链（官方第 57 行明文）。"""

    ctx = _ctx(baotou=False, chain_count=2, chain_piao=0)
    term = chain.path_term(_cand(Discard(WEALTH)), ctx, PARAMS)
    assert term == pytest.approx(-2 * SCALE)


def test_normal_discard_breaks_the_chain_only_when_it_is_nonzero() -> None:
    """打出非飘非杠的牌 → 链断重新计数；链本来就是 0 时无损失。"""

    assert chain.path_term(_cand(Discard(OTHER)), _ctx(chain_count=0), PARAMS) == 0.0
    assert chain.path_term(
        _cand(Discard(OTHER)), _ctx(chain_count=3), PARAMS) == pytest.approx(-3 * SCALE)


@pytest.mark.parametrize("action", [
    Chi((Tile("1w"), Tile("2w"), Tile("3w"))),
    Peng(Tile("1w")),
    Pass(),
])
def test_claim_actions_do_not_touch_the_chain(action) -> None:
    """**P3 分层修正**：吃/碰/过不改动作链，故本项恒为 0。

    M4 把"过牌那边的等待牌效"只加给吃碰候选（按动作标签扣分）；官方明文允许
    "圈内吃碰后再打财神 = 财飘链 +1"，因此吃碰是否是链投资属状态问题，
    不能无条件按动作类别扣分。
    """

    for chain_count in (0, 2, 5):
        assert chain.path_term(_cand(action), _ctx(chain_count=chain_count), PARAMS) == 0.0


def test_win_action_is_zero_by_documented_convention() -> None:
    """胡牌返回 0（链在胡牌时兑现，不是断链）；见模块 docstring 的偏离说明。"""

    assert chain.path_term(_cand(Hu()), _ctx(chain_count=4, baotou=True), PARAMS) == 0.0


@pytest.mark.parametrize("steps", [1, 2, 3, 6])
def test_cycle_criterion_sums_to_zero(steps: int) -> None:
    """**P2 环判据**（Ng §3）：链 0 → 连续杠 → 普通弃牌断链，闭环求和必须为 0。"""

    break_term = chain.path_term(_cand(Discard(OTHER)),
                                 _ctx(chain_count=steps), PARAMS)
    total = sum(
        chain.path_term(_cand(GANG), _ctx(chain_count=index), PARAMS)
        for index in range(steps)
    ) + break_term
    assert total == pytest.approx(0.0, abs=1e-9)


def test_term_is_the_difference_of_one_state_potential() -> None:
    """**P1 势差形状**：term 必须等于 scale×(链次数增量)，与动作标签无关。"""

    def phi(chain_count: int) -> float:
        return SCALE * chain.CHAIN_STEP_LOG2 * chain_count

    cases = [
        (_cand(GANG), _ctx(chain_count=2)),
        (_cand(Discard(WEALTH)), _ctx(chain_count=1, baotou=True)),
        (_cand(Discard(WEALTH)), _ctx(chain_count=1, baotou=False)),
        (_cand(Discard(OTHER)), _ctx(chain_count=5)),
    ]
    for candidate, ctx in cases:
        after = chain.chain_count_after(ctx, candidate.action)
        assert chain.path_term(candidate, ctx, PARAMS) == pytest.approx(
            phi(after) - phi(ctx.chain_count), abs=1e-6)


def test_same_state_gives_the_same_number_for_the_same_action_family() -> None:
    """同状态内"加多少"只由状态变化决定：两个不同杠种给出同一个数。"""

    ctx = _ctx(chain_count=3)
    terms = [
        chain.path_term(_cand(Gang(Tile("1w"), kind)), ctx, PARAMS)
        for kind in GangKind
    ]
    assert len(set(terms)) == 1          # 三个杠种给出同一个数
    assert terms[0] == pytest.approx(SCALE)


def test_scale_zero_disables_the_family() -> None:
    """scale=0 ⇒ 恒 0，用于"关闭本族但保留装载"的消融。"""

    zero = chain.ChainPathParams(scale=0.0)
    ctx = _ctx(chain_count=4, baotou=True)
    assert chain.path_term(_cand(GANG), ctx, zero) == 0.0
    assert chain.path_term(_cand(Discard(OTHER)), ctx, zero) == 0.0


def test_max_rule_chain_stays_within_the_declared_bound() -> None:
    """官方链计数上界 6 ⇒ 最大幅度 6×scale，必须不超过声明上限（否则会被钳制）。"""

    ctx = _ctx(chain_count=chain.MAX_CHAIN_COUNT)
    term = chain.path_term(_cand(Discard(OTHER)), ctx, PARAMS)
    assert abs(term) <= PARAMS.bound
    assert term == pytest.approx(-chain.MAX_CHAIN_COUNT * SCALE)


def test_chain_piao_is_not_consumed_by_this_family() -> None:
    """**P4 不猜**：本族只用链次数；链内飘次数未知不得改变结果。"""

    known = _ctx(chain_count=2, baotou=True, chain_piao=2)
    unknown = _ctx(chain_count=2, baotou=True, chain_piao=None)
    for action in (GANG, Discard(WEALTH), Discard(OTHER)):
        assert (chain.path_term(_cand(action), known, PARAMS)
                == chain.path_term(_cand(action), unknown, PARAMS))


def test_scope_covers_every_action_kind() -> None:
    """作用面必须是全部动作类别；用动作类别卡会把状态势退化成动作标签加分。"""

    assert set(PARAMS.scope) == {"chi", "peng", "gang", "discard", "pass", "hu"}


def test_unknown_parameter_key_is_rejected() -> None:
    with pytest.raises(ValueError):
        chain.build_adjustment_from_params({"scal": 1.0})


def test_declaration_parameters_round_trip() -> None:
    adjustment = chain.build_adjustment_from_params({"scale": 12.5})
    assert "scale=12.5" in adjustment.identity()
    assert "chain-path-value-v1" in adjustment.identity()


# --- 价值族①：七对路径保护（此前只有门禁验证，此处补契约测试） -------------

def _progress_facts(seven, standard, shanten=1):
    return CandidateFacts(
        CandidateFactKind.HAND_PROGRESS, shanten,
        standard_shanten_after=standard, seven_pairs_shanten_after=seven)


def test_seven_pairs_path_is_closed_by_a_meld() -> None:
    """官方《1.2》明文「七对子：禁止吃碰明杠暗杠」⇒ 副露把该路径永久关闭。"""

    before = _cand(Pass(), _progress_facts(seven=1, standard=2))
    after = _cand(Peng(Tile("1w")), _progress_facts(seven=None, standard=1))
    term = pairs.path_term(after, before, pairs.SevenPairsPathParams())
    # 七对 ×2 = log2 1，且七对本来更近 ⇒ 再计 closer_bonus 1.0
    assert term == pytest.approx(-2.0)


def test_seven_pairs_path_survives_when_facts_say_so() -> None:
    before = _cand(Pass(), _progress_facts(seven=1, standard=2))
    after = _cand(Pass(), _progress_facts(seven=1, standard=2))
    assert pairs.path_term(after, before, pairs.SevenPairsPathParams()) == 0.0


def test_seven_pairs_term_does_not_guess_without_facts() -> None:
    """事实缺失 ⇒ 0，不推断"路径没了"。"""

    before = _cand(Pass(), _progress_facts(seven=1, standard=2))
    after = _cand(Peng(Tile("1w")), None)
    assert pairs.path_term(after, before, pairs.SevenPairsPathParams()) == 0.0
    assert pairs.path_term(before, before, pairs.SevenPairsPathParams()) == 0.0
