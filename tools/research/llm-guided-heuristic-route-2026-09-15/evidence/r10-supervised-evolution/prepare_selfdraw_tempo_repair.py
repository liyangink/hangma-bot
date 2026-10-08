"""仅为已证实的缺分支证据遗漏签发一次修复；不改变效果清单和算法公式。"""

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
import selfdraw_tempo_batch as experiment
b = experiment.b
sub = experiment.OUT / experiment.NAME
root = sub / 'run'
state_path = b.search.av_latest_state_path(root)
state = b.search.av_state_load(state_path)
assert state['status'] == 'BEHAVIOR_CHECKED'
assert not (sub / 'authorization-repair.json').exists()
evidence = sub / 'first-answer-arithmetic.json'
report = b.read(evidence)
assert report['status'] == 'FAIL'
assert len([r for r in report['rows'] if r['errors']]) == 6
first = sub / 'first-answer'
first.mkdir()
for name in ('source-review.json', 'boundary-check.json', 'diagnostic-comparison.json',
             'python-semantics-check.json', 'reference-process.json'):
    (sub / name).rename(first / name)
reason = {'reason': '缺分支时抹掉独立直接牌效或条件路线，违背冻结题面及已声明机制',
          'code': 'supervised.independent_call_facts_dropped',
          'evidence': str(evidence), 'evidence_sha256': b.digest(evidence.read_bytes()),
          'automatic_gate_failure': False}
state['rejection'] = reason
b.search.av_state_history_append(state, 'REJECTED',
    '监督算术发现六项证据保留反例；原始公共门禁PASS保留，效果桌赛0')
b.search.av_state_save(state_path, state)
b.search.av_proposal_event_record(root, state)
b.write(sub / 'repair-needed.json', {'status':'ACTUAL_IMPLEMENTATION_DEFECT',
    'calls_used':1, 'calls_remaining':1, 'evidence':reason, 'effect_tables':0,
    'scope':'只修独立事实保留及同刻度比较；不调公式、不换机制、不看效果'})
auth = b.read(sub / 'authorization.json')
auth['supervisor_feedback'] += '''\n这是首答的唯一一次实际实现错误修复，原有I1方向及所有T/R/结算公式、常数保持。公共准入通过；112固定输入均可评分且标准Python/受限执行一致，最高26524操作，不是性能问题。独立12项算术有6项失败，全因吃碰路径仅在followup_branches中找直接/路线证据。冻结任务明确：分支缺失不抹掉独立成功的直接事实或条件路线；你原答也声明独立已知T仍可用。CandidateFacts公开合同规定，吃碰的shanten_after/useful_tiles已经是最佳合法后续弃牌后的等待状态，并有best_followup_discard；不需要分支列表才能用。ValueRoute也独立生产，缺失/部分分支列表不能否定已存在条件见证。
反例1：peng:4b直接shanten_after=1、支持12、best_followup_discard=9b，followup_branches=None；pass直接q=1,n=10。按原公式应508对500，实际-330对500。把唯一分支设成combined_shanten/support_remaining均None或均True，独立直接事实仍应508，当前也错误退为-330。
反例2：peng:4b无直接牌效、followup_branches=None，但routes里有followup_discard=9b、shanten=0、useful_tiles=[{code:1t,remaining_estimate:2}]、本人条件增量12、四座[12,-4,-4,-4]、正常摸牌见证，阶段账未知。原公式R=760+480/52=769.230769...；当前退为-350。相同见证discard=8b即使不在仅含9b的部分分支列表里也不能消失；它不是需要你重建的合法性，而是独立已生产路线。两条互斥已知路线n=2与n=4、同增量12时只应取790+480/52，不得相加。
要求：在不改变其他公式/胡最高层/未知锚定前提下，使吃碰的已知直接前沿、每个已知分支前沿、每条独立条件见证均能在同一刻度选择唯一最佳者。说明直接值绑定best_followup_discard，路线绑定自己的followup_discard；不将不同弃牌或条件拼接。缺失、未知或布尔分支不否定其他事实，不把不完整路线伪造成完整路线。现有有完整分支的分数可能因恢复此前遗漏的直接分牌型或路线证据而变化，应诚实记为缺陷修复，不能承诺全域不变。
只修这一遗漏并补充对应手算和可比行为说明，完整交付正式I1格式及源码；不要调整模型外参数、其他启发或编写测试。可读取同目录author-reply.txt首答，除此只读冻结修复prompt。无新增效果反馈，不声称已测试。'''
assert len(auth['supervisor_feedback']) <= 12000
b.write(sub / 'authorization-repair.json', auth)
b.write(sub / 'author-task-01.json', b.read(sub / 'author-task.json'))
new = b.search.av_start_iteration(root, operator='i1', generation_mode='delegate',
    predicate='branch_open', opponent='H', natural_roots=8, natural_seats=4,
    prefix_source='v2_behavior', panel_seed=2026092001, authorization=auth,
    archive_in={'source':'empty','path':None,'applied_operator':'i1',
                'note':'同一独立I1的唯一缺证据实现修复；不是新的机制初答'})
assert not new.get('stop_reason'), new.get('stop_reason')
r=b.search.av_iteration_advance(b.search.av_latest_state_path(root),root,
    authorization=auth,stop_after='BEHAVIOR_CHECKED')
assert r.get('waiting_for_reply'),r
state=b.search.av_state_load(b.search.av_latest_state_path(root))
prompt=b.Path(state['generation']['pending_dir'])/'prompt.txt'
b.write(sub/'author-task.json',{'model':'gpt-5.6-terra','effort':'max','task':'i1-repair',
    'prompt':str(prompt),'prompt_sha256':b.digest(prompt.read_bytes()),
    'reply_path':str(sub/'author-reply-repair.txt'),
    'dispatch_file':'author-dispatch-repair.json','completion_file':'author-completion-repair.json'})
print('repair prepared',b.digest(prompt.read_bytes()),len(prompt.read_text()),flush=True)
