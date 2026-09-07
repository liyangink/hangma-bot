"""单局结果取原始结算事件；顶层摘要缺条或编号不同不覆盖单局事实。"""
from copy import deepcopy

from test_replay_score_context import score_document, read_hand


def test_summary_winner_and_score_do_not_override_settlement_event():
    doc = score_document()
    doc['rounds'][0].update(winner=3, scores=[0, 0, 0, 0])
    original = deepcopy(doc)
    row = read_hand(doc, 1)
    assert row['winner_seat'] == 0
    assert row['scores_after'] == [124, 192, 292, 392]
    assert row['result_source'] == 'round_ended'
    assert row['result_consistency']['status'] == 'conflict'
    assert doc == original


def test_all_event_hands_import_when_top_summary_contains_only_last_entry():
    doc = score_document()
    doc['rounds'] = [doc['rounds'][-1]]
    first = read_hand(doc, 1)
    assert first['winner_seat'] == 0
    assert first['result_confirmed']
    assert first['result_consistency']['status'] == 'not_checked'


def test_missing_top_summaries_still_preserve_confirmed_event_scores():
    doc = score_document()
    del doc['rounds']
    row = read_hand(doc, 2)
    assert row['winner_seat'] == 1
    assert row['score_delta'] == [-16, 20, -2, -2]


def test_second_hand_history_origin_does_not_require_sequence_reset():
    doc = score_document()
    # 形状证据：新单局完整起手，前一单局在本块首序号之前结束。
    doc['blocks'][1]['start_hands'] = [['1w'] * 14, ['2w'] * 13, ['3w'] * 13, ['4w'] * 13]
    assert read_hand(doc, 2)['coverage'] == 'full_history'
    doc['blocks'][0]['events'] = []
    assert read_hand(doc, 2)['coverage'] == 'observed'


def test_terminal_draw_flag_without_winner_seat_does_not_confirm_result():
    doc = score_document()
    del doc['blocks'][0]['events'][0]['seat']
    row = read_hand(doc, 1)
    assert row['winner_seat'] is None and not row['result_confirmed']


def test_declared_block_range_cannot_hide_missing_history():
    doc = score_document()
    doc['blocks'][0].update(seq_start=50, seq_end=50)
    assert read_hand(doc, 1)['coverage'] == 'observed'
