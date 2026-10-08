"""作者前缀压缩：保留读数/缺口、证据不一致拒绝、计划身份与发题接线。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import copy
import json

import pytest

import sitin_feedback as feedback
import sitin_search as search


def projection(n=40, collected=True):
    """构造带实际两臂读数或显式未采集的开发投影，不调用模拟器。"""
    prefix = [{'window_key': {'game_id': 'test-visible', 'seat': i % 4,
        'phase': 'response_peng', 'round_no': 1, 'trigger_seq': i},
        'action_key': 'pass' if i % 2 else 'discard:1w'} for i in range(n)]
    expanded = '；'.join('{}→{}'.format(json.dumps(s['window_key'], ensure_ascii=False,
        sort_keys=True), s['action_key']) for s in prefix)
    detail = '（逐座位 window_key→action_key，共 {} 步）：{}'.format(
        n, expanded or '（空：截取窗口就是前缀起点）')
    reading = 'baseline=discard:2w；candidate=discard:3b' if collected else '两臂动作未采集，不推算'
    item = {'key': 'window.actions', 'text': reading + '\n行为策略的合法动作前缀' + detail,
        'evidence': {'artifact': '/audit/panel.json', 'locator': '/scenarios/0/snapshot/legal_action_prefix',
                     'value': prefix}, 'extra_evidences': []}
    fact = {'key': 'window.mask', 'text': 'branch_open=UNKNOWN；不补零'}
    return {'status': feedback.PROJECTION_OK, 'executable': True, 'refusals': [],
        'facts_items': [fact, item], 'facts': [fact['text'], item['text']],
        'associated_results': ['H=-0.1；M=0.2；识别区间不是置信区间'],
        'mechanism_hypothesis': '未采集trace，只是槽位，不能推测数值',
        'gaps': [{'code': 'test.gap', 'detail': '缺剩余赛程'}]}


@pytest.mark.parametrize('collected', [True, False])
def test_long_prefix_only_is_compacted_with_readings_and_gaps_preserved(collected):
    raw = projection(collected=collected)
    before = copy.deepcopy(raw)
    full = feedback.projection_segments(raw)
    compact = feedback.author_projection_segments(raw, mode='compact_prefix_v1')
    assert raw == before
    assert compact['associated_results'] == full['associated_results']
    assert compact['mechanism_hypothesis'] == full['mechanism_hypothesis']
    assert len(compact['facts']) < len(full['facts']) / 2
    for text in ('branch_open=UNKNOWN', '缺剩余赛程', '共 40 步', 'SHA256=',
                 '/audit/panel.json#/scenarios/0/snapshot/legal_action_prefix',
                 '完整逐步轨迹保留在审计产物，未随本正文传递'):
        assert text in compact['facts']
    reading = 'baseline=discard:2w；candidate=discard:3b' if collected else '两臂动作未采集，不推算'
    assert reading in compact['facts']
    assert 'test-visible' not in compact['facts']
    assert '"discard": 20' in compact['facts'] and '"pass": 20' in compact['facts']


@pytest.mark.parametrize('n', [0, 1, 3])
def test_short_prefix_retains_raw_reading_and_default_is_byte_identical(n):
    raw = projection(n)
    assert feedback.author_projection_segments(raw) == feedback.projection_segments(raw)
    compact = feedback.author_projection_segments(raw, mode='compact_prefix_v1')
    assert raw['facts'][1] in compact['facts']


def test_ordered_prefix_identity_changes_even_when_counts_unchanged():
    first = projection()
    second = projection()
    item = second['facts_items'][1]
    prefix = item['evidence']['value']
    prefix.reverse()
    item['text'] = item['text'].split('（逐座位')[0] + '（逐座位 window_key→action_key，共 40 步）：' + '；'.join(
        '{}→{}'.format(json.dumps(s['window_key'], ensure_ascii=False, sort_keys=True), s['action_key']) for s in prefix)
    second['facts'][1] = item['text']
    a = feedback.author_projection_segments(first, mode='compact_prefix_v1')['facts']
    z = feedback.author_projection_segments(second, mode='compact_prefix_v1')['facts']
    assert a != z
    assert '"discard": 20' in a and '"discard": 20' in z


@pytest.mark.parametrize('defect', ['refused', 'not_executable', 'facts_drift', 'missing_evidence',
    'duplicate_evidence', 'prefix_value_drift', 'malformed_step', 'missing_text'])
def test_bad_projection_cannot_silently_drop_or_rewrite_evidence(defect):
    raw = projection()
    item = raw['facts_items'][1]
    if defect == 'refused':
        raw['refusals'] = [{'code': 'root.confirmation', 'detail': '禁止消费'}]
    elif defect == 'not_executable':
        raw['executable'] = False
    elif defect == 'facts_drift':
        raw['facts'][1] += 'new unsupported fact'
    elif defect == 'missing_evidence':
        item['evidence'] = None
    elif defect == 'duplicate_evidence':
        item['extra_evidences'] = [copy.deepcopy(item['evidence'])]
    elif defect == 'prefix_value_drift':
        item['evidence']['value'][0]['action_key'] = 'discard:9w'
    elif defect == 'malformed_step':
        del item['evidence']['value'][0]['window_key']
    else:
        del item['text']
    with pytest.raises(feedback.FeedbackInputError):
        feedback.author_projection_segments(raw, mode='compact_prefix_v1')


def auth(mode):
    return {'schema': 'sitin-authorization/1', 'authorization_id': 'author-feedback-test',
        'batch_label': 'author-feedback-test', 'issued_by': 'lead', 'trusted': True,
        'issued_at_utc': '2026-09-20T00:00:00Z', 'allowed_operations': [],
        'allowed_accounts': {'tokens_input': 2048, 'tokens_output': 8192},
        'author_feedback_mode': mode}


def test_mode_is_frozen_and_tampering_rejected(tmp_path):
    state = search.av_start_iteration(tmp_path / 'run', generation_mode='mock',
        authorization=auth('compact_prefix_v1'))
    assert state['plan']['author_feedback_mode'] == 'compact_prefix_v1'
    assert state['identity']['frozen_manifest']['surfaces']['author_feedback_mode'] == 'compact_prefix_v1'
    assert search.av_verify_run_identity(state)[0]
    before = (tmp_path / 'run/av-ledger.json').read_bytes()
    state['plan']['author_feedback_mode'] = 'full_v1'
    assert not search.av_verify_run_identity(state)[0]
    assert (tmp_path / 'run/av-ledger.json').read_bytes() == before


@pytest.mark.parametrize('mode', ['', False, [], 'compact_v99'])
def test_unknown_mode_rejected_before_any_reservation(tmp_path, mode):
    with pytest.raises(ValueError, match='author_feedback_mode'):
        search.av_start_iteration(tmp_path / 'run', authorization=auth(mode))
    assert not (tmp_path / 'run').exists()


def test_render_adapter_preserves_results_and_applies_mode():
    raw = projection()
    full = search._av_render_feedback_payload(raw)
    compact = search._av_render_feedback_payload(raw, mode='compact_prefix_v1')
    assert 'compact_prefix_v1' in compact['facts']
    assert compact['associated_results'] == full['associated_results']
    assert compact['mechanism_hypothesis'] == full['mechanism_hypothesis']


def test_real_generation_packet_uses_frozen_mode_without_changing_parent_or_contract(tmp_path, monkeypatch):
    from pathlib import Path
    parent = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[1] / 'evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation')
    if not parent.is_dir():
        pytest.skip('真实父代验收产物不在当前检出')
    raw = projection()
    monkeypatch.setattr(search, '_av_m1_feedback', lambda _: (raw, {'ok': True}))
    plan = {'operator': 'm1', 'predicate': 'branch_open', 'opponent': 'H', 'parent_dir': str(parent)}
    gen = search.av_generate()
    full = search._av_generation_packet({'plan': plan}, gen, tmp_path)
    compact = search._av_generation_packet({'plan': dict(plan, author_feedback_mode='compact_prefix_v1')}, gen, tmp_path)
    source = (parent / 'candidate.py').read_text().strip()
    assert source in full.text and source in compact.text
    assert 'compact_prefix_v1' not in full.text and 'compact_prefix_v1' in compact.text
    assert len(compact.text) < len(full.text)
    for heading in ('【受限子集静态规则', '【作者守卫条款', '【公开接口附录'):
        assert heading in full.text and heading in compact.text
    raw_facts = feedback.projection_segments(raw)['facts']
    short_facts = feedback.author_projection_segments(raw, mode='compact_prefix_v1')['facts']
    assert full.text.count(raw_facts) == compact.text.count(short_facts) == 1
    assert full.text.replace(raw_facts, '<facts>') == compact.text.replace(short_facts, '<facts>')


def test_generation_packet_checks_consumption_before_compaction(tmp_path, monkeypatch):
    from types import SimpleNamespace
    called = []
    gen = SimpleNamespace(av_parent_binding=lambda _: {
        'identity': {}, 'candidate_id': 'p', 'prompt_sha256': 'p', 'dir': str(tmp_path),
        'code_sha256': 'p', 'code': 'parent'})
    monkeypatch.setattr(search, '_av_m1_feedback', lambda _: ({}, {'ok': False, 'detail': 'identity drift'}))
    monkeypatch.setattr(search, '_av_render_feedback_payload', lambda *a, **k: called.append(True))
    with pytest.raises(search.AvFeedbackRefused, match='identity drift'):
        search._av_generation_packet({'plan': {'operator': 'm1', 'parent_dir': str(tmp_path),
            'author_feedback_mode': 'compact_prefix_v1'}}, gen, tmp_path)
    assert called == []


def test_render_failure_closes_iteration_without_emitting_prompt_or_model_charge(tmp_path, monkeypatch):
    root = tmp_path / 'run'
    state = search.av_start_iteration(root, generation_mode='mock', authorization=auth('compact_prefix_v1'),
        archive_in={'source': 'empty', 'path': None})
    def refused(*args):
        raise search.av_feedback().FeedbackInputError('前缀证据不一致')
    monkeypatch.setattr(search, '_av_generation_packet', refused)
    outcome = search.av_iteration_advance(search.av_latest_state_path(root), root,
        authorization=auth('compact_prefix_v1'))
    assert outcome['terminal'] == 'INPUT_GAP'
    saved = search.av_state_load(search.av_latest_state_path(root))
    assert saved['stop_reason'] == 'author_feedback_render_refused'
    assert not list(root.rglob('prompt.txt'))
    assert not list(root.rglob('tx-model-call-before.json'))
    ledger = json.loads((root / 'av-ledger.json').read_text())
    assert ledger['spent']['tokens_input'] == ledger['spent']['tokens_output'] == 0


@pytest.mark.parametrize('artifact', ['transactions/tx-model-call-before.json',
    'pending/i1/prompt.txt', 'reply-envelope.json'])
def test_render_failure_never_refunds_a_possible_previous_handoff(tmp_path, monkeypatch, artifact):
    root = tmp_path / 'run'
    state = search.av_start_iteration(root, generation_mode='mock', authorization=auth('compact_prefix_v1'),
        archive_in={'source': 'empty', 'path': None})
    from pathlib import Path
    evidence = Path(state['iter_dir']) / artifact
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text('{}')
    def refused(*args):
        raise search.av_feedback().FeedbackInputError('前缀证据不一致')
    monkeypatch.setattr(search, '_av_generation_packet', refused)
    outcome = search.av_iteration_advance(search.av_latest_state_path(root), root,
        authorization=auth('compact_prefix_v1'))
    assert outcome['terminal'] == 'INPUT_GAP'
    saved = search.av_state_load(search.av_latest_state_path(root))
    assert saved['stop_reason'] == 'author_feedback_render_refused'
    assert saved['feedback_refusal']['unissued_reservations_released'] is False
    ledger = json.loads((root / 'av-ledger.json').read_text())
    assert ledger['spent']['tokens_input'] == 2048 and ledger['spent']['tokens_output'] == 8192
