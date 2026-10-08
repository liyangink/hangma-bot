"""冻结开发流程的旁路评分审计；只读取公开驱动结果，不改变选择、计分或预算。"""

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
from contextlib import contextmanager
import json
from pathlib import Path
import sitin_natural_panel as natural

def summarize(decisions):
    """按物理座位0到3计数，每个窗口只分类一次；非评分策略与未知诊断不得冒充成功。"""
    keys=('decision_count','action_value_scored','action_value_failed','other_policy_decisions','ambiguous_diagnostics','unclassified_action_value')
    totals={k:0 for k in keys};seats=[{k:0 for k in keys} for _ in range(4)];failures={}
    for row in decisions:
        reasons=tuple(row.degraded_reasons)
        scored=any(s.startswith('action_value: ') and s.endswith(' 评分完成') for s in reasons)
        failed=any(s.startswith('action_value_failed:') for s in reasons)
        ambiguous=scored and failed
        is_action_value=str(getattr(row,'policy_id','')).startswith('action_value_v1:')
        bucket='ambiguous_diagnostics' if ambiguous else 'action_value_failed' if failed else 'action_value_scored' if scored else 'unclassified_action_value' if is_action_value else 'other_policy_decisions'
        if not 0<=row.seat<4:raise ValueError('审计窗口座位越界')
        totals['decision_count']+=1;totals[bucket]+=1
        seats[row.seat]['decision_count']+=1;seats[row.seat][bucket]+=1
        for reason in dict.fromkeys(s for s in reasons if s.startswith('action_value_failed:')):
            failures[reason]=failures.get(reason,0)+1
    assert sum(totals[k] for k in keys[1:])==totals['decision_count']
    return {'schema':'natural_policy_execution_v1',**totals,'by_seat':seats,'failure_reason_counts':failures,
            'scope':'策略内部评分成功/失败计数，独立于驱动fallbacks；不把规则提示或评分完成说明误算失败。'}

@contextmanager
def observe_tables(path=None):
    """仅供同步自然桌入口：完整表级计数追加到可选文件；缺回调、重复ID或重入立即失败。"""
    original_drive=natural.drive_match;original_table=natural.execute_natural_table
    pending={};seen=set();records=[]
    async def drive(**kwargs):
        outcome=await original_drive(**kwargs)
        match_id=kwargs['spec'].match_id
        if match_id in pending:raise ValueError('评分审计重复待取match_id')
        pending[match_id]=summarize(outcome.decisions)
        return outcome
    def table(**kwargs):
        if pending:raise ValueError('评分审计未消费上一次驱动结果')
        result=original_table(**kwargs);plan=kwargs['plan']
        if set(pending)!={plan.match_id}:raise ValueError('评分审计驱动与桌赛身份不匹配')
        audit=pending.pop(plan.match_id)
        # 同牌山双臂允许同match_id；策略身份与顺序共同标识本次实际执行。
        ordinal=len(records)
        record={'ordinal':ordinal,'table_id':plan.table_id,'match_id':plan.match_id,
                'policy_ids_by_seat':[str(getattr(p,'policy_id',type(p).__name__)) for p in kwargs['policies_by_seat']],
                'audit':audit}
        if ordinal in seen:raise ValueError('评分审计重复序号')
        seen.add(ordinal);records.append(record)
        if path is not None:
            with Path(path).open('a',encoding='utf-8') as handle:
                handle.write(json.dumps(record,ensure_ascii=False,sort_keys=True)+'\n')
        return {**result,'policy_execution':audit}
    if path is not None and Path(path).exists():raise ValueError('拒绝覆盖已有评分审计文件')
    natural.drive_match=drive;natural.execute_natural_table=table
    try:yield records
    finally:
        natural.drive_match=original_drive;natural.execute_natural_table=original_table
