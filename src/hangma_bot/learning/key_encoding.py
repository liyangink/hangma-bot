"""起手与关键决策的共享可见编码；条件分值是规则见证，不是期望积分。

不生成合法动作、向听、爆头或结算。只聚合已有 CandidateFacts /
CandidateValueFacts，未知和局部覆盖保留掩码；完整世界、教师选择与终局
标签均不是函数参数。旧 299/159 维编码保持原样。
"""
from __future__ import annotations

from collections import defaultdict

from hangma_bot.hangma.interface import RuleAnalysis, RuleCandidate, RuleCompleteness, ValueCoverage
from hangma_bot.kernel.actions import CANONICAL_TILE_INDEX, Discard, Gang, Hu, Peng
from hangma_bot.kernel.observation import PlayerObservation
from .encoding import encode_compact_observation, encode_candidate

KEY_FEATURE_VERSION = 'visible-counts-current-draw-v2'
KEY_ACTION_VERSION = 'candidate-visible-relations-conditional-value-v2'
KEY_TAG_VERSION = 'visible-key-decision-tags-v1'
KEY_STATE_DIM = 334
RELATION_NAMES = ('tile_present', 'tile_own_count_4', 'tile_my_river_count_4',
    'tile_next_river_count_4', 'tile_across_river_count_4', 'tile_previous_river_count_4',
    'near_next_meld', 'near_dealer_meld', 'white_after_direct_discard_4',
    'effective_total_136', 'standard_effective_total_136', 'seven_pairs_effective_total_136')
VALUE_NAMES = ('present', 'complete', 'partial', 'unavailable', 'immediate_present',
    'immediate_own_points_100', 'route_present', 'route_min_own_points_100',
    'route_max_own_points_100', 'max_same_followup_unseen_136', 'any_baotou_route',
    'max_chain_count_8', 'max_chain_piao_4')
KEY_ACTION_DIM = 159 + len(RELATION_NAMES) + len(VALUE_NAMES)
TAG_PRIORITY = ('legal_hu', 'gang_choice', 'draw_white', 'draw_fourth',
                'tenpai_candidate', 'response_choice', 'opening_discards', 'holding_white', 'draw_pair')


def visible_hand_counts(observation: PlayerObservation) -> tuple[int, ...]:
    """复用已归一化的共享编码，还原当前本人 34 种暗牌计数（含当前摸牌）。"""
    return tuple(round(x * 4) for x in encode_compact_observation(observation)[33:67])


def key_window_tags(observation: PlayerObservation, analysis: RuleAnalysis) -> tuple[str, ...]:
    """当前可见条件的多标签，按固定优先级排列；不看结局决定重要性。

    opening_discards 仅指本人已记录弃牌少于三次，不宣称就是起手发牌。
    tenpai_candidate 指存在规则零向听候选，不冒称本次才进入听牌。
    成对/第四张是当前摸牌后的机械计数，不保证该进张值得保留或杠。
    """
    if (analysis.completeness != RuleCompleteness.COMPLETE
            or observation.observation_issues or not 2 <= len(analysis.legal_candidates) <= 128):
        return ()
    counts = visible_hand_counts(observation)
    candidates = analysis.legal_candidates
    drawn = observation.drawn_tile
    tags = set()
    if any(isinstance(c.action, Hu) for c in candidates): tags.add('legal_hu')
    if any(isinstance(c.action, Gang) for c in candidates): tags.add('gang_choice')
    if drawn is not None:
        if drawn == observation.rule_state.wealth_god: tags.add('draw_white')
        if counts[CANONICAL_TILE_INDEX[drawn.code]] == 2: tags.add('draw_pair')
        if counts[CANONICAL_TILE_INDEX[drawn.code]] == 4: tags.add('draw_fourth')
    if any(c.facts is not None and c.facts.shanten_after == 0 for c in candidates):
        tags.add('tenpai_candidate')
    if observation.phase in ('response_chi', 'response_peng'): tags.add('response_choice')
    if len(observation.discards[observation.seat]) < 3: tags.add('opening_discards')
    if counts[CANONICAL_TILE_INDEX[observation.rule_state.wealth_god.code]]: tags.add('holding_white')
    return tuple(t for t in TAG_PRIORITY if t in tags)


def encode_key_observation(observation: PlayerObservation) -> tuple[float, ...]:
    """334 维：原可见 299 维、当前摸牌存在掩码、规范牌序 34 维 one-hot。

    无当前摸牌时 35 维全零；原始身份/绝对序号不进入输入。显式摸牌
    身份帮助关联进张，不表示原持牌计数无法反映结构变化。
    """
    drawn = [0.] * 34
    if observation.drawn_tile is not None:
        drawn[CANONICAL_TILE_INDEX[observation.drawn_tile.code]] = 1.
    return encode_compact_observation(observation) + (float(observation.drawn_tile is not None),) + tuple(drawn)


def conditional_value_features(observation: PlayerObservation, candidate: RuleCandidate) -> tuple[float, ...]:
    """13 维条件见证摘要；分数为本人净积分/100，未见张数/136。

    不同 followup_discard/摸前状态不能相加；同组进张必须互斥。
    最大分、最大未见数分别是摘要，不能解释为同一路线的联合承诺。
    PARTIAL 的正见证可保留，但完整性掩码明确禁止把它当全部机会。
    """
    facts = candidate.value_facts
    if facts is None:
        return (0., 0., 0., 1.) + (0.,) * 9
    immediate = facts.immediate_settlement
    values = [1., float(facts.coverage == ValueCoverage.COMPLETE),
              float(facts.coverage == ValueCoverage.PARTIAL), float(facts.coverage == ValueCoverage.UNAVAILABLE),
              float(immediate is not None), 0. if immediate is None else immediate.score_delta[observation.seat]/100.]
    if not facts.routes:
        return tuple(values) + (0.,) * 7
    groups = defaultdict(dict)
    for route in facts.routes:
        group = groups[(route.followup_discard, route.conditions)]
        for tile in route.useful_tiles:
            if tile.code in group:
                raise ValueError('同一条件路线重复计算进张')
            group[tile.code] = tile.remaining_estimate
    scores = [r.conditional_settlement.score_delta[observation.seat] for r in facts.routes]
    return tuple(values + [1., min(scores)/100., max(scores)/100.,
        max(sum(g.values()) for g in groups.values())/136., float(any(r.conditions.baotou for r in facts.routes)),
        max(r.conditions.chain_count for r in facts.routes)/8., max(r.conditions.chain_piao for r in facts.routes)/4.])


def encode_key_candidate(observation: PlayerObservation, candidate: RuleCandidate) -> tuple[float, ...]:
    """184 维：原候选159维、12维候选相关公开事实、13维条件分值。

    牌河出现次数只是公开记录计数，不是物理剩余张数或安全概率。
    接近副露仅表示同花色序数距离不超过二，不判断吃牌是否合法。
    白板数只扣本次直接弃白，不预先扣吃碰后未来可能弃的牌。
    """
    return _encode_key_candidate_with_counts(observation, candidate, visible_hand_counts(observation))


def _encode_key_candidate_with_counts(
    observation: PlayerObservation, candidate: RuleCandidate, counts: tuple[int, ...],
) -> tuple[float, ...]:
    """复用同一次完整观察编码还原的 34 种暗牌计数，不跨窗口缓存。

    调用方先由共享观察编码校验和归一化摸牌；这里仅计算候选相关特征。
    """
    action = candidate.action
    tile = action.tile if isinstance(action, (Discard, Peng, Gang)) else None
    code = None if tile is None else tile.code
    order = [(observation.seat + i) % 4 for i in range(4)]
    def near(seat):
        if code is None or len(code) != 2 or code[0] not in '123456789' or code[1] not in 'wbt':
            return 0.
        return float(any(len(t.code) == 2 and t.code[1] == code[1]
                         and t.code[0] in '123456789' and abs(int(t.code[0])-int(code[0])) <= 2
                         for m in observation.melds[seat] for t in m.tiles))
    values = [float(tile is not None), 0. if tile is None else counts[CANONICAL_TILE_INDEX[code]]/4.]
    values += [sum(t.code == code for t in observation.discards[s])/4. for s in order]
    values += [near(order[1]), near(observation.dealer_seat)]
    white = counts[CANONICAL_TILE_INDEX[observation.rule_state.wealth_god.code]]
    values.append((white - int(isinstance(action, Discard) and action.tile == observation.rule_state.wealth_god))/4.)
    facts = candidate.facts
    for name in ('useful_tiles', 'standard_useful_tiles', 'seven_pairs_useful_tiles'):
        useful = None if facts is None else getattr(facts, name)
        values.append(sum(t.remaining_estimate for t in useful or ())/136.)
    return encode_candidate(candidate) + tuple(values) + conditional_value_features(observation, candidate)
