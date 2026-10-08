"""冻结续打结果的配对分析；条件案例均值不能外推成自然桌赛平均净分。"""

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
from collections import Counter
import gzip
import hashlib
import json
import random

from lab import HERE,ROOT

DIRECTORY=_project_file(_PROJECT_ROOT, HERE/'pattern-progress')
CONTRASTS={
    'root_with_v2':('seven_v2','base_v2'),
    'continuation_after_seven':('seven_persistent','seven_v2'),
    'root_with_persistent':('seven_persistent','base_persistent'),
    'combined':('seven_persistent','base_v2'),
}


def interval(values,rng):
    """本案例固定条件世界的配对重采样；返回95%区间，不用于赛事门禁。"""
    means=sorted(sum(rng.choices(values,k=len(values)))/len(values) for _ in range(4000))
    return [means[99],means[3899]]


def main():
    manifest=json.loads((DIRECTORY/'persistent-freeze.json').read_text())
    summaries=json.loads((DIRECTORY/'persistent-summary.json').read_text())
    assert len(summaries['cases'])==len(manifest['cases'])==11
    for name,expected in manifest['source_sha256'].items():
        assert hashlib.sha256((_project_file(_PROJECT_ROOT, ROOT/name)).read_bytes()).hexdigest()==expected,name
    frozen_summary={r['case_id']:r for r in summaries['cases']}
    all_rows=[];cases=[];rng=random.Random(1080999)
    for case in manifest['cases']:
        cid=case['case']['case_id'];path=DIRECTORY/f'persistent-{cid}.jsonl.gz'
        assert hashlib.sha256(path.read_bytes()).hexdigest()==frozen_summary[cid]['sha256']
        rows=[json.loads(x) for x in gzip.open(path,'rt')]
        assert [r['seed'] for r in rows]==list(range(manifest['seed_range'][0],manifest['seed_range'][1]+1))
        assert all(r['case_id']==cid and len(r['arms'])==4 for r in rows)
        arm_stats={}
        for arm in rows[0]['arms']:
            outcomes=[r['arms'][arm] for r in rows]
            wins=[o for o in outcomes if o['winner']==0]
            arm_stats[arm]=dict(mean_score=sum(o['score'] for o in outcomes)/len(rows),
                own_hu=len(wins),draws=sum(o['winner'] is None for o in outcomes),
                win_fan=dict(Counter(o['fan'] for o in wins)),
                win_details=dict(Counter('·'.join(o['details']) for o in wins)),
                own_changed_decisions=sum(sum(t['enhanced'] for t in o['trace']) for o in outcomes))
        contrasts={}
        for name,(new,old) in CONTRASTS.items():
            values=[r['arms'][new]['score']-r['arms'][old]['score'] for r in rows]
            contrasts[name]=dict(mean=sum(values)/len(values),ci95=interval(values,rng))
        cases.append(dict(case_id=cid,hand=case['case']['initial_hand'],root_actions=[case['baseline'],case['alternative']],
            arms=arm_stats,contrasts=contrasts))
        all_rows.extend(rows)
    pooled={}
    for arm in all_rows[0]['arms']:
        outcomes=[r['arms'][arm] for r in all_rows];wins=[o for o in outcomes if o['winner']==0]
        pooled[arm]=dict(mean_score=sum(o['score'] for o in outcomes)/len(outcomes),own_hu=len(wins),
            win_fan=dict(Counter(o['fan'] for o in wins)),win_details=dict(Counter('·'.join(o['details']) for o in wins)),
            mean_win_score=sum(o['score'] for o in wins)/len(wins) if wins else None,
            changed_decisions=sum(sum(t['enhanced'] for t in o['trace']) for o in outcomes))
    result=dict(schema='persistent-analysis/1',scope='11个固定构造起手的条件世界开发分析，非自然桌赛效果',
        worlds=len(all_rows),hands=4*len(all_rows),cases=cases,pooled=pooled,
        sources_verified=True,elapsed_seconds=summaries['elapsed_seconds'])
    (DIRECTORY/'persistent-analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(worlds=len(all_rows),hands=4*len(all_rows),pooled=pooled),ensure_ascii=False,indent=2))
    for case in cases:print(case['case_id'],case['contrasts'])


if __name__=='__main__':main()
