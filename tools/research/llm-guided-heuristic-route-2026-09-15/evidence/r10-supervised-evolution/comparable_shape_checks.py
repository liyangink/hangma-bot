"""新弃牌结构的固定多来源行为与跨执行器核验，不把改选当效果。"""

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
import json
import subprocess
import sys
import strong_seed_batch as b
import comparable_shape_batch as batch
import diverse_proposal_checks as inherited
import check_candidate_python_semantics as semantics

PANEL=batch.OUT/'diagnostic-panel.json'


def freeze():
    """交付前合并旧112窗与新诊断原件；不按新源码挑输入。"""
    assert not PANEL.exists()
    old_path=b.HERE/'stage-rank-preflight-20260920/panel.json'
    old=b.read(old_path);assert old['deps_digest']==b.search.av_gates().av_deps_digest()
    rows=list(old['rows'])
    recent=b.HERE/'discard-shape-mix-diagnostic-20260920/panel.json'
    _,loaded=b.behavior.load_panel(recent)
    for name,request in loaded:
        rows.append({'origin':'shape_mix','name':name,'record':b.behavior.capture_request(request)})
    b.write(PANEL,{'at_utc':b.search.utc_now(),'rows':rows,'deps_digest':old['deps_digest'],
        'provenance':[{'path':str(p),'sha256':b.digest(p.read_bytes())} for p in (old_path,recent)],
        'scope':'112旧固定输入加新诊断去重窗口；来源有相关性，不是独立效果样本'})
    print('frozen inputs',len(rows),flush=True)


def behavior():
    """检查完整分数和顺序，另外检查非弃牌分数没有被新机制意外改变。"""
    inherited.PANEL=PANEL;inherited.experiment.OUT=batch.OUT
    inherited.check(batch.NAME)
    report=b.read(batch.OUT/batch.NAME/'diagnostic-comparison.json')
    source=b.read(PANEL);summary={};changed_non_discard=[]
    for row,original in zip(report['rows'],source['rows'],strict=True):
        counts=summary.setdefault(row['origin'],{'inputs':0,'scored':0,'first_changed':0,'scores_changed':0})
        counts['inputs']+=1;counts['scored']+=row['results']['candidate']['status']=='SCORED'
        for key in ('first_changed','scores_changed'):counts[key]+=row[key]
        request=b.behavior.decision_request_from_json(original['record']['request'])
        view=b.behavior.build_scoring_view(request)
        before={e['action_key']:e['score'] for e in row['results']['parent']['entries']}
        after={e['action_key']:e['score'] for e in row['results']['candidate']['entries']}
        for a in view.actions:
            # 未知底分可以因已知动作最低分移动；只核对两端已知非弃牌。
            if a.action_type!='discard':
                old=next((e for e in row['results']['parent']['entries'] if e['action_key']==a.action_key),None)
                new=next((e for e in row['results']['candidate']['entries'] if e['action_key']==a.action_key),None)
                if old and new and old['trace'].get('unknown') is not True and new['trace'].get('unknown') is not True and before[a.action_key]!=after[a.action_key]:
                    changed_non_discard.append({'origin':row['origin'],'name':row['name'],'action_key':a.action_key})
    b.write(batch.OUT/batch.NAME/'diagnostic-scope-summary.json',{'summary':summary,
        'known_non_discard_score_changes':changed_non_discard,'source_sha256':report['source_sha256'],
        'scope':'已知非弃牌分数变动需源码裁定；本检查不是算法效果门禁'})
    print(summary,'known non-discard changes',len(changed_non_discard),flush=True)


def reference(worker=False):
    """只执行已静态准入且被监督审阅的源码，独立进程限30秒。"""
    semantics.experiment.OUT=batch.OUT;semantics.checks.PANEL=PANEL
    if worker:
        state=b.search.av_state_load(b.search.av_latest_state_path(batch.OUT/batch.NAME/'run'))
        semantics.worker(batch.NAME,b.Path(state['iter_dir'])/'generation/candidate.py');return
    output=batch.OUT/batch.NAME/'python-semantics-check.json';assert not output.exists()
    result=subprocess.run([sys.executable,__file__,'reference','--worker'],capture_output=True,text=True,timeout=30,check=True)
    data=json.loads(result.stdout);data['scope']='冻结组合输入的标准Python/受限执行器分数与trace对照，不证明全域等价'
    b.write(output,data);print(data['status'],data['cases'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','behavior','reference']);p.add_argument('--worker',action='store_true');a=p.parse_args()
    freeze() if a.action=='freeze' else behavior() if a.action=='behavior' else reference(a.worker)
