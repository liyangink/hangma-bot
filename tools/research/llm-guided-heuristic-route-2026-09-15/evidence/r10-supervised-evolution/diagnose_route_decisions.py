"""重演固定三个已见M场景，保存每阶段前八个首选分歧；最多六桌、零模型。"""

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
import asyncio
from collections import Counter

import strong_seed_batch as b
import diverse_second_panel as second
import route_executor_recovery as engine
import sitin_natural_panel as natural
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.action_value_policy import ActionValuePolicy

OUT = b.HERE / 'route-decision-diagnostic-20260920'


def plan_view(plan):
    """留完整排序、分项与解释，不从跨优先层数值重建V2排序。"""
    return {'order': [c.action_key for c in plan.candidates],
        'degraded_reasons': list(plan.degraded_reasons),
        'candidates': [{'action_key': c.action_key, 'total_score': c.total_score,
            'parts': [{'name': p.name, 'value': p.value} for p in c.score_parts],
            'reasons': list(c.reasons), 'trace': dict(c.score_trace) if c.score_trace else None}
            for c in plan.candidates]}


def main():
    """先冻结清单、逐阶段预留费用；终局逐桌复现后才采纳旁路诊断。"""
    assert not OUT.exists(), '禁止隐式重跑'
    frozen = b.read(second.OUT / 'manifest.json')
    assert b.read(second.OUT / 'summary.json')['status'] == 'COMPLETE_SEEN_DEVELOPMENT'
    engine.verify(frozen)
    original_path = second.OUT / 'parent/natural-M/panel.json'
    original = b.read(original_path)
    contract = b.read(b.ROUTE / 'contracts/group-dev-v1.json')
    plan = {**frozen, 'purpose': 'selected_seen_development_decision_diagnostic',
        'created_at_utc': b.search.utc_now(), 'roots': [1, 3, 5], 'opponents': ['M'],
        'focal_anchor_seat': 0, 'tables_per_source': None, 'max_full_tables': 6,
        'selection': '预定根1/3/5座位0父代臂；每阶段前8个首选分歧；失利后选择，不是无偏样本',
        'max_saved_per_stage': 8, 'max_requests_per_stage': 10000,
        'original_panel_sha256': b.digest(original_path.read_bytes()),
        'runner_sha256': b.digest(b.Path(__file__).read_bytes()),
        'decision_rule': '诊断不作效果选留；结果不复现则停止消费；不自动扩根',
        'model_calls': 0, 'confirmation_roots': 0, 'release_eligible': False}
    OUT.mkdir()
    (OUT / 'windows').mkdir()
    b.write(OUT / 'manifest.json', plan)
    auth = b.unified_document(batch_label='route-decisions', authorization_id='r10-route-decisions-six-tables',
        accounts={'tables_full': 6}, issued_by='lead', issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth['issuance_basis'] = '用户持续推进授权；按上一结案报告固定6桌诊断，不新增效果样本或模型调用'
    natural.require_authorization(auth)
    b.write(OUT / 'authorization.json', auth)
    ledger = b.search.ActionValueLedger.load(OUT / 'ledger.json',
        authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    sources = {name: b.Path(plan['sources'][key]['path']).read_text()
        for name, key in [('parent', 'parent'), ('simplified', 'simplify-terra-max')]}
    scorers = {name: ActionValueScorer(name, source) for name, source in sources.items()}
    panels, reports, saved_ids = [], [], set()
    for root in plan['roots']:
        engine.verify(plan)
        assert b.digest(original_path.read_bytes()) == plan['original_panel_sha256']
        requests = []

        def observe(request):
            """只暂存原玩家可见请求，不改变执行中的动作计划。"""
            if len(requests) >= plan['max_requests_per_stage']:
                raise ValueError('超过冻结采集上界')
            requests.append(request)

        expected = next(s for s in original['samples'] if s['root_index'] == root and s['focal_anchor_seat'] == 0)['raw_arms']['candidate']
        plans = natural.build_seat_stage_plans(contract=contract, opponent='M', root_index=root,
            focal_seat=0, panel_seed=plan['panel_seed'])
        reservation = ledger.reserve(step_id='diagnostic:root'+str(root), account='tables_full', amount=2,
            note='已见开发重演，零新增效果样本')
        try:
            result = natural.run_arm_stage(arm='candidate', plans=plans, candidate_scorer=scorers['parent'],
                opponent_policies=contract['panel']['opponent_scenarios']['M']['opponent_policies'],
                versions_block=natural.stage.contract_versions_block(contract), step_limit=int(contract['stop']['step_limit']),
                value_limits=natural.ValueAnalysisLimits(), decision_observer=observe)
        finally:
            ledger.settle(reservation, usage_unknown=True, note='异常保守按上界结算；成功再核定实际')
        b.write(OUT / ('root'+str(root)+'-stage.json'), result)
        assert result['status'] == 'complete', result['error']
        ledger.settle(reservation, actual=len(result['tables']))
        for key in ('stage_totals_by_participant', 'stage_place_points_by_participant', 'u_low', 'u_high'):
            assert result[key] == expected[key], ('stage mismatch', root, key)
        assert len(result['tables']) == len(expected['tables']) == 2
        for a, z in zip(result['tables'], expected['tables'], strict=True):
            assert a['table_id'] == z['table_id'] and a['seed'] == z['seed']
            for key in ('scores_before', 'scores_after', 'completed_hands', 'expected_hands', 'runtime_counts', 'status', 'invalid_reasons'):
                assert a['result'][key] == z['result'][key], ('table mismatch', root, key)
        counts, rows = Counter(), []
        # 重演已经完成，之后评分无从影响实际执行，也不造成嵌套事件循环。
        for index, request in enumerate(requests):
            view = b.behavior.build_scoring_view(request)
            name = b.behavior.digest(view.candidate_view())
            budget = b.behavior.DecisionBudget(1.0, 2.0, 3.0)
            policies = {label: ActionValuePolicy(scorer) for label, scorer in scorers.items()}
            policies['v2'] = natural.stage.build_panel_policy(natural.BASELINE_FOCAL_POLICY, lambda: 0.0)
            choices = {label: plan_view(asyncio.run(policy.choose(request, budget))) for label, policy in policies.items()}
            assert all(c['order'] for c in choices.values())
            counts['requests_scored'] += 1
            differs = choices['parent']['order'][0] != choices['v2']['order'][0]
            mutation = choices['parent']['order'][0] != choices['simplified']['order'][0]
            counts['parent_vs_v2_first_diff'] += int(differs)
            counts['parent_vs_simplified_first_diff'] += int(mutation)
            if (differs or mutation) and len(rows) < 8:
                record = b.behavior.capture_request(request)
                rows.append({'root': root, 'request_index': index, 'window_id': name,
                    'request_sha256': record['request_sha256'], 'choices': choices,
                    'parent_vs_v2_first_diff': differs, 'parent_vs_simplified_first_diff': mutation})
                if name not in saved_ids:
                    file = 'windows/' + name + '.json'
                    b.write(OUT / file, record)
                    panels.append({'file': file, 'candidate_view_sha256': name, 'record_sha256': b.behavior.digest(record)})
                    saved_ids.add(name)
        report = {'root': root, 'terminal_reproduced': True, 'tables': 2, 'counts': dict(counts), 'rows': rows}
        b.write(OUT / ('root'+str(root)+'-diagnostic.json'), report)
        reports.append({k: v for k, v in report.items() if k != 'rows'})
        print(reports[-1], flush=True)
    engine.verify(plan)
    b.write(OUT / 'panel.json', {'schema': 'sitin-real-behavior-panel/1', 'purpose': 'development_behavior',
        'selection_eligible': False, 'windows': panels, 'source': 'manifest.json'})
    if panels:
        b.behavior.load_panel(OUT / 'panel.json')
    final_ledger = b.read(OUT / 'ledger.json')
    assert final_ledger['spent']['tables_full'] == 6
    assert not any(r['status'] == 'reserved' for r in final_ledger['reservations'])
    b.write(OUT / 'summary.json', {'status': 'COMPLETE_DIAGNOSTIC_ONLY', 'reports': reports,
        'saved_windows': len(panels), 'spent': final_ledger['spent'], 'model_calls': 0,
        'confirmation_roots': 0, 'release_eligible': False,
        'limits': '父代已见失利场景轨迹；旁路不证明改选后效果；首8窗有早期偏差；逻辑时钟不作时限证据'})


if __name__ == '__main__':
    main()
