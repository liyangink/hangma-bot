"""按预登记分流在第二已见清单复核；共享一个新核心父代，不把开发复用冒充确认。"""

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
import argparse
import statistics

import strong_seed_batch as b
import diverse_proposal_batch as batch
import route_executor_recovery as engine

OUT = b.HERE / 'diverse-second-dev-20260920'
NAMES = ('parent', *batch.CONFIGS)


def eligible(name):
    """只有完整第一清单的固定分流已通过才执行该提案，不据中途数值追加。"""
    if name == 'parent':
        return True
    path = batch.OUT / name / 'development-decision.json'
    return path.exists() and b.read(path)['continue_second_seen_panel'] is True


def prepare():
    """先冻结全部可能来源与同一根设计；负来源不运行、不结算成已执行。"""
    assert not OUT.exists()
    assert any(eligible(name) for name in batch.CONFIGS)
    first = b.read(batch.OUT / 'manifest.json')
    original = b.read(engine.OUT / 'manifest.json')
    paths = {'parent': b.Path(first['parent']) / 'candidate.py'}
    paths.update({name: batch.OUT / name / 'run/iterations/iter-01/generation/candidate.py' for name in batch.CONFIGS})
    plan = {**original, 'created_at_utc': b.search.utc_now(), 'panel_seed': 2026092097,
        'sources': {name: {'path': str(path), 'sha256': b.digest(path.read_bytes())} for name, path in paths.items()},
        'full_tables': None, 'max_full_tables': 768, 'tables_per_source': 256,
        'scope': '第二已见开发清单；只有第一清单分流通过者运行，父代共享一次；非独立确认',
        'old_results': '旧核心该清单结果仅背景；当前所有比较来源重新在共同新核心评价，不混身份。',
        'decision_rule': '第一清单通过且本清单H/M对V2均正、对父代等权识别差下界正，才待新开发验证；否则拒绝本批效果晋升。',
        'model_calls': 0, 'confirmation_roots': 0, 'release_eligible': False}
    engine.verify(plan)
    OUT.mkdir()
    b.write(OUT / 'manifest.json', plan)
    for name in NAMES:
        sub = OUT / name
        sub.mkdir()
        auth = b.unified_document(batch_label='second-dev-' + name,
            authorization_id='r10-second-dev-' + name, accounts={'tables_full': 256},
            issued_by='lead', issued_at_utc=b.search.utc_now(), legacy_alias=False)
        auth['issuance_basis'] = '用户持续推进授权；第一清单固定分流为前置，第二已见清单至多256桌/来源，零作者调用'
        b.write(sub / 'authorization.json', auth)
    b.write(OUT / 'prepared.json', {'status': 'READY', 'at_utc': b.search.utc_now()})
    print({'prepared': str(OUT), 'eligible_now': [name for name in NAMES if eligible(name)]})


def run(name):
    """复用已验证的固定来源运行器；启动前再检查第一清单完整分流。"""
    assert eligible(name), '第一清单尚未满足继续条件，不启动、不追加费用'
    if name != 'parent':
        b.write(OUT / name / 'first-panel-eligibility.json', {
            'decision_sha256': b.digest((batch.OUT / name / 'development-decision.json').read_bytes()),
            'closure_sha256': b.digest((batch.OUT / name / 'batch-closure.json').read_bytes())})
    engine.OUT = OUT
    engine.run(name)


def close():
    """全部已通过来源完成后，核验共同V2臂并按第二清单固定规则分流。"""
    plan = b.read(OUT / 'manifest.json')
    engine.verify(plan)
    assert not (OUT / 'summary.json').exists()
    assert all((batch.OUT / name / 'development-decision.json').exists() for name in batch.CONFIGS)
    selected = [name for name in batch.CONFIGS if eligible(name)]
    for name in ['parent', *selected]:
        assert b.read(OUT / name / 'closure.json')['status'] == 'COMPLETE_DEVELOPMENT_ONLY'
    reports = []
    for name in selected:
        stats, pairs = {}, []
        for mix in plan['opponents']:
            panel = b.read(OUT / name / ('natural-' + mix) / 'panel.json')
            parent = b.read(OUT / 'parent' / ('natural-' + mix) / 'panel.json')
            stats[mix] = next(iter(panel['statistics']['by_candidate'].values()))['panels']['normal']['panels'][mix]
            index = {(s['root_index'], s['focal_anchor_seat']): s for s in parent['samples']}
            by_root = {i: [] for i in plan['roots']}
            for sample in panel['samples']:
                p = index[(sample['root_index'], sample['focal_anchor_seat'])]
                assert sample['root_content_digest'] == p['root_content_digest']
                for key in ('stage_totals_by_participant', 'stage_place_points_by_participant', 'u_low', 'u_high'):
                    assert sample['raw_arms']['baseline'][key] == p['raw_arms']['baseline'][key]
                a, z = sample['arms']['candidate'], p['arms']['candidate']
                by_root[sample['root_index']].append((a['u_low'] - z['u_high'], a['u_high'] - z['u_low']))
            for root, values in by_root.items():
                assert len(values) == 4
                pairs.append({'mix': mix, 'root': root, 'low': statistics.mean(v[0] for v in values),
                              'high': statistics.mean(v[1] for v in values)})
        low, high = statistics.mean(p['low'] for p in pairs), statistics.mean(p['high'] for p in pairs)
        reports.append({'name': name, 'statistics': stats, 'paired_roots': pairs,
            'equal_mix_vs_v2': statistics.mean(s['mean_delta'] for s in stats.values()),
            'parent_difference_low': low, 'parent_difference_high': high,
            'continue_new_development': low > 0 and all(s['mean_delta'] > 0 for s in stats.values())})
    b.write(OUT / 'summary.json', {'status': 'COMPLETE_SEEN_DEVELOPMENT', 'reports': reports,
        'full_tables_verified': 256 * (1 + len(selected)), 'not_run': [name for name in batch.CONFIGS if name not in selected],
        'model_calls': 0, 'confirmation_roots': 0, 'release_eligible': False})
    print([{k: row[k] for k in ('name', 'equal_mix_vs_v2', 'parent_difference_low', 'continue_new_development')} for row in reports])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run', 'close'])
    parser.add_argument('--name', choices=NAMES)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.action == 'close':
        close()
    elif args.name:
        run(args.name)
    else:
        parser.error('run需要name')
