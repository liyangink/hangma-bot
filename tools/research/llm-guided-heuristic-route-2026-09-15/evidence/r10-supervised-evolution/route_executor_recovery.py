"""执行器修复后的原源码对照：重新准入、冻结新身份并核验512个完整桌赛。"""

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
import route_group_batch as experiment
import route_group_probe as probe
import sitin_natural_panel as natural
from verify_full_natural_results import verify_full_panel
from hangma_bot.simulation.artifacts import compute_rules_hash

OUT = b.HERE / 'route-executor-recovery-20260920'
OLD = experiment.ROOT / experiment.NAME
NAMES = ('parent', 'candidate')


def verify(plan):
    """所有执行前后验证核心、规则、合同与原始候选身份。"""
    assert b.search.av_gates().av_deps_digest() == plan['deps_digest']
    assert compute_rules_hash(b.ROUTE.parents[1]) == plan['rules_hash']
    assert b.digest((b.ROUTE / 'contracts/group-dev-v1.json').read_bytes()) == plan['contract_sha256']
    for spec in plan['sources'].values():
        assert b.digest(b.Path(spec['path']).read_bytes()) == spec['sha256']


def prepare():
    """一次性冻结，不新增模型调用，不借旧准入或旧核心成绩直接晋升。"""
    assert not OUT.exists()
    assert b.read(OLD / 'executor-defect-disposition.json')['evaluation_exit_code'] == 0
    assert b.read(OLD / 'route-arithmetic-after-executor-fix.json')['status'] == 'PASS'
    paths = {'parent': experiment.PARENT / 'candidate.py',
             'candidate': OLD / 'run/iterations/iter-01/generation/candidate.py'}
    plan = {'created_at_utc': b.search.utc_now(), 'deps_digest': b.search.av_gates().av_deps_digest(),
            'rules_hash': compute_rules_hash(b.ROUTE.parents[1]),
            'contract_sha256': b.digest((b.ROUTE / 'contracts/group-dev-v1.json').read_bytes()),
            'sources': {name: {'path': str(p), 'sha256': b.digest(p.read_bytes())} for name, p in paths.items()},
            'panel_seed': 2026092001, 'roots': list(range(1, 9)), 'opponents': ['H', 'M'],
            'tables_per_source': 256, 'full_tables': 512, 'model_calls': 0, 'confirmation_roots': 0,
            'old_results': '保留旧身份故障证据；跨核心结果只作诊断，父子选留使用本批共同新核心',
            'decision_rule': '修复候选H/M对V2均正且同新核心对父代等权差下界正，才进入第二已见开发清单；否则停止本机制效果投入。下界为平分识别界，不是置信区间。',
            'release_eligible': False}
    verify(plan)
    OUT.mkdir()
    b.write(OUT / 'manifest.json', plan)
    old_panel = b.read(probe.PANEL)
    old_panel['refrozen_from_sha256'] = b.digest(probe.PANEL.read_bytes())
    old_panel['original_execution_deps_digest'] = old_panel['execution_deps_digest']
    old_panel['execution_deps_digest'] = plan['deps_digest']
    b.write(OUT / 'route-invariance-panel.json', old_panel)
    probe.PANEL = OUT / 'route-invariance-panel.json'
    for name, path in paths.items():
        sub = OUT / name
        sub.mkdir()
        admission = b.search.av_gates().admit_action_value(path.read_text())
        b.write(sub / 'admission.json', admission)
        assert admission['execution_safety_pass'], (name, admission)
        invariance = probe.compare_source(path)
        b.write(sub / 'route-invariance.json', invariance)
        if name == 'candidate':
            assert invariance['invariant'] == invariance['cases'] == 12
        auth = b.unified_document(batch_label='executor-recovery-' + name,
            authorization_id='r10-executor-recovery-' + name,
            accounts={'tables_full': 256}, issued_by='lead', issued_at_utc=b.search.utc_now(), legacy_alias=False)
        auth['issuance_basis'] = '用户持续推进授权；执行器缺陷修复，原父子源码各256桌，零作者调用、零独立确认'
        b.write(sub / 'authorization.json', auth)
        print(name, 'admitted', 'invariant', invariance['invariant'], flush=True)
    verify(plan)
    b.write(OUT / 'prepared.json', {'status': 'READY', 'at_utc': b.search.utc_now()})


def run(name):
    """每来源运行固定H/M各8根；有启动标志时拒绝隐式重跑。"""
    plan = b.read(OUT / 'manifest.json')
    assert b.read(OUT / 'prepared.json')['status'] == 'READY'
    verify(plan)
    sub = OUT / name
    assert not (sub / 'started.json').exists()
    b.write(sub / 'started.json', {'at_utc': b.search.utc_now()})
    auth = b.read(sub / 'authorization.json')
    source = b.Path(plan['sources'][name]['path']).read_text()
    contract = b.read(b.ROUTE / 'contracts/group-dev-v1.json')
    checks = []
    for mix in plan['opponents']:
        verify(plan)
        natural.run_natural_panel(candidate_source=source, opponent=mix, roots=8, seats_per_root=4,
            contract=contract, out_dir=sub / ('natural-' + mix), authorization=auth,
            panel_seed=plan['panel_seed'], ledger_path=sub / 'ledger.json',
            ledger_authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth), min_roots=8)
        panel = b.read(sub / ('natural-' + mix) / 'panel.json')
        assert panel['identity']['candidate_source_sha256'] == plan['sources'][name]['sha256']
        assert panel['identity']['panel_seed'] == plan['panel_seed']
        checks.append(verify_full_panel(panel, contract, expected_identity=panel['identity'],
            expected_root_indices=plan['roots'], expected_rules_hash=plan['rules_hash']))
        print(name, mix, checks[-1]['full_results_verified'], flush=True)
    verify(plan)
    ledger = b.read(sub / 'ledger.json')
    assert ledger['spent']['tables_full'] == 256
    assert not any(r['status'] == 'reserved' for r in ledger['reservations'])
    b.write(sub / 'closure.json', {'status': 'COMPLETE_DEVELOPMENT_ONLY', 'verification': checks,
            'spent': ledger['spent'], 'release_eligible': False})


def close():
    """同新核心父子配对，核对共同V2臂；不将开发差异叫显著增强。"""
    plan = b.read(OUT / 'manifest.json')
    verify(plan)
    assert not (OUT / 'summary.json').exists()
    for name in NAMES:
        assert b.read(OUT / name / 'closure.json')['status'] == 'COMPLETE_DEVELOPMENT_ONLY'
    stats = {name: {} for name in NAMES}
    pairs = []
    for mix in plan['opponents']:
        panels = {name: b.read(OUT / name / ('natural-' + mix) / 'panel.json') for name in NAMES}
        for name, panel in panels.items():
            stats[name][mix] = next(iter(panel['statistics']['by_candidate'].values()))['panels']['normal']['panels'][mix]
        parent = {(s['root_index'], s['focal_anchor_seat']): s for s in panels['parent']['samples']}
        by_root = {i: [] for i in plan['roots']}
        for sample in panels['candidate']['samples']:
            p = parent[(sample['root_index'], sample['focal_anchor_seat'])]
            assert p['root_content_digest'] == sample['root_content_digest']
            for key in ('stage_totals_by_participant', 'stage_place_points_by_participant', 'u_low', 'u_high'):
                assert p['raw_arms']['baseline'][key] == sample['raw_arms']['baseline'][key]
            a, z = sample['arms']['candidate'], p['arms']['candidate']
            by_root[sample['root_index']].append((a['u_low'] - z['u_high'], a['u_high'] - z['u_low']))
        for root, values in by_root.items():
            assert len(values) == 4
            pairs.append({'mix': mix, 'root': root, 'low': statistics.mean(v[0] for v in values),
                          'high': statistics.mean(v[1] for v in values)})
    low, high = statistics.mean(p['low'] for p in pairs), statistics.mean(p['high'] for p in pairs)
    result = {'status': 'COMPLETE_DEVELOPMENT_ONLY', 'statistics': stats, 'root_pairs': pairs,
              'parent_difference_low': low, 'parent_difference_high': high,
              'equal_mix_vs_v2': {name: statistics.mean(s['mean_delta'] for s in values.values()) for name, values in stats.items()},
              'continue_second_seen_panel': low > 0 and all(s['mean_delta'] > 0 for s in stats['candidate'].values()),
              'full_tables_verified': 512, 'model_calls': 0, 'release_eligible': False}
    b.write(OUT / 'summary.json', result)
    print({k: v for k, v in result.items() if k not in ('statistics', 'root_pairs')}, flush=True)


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
