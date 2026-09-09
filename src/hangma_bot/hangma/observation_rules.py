"""从依法可见事实补足当前规则状态；不读取完整世界、网络或时钟。

依据：官方指南 v18（2026-09-06）§1.2、§1.3、§2.1 及 RULES_EVIDENCE
动作链生命周期修订。官方 god 是权威
事实；本模块只补充未提供的链内飘次数、当前摸牌来源，未知保留为空。
"""

from collections import Counter
from dataclasses import replace
from typing import Optional

from hangma_bot.kernel.actions import Action, Chi, Discard, Gang, GangKind, Pass, Peng, Tile
from hangma_bot.kernel.observation import PlayerObservation, PublicEvent, PublicMeld, RulePublicState

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


def reconcile_observation(
    before: PlayerObservation,
    after: PlayerObservation,
    *,
    confirmed_action: Optional[Action] = None,
) -> PlayerObservation:
    """核对前态与新快照后补足链事实；不改写官方 god、事件或历史完整性。

    confirmed_action 只能是本场本人已获官方明确成功响应的动作，不能传入
    仅已发送、拒绝或结果不确定的动作。动作必须与新快照的本人牌河、副露、
    暗牌差量和官方链计数同时一致；水位以 consumed_seq 为准，不以旧快照
    基线判断。依据 v20/2026-09-07 的成功明杠后 events=null 实测，以及
    progression 共用的飘/杠生命周期，杠保持飘次数而普通弃牌重置链。

    没有动作确认时，只在本人牌河、副露、链计数不变且暗牌未发生无法解释
    的变化时保留已知飘数。杠补来源另须证明还是同一次摸牌，不能只因牌值
    相同就沿用。任一证据不足保留未知；after 已知字段优先，冲突时不混填。
    本函数纯计算，无网络、时钟或副作用；不补造缺失事件。
    """
    after = enrich_observation(after)
    if (before.game_id, before.seat, before.round_no, before.dealer_seat) != (
        after.game_id, after.seat, after.round_no, after.dealer_seat
    ):
        return after
    if (before.consumed_seq is None or after.consumed_seq is None
            or after.consumed_seq < before.consumed_seq):
        return after
    before = enrich_observation(before)
    if confirmed_action is None or isinstance(confirmed_action, Pass):
        facts = _unchanged_chain_facts(before, after)
    else:
        # 核对失败不能退回“没有确认动作”的沿用路径；确认本身不是执行结果
        # 与任意新快照均一致的证明，尤其不能让旧杠补污染下一次摸牌。
        if after.consumed_seq <= before.consumed_seq:
            return after
        facts = _confirmed_action_facts(before, after, confirmed_action)
    if facts is None:
        return after
    piao, gang_draw = facts
    if ((after.chain_piao is not None and piao is not None and after.chain_piao != piao)
            or (after.gang_draw is not None and gang_draw is not None and after.gang_draw != gang_draw)):
        return after
    return replace(
        after,
        chain_piao=after.chain_piao if after.chain_piao is not None else piao,
        gang_draw=after.gang_draw if after.gang_draw is not None else gang_draw,
    )


def _concealed_tiles(observation: PlayerObservation) -> Optional[tuple[Tile, ...]]:
    """返回当前暗牌全集；兼容官方含摸牌与模拟单列摸牌，残缺牌数不参与证明。"""
    hand = tuple(observation.my_hand)
    waiting_count = 13 - 3 * len(observation.melds[observation.seat])
    own_draw = observation.phase == "draw" and observation.turn_seat == observation.seat
    if not own_draw:
        return hand if observation.drawn_tile is None and len(hand) == waiting_count else None
    if observation.drawn_tile is not None:
        if len(hand) == waiting_count:
            return hand + (observation.drawn_tile,)
        if len(hand) == waiting_count + 1 and observation.drawn_tile in hand:
            return hand
        return None
    # 吃碰后的出牌窗口没有摸牌，但本人已有待弃的一张；待摸暂态仍为听牌数。
    return hand if len(hand) in (waiting_count, waiting_count + 1) else None


def _without_tiles(hand: tuple[Tile, ...], removed: tuple[Tile, ...]) -> Optional[Counter]:
    counts = Counter(hand)
    counts.subtract(removed)
    return +counts if all(count >= 0 for count in counts.values()) else None


def _unchanged_chain_facts(
    before: PlayerObservation, after: PlayerObservation,
) -> Optional[tuple[Optional[int], Optional[bool]]]:
    seat = before.seat
    if (before.rule_state.chain_count != after.rule_state.chain_count
            or before.discards[seat] != after.discards[seat]
            or before.melds[seat] != after.melds[seat]):
        return None
    old_hand, new_hand = _concealed_tiles(before), _concealed_tiles(after)
    if old_hand is None or new_hand is None:
        return None
    same_hand = Counter(old_hand) == Counter(new_hand)
    if (before.consumed_seq == after.consumed_seq
            and (not same_hand or before.drawn_tile != after.drawn_tile
                 or before.discards != after.discards or before.melds != after.melds
                 or (before.remaining_tile_count is not None and after.remaining_tile_count is not None
                     and before.remaining_tile_count != after.remaining_tile_count))):
        return None
    new_draw = (before.drawn_tile is None and after.drawn_tile is not None
                and after.phase == "draw" and after.turn_seat == seat
                and Counter(new_hand) == Counter(old_hand + (after.drawn_tile,)))
    if not same_hand and not new_draw:
        return None
    gang_draw = None
    # 同水位必须同牌面；水位前进时还要全桌公开牌面、牌墙余量不变，
    # 否则即便刚摸牌码与暗牌集合碰巧相同，也无法证明不是后续一次摸牌。
    same_public_draw = (before.phase == after.phase == "draw"
                        and before.turn_seat == after.turn_seat == seat
                        and before.drawn_tile is not None
                        and before.drawn_tile == after.drawn_tile and same_hand
                        and before.discards == after.discards and before.melds == after.melds
                        and (before.consumed_seq == after.consumed_seq
                             or (before.remaining_tile_count is not None
                                 and before.remaining_tile_count == after.remaining_tile_count)))
    if same_public_draw:
        gang_draw = before.gang_draw
    return before.chain_piao, gang_draw


def _meld_matches(
    meld: PublicMeld, seat: int, kinds: tuple[str, ...],
    tiles: tuple[Tile, ...], from_seat: Optional[int],
) -> bool:
    # v20 快照有 gang_ming 等种类且可省略来源；成功动作前 last_discard
    # 提供明杠/吃碰来源。字段明确存在时必须一致，不能忽略实际矛盾。
    return (meld.seat == seat and meld.kind in kinds and Counter(meld.tiles) == Counter(tiles)
            and (meld.from_seat is None or meld.from_seat == from_seat))


def _claimed_discard(before: PlayerObservation, tiles: tuple[Tile, ...]) -> Optional[int]:
    discard = before.last_discard
    if (discard is None or discard.seat == before.seat or discard.tile not in tiles
            or before.seat not in before.responding_seats
            or before.consumed_seq is None or discard.seq > before.consumed_seq):
        return None
    return discard.seat


def _confirmed_action_facts(
    before: PlayerObservation, after: PlayerObservation, action: Action,
) -> Optional[tuple[Optional[int], Optional[bool]]]:
    from .progression import chain_after_discard, chain_after_gang

    seat = before.seat
    old_hand, new_hand = _concealed_tiles(before), _concealed_tiles(after)
    if old_hand is None or new_hand is None:
        return None
    old_melds, new_melds = before.melds[seat], after.melds[seat]
    count, piao = before.rule_state.chain_count, before.chain_piao
    if isinstance(action, Discard):
        if (before.phase != "draw" or before.turn_seat != seat
                or after.drawn_tile is not None or old_melds != new_melds
                or after.discards[seat] != before.discards[seat] + (action.tile,)
                or _without_tiles(old_hand, (action.tile,)) != Counter(new_hand)):
            return None
        expected_count, known_piao = chain_after_discard(count, piao or 0, before.rule_state.baotou, action.tile)
        if expected_count != after.rule_state.chain_count:
            return None
        # 旧飘数未知时，普通弃牌仍可确认清零；飘白则不能用占位零生成精确数。
        return (known_piao if piao is not None or expected_count == 0 else None), False
    if before.discards[seat] != after.discards[seat]:
        return None
    if isinstance(action, Gang):
        if (after.phase != "draw" or after.turn_seat != seat or after.drawn_tile is None
                or after.consumed_seq - before.consumed_seq < 2):
            return None
        expected_count, _ = chain_after_gang(count, piao or 0)
        if expected_count != after.rule_state.chain_count:
            return None
        if (before.remaining_tile_count is not None and after.remaining_tile_count is not None
                and after.remaining_tile_count != before.remaining_tile_count - 1):
            return None
        from_seat = None
        if action.kind is GangKind.EXPOSED:
            from_seat = _claimed_discard(before, (action.tile,))
            if before.phase != "response_peng" or from_seat is None:
                return None
            removed, kinds = 3, ("gang", "gang_ming")
        else:
            if before.phase != "draw" or before.turn_seat != seat:
                return None
            removed = 4 if action.kind is GangKind.CONCEALED else 1
            kinds = ("gang", "gang_an") if action.kind is GangKind.CONCEALED else ("gang", "gang_bu")
        if action.kind is GangKind.ADDED:
            indexes = [i for i, meld in enumerate(old_melds)
                       if meld.seat == seat and meld.kind == "peng" and meld.tiles == (action.tile,) * 3]
            if len(indexes) != 1 or len(new_melds) != len(old_melds):
                return None
            index = indexes[0]
            from_seat = old_melds[index].from_seat
            if (new_melds[:index] + new_melds[index + 1:] != old_melds[:index] + old_melds[index + 1:]
                    or not _meld_matches(new_melds[index], seat, kinds, (action.tile,) * 4, from_seat)):
                return None
        elif (len(new_melds) != len(old_melds) + 1 or new_melds[:-1] != old_melds
              or not _meld_matches(new_melds[-1], seat, kinds, (action.tile,) * 4, from_seat)):
            return None
        expected_hand = _without_tiles(old_hand, (action.tile,) * removed)
        if expected_hand is None:
            return None
        expected_hand.update((after.drawn_tile,))
        return (piao, True) if expected_hand == Counter(new_hand) else None
    if isinstance(action, (Chi, Peng)):
        claimed = action.tiles if isinstance(action, Chi) else (action.tile,) * 3
        source = _claimed_discard(before, claimed)
        if (source is None or before.phase != ("response_chi" if isinstance(action, Chi) else "response_peng")
                or after.phase != "draw" or after.turn_seat != seat or after.drawn_tile is not None
                or after.rule_state.chain_count != count
                or len(new_melds) != len(old_melds) + 1 or new_melds[:-1] != old_melds):
            return None
        kind = "chi" if isinstance(action, Chi) else "peng"
        if not _meld_matches(new_melds[-1], seat, (kind,), claimed, source):
            return None
        taken = list(claimed)
        taken.remove(before.last_discard.tile)
        # 吃碰不增加链次数，也没有补摸牌；精确暗牌差量排除随后的弃牌。
        return (piao, False) if _without_tiles(old_hand, tuple(taken)) == Counter(new_hand) else None
    return None


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
    空缺的字段表示已检查且一致。此入口只检查本人动作链，抓打圈当前权限
    由 catch_play.analyze_catch_play 单独解析，不在这里重复推进。
    """
    from .progression import baotou_after_draw, chain_after_discard, chain_after_gang, recompute_baotou

    skipped_catch = "not_checked:catch_play:抓打圈由独立归属解析消费权威标记"
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
