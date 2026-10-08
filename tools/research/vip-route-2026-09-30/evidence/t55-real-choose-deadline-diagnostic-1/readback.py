"""只读核验六次真实 choose、完整实际输入、默认预算和原评分对账。

不会重新评分或推进世界。--write-receipt 只首次保存本目录独立读回收据；
其后验证原封条。结果区分研发评分完整、实际预算缺口与未测官方接线。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t55-real-choose-deadline-diagnostic-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT
REFERENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t54-public-count-native-cache-1/SCORING-CLOSURE.json')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locate(recorded_path):
    """只把原证据路径映射为本仓review下同原件；不读取旧机器的任意路径。"""
    parts = Path(recorded_path).parts
    suffix = Path(*parts[parts.index('review'):])
    assert '..' not in suffix.parts
    return _project_file(_PROJECT_ROOT, REPO / suffix)


def audit():
    reference = json.loads(REFERENCE.read_text())
    expected = {row['label']: row for row in reference['rows']}
    assert reference['complete']
    actual_inputs, rows = 0, []
    for prefix, count in (('V2-', 5), ('PROFILE-', 1)):
        plan = json.loads((_project_file(_PROJECT_ROOT, HERE / (prefix + 'PLAN.json'))).read_text())
        closure = json.loads((_project_file(_PROJECT_ROOT, HERE / (prefix + 'CLOSURE.json'))).read_text())
        assert closure['complete'] and closure['source_identity_stable']
        assert closure['candidate_identity'] == plan['candidate_identity'] == reference['runtime_identity']
        assert closure['actual_choose_and_score_calls'] == closure['actual_full_inputs_readback'] == count
        assert not closure['online_admission'] and closure['normal_r18_fallbacks'] == 0
        assert plan['candidate_score_call_limit'] == count
        assert plan['budget'] == {'post_reserve_seconds': 0.10, 'enhancement_fraction': 0.5, 'fallback_fraction': 0.7}
        for path, digest in plan['frozen_files'].items():
            assert sha(locate(path)) == digest, path
        by_label = {row['label']: row for row in closure['rows']}
        assert len(by_label) == len(closure['rows']) == count
        seen = set()
        with gzip.open(_project_file(_PROJECT_ROOT, HERE / (prefix + 'ACTUAL-INPUTS-BEFORE-SCORE.jsonl.gz')), 'rt', encoding='utf-8') as stream:
            for line in stream:
                item = json.loads(line)
                label = item['label']
                assert label not in seen
                seen.add(label)
                row, old = by_label[label], expected['public:' + label.split(':')[1]]
                assert row['status'] == 'SCORED' and row['all_legal_scores_traces_operations_equal']
                assert hashlib.sha256(canonical(item['candidate_view'])).hexdigest() == item['view_sha256'] == row['actual_input_sha256'] == old['view_sha256']
                assert canonical(row['actual_full_scores']) == canonical(old['scores'])
                assert row['operations'] == old['operations']
                assert set(row['actual_full_scores']) == {action['action_key'] for action in item['candidate_view']['actions']}
                assert row['elapsed_including_capture_seconds'] >= row['elapsed_minus_capture_seconds'] > 0
                assert abs(row['elapsed_minus_capture_seconds'] + row['capture_seconds'] - row['elapsed_including_capture_seconds']) < 1e-8
                assert row['ready_before_fallback'] == (row['elapsed_including_capture_seconds'] <= row['fallback_budget_seconds'])
                assert row['ready_before_latest_send'] == (row['elapsed_including_capture_seconds'] <= row['latest_send_budget_seconds'])
                rows.append(row)
        assert seen == set(by_label)
        actual_inputs += len(seen)
    assert actual_inputs == len(rows) == 6
    unprofiled = rows[:5]
    assert [row['ready_before_fallback'] for row in unprofiled] == [False, False, True, True, True]
    assert all(row['elapsed_minus_capture_seconds'] > row['fallback_budget_seconds'] for row in unprofiled[:2])
    assert all(row['event_loop_timer_lag_seconds'] > 2 for row in unprofiled[:2])
    files = {path.relative_to(HERE).as_posix(): sha(path) for path in HERE.iterdir()
             if path.is_file() and path.name != 'ROOT-READBACK.json'}
    return {'schema': 't55-root-readback/1', 'complete': True,
            'actual_choose_scores_full_inputs': 6, 'unprofiled_budget_misses': 2,
            'profiled_calls_not_deadline_credit': 1,
            'all_legal_scores_traces_operations_equal': True,
            'candidate_id': reference['runtime_identity']['candidate_id'],
            'full_archive_sha256': files, 'new_scores_worlds_tables_in_readback': 0,
            'online_admission': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--write-receipt', action='store_true')
    args = parser.parse_args()
    result = audit()
    receipt = _project_file(_PROJECT_ROOT, HERE / 'ROOT-READBACK.json')
    if args.write_receipt:
        with receipt.open('xb') as stream:
            stream.write(canonical(result) + b'\n')
    else:
        assert result == json.loads(receipt.read_text())
    print({'verified': True, 'actual_choose_inputs_scores': 6,
           'unprofiled_budget_misses': 2, 'new_scores_worlds_tables': 0})
