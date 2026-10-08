"""两清单通过后澄清一处追踪标签；机械派生源码，不伪装成作者修复答复。"""

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
import strong_seed_batch as b
import pattern_option_batch as first
import pattern_option_second_panel as second
import wealth_branch_probe as helper
from hangma_bot.policy.action_value_seeds import ActionValueScorer

OUT=b.HERE/'pattern-option-curated-20260920'


def main():
    """仅替换一次输出标签并核对112窗分数/排序；原源码、原答和历史成绩不变。"""
    assert not OUT.exists()
    assert b.read(second.OUT/'summary.json')['continue_new_development'] is True
    sub=first.OUT/first.NAME
    state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    source=b.Path(state['iter_dir'])/'generation/candidate.py'
    original=source.read_text()
    old='"unknown_policy": "known_final_floor_minus_1"'
    new='"unknown_policy": "parent_known_floor_minus_1_before_nonnegative_pattern_bonus"'
    assert original.count(old)==1
    corrected=original.replace(old,new)
    assert corrected.replace(new,old)==original
    OUT.mkdir();target=OUT/'candidate.py';target.write_text(corrected)
    admission=b.search.av_gates().admit_action_value(corrected)
    b.write(OUT/'admission.json',admission)
    assert admission['execution_safety_pass']
    scorers={'original':ActionValueScorer('original',original),'curated':ActionValueScorer('curated',corrected)}
    panel=b.HERE/'stage-rank-preflight-20260920/panel.json'
    rows=[]
    for row in b.read(panel)['rows']:
        request=helper.decision_request_from_json(row['record']['request']);view=helper.build_scoring_view(request)
        results={name:scorer.score(view) for name,scorer in scorers.items()}
        a,z=results['original'],results['curated']
        assert a.status==z.status
        assert {e.action_key:e.score for e in a.entries}=={e.action_key:e.score for e in z.entries}
        for left,right in zip(a.entries,z.entries,strict=True):
            trace=dict(left.trace)
            if trace.get('unknown_policy')=='known_final_floor_minus_1':trace['unknown_policy']='parent_known_floor_minus_1_before_nonnegative_pattern_bonus'
            assert trace==dict(right.trace)
        rows.append({'name':row['name'],'origin':row['origin'],'scores_equal':True,'trace_only_expected_label':True})
    b.write(OUT/'derivation.json',{'origin':'supervisor_mechanical_trace_label_correction',
        'source_path':str(source),'original_source_sha256':b.digest(source.read_bytes()),
        'curated_source_sha256':b.digest(target.read_bytes()),'exact_inverse_restores_original':True,
        'changed_literal_from':old,'changed_literal_to':new,'rows':rows,'behavior_cases':len(rows),
        'panel_sha256':b.digest(panel.read_bytes()),'new_author_calls':0,'author_raw_reply_modified':False,
        'claim':'静态差分只有一处输出标签字符串，算术与控制流未改；112输入逐分/顺序不变。新源码身份单独准入，后续新开发和确认都用新身份，旧结果不改写。',
        'release_eligible':False})
    print('curated trace only; 112 behavior pairs equal; admission passed',flush=True)


if __name__=='__main__':main()
