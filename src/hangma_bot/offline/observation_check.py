"""离线比较两份已对齐的玩家观察；不读取网络，不进入线上决策。

参考观察必须由独立依据构造，例如同边界官方快照的人工核对记录。
两次调用同一解析器得到相同结果只能验证一致性，不能证明官方协议正确。
"""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Literal, Tuple

from hangma_bot.kernel.observation import PlayerObservation

CheckStatus = Literal["passed", "failed", "not_checked"]


@dataclass(frozen=True)
class ObservationDifference:
    """一项可见事实差异；字段路径用于定位，不包含隐藏世界或原始报文。"""

    path: str  # 观察字段路径；事件按官方 seq 定位
    actual: object  # 本地观察的值，仅为 PlayerObservation 可见字段
    reference: object  # 独立参考的期望值；缺少元素时为空


@dataclass(frozen=True)
class ObservationCheckReport:
    """状态和历史分别核验；任何未核验项都不能被总体 passed 掩盖。"""

    status: CheckStatus
    state_status: CheckStatus
    history_status: CheckStatus
    differences: Tuple[ObservationDifference, ...]
    not_checked_fields: Tuple[str, ...]  # 未知字段、缺史或未经调用方确认对齐的原因
    boundary_differences: Tuple[ObservationDifference, ...]  # 边界不一致时禁止状态对拍


def _differences(path: str, actual: object, reference: object) -> list[ObservationDifference]:
    """递归定位结构差异；不改变牌序，因为最右弃牌依赖顺序。"""
    if actual == reference:
        return []
    if type(actual) is type(reference) and is_dataclass(actual):
        result = []
        for item in fields(actual):
            result.extend(_differences(path + "." + item.name, getattr(actual, item.name), getattr(reference, item.name)))
        return result
    if isinstance(actual, tuple) and isinstance(reference, tuple) and len(actual) == len(reference):
        result = []
        for index, (left, right) in enumerate(zip(actual, reference)):
            result.extend(_differences("{}[{}]".format(path, index), left, right))
        return result
    return [ObservationDifference(path, actual, reference)]


def _comparison_hand(observation: PlayerObservation) -> tuple:
    """只为比较统一为摸牌前暗牌序列，不改观察或把同牌副本全部删除。

    仅在本人摸牌阶段，暗牌数量和 hand_counts 同时证明 my_hand 已含
    drawn_tile 时移除最后一个匹配副本。其余牌相对顺序完全保留；不能
    确定格式时原样比较，不靠排序掩盖真实手牌顺序或数量变化。
    """
    hand = observation.my_hand
    expected = 14 - 3 * len(observation.melds[observation.seat])
    if (observation.phase == "draw" and observation.turn_seat == observation.seat
            and observation.drawn_tile is not None and len(hand) == expected
            and observation.hand_counts[observation.seat] == expected
            and observation.drawn_tile in hand):
        index = len(hand) - 1 - hand[::-1].index(observation.drawn_tile)
        return hand[:index] + hand[index + 1:]
    return hand


def compare_observations(
    actual: PlayerObservation,
    reference: PlayerObservation,
    *,
    boundary_verified: bool = False,
) -> ObservationCheckReport:
    """比较同一座位、同一观察边界的可见事实，返回结构差异且无副作用。

    ``boundary_verified`` 必须由调用方依据取证关系显式确认。相同 seq、
    phase、最近弃牌及摸牌标记只是必要条件：这些字段不能独立证明两个
    报文属于同一时点。未确认或边界不同返回 not_checked，不误报规则错。
    官方快照基线 snapshot_seq 可以不同，以 consumed_seq 对齐已消费水位。
    缺历史、未知链内飘数/杠补牌、缺可见牌墙数不会因两边都是空而通过。
    my_hand 的含/不含 drawn_tile 兼容形态在数量可证明时统一后比较；不排序。
    """
    if not isinstance(actual, PlayerObservation) or not isinstance(reference, PlayerObservation):
        raise TypeError("对拍输入必须是两份 PlayerObservation")
    boundary = []
    for name in ("game_id", "seat", "round_no", "phase", "consumed_seq", "last_discard", "drawn_tile"):
        boundary.extend(_differences("boundary." + name, getattr(actual, name), getattr(reference, name)))
    unchecked = []
    if not boundary_verified:
        unchecked.append("boundary_not_verified")
    if actual.consumed_seq is None or reference.consumed_seq is None:
        unchecked.append("consumed_seq_unknown")
    if boundary:
        unchecked.append("boundary_mismatch")
    if unchecked:
        return ObservationCheckReport("not_checked", "not_checked", "not_checked", (), tuple(unchecked), tuple(boundary))

    state_differences = []
    state_unchecked = []
    for name in (
        "dealer_seat", "turn_seat", "responding_seats", "my_hand", "drawn_tile",
        "discards", "melds", "hand_counts", "last_discard", "remaining_tile_count",
        "scores", "rule_state", "chain_piao", "gang_draw",
    ):
        left, right = getattr(actual, name), getattr(reference, name)
        if name == "my_hand" and len(left) != len(right):
            left, right = _comparison_hand(actual), _comparison_hand(reference)
        if name in ("remaining_tile_count", "chain_piao", "gang_draw") and (left is None or right is None):
            state_unchecked.append(name)
        else:
            state_differences.extend(_differences(name, left, right))
    # 观察自身报告的未核对信息不能被同值对拍洗成 COMPLETE。
    if actual.observation_issues:
        state_unchecked.append("actual.observation_issues")
    if reference.observation_issues:
        state_unchecked.append("reference.observation_issues")
    state_status: CheckStatus = "failed" if state_differences else "not_checked" if state_unchecked else "passed"

    history_differences = []
    history_unchecked = []
    if not actual.history_complete:
        history_unchecked.append("actual.history_complete")
    if not reference.history_complete:
        history_unchecked.append("reference.history_complete")
    left_events = {item.seq: item for item in actual.public_history}
    right_events = {item.seq: item for item in reference.public_history}
    for source, observation, indexed in (("actual", actual, left_events), ("reference", reference, right_events)):
        seqs = tuple(item.seq for item in observation.public_history)
        if len(indexed) != len(seqs) or tuple(sorted(seqs)) != seqs:
            history_differences.append(ObservationDifference("public_history." + source + ".sequence", seqs, "strictly_increasing"))
        if any(seq > observation.consumed_seq for seq in seqs):
            history_differences.append(ObservationDifference("public_history." + source + ".watermark", seqs, observation.consumed_seq))
    for seq, expected in right_events.items():
        history_differences.extend(_differences("public_history[seq={}]".format(seq), left_events.get(seq), expected))
    # 参考可能仅保留部分历史；本地多保存的公开事件不因此算错。
    if reference.history_complete:
        for seq, observed in left_events.items():
            if seq not in right_events:
                history_differences.append(ObservationDifference("public_history[seq={}]".format(seq), observed, None))
    history_status: CheckStatus = "failed" if history_differences else "not_checked" if history_unchecked else "passed"
    status: CheckStatus = "failed" if "failed" in (state_status, history_status) else "not_checked" if "not_checked" in (state_status, history_status) else "passed"
    return ObservationCheckReport(status, state_status, history_status, tuple(state_differences + history_differences), tuple(state_unchecked + history_unchecked), ())
