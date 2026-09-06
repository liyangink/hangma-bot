"""官方适配器内部状态机的补史账本；只调用公开方法，不读取私有字段。"""
from dataclasses import replace

import pytest

from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.errors import DtoError
from hangma_bot.adapters.official.sync_state import ProtocolSyncState
from _official_testkit import TIMING
from test_sync_repair_regressions import event, snapshot


def parsed_snapshot(seq, **kwargs):
    raw = snapshot(seq, **kwargs)
    raw['snapshot']['melds'] = [[], [], [], []]
    return parse_state_response(raw).snapshot


def events(*raw):
    return parse_state_response({'events': list(raw)}).events


def start(seq=100):
    state = ProtocolSyncState('g_room1_batch1', TIMING)
    state.apply_full_snapshot(parsed_snapshot(seq, phase='deal'))
    return state


def test_debt_partial_merge_and_complete_repair_do_not_replay_board():
    state = start()
    state.apply_full_snapshot(parsed_snapshot(105, phase='response_peng', river=('6t',), discard='6t', responders=(2,)))
    before = state.current_observation()
    assert state.history_origin_known and state.history_floor_seq == 100
    assert state.history_missing_ranges() == ((101, 105),)
    state.merge_history(events(event(101, 'tile_discarded', tile='6t'), event(103, 'pass', seat=1), event(105, 'pass', seat=3)), round_no=1)
    assert state.history_missing_ranges() == ((102, 102), (104, 104))
    state.merge_history(events(event(102, 'pass', seat=1), event(104, 'pass', seat=3)), round_no=1)
    after = state.current_observation()
    assert state.history_missing_ranges() == ()
    assert after.history_complete
    assert 'history_gap_snapshot' not in after.observation_issues
    assert after.discards == before.discards
    assert after.hand_counts == before.hand_counts
    assert after.remaining_tile_count == before.remaining_tile_count
    assert after.rule_state == before.rule_state
    assert state.last_seq == 105


def test_mid_hand_unknown_prefix_remains_incomplete_after_known_debt_is_filled():
    state = ProtocolSyncState('g_room1_batch1', TIMING)
    state.apply_full_snapshot(parsed_snapshot(100, phase='response_peng', river=('6t',), discard='6t'))
    assert not state.history_origin_known and state.history_floor_seq == 100
    assert state.history_missing_ranges() == ()
    state.apply_full_snapshot(parsed_snapshot(101, phase='response_peng', river=('6t',), discard='6t'))
    state.merge_history(events(event(101, 'pass', seat=1)), round_no=1)
    assert state.history_missing_ranges() == ()
    assert not state.current_observation().history_complete


def test_large_watermark_uses_intervals_instead_of_enumerating_sequences():
    state = start()
    state.apply_full_snapshot(parsed_snapshot(10**12))
    assert state.history_missing_ranges() == ((101, 10**12),)
    state.merge_history(events(event(10**12, 'pass', seat=1)), round_no=1)
    assert state.history_missing_ranges() == ((101, 10**12-1),)


@pytest.mark.parametrize('bad', [
    event(102, 'pass', seat=3),
    event(103, 'new_rule_event'),
    event(104, 'pass', seat=1),
    event(100, 'pass', seat=1),
    event(103, 'tile_drawn', seat=1, tile='1b'),
])
def test_merge_rejects_whole_batch_on_conflict_unknown_range_or_private_draw(bad):
    state = start()
    state.apply_full_snapshot(parsed_snapshot(103))
    state.merge_history(events(event(102, 'pass', seat=1)), round_no=1)
    before = state.current_observation()
    with pytest.raises(DtoError):
        state.merge_history(events(event(101, 'pass', seat=1), bad), round_no=1)
    assert state.current_observation() == before
    assert state.history_missing_ranges() == ((101, 101), (103, 103))


def test_wrong_hand_and_beyond_snapshot_incremental_cannot_be_merged():
    state = start()
    state.apply_events(events(event(101, 'pass', seat=1)))
    with pytest.raises(DtoError):
        state.merge_history(events(event(101, 'pass', seat=1)), round_no=1)
    with pytest.raises(DtoError):
        state.merge_history((), round_no=2)
    assert state.last_seq == 101


def test_other_completeness_defect_is_not_cleared_with_gap():
    state = start()
    state.apply_full_snapshot(parsed_snapshot(101))
    state.note_rebuild_absorbed('new_rule_event')
    state.merge_history(events(event(101, 'pass', seat=1)), round_no=1)
    assert state.history_missing_ranges() == ()
    assert not state.current_observation().history_complete
    assert 'unknown_event:new_rule_event' in state.current_observation().observation_issues


def test_new_hand_origin_uses_received_previous_ending_and_resets_debt():
    state = start()
    state.apply_full_snapshot(parsed_snapshot(103), events=events(event(103, 'round_ended', data={'draw': True})))
    state.apply_full_snapshot(parsed_snapshot(104, round_no=2, phase='response_peng', river=('6t',), discard='6t'))
    assert state.history_origin_known
    assert state.history_floor_seq == 103
    assert state.history_missing_ranges() == ((104, 104),)
    assert state.current_observation().public_history == ()
    state.merge_history(events(event(104, 'tile_discarded', tile='6t')), round_no=2)
    assert state.current_observation().history_complete


def test_new_hand_start_without_previous_end_resets_unknown_prefix():
    state = ProtocolSyncState('g_room1_batch1', TIMING)
    state.apply_full_snapshot(parsed_snapshot(100, phase='response_peng', river=('6t',), discard='6t'))
    state.apply_full_snapshot(parsed_snapshot(105, round_no=2, phase='deal'))
    assert state.history_origin_known and state.history_floor_seq == 105
    assert state.current_observation().history_complete


def test_late_current_pass_suppresses_and_true_discard_does_not_rekey_window():
    state = start()
    state.apply_full_snapshot(parsed_snapshot(103, phase='response_peng', river=('6t',), discard='6t', responders=(2,)))
    old = state.current_window().window_key
    state.merge_history(events(event(101, 'tile_discarded', tile='6t'), event(102, 'pass', seat=2), event(103, 'pass', seat=1)), round_no=1)
    assert state.response_suppressed_for_self
    assert state.current_window().window_key == old
    structured = replace(parsed_snapshot(103, phase='response_chi', river=('6t',), discard='6t', responders=(2,)), last_discard=(0, '6t', 101))
    state.apply_full_snapshot(structured)
    assert state.current_window().window_key.trigger_seq == old.trigger_seq
    assert state.response_suppressed_for_self


def test_old_matching_discard_and_pass_do_not_suppress_new_cycle():
    state = start()
    state.apply_full_snapshot(parsed_snapshot(105, phase='response_peng', river=('6t', '6t'), discard='6t', responders=(2,)))
    state.current_window()
    state.merge_history(events(event(101, 'tile_discarded', tile='6t'), event(102, 'pass', seat=2)), round_no=1)
    assert not state.response_suppressed_for_self


def test_terminal_pair_can_be_merged_but_following_activity_cannot():
    state = start()
    state.apply_full_snapshot(parsed_snapshot(103, phase='finished'), finished=True)
    state.merge_history(events(event(102, 'round_ended', data={'draw': True}), event(103, 'game_ended', seat=-1, data={'final_scores': [1, 2, 3, 4]})), round_no=1)
    before = state.current_observation()
    assert [e.kind for e in before.public_history] == ['round_ended', 'game_ended']
    assert before.public_history[-1].final_scores == (1, 2, 3, 4)
    with pytest.raises(DtoError):
        state.merge_history(events(event(103, 'pass', seat=1)), round_no=1)
    assert state.current_observation() == before


def test_known_origin_does_not_leak_into_unknown_next_hand():
    state = start()
    state.apply_full_snapshot(parsed_snapshot(105, round_no=2, phase='response_peng', river=('6t',), discard='6t'))
    assert not state.history_origin_known
    assert state.history_floor_seq == 105
    assert not state.current_observation().history_complete


def test_first_terminal_duplicate_end_does_not_prove_history_origin():
    state = ProtocolSyncState('g_room1_batch1', TIMING)
    ending = event(100, 'round_ended', data={'draw': True})
    state.apply_full_snapshot(parsed_snapshot(100, phase='finished'), finished=True, events=events(ending, ending))
    assert not state.history_origin_known
    assert not state.current_observation().history_complete


def test_snapshot_supplied_incomplete_chi_cannot_be_marked_complete():
    state = start()
    state.apply_full_snapshot(parsed_snapshot(101), events=events(event(101, 'chi', seat=1, tile='6t')))
    assert state.history_missing_ranges() == ()
    assert not state.current_observation().history_complete
    assert 'event_detail_incomplete:chi' in state.current_observation().observation_issues


def test_new_discard_releases_estimated_window_identity():
    state = start()
    state.apply_full_snapshot(parsed_snapshot(103, phase='response_peng', river=('6t',), discard='6t', responders=(2,)))
    assert state.current_window().window_key.trigger_seq == 103
    state.merge_history(events(event(101, 'tile_discarded', tile='6t'), event(102, 'pass', seat=1), event(103, 'pass', seat=3)), round_no=1)
    state.apply_events(events(event(104, 'tile_discarded', tile='6t')))
    state.apply_full_snapshot(parsed_snapshot(104, phase='response_peng', river=('6t', '6t'), discard='6t', responders=(2,)))
    assert state.current_window().window_key.trigger_seq == 104


def test_snapshot_debt_correction_preserves_later_incremental_watermark():
    state = start()
    state.apply_full_snapshot(parsed_snapshot(101))
    state.apply_events(events(event(102, 'pass', seat=1)))
    state.merge_history(events(event(101, 'pass', seat=3)), round_no=1)
    assert state.last_seq == 102
    assert state.current_observation().snapshot_seq == 101
    assert state.current_observation().consumed_seq == 102
    assert [e.seq for e in state.current_observation().public_history] == [101, 102]


def test_snapshot_attached_late_pass_uses_true_discard_without_rekeying():
    state = start()
    current = parsed_snapshot(103, phase='response_peng', river=('6t',), discard='6t', responders=(2,))
    state.apply_full_snapshot(current)
    assert state.current_window().window_key.trigger_seq == 103
    state.apply_full_snapshot(replace(current, phase='response_chi'), events=events(event(101, 'tile_discarded', tile='6t'), event(102, 'pass', seat=1), event(103, 'pass', seat=2)))
    assert state.current_window().window_key.trigger_seq == 103
    assert state.response_suppressed_for_self
