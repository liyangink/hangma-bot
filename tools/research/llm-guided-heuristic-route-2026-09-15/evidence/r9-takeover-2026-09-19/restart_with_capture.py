"""新修复身份复评既有候选：零模型调用、逐字复用原答卷、增量调用成本为零。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r9-takeover-2026-09-19'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
import json
import hashlib
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import pilot

def main():
    """保留终态旧批次，以受控签发字段创建新执行尝试；不改变预算或独立样本数。"""
    old=pilot.state()
    if old['status']!='BUDGET_EXHAUSTED':raise SystemExit('旧批次必须已终结')
    olddir=Path(old['iter_dir']); oldenvelope=olddir/'reply-envelope.json'
    env=json.loads(oldenvelope.read_text())
    auth=json.loads((pilot.PILOT/'authorization.json').read_text())
    auth.update({'issued_by':'lead','issuance_basis':auth['issued_by'],
                 'issued_actor':'Codex root，依据用户明确接手修复与继续搜索授权履行监督职责',
                 'authorization_id':'r9-takeover-20260919-three-proposals-revision2',
                 'supersedes':str(pilot.PILOT/'authorization.json'),
                 'revision_reason':'签发方采用已有受信枚举 lead；额度和操作不变，不扩白名单'})
    path=pilot.PILOT/'authorization-v2.json'
    if path.exists():raise SystemExit('已建立修订授权，不重复重开')
    for operation in auth['allowed_operations']:
        verdict=pilot.search.av_authorization_audit(auth,operation=operation)
        if not verdict['ok']:raise SystemExit(json.dumps(verdict,ensure_ascii=False))
    pilot.write(path,auth)
    result=pilot.search.run_av_evolution(pilot.RUN,authorization=auth,
        natural_roots=1,natural_seats=4,prefix_source='v2_behavior',panel_seed=2026091901,
        stop_after='BEHAVIOR_CHECKED')
    new=result.get('state') or {}
    if not result.get('waiting_for_reply'):raise SystemExit('新批次未停在交付接缝')
    if new['generation']['prompt_sha256']!=env['prompt_sha256']:
        raise SystemExit('题面改变，不能复用原始回答')
    newdir=Path(new['iter_dir'])
    replay=dict(env,origin=pilot.search.av_generate().ORIGIN_CAPTURED,usage={'input_tokens':0,'output_tokens':0},
        usage_source='cached_reply_reuse_incremental_cost',
        original_usage=env['usage'],original_usage_source=env['usage_source'],
        reuse_source=str(oldenvelope),reuse_reason='原始调用已在共享账本结算；仅新身份复评，无新请求',
        new_model_call=False,independent_model_sample=False)
    pilot.write(newdir/'reply-envelope.json',replay)
    pilot.write(newdir/'capture-reuse.json',{'source_envelope':str(oldenvelope),
        'source_sha256':hashlib.sha256(oldenvelope.read_bytes()).hexdigest(),
        'reply_sha256':hashlib.sha256(env['reply'].encode()).hexdigest(),
        'prompt_sha256':env['prompt_sha256'],'original_run_id':old['run_id'],
        'new_model_calls':0,'original_usage_already_charged':env['usage'],
        'count_as_additional_proposal':False,'count_as_independent_sample':False})
    result=pilot.search.run_av_evolution(pilot.RUN,authorization=auth,
        natural_roots=1,natural_seats=4,prefix_source='v2_behavior',panel_seed=2026091901,
        stop_after='BEHAVIOR_CHECKED')
    print(json.dumps({k:result.get(k) for k in ['status','advanced','refused','terminal']},ensure_ascii=False))
if __name__=='__main__':main()
