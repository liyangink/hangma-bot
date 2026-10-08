"""修正早期诊断根请求的窗口标签旁路副本；不覆盖已冻结数据或重跑结果。"""

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
from dataclasses import replace
import gzip
import hashlib
import json

from lab import DecisionBudget
from response_probe import DIRECTORY, CASES, root
from upgrade_persistent import upgrade_policy
from hangma_bot.application.audit_codec import decision_request_from_json,decision_request_to_json


async def main():
    output=DIRECTORY/'root-request-corrections.jsonl.gz'
    count=0
    with gzip.open(output,'xt',encoding='utf8') as stream:
        for case in CASES:
            original=DIRECTORY/(case['case_id']+'.jsonl.gz')
            raw_hash=hashlib.sha256(original.read_bytes()).hexdigest()
            for row in map(json.loads,gzip.open(original,'rt')):
                _,raw,world=root(case,row['seed'])
                decision=next(d for d in raw.frame(world).decisions if d.observation.seat==0)
                old=decision_request_from_json(row['root_request'])
                assert old.observation==decision.observation
                corrected=replace(old,window_key=decision.window_key)
                assert old.window_key!=corrected.window_key
                policy=upgrade_policy()
                before=await policy.choose(old,DecisionBudget(10,11,12))
                after=await policy.choose(corrected,DecisionBudget(10,11,12))
                assert before.candidates==after.candidates
                assert after.candidates[0].action_key==row['baseline_action']
                assert all(arm['trace'][0]['policy_action']==row['baseline_action'] for arm in row['arms'].values())
                stream.write(json.dumps(dict(case_id=case['case_id'],seed=row['seed'],original_sha256=raw_hash,
                    corrected_root_request=decision_request_to_json(corrected)),ensure_ascii=False)+'\n')
                count+=1
    report=dict(requests=count,candidate_plans_unchanged=True,
        actual_continuation_already_used_authoritative_window=True,
        cause='根诊断沿用仅用于摸牌案例的 lab.request_for，window_key.phase 被标记为 DRAW；实际 conditional_play 已用真实模拟窗口',
        raw_results_untouched=True,corrected_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    (DIRECTORY/'root-window-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':
    asyncio.run(main())
