"""独立列举次优牌型奖励与底分；不复制候选的分组循环作期望值。"""

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
import re
from dataclasses import replace
import strong_seed_batch as b
import pattern_option_batch as batch
from check_discard_arithmetic import action, view
from hangma_bot.hangma.interface import UsefulTileFact
from hangma_bot.policy.action_value_seeds import ActionValueScorer


def shaped(code='1w', gap=1, unique=8, seven_best=False):
    """合成普通/七对事实；主支持12张，次支持共享4张及指定独有枚数。"""
    a=action(code,12,2)
    extras=[]
    for tile in ('7b','8b','9b'):
        n=min(unique,4)
        if n:extras.append(UsefulTileFact(tile,n))
        unique-=n
    assert unique==0
    secondary=(UsefulTileFact('1t',4),)+tuple(extras)
    return replace(a, standard_shanten_after=2+gap if seven_best else 2,
        seven_pairs_shanten_after=2 if seven_best else 2+gap,
        standard_useful_tiles=secondary if seven_best else a.useful_tiles,
        seven_pairs_useful_tiles=a.useful_tiles if seven_best else secondary)


def main():
    """先验证移除新增机制恢复父代，再核验固定非零分数与安全底分。"""
    sub=batch.OUT/batch.NAME
    state=b.search.av_state_load(b.search.av_latest_state_path(sub/'run'))
    path=b.Path(state['iter_dir'])/'generation/candidate.py'
    source=path.read_text();parent=(b.Path(b.read(batch.OUT/'manifest.json')['parent'])/'candidate.py').read_text()
    reverted=source.replace(source.splitlines()[0],parent.splitlines()[0],1)
    reverted=reverted.replace('    hu_present = False\n','').replace('        if kind == "hu":\n            hu_present = True\n','')
    start=reverted.index('        pattern_bonus = 0.0\n');end=reverted.index('        produced = ',start)
    reverted=reverted[:start]+reverted[end:]
    start=reverted.index('        pattern_applied_bonus = ');end=reverted.index('        trace = ',start)
    reverted=reverted[:start]+reverted[end:]
    start=reverted.index('        pattern_bonus = entry.get(');end=reverted.index('        final_entries.append(',start)
    reverted=reverted[:start]+reverted[end:]
    reverted=re.sub(r', "pattern[^"\n]*": [^,}\n]+','',reverted)
    reverted=reverted.replace('；分牌型选择余地只作用于无胡的直接弃牌','')
    assert reverted==parent, '新机制移除后未精确恢复父代'
    scorers={label:ActionValueScorer(label,code) for label,code in [('candidate',source),('parent',parent)]}
    cases=[('gap1_u8',view((shaped(),),familiar=()),2),
        ('gap2_u8',view((shaped(gap=2),),familiar=()),1),
        ('gap1_u4',view((shaped(unique=4),),familiar=()),1),
        ('cap_u12',view((shaped(unique=12),),familiar=()),2),
        ('only_shared',view((shaped(unique=0),),familiar=()),0),
        ('gap3',view((shaped(gap=3),),familiar=()),0),
        ('same_best',view((shaped(gap=0),),familiar=()),0),
        ('seven_best',view((shaped(seven_best=True),),familiar=()),2),
        ('pattern_note',view((replace(shaped(),pattern_progress_note='公开计数缺证据'),),familiar=()),0),
        ('hu_suppresses',view((shaped(),action('',kind='hu')),familiar=()),0),
        ('unknown_anchor',view((shaped(),action('',kind='pass')),familiar=()),2)]
    rows=[]
    for name,sample,delta in cases:
        answers={k:s.score(sample) for k,s in scorers.items()}
        scores={k:{e.action_key:e.score for e in v.entries} for k,v in answers.items()}
        expected=scores['parent']['discard:1w']+delta
        assert scores['candidate']['discard:1w']==expected,(name,scores,expected)
        if name=='hu_suppresses':assert scores['candidate']==scores['parent']
        if name=='unknown_anchor':assert scores['candidate']['pass'] < scores['candidate']['discard:1w']
        rows.append({'name':name,'expected_bonus':delta,'scores':scores,'trace':{e.action_key:dict(e.trace) for e in answers['candidate'].entries}})
    b.write(sub/'independent-arithmetic.json',{'status':'PASS_WITH_TRACE_CAVEAT','cases':len(rows),'rows':rows,
        'ablation_restores_parent_bytes':True,'source_sha256':b.digest(path.read_bytes()),
        'trace_caveat':'unknown_policy沿用known_final_floor_minus_1名称，但新增非负奖励在旧底分确定后加入；未知严格低于所有已知保持成立，数值并非总等于新最低分减1。新机制奖励为0时精确还原父代。此是审计标签偏差，非未知越位；不据此改写候选或放松安全门禁。',
        'scope':'11个后验独立合成算术，另有作者前冻结14边界；不计强度样本','release_eligible':False})
    b.write(sub/'source-review.json',{'source_sha256':b.digest(path.read_bytes()),'allow_development_evaluation':False,
        'status':'MATH_REVIEWED_PENDING_TRIGGER_AND_REFERENCE','ablation_restores_parent_bytes':True,
        'unknown_safety':'奖励非负且仅直接已知弃牌；未知旧底分仍严格低于所有新已知分；含胡时奖励归零',
        'trace_caveat':'底分标签沿用旧名，实际仍以奖励前的父代已知最低分锚定；如晋升需澄清后重验',
        'initial_reference_attempt':'因源码裁定尚未写出被检查器拒绝，未得到Python语义比较；待此裁定后复跑',
        'release_eligible':False})
    print('arithmetic PASS 11; exact ablation PASS; nonblocking trace caveat')


if __name__=='__main__':main()
