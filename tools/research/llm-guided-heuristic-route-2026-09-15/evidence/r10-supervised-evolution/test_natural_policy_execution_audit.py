"""零真实桌赛反例：评分器内部降级仍产合法计划，必须在自然评测保留单独计数。"""

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
import sys
from pathlib import Path
import pytest
from contextlib import nullcontext
import strong_seed_batch as b
import sitin_natural_panel as natural
from hangma_bot import bootstrap
from hangma_bot.policy.action_value_policy import ActionValuePolicy
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.hangma.interface import ValueAnalysisLimits

sys.path.insert(0,str(b.ROUTE.parents[1]/'tests/offline'))
from support import FakeEngine, FakeFrame, FakeDecision, FakeChoice, FakeMatchSpec, final_frame
from natural_policy_execution_audit import observe_tables, summarize

SOURCE='''def score_actions(view):
    for i in range(100001):
        x = i
    return {"status": "ABSTAIN", "entries": [], "reason": "test"}
'''

def run_probe(monkeypatch, source, *, audited=False):
    """真实评分器、策略和自然桌执行入口；只替换世界推进为单窗脚本，不是强度样本。"""
    raw=b.read(b.HERE/'support-competition-20260920/rule-generated-stress.json')['rows'][0]
    request=b.behavior.decision_request_from_json(raw['record']['request'])
    decision=FakeDecision(request.window_key,request.observation)
    contract=b.read(b.ROUTE/'contracts/group-dev-v1.json');versions=natural.stage.contract_versions_block(contract)
    engine=FakeEngine(lambda spec:[FakeFrame(1,(decision,),0),final_frame(2,(0,0,0,0),int(versions['rounds_per_game']))])
    monkeypatch.setattr(bootstrap,natural.BOOTSTRAP_RUNTIME_HOOK,
        lambda *args:{'engine':engine,'spec_factory':FakeMatchSpec,'choice_factory':FakeChoice})
    original=natural.drive_match;observed={}
    async def capture(**kwargs):
        outcome=await original(**kwargs);observed['outcome']=outcome;return outcome
    monkeypatch.setattr(natural,'drive_match',capture)
    policy=ActionValuePolicy(ActionValueScorer('accounting-probe',source))
    plan=natural.build_seat_stage_plans(contract=contract,opponent='H',root_index=1,
        focal_seat=0,panel_seed=2026092001)[0]
    with observe_tables() if audited else nullcontext():
        row=natural.execute_natural_table(plan=plan,policies_by_seat=(policy,)*4,
            versions_block=versions,step_limit=3,value_limits=ValueAnalysisLimits())
    return row,observed['outcome']

@pytest.mark.parametrize('mode',['workload','abstain','scored'])
def test_natural_output_preserves_internal_scoring_outcome(monkeypatch,mode):
    """成功说明也在degraded_reasons里，不能只用列表非空来误报失败。"""
    source=SOURCE if mode=='workload' else 'def score_actions(view):\n    return {"status": "ABSTAIN", "entries": [], "reason": "test"}\n'
    if mode=='scored':source=(b.HERE/'v2-seed-terra-02/run/iterations/iter-01/generation/candidate.py').read_text()
    row,outcome=run_probe(monkeypatch,source,audited=True)
    assert len(outcome.decisions)==1 and outcome.decisions[0].legal is True
    reasons=outcome.decisions[0].degraded_reasons
    assert any(s.startswith('action_value_failed:') for s in reasons)==(mode!='scored')
    assert row['result']['runtime_counts']['fallbacks']==0
    audit=row.get('policy_execution')
    assert audit is not None, '合法保底隐藏了评分器失败，逐决策原因未保留在自然桌结果'
    assert audit['schema']=='natural_policy_execution_v1'
    assert audit['decision_count']==1
    assert audit['action_value_failed']==int(mode!='scored')
    assert audit['action_value_scored']==int(mode=='scored')
    assert audit['by_seat'][0]['action_value_failed']==int(mode!='scored')

def test_formal_entry_now_preserves_failure_without_sidecar(monkeypatch):
    """正式入口接入后无需旁路；历史缺失记录仍由正式核验器判为未知。"""
    row,outcome=run_probe(monkeypatch,SOURCE)
    assert row['result']['runtime_counts']['fallbacks']==0
    assert any(s.startswith('action_value_failed:') for s in outcome.decisions[0].degraded_reasons)
    assert row['policy_execution']['schema']=='sitin-policy-execution/1'
    assert row['policy_execution']['action_value_failed']==1

def test_observer_preserves_original_decisions(monkeypatch):
    """审计开关前后运行同一受限源码，完整窗口记录和终局结果必须一致。"""
    with monkeypatch.context() as first:
        before,left=run_probe(first,SOURCE)
    with monkeypatch.context() as second:
        after,right=run_probe(second,SOURCE,audited=True)
    assert left==right
    for key in ('result','scores_by_seat','table_id','seed','match_status'):
        assert before[key]==after[key]

def test_summarize_does_not_confuse_rule_messages_and_score_success():
    """按物理座位记账，混合矛盾标志不能计成功；规则提示不是评分器失败。"""
    from types import SimpleNamespace
    rows=[SimpleNamespace(seat=0,degraded_reasons=('action_value: x 评分完成','规则降级[x]：测试')),
          SimpleNamespace(seat=1,degraded_reasons=('规则降级[x]：测试',)),
          SimpleNamespace(seat=2,degraded_reasons=('action_value_failed: ABSTAIN x',)),
          SimpleNamespace(seat=3,degraded_reasons=('action_value: x 评分完成','action_value_failed: ABSTAIN x'))]
    result=summarize(rows)
    assert [result[k] for k in ('decision_count','action_value_scored','action_value_failed','other_policy_decisions','ambiguous_diagnostics')]==[4,1,1,1,1]

def test_observer_refuses_existing_audit_file(tmp_path):
    """已有部分执行证据不可覆盖或隐式追加重跑。"""
    path=tmp_path/'audit.jsonl';path.write_text('existing\n')
    with pytest.raises(ValueError,match='拒绝覆盖'):
        with observe_tables(path):pass
    assert path.read_text()=='existing\n'

def test_missing_marker_for_action_value_is_unknown_not_success():
    """评分策略身份存在但诊断缺失必须显式未知，不能归入普通对手窗口。"""
    from types import SimpleNamespace
    result=summarize([SimpleNamespace(seat=0,policy_id='action_value_v1:x',degraded_reasons=())])
    assert result['unclassified_action_value']==1
    assert result['action_value_scored']==result['other_policy_decisions']==0
