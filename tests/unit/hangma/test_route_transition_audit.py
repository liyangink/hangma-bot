"""P2 条件公开事件的独立反例；故意以预期不变量断言当前缺口。"""

from hangma_bot.hangma.engine import HangmaRules, _build_context
from hangma_bot.hangma.route_transition import (
    ConditionalPhase, advance_given_other_discard, advance_given_other_draw,
    advance_given_response, apply_given_draw, project_legal_roots,
)
from hangma_bot.kernel.actions import Gang, GangKind, Pass, Peng, Tile
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.kernel.observation import PlayerObservation, PublicDiscard, RulePublicState


_CONFIG = RuleConfig("route-audit", 1, False)


def _observation(*, phase="draw", hand=None, drawn=None, last=None):
    if hand is None:
        hand = ("1w", "1w", "1w", "2w", "3w", "4w", "5w", "6w",
                "7w", "8w", "9w", "东", "南")
    return PlayerObservation(
        game_id="route-audit", seat=0, round_no=1, snapshot_seq=10,
        phase=phase, dealer_seat=0, turn_seat=0 if phase == "draw" else 1,
        responding_seats=() if phase == "draw" else (2, 3, 0),
        my_hand=tuple(Tile(code) for code in hand), drawn_tile=drawn,
        discards=((), (last.tile,) if last is not None else (), (), ()),
        melds=((), (), (), ()),
        hand_counts=(len(hand) + int(drawn is not None), 13, 13, 13),
        last_discard=last, remaining_tile_count=60, scores=(0, 0, 0, 0),
        rule_state=RulePublicState(Tile("白"), False, 0, False),
        public_history=(), chain_piao=0, gang_draw=False,
    )


def _roots(observation):
    analysis = HangmaRules(_CONFIG).analyze(observation)
    return {root.action_key: root for root in project_legal_roots(
        observation, _build_context(observation), analysis.legal_candidates,
        config=_CONFIG)}


def test_exposed_gang_losing_response_keeps_original_hand_and_chain():
    """同时鸣牌裁决被阻断时，本人没有执行杠。"""

    observation = _observation(
        phase="response_peng", last=PublicDiscard(1, Tile("1w"), 10))
    root = _roots(observation)["gang:exposed:1w"]
    result = advance_given_response(
        root, window="response_peng", discard_seat=1,
        discarded_tile=Tile("1w"), responding=(2, 3, 0),
        choices=((2, Peng(Tile("1w"))), (3, Pass()),
                 (0, Gang(Tile("1w"), GangKind.EXPOSED))),
        retained_in_river=False,
    )
    # 两家同时鸣牌按同源裁决 blocked；单家获裁决可由本人过牌根检验。
    assert result.resolution.status == "blocked"
    assert result.state.concealed == observation.my_hand
    assert result.state.chain_count == 0
    assert result.state.meld_count == 0


def test_exposed_gang_incomplete_resolution_does_not_preapply_gang():
    """有响应成员未选择时，待裁决状态必须保留原暗牌。"""

    observation = _observation(
        phase="response_peng", last=PublicDiscard(1, Tile("1w"), 10))
    root = _roots(observation)["gang:exposed:1w"]
    result = advance_given_response(
        root, window="response_peng", discard_seat=1,
        discarded_tile=Tile("1w"), responding=(2, 3, 0),
        choices=((2, Pass()), (0, Gang(Tile("1w"), GangKind.EXPOSED))),
    )
    assert result.resolution.status == "unready"
    assert result.state.phase is ConditionalPhase.RESPONSE_RESOLUTION
    assert result.state.concealed == observation.my_hand


def test_other_discard_cannot_create_fifth_physical_copy():
    """本人已持四张 1w 时，未来他座不能再公开打出 1w。"""

    observation = _observation(
        hand=("1w", "1w", "1w", "1w", "2w", "3w", "4w", "5w",
              "6w", "7w", "8w", "9w", "东"), drawn=Tile("白"))
    waiting = _roots(observation)["discard:白"].branches[0].state
    drawn = advance_given_other_draw(waiting, seat=1)
    try:
        advance_given_other_discard(drawn, seat=1, tile=Tile("1w"))
    except ValueError:
        return
    raise AssertionError("本人已持满四张的牌仍被接受为他座弃牌")


def test_other_claim_cannot_use_publicly_exhausted_tile():
    """本人三张加触发弃牌一张时，他座不可能再碰该牌。"""

    observation = _observation(
        phase="response_peng", last=PublicDiscard(1, Tile("1w"), 10))
    root = _roots(observation)["pass"]
    try:
        advance_given_response(
            root, window="response_peng", discard_seat=1,
            discarded_tile=Tile("1w"), responding=(2, 3, 0),
            choices=((2, Peng(Tile("1w"))), (3, Pass()), (0, Pass())),
            retained_in_river=False,
        )
    except ValueError:
        return
    raise AssertionError("公开已占满四张的牌仍允许他座碰")


def test_exposed_gang_cannot_draw_replacement_before_response_award():
    """提出明杠的预列成功状态不可跳过响应裁决直接摸补牌。"""

    observation = _observation(
        phase="response_peng", last=PublicDiscard(1, Tile("1w"), 10))
    tentative = _roots(observation)["gang:exposed:1w"].branches[0].state
    assert tentative.structural_only
    assert not tentative.claim_awarded
    try:
        apply_given_draw(tentative, Tile("2w"), replacement=True)
    except ValueError:
        return
    raise AssertionError("明杠尚未获裁决却允许进入杠补摸牌窗口")


def test_discard_cannot_skip_peng_window_and_start_chi_resolution():
    """普通弃牌后必须先走碰窗，随后才可能开下家的吃窗。"""

    observation = _observation(drawn=Tile("3b"))
    root = _roots(observation)["discard:3b"]
    try:
        advance_given_response(
            root, window="response_chi", discard_seat=0,
            discarded_tile=Tile("3b"), responding=(1,),
            choices=((1, Pass()),),
        )
    except ValueError:
        return
    raise AssertionError("弃牌后跳过碰窗仍被接受为吃窗裁决")
