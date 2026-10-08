"""保留首次测量失败，另冻一份字段修正和分段计时器；不执行业务计算。"""

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

HERE = Path(__file__).resolve().parent


def sha(path):
    """读取原记录真实字节，不修订旧失败、耗时或候选源码。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    """独占创建新证据，重复准备或已有文件时拒绝覆盖。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def replace_once(source, before, after):
    """仅更改已核对的调用位置，模板漂移时拒绝继续。"""
    assert source.count(before) == 1, before
    return source.replace(before, after)


def main():
    """冻结一轮修正执行，总费用包括已失败的首次实际评分。"""
    prior = json.loads((_project_file(_PROJECT_ROOT, HERE / 'actual-direct-1/CLOSURE.json')).read_text())
    terminal = json.loads((_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-DIRECT-EXECUTION-TERMINAL.json')).read_text())
    assert terminal['verified_tool_terminal'] and terminal['exit_code'] == 1
    assert prior['actual_costs']['choose_attempts'] == prior['actual_costs']['direct_score_attempts'] == 1
    assert prior['actual_costs']['failed_score_attempts'] == 0
    assert prior['issues'] == ["AttributeError: 'RuleAnalysis' object has no attribute 'candidates'"]
    score = json.loads((_project_file(_PROJECT_ROOT, HERE / 'actual-direct-1/SCORE-01-direct.json')).read_text())
    reference = next(r for r in json.loads((_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-REQUESTS.json')).read_text())['cases']
                     if r['label'] == 'old:public:20')
    canonical = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    order = lambda entries: sorted(entries, key=lambda e: e['action_key'])
    assert score['status'] == 'SCORED'
    assert score['input_capture']['view_sha256'] == reference['known_complete_view_sha256']
    assert score['operations'] == reference['known_T110_S02_operations']
    assert canonical(order(score['entries'])) == canonical(order(reference['known_T110_S02_actual_entries']))
    old = (_project_file(_PROJECT_ROOT, HERE / 'run_deadline.py')).read_text()
    fixed = replace_once(old, "OUT = HERE / 'actual-direct-1'", "OUT = HERE / 'actual-direct-2'")
    assert fixed.count('EXECUTABLE-FREEZE.json') == 2
    fixed = fixed.replace('EXECUTABLE-FREEZE.json', 'CORRECTED-EXECUTABLE-FREEZE.json')
    fixed = replace_once(fixed, 'for c in rules.candidates}', 'for c in rules.legal_candidates}')
    fixed = replace_once(fixed,
        "call = {'label': self.label, 'kind': self.kind, 'input_capture': asdict(receipt),",
        "call = {'label': self.label, 'kind': self.kind, 'input_capture': asdict(receipt),\n                'input_ready_monotonic': wall,")
    fixed = replace_once(fixed,
        "            result = self.original.score_vip_route(view)\n            call.update(status=result.status, operations=self.last_operation_count,",
        "            score_begin, score_cpu_begin = time.monotonic(), time.process_time()\n            result = self.original.score_vip_route(view)\n            score_end = time.monotonic()\n            call.update(score_wall_seconds=score_end - score_begin,\n                        score_cpu_seconds=time.process_time() - score_cpu_begin,\n                        score_finished_monotonic=score_end)\n            call.update(status=result.status, operations=self.last_operation_count,")
    fixed = replace_once(fixed,
        "                           capture_wall_seconds=call['capture_wall_seconds'], capture_cpu_seconds=call['capture_cpu_seconds'])",
        "                           capture_wall_seconds=call['capture_wall_seconds'], capture_cpu_seconds=call['capture_cpu_seconds'],\n                           pre_score_policy_wall_seconds=call['input_ready_monotonic'] - begin - row['rules_wall_seconds'],\n                           score_wall_seconds=call['score_wall_seconds'], score_cpu_seconds=call['score_cpu_seconds'],\n                           post_score_wall_seconds=ready - call['score_finished_monotonic'])")
    ast.parse(fixed)
    with (_project_file(_PROJECT_ROOT, HERE / 'run_deadline_corrected.py')).open('x') as stream:
        stream.write(fixed)
    with (_project_file(_PROJECT_ROOT, HERE / 'run_deadline_corrected.py.diff')).open('x') as stream:
        stream.write(''.join(difflib.unified_diff(old.splitlines(True), fixed.splitlines(True))))
    freeze = json.loads((_project_file(_PROJECT_ROOT, HERE / 'EXECUTABLE-FREEZE.json')).read_text())
    freeze.update(schema='t113-corrected-rule-contract-timer-freeze/1',
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        runner_sha256=sha(_project_file(_PROJECT_ROOT, HERE / 'run_deadline_corrected.py')),
        prior_failed_execution_preserved=True, original_choose_attempts=1,
        corrected_max_choose_attempts=8, aggregate_max_choose_attempts=9,
        aggregate_max_direct_and_reference_score_attempts=10,
        max_new_reference_score_attempts=1,
        correction='RuleAnalysis.legal_candidates replaces nonexistent candidates; policy and formula unchanged',
        diagnostics='monotonic wall and CPU times outside scoring executor; capture still counts in deadline',
        no_repeat_after_corrected_timing_failure=True)
    save('CORRECTED-EXECUTABLE-FREEZE.json', freeze)
    preserved = [_project_file(_PROJECT_ROOT, HERE / 'run_deadline.py'), _project_file(_PROJECT_ROOT, HERE / 'EXECUTABLE-FREEZE.json'),
        _project_file(_PROJECT_ROOT, HERE / 'ACTUAL-DIRECT-EXECUTION-TERMINAL.json'), _project_file(_PROJECT_ROOT, HERE / 'ACTUAL-DIRECT-EXECUTION.log'),
        _project_file(_PROJECT_ROOT, HERE / 'actual-direct-1/CLOSURE.json'), _project_file(_PROJECT_ROOT, HERE / 'actual-direct-1/SCORE-01-direct.json'),
        _project_file(_PROJECT_ROOT, HERE / 'RULE-CONTRACT-RED.log')]
    save('CORRECTION-PREPARATION-CLOSED.json', {
        'prepared': True, 'preserved_original_files': {str(p): sha(p) for p in preserved},
        'minimal_repro_actual_tool_terminal': {'verified_tool_terminal': True, 'exit_code': 1, 'terminal_chunk': '8f8f59'},
        'first_complete_score_exact_reference_match': True,
        'first_return_seconds_preserved': prior['rows'][0]['elapsed_wall_seconds'],
        'first_return_before_fallback': prior['rows'][0]['ready_before_fallback'],
        'prior_measurement_not_reclassified_as_pass': True,
        'modified_candidate_or_rules': False, 'all_original_requests_and_budgets_preserved': True,
        'one_corrected_run_only': True, 'new_rules_scores_choose_worlds_tables': 0})
    print({'correction_prepared': True, 'prior_failed_choose': 1, 'planned_corrected_choose': 8,
           'aggregate_max_choose': 9, 'candidate_rules_budgets_unchanged': True,
           'first_complete_score_exact': True, 'new_business_calls': 0})


if __name__ == '__main__':
    main()
