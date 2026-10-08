"""整段父／子／R18续打终态后纯读验证，无首手强制。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1/S01-continuation-root009'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import json
import math
from pathlib import Path
from io_helpers import HERE, canonical, pin, save


def rows(path):
    """完整读取压缩记录；截断、缺件及错误不转成零费用。"""
    with gzip.open(path, 'rt') as stream:
        for line in stream:
            yield json.loads(line)


def main():
    terminal = json.loads((_project_file(_PROJECT_ROOT, HERE / 'CAUSAL-TOOL-TERMINAL.json')).read_text())
    assert type(terminal['exit_code']) is int and terminal['exit_code'] == 0
    assert terminal['verified_tool_terminal']
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'RUN-PREPARED.json')).read_text())
    closed = json.loads((_project_file(_PROJECT_ROOT, HERE / 'CAUSAL-CLOSURE.json')).read_text())
    assert closed['complete'] and closed['source_stable'] and not closed['cleanup_errors']
    for name, expected in plan['files'].items():
        assert pin(name) == expected
    archive = {}
    for row in rows(_project_file(_PROJECT_ROOT, HERE / 'CAUSAL-VIEWS.jsonl.gz')):
        raw = canonical(row['view'])
        digest = row['view_sha256']
        assert digest not in archive and hashlib.sha256(raw).hexdigest() == digest
        assert len(raw) == row['json_bytes']
        archive[digest] = set(a['action_key'] for a in row['view']['actions'])
    groups, calls, used = {}, set(), set()
    finite_outputs = 0
    for row in rows(_project_file(_PROJECT_ROOT, HERE / 'CAUSAL-DECISIONS.jsonl.gz')):
        assert row['status'] == 'chosen' and row['selected_action_key'] in row['legal_action_keys']
        # C正常路径必须无降级；其他策略的三个既有审计说明并非失败或回退。
        if row['focal_vip']:
            assert not row['degraded_reasons']
        else:
            allowed = {
                '评分兼容视图[legacy-pass-neutral-v1]：可信过牌恢复旧中性基线；原始规则事实不改写',
                '抓打圈生效：排序仅在规则允许的硬约束候选内进行',
                'action_value: r18_integrated_positive_v2 评分完成',
            }
            assert set(row['degraded_reasons']) <= allowed
        groups.setdefault((row['root_id'], row['arm']), []).append(row)
        if not row['focal_vip']:
            continue
        assert row['c_self_scored'] and len(row['scoring_calls']) == 1
        call = row['scoring_calls'][0]
        receipt = call['input_capture']
        assert call['status'] == 'SCORED' and call['full_legal_keys'] and call['actual_score_calls'] == 1
        assert receipt['saved_before_score'] and receipt['error'] is None
        digest, seq = receipt['view_sha256'], receipt['store_call_no']
        assert seq not in calls and digest in archive
        assert archive[digest] == set(row['legal_action_keys']) == set(call['scored_action_keys'])
        assert set(c['action_key'] for c in row['candidates']) == archive[digest]
        assert all(type(c['score']) in (int, float) and math.isfinite(c['score']) for c in row['candidates'])
        calls.add(seq)
        used.add(digest)
        finite_outputs += len(row['candidates'])
    capture = closed['scoring_input_capture']
    assert capture['terminal']['closed'] and capture['terminal']['terminal_valid']
    assert pin(_project_file(_PROJECT_ROOT, HERE / 'CAUSAL-VIEWS.jsonl.gz'))['sha256'] == capture['terminal']['compressed_sha256']
    assert calls == set(range(1, capture['store_calls'] + 1)) and used == set(archive)
    assert len(calls) == closed['actual_explicit_api_counts']['actual_vip_score_calls']
    reconciled = []
    for target in plan['targets']:
        for arm in ('P', 'C', 'A'):
            outcome = json.loads((_project_file(_PROJECT_ROOT, HERE / target['name'] / (arm + '-OUTCOME.json'))).read_text())
            result = json.loads((_project_file(_PROJECT_ROOT, HERE / target['name'] / (arm + '-RESULT.json'))).read_text())
            actual = groups[(target['name'], arm)]
            assert outcome['status'] == 'complete' and outcome['completed_hands'] == 1
            assert len(actual) == len(outcome['decisions']) == result['actual_decisions']
            mismatches = []
            for index, (record, executed) in enumerate(zip(actual, outcome['decisions'])):
                assert record['window_key'] == executed['window_key'] and record['seat'] == executed['seat']
                if record['selected_action_key'] != executed['action_key']:
                    mismatches.append(index)
                    raise AssertionError('整段候选不得强制或改写实际选择')
                    assert executed['window_key']['trigger_seq'] == target['trigger_seq']
            assert mismatches == []
            assert result['forced_first_count'] == 0
            if mismatches:
                reconciled.append({'target': target['name'], 'arm': arm,
                                   'policy_original_first': actual[0]['selected_action_key'],
                                   'actually_executed_first': target['forced_first']})
    assert len(groups) == plan['max_continuations'] == 6
    save(_project_file(_PROJECT_ROOT, HERE / 'ROOT-READBACK.json'), {'complete': True, 'actual_tool_terminal': terminal,
         'actual_candidate_scores': len(calls), 'finite_legal_outputs': finite_outputs,
         'unique_actual_views': len(archive), 'forced_first_reconciliations': reconciled,
         'results': closed['results'], 'new_models_rules_scores_worlds_tables_in_readback': 0,
         'known_independent_development_sources': 1, 'fresh_confirmation': False,
         'source_identity': plan['candidate_identity'], 'child_identity': plan['child_identity'], 'published': False})
    print({'complete': True, 'actual_scores': len(calls), 'finite_outputs': finite_outputs,
           'results': [{k: r[k] for k in ('target', 'C_minus_P', 'A_minus_P')} for r in closed['results']]})


if __name__ == '__main__':
    main()
