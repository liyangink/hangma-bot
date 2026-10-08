"""V2种子比较器的负对照：可执行或弃权不能冒充正确排序。"""

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
from dataclasses import replace
import v2_seed_parity as parity


ZERO = '''def score_actions(view):
    entries=[]
    for a in view["actions"]:
        entries.append({"action_key":a["action_key"],"score":0.0,"trace":{}})
    return {"status":"SCORED","entries":tuple(entries),"reason":"negative control"}
'''
ABSTAIN = '''def score_actions(view):
    return {"status":"ABSTAIN","entries":(),"reason":"negative control"}
'''


def test_executable_constant_scores_do_not_pass_parity():
    result=parity.run(ZERO)
    assert result['execution_acceptable']
    assert result['strict_mismatches']>0
    assert not result['strict_pass']
    assert not result['release_eligible']


def test_blanket_abstention_does_not_pass_and_known_unknown_pair_is_in_scope():
    result=parity.run(ABSTAIN)
    assert not result['execution_acceptable']
    assert result['strict_mismatches']==result['strict_count']
    row=next(r for r in result['rows'] if r['name']=='unknown_below_negative')
    assert row['strict_scope'] and not row['full_order_equal']


def test_exclusions_are_input_based_and_degraded_facts_stay_explicit():
    cases=dict(parity.fixtures())
    assert parity.scope(cases['boundary_all_unknown'])==['all_unknown_emergency_identity_not_visible']
    assert parity.scope(cases['boundary_missing_pass'])==['missing_waiting_baseline_contract_difference']
    request=cases['shanten_priority']
    assert parity.scope(request)==[]
    first=request.rules.legal_candidates[0]
    changed=replace(first,facts=replace(first.facts,completeness=parity.RuleCompleteness.DEGRADED))
    request=replace(request,rules=replace(request.rules,legal_candidates=(changed,)+request.rules.legal_candidates[1:]))
    assert parity.scope(request)==['fact_completeness_not_visible']


def test_extended_counterexamples_detect_first_author_source_mistakes():
    """初版58项曾全绿；新增例必须实际区分三个已发现错误，而非只检查执行成功。"""
    source=(parity.HERE/'v2-seed-terra-01/run/iterations/iter-01/generation/candidate.py').read_text()
    result=parity.run(source)
    bad={r['name'] for r in result['rows'] if r['strict_scope'] and not r['full_order_equal']}
    assert {'own_river_is_not_opponent_safe','next_seat_also_dealer_risk',
            'hu_priority_extreme_contract_fixture'} <= bad
    assert not result['strict_pass']
