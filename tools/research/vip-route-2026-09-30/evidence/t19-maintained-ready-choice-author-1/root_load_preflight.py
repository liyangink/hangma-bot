"""根代理封存一次作者原答并核正式解析；不评分、不修复原答。"""

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
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
from hangma_bot.offline.vip_eoh_generate import VipEohBatch,load_vip_parents,parse_vip_eoh_reply
from hangma_bot.policy.action_value_executor import ActionValueExecutor
B=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t19-maintained-ready-choice-author-1')
P=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t17-public-interruption-trade-author-1/S01-model-output')
def pin(p):
    b=p.read_bytes();return {'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def write(name,obj):
    with (_project_file(_PROJECT_ROOT, B/name)).open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
write('ROOT-AUTHOR-REPLY-FIRST-SEAL.json',{'schema':'root-author-reply-first-seal/1','created_at_utc':datetime.now(timezone.utc).isoformat(),'files':{str(_project_file(_PROJECT_ROOT, B/n)):pin(_project_file(_PROJECT_ROOT, B/n)) for n in ('RAW-REPLY.txt','candidate.py','STATIC-CHECKS.json')},'actual_author_delegations':1,'requested_model':'gpt-6.1-sol','requested_reasoning_effort':'max','actual_backend_model_and_tokens':'unknown','business_calls':0,'repair_calls':0})
batch=VipEohBatch.read(_project_file(_PROJECT_ROOT, B/'S01-generation.batch.json'))
parents=load_vip_parents([P],batch)
raw=(_project_file(_PROJECT_ROOT, B/'RAW-REPLY.txt')).read_text()
parsed=parse_vip_eoh_reply(raw,'m1',parents)
assert parsed['source_raw'].encode()==(_project_file(_PROJECT_ROOT, B/'candidate.py')).read_bytes().rstrip(b'\n')
assert parsed['source'].strip()==(_project_file(_PROJECT_ROOT, B/'candidate.py')).read_text().strip()
executor=ActionValueExecutor(parsed['source'],max_operations=batch.max_operations)
emitted=json.loads((_project_file(_PROJECT_ROOT, B/'S01-prompt-emission/generation.json')).read_text())
write('ROOT-LOAD-PREFLIGHT.json',{'schema':'t19-load-preflight/1','status':'parser_and_executor_constructor_pass_no_scoring','parent_candidate_id':parents[0]['identity']['candidate_id'],'parsed_source_sha256':hashlib.sha256(parsed['source'].encode()).hexdigest(),'raw_code_source_sha256':pin(_project_file(_PROJECT_ROOT, B/'candidate.py'))['sha256'],'emitted_prompt_sha256':emitted['prompt_sha256'],'source_raw_byte_identity':True,'reply_format_version':parsed['reply_format_version'],'actual_business_scores':0,'new_author_calls':0})
write('REPLAY-ENVELOPE.json',{'schema':'sitin-generation-reply/1','captured_at_utc':datetime.now(timezone.utc).isoformat(),'origin':'delegated_model_reply','provider':'codex-collaboration','model':'unknown','delegator':'/root via /root/t13_sol_max_joint_route_quality_author','finish_reason':'stop','prompt_sha256':emitted['prompt_sha256'],'reply':raw,'note':'Original one author reply unchanged. finish_reason=stop is ROOT self-attestation of delivered immutable outputs and FINAL_ANSWER; vendor API finish_reason and actual backend model/tokens are not exposed. This replay makes no new model call.'})
print(json.dumps({'status':'preflight_pass','source_raw':pin(_project_file(_PROJECT_ROOT, B/'candidate.py')),'prompt_sha256':emitted['prompt_sha256']},ensure_ascii=False))
