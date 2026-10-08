"""固定六桌已见轨迹与规则条件探针；只诊断机会覆盖，不生成候选或效果结论。"""

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
from collections import Counter
from dataclasses import replace
import sys

import strong_seed_batch as b
import route_executor_recovery as engine
import sitin_natural_panel as natural
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.action_value_policy import build_scoring_view

sys.path.insert(0, str(b.ROUTE.parents[1]))
from tests.unit.hangma.test_value_analysis import _observation
from tests.unit.policy.support import make_request
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.config import RuleConfig

OUT = b.HERE / 'piao-opportunity-probe-20260920'
PARENT = b.HERE / 'v2-parent-revalidation-20260920'


def compact(view):
    """保留当前胡牌与打白后的条件事实；未见张数不转换为概率。"""
    payload = view.candidate_view()
    visible = payload['visible_state']
    actions = {a['action_key']: a for a in payload['actions']}
    hu, white = actions.get('hu'), actions.get('discard:白')
    routes = [] if white is None else white.get('routes') or []
    return {'hu_legal': hu is not None, 'white_legal': white is not None,
        'baotou': visible['rule_state']['baotou'],
        'remaining_tile_count': visible['remaining_tile_count'],
        'hu_settlement': None if hu is None else hu['immediate_settlement'],
        'white_coverage': None if white is None else white['value_coverage'],
        'white_routes': [{'conditions': r['conditions'],
            'settlement': r['conditional_settlement'],
            'tile_codes': [t['code'] for t in r['useful_tiles']],
            'unseen_support': sum(t['remaining_estimate'] for t in r['useful_tiles'])}
            for r in routes]}


def main():
    """清单先冻结；重演必须逐桌复现父代结果，诊断不能算新效果样本。"""
    assert not OUT.exists(), '已有产物，禁止隐式重跑'
    frozen = b.read(PARENT / 'manifest.json')
    engine.verify(frozen)
    original_path = PARENT / 'parent/natural-M/panel.json'
    original = b.read(original_path)
    contract = b.read(b.ROUTE / 'contracts/group-dev-v1.json')
    plan = {**frozen, 'created_at_utc': b.search.utc_now(),
        'purpose': 'piao_opportunity_coverage_only', 'roots': [1, 3, 5],
        'opponents': ['M'], 'focal_anchor_seat': 0, 'max_full_tables': 6,
        'full_tables': 6, 'tables_per_source': 6,
        'max_requests_per_stage': 10000, 'max_saved_per_stage': 32,
        'original_panel_sha256': b.digest(original_path.read_bytes()),
        'runner_sha256': b.digest(b.Path(__file__).read_bytes()),
        'selection': '固定已见M根1/3/5座位0父代臂，保存每阶段前32个可胡且可打白窗口；全部窗口计数',
        'decision_rule': '只决定题面是否有规则事实及真实覆盖；不判定续飘收益，不追加根或作者调用',
        'model_calls': 0, 'confirmation_roots': 0, 'release_eligible': False}
    OUT.mkdir()
    (OUT / 'windows').mkdir()
    b.write(OUT / 'manifest.json', plan)
    # 规则条件由唯一规则引擎生成；不冒充完整历史可达轨迹。
    rules = HangmaRules(RuleConfig('hangma-mvp-v10-public-counts', 1, False))
    rows = []
    for baotou in (False, True):
        for dealer in (0, 1):
            for wall in (20, 21, 23, 24, 25, 60):
                obs = _observation('1w 1w 2w 2w 3w 3w 4b 4b 5b 5b 6t 6t 白',
                    draw='白', baotou=baotou, dealer=dealer)
                obs = replace(obs, remaining_tile_count=wall)
                analysis = rules.analyze(obs, value_limits=natural.ValueAnalysisLimits())
                request = make_request(obs, analysis)
                view = build_scoring_view(request)
                rows.append({'name': f'baotou{baotou}-dealer{dealer}-wall{wall}',
                    'record': b.behavior.capture_request(request), 'facts': compact(view)})
    b.write(OUT / 'rule-conditions.json', {'rows': rows,
        'scope': '24个合成可见观察经唯一规则引擎计算；不证明历史可达、摸牌机会或效果',
        'selection_eligible': False})
    auth = b.unified_document(batch_label='piao-opportunity',
        authorization_id='r10-piao-opportunity-six-tables', accounts={'tables_full': 6},
        issued_by='lead', issued_at_utc=b.search.utc_now(), legacy_alias=False)
    auth['issuance_basis'] = '用户持续推进授权，固定六桌已见机会诊断，零新增作者'
    natural.require_authorization(auth)
    b.write(OUT / 'authorization.json', auth)
    ledger = b.search.ActionValueLedger.load(OUT / 'ledger.json',
        authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    scorer = ActionValueScorer('v2-like-parent', b.Path(plan['sources']['parent']['path']).read_text())
    panel, reports, ids = [], [], set()
    for root in plan['roots']:
        engine.verify(plan)
        assert b.digest(original_path.read_bytes()) == plan['original_panel_sha256']
        requests = []

        def observe(request):
            """保存本人合法可见请求；不在评分或动作执行路径引入其它选择。"""
            assert len(requests) < plan['max_requests_per_stage']
            requests.append(request)

        expected = next(s for s in original['samples'] if s['root_index'] == root
            and s['focal_anchor_seat'] == 0)['raw_arms']['candidate']
        plans = natural.build_seat_stage_plans(contract=contract, opponent='M',
            root_index=root, focal_seat=0, panel_seed=plan['panel_seed'])
        reservation = ledger.reserve(step_id='piao:root'+str(root), account='tables_full', amount=2,
            note='固定已见轨迹机会诊断')
        try:
            result = natural.run_arm_stage(arm='candidate', plans=plans, candidate_scorer=scorer,
                opponent_policies=contract['panel']['opponent_scenarios']['M']['opponent_policies'],
                versions_block=natural.stage.contract_versions_block(contract),
                step_limit=int(contract['stop']['step_limit']),
                value_limits=natural.ValueAnalysisLimits(), decision_observer=observe)
        finally:
            ledger.settle(reservation, usage_unknown=True, note='异常保守计上界；成功后核定实际')
        b.write(OUT / f'root{root}-stage.json', result)
        assert result['status'] == 'complete', result['error']
        ledger.settle(reservation, actual=len(result['tables']))
        for key in ('stage_totals_by_participant', 'stage_place_points_by_participant', 'u_low', 'u_high'):
            assert result[key] == expected[key], (root, key)
        assert len(result['tables']) == len(expected['tables']) == 2
        for actual, prior in zip(result['tables'], expected['tables'], strict=True):
            assert actual['table_id'] == prior['table_id'] and actual['seed'] == prior['seed']
            for key in ('scores_before', 'scores_after', 'completed_hands', 'expected_hands',
                        'runtime_counts', 'status', 'invalid_reasons'):
                assert actual['result'][key] == prior['result'][key], (root, key)
        counts, saved = Counter(), []
        for index, request in enumerate(requests):
            view = build_scoring_view(request)
            facts = compact(view)
            counts['requests'] += 1
            counts['hu_windows'] += int(facts['hu_legal'])
            opportunity = facts['hu_legal'] and facts['white_legal']
            counts['hu_white_windows'] += int(opportunity)
            counts['hu_white_baotou_windows'] += int(opportunity and facts['baotou'])
            if opportunity and len(saved) < plan['max_saved_per_stage']:
                record = b.behavior.capture_request(request)
                wid = record['candidate_view_sha256']
                saved.append({'request_index': index, 'window_id': wid, 'facts': facts})
                if wid not in ids:
                    file = 'windows/'+wid+'.json'
                    b.write(OUT / file, record)
                    panel.append({'file': file, 'candidate_view_sha256': wid,
                        'record_sha256': b.behavior.digest(record)})
                    ids.add(wid)
        report = {'root': root, 'terminal_reproduced': True, 'counts': dict(counts), 'saved': saved}
        b.write(OUT / f'root{root}-diagnostic.json', report)
        reports.append({k: v for k, v in report.items() if k != 'saved'})
        print(reports[-1], flush=True)
    engine.verify(plan)
    b.write(OUT / 'panel.json', {'schema': 'sitin-real-behavior-panel/1',
        'purpose': 'development_behavior', 'selection_eligible': False,
        'windows': panel, 'source': 'manifest.json'})
    if panel:
        b.behavior.load_panel(OUT / 'panel.json')
    final = b.read(OUT / 'ledger.json')
    assert final['spent']['tables_full'] == 6
    assert not any(r['status'] == 'reserved' for r in final['reservations'])
    b.write(OUT / 'summary.json', {'status': 'COMPLETE_DIAGNOSTIC_ONLY', 'reports': reports,
        'saved_windows': len(panel), 'rule_conditions': len(rows), 'spent': final['spent'],
        'model_calls': 0, 'confirmation_roots': 0, 'release_eligible': False,
        'limits': '已见少量V2轨迹，仅机会覆盖；条件结算不是收益预测，逻辑时钟不是时限证明'})


if __name__ == '__main__':
    main()
