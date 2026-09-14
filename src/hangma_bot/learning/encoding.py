"""候选结果模型首版的共享可见编码；不读取世界、标签、文件或时钟。

保留当前手牌、四家完整牌河/副露以及有界完整公开事件序列；超出
编码容量明确拒绝，绝不静默截断。座位按本人、下家、对家、上家旋转。
标识、绝对序号、墙钟和诊断文字不作为模型输入。
"""
from __future__ import annotations

from hangma_bot.hangma.interface import RuleCandidate, RuleCompleteness
from hangma_bot.kernel.actions import CANONICAL_TILE_INDEX, Chi, Discard, Gang, Hu, Pass, Peng
from hangma_bot.kernel.observation import PlayerObservation

FEATURE_VERSION = 'visible-flat-v1'
ACTION_VERSION = 'candidate-facts-v1'
ACTION_FEATURE_DIM = 159  # candidate-facts-v1 的固定候选特征维度；与版本共同校验制品。
COMPACT_FEATURE_VERSION = 'visible-counts-melds-v1'
MAX_HISTORY = 512
MAX_RIVER = 128
EVENT_KINDS = ('round_started', 'tile_drawn', 'tile_discarded', 'chi', 'peng', 'gang',
               'pass', 'timeout', 'response_peng', 'response_chi', 'turn_started',
               'round_ended', 'game_ended', 'deal', 'response_opened', 'response_closed')
MELD_KINDS = ('chi', 'peng', 'gang', 'an', 'ming', 'bu', 'concealed', 'exposed', 'added')


def compact_feature_indices() -> tuple[int, ...]:
    """从 visible-flat-v1 取 299 维可见消融特征；不作为完整观察替代品。

    保留 33 维窗口/分数/规则上下文、本人 34 种持牌计数、四家牌河
    计数和副露。明确舍弃手牌排列、牌河顺序和逐事件历史，用于检验
    大量填充历史是否妨碍小样本学习；未知值掩码仍随上下文保留。
    """
    context = 33
    hand_sequence = 15  # 14 张手牌槽与一个独立摸牌槽。
    own_counts_end = context + hand_sequence + 34
    indices = list(range(context)) + list(range(context + hand_sequence, own_counts_end))
    seat_stride = MAX_RIVER + 34 + 4 * 6
    for seat in range(4):
        start = own_counts_end + seat * seat_stride + MAX_RIVER
        indices += list(range(start, start + 34 + 4 * 6))
    return tuple(indices)


def encode_compact_observation(observation: PlayerObservation) -> tuple[float, ...]:
    """与完整编码共用准入和牌面归一化；输出版本为 visible-counts-melds-v1。"""
    full = encode_observation(observation)
    return tuple(full[i] for i in compact_feature_indices())


def _tile(tile) -> float:
    return 0.0 if tile is None else (CANONICAL_TILE_INDEX[tile.code] + 1) / 34.0


def _optional(value, scale=1.0):
    return [0.0, 0.0] if value is None else [1.0, float(value) / scale]


def _enum(value, choices):
    return 0.0 if value is None else (choices.index(value) + 1) / (len(choices) + 1) if value in choices else 1.0


def _counts(tiles):
    values = [0.0] * 34
    for tile in tiles:
        values[CANONICAL_TILE_INDEX[tile.code]] += 0.25
    return values


def _sequence(tiles, maximum):
    if len(tiles) > maximum:
        raise ValueError('可见牌序超过编码容量')
    return [_tile(t) for t in tiles] + [0.0] * (maximum - len(tiles))


def encode_observation(observation: PlayerObservation) -> tuple[float, ...]:
    """编码玩家当前合法观察；输出固定维 float，未知数值附存在掩码。

    当前单局历史全部编码；不完整历史保留 history_complete=False。
    终局事件不能作为动作时的当前单局输入，避免把标签带入模型。
    牌码序列是首版紧凑数值表示，另附多重集计数；不把牌码距离当规则。
    """
    o = observation
    if o.phase not in ('draw', 'response_peng', 'response_chi'):
        raise ValueError('只编码真实动作窗口')
    if len(o.public_history) > MAX_HISTORY:
        raise ValueError('公开历史超过编码容量，模型应显式回退')
    if any(e.kind in ('round_ended', 'game_ended') for e in o.public_history):
        raise ValueError('当前单局动作观察中含终局事件')
    relative = lambda seat: 0.0 if seat is None else ((seat - o.seat) % 4 + 1) / 4.0
    order = tuple((o.seat + i) % 4 for i in range(4))
    values = [float(o.phase == p) for p in ('draw', 'response_peng', 'response_chi')]
    values += [relative(o.dealer_seat), relative(o.turn_seat), o.round_no / 80,
               float(o.history_complete), float(bool(o.observation_issues))]
    values += [float(s in o.responding_seats) for s in order]
    values += [o.hand_counts[s] / 14 for s in order]
    values += [o.scores[s] / 100 for s in order]
    values += _optional(o.remaining_tile_count, 136)
    values += [_tile(o.rule_state.wealth_god), float(o.rule_state.baotou),
               o.rule_state.chain_count / 8, float(o.rule_state.catch_play),
               relative(o.rule_state.catch_play_owner_seat)]
    values += _optional(o.chain_piao, 4) + _optional(o.gang_draw)
    values += [relative(None if o.last_discard is None else o.last_discard.seat),
               _tile(None if o.last_discard is None else o.last_discard.tile)]
    hand = list(o.my_hand)
    # 协议有“摸牌在手牌内”和“摸牌单列”两种表示；只做表示归一化。
    if o.drawn_tile is not None and len(hand) == 14 - 3 * len(o.melds[o.seat]):
        if o.drawn_tile not in hand:
            raise ValueError('手牌与独立摸牌不一致')
        hand.reverse()
        hand.remove(o.drawn_tile)
        hand.reverse()
    values += _sequence(hand, 14) + [_tile(o.drawn_tile)]
    values += _counts(hand + ([] if o.drawn_tile is None else [o.drawn_tile]))
    for seat in order:
        values += _sequence(o.discards[seat], MAX_RIVER) + _counts(o.discards[seat])
        melds = o.melds[seat]
        if len(melds) > 4:
            raise ValueError('副露数超过编码容量')
        for meld in melds:
            values += [_enum(meld.kind, MELD_KINDS), relative(meld.from_seat)] + _sequence(meld.tiles, 4)
        values += [0.0] * (6 * (4 - len(melds)))
    previous_seq = None
    for event in o.public_history:
        values += [1.0, _enum(event.kind, EVENT_KINDS), relative(event.seat)]
        values += _sequence(event.tiles, 4)
        values += [_enum(event.detail_kind, MELD_KINDS),
                   _enum(event.response_window, ('peng', 'chi'))]
        values += _optional(event.catch_play) + _optional(event.gang_replenish)
        values += [float(previous_seq is not None and event.seq != previous_seq + 1)]
        previous_seq = event.seq
    values += [0.0] * (14 * (MAX_HISTORY - len(o.public_history)))
    return tuple(values)


def encode_candidate(candidate: RuleCandidate) -> tuple[float, ...]:
    """编码动作身份与生产规则给出的事实；不重新计算任何牌型。"""
    action = candidate.action
    families = (Discard, Chi, Peng, Gang, Hu, Pass)
    values = [float(isinstance(action, family)) for family in families]
    values += [float(isinstance(action, Gang) and action.kind.value == kind)
               for kind in ('concealed', 'exposed', 'added')]
    tiles = action.tiles if isinstance(action, Chi) else (action.tile,) if isinstance(action, (Discard, Peng, Gang)) else ()
    values += _counts(tiles)
    facts = candidate.facts
    values += [float(facts is not None), float(facts is not None and facts.completeness == RuleCompleteness.COMPLETE)]
    for name in ('shanten_after', 'standard_shanten_after', 'seven_pairs_shanten_after'):
        values += _optional(None if facts is None else getattr(facts, name), 8)
    values += [0.0 if facts is None else _enum(facts.fact_kind.value,
               ('hand_progress', 'win', 'not_applicable', 'analysis_failed')),
               0.0 if facts is None or facts.best_followup_discard is None else
               (CANONICAL_TILE_INDEX[facts.best_followup_discard] + 1) / 34,
               float(facts is not None and facts.replacement_draw_unknown)]
    for name in ('useful_tiles', 'standard_useful_tiles', 'seven_pairs_useful_tiles'):
        useful = None if facts is None else getattr(facts, name)
        counts = [0.0] * 34
        for item in useful or ():
            counts[CANONICAL_TILE_INDEX[item.code]] = item.remaining_estimate / 4
        values += [float(useful is not None)] + counts
    return tuple(values)
