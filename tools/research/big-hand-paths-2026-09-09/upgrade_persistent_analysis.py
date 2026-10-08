"""等胡交叉对照的配对差值；复用世界只用于消融，不作为独立确认。"""

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
import gzip
import json
import random

from lab import HERE
import persistent_analysis


def main():
    directory=_project_file(_PROJECT_ROOT, HERE/'upgrade-persistent-v2')
    persistent_analysis.DIRECTORY=directory
    persistent_analysis.CONTRASTS={
        'root_with_upgrade':('seven_upgrade','base_upgrade'),
        'continuation_after_seven':('seven_combined','seven_upgrade'),
        'root_with_combined':('seven_combined','base_combined'),
        'combined':('seven_combined','base_upgrade'),
    }
    persistent_analysis.main()
    old_dir=_project_file(_PROJECT_ROOT, HERE/'pattern-progress')
    manifest=json.loads((directory/'persistent-freeze.json').read_text())
    grouped={};hu_decisions={};rng=random.Random(1080998)
    comparisons={
        'upgrade_only_increment':('base_upgrade','base_v2'),
        'root_and_upgrade_increment':('seven_upgrade','base_upgrade'),
        'persistent_increment_on_upgrade':('seven_combined','seven_upgrade'),
        'combined_increment_on_upgrade':('seven_combined','base_upgrade'),
        'upgrade_increment_on_persistent':('seven_combined','seven_persistent'),
    }
    for case in manifest['cases']:
        filename=f'persistent-{case["case"]["case_id"]}.jsonl.gz'
        old=[json.loads(x) for x in gzip.open(old_dir/filename,'rt')]
        new=[json.loads(x) for x in gzip.open(directory/filename,'rt')]
        groups={name:[] for name in comparisons}
        for a,b in zip(old,new,strict=True):
            assert (a['case_id'],a['seed'],a['source_sha256'])==(b['case_id'],b['seed'],b['source_sha256'])
            arms={**a['arms'],**b['arms']}
            for name,(new_arm,old_arm) in comparisons.items():
                groups[name].append(arms[new_arm]['score']-arms[old_arm]['score'])
            for arm,result in b['arms'].items():
                counts=hu_decisions.setdefault(arm,dict(hu_opportunities=0,hu_declines=0))
                counts['hu_opportunities']+=len(result['hu_choices'])
                counts['hu_declines']+=result['hu_declines']
        for name,values in groups.items():grouped.setdefault(name,[]).append(values)
    effects={}
    for name,groups in grouped.items():
        boot=sorted(sum(sum(rng.choices(values,k=len(values)))/len(values) for values in groups)/len(groups)
                    for _ in range(4000))
        effects[name]=dict(mean=sum(sum(values)/len(values) for values in groups)/len(groups),
            ci95=[boot[99],boot[3899]])
    report=dict(scope='固定11个构造案例，分别在案例内重采样64个条件世界，再等权平均；非自然桌赛总体',
        paired_worlds_verified=True,bootstrap_seed=1080998,effects=effects,hu_decisions=hu_decisions)
    (directory/'cross-analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
