"""整批终点后的纯文件复核：全部实际输入、评分收据及合法有限输出。

不重新评分、不调用规则、不创建世界；母牌山仍按整批预登记统计。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t77-net-upgrade-fresh-qualifier-pilot-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
from collections import Counter
import gzip
import hashlib
import json
import math

HERE = Path(__file__).resolve().parent


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def rows(path):
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def main():
    closed = json.loads((_project_file(_PROJECT_ROOT, HERE / 'CAMPAIGN-CLOSURE.json')).read_text())
    assert closed['whole_batch_valid'] and closed['actual_started_tables'] == 64
    candidate_id = 'vip:' + closed['candidate_identity']['candidate_id']
    score_calls = action_scores = decisions = unique_views = 0
    selected = Counter()
    by_root = {}
    dealer = {a: {k: {'hands': 0, 'score': 0} for k in ('dealer', 'nondealer')} for a in ('A', 'C')}
    for block in range(1, 5):
        out = _project_file(_PROJECT_ROOT, HERE / ('block-' + format(block, '02d')))
        summary = json.loads((out / 'summary.json').read_text())
        assert summary['development_complete'] and summary['identity_stable'] and not summary['issues']
        archive = {}
        for row in rows(out / 'views.jsonl.gz'):
            raw = canonical(row['view'])
            key = row['view_sha256']
            assert hashlib.sha256(raw).hexdigest() == key and len(raw) == row['json_bytes']
            assert key not in archive
            keys = [a['action_key'] for a in row['view']['actions']]
            assert keys and len(set(keys)) == len(keys)
            archive[key] = (len(raw), set(keys))
        calls, used = set(), set()
        block_decisions = 0
        for row in rows(out / 'decisions.jsonl.gz'):
            block_decisions += 1
            assert row['status'] == 'chosen' and row['selected_action_key'] in row['legal_action_keys']
            if row['policy_id'] != candidate_id:
                continue
            assert row['c_self_scored'] and row['scoring_cumulative_failed_calls'] == 0
            assert not row['degraded_reasons']
            selected[row['selected_action_key'].split(':', 1)[0]] += 1
            candidates = row['candidates']
            keys = [c['action_key'] for c in candidates]
            assert len(set(keys)) == len(keys) and set(keys) == set(row['legal_action_keys'])
            assert all(type(c['score']) in (int, float) and math.isfinite(c['score']) for c in candidates)
            assert candidates[0]['action_key'] == row['selected_action_key']
            action_scores += len(candidates)
            assert row['scoring_calls']
            for call in row['scoring_calls']:
                receipt = call['input_capture']
                assert call['score_completed'] and call['full_legal_keys'] and call['cumulative_failed_calls'] == 0
                assert receipt['saved_before_score'] and receipt['error'] is None
                seq = receipt['store_call_no']
                assert seq not in calls
                calls.add(seq)
                digest = receipt['view_sha256']
                assert digest in archive and archive[digest][0] == receipt['json_bytes']
                assert archive[digest][1] == set(call['scored_action_keys']) == set(keys)
                used.add(digest)
                score_calls += 1
        terminal = summary['scoring_input_capture']['terminal']
        assert terminal['terminal_valid'] and sha(out / 'views.jsonl.gz') == terminal['compressed_sha256']
        assert len(archive) == terminal['verified_unique_views'] and used == set(archive)
        assert calls == set(range(1, summary['scoring_input_capture']['store_calls'] + 1))
        assert block_decisions == summary['decision_windows']
        decisions += block_decisions
        unique_views += len(archive)
        for row in rows(out / 'settlements.jsonl.gz'):
            s = row['settlement']
            seat = row['focal_physical_seat']
            arm = 'C' if row['match_id'].endswith(':' + candidate_id) else 'A'
            root = by_root.setdefault(row['root_id'], {a: {'hands': 0, 'score': 0, 'own_ge4': 0} for a in ('A', 'C')})
            root[arm]['hands'] += 1
            root[arm]['score'] += s['score_delta'][seat]
            root[arm]['own_ge4'] += int(not s['is_draw'] and s['winner_seat'] == seat and s['fan'] >= 4)
            kind = 'dealer' if s['dealer_seat'] == seat else 'nondealer'
            dealer[arm][kind]['hands'] += 1
            dealer[arm][kind]['score'] += s['score_delta'][seat]
    assert decisions == closed['decision_windows'] and unique_views == closed['actual_complete_views']
    assert len(by_root) == 8 and all(root[a]['hands'] == 32 for root in by_root.values() for a in ('A', 'C'))
    for arm in ('A', 'C'):
        assert sum(v[arm]['score'] for v in by_root.values()) == closed['realized_net_by_arm'][arm]
        assert sum(v['score'] for v in dealer[arm].values()) == closed['realized_net_by_arm'][arm]
    files = {str(p.relative_to(HERE)): {'bytes': p.stat().st_size, 'sha256': sha(p)}
             for p in sorted(HERE.rglob('*')) if p.is_file() and p.name != 'ROOT-READBACK.json'
             and '__pycache__' not in p.parts and '.locks' not in p.parts}
    result = {'schema': 't77-whole-actual-input-readback/1', 'complete': True,
        'actual_tables': 64, 'actual_hands': 512, 'independent_roots': 8,
        'actual_all_seat_decisions': decisions, 'actual_candidate_score_calls': score_calls,
        'actual_finite_action_score_outputs': action_scores, 'unique_complete_actual_views_readback': unique_views,
        'all_capture_refs_and_legal_outputs_reconciled': True, 'realized_by_root': by_root,
        'dealer_and_nondealer_actual_sums': dealer, 'candidate_selected_action_counts': dict(selected),
        'source_stable': True, 'files': files, 'new_models_scores_worlds_tables': 0,
        'confirmation_admission_publication': False}
    with (_project_file(_PROJECT_ROOT, HERE / 'ROOT-READBACK.json')).open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print({k: result[k] for k in ('complete', 'actual_tables', 'actual_hands',
        'actual_candidate_score_calls', 'unique_complete_actual_views_readback', 'actual_finite_action_score_outputs')})


if __name__ == '__main__':
    main()
