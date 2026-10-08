"""全部构造起手的分牌型诊断；不按此前七对二向听筛选，也不使用未来牌。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/big-hand-paths-2026-09-09'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import asyncio
from collections import Counter
from dataclasses import asdict
import gzip
import hashlib
import json
import time

from lab import HERE, ROOT, RULESET, HangmaRules, RuleConfig, observation, request_for, DecisionBudget
from mutations import generated_cases
from frontier import V2RouteFrontierPolicy, preserves_standard_progress
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2


def facts_row(candidate):
    """只导出可见事实；集合中的剩余量含他家暗牌，不是墙内确切张数。"""
    f=candidate.facts
    if f is None or f.seven_pairs_shanten_after is None:return None
    return dict(action=candidate.action_key, shanten=f.shanten_after,
        standard=f.standard_shanten_after, seven=f.seven_pairs_shanten_after,
        useful={t.code:t.remaining_estimate for t in f.useful_tiles},
        standard_useful=None if f.standard_useful_tiles is None else {t.code:t.remaining_estimate for t in f.standard_useful_tiles},
        seven_useful=None if f.seven_pairs_useful_tiles is None else {t.code:t.remaining_estimate for t in f.seven_pairs_useful_tiles})


async def run():
    """固定全部2,525个输入；报告未触发原因，不把构造集频率当自然赛频率。"""
    directory=_project_file(_PROJECT_ROOT, HERE/'pattern-progress');directory.mkdir(exist_ok=True)
    output=directory/'all-opening.jsonl.gz'
    if output.exists():raise FileExistsError(output)
    rules=HangmaRules(RuleConfig(RULESET,1,False))
    baseline=ComparableHeuristicPolicyV2(monotonic=lambda:0)
    frontier=V2RouteFrontierPolicy(monotonic=lambda:0)
    counts=Counter();differences=[]; started=time.monotonic()
    with gzip.open(output,'wt',encoding='utf8') as stream:
        for case in generated_cases():
            obs=observation(case.initial_hand,case_id=case.case_id,wall=83,dealer=0)
            analysis=rules.analyze(obs);request=request_for(obs,analysis)
            base=await baseline.choose(request,DecisionBudget(10,11,12))
            new=await frontier.choose(request,DecisionBudget(10,11,12))
            old=next(c for c in analysis.legal_candidates if c.action_key==base.candidates[0].action_key)
            counts['inputs']+=1
            alternatives=[]
            if old.action_key.startswith('discard:') and old.facts.seven_pairs_shanten_after is not None:
                counts['baseline_discard']+=1
                counts[f'baseline_seven_{old.facts.seven_pairs_shanten_after}']+=1
                for candidate in analysis.legal_candidates:
                    f=candidate.facts
                    if not candidate.action_key.startswith('discard:') or f.seven_pairs_shanten_after>=old.facts.seven_pairs_shanten_after:
                        continue
                    row=facts_row(candidate)
                    row['standard_no_regression']=preserves_standard_progress(f,old.facts)
                    alternatives.append(row)
                if alternatives:
                    counts['has_closer_seven']+=1
                    counts['has_standard_no_regression']+=any(r['standard_no_regression'] for r in alternatives)
            if new.candidates[0].action_key!=old.action_key:
                counts['frontier_changes']+=1
                differences.append(case.case_id)
            stream.write(json.dumps(dict(case=asdict(case),baseline=old.action_key,
                frontier=new.candidates[0].action_key,baseline_facts=facts_row(old),
                closer_seven=alternatives,candidates=[r for c in analysis.legal_candidates if (r:=facts_row(c)) is not None]),ensure_ascii=False)+'\n')
    report=dict(schema='pattern-probe/1',rules_config=dict(you_cai_bi_kao=False),
        generation_seed=2026090901,counts=counts,frontier_cases=differences,elapsed_seconds=time.monotonic()-started,
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [_project_file(_PROJECT_ROOT, HERE/'pattern_probe.py'),_project_file(_PROJECT_ROOT, HERE/'mutations.py'),_project_file(_PROJECT_ROOT, HERE/'frontier.py'),_project_file(_PROJECT_ROOT, HERE/'lab.py'),
                *sorted((_project_file(_PROJECT_ROOT, ROOT/'src/hangma_bot/hangma')).glob('*.py'))]},
        data_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    (directory/'probe-summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(counts=counts,frontier_cases=differences,elapsed_seconds=report['elapsed_seconds']),ensure_ascii=False))


if __name__=='__main__':asyncio.run(run())
