"""以官方快照边界验证模型输入，区分归档覆盖与未恢复的增量断序。"""
from dataclasses import replace

import pytest

from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicEvent
from hangma_bot.learning.key_encoding import key_window_tags
from hangma_bot.learning.sequence_encoding import encode_sequence_input
from tests.unit.policy.support import make_observation, rules_from_engine


def snapshot():
    """当前牌面直接来自水位10；早期逐事件记录可有可无。"""
    return make_observation(
        my_hand=tuple(Tile(code) for code in
                      ("1b", "2b", "3b", "4b", "5b", "6b", "7b", "8b", "9b", "1t", "2t", "3t", "白")),
        drawn_tile=Tile("5t"), consumed_seq=10,
        discards=((), (Tile("9t"),), (), ()),
    )


def event(seq):
    return PublicEvent(seq, "pass", 1)


@pytest.mark.parametrize("history", [(), (event(8),), (event(3), event(8))])
def test_snapshot_accepts_optional_archived_event_fragments(history):
    observation = replace(snapshot(), public_history=history)
    candidates = rules_from_engine(observation).legal_candidates
    encoded = encode_sequence_input(observation, candidates)
    assert len(encoded.context) == 334 and encoded.context[6] == 0.
    assert len(encoded.history) == len(history)
    assert observation.history_complete is False


def test_continuous_suffix_after_snapshot_is_accepted():
    observation = replace(snapshot(), consumed_seq=12,
                          public_history=(event(3), event(10), event(11), event(12)))
    candidates = rules_from_engine(observation).legal_candidates
    assert len(encode_sequence_input(observation, candidates).history) == 4


@pytest.mark.parametrize("history,consumed", [
    ((event(11), event(13)), 13),  # 快照以后真正缺少增量12。
    ((), 11),  # 状态水位声称已前进，却没有相应增量。
    ((event(3), event(3)), 10),  # 冲突或重复序号不能当两个真实事件输入。
    ((event(8), event(3)), 10),  # 顺序颠倒。
    ((event(11),), 10),  # 尚未消费的未来事件。
])
@pytest.mark.parametrize("complete", [False, True])
def test_actual_sequence_inconsistency_is_rejected_regardless_of_archive_flag(history, consumed, complete):
    base = snapshot()
    candidates = rules_from_engine(base).legal_candidates
    observation = replace(base, public_history=history, consumed_seq=consumed,
                          history_complete=complete)
    with pytest.raises(ValueError, match="水位矛盾|连续同步"):
        encode_sequence_input(observation, candidates)


def test_current_snapshot_tags_do_not_require_an_event_archive():
    observation = snapshot()
    analysis = rules_from_engine(observation)
    tags = key_window_tags(observation, analysis)
    assert "holding_white" in tags
    assert tags == key_window_tags(replace(observation, history_complete=True), analysis)


def test_archive_flag_does_not_change_existing_feature_layout_or_other_values():
    observation = replace(snapshot(), public_history=(event(3), event(8)))
    candidates = rules_from_engine(observation).legal_candidates
    partial = encode_sequence_input(observation, candidates)
    complete = encode_sequence_input(replace(observation, history_complete=True), candidates)
    assert partial.context[:6] == complete.context[:6]
    assert partial.context[7:] == complete.context[7:]
    assert partial.context[6] == 0. and complete.context[6] == 1.
    assert partial.history == complete.history
    assert partial.candidates == complete.candidates
    assert partial.action_keys == complete.action_keys
