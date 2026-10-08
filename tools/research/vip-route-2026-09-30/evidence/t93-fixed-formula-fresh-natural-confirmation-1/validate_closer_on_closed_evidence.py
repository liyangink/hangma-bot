"""只读已闭合T92输入和T77区间，验证新闭合工具；不读取运行中的T93结局。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t93-fixed-formula-fresh-natural-confirmation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import json

HERE = Path(__file__).resolve().parent


def main():
    tool_path = _project_file(_PROJECT_ROOT, HERE/'close_campaign.py')
    spec = importlib.util.spec_from_file_location('t93_closer_validation',tool_path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    t92 = _project_file(_PROJECT_ROOT, HERE.parent/'t92-fixed-formula-natural-engineering-1')
    summary = json.loads((t92/'run-1/summary.json').read_text())
    plan = json.loads((t92/'PLAN.json').read_text())
    reference = json.loads((t92/'ROOT-READBACK.json').read_text())
    observed = tool.audit_actual_inputs(t92/'run-1',summary,plan)
    mappings = {'all_seat_decisions':'actual_all_seat_decisions',
        'candidate_decisions':'actual_candidate_decisions','actual_score_calls':'actual_candidate_score_calls',
        'finite_legal_action_score_outputs':'actual_finite_action_score_outputs',
        'unique_complete_views':'unique_complete_actual_views_readback',
        'max_candidate_operations':'max_candidate_operations',
        'white_counts_at_C_decisions':'white_counts_at_C_decisions',
        'selected_action_counts':'candidate_selected_action_counts',
        'choose_with_capture_ms_by_phase':'choose_with_capture_latency_ms_by_phase'}
    for key,expected in mappings.items():
        assert observed[key] == reference[expected], key
    t77 = _project_file(_PROJECT_ROOT, HERE.parent/'t77-net-upgrade-fresh-qualifier-pilot-1')
    old = json.loads((t77/'CAMPAIGN-CLOSURE.json').read_text())
    old_plan = json.loads((t77/'CAMPAIGN-PLAN.json').read_text())
    interval = tool.bootstrap(old['root_mean_deltas'],old_plan['confidence'])
    assert interval == old['root_cluster_percentile_95']
    assert not any((_project_file(_PROJECT_ROOT, HERE/f'BLOCK-{i:02d}-TERMINAL.json')).exists() for i in range(1,5))
    with (_project_file(_PROJECT_ROOT, HERE/'OUTCOME-READER-FREEZE.json')).open('x') as stream:
        json.dump({'schema':'t93-outcome-reader-preinspection-freeze/1',
            'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'close_tool_sha256':tool.sha(tool_path),'campaign_plan_sha256':tool.sha(_project_file(_PROJECT_ROOT, HERE/'CAMPAIGN-PLAN.json')),
            'empirical_percentile_indices_for20000_resamples':[500,19499],
            'T93_terminal_records_read':False,'T93_outcomes_read':False,
            'current_closer_actual_input_counts_equal_T92':observed,
            'old_T77_bootstrap_interval_exact':interval,
            'source_references':{str(p):tool.sha(p) for p in (t92/'ROOT-READBACK.json',t92/'run-1/summary.json',
                t92/'PLAN.json',t77/'CAMPAIGN-CLOSURE.json',t77/'CAMPAIGN-PLAN.json')},
            'new_models_rules_scores_worlds_tables':0,'scope':'pure file readback and bootstrap only; no new admission'},
            stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
        stream.write('\n')
    print({'tool_validated':True,'T92_score_call_receipts':observed['actual_score_calls'],
        'T92_legal_score_outputs':observed['finite_legal_action_score_outputs'],
        'T77_cluster_interval_exact':True,'T93_outcomes_read':False,'new_scores_worlds_tables':0})


if __name__ == '__main__':
    main()
