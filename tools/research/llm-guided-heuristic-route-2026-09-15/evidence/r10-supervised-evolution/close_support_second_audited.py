"""第二清单结案补正：阶段汇总丢弃额外表字段，直接用持久旁路与原始桌身份对账。"""

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
import json
import strong_seed_batch as b
import support_competition_second_panel as task

def main():
    """不重跑模拟，不更改冻结入口；新旁路记录完整对账后才写最终分流。"""
    plan=b.read(task.OUT/'manifest.json');task.verify_reused(plan)
    note=b.read(task.OUT/'closure-correction.json')
    assert b.digest(b.Path(__file__).read_bytes())==note['replacement_closer_sha256']
    assert not (task.OUT/'summary.json').exists()
    rows=[json.loads(line) for line in (task.OUT/'candidate/policy-execution.jsonl').read_text().splitlines()]
    assert len(rows)==256 and [r['ordinal'] for r in rows]==list(range(256))
    expected=set()
    for mix in plan['opponents']:
        panel=b.read(task.OUT/'candidate'/('natural-'+mix)/'panel.json')
        for sample in panel['samples']:
            for arm in ('baseline','candidate'):
                for table in sample['raw_arms'][arm]['tables']:
                    key=(table['table_id'],tuple(table['result']['versions']['natural_seat_policy:'+str(i)] for i in range(4)))
                    assert key not in expected;expected.add(key)
    observed={(r['table_id'],tuple(r['policy_ids_by_seat'])) for r in rows}
    assert len(observed)==256 and observed==expected
    keys=('decision_count','action_value_scored','action_value_failed','other_policy_decisions','unclassified_action_value','ambiguous_diagnostics')
    for row in rows:
        audit=row['audit'];assert audit['schema']=='natural_policy_execution_v1'
        for key in keys:assert audit[key]==sum(s[key] for s in audit['by_seat'])
        assert audit['decision_count']==sum(audit[k] for k in keys[1:])
    counts={k:sum(r['audit'][k] for r in rows) for k in keys};reasons={}
    for row in rows:
        for reason,count in row['audit']['failure_reason_counts'].items():reasons[reason]=reasons.get(reason,0)+count
    task.engine.OUT=task.OUT;task.engine.NAMES=('parent','candidate');task.engine.close()
    result=b.read(task.OUT/'summary.json')
    b.write(task.OUT/'paired-effect-summary.json',result)
    keep=result.pop('continue_second_seen_panel')
    unresolved=any('候选整批失败' in reason for reason in reasons) or any(counts[k] for k in ('unclassified_action_value','ambiguous_diagnostics'))
    result.update({'new_full_tables':256,'reused_full_tables':256,'scope':plan['scope'],
        'effect_condition_passed':keep,'requires_execution_failure_review':unresolved,
        'continue_new_development':keep and not unresolved,
        'policy_execution_audit':{**counts,'failure_reason_counts':reasons,'parent_historical_counts':'unknown',
            'identity_joined_tables':256,'sidecar_sha256':b.digest((task.OUT/'candidate/policy-execution.jsonl').read_bytes())},
        'closure_correction_sha256':b.digest((task.OUT/'closure-correction.json').read_bytes())})
    b.write(task.OUT/'summary.json',result)
    print({k:result[k] for k in ('equal_mix_vs_v2','parent_difference_low','parent_difference_high','effect_condition_passed','requires_execution_failure_review','continue_new_development','policy_execution_audit')},flush=True)

if __name__=='__main__':main()
