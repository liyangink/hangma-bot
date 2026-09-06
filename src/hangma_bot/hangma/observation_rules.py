"""从依法可见事实补足当前规则状态；不读取完整世界、网络或时钟。

依据：官方指南 v18（2026-09-06）§1.2、§1.3、§2.1 及 RULES_EVIDENCE
动作链生命周期修订。官方 god 是权威
事实；本模块只补充未提供的链内飘次数、当前摸牌来源，未知保留为空。
"""

from dataclasses import replace
from typing import Optional

from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PlayerObservation, PublicEvent, RulePublicState

from .settlement import infer_piao_count
from .special_rules import is_passive_observation_event


def infer_gang_draw(observation: PlayerObservation) -> Optional[bool]:
    """判断当前本人摸牌来源；证据不足返回 None，明确非本人摸牌返回 False。

    只接受与已消费水位对齐的连续事件后缀，避免刷新后把旧杠补牌沿用
    到新的窗口。匹配本次摸牌的 gang_replenish 字段优先提供直接证据，
    不要求存在更早杠事件；未提供时才使用本人杠/摸牌相邻关系。
    """
    if observation.phase != "draw" or observation.turn_seat != observation.seat:
        return False
    if observation.drawn_tile is None:
        return None
    expected = observation.consumed_seq
    history = observation.public_history
    if expected is None or not history or history[-1].seq != expected:
        return None
    for index in range(len(history) - 1, -1, -1):
        event = history[index]
        if event.seq != expected:
            return None
        expected -= 1
        if event.kind == "tile_drawn" and event.seat == observation.seat:
            if len(event.tiles) != 1 or event.tiles[0] != observation.drawn_tile:
                return None
            if event.gang_replenish is not None:
                return event.gang_replenish
            if index == 0:
                return None
            previous = history[index - 1]
            if previous.seq != expected:
                return None
            if previous.kind == "gang":
                return previous.seat == observation.seat
            if previous.kind in ("tile_discarded", "tile_drawn") or is_passive_observation_event(previous):
                return False
            return None
        if not is_passive_observation_event(event):
            return None
    return None


def enrich_observation(observation: PlayerObservation) -> PlayerObservation:
    """补充能精确推导的可见事实，保留调用方已明确提供的事实。

    不要求整单局历史完整：连续当前链后缀足够；缺口前的片段不会拼接。
    不修改官方 god；不会为未知事实填零或 False。
    """
    piao = observation.chain_piao
    if piao is None:
        piao = infer_piao_count(
            observation.public_history, observation.seat,
            observation.rule_state.chain_count, observation.consumed_seq,
        )
    gang_draw = observation.gang_draw
    if gang_draw is None:
        gang_draw = infer_gang_draw(observation)
    return replace(observation, chain_piao=piao, gang_draw=gang_draw)


def recompute_draw_rule_state(
    base: PlayerObservation, drawn: Tile, *, replacement: Optional[bool] = False
) -> RulePublicState:
    """由摸牌前暗牌、既有爆头与补牌来源推进爆头，其余官方 god 字段保持不变。

    输入 base 必须是本次摸牌前观察，my_hand 为摸牌前实际暗牌（13−3×副露
    张），不能传摸牌后的快照。缺少正确前态抛 ValueError，让适配器恢复
    快照，不能把不完整手牌当成非爆头。链和抓打状态若可能变化须另行恢复。
    """
    from .progression import baotou_after_draw

    meld_count = len(base.melds[base.seat])
    hand = tuple(base.my_hand)
    if len(hand) != 13 - 3 * meld_count:
        raise ValueError("增量摸牌缺少完整摸牌前暗牌，须恢复权威快照")
    return replace(
        base.rule_state,
        baotou=baotou_after_draw(base.rule_state.baotou, hand, meld_count, drawn, replacement=replacement),
    )


def compare_observation_transition(
    before: PlayerObservation,
    events: tuple[PublicEvent, ...],
    after: PlayerObservation,
) -> tuple[str, ...]:
    """核对已连续接收的简单本人动作与官方新 god；不覆盖权威 after。

    输入事件必须覆盖 before.consumed_seq 之后到 after.consumed_seq 的全部
    序号，且两份观察属于同座位同单局。只检查可确定的链次数、摸牌爆头
    和摸牌事件明确声明的补牌来源；只有他家事件时本人链次数保持不变。
    不推进完整牌桌。返回 god_mismatch:<字段>:原因 或 not_checked:<字段>:原因；
    空缺的字段表示已检查且一致。抓打圈作用范围仍待官方验证，始终明确跳过。
    """
    from .progression import baotou_after_draw, chain_after_discard, chain_after_gang, recompute_baotou

    skipped_catch = "not_checked:catch_play:官方四座位作用范围尚未核实"
    def skip(reason: str) -> tuple[str, ...]:
        return ("not_checked:chain_count:" + reason, "not_checked:baotou:" + reason, skipped_catch)

    if (before.game_id, before.seat, before.round_no) != (after.game_id, after.seat, after.round_no):
        return skip("不是同场同座位同单局")
    if before.consumed_seq is None or after.consumed_seq is None:
        return skip("缺少已消费水位")
    if after.consumed_seq <= before.consumed_seq:
        return skip("没有向前连续事件区间，可能只是阶段边界变化")
    expected = before.consumed_seq + 1
    for event in events:
        if event.seq != expected:
            return skip("事件序号未完整覆盖前后观察")
        expected += 1
    if expected != after.consumed_seq + 1:
        return skip("事件序号未完整覆盖前后观察")
    allowed = {"tile_drawn", "tile_discarded", "gang", "chi", "peng", "pass", "timeout"}
    if any(event.kind not in allowed for event in events):
        return skip("存在未知或跨单局关键事件")
    if any(event.kind == "timeout" and not is_passive_observation_event(event) for event in events):
        return skip("存在自动动作或未知类别的超时，不能当作单纯响应")
    own = tuple(event for event in events if event.seat == before.seat and not is_passive_observation_event(event))
    kinds = tuple(event.kind for event in own)
    if kinds not in ((), ("tile_drawn",), ("tile_discarded",), ("chi",), ("peng",), ("gang",), ("gang", "tile_drawn")):
        return skip("本人动作组合超出已验证的简单转移")
    result = []
    count = before.rule_state.chain_count
    if kinds == ("tile_discarded",):
        if len(own[0].tiles) != 1:
            return skip("本人弃牌缺少唯一牌值")
        count, _ = chain_after_discard(count, 0, before.rule_state.baotou, own[0].tiles[0])
    elif kinds and kinds[0] == "gang":
        count, _ = chain_after_gang(count, 0)
    if count != after.rule_state.chain_count:
        result.append("god_mismatch:chain_count:本地推导={0},官方={1}".format(count, after.rule_state.chain_count))

    # 与模拟推进共用相同边界：吃碰杠继承；弃牌按弃后听牌态更新。
    if kinds in (("chi",), ("peng",), ("gang",)):
        if before.rule_state.baotou != after.rule_state.baotou:
            result.append("god_mismatch:baotou:连续吃碰杠未保留动作前状态")
        result.append(skipped_catch)
        return tuple(result)
    if kinds == ("tile_discarded",):
        meld_count = len(after.melds[after.seat])
        if len(after.my_hand) == 13 - 3 * meld_count:
            predicted = recompute_baotou(tuple(after.my_hand), meld_count, sum(t.code == "白" for t in after.my_hand))
            if predicted != after.rule_state.baotou:
                result.append("god_mismatch:baotou:弃牌后听牌态与官方不符")
        else:
            result.append("not_checked:baotou:缺少完整弃牌后暗牌")
        result.append(skipped_catch)
        return tuple(result)
    if not kinds or kinds[-1] != "tile_drawn" or after.phase != "draw" or after.turn_seat != after.seat:
        result.append("not_checked:baotou:终态不是可验证的本人摸牌窗口")
    elif after.drawn_tile is None or own[-1].tiles != (after.drawn_tile,):
        result.append("not_checked:baotou:摸牌事件与终态摸牌未对齐")
    else:
        # 实测 v17 摸牌事件已直接声明 gang_replenish，不依赖缺失的前史。
        # 只核对当前座位本次摸牌，不从他家字段推导我方补牌或抓打状态。
        source = own[-1].gang_replenish
        if source is not None and after.gang_draw is not None and source != after.gang_draw:
            result.append("god_mismatch:gang_draw:官方摸牌事件={0},观察={1}".format(source, after.gang_draw))
        meld_count = len(after.melds[after.seat])
        hand = list(after.my_hand)
        # 与既有兼容契约一致：官方手牌含摸牌，模拟手牌不含单列摸牌。
        if len(hand) == 14 - 3 * meld_count:
            try:
                hand.remove(after.drawn_tile)
            except ValueError:
                hand = []
        if len(hand) != 13 - 3 * meld_count:
            result.append("not_checked:baotou:终态缺少完整摸牌前暗牌")
        else:
            replacement = source if source is not None else (True if kinds == ("gang", "tile_drawn") else infer_gang_draw(after))
            try:
                predicted = baotou_after_draw(before.rule_state.baotou, tuple(hand), meld_count, after.drawn_tile, replacement=replacement)
            except ValueError:
                return tuple(result + ["not_checked:baotou:摸牌来源不足以确定连续状态", skipped_catch])
            if predicted != after.rule_state.baotou:
                result.append("god_mismatch:baotou:本地推导={0},官方={1}".format(predicted, after.rule_state.baotou))
    result.append(skipped_catch)
    return tuple(result)
