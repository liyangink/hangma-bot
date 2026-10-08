"""在两组已见开发清单评测胡牌优先级消融；不作独立确认。"""

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

import strong_seed_batch as batch
import strong_seed_validation as validation
import sitin_natural_panel as natural
from verify_full_natural_results import verify_full_panel

OUT = batch.HERE / 'route-hu-priority-ablation-20260920'


def verify(plan):
    """核对核心、规则、消融源码及已完成原版面板，防止跨版本比较。"""
    validation.verify_identity(batch.read(validation.OUT / 'manifest.json'))
    if batch.digest((OUT / 'candidate.py').read_bytes()) != plan['candidate_sha256']:
        raise ValueError('消融源码身份改变')
    admission = batch.read(OUT / 'admission/admission.json')
    if not admission['execution_safety_pass']:
        raise ValueError('执行安全未通过')
    proof = batch.read(OUT / 'mechanical-difference-check.json')
    if proof['status'] != 'PASS' or proof['source_sha256'] != plan['candidate_sha256']:
        raise ValueError('缺少匹配的机械差异核验')
    for config in plan['sets'].values():
        for mix, sha in config['original_panel_sha256'].items():
            path = batch.Path(config['original']) / ('natural-' + mix) / 'panel.json'
            if batch.digest(path.read_bytes()) != sha:
                raise ValueError('原版面板改变')
            panel = batch.read(path)
            if panel['identity']['candidate_source_sha256'] != plan['parent_sha256']:
                raise ValueError('原版源码不符')


def run(name):
    """每清单独立账本256桌；不重启已运行目录。"""
    plan = batch.read(OUT / 'execution-plan.json')
    verify(plan)
    sub = OUT / name
    if (sub / 'started.json').exists():
        raise SystemExit('已运行，不隐式重跑')
    batch.write(sub / 'started.json', {'at_utc': batch.search.utc_now()})
    auth = batch.read(sub / 'authorization.json')
    contract = batch.read(batch.ROUTE / 'contracts/group-dev-v1.json')
    source = (OUT / 'candidate.py').read_text()
    rules_hash = batch.read(validation.OUT / 'manifest.json')['rules_hash']
    verification = []
    for mix in ['H', 'M']:
        verify(plan)
        natural.run_natural_panel(candidate_source=source, opponent=mix, roots=8, seats_per_root=4,
            contract=contract, out_dir=sub / ('natural-' + mix), authorization=auth,
            panel_seed=plan['sets'][name]['seed'], ledger_path=sub / 'ledger.json',
            ledger_authorized_budgets=batch.search.av_ledger_budgets_from_authorization(auth), min_roots=8)
        panel = batch.read(sub / ('natural-' + mix) / 'panel.json')
        if panel['identity']['candidate_source_sha256'] != plan['candidate_sha256']:
            raise ValueError('实际执行源码改变')
        if panel['identity']['panel_seed'] != plan['sets'][name]['seed']:
            raise ValueError('实际执行种子改变')
        verification.append(verify_full_panel(panel, contract, expected_identity=panel['identity'],
            expected_root_indices=plan['roots'], expected_rules_hash=rules_hash))
        print(name, mix, verification[-1]['full_results_verified'], flush=True)
    verify(plan)
    ledger = batch.read(sub / 'ledger.json')
    if ledger['spent']['tables_full'] != 256 or any(r['status'] == 'reserved' for r in ledger['reservations']):
        raise ValueError('成本未正常结清')
    batch.write(sub / 'closure.json', {'status': 'COMPLETE_DEVELOPMENT_ABLATION',
        'verification': verification, 'spent': ledger['spent'], 'release_eligible': False})


def close():
    """只对完整两清单结案，保留原版与V2差值及识别区间。"""
    plan = batch.read(OUT / 'execution-plan.json')
    verify(plan)
    if (OUT / 'summary.json').exists():
        raise SystemExit('已结案，不覆盖')
    results = []
    for name, config in plan['sets'].items():
        if batch.read(OUT / name / 'closure.json')['status'] != 'COMPLETE_DEVELOPMENT_ABLATION':
            raise ValueError('清单未完成')
        stats = {}; root_rows = []
        for mix in ['H', 'M']:
            child = batch.read(OUT / name / ('natural-' + mix) / 'panel.json')
            parent = batch.read(batch.Path(config['original']) / ('natural-' + mix) / 'panel.json')
            stats[mix] = next(iter(child['statistics']['by_candidate'].values()))['panels']['normal']['panels'][mix]
            index = {(s['root_index'], s['focal_anchor_seat']): s for s in parent['samples']}
            by_root = {i: [] for i in plan['roots']}
            for sample in child['samples']:
                p = index[(sample['root_index'], sample['focal_anchor_seat'])]
                if sample['root_content_digest'] != p['root_content_digest']:
                    raise ValueError('原版与消融根不匹配')
                for key in ['stage_totals_by_participant', 'stage_place_points_by_participant', 'u_low', 'u_high']:
                    if sample['raw_arms']['baseline'][key] != p['raw_arms']['baseline'][key]:
                        raise ValueError('共同V2臂不复现')
                a = sample['arms']['candidate']; z = p['arms']['candidate']
                by_root[sample['root_index']].append((a['u_low'] - z['u_high'], a['u_high'] - z['u_low']))
            for root, values in by_root.items():
                if len(values) != 4:
                    raise ValueError('根缺少座位配置')
                root_rows.append({'mix': mix, 'root': root,
                    'delta_low': statistics.mean(v[0] for v in values),
                    'delta_high': statistics.mean(v[1] for v in values)})
        results.append({'set': name, 'statistics': stats, 'versus_original_roots': root_rows,
            'equal_mix_vs_v2': statistics.mean(v['mean_delta'] for v in stats.values()),
            'versus_original_low': statistics.mean(v['delta_low'] for v in root_rows),
            'versus_original_high': statistics.mean(v['delta_high'] for v in root_rows)})
    batch.write(OUT / 'summary.json', {'status': 'COMPLETE_DEVELOPMENT_ABLATION', 'results': results,
        'tables_verified': 512, 'author_calls': 0, 'release_eligible': False})
    print([{k: r[k] for k in ['set', 'equal_mix_vs_v2', 'versus_original_low', 'versus_original_high']} for r in results])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['run', 'close'])
    parser.add_argument('--name', choices=['core', 'validation_reused'])
    args = parser.parse_args()
    if args.action == 'close':
        close()
    elif args.name:
        run(args.name)
    else:
        parser.error('run需要name')
