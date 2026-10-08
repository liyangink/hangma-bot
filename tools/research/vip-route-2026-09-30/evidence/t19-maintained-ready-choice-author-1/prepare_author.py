"""标准库冻结一份当前胡取舍作者材料，仅读既有公开证据，不评分。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t19-maintained-ready-choice-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip,hashlib,json,datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent
BASE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(name,value):
    with (_project_file(_PROJECT_ROOT, HERE/name)).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')

def main():
    t17=_project_file(_PROJECT_ROOT, BASE/'t17-public-interruption-trade-author-1')
    diag=_project_file(_PROJECT_ROOT, BASE/'t18-natural-outcome-and-three-white-diagnostic-1')
    closure=_project_file(_PROJECT_ROOT, BASE/'t18-maintained-wait-abc-closure-1')
    origin=_project_file(_PROJECT_ROOT, BASE/'t18-actual-C-maintained-wait-abc-preparation-2')
    selection=read(origin/'SOURCE-SELECTION.json');inputs=read(diag/'ALL-C-CURRENT-HU-PUBLIC-INPUTS.json')
    wanted={s['fact']['input_capture']['view_sha256'] for s in selection['selected']};views={}
    with gzip.open(t17/'S01-natural-development-64/views.jsonl.gz','rt') as stream:
        for line in stream:
            row=json.loads(line)
            if row['view_sha256'] in wanted:views[row['view_sha256']]=row['view']
    assert set(views)==wanted
    feedback={
        'scope':'known development public inputs and intervention results; no hidden hands or future wall',
        'parent':{'package':str((t17/'S01-model-output').resolve()),'candidate_id':'b198e694fb46bb95cfac31b0d14a08744e018efb5f0966034b4015a31b05f655','source_sha256':sha(t17/'candidate.py')},
        'closed_natural_summary':{'source_roots':4,'H_CA':1.0625,'M_CA':-9.6875,'combined_CA':-4.3125,'self_fan_ge4':0,'self_Hu_increase_mainly_fan1':True,'not_confirmation_or_strength':True},
        'intervention_receipt':read(closure/'ROOT-CLOSED-CHECK.json'),
        'intervention_results':read(closure/'DEVELOPMENT-BEHAVIOR.json'),
        'actual_public_cases':[{'selection':s,'original_C_input':next(r for r in inputs['rows'] if r['pool']==s['fact']['pool'] and r['window_key']==s['fact']['window_key']),'complete_DTO':views[s['fact']['input_capture']['view_sha256']]} for s in selection['selected']],
        'all_85_public_condition_facts':read(diag/'CURRENT-HU-MAINTAINED-WAIT-FACTS.json'),
        'interpretation':'three different source roots and three continuations, both worlds +10 versus immediateHu, no continuation loss. Local VIP early stopping shortfall; not superiority over R18. Old pointwise currentHu protection was author scope, not permanent framework contract.'}
    with (_project_file(_PROJECT_ROOT, HERE/'FEEDBACK.json')).open('x') as f:json.dump(feedback,f,ensure_ascii=False,separators=(',',':'),allow_nan=False);f.write('\n')
    batch=read(t17/'S01-generation.batch.json');batch['batch_id']='vip-t19-S01-maintained-ready-choice-20261002'
    write('S01-generation.batch.json',batch)
    plan={
        'schema':'t19-maintained-ready-choice-development-plan/1','status':'frozen_before_one_author','at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'true_parent_package':str((t17/'S01-model-output').resolve()),'true_parent_candidate_id':feedback['parent']['candidate_id'],'authors_max':1,
        'single_mechanism':'current legal Hu versus qualified maintained-ready next-own-draw trade within complete joint formula',
        'protected_pointwise_parent':'no current legal Hu, or current zero whites: all legal root numeric values same as actual T17 parent',
        'allowed_change':'current-Hu anchored wait ranking and bounded trace only; immediate settlement/pay_points/normal payments/natural geometry/non-Hu mechanisms unchanged',
        'public_probes':{'old_cross_source_windows_upper':160,'all_actual_T17_current_Hu_windows':85,'parent_child_score_entries_upper':490},
        'local_continuation_gate':{'existing_four_public_sources':'new candidate naturally chooses first action; no forced C; B first candidate action then R18','max_arms':40,'T18_forced_results_not_imported_as_child_credit':True,'other_negative_or_late_wall':'freeze by public predicate before endpoint reading, separate small budget when informative'},
        'fresh_natural_frame':{'seed_ids':[2026102401,2026102402,2026102403,2026102404],'source_roots':4,'pools':['H','M'],
            'permutations':[[0,1,2,3],[1,2,3,0],[2,3,0,1],[3,0,1,2]],'hands_per_table':8,'child_and_parent_separate_same_tool_batches':True,
            'first_two_roots_actual_table_instances_upper':64,'all_four_roots_actual_table_instances_upper':128,
            'baseline_A_repeated_across_candidates_not_independent':True,'next_two_roots_only_after_root_assesses_first_two':True,'no_natural_START_issued':True},
        'effect_gates':['complete legal finite scores, same actual DTOs/identity, zero C normal fallback','natural child enters upgrade across sources; ordinary and late-wall exits remain','same-start child vs true parent and R18, retain all negative outcomes','new common-root complete table true parent increment and R18 gap; development only','later unexposed confirmation and rule/timing/wiring/independent promotion before release'],
        'review_policy':'same contract/tool root checks; independent on interfaces/rules/new critical tools/promotion only',
        'no_new_rules_interfaces_or_online_changes':True,'no_auto_second_author_or_tables':True,'within_live_families_six_formula_limit':True,
        'not_confirmation':True,'new_score_world_model_calls_in_plan':0}
    write('EVALUATION-PLAN.json',plan)
    task='''请交付恰一份完整m1联合公式，真父T17/S01-model-output，同240万操作身份。唯一新机制：已有合法Hu时，用真实保持听牌的下一普通摸牌资格/支付，合理排名立即胡与非白弃牌继续等。旧批次当前Hu全部等父值只是范围限制，本批解除这一个限制。无当前合法Hu及当前零白输入全部合法根分值必须逐项等于真父T17。即时Hu/pay_points、精确结算、条件支付、自然用途、既有公开交互与非Hu聚合不改；不扩接口，不复制规则。

40条显式首手干预已闭：三个不同母牌山，三白4b、二白6w/5t，原世界与公开相容隐藏世界、R18/T17/T16三续策均由当前一番+10变保持听牌二番+20；零白胡24持平。VIP自然选择仍Hu，定位当下取舍，未见续策损失，不证明胜过R18。32码/79公开未见张不是墙内概率或存活承诺。不得按牌码、形状样本、seq/hash特判；应由已有条件事实全局判断。

结合完整公开DTO/原评分及受控结果，给出小而通用的共同排序公式：保持听牌、公开支持覆盖、下一摸支付下界/包络和高番增量、需要等待次数、墙余与三家公开副露粗压力。仅排名点启发式，不假称生存概率或精确长期期望；未知资格不写为零或全覆盖，不无限等，不全部放弃当前二番/大牌。晚墙/无升级/非保持听牌/危险副露普通出口保留。有界先验明确非规则。继承父公式原式不算R18回退，正常全动作自身评分不回退R18。只读已知支付；新增少量常数说明单位/界，m1 parameter_changes=[]，trace保持父压缩界。成效由根验证，不自报。

读S01-prompt-emission/prompt.txt、只读合同、真T17 candidate.py、FEEDBACK。写RAW-REPLY.txt（严格一句思想、一个json围栏含完整m1机制、一个完整python围栏）、candidate.py与原围栏代码字节一致、STATIC-CHECKS.json。仅AST/compile/静态差异；禁止规则、评分、世界、桌赛、网络、额外模型、git、START或隐式自修。一份交付后结束。请求GPT6.1 Sol/max，实际后端/token未暴露记未知。
'''
    with (_project_file(_PROJECT_ROOT, HERE/'AUTHOR-TASK.txt')).open('x') as f:f.write(task)
    write('PREPARATION-RECEIPT.json',{'status':'closed_stdlib_public_author_materials','feedback_bytes':(_project_file(_PROJECT_ROOT, HERE/'FEEDBACK.json')).stat().st_size,'source_sha256':sha(Path(__file__)),'new_score_rule_world_model_calls':0})
    print(json.dumps({'status':'prepared','feedback_bytes':(_project_file(_PROJECT_ROOT, HERE/'FEEDBACK.json')).stat().st_size,'new_model_calls':0,'fresh_roots_frozen':4}))

if __name__=='__main__':main()
