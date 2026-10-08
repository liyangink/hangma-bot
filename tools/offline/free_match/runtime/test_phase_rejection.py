"""相位拒绝的窄回归：保留旧合成反控，另重放已脱敏的真实吃窗证据。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import phase_rejection as phase


def fixture():
    """合成证据只描述合法复核/提交/权威恢复，不代表真实HTTP已验证。"""
    ctx = {'game_id': 'synthetic-game', 'decision_id': 'synthetic-decision',
           'attempt_no': 1, 'round_no': 2, 'trigger_seq': 404}
    window = {'game_id': ctx['game_id'], 'round_no': 2, 'trigger_seq': 404,
              'phase': 'response_peng', 'seat': 3}
    def row(kind, payload, stamp):
        return {'kind': kind, 'context': dict(ctx), 'payload': payload,
                'monotonic_ns': stamp, 'original_line_sha256': 'a' * 64}
    records = [
        row('decision_input', {'window': window, 'rule_completeness': 'complete',
            'legal_keys': ['peng:4t', 'pass'], 'snapshot_seq': 404, 'consumed_seq': 404,
            'budget': {'latest_send_at_monotonic': 2.}}, 1000000000),
        row('candidate_validated', {'action_key': 'peng:4t', 'legal': True, 'window': window,
            'action': {'kind': 'peng', 'tile': '4t', 'schema_version': 1}}, 1100000000),
        row('submission_intent', {'action_key': 'peng:4t', 'window': window,
            'based_on_authoritative_seq': 404, 'latest_send_at_monotonic': 2.}, 1200000000),
        row('submission_intent', {'body': {'action': 'peng', 'tile': '4t'}, 'window': window,
            'action_key': 'peng:4t', 'based_on_authoritative_seq': 404,
            'decision_id': ctx['decision_id'], 'attempt_no': 1}, 1300000000),
        row('submission_outcome', {'outcome_type': 'SubmitRejectedNoRefresh',
            'reason': 'conflict_refresh_unavailable', 'official_code': 'INVALID_ACTION',
            'rejected_action_key': 'peng:4t'}, 3001000000),
        row('decision_ended', {'attempt_count': 1, 'sent_attempts': 1, 'window': window}, 3002000000)]
    reject = row('action_submit_response', {'http_status': 409,
        'raw': json.dumps({'code': 'INVALID_ACTION', 'message': 'peng only in peng window'}),
        'request_timing': {'transport_started_at_monotonic': 1.5, 'completed_at_monotonic': 3.}}, 3000000000)
    pre = {'phase': 'response_peng', 'round_no': 2, 'seat': 3, 'turn': 0, 'last_discard': '4t'}
    after = {**pre, 'turn': 1, 'last_discard': '西'}
    snapshots = [{'gid': ctx['game_id'], 'stamp': stamp, 'seq_requested': 0, 'applied': True,
        'body': {'gap': False, 'seq': seq, 'snapshot': snap}} for stamp, seq, snap in
        ((900000000, 404, pre), (3100000000, 409, after))]
    return {'rejection': reject, 'records': records, 'snapshots': snapshots,
            'post_counts': {phase.window(window): 1}, 'adapter_counts': {phase.window(window): 1}}


def prove(case):
    return phase.prove(case['rejection'], case['records'], case['snapshots'],
                       case['post_counts'], case['adapter_counts'])


class PhaseRejectionCases(unittest.TestCase):
    """原NoRefresh与所有缺证据分支守恒；只分类不提交动作。"""
    def test_one_positive_and_twenty_direct_negatives(self):
        case = fixture(); result = prove(case)
        self.assertIsNotNone(result)
        self.assertEqual(result['actual_outcome'], 'SubmitRejectedNoRefresh')
        self.assertEqual(result['decision_sent_attempts'], 1)
        mutators = {
            'NOT_QUALIFIED': lambda c: c['rejection']['payload'].update(raw=json.dumps({'code': 'NOT_QUALIFIED', 'message': 'peng only in peng window'})),
            'shape_error_message': lambda c: c['rejection']['payload'].update(raw=json.dumps({'code': 'INVALID_ACTION', 'message': 'tile count invalid'})),
            'missing_message': lambda c: c['rejection']['payload'].update(raw=json.dumps({'code': 'INVALID_ACTION'})),
            'wrong_wire_tile': lambda c: c['records'][3]['payload']['body'].update(tile='5t'),
            'missing_wire_tile': lambda c: c['records'][3]['payload']['body'].pop('tile'),
            'extra_wire_shape_field': lambda c: c['records'][3]['payload']['body'].update(extra=True),
            'wrong_validated_action_shape': lambda c: c['records'][1]['payload']['action'].update(tile='5t'),
            'missing_legal_validation': lambda c: c['records'].pop(1),
            'illegal_validation': lambda c: c['records'][1]['payload'].update(legal=False),
            'late_actual_transport_start': lambda c: c['rejection']['payload']['request_timing'].update(transport_started_at_monotonic=2.01),
            'missing_authoritative_after': lambda c: c['snapshots'].pop(),
            'after_gap_true': lambda c: c['snapshots'][1]['body'].update(gap=True),
            'after_not_applied': lambda c: c['snapshots'][1].update(applied=False),
            'before_not_applied': lambda c: c['snapshots'][0].update(applied=False),
            'same_authoritative_window': lambda c: c['snapshots'][1]['body'].update(snapshot=deepcopy(c['snapshots'][0]['body']['snapshot'])),
            'ambiguous_submission_outcome': lambda c: c['records'][4]['payload'].update(outcome_type='SubmitAmbiguous'),
            'sent_attempts_two': lambda c: c['records'][5]['payload'].update(sent_attempts=2),
            'attempt_count_two': lambda c: c['records'][5]['payload'].update(attempt_count=2),
            'wrong_adapter_DID': lambda c: c['records'][3]['context'].update(decision_id='other-decision'),
            'wrong_adapter_window': lambda c: c['records'][3]['payload'].update(window={**c['records'][3]['payload']['window'], 'trigger_seq': 405})}
        self.assertEqual(len(mutators), 20)
        for name, mutate in mutators.items():
            with self.subTest(name=name):
                case = fixture(); mutate(case); self.assertIsNone(prove(case))


class OnlyPassPhaseRejectionCases(unittest.TestCase):
    """只锁定实战发现的唯一过牌相位拒绝；保留所有未证实情况的硬门。"""
    @staticmethod
    def case():
        case = fixture()
        case['records'][0]['payload']['window']['phase'] = 'response_chi'
        case['records'][0]['payload']['legal_keys'] = ['pass']
        case['records'][1]['payload'].update(action_key='pass', action={'kind': 'pass', 'schema_version': 1})
        case['records'][2]['payload']['action_key'] = 'pass'
        case['records'][3]['payload'].update(action_key='pass', body={'action': 'pass', 'tile': ''})
        case['records'][4]['payload']['rejected_action_key'] = 'pass'
        case['rejection']['payload']['raw'] = json.dumps({'code': 'INVALID_ACTION', 'message': 'cannot pass in phase 1'})
        case['snapshots'][0]['body']['snapshot']['phase'] = 'response_chi'
        case['snapshots'][1]['body']['snapshot']['phase'] = 'draw'
        case['adapter_counts'] = {phase.window(case['records'][0]['payload']['window']): 1}
        case['post_counts'] = dict(case['adapter_counts'])
        return case

    def test_only_pass_recovery_preserves_original_outcome(self):
        result = prove(self.case())
        self.assertIsNotNone(result)
        self.assertEqual(result['classification'], 'recovered_expired_only_pass_window')
        self.assertEqual(result['actual_outcome'], 'SubmitRejectedNoRefresh')
        self.assertEqual(result['all_window_adapter_body_intents'], 1)
        self.assertIn('no_evidence_of_lost_claim_opportunity', result['warning'])

    def test_unproved_pass_cases_still_block(self):
        mutations = {
            'valuable_action_available': lambda c: c['records'][0]['payload'].update(legal_keys=['pass', 'chi:1w,2w,3w']),
            'wrong_local_phase': lambda c: c['records'][0]['payload']['window'].update(phase='response_peng'),
            'other_server_phase_message': lambda c: c['rejection']['payload'].update(raw=json.dumps({'code': 'INVALID_ACTION', 'message': 'cannot pass in phase 2'})),
            'NOT_QUALIFIED': lambda c: c['rejection']['payload'].update(raw=json.dumps({'code': 'NOT_QUALIFIED', 'message': 'cannot pass in phase 1'})),
            'late_transport': lambda c: c['rejection']['payload']['request_timing'].update(transport_started_at_monotonic=2.01),
            'wrong_wire_body': lambda c: c['records'][3]['payload']['body'].update(tile='4t'),
            'bad_validation': lambda c: c['records'][1]['payload'].update(legal=False),
            'before_not_applied': lambda c: c['snapshots'][0].update(applied=False),
            'after_gap': lambda c: c['snapshots'][1]['body'].update(gap=True),
            'missing_authoritative_after': lambda c: c['snapshots'].pop(),
            'same_window': lambda c: c['snapshots'][1]['body'].update(snapshot=deepcopy(c['snapshots'][0]['body']['snapshot'])),
            'ambiguous_outcome': lambda c: c['records'][4]['payload'].update(outcome_type='SubmitAmbiguous'),
            'second_POST': lambda c: c['post_counts'].update({next(iter(c['post_counts'])): 2}),
            'second_adapter_body': lambda c: c['adapter_counts'].update({next(iter(c['adapter_counts'])): 2}),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                case = self.case(); mutate(case); self.assertIsNone(prove(case))

    def test_three_second_intents_without_second_raw_response(self):
        for name in ('same_DID', 'other_DID', 'other_DID_malformed_body'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                case = fixture(); wire = deepcopy(case['records'][3]); second = deepcopy(wire)
                if name != 'same_DID': second['context']['decision_id'] = 'other-decision'
                if name == 'other_DID_malformed_body': second['payload']['body'] = None
                path = Path(temp)/'participants/synthetic/decisions.jsonl'; path.parent.mkdir(parents=True)
                path.write_text('\n'.join(json.dumps(row) for row in (wire, second))+'\n')
                _, info, counts, _ = phase.collect(Path(temp), {'synthetic-decision'}, max_bytes=1048576, max_seconds=5.)
                self.assertTrue(info['complete']); self.assertEqual(counts[phase.window(wire['payload']['window'])], 2)
                self.assertEqual(next(iter(case['post_counts'].values())), 1)
                case['adapter_counts'] = counts; self.assertIsNone(prove(case))

    def test_unknown_prefix_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'participants/synthetic/decisions.jsonl'; path.parent.mkdir(parents=True)
            row = {'padding': 'x'*4096, **fixture()['records'][3]}
            path.write_text(json.dumps(row)+'\n')
            _, info, _, _ = phase.collect(Path(temp), {'synthetic-decision'}, max_bytes=1048576, max_seconds=5.)
            self.assertFalse(info['complete']); self.assertEqual(info['unknown'], 'compact_prefix_contract_missing')


class ChiPhaseRejectionCases(unittest.TestCase):
    """吃窗只豁免完整合法、及时、一次且权威应用新窗口的已响应拒绝。"""
    @staticmethod
    def case():
        case = fixture()
        case['records'][0]['payload']['window']['phase'] = 'response_chi'
        case['records'][0]['payload']['legal_keys'] = ['chi:7t,8t,9t', 'pass']
        case['records'][1]['payload'].update(action_key='chi:7t,8t,9t',
            action={'kind': 'chi', 'tiles': ['7t', '8t', '9t'], 'schema_version': 1})
        case['records'][2]['payload']['action_key'] = 'chi:7t,8t,9t'
        case['records'][3]['payload'].update(action_key='chi:7t,8t,9t',
            body={'action': 'chi', 'tile': '9t', 'tiles': ['7t', '8t']})
        case['records'][4]['payload']['rejected_action_key'] = 'chi:7t,8t,9t'
        case['rejection']['payload']['raw'] = json.dumps(
            {'code': 'INVALID_ACTION', 'message': 'chi only in chi window'})
        case['rejection']['payload']['request_timing'].update(
            started_wall_unix_ms=1500, completed_wall_unix_ms=3000)
        pre = case['snapshots'][0]['body']['snapshot']
        pre.update(phase='response_chi', turn=2, responding_seats=[3], last_discard='9t',
            my_hand=['7t', '8t', '1w'], hand_counts=[3, 3, 3, 3], window_deadline_ms=2000)
        case['snapshots'][1]['body']['snapshot'] = {**deepcopy(pre), 'phase': 'draw', 'turn': 3}
        case['adapter_counts'] = {phase.window(case['records'][0]['payload']['window']): 1}
        case['post_counts'] = dict(case['adapter_counts'])
        return case

    def test_chi_positive_and_strict_negatives(self):
        result = prove(self.case())
        self.assertIsNotNone(result)
        self.assertEqual(result['classification'], 'recovered_expired_chi_window')
        self.assertEqual(result['actual_outcome'], 'SubmitRejectedNoRefresh')
        self.assertIn('lost_response_opportunity', result['warning'])
        mutations = {
            'NOT_QUALIFIED': lambda c: c['rejection']['payload'].update(raw=json.dumps({'code': 'NOT_QUALIFIED', 'message': 'chi only in chi window'})),
            'other_message': lambda c: c['rejection']['payload'].update(raw=json.dumps({'code': 'INVALID_ACTION', 'message': 'tile count invalid'})),
            'no_response': lambda c: c['rejection']['payload'].update(http_status=None),
            'wrong_phase': lambda c: c['records'][0]['payload']['window'].update(phase='response_peng'),
            'incomplete_rule': lambda c: c['records'][0]['payload'].update(rule_completeness='partial'),
            'incomplete_consumed_seq': lambda c: c['records'][0]['payload'].update(consumed_seq=403),
            'action_not_legal': lambda c: c['records'][0]['payload'].update(legal_keys=['pass']),
            'illegal_validation': lambda c: c['records'][1]['payload'].update(legal=False),
            'wrong_validated_group': lambda c: c['records'][1]['payload']['action'].update(tiles=['7t', '8t', '9w']),
            'wrong_wire_discard': lambda c: c['records'][3]['payload']['body'].update(tile='8t'),
            'wrong_wire_owned_tiles': lambda c: c['records'][3]['payload']['body'].update(tiles=['7t', '9t']),
            'extra_wire_field': lambda c: c['records'][3]['payload']['body'].update(extra=True),
            'missing_owned_tile': lambda c: c['snapshots'][0]['body']['snapshot']['my_hand'].remove('7t'),
            'wrong_direction': lambda c: c['snapshots'][0]['body']['snapshot'].update(turn=0),
            'wrong_responding_seat': lambda c: c['snapshots'][0]['body']['snapshot'].update(responding_seats=[2]),
            'wrong_discard_snapshot': lambda c: c['snapshots'][0]['body']['snapshot'].update(last_discard='8t'),
            'late_monotonic_start': lambda c: c['rejection']['payload']['request_timing'].update(transport_started_at_monotonic=2.01),
            'late_wall_start': lambda c: c['rejection']['payload']['request_timing'].update(started_wall_unix_ms=2001),
            'missing_official_deadline': lambda c: c['snapshots'][0]['body']['snapshot'].pop('window_deadline_ms'),
            'missing_authoritative_after': lambda c: c['snapshots'].pop(),
            'before_not_applied': lambda c: c['snapshots'][0].update(applied=False),
            'after_not_applied': lambda c: c['snapshots'][1].update(applied=False),
            'after_gap': lambda c: c['snapshots'][1]['body'].update(gap=True),
            'same_window': lambda c: c['snapshots'][1]['body'].update(snapshot=deepcopy(c['snapshots'][0]['body']['snapshot'])),
            'ambiguous_outcome': lambda c: c['records'][4]['payload'].update(outcome_type='SubmitAmbiguous'),
            'second_POST': lambda c: c['post_counts'].update({next(iter(c['post_counts'])): 2}),
            'second_adapter': lambda c: c['adapter_counts'].update({next(iter(c['adapter_counts'])): 2}),
            'sent_twice': lambda c: c['records'][5]['payload'].update(sent_attempts=2),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                case = self.case(); mutate(case); self.assertIsNone(prove(case))

    def test_actual_batch011_chi_piece_replay(self):
        """真实拒绝原件缩成fixture；不读凭据、不重新提交或重算规则。"""
        import hashlib
        path = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[5] / '.private/t200-eoh-fast-evolution/free-incident-batch011-chi/CHI-CASE.json')
        if not path.is_file():
            self.skipTest('真实Chi原件仅在本机私有证据中；28项合成反控仍必跑')
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '33c53e5009b90ac6c0acfc5791ede629c923a44927738e4dea2230c8125a08c1')
        case = json.loads(raw)
        # 旧原件只含单一吃窗，沿其可信原窗口把历史三元计数转换为当前五元键。
        original_window = phase.window(case['records'][0]['payload']['window'])
        self.assertEqual(case['post_counts'], [{'key': list(original_window[:3]), 'value': 1}])
        case['post_counts'] = {original_window: 1}
        case['adapter_counts'] = {tuple(row['window']): row['value'] for row in case['adapter_counts']}
        result = prove(case)
        self.assertIsNotNone(result)
        self.assertEqual(result['classification'], 'recovered_expired_chi_window')
        self.assertEqual(result['authoritative_recovery_seq'], 1217)
        self.assertAlmostEqual(result['timely_send_margin_ms'], 426.1557227000594, places=5)

    def test_legacy_positive_proofs_equal_frozen_previous_helper(self):
        """新增吃窗不改变旧碰牌和唯一过牌证明的任何结果字段。"""
        import importlib.util
        path = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[5] / '.private/t199-four-step-execution/runtime-workspace/runtime-root-p0-pass026-prepared-v1/review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime/phase_rejection.py')
        if not path.is_file():
            self.skipTest('旧冻结根只供本机逐字段差分；旧Peng/Pass合成回归仍必跑')
        spec = importlib.util.spec_from_file_location('previous_frozen_phase', path)
        previous = importlib.util.module_from_spec(spec); spec.loader.exec_module(previous)
        for case in (fixture(), OnlyPassPhaseRejectionCases.case()):
            self.assertEqual(prove(case), previous.prove(case['rejection'], case['records'],
                case['snapshots'], {window[:3]: count for window, count in case['post_counts'].items()}, case['adapter_counts']))


class FullWindowPostAssociationCases(unittest.TestCase):
    """原HTTP响应必须经适配器意图关联完整五元窗；不同DID不能绕过同窗重复保护。"""

    @staticmethod
    def synthetic_case():
        """同次弃牌依次进入碰窗、吃窗，各自只发送一次；不执行规则或HTTP。"""
        case = fixture()
        original = case['records'][0]['payload']['window']
        next_window = {**original, 'phase': 'response_chi'}
        next_wire = deepcopy(case['records'][3])
        next_wire['context']['decision_id'] = 'next-chi-decision'
        next_wire['payload'].update(decision_id='next-chi-decision', window=next_window,
            action_key='pass', body={'action': 'pass', 'tile': ''}, based_on_authoritative_seq=409)
        next_wire['monotonic_ns'] = 3200000000
        rejected = deepcopy(case['rejection'])
        rejected['kind'] = 'raw_protocol_state'
        rejected['payload'].update(source='action_submit_response',
            decision_id=rejected['context']['decision_id'], attempt_no=1)
        next_post = deepcopy(rejected)
        next_post['context'] = dict(next_wire['context'])
        next_post['monotonic_ns'] = 3400000000
        next_post['payload'].update(http_status=200, raw=json.dumps({'ok': True}),
            decision_id='next-chi-decision', request_timing={
                'transport_started_at_monotonic': 3.3, 'completed_at_monotonic': 3.4})
        snapshots = deepcopy(case['snapshots'])
        snapshots[0]['body']['snapshot']['turn'] = 2
        snapshots[1]['body']['snapshot'].update(phase='response_chi', turn=2, last_discard='4t')
        raw_states = [{'kind': 'raw_protocol_state', 'context': {'game_id': original['game_id']},
            'monotonic_ns': item['stamp'], 'payload': {'source': 'state_response',
                'http_status': 200, 'seq_requested': 0, 'raw': json.dumps(item['body'])}}
            for item in snapshots]
        applied = [{'kind': 'authoritative_state', 'context': {'game_id': original['game_id']},
            'monotonic_ns': item['stamp'] + 1000, 'payload': {'seq': item['body']['seq']}}
            for item in snapshots]
        return {'records': [*case['records'], next_wire],
                'raw_records': [raw_states[0], rejected, raw_states[1], next_post],
                'applied_records': applied, 'rejection': rejected}

    def scan(self, case):
        """缩小原件走生产轻扫入口；仅写临时审计，不读凭据或连接平台。"""
        import controller as runtime
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            participant = run / 'participants/synthetic'
            (participant / 'raw').mkdir(parents=True)
            (participant / 'games').mkdir()
            records = deepcopy(case['records'])
            for record in records:
                if record['kind'] == 'decision_input':
                    item = record['payload']
                    record['payload'] = {'budget': item['budget'], 'request': {
                        'window_key': item['window'],
                        'rejected_attempts': item.get('rejected_attempts'),
                        'observation': {'snapshot_seq': item['snapshot_seq'],
                                        'consumed_seq': item['consumed_seq']},
                        'rules': {'completeness': item['rule_completeness'],
                            'legal_candidates': [{'action_key': key} for key in item['legal_keys']]}}}
            for path, rows in ((participant/'decisions.jsonl', records),
                               (participant/'raw/g.jsonl', case['raw_records']),
                               (participant/'games/g.jsonl', case['applied_records'])):
                path.write_text('\n'.join(json.dumps(row) for row in rows) + '\n')
            return runtime.scan_lightweight(run, max_bytes=1048576, max_seconds=5.,
                phase_index_max_bytes=1048576, phase_index_max_seconds=5.)

    def test_peng_then_chi_same_discard_are_separate_windows(self):
        result = self.scan(self.synthetic_case())
        self.assertEqual(result['illegal_submissions'], 0)
        self.assertEqual(result['warnings']['recovered_expired_peng_window'], 1)
        self.assertEqual(result['raw_source_counts']['action_submit_response'], 2)
        self.assertEqual(result['phase_reclassification_proofs'][0]['decision_sent_attempts'], 1)

    def test_different_decisions_same_full_window_still_block(self):
        case = self.synthetic_case()
        case['records'][-1]['payload']['window']['phase'] = 'response_peng'
        result = self.scan(case)
        self.assertEqual(result['illegal_submissions'], 1)
        self.assertEqual(result['phase_reclassification_proofs'], [])
        self.assertTrue(result['phase_post_mapping']['complete'])
        self.assertEqual(result['phase_post_mapping']['mapped_post_records'], 2)

    def test_second_window_intent_without_response_still_blocks(self):
        """另一DID的同窗失败/模糊POST没有原响应，也不能漏计适配器body意图。"""
        case = self.synthetic_case()
        case['records'][-1]['payload']['window']['phase'] = 'response_peng'
        case['raw_records'].pop()
        result = self.scan(case)
        self.assertTrue(result['phase_post_mapping']['complete'])
        self.assertEqual(result['phase_post_mapping']['mapped_post_records'], 1)
        self.assertEqual(result['illegal_submissions'], 1)
        self.assertEqual(result['phase_reclassification_proofs'], [])

    def test_missing_or_conflicting_mapping_is_closed(self):
        mutators = {
            'unmapped_later_phase': lambda c: c['records'].pop(),
            'unmapped_other_trigger': lambda c: (c['records'].pop(),
                c['raw_records'][-1]['context'].update(trigger_seq=405)),
            'two_windows_same_attempt_identity': lambda c: (
                c['records'][-1]['context'].update(decision_id='synthetic-decision'),
                c['records'][-1]['payload'].update(decision_id='synthetic-decision'),
                c['raw_records'][-1]['context'].update(decision_id='synthetic-decision'),
                c['raw_records'][-1]['payload'].update(decision_id='synthetic-decision')),
            'raw_payload_context_mismatch': lambda c: c['raw_records'][-1]['payload'].update(decision_id='wrong-decision'),
            'raw_game_conflict': lambda c: c['raw_records'][-1]['context'].update(game_id='wrong-game'),
            'raw_round_conflict': lambda c: c['raw_records'][-1]['context'].update(round_no=3),
            'raw_trigger_conflict': lambda c: c['raw_records'][-1]['context'].update(trigger_seq=405),
            'raw_DID_missing': lambda c: c['raw_records'][-1]['context'].pop('decision_id'),
            'raw_DID_type': lambda c: c['raw_records'][-1]['context'].update(decision_id=1),
            'raw_attempt_missing': lambda c: c['raw_records'][-1]['context'].pop('attempt_no'),
            'raw_attempt_string': lambda c: c['raw_records'][-1]['context'].update(attempt_no='1'),
            'raw_attempt_bool': lambda c: c['raw_records'][-1]['context'].update(attempt_no=True),
            'raw_round_bool': lambda c: c['raw_records'][-1]['context'].update(round_no=True),
            'adapter_context_window_mismatch': lambda c: c['records'][-1]['payload']['window'].update(trigger_seq=405),
            'adapter_window_missing': lambda c: c['records'][-1]['payload'].pop('window'),
            'adapter_body_missing': lambda c: c['records'][-1]['payload'].update(body=None),
            'adapter_attempt_missing': lambda c: c['records'][-1]['context'].pop('attempt_no'),
            'adapter_attempt_bool': lambda c: c['records'][-1]['context'].update(attempt_no=True),
            'adapter_payload_context_mismatch': lambda c: c['records'][-1]['payload'].update(attempt_no=2),
            'adapter_payload_attempt_bool': lambda c: c['records'][-1]['payload'].update(attempt_no=True),
            'adapter_window_seat_bool': lambda c: c['records'][-1]['payload']['window'].update(seat=True),
            'adapter_intent_after_transport': lambda c: c['records'][-1].update(monotonic_ns=3500000000),
        }
        for name, mutate in mutators.items():
            with self.subTest(name=name):
                case = self.synthetic_case(); mutate(case)
                result = self.scan(case)
                self.assertEqual(result['illegal_submissions'], 1)
                self.assertEqual(result['phase_reclassification_proofs'], [])
                self.assertIsNotNone(result['warnings']['phase_index_unknown'])

    def test_actual_batch015_peng_then_chi_original_piece(self):
        """真实015原件保持409与NoRefresh；仅修复后继吃窗混入碰窗POST计数。"""
        import hashlib
        path = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[5] / '.private/t200-eoh-fast-evolution/free-incident-015-investigation-001/BATCH015-CASE.json')
        if not path.is_file():
            self.skipTest('真实015原件仅在本机私有证据；合成同窗/缺映射反控仍必跑')
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '2032d4d6065bf7fc81d351c73d603a81ca05e5f6d9ae74094f4495f1072dfaa5')
        case = json.loads(raw)
        result = self.scan(case)
        self.assertEqual(result['illegal_submissions'], 0)
        self.assertEqual(result['unrecovered_state'], 0)
        self.assertEqual(result['warnings']['explicit_rejection'], 1)
        self.assertEqual(result['warnings']['recovered_expired_peng_window'], 1)
        proof = result['phase_reclassification_proofs'][0]
        self.assertEqual(proof['actual_outcome'], 'SubmitRejectedNoRefresh')
        self.assertEqual(proof['authoritative_recovery_seq'], 237)
        self.assertAlmostEqual(proof['timely_send_margin_ms'], 628.2937079668045, places=5)
        self.assertEqual(json.loads(case['rejection']['payload']['raw']),
            {'code': 'INVALID_ACTION', 'message': 'peng only in peng window'})




class ServerClosedResponsePassCases(unittest.TestCase):
    """只用即时权威吃窗→本人摸牌及独立新决策；不借赛后timeout或本地钟推断迟到。"""

    @staticmethod
    def case():
        case = OnlyPassPhaseRejectionCases.case()
        case['records'][0]['payload']['legal_keys'] = ['chi:1w,2w,3w', 'pass']
        case['rejection']['payload']['request_timing']['completed_at_monotonic'] = 1.6
        case['rejection']['monotonic_ns'] = 1600000000
        case['records'][4]['monotonic_ns'] = 1601000000
        case['records'][5]['monotonic_ns'] = 1602000000
        pre = case['snapshots'][0]
        pre['applied_at_monotonic_ns'] = 900001000
        pre['body']['snapshot'].update(game_id='synthetic-game', turn=2,
            last_discard='3w', responding_seats=[3], my_hand=['1w', '2w'])
        following = case['snapshots'][1]
        following['applied_at_monotonic_ns'] = 3100001000
        following['body']['snapshot'].update(game_id='synthetic-game', phase='draw', turn=3)
        window = {'game_id': 'synthetic-game', 'round_no': 2, 'trigger_seq': 409,
                  'phase': 'draw', 'seat': 3}
        ctx = {'game_id': 'synthetic-game', 'decision_id': 'next-draw',
               'attempt_no': 1, 'round_no': 2, 'trigger_seq': 409}
        def row(kind, payload, stamp):
            return {'kind': kind, 'context': dict(ctx), 'payload': payload,
                    'monotonic_ns': stamp, 'original_line_sha256': 'b' * 64}
        case['records'].extend([
            row('decision_input', {'window': window, 'rule_completeness': 'complete',
                'legal_keys': ['discard:东'], 'snapshot_seq': 409, 'consumed_seq': 409,
                'rejected_attempts': [], 'budget': {'latest_send_at_monotonic': 6.}}, 3200000000),
            row('candidate_validated', {'action_key': 'discard:东', 'legal': True, 'window': window,
                'action': {'kind': 'discard', 'tile': '东', 'schema_version': 1}}, 3300000000),
            row('submission_intent', {'action_key': 'discard:东', 'window': window,
                'based_on_authoritative_seq': 409, 'latest_send_at_monotonic': 6.}, 3400000000),
            row('submission_intent', {'body': {'action': 'discard', 'tile': '东'}, 'window': window,
                'action_key': 'discard:东', 'based_on_authoritative_seq': 409,
                'decision_id': 'next-draw', 'attempt_no': 1}, 3500000000),
            row('submission_outcome', {'outcome_type': 'SubmitAccepted', 'action_key': 'discard:东',
                'decision_id': 'next-draw', 'attempt_no': 1}, 3600000000),
            row('decision_ended', {'attempt_count': 1, 'sent_attempts': 1, 'window': window}, 3700000000)])
        case['adapter_counts'][phase.window(window)] = 1
        case['post_counts'][phase.window(window)] = 1
        return case

    def test_server_closed_chi_pass_without_local_deadline_crossing(self):
        result = prove(self.case())
        self.assertIsNotNone(result)
        self.assertEqual(result['classification'], 'recovered_server_closed_response_pass')
        self.assertEqual(result['actual_outcome'], 'SubmitRejectedNoRefresh')
        self.assertEqual(result['authoritative_recovery_seq'], 409)
        self.assertIsNone(result['timely_send_margin_ms'])
        self.assertEqual(result['recovery_decision_id'], 'next-draw')
        self.assertTrue(result['clock_unknown'])
        self.assertTrue(result['closure_reason_unknown'])
        self.assertIn('possible_lost_chi', result['warning'])

    def test_missing_or_conflicting_runtime_evidence_stays_illegal(self):
        mutations = {
            'only_pass_without_new_draw': lambda c: (c['records'][0]['payload'].update(legal_keys=['pass']), c['records'].pop(6)),
            'other_legal_family': lambda c: c['records'][0]['payload']['legal_keys'].append('peng:3w'),
            'malformed_chi': lambda c: c['records'][0]['payload'].update(legal_keys=['chi:1w,2w,4w', 'pass']),
            'duplicate_legal': lambda c: c['records'][0]['payload']['legal_keys'].append('pass'),
            'incomplete_rules': lambda c: c['records'][0]['payload'].update(rule_completeness='partial'),
            'old_consumed_lags': lambda c: c['records'][0]['payload'].update(consumed_seq=403),
            'wrong_original_action': lambda c: c['records'][2]['payload'].update(action_key='chi:1w,2w,3w'),
            'wrong_body': lambda c: c['records'][3]['payload']['body'].update(tile='3w'),
            'extra_body': lambda c: c['records'][3]['payload']['body'].update(extra=True),
            'original_not_legal': lambda c: c['records'][1]['payload'].update(legal=False),
            'pre_missing': lambda c: c['snapshots'].pop(0),
            'pre_gap': lambda c: c['snapshots'][0]['body'].update(gap=True),
            'pre_not_seq0': lambda c: c['snapshots'][0].update(seq_requested=1),
            'pre_not_applied': lambda c: c['snapshots'][0].update(applied=False),
            'pre_applied_too_late': lambda c: c['snapshots'][0].update(applied_at_monotonic_ns=1600000001),
            'pre_wrong_phase': lambda c: c['snapshots'][0]['body']['snapshot'].update(phase='response_peng'),
            'pre_wrong_game': lambda c: c['snapshots'][0]['body']['snapshot'].update(game_id='other'),
            'pre_wrong_seat': lambda c: c['snapshots'][0]['body']['snapshot'].update(seat=2),
            'pre_wrong_direction': lambda c: c['snapshots'][0]['body']['snapshot'].update(turn=0),
            'pre_wrong_discard': lambda c: c['snapshots'][0]['body']['snapshot'].update(last_discard='9w'),
            'post_missing': lambda c: c['snapshots'].pop(),
            'post_gap': lambda c: c['snapshots'][1]['body'].update(gap=True),
            'post_not_seq0': lambda c: c['snapshots'][1].update(seq_requested=1),
            'post_not_applied': lambda c: c['snapshots'][1].update(applied=False),
            'post_apply_missing': lambda c: c['snapshots'][1].pop('applied_at_monotonic_ns'),
            'post_wrong_phase': lambda c: c['snapshots'][1]['body']['snapshot'].update(phase='response_peng'),
            'post_wrong_round': lambda c: c['snapshots'][1]['body']['snapshot'].update(round_no=3),
            'post_wrong_seat': lambda c: c['snapshots'][1]['body']['snapshot'].update(seat=2),
            'post_not_own_turn': lambda c: c['snapshots'][1]['body']['snapshot'].update(turn=0),
            'post_wrong_game': lambda c: c['snapshots'][1]['body']['snapshot'].update(game_id='other'),
            'post_bool_seq': lambda c: c['snapshots'][1]['body'].update(seq=True),
            'next_input_missing': lambda c: c['records'].pop(6),
            'next_input_before_applied': lambda c: c['records'][6].update(monotonic_ns=3100000000),
            'next_wrong_window': lambda c: c['records'][6]['payload']['window'].update(phase='response_chi'),
            'next_wrong_context': lambda c: c['records'][6]['context'].update(trigger_seq=410),
            'next_wrong_authority': lambda c: c['records'][6]['payload'].update(snapshot_seq=410),
            'next_rejected_attempts': lambda c: c['records'][6]['payload'].update(rejected_attempts=[{}]),
            'next_rejected_attempts_missing': lambda c: c['records'][6]['payload'].pop('rejected_attempts'),
            'next_bad_validation': lambda c: c['records'][7]['payload'].update(legal=False),
            'next_not_legal_action': lambda c: c['records'][6]['payload'].update(legal_keys=['discard:西']),
            'next_legal_missing': lambda c: c['records'][6]['payload'].update(legal_keys=None),
            'next_wrong_body': lambda c: c['records'][9]['payload']['body'].update(tile='西'),
            'next_wrong_wire_DID': lambda c: c['records'][9]['payload'].update(decision_id='other'),
            'next_submit_missing': lambda c: c['records'].pop(10),
            'next_ambiguous': lambda c: c['records'][10]['payload'].update(outcome_type='SubmitAmbiguous'),
            'next_attempt_two': lambda c: c['records'][11]['payload'].update(attempt_count=2),
            'next_sent_twice': lambda c: c['records'][11]['payload'].update(sent_attempts=2),
            'second_old_POST': lambda c: c['post_counts'].update({phase.window(c['records'][0]['payload']['window']): 2}),
            'second_old_body_intent': lambda c: c['adapter_counts'].update({phase.window(c['records'][0]['payload']['window']): 2}),
            'second_new_POST': lambda c: c['post_counts'].update({phase.window(c['records'][6]['payload']['window']): 2}),
            'second_new_body_intent': lambda c: c['adapter_counts'].update({phase.window(c['records'][6]['payload']['window']): 2}),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                case = self.case(); mutate(case); self.assertIsNone(prove(case))

    def test_compact_next_draw_preserves_empty_rejected_attempts(self):
        case = self.case()
        inp = case['records'][6]['payload']
        row = deepcopy(case['records'][6])
        row['payload'] = {'budget': inp['budget'], 'request': {
            'window_key': inp['window'], 'rejected_attempts': [],
            'observation': {'snapshot_seq': 409, 'consumed_seq': 409},
            'rules': {'completeness': 'complete', 'legal_candidates': [{'action_key': 'discard:东'}]}}}
        self.assertEqual(phase.compact(row)['payload']['rejected_attempts'], [])

    def scan_case(self, case):
        """从同一临时raw/games/decisions走真实LIGHT；不写运行根或启动玩家。"""
        rejected = deepcopy(case['rejection'])
        rejected['kind'] = 'raw_protocol_state'
        rejected['payload'].update(source='action_submit_response',
            decision_id=rejected['context']['decision_id'], attempt_no=1)
        next_post = deepcopy(rejected)
        next_post['context'] = deepcopy(case['records'][9]['context'])
        next_post['monotonic_ns'] = 3600000000
        next_post['payload'].update(decision_id='next-draw', http_status=200,
            raw=json.dumps({'ok': True}), request_timing={
                'transport_started_at_monotonic': 3.51, 'completed_at_monotonic': 3.6})
        states = [{'kind': 'raw_protocol_state', 'context': {'game_id': item['gid']},
            'monotonic_ns': item['stamp'], 'payload': {'source': 'state_response',
                'http_status': 200, 'seq_requested': item['seq_requested'], 'raw': json.dumps(item['body'])}}
            for item in case['snapshots']]
        applied = [{'kind': 'authoritative_state', 'context': {'game_id': item['gid']},
            'monotonic_ns': item['applied_at_monotonic_ns'], 'payload': {'seq': item['body']['seq']}}
            for item in case['snapshots']]
        # 真实batch007在新决定之后又记同一seq；不能用最后一次记账遮掉此前已应用事实。
        applied.append({**deepcopy(applied[-1]), 'monotonic_ns': 3800000000})
        return FullWindowPostAssociationCases().scan({'records': case['records'],
            'raw_records': [states[0], rejected, states[1], next_post], 'applied_records': applied})

    def test_light_collects_next_draw_and_only_reclassifies_one_illegal(self):
        result = self.scan_case(self.case())
        self.assertEqual(result['illegal_submissions'], 0)
        self.assertEqual(result['warnings']['explicit_rejection'], 1)
        self.assertEqual(result['warnings']['recovered_server_closed_response_pass'], 1)
        self.assertEqual(result['warnings']['possible_lost_chi'], 1)
        self.assertEqual(result['warnings']['clock_unknown'], 1)
        self.assertEqual(result['warnings']['lost_response_opportunity'], 0)
        self.assertEqual(result['warnings']['recovered_expired_only_pass_window'], 0)
        self.assertEqual(result['phase_reclassification_proofs'][0]['actual_outcome'], 'SubmitRejectedNoRefresh')

    def test_next_draw_retry_or_missing_submit_blocks_light(self):
        for label in ('missing_submit', 'second_body', 'wrong_new_window'):
            with self.subTest(label=label):
                case = self.case()
                if label == 'missing_submit': case['records'].pop(10)
                elif label == 'second_body': case['records'].append(deepcopy(case['records'][9]))
                else: case['records'][6]['payload']['window']['phase'] = 'response_peng'
                result = self.scan_case(case)
                self.assertEqual(result['illegal_submissions'], 1)
                self.assertEqual(result['phase_reclassification_proofs'], [])

    def test_three_legacy_positive_proofs_equal_frozen_window015(self):
        """新分类不改变旧Peng、Chi、唯一Pass的逐字段证据。"""
        import importlib.util
        path = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parents[5] / '.private/t199-four-step-execution/runtime-workspace/runtime-root-p0-window015-v1/review/vip-route-2026-09-30/evidence/t199-four-step-execution-1/runtime/phase_rejection.py')
        if not path.is_file(): self.skipTest('本机冻结根只供离线差分，旧三类合成反控仍必跑')
        spec = importlib.util.spec_from_file_location('frozen_window015_phase', path)
        frozen = importlib.util.module_from_spec(spec); spec.loader.exec_module(frozen)
        for case in (fixture(), OnlyPassPhaseRejectionCases.case(), ChiPhaseRejectionCases.case()):
            self.assertEqual(prove(case), frozen.prove(case['rejection'], case['records'],
                case['snapshots'], case['post_counts'], case['adapter_counts']))

    def test_old_did_future_window_attempt_two_cannot_hide_behind_window_count_one(self):
        """旧窗只发一次也不代表旧DID未跨窗重试；保留end1与未来attempt2的矛盾。"""
        case = self.case()
        future = {'game_id': 'synthetic-game', 'round_no': 2, 'trigger_seq': 410,
                  'phase': 'draw', 'seat': 3}
        for index in (2, 3, 4):
            extra = deepcopy(case['records'][index])
            extra['context'].update(attempt_no=2, trigger_seq=410)
            extra['payload'].update(window=deepcopy(future))
            if 'attempt_no' in extra['payload']: extra['payload']['attempt_no'] = 2
            extra['monotonic_ns'] = 4100000000 + index
            case['records'].append(extra)
        case['post_counts'][phase.window(future)] = 1
        case['adapter_counts'][phase.window(future)] = 1
        original = phase.window(case['records'][0]['payload']['window'])
        self.assertEqual(case['post_counts'][original], 1)
        self.assertEqual(case['records'][5]['payload']['sent_attempts'], 1)
        self.assertIsNone(prove(case))

    def test_used_old_input_validation_and_end_context_must_match_original_window(self):
        """payload窗口正确也不能替代原context的整数round/trigger身份。"""
        for index in (0, 1, 5):
            for field, value in (('round_no', 3), ('trigger_seq', 405), ('round_no', 2.0)):
                with self.subTest(index=index, field=field, value=value):
                    case = self.case()
                    case['records'][index]['context'][field] = value
                    self.assertIsNone(prove(case))


class ServerClosedOnlyPassCases(unittest.TestCase):
    """batch013仅过牌、响应早于本地截止的新窄类；所有旧类别保持原门。"""

    @staticmethod
    def case():
        case = ServerClosedResponsePassCases.case()
        case['records'][0]['payload'].update(legal_keys=['pass'], rejected_attempts=[])
        return case

    def test_only_pass_early_response_requires_complete_independent_draw_recovery(self):
        result = prove(self.case())
        self.assertIsNotNone(result)
        self.assertEqual(result['classification'], 'recovered_server_closed_only_pass')
        self.assertEqual(result['actual_outcome'], 'SubmitRejectedNoRefresh')
        self.assertIsNone(result['timely_send_margin_ms'])
        self.assertEqual(result['recovery_decision_id'], 'next-draw')
        self.assertEqual(result['recovery_actual_outcome'], 'SubmitAccepted')
        self.assertTrue(result['clock_unknown'])
        self.assertTrue(result['closure_reason_unknown'])
        self.assertNotIn('possible_lost_chi', result['warning'])
        self.assertIn('no_evidence_of_lost_claim_opportunity', result['warning'])

    def test_missing_or_conflicting_only_pass_evidence_stays_illegal(self):
        mutations = {
            'no_new_DRAW_input': lambda c: c['records'].pop(6),
            'no_new_DRAW_submission': lambda c: c['records'].pop(10),
            'no_after_snapshot': lambda c: c['snapshots'].pop(),
            'after_not_applied': lambda c: c['snapshots'][1].update(applied=False),
            'before_not_applied': lambda c: c['snapshots'][0].update(applied=False),
            'before_applied_after_input': lambda c: c['snapshots'][0].update(applied_at_monotonic_ns=1600000001),
            'wrong_after_seat': lambda c: c['snapshots'][1]['body']['snapshot'].update(seat=2),
            'wrong_after_turn': lambda c: c['snapshots'][1]['body']['snapshot'].update(turn=0),
            'wrong_after_round': lambda c: c['snapshots'][1]['body']['snapshot'].update(round_no=3),
            'after_gap': lambda c: c['snapshots'][1]['body'].update(gap=True),
            'after_not_seq0': lambda c: c['snapshots'][1].update(seq_requested=1),
            'wrong_source_phase': lambda c: c['records'][0]['payload']['window'].update(phase='response_peng'),
            'wrong_pass_wire_body': lambda c: c['records'][3]['payload']['body'].update(tile='3w'),
            'extra_pass_wire_field': lambda c: c['records'][3]['payload']['body'].update(extra=True),
            'bad_old_validation': lambda c: c['records'][1]['payload'].update(legal=False),
            'incomplete_old_rules': lambda c: c['records'][0]['payload'].update(rule_completeness='partial'),
            'old_rejected_attempts_missing': lambda c: c['records'][0]['payload'].pop('rejected_attempts'),
            'old_rejected_attempts_nonempty': lambda c: c['records'][0]['payload'].update(rejected_attempts=[{}]),
            'missing_latest': lambda c: c['records'][0]['payload']['budget'].pop('latest_send_at_monotonic'),
            'late_start': lambda c: c['rejection']['payload']['request_timing'].update(transport_started_at_monotonic=2.01),
            'NOT_QUALIFIED': lambda c: c['rejection']['payload'].update(raw=json.dumps({'code': 'NOT_QUALIFIED', 'message': 'cannot pass in phase 1'})),
            'other_error_message': lambda c: c['rejection']['payload'].update(raw=json.dumps({'code': 'INVALID_ACTION', 'message': 'tile count invalid'})),
            'old_POST_twice': lambda c: c['post_counts'].update({phase.window(c['records'][0]['payload']['window']): 2}),
            'old_body_twice': lambda c: c['adapter_counts'].update({phase.window(c['records'][0]['payload']['window']): 2}),
            'old_end_attempt_two': lambda c: c['records'][5]['payload'].update(attempt_count=2),
            'new_body_twice': lambda c: c['adapter_counts'].update({phase.window(c['records'][6]['payload']['window']): 2}),
            'new_attempt_two': lambda c: c['records'][11]['payload'].update(attempt_count=2),
            'new_same_DID': lambda c: c['records'][6]['context'].update(decision_id='synthetic-decision'),
            'new_wrong_body': lambda c: c['records'][9]['payload']['body'].update(tile='西'),
            'new_ambiguous': lambda c: c['records'][10]['payload'].update(outcome_type='SubmitAmbiguous'),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                case = self.case(); mutate(case); self.assertIsNone(prove(case))
        case = self.case()
        future = {'game_id': 'synthetic-game', 'round_no': 2, 'trigger_seq': 410, 'phase': 'draw', 'seat': 3}
        for index in (2, 3, 4):
            extra = deepcopy(case['records'][index])
            extra['context'].update(attempt_no=2, trigger_seq=410)
            extra['payload'].update(window=deepcopy(future))
            if 'attempt_no' in extra['payload']: extra['payload']['attempt_no'] = 2
            extra['monotonic_ns'] = 4100000000 + index
            case['records'].append(extra)
        case['post_counts'][phase.window(future)] = 1
        case['adapter_counts'][phase.window(future)] = 1
        self.assertIsNone(prove(case))

    def test_LIGHT_keeps_original_rejection_and_clock_unknown_without_lost_chi(self):
        result = ServerClosedResponsePassCases().scan_case(self.case())
        self.assertEqual(result['illegal_submissions'], 0)
        self.assertEqual(result['warnings']['explicit_rejection'], 1)
        self.assertEqual(result['warnings']['recovered_server_closed_only_pass'], 1)
        self.assertEqual(result['warnings']['possible_lost_chi'], 0)
        self.assertEqual(result['warnings']['clock_unknown'], 1)
        self.assertEqual(result['warnings']['closure_reason_unknown'], 1)
        self.assertEqual(result['phase_reclassification_proofs'][0]['actual_outcome'], 'SubmitRejectedNoRefresh')


if __name__ == '__main__':
    unittest.main()
