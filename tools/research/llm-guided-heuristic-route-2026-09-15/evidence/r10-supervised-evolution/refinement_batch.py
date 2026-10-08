"""在完整开发反馈后冻结一份分支机制修订；原生作者只读题面。"""

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
import argparse
import strong_seed_batch as b

NAME='branch-terra-max'
ROOT=b.HERE/'branch-refinement-20260920'
PARENT=b.BATCH/'hard-terra-max/run/iterations/iter-01/generation'


def prepare():
    """以明确父代进入公共M1通道，不继承旧效果作为新结果。"""
    if ROOT.exists():raise SystemExit('已冻结，不覆盖')
    ROOT.mkdir();sub=_project_file(_PROJECT_ROOT, ROOT/NAME);sub.mkdir()
    feedback='''本次是完整反馈驱动的M1机制修订，唯一父代是所附hard-terra-max源码。不是复刻V2，不要求V2等价，也不是换一组任意阈值。
父代在共同核心清单：H +0.125、M +0.09375；未见开发清单：H +0.03125、M -0.046875。都只是各8根开发均值，未证明显著提升，没有准入发布资格。未见开发结果已经用于此次反思，不能再叫独立确认。当前不使用阶段内胡牌次数或改选数冒充效用。
需要处理的具体问题：
1. 在既有32个真实开发窗口、159个动作评分中，父代最终basis只有combined_hand 115、conditional_route 42、immediate_hu_priority 2；有19份吃碰分支读数，却没有followup_branch成为最终评分来源。源码先比较不带分支修正的直接摘要，再比较含分支家族/财神修正的具体分支，因此负修正可能被同一动作的摘要绕过。请查明并设计一致的整条分支比较机制：每个合法弃牌后继的已知牌效、财神与家族修正应同刻度计算后再择优；不要把不相容后继相加。仅有摘要、分支未知或部分分析时必须区分，不能凭缺失把已知事实清零。
2. 父代wealth_count的补摸牌条件写反：my_hand长度已是14-3*副露数时已经包含摸牌，不应再加；长度13-3*副露数且drawn_tile存在时才补。当前唯一规则引擎兼容两者。此变量目前主要用于吃碰后分支财富差，合法响应drawn_tile为空，所以这是潜在计数缺陷，不把修复它宣传成提升主因。
3. 保持不相关弃牌、条件路线、立即结算等行为尽量稳定；有必要改变必须给因果理由。不要同时新加无关的对手/阶段风险项。合法胡牌兑现不能被未经标定的支持枚数轻易压过；父代在20个官方算分条件投影检查中首选hu均通过，但不是全域证明。
交付目标是一个有明确作用路径的启发式变异，而非强行使所有分支胜出；可能只有少部分动作改变。同题其他分支实现并未自动超过父代，因此不能承诺去掉摘要就提分。说明一个新机制会改变排序的构造反例，以及什么时候保持直接已知事实更合理；构造例不冒充真实轨迹。
输入仍是纯字典view，直接get，不调用.candidate_view；不导入、不重算合法性/向听/结算，不读其他文件或模型。不硬编码开发样本。遵守后附完整M1输出格式，交付机制说明、JSON四字段和唯一完整Python源码。
杭麻规则约束：只自摸，无点炮/抢杠胡；喂牌对吃碰提速的影响需独立解释；七对与副露、财神、爆头/财飘/杠链、四白均使用已生产且相容的规则事实。未知不当零，互斥路线不相加，统计目标仍为完整阶段前二效用。
'''
    auth=b.unified_document(batch_label=NAME,authorization_id='r10-branch-refinement-terra',accounts={'tokens_input':393216,'tokens_output':131072,'tables_full':300,'tables_partial':8,'prefix_generation':8},issued_by='lead',issued_at_utc=b.search.utc_now(),legacy_alias=False)
    panel=b.HERE/'batch03-known-root-diagnostic/panel.json'
    auth.update({'generation_call_limits':{'tokens_input':196608,'tokens_output':65536},'max_model_calls':2,'max_proposals':2,'repair_calls_count_in_total':True,'wall_clock_limit_seconds':14400,'author_channel':'codex_native_subagent','requested_model':'gpt-5.6-terra','requested_reasoning_effort':'max','autonomous_admission':False,'supervisor_feedback':feedback,'issuance_basis':'用户持续进化及原生Terra作者授权；一份M1加至多一次错误修复，保守原生占额不代表实际token','scope':'核心开发256自然桌赛，条件费用另计；零独立确认；不发布','development_behavior_panel':{'path':str(panel),'panel_digest':b.behavior.load_panel(panel)[0]}})
    b.write(sub/'authorization.json',auth)
    state=b.search.av_start_iteration(sub/'run',operator='m1',parent_dir=PARENT,generation_mode='delegate',predicate='branch_open',opponent='H',natural_roots=8,natural_seats=4,prefix_source='v2_behavior',panel_seed=2026092001,authorization=auth,archive_in={'source':'empty','path':None,'applied_operator':'m1','note':'完整反馈后显式选hard-terra-max作探索父代，不作为效果晋升或新成绩'})
    if state.get('stop_reason'):raise ValueError(state['stop_reason'])
    result=b.search.av_iteration_advance(b.search.av_latest_state_path(sub/'run'),sub/'run',authorization=auth,stop_after='BEHAVIOR_CHECKED')
    assert result.get('waiting_for_reply')
    state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'));prompt=b.Path(state['generation']['pending_dir'])/'prompt.txt'
    b.write(sub/'author-task.json',{'model':'gpt-5.6-terra','effort':'max','task':'M1完整分支与摘要一致比较','prompt':str(prompt),'prompt_sha256':b.digest(prompt.read_bytes()),'reply_path':str(sub/'author-reply.txt')})
    b.write(_project_file(_PROJECT_ROOT, ROOT/'manifest.json'),{'created_at_utc':b.search.utc_now(),'parent_path':str(PARENT/'candidate.py'),'parent_sha256':b.digest((PARENT/'candidate.py').read_bytes()),'initial_proposals':1,'max_author_calls':2,'native_tokens':'unknown; conservative reservation only','max_native_turn_seconds':1800,'purpose':'真实M1提案，修正并检验分支机制，不是自主发布','release_eligible':False})
    print({'prompt':str(prompt),'prompt_chars':len(prompt.read_text())},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','ingest','evaluate']);a=parser.parse_args()
    if a.action=='prepare':prepare()
    else:
        b.BATCH=ROOT
        b.advance(NAME,a.action=='evaluate')
