"""只读已结案开发产物，分开记录积分、阶段目标和父子差异；不新增评测。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import statistics

import strong_seed_batch as b
import diverse_second_panel as second


def diagnose():
    """核验共同基线和完整清单，输出可复查分层；不对缺失动作轨迹作因果归因。"""
    out = second.OUT / 'failure-stratification.json'
    assert not out.exists(), '保留已冻结诊断'
    summary = b.read(second.OUT / 'summary.json')
    assert summary['status'] == 'COMPLETE_SEEN_DEVELOPMENT'
    rows, differences = [], []
    for name in ('parent', 'simplify-terra-max'):
        closure = b.read(second.OUT / name / 'closure.json')
        assert closure['spent']['tables_full'] == 256
        for mix in ('H', 'M'):
            panel = b.read(second.OUT / name / ('natural-' + mix) / 'panel.json')
            parent = b.read(second.OUT / 'parent' / ('natural-' + mix) / 'panel.json')
            stats = next(iter(panel['statistics']['by_candidate'].values()))['panels']['normal']['panels'][mix]
            assert stats['manifest_complete'] and stats['n_invalid_roots'] == 0
            index = {(s['root_index'], s['focal_anchor_seat']): s for s in parent['samples']}
            equal = {'baseline': 0, 'candidate': 0}
            score_deltas = []
            counts = {k: 0 for k in ('illegal_choices', 'fallbacks', 'timeouts', 'audit_missing', 'auto_actions')}
            for sample in panel['samples']:
                p = index[(sample['root_index'], sample['focal_anchor_seat'])]
                assert sample['root_content_digest'] == p['root_content_digest']
                score_deltas.append(sample['arms']['candidate']['focal_stage_score'] - sample['arms']['baseline']['focal_stage_score'])
                for arm in ('baseline', 'candidate'):
                    for a, z in zip(sample['raw_arms'][arm]['tables'], p['raw_arms'][arm]['tables'], strict=True):
                        assert a['seed'] == z['seed'] and a['table_id'] == z['table_id']
                        keys = ('scores_before', 'scores_after', 'completed_hands', 'expected_hands', 'runtime_counts', 'status', 'invalid_reasons')
                        same = all(a['result'][k] == z['result'][k] for k in keys)
                        equal[arm] += int(same)
                        if arm == 'baseline':
                            assert same
                        else:
                            for k in counts:
                                counts[k] += a['result']['runtime_counts'][k]
                            if not same:
                                differences.append({'source': name, 'mix': mix, 'root': sample['root_index'], 'seat': sample['focal_anchor_seat'], 'table_id': a['table_id']})
            roots = stats['root_rows']
            rows.append({'source': name, 'mix': mix, 'mean_stage_utility_delta_vs_v2': stats['mean_delta'],
                'identification_bounds': [stats['delta_bounds']['mean_delta_low'], stats['delta_bounds']['mean_delta_high']],
                'positive_roots': sum(r['d_point'] > 0 for r in roots),
                'negative_roots': sum(r['d_point'] < 0 for r in roots),
                'zero_roots': sum(r['d_point'] == 0 for r in roots),
                'unresolved_roots': stats['delta_bounds']['unresolved_roots'],
                'mean_focal_stage_score_delta_vs_v2': statistics.mean(score_deltas),
                'terminal_equal_to_parent': equal, 'candidate_runtime_counts': counts})
    report = {'status': 'COMPLETE_DIAGNOSTIC_ONLY', 'rows': rows, 'terminal_differences': differences,
        'model_calls': 0, 'additional_tables': 0, 'release_eligible': False,
        'limits': ['终局分层不识别具体错误动作或负向因果机制', '积分差是诊断项，不能替代冻结阶段目标',
                   '识别区间不是抽样置信区间；清单已经多次用于开发', '逻辑时钟零异常不证明真实时限通过',
                   '根内四座位配置相关；不将64候选桌赛计为64独立来源根']}
    b.write(out, report)
    print(rows)


if __name__ == '__main__':
    diagnose()
