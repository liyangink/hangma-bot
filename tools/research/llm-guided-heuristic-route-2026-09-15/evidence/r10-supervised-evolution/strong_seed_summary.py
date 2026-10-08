"""汇总六份已结案种子；保留分层不确定性与实际运行成本。"""

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
import collections
import json

import strong_seed_batch as batch


def summarize():
    """只读完整结案；不以提前返回结果改变比较清单。"""
    output = batch.BATCH / 'batch-summary.json'
    if output.exists():
        raise SystemExit('汇总已冻结，不覆盖')
    rows = []
    for name, (model, effort, task) in batch.CONFIGS.items():
        sub = batch.BATCH / name
        closure = batch.read(sub / 'batch-closure.json')
        if closure['full_natural_results_verified'] != 256:
            raise ValueError('候选缺完整自然结果')
        state = batch.search.av_state_load(batch.search.av_latest_state_path(sub / 'run'))
        ok, why, _ = batch.search.av_verify_run_identity(state)
        if not ok:
            raise ValueError(why)
        idir = batch.Path(state['iter_dir'])
        runtime = collections.Counter()
        uncertainty = {}
        for mix in ['H', 'M']:
            panel = batch.read(idir / ('natural-' + mix) / 'panel.json')
            stats = next(iter(panel['statistics']['by_candidate'].values()))['panels']['normal']['panels'][mix]
            uncertainty[mix] = {k: stats[k] for k in ['n_roots', 'mean_delta', 'standard_error', 'interval_95', 'interval_kind', 'delta_bounds']}
            for sample in panel['samples']:
                for table in sample['raw_arms']['candidate']['tables']:
                    runtime.update(table['result']['runtime_counts'])
        comparison = batch.read(sub / 'real-parent-comparison.json')['comparison']
        rows.append({'name': name, 'requested_model': model, 'effort': effort, 'task': task,
                     'source_sha256': closure['candidate_source_sha256'],
                     'equal_mix_vs_v2': closure['equal_mix_vs_v2'],
                     'versus_parents': closure['versus_parents'],
                     'uncertainty': uncertainty, 'candidate_arm_runtime_counts': dict(runtime),
                     'full_order_changes_on_32': len(comparison['changed_windows']),
                     'first_choice_changes_on_32': len(comparison['changed_first_choices']),
                     'spent': closure['spent'],
                     'source_review': str(sub / 'source-review.json')})
    result = {'schema': 'strong-seed-summary/1', 'completed_at_utc': batch.search.utc_now(),
              'status': 'COMPLETE_DEVELOPMENT_ONLY', 'rows': rows,
              'native_initial_calls': 6, 'native_repair_calls': 1,
              'native_actual_tokens': None, 'external_glm_calls_this_batch': 0,
              'natural_full_tables': 2048,
              'all_full_tables_including_conditional': 512 + sum(r['spent']['tables_full'] for r in rows),
              'partial_tables': sum(r['spent']['tables_partial'] for r in rows),
              'prefix_generation': sum(r['spent']['prefix_generation'] for r in rows),
              'confirmation_roots': 0, 'release_eligible': False,
              'limitations': ['各困难题模型仅一份初答，不能排名模型',
                              '区间是既有开发正态近似诊断，不是选择后有效的发布显著性',
                              '识别区间与抽样区间分开保留，不把缺失平分依据当成确定名次',
                              '运行计数来自本地逻辑时钟模拟，不能替代官方时限与赛事可靠性门禁']}
    batch.write(output, result)
    print(json.dumps({'status': result['status'], 'rows': [{k: r[k] for k in ['name', 'equal_mix_vs_v2', 'versus_parents']} for r in rows]}, ensure_ascii=False))


if __name__ == '__main__':
    summarize()
