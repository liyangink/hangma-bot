"""冻结当前S02的本地时限输入；不读运行中确认成绩，不执行业务计算。

从已闭的103个公开窗口选各动作阶段的最高实际操作输入，复用T104
计时器。评分参考只取S02自己的完整记录；旧故障响应另补一份真参考。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t113-t110-s02-deadline-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path

from hangma_bot.application.deadline import BudgetPolicy
from hangma_bot.offline.scoring_sources import source_manifest
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents

HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1')
CONFIRMATION = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t112-fixed-t110-s02-fresh-confirmation-1')
BASE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t104-current-candidate-deadline-preparation-1')
FAILURE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t80-witness-capacity-failure-diagnostic-1/FAILED-PUBLIC-WINDOW.json')


def sha(path):
    """冻结文件真实字节；不根据名称迁移旧候选成绩。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    """独占创建准备文件，已存在或失败时不覆盖原记录。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    """只检查已有数据并绑定身份；规则、评分、choose和模型新增均为0。"""
    panel_file = _project_file(_PROJECT_ROOT, AUTHOR / 'PUBLIC-PANEL.json')
    closure_file = _project_file(_PROJECT_ROOT, AUTHOR / 'S02-public-probe/CLOSURE.json')
    readback_file = _project_file(_PROJECT_ROOT, AUTHOR / 'S02-public-probe/ROOT-READBACK.json')
    panel = json.loads(panel_file.read_text())['cases']
    closure = json.loads(closure_file.read_text())
    readback = json.loads(readback_file.read_text())
    assert len(panel) == len(closure['rows']) == 103
    assert closure['complete'] and closure['source_stable'] and closure['primary_failure'] is None
    assert readback['complete'] and readback['actual_tool_terminal']['verified_tool_terminal']
    assert readback['actual_tool_terminal']['exit_code'] == 0
    batch_file = _project_file(_PROJECT_ROOT, AUTHOR / 'AUTHOR-BATCH.json')
    batch = VipEohBatch.read(batch_file)
    candidate = load_vip_parents([_project_file(_PROJECT_ROOT, AUTHOR / 'S02-model-output')], batch)[0]
    confirmation = json.loads((_project_file(_PROJECT_ROOT, CONFIRMATION / 'CAMPAIGN-PLAN.json')).read_text())
    assert candidate['identity'] == closure['candidate_identity'] == readback['candidate_identity']
    assert candidate['identity'] == confirmation['candidate_identity']
    assert candidate['identity']['candidate_id'] == '54d4029ba095572490c41406a481d73d27e350e385438b177013ce72f274b710'
    actual = {row['label']: row for row in closure['rows']}
    cases = {case['label']: case for case in panel}
    assert len(actual) == len(cases) == 103
    selected = []
    for phase in ('draw', 'response_chi', 'response_peng'):
        case = max((c for c in panel if c['observation']['phase'] == phase),
                   key=lambda c: actual[c['label']]['child_scores']['operations'])
        selected.append((case, 'highest_actual_operations_' + phase))
    ordinary = min((c for c in panel if c['observation']['phase'] == 'draw'),
                   key=lambda c: actual[c['label']]['child_scores']['operations'])
    selected += [(ordinary, 'ordinary_outlet'), (cases['T96:1815'], 'natural_set_control'),
                 (cases['T94:1875'], 'current_hu_control')]
    assert len({case['label'] for case, _ in selected}) == 6
    rows = []
    for case, reason in selected:
        old = actual[case['label']]
        assert old['status'] == 'complete' and old['view_sha256'] == case['view_sha256']
        rows.append({'label': case['label'], 'selection_reason': reason,
            'observation': case['observation'], 'window_key': case['window_key'],
            'known_complete_view_sha256': old['view_sha256'],
            'known_T110_S02_actual_entries': old['child_scores']['entries'],
            'known_T110_S02_operations': old['child_scores']['operations'],
            'reference': 'closed real S02 full scoring; not transferred parent scores or new timing'})
    failure = json.loads(FAILURE.read_text())['actual_failed_row']
    assert not any(c['observation'] == failure['observation'] and c['window_key'] == failure['window_key']
                   for c in panel)
    rows.append({'label': 'original-T80-failed-response',
        'selection_reason': 'prior_real_capacity_and_deadline_failure',
        'observation': failure['observation'], 'window_key': failure['window_key'],
        'known_complete_view_sha256': None, 'known_T110_S02_actual_entries': None,
        'known_T110_S02_operations': None,
        'reference': 'no current S02 reference in the closed panel; one real reference after timed choose'})
    save('PUBLIC-REQUESTS.json', {'schema': 't113-current-public-request-selection/1', 'cases': rows,
        'scope': 'seven development engineering requests only; no independent strength or global deadline coverage'})
    manifest = source_manifest(('hangma_bot.application.deadline', 'hangma_bot.application.decision_compute',
                                'hangma_bot.bootstrap', 'hangma_bot.policy.route_vip_heuristic'))
    manifest.update(candidate['identity']['source_manifest'])
    save('FROZEN-ENGINEERING-SOURCE-MANIFEST.json', manifest)
    original = (_project_file(_PROJECT_ROOT, BASE / 'run_deadline.py')).read_text()
    edits = [
        ('t101-joint-breadth-recovery-author-1', 't110-compact-target-cost-joint-evolution-1'),
        ('t103-joint-breadth-fresh-confirmation-1', 't112-fixed-t110-s02-fresh-confirmation-1'),
        ('S02-generation.batch.json', 'AUTHOR-BATCH.json'),
        ('known_T101', 'known_T110_S02'), ('T101', 'T110-S02'), ('T103', 'T112'), ('t104', 't113')]
    adapted = original
    for old, new in edits:
        assert old in adapted, old
        adapted = adapted.replace(old, new)
    ast.parse(adapted)
    with (_project_file(_PROJECT_ROOT, HERE / 'run_deadline.py')).open('x') as stream:
        stream.write(adapted)
    with (_project_file(_PROJECT_ROOT, HERE / 'run_deadline.py.diff')).open('x') as stream:
        stream.write(''.join(difflib.unified_diff(original.splitlines(True), adapted.splitlines(True))))
    files = [Path(__file__), _project_file(_PROJECT_ROOT, BASE / 'run_deadline.py'), panel_file, closure_file, readback_file,
        batch_file, _project_file(_PROJECT_ROOT, AUTHOR / 'S02-model-output/generation.json'), _project_file(_PROJECT_ROOT, AUTHOR / 'S02-model-output/candidate.py'),
        FAILURE, _project_file(_PROJECT_ROOT, CONFIRMATION / 'CAMPAIGN-PLAN.json'), _project_file(_PROJECT_ROOT, HERE / 'PUBLIC-REQUESTS.json'),
        _project_file(_PROJECT_ROOT, HERE / 'FROZEN-ENGINEERING-SOURCE-MANIFEST.json'), _project_file(_PROJECT_ROOT, HERE / 'run_deadline.py'), _project_file(_PROJECT_ROOT, HERE / 'run_deadline.py.diff')]
    budgets = BudgetPolicy()
    spans = {str(span): {
        'enhancement_seconds': budgets.build(100., span).enhancement_deadline_monotonic - 100.,
        'fallback_seconds': budgets.build(100., span).fallback_deadline_monotonic - 100.,
        'latest_send_seconds': budgets.build(100., span).latest_send_at_monotonic - 100.}
        for span in (1., 3.)}
    plan = json.loads((_project_file(_PROJECT_ROOT, BASE / 'PLAN.json')).read_text())
    plan.update(schema='t113-current-s02-deadline-preparation/1',
        created_at_utc=datetime.now(timezone.utc).isoformat(), candidate_identity=candidate['identity'],
        frozen_files={str(path): sha(path) for path in files},
        ordered_direct_choose_requests=[r['label'] for r in rows] + [rows[0]['label']],
        first_run_source='unmodified formal T110 S02 source, original rule/route/projection/operation limits',
        activation_requires='T112 complete valid strength signal, original four handles and reader terminal, no parallel table load',
        budget_seconds_by_original_span=spans)
    save('PLAN.json', plan)
    freeze = json.loads((_project_file(_PROJECT_ROOT, BASE / 'EXECUTABLE-FREEZE.json')).read_text())
    freeze.update(schema='t113-current-s02-direct-executable-freeze/1',
        created_at_utc=datetime.now(timezone.utc).isoformat(), candidate_identity=candidate['identity'],
        runner_sha256=sha(_project_file(_PROJECT_ROOT, HERE / 'run_deadline.py')), plan_sha256=sha(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')),
        runtime_source_manifest=manifest,
        activation='four actual T112 terminals + actual reader terminal + whole valid positive cluster interval + positive highfan net from multiple roots + no live known table runner')
    save('EXECUTABLE-FREEZE.json', freeze)
    save('PREPARATION-CLOSED.json', {'prepared': True, 'candidate_identity': candidate['identity'],
        'selected_cases': [{'label': row['label'], 'reason': row['selection_reason'],
                            'known_operations': row['known_T110_S02_operations']} for row in rows],
        'runtime_sources_frozen': len(manifest), 'runner_changes': edits,
        'formula_rules_budgets_changed': False, 'confirmation_outcomes_read': False,
        'new_models_rules_scores_choose_worlds_tables': 0, 'actual_choose_executions': 0,
        'published': False})
    print({'prepared': True, 'candidate': candidate['identity']['candidate_id'],
           'unique_requests': 7, 'planned_choose': 8, 'new_reference_scores': 1,
           'budget_seconds': spans, 'actual_rules_scores_choose_worlds_tables': 0,
           'confirmation_outcomes_read': False})


if __name__ == '__main__':
    main()
