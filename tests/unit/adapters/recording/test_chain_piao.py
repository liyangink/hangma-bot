"""3.6d 记录层：链内飘出白板数的**可归因**推导与落盘。

覆盖三层判据：
1. 推导：六级规则档位各自成立时的取值、档位冲突与不可归因一律记 unknown（未知不填零）；
2. 归因：每个 +1 能指到本人链动作事件序号，或由规则档位排除其他可能；
   与 ``hangma.settlement.infer_piao_count`` 的单一规则来源逐例一致（等价性，不是第二套规则）；
3. 落盘：``normalize_decision_input_payload`` 只改 observation.chain_piao 与归因块，
   不改其他字段、不改入参；记录器把它接在 DECISION_INPUT 的落盘路径上。

夹具纪律：所有观察都是**规则自洽的世界**（链动作只能来自杠组或白板弃牌），
因此"牌河无白 + 有杠组"表示杠链、"牌河有白 + 无杠组"表示飘链；
不一致的世界由档位冲突路径显式降级为未知，并有专门用例。
"""

from __future__ import annotations

import json

import pytest

from hangma_bot.adapters.recording import JsonlAuditSink
from hangma_bot.adapters.recording.chain_piao import (
    ATTRIBUTION_SCHEMA,
    CHAIN_PIAO_ATTRIBUTION_KEY,
    RUNG_CHAIN_ZERO,
    RUNG_GANG_DRAW_SINGLE,
    RUNG_HELD_FOUR,
    RUNG_NO_GANG_MELD,
    RUNG_PUBLIC_HISTORY,
    RUNG_RIVER_NO_WHITE,
    derive_chain_piao,
    has_own_unknown_action,
    normalize_decision_input_payload,
    own_melds_contain_gang,
    own_melds_contain_white,
    rule_value_for_cross_check,
)
from hangma_bot.application.contracts import AuditContext, AuditKind, AuditRecord
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicMeld, RulePublicState
from hangma_bot.kernel.serialization import observation_to_json

from .support import (
    WEALTH_CODE,
    discard_event,
    draw_event,
    gang_event,
    history,
    make_observation,
    meld,
    observation_with_river,
    timeout_event,
)


def _rule_state(chain_count: int, *, baotou: bool = True, catch_play: bool = False) -> RulePublicState:
    """显式声明平台权威链状态；财神固定为白板。"""

    return RulePublicState(
        wealth_god=Tile(WEALTH_CODE), baotou=baotou, chain_count=chain_count,
        catch_play=catch_play,
    )


def _melds(seat: int, *items: PublicMeld) -> tuple:
    """把副露放到指定座位（其余座位为空）。"""

    rows = [[], [], [], []]
    rows[seat] = list(items)
    return tuple(tuple(row) for row in rows)


def _gang(seat: int, code: str = "3w") -> PublicMeld:
    """暗杠副露：杠动作在公开副露里的形态。"""

    return meld(seat, "gang_an", [code] * 4)


def _peng(seat: int, code: str = "3w") -> PublicMeld:
    """碰副露：非杠动作。"""

    return meld(seat, "peng", [code, code, code])


def _invariants(derivation) -> dict:
    return {name: holds for name, _, holds in derivation.invariants}


# --- 1. 推导档位 ---------------------------------------------------------

def test_chain_zero_is_attributed_as_zero() -> None:
    """链次数为 0 ⇒ 飘必为 0；不需要任何历史（规则函数首分支）。"""

    derivation = derive_chain_piao(make_observation(rule_state=_rule_state(0)))
    assert derivation.piao == 0
    assert derivation.attributed is True
    # 空牌河同时命中「牌河无白」档位；两档必须一致（都是 0）。
    assert derivation.rungs == (RUNG_CHAIN_ZERO, RUNG_RIVER_NO_WHITE)
    assert derivation.reason is None
    assert set(_invariants(derivation).values()) == {True}


def test_river_without_white_attributes_zero_without_history() -> None:
    """杠链 + 本人牌河无白 ⇒ 飘 0（09-06 语料那个链窗口的形态，副露含暗杠）。"""

    observation = observation_with_river(
        1, ["发", "1b", "7w", "2w", "南", "6w", "东"], rule_state=_rule_state(1),
        consumed_seq=None, melds=_melds(1, _gang(1, "西")),
    )
    derivation = derive_chain_piao(observation)
    assert derivation.piao == 0
    assert derivation.rungs == (RUNG_RIVER_NO_WHITE,)
    assert derivation.own_river_whites == 0


def test_river_with_white_long_gang_chain_is_unknown() -> None:
    """副露有杠组、牌河有白、历史不足、链长 >1 ⇒ 无法区分杠与飘 ⇒ 未知（不是 0）。"""

    observation = observation_with_river(
        1, [WEALTH_CODE, "3b"], rule_state=_rule_state(2), consumed_seq=None,
        melds=_melds(1, _gang(1, "西")),
    )
    derivation = derive_chain_piao(observation)
    assert derivation.piao is None
    assert derivation.attributed is False
    assert derivation.rungs == ()
    assert derivation.reason and "无法" in derivation.reason


def test_public_history_witness_locates_every_increment() -> None:
    """连续历史后缀给出值，并把每个 +1 指到具体事件序号（白板弃牌 +1、杠 +0）。"""

    events = history(
        draw_event(4, 0, "9b"),
        discard_event(5, 0, WEALTH_CODE),  # 本人飘：链 +1、飘 +1
        gang_event(6, 0, "2w"),            # 本人杠：链 +1、飘不变
    )
    observation = observation_with_river(
        0, [WEALTH_CODE], rule_state=_rule_state(2), public_history=events, consumed_seq=6,
        melds=_melds(0, _gang(0, "2w")),
    )
    derivation = derive_chain_piao(observation)
    assert derivation.piao == 1
    assert derivation.rungs == (RUNG_PUBLIC_HISTORY,)
    assert derivation.attributed_seqs == (5, 6)
    assert derivation.witnessed is True
    assert derivation.reason is None
    assert _invariants(derivation)["every_increment_attributed"] is True


def test_conflicting_rungs_degrade_to_unknown() -> None:
    """两个独立档位取值不一致 ⇒ 记 unknown（不挑一个更顺眼的）。"""

    events = history(discard_event(5, 0, WEALTH_CODE))
    observation = observation_with_river(
        0, [], rule_state=_rule_state(1), public_history=events, consumed_seq=5,
    )
    derivation = derive_chain_piao(observation)
    assert derivation.piao is None
    assert "档位冲突" in (derivation.reason or "")


def test_whites_held_four_attributes_zero() -> None:
    """手留 4 张白 ⇒ 链内飘出必为 0（白板共 4 张）；本用例隔离该档位。"""

    hand = [WEALTH_CODE] * 4 + ["1w", "2w", "3w", "4w", "5w", "6w", "7w", "8w", "9w"]
    observation = observation_with_river(
        0, [WEALTH_CODE], rule_state=_rule_state(2),
        my_hand=tuple(Tile(code) for code in hand), melds=_melds(0, _gang(0, "3w")),
    )
    derivation = derive_chain_piao(observation)
    assert derivation.piao == 0
    assert derivation.rungs == (RUNG_HELD_FOUR,)
    assert derivation.whites_held == 4


def test_gang_replenish_single_chain_attributes_zero() -> None:
    """杠上补牌且链长 1 ⇒ 该链动作就是这次杠 ⇒ 飘 0（牌河有白也能归因）。"""

    observation = observation_with_river(
        0, [WEALTH_CODE], rule_state=_rule_state(1), gang_draw=True,
        melds=_melds(0, _gang(0, "3w")),
    )
    derivation = derive_chain_piao(observation)
    assert derivation.piao == 0
    assert derivation.rungs == (RUNG_GANG_DRAW_SINGLE,)


def test_gang_replenish_multi_chain_is_unknown() -> None:
    """杠上补牌但链长 >1 ⇒ 前一次链动作可能是飘，历史不足时记未知。"""

    observation = observation_with_river(
        0, [WEALTH_CODE], rule_state=_rule_state(2), gang_draw=True,
        melds=_melds(0, _gang(0, "3w")),
    )
    derivation = derive_chain_piao(observation)
    assert derivation.piao is None
    assert derivation.attributed is False


def test_no_gang_meld_attributes_all_chain_actions_as_piao() -> None:
    """本局副露无杠组 ⇒ 链动作只能是飘 ⇒ 飘数等于链次数（牌河确有白板交叉核对）。"""

    observation = observation_with_river(
        0, [WEALTH_CODE], rule_state=_rule_state(1), consumed_seq=None,
        melds=_melds(0, _peng(0, "3w")),
    )
    derivation = derive_chain_piao(observation)
    assert derivation.piao == 1
    assert derivation.rungs == (RUNG_NO_GANG_MELD,)
    assert derivation.rule_accounted is True
    assert derivation.witnessed is False


def test_all_piao_rung_violating_river_bound_is_unknown() -> None:
    """「本局无杠」推出飘数 > 牌河白板数 ⇒ 与规则矛盾 ⇒ 降级为未知。"""

    observation = observation_with_river(
        0, [WEALTH_CODE], rule_state=_rule_state(2), consumed_seq=None,
        melds=_melds(0, _peng(0, "3w")),
    )
    derivation = derive_chain_piao(observation)
    assert derivation.piao is None
    assert "不变量" in (derivation.reason or "")


def test_own_meld_with_white_is_refused() -> None:
    """本人副露出现白板 ⇒ 与「白板不可被吃碰杠」矛盾，本记录不作归因。"""

    observation = make_observation(
        melds=_melds(0, meld(0, "peng", [WEALTH_CODE] * 3)),
        rule_state=_rule_state(1),
    )
    assert own_melds_contain_white(observation) is True
    derivation = derive_chain_piao(observation)
    assert derivation.piao is None
    assert "不可被吃碰杠" in (derivation.reason or "")


# --- 2. 与规则单一来源的等价性 -------------------------------------------

@pytest.mark.parametrize(
    "events,consumed,chain_count,melds,expected",
    [
        ((), None, 0, (), 0),
        ((discard_event(1, 0, WEALTH_CODE),), 1, 1, (), 1),
        ((gang_event(1, 0, "2w"),), 1, 1, (_gang(0, "2w"),), 0),
        ((discard_event(1, 0, WEALTH_CODE), gang_event(2, 0, "2w")), 2, 2,
         (_gang(0, "2w"),), 1),
        ((discard_event(1, 0, "3w"),), 1, 1, (_peng(0, "3w"),), None),  # 链已断，历史走不通
        ((gang_event(1, 0, "2w"),), 1, 2, (_gang(0, "2w"),), None),     # 历史不足以覆盖 2 次链动作
        # timeout 的三态（返工 blocker-1：判定必须与 is_passive_observation_event 同宽）：
        #   detail_kind 缺省 / "discard" = 无法排除自动出牌 ⇒ 规则函数返回 None，第⑤档也不得命中；
        #   detail_kind="response" = 纯表态 ⇒ 两侧都必须跨过它继续反查。
        ((discard_event(1, 0, WEALTH_CODE), timeout_event(2, 0, None)), 2, 1, (),
         None),
        ((discard_event(1, 0, WEALTH_CODE), timeout_event(2, 0, "discard")), 2, 1, (),
         None),
        ((discard_event(1, 0, WEALTH_CODE), timeout_event(2, 1, None)), 2, 1, (),
         None),
        ((discard_event(1, 0, WEALTH_CODE), timeout_event(2, 0, "response"),
          gang_event(3, 0, "2w")), 3, 2, (_gang(0, "2w"),), 1),
    ],
)
def test_history_rung_matches_rule_source(events, consumed, chain_count, melds, expected) -> None:
    """第⑤档（逐事件见证）与 ``infer_piao_count`` 同口径：值必须相等，None 必须同为 None。

    ``expected is None` 时断言的是**第⑤档不命中**（``witnessed=False`、档位不在集合里），
    而不是"整条推导必须未知"——其他档位（牌面单调事实）可以独立成立，那是另一条证据链。
    """

    observation = observation_with_river(
        0, [WEALTH_CODE], rule_state=_rule_state(chain_count),
        public_history=history(*events), consumed_seq=consumed,
        melds=_melds(0, *melds),
    )
    assert rule_value_for_cross_check(observation) == expected
    derivation = derive_chain_piao(observation)
    if expected is not None:
        assert derivation.piao == expected
        assert derivation.attributed is True
    else:
        assert RUNG_PUBLIC_HISTORY not in derivation.rungs
        assert derivation.witnessed is False


def test_own_auto_action_suppresses_chain_composition_rungs() -> None:
    """评审判给的最小复现：本座非被动 timeout ⇒ 不得由链构成档位给出 piao=1。

    世界：无杠组副露、chain_count=1、牌河恰 1 张白、历史=[本座白弃牌, 本座非被动 timeout]。
    第⑤档按规则函数口径返回 None；第⑥档（无杠 ⇒ 链动作全是飘）与第④档因本座存在
    **未知牌的自动动作**（自动弃牌不落 tile_discarded 事件）而让位 ⇒ 整条推导 unknown。
    """

    assert has_own_unknown_action is not None  # 导入自检：函数在公开面上
    observation = observation_with_river(
        0, [WEALTH_CODE], rule_state=_rule_state(1), consumed_seq=2,
        public_history=history(discard_event(1, 0, WEALTH_CODE), timeout_event(2, 0, None)),
        melds=_melds(0, _peng(0, "3w")),
    )
    assert rule_value_for_cross_check(observation) is None
    derivation = derive_chain_piao(observation)
    assert derivation.piao is None
    assert derivation.attributed is False
    assert RUNG_NO_GANG_MELD not in derivation.rungs
    assert RUNG_PUBLIC_HISTORY not in derivation.rungs
    assert derivation.reason


def test_own_auto_action_does_not_suppress_board_facts() -> None:
    """牌面单调事实不受本座自动动作影响：牌河无白 ⇒ 飘必为 0（第二条独立证据链）。"""

    observation = observation_with_river(
        0, ["3w"], rule_state=_rule_state(1), consumed_seq=2,
        public_history=history(discard_event(1, 0, "3w"), timeout_event(2, 0, None)),
        melds=_melds(0, _peng(0, "3w")),
    )
    derivation = derive_chain_piao(observation)
    assert derivation.piao == 0
    assert derivation.rungs == (RUNG_RIVER_NO_WHITE,)


def test_other_seat_timeout_keeps_the_no_gang_rung() -> None:
    """**他家**非被动 timeout 与本座链无关 ⇒ 第⑥档仍成立（真实基线里 4 行非零归因属此形态）。"""

    observation = observation_with_river(
        0, [WEALTH_CODE], rule_state=_rule_state(1), consumed_seq=2,
        public_history=history(discard_event(1, 0, WEALTH_CODE), timeout_event(2, 1, None)),
        melds=_melds(0, _peng(0, "3w")),
    )
    assert rule_value_for_cross_check(observation) is None
    derivation = derive_chain_piao(observation)
    assert derivation.piao == 1
    assert derivation.rungs == (RUNG_NO_GANG_MELD,)
    assert derivation.rule_accounted is True
    assert derivation.witnessed is False


def test_rule_source_none_never_becomes_history_attribution() -> None:
    """规则函数给不出值时，**不得**由历史档位硬凑一个值（只能由其他规则档位支撑）。"""

    events = history(discard_event(1, 0, "3w"))
    observation = observation_with_river(
        0, [WEALTH_CODE], rule_state=_rule_state(1), public_history=events, consumed_seq=1,
        melds=_melds(0, _gang(0, "2w")),
    )
    assert rule_value_for_cross_check(observation) is None
    derivation = derive_chain_piao(observation)
    assert derivation.attributed is False
    assert RUNG_PUBLIC_HISTORY not in derivation.rungs


# --- 3. 落盘归一化 -------------------------------------------------------

def _payload(observation, **extra) -> dict:
    """按 DECISION_INPUT 的真实形态构造 payload（request.observation 为 codec JSON）。"""

    payload = {
        "plan_revision": 1,
        "request": {
            "codec_version": 1,
            "observation": observation_to_json(observation),
            "decision_id": "dec-1",
        },
    }
    payload.update(extra)
    return payload


def test_normalize_fills_value_and_records_attribution() -> None:
    """可归因时把 observation.chain_piao 写成推导值，并附归因块（含 live 原值与依据）。"""

    observation = observation_with_river(
        1, ["发", "1b"], rule_state=_rule_state(1), consumed_seq=None,
        melds=_melds(1, _gang(1, "西")),
    )
    payload = _payload(observation)
    before_nested = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    normalized = normalize_decision_input_payload(payload)

    assert normalized["request"]["observation"]["chain_piao"] == 0
    block = normalized[CHAIN_PIAO_ATTRIBUTION_KEY]
    assert block["schema"] == ATTRIBUTION_SCHEMA
    assert block["status"] == "attributed"
    assert block["piao"] == 0
    assert block["rungs"] == [RUNG_RIVER_NO_WHITE]
    assert block["rung_basis"][RUNG_RIVER_NO_WHITE]
    assert block["attribution_basis"] == ["zero_by_rule_rung"]
    assert block["live_value"] is None
    assert block["changed"] is True
    assert block["units"]["piao"] == "张（= 链内飘出次数）"
    # 只碰两处：其他字段与入参都不变。
    assert normalized["plan_revision"] == 1
    assert normalized["request"]["decision_id"] == "dec-1"
    assert json.dumps(payload, sort_keys=True, ensure_ascii=False) == before_nested


def test_normalize_unknown_stays_unknown_and_never_zero() -> None:
    """不可归因 ⇒ chain_piao 落盘为 null（未知），归因块给出原因。"""

    observation = observation_with_river(
        1, [WEALTH_CODE, "3b"], rule_state=_rule_state(2), consumed_seq=None,
        melds=_melds(1, _gang(1, "西")),
    )
    normalized = normalize_decision_input_payload(_payload(observation))
    assert normalized["request"]["observation"]["chain_piao"] is None
    block = normalized[CHAIN_PIAO_ATTRIBUTION_KEY]
    assert block["status"] == "unknown"
    assert block["piao"] is None
    assert block["reason"]


def test_normalize_is_idempotent() -> None:
    """二次归一化结果相同（第二次 live 值已等于推导值，changed 变 False）。"""

    observation = observation_with_river(
        1, ["发"], rule_state=_rule_state(1), consumed_seq=None,
        melds=_melds(1, _gang(1, "西")),
    )
    once = normalize_decision_input_payload(_payload(observation))
    twice = normalize_decision_input_payload(once)
    assert twice["request"]["observation"]["chain_piao"] == 0
    assert twice[CHAIN_PIAO_ATTRIBUTION_KEY]["piao"] == 0
    assert twice[CHAIN_PIAO_ATTRIBUTION_KEY]["changed"] is False


@pytest.mark.parametrize(
    "payload,status",
    [
        ({}, "not_applicable"),
        ({"request": "not-a-mapping"}, "not_applicable"),
        ({"request": {"observation": {"schema_version": 1}}}, "error"),
    ],
)
def test_normalize_tolerates_absent_or_broken_input(payload, status) -> None:
    """补全失败不改写原 payload、不抛异常，只落一条显式失败归因块。"""

    normalized = normalize_decision_input_payload(payload)
    assert normalized[CHAIN_PIAO_ATTRIBUTION_KEY]["status"] == status
    assert normalized[CHAIN_PIAO_ATTRIBUTION_KEY]["piao"] is None
    for key, value in payload.items():
        assert normalized[key] == value
    assert set(normalized) - set(payload) == {CHAIN_PIAO_ATTRIBUTION_KEY}


# --- 4. 记录器接线 -------------------------------------------------------

def _record(kind: AuditKind, payload: dict) -> AuditRecord:
    return AuditRecord(
        schema_version=1,
        kind=kind,
        context=AuditContext(
            run_id="run-1", tournament_id="t-1", participant_id="P1",
            stage_attempt_id="st-1", game_id="G1", round_no=1, trigger_seq=1,
            decision_id="dec-1", attempt_no=None,
        ),
        wall_time_unix_ms=1000, monotonic_ns=1, payload=payload,
    )


async def test_sink_writes_normalized_decision_input(tmp_path) -> None:
    """DECISION_INPUT 落盘后可以只看记录本身复核链内飘出（observation + 归因块）。"""

    observation = observation_with_river(
        1, ["发", "1b"], rule_state=_rule_state(1), consumed_seq=None,
        melds=_melds(1, _gang(1, "西")),
    )
    sink = JsonlAuditSink(tmp_path, "run-1")
    assert sink.emit(_record(AuditKind.DECISION_INPUT, _payload(observation))).queued is True
    assert sink.emit(_record(AuditKind.LIFECYCLE_CHANGED, {"status": "running"})).queued is True
    summary = await sink.aclose(timeout_seconds=5.0)
    assert summary.written == 2
    assert summary.serialization_failures == 0

    lines = (
        tmp_path / "runs" / "run-1" / "participants" / "P1" / "decisions.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    decision = next(json.loads(line) for line in lines
                    if json.loads(line)["kind"] == AuditKind.DECISION_INPUT.value)
    assert decision["payload"]["request"]["observation"]["chain_piao"] == 0
    assert decision["payload"][CHAIN_PIAO_ATTRIBUTION_KEY]["status"] == "attributed"

    lifecycles = (
        tmp_path / "runs" / "run-1" / "lifecycle.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    assert CHAIN_PIAO_ATTRIBUTION_KEY not in json.loads(lifecycles[0])["payload"]


async def test_sink_keeps_record_when_derivation_fails(tmp_path) -> None:
    """补全失败不得丢记录：坏观察仍按 error 归因块落盘。"""

    sink = JsonlAuditSink(tmp_path, "run-1")
    payload = {"request": {"observation": {"schema_version": 1}}}
    assert sink.emit(_record(AuditKind.DECISION_INPUT, payload)).queued is True
    summary = await sink.aclose(timeout_seconds=5.0)
    assert summary.written == 1
    line = (
        tmp_path / "runs" / "run-1" / "participants" / "P1" / "decisions.jsonl"
    ).read_text(encoding="utf-8").splitlines()[0]
    assert json.loads(line)["payload"][CHAIN_PIAO_ATTRIBUTION_KEY]["status"] == "error"


def test_unknown_meld_kind_blocks_the_no_gang_rung() -> None:
    """副露出现白名单外的种类 ⇒ "无杠"不成立，档位⑥ 必须 fail-closed 不归因。"""

    observation = observation_with_river(
        0, [WEALTH_CODE], rule_state=_rule_state(1), consumed_seq=None,
        melds=_melds(0, meld(0, "kong_future", ["3w"] * 4)),
    )
    derivation = derive_chain_piao(observation)
    assert derivation.piao is None
    assert RUNG_NO_GANG_MELD not in derivation.rungs


def test_own_melds_contain_gang_detects_every_gang_kind() -> None:
    """杠的三种形态（明/暗/补）都以 gang* 留在副露里，必须都被识别。"""

    for kind in ("gang", "gang_an", "gang_ming", "gang_bu"):
        observation = make_observation(melds=_melds(0, meld(0, kind, ["3w"] * 4)))
        assert own_melds_contain_gang(observation) is True
    assert own_melds_contain_gang(
        make_observation(melds=_melds(0, _peng(0, "3w")))
    ) is False
