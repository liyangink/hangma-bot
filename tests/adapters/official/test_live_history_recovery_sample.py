"""以 v17 实测 seq710 缺失重现后补领；原始来源与注入语义见fixture/source.json。"""
from pathlib import Path
import json
from hangma_bot.adapters.official.dto import parse_state_response
from hangma_bot.adapters.official.sync_state import ProtocolSyncState,SyncDecision
from _official_testkit import TIMING


def test_real_discard_710_can_be_recovered_without_changing_current_board():
    path=Path(__file__).parents[2]/'fixtures/official/v17/history-recovery/discard-710.json'
    sample=json.loads(path.read_text())
    state=ProtocolSyncState('live-history-fixture',TIMING)
    state.apply_full_snapshot(parse_state_response(sample['before']).snapshot)
    assert state.apply_events(parse_state_response(sample['intermediate']).events).decision is SyncDecision.ACCEPTED
    state.apply_full_snapshot(parse_state_response(sample['after']).snapshot)
    before=state.current_observation();window=state.current_window()
    assert state.history_missing_ranges()==((710,710),)
    state.merge_history(parse_state_response(sample['late']).events,round_no=before.round_no)
    after=state.current_observation()
    assert state.history_missing_ranges()==()
    assert sum(e.seq==710 for e in after.public_history)==1
    assert before.my_hand==after.my_hand and before.discards==after.discards
    assert before.hand_counts==after.hand_counts and before.rule_state==after.rule_state
    assert before.snapshot_seq==after.snapshot_seq and before.consumed_seq==after.consumed_seq
    assert state.current_window()==window
    assert not after.history_complete  # 从707中途快照开始，不能顺便声称整手前缀已完整。
