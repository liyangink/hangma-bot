"""冻结三份源码，在未见开发牌山上比较；不调用作者、不作为独立发布确认。"""

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
import sitin_natural_panel as natural
from verify_full_natural_results import verify_full_panel
from hangma_bot.simulation.artifacts import compute_rules_hash

OUT = batch.HERE / 'strong-seeds-unseen-dev-20260920'
NAMES = ('parent-a', 'route-terra-max', 'hard-terra-max')


def verify_identity(manifest):
    """运行前后核对同一核心、规则、合同与全部候选源码。"""
    state = batch.search.av_state_load(batch.search.av_latest_state_path(batch.BATCH / 'hard-sol-high/run'))
    ok, why, _ = batch.search.av_verify_run_identity(state)
    if not ok:
        raise ValueError(why)
    if state['identity']['deps_digest'] != manifest['frozen_deps_digest']:
        raise ValueError('开发验证核心发生漂移')
    if compute_rules_hash(batch.ROUTE.parents[1]) != manifest['rules_hash']:
        raise ValueError('规则发生漂移')
    if batch.digest((batch.ROUTE / 'contracts/group-dev-v1.json').read_bytes()) != manifest['contract_file_sha256']:
        raise ValueError('合同文件发生漂移')
    for source in manifest['sources'].values():
        if batch.digest(batch.Path(source['path']).read_bytes()) != source['sha256']:
            raise ValueError('验证中的源码发生漂移')


def prepare():
    """只冻结清单，不生成或读取新根；选择只依据完整旧开发结果。"""
    if OUT.exists():
        raise SystemExit('验证目录已存在')
    summary = batch.read(batch.BATCH / 'batch-summary.json')
    if summary['status'] != 'COMPLETE_DEVELOPMENT_ONLY':
        raise ValueError('六提案尚未全部关闭')
    sources = {}
    for name in NAMES:
        if name == 'parent-a':
            p = batch.Path(batch.read(batch.BATCH / name / 'manifest.json')['source_path'])
        else:
            state = batch.search.av_state_load(batch.search.av_latest_state_path(batch.BATCH / name / 'run'))
            p = batch.Path(state['iter_dir']) / 'generation/candidate.py'
        sources[name] = {'path': str(p), 'sha256': batch.digest(p.read_bytes())}
    reference = batch.search.av_state_load(batch.search.av_latest_state_path(batch.BATCH / 'hard-sol-high/run'))
    manifest = {'schema': 'strong-seed-unseen-development/1', 'created_at_utc': batch.search.utc_now(),
                'purpose': 'held_out_development_validation', 'sources': sources,
                'selection_basis': '六初答完整结果后选父代A、均值最高路线候选、困难题最高候选；不因中途成绩改选',
                'old_summary_sha256': batch.digest((batch.BATCH / 'batch-summary.json').read_bytes()),
                'panel_seed': 2026092097, 'roots': list(range(1, 9)), 'opponents': ['H', 'M'],
                'seats': 4, 'tables_per_source': 256, 'total_full_tables': 768,
                'author_calls': 0, 'confirmation_roots': 0, 'release_eligible': False,
                'frozen_deps_digest': reference['identity']['deps_digest'],
                'rules_hash': compute_rules_hash(batch.ROUTE.parents[1]),
                'contract_file_sha256': batch.digest((batch.ROUTE / 'contracts/group-dev-v1.json').read_bytes()),
                'decision_rule': '完整结束后报告H/M、平分识别区间及同根父子差；两层均值正且对子代相对A平均差下界正才列为后续消融优先，否则保留探索资格但不升为效果父代。该工程分流规则不是显著性门禁。',
                'stop_rule': '身份漂移、预算耗尽或缺失结果停止受影响执行，保留现场，不追加样本或替换坏根',
                'limitations': ['全三来源共享同一新根；新数据使用后转为已见开发数据',
                                '不改原源码；hard-terra-max潜在财神计数缺陷仍在发布前问题单',
                                '逻辑时钟模拟不能代替官方可靠性门禁']}
    verify_identity(manifest)
    OUT.mkdir()
    batch.write(OUT / 'manifest.json', manifest)
    for name in NAMES:
        sub = OUT / name
        sub.mkdir()
        auth = batch.unified_document(batch_label=name + '-unseen', authorization_id='r10-unseen-' + name,
            accounts={'tables_full': 256}, issued_by='lead', issued_at_utc=batch.search.utc_now(), legacy_alias=False)
        auth['issuance_basis'] = '用户持续推进授权；监督者冻结三源码未见开发验证，各256完整桌赛，无模型调用'
        batch.write(sub / 'authorization.json', auth)
    print(str(OUT), flush=True)


def run(name):
    """按冻结清单执行；开始标志存在即拒绝第二次启动。"""
    manifest = batch.read(OUT / 'manifest.json')
    verify_identity(manifest)
    sub = OUT / name
    if (sub / 'started.json').exists():
        raise SystemExit('已启动，禁止隐式重跑')
    batch.write(sub / 'started.json', {'started_at_utc': batch.search.utc_now()})
    source = batch.Path(manifest['sources'][name]['path']).read_text()
    auth = batch.read(sub / 'authorization.json')
    contract = batch.read(batch.ROUTE / 'contracts/group-dev-v1.json')
    results = []
    for mix in manifest['opponents']:
        verify_identity(manifest)
        natural.run_natural_panel(candidate_source=source, opponent=mix, roots=8, seats_per_root=4,
            contract=contract, out_dir=sub / ('natural-' + mix), authorization=auth,
            panel_seed=manifest['panel_seed'], ledger_path=sub / 'ledger.json',
            ledger_authorized_budgets=batch.search.av_ledger_budgets_from_authorization(auth), min_roots=8)
        panel = batch.read(sub / ('natural-' + mix) / 'panel.json')
        if panel['identity']['candidate_source_sha256'] != manifest['sources'][name]['sha256']:
            raise ValueError('面板源码不匹配')
        if panel['identity']['panel_seed'] != manifest['panel_seed']:
            raise ValueError('面板种子不匹配')
        results.append(verify_full_panel(panel, contract, expected_identity=panel['identity'],
            expected_root_indices=manifest['roots'], expected_rules_hash=manifest['rules_hash']))
        print(name, mix, results[-1]['full_results_verified'], flush=True)
    verify_identity(manifest)
    ledger = batch.read(sub / 'ledger.json')
    if ledger['spent']['tables_full'] != 256 or any(r['status'] == 'reserved' for r in ledger['reservations']):
        raise ValueError('实际成本或预留结算不匹配')
    batch.write(sub / 'batch-closure.json', {'status': 'COMPLETE_UNSEEN_DEVELOPMENT',
        'verifications': results, 'spent': ledger['spent'], 'release_eligible': False})


def close():
    """对账所有来源的共同V2臂，再形成预登记开发分流。"""
    manifest = batch.read(OUT / 'manifest.json')
    verify_identity(manifest)
    if (OUT / 'summary.json').exists():
        raise SystemExit('已结案，不覆盖')
    for name in NAMES:
        if batch.read(OUT / name / 'batch-closure.json')['status'] != 'COMPLETE_UNSEEN_DEVELOPMENT':
            raise ValueError('来源未完成')
    rows = []
    for name in NAMES:
        stats = {}; pairs = []
        for mix in manifest['opponents']:
            panel = batch.read(OUT / name / ('natural-' + mix) / 'panel.json')
            parent = batch.read(OUT / 'parent-a' / ('natural-' + mix) / 'panel.json')
            stats[mix] = next(iter(panel['statistics']['by_candidate'].values()))['panels']['normal']['panels'][mix]
            index = {(s['root_index'], s['focal_anchor_seat']): s for s in parent['samples']}
            for sample in panel['samples']:
                p = index[(sample['root_index'], sample['focal_anchor_seat'])]
                if sample['root_content_digest'] != p['root_content_digest']:
                    raise ValueError('来源根未对齐')
                for key in ['stage_totals_by_participant', 'stage_place_points_by_participant', 'u_low', 'u_high']:
                    if sample['raw_arms']['baseline'][key] != p['raw_arms']['baseline'][key]:
                        raise ValueError('共同V2臂不复现')
                a = sample['arms']['candidate']; z = p['arms']['candidate']
                pairs.append((0.0, 0.0) if name == 'parent-a' else
                             (a['u_low'] - z['u_high'], a['u_high'] - z['u_low']))
        low = statistics.mean(x[0] for x in pairs); high = statistics.mean(x[1] for x in pairs)
        rows.append({'name': name, 'statistics': stats, 'parent_a_difference_low': low,
            'parent_a_difference_high': high, 'equal_mix_vs_v2': statistics.mean(s['mean_delta'] for s in stats.values()),
            'ablation_priority': name != 'parent-a' and low > 0 and all(s['mean_delta'] > 0 for s in stats.values())})
    batch.write(OUT / 'summary.json', {'status': 'COMPLETE_UNSEEN_DEVELOPMENT', 'rows': rows,
        'tables_verified': 768, 'common_v2_arms_reproduced': True, 'release_eligible': False})
    print([(r['name'], r['equal_mix_vs_v2'], r['ablation_priority']) for r in rows], flush=True)


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
        parser.error('run需要指定name')
