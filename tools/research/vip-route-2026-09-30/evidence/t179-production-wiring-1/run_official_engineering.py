"""一次必要接线复验：四席同配置，小房自然完赛；不自动续、不终止玩家。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t179-production-wiring-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import httpx
import hangma_bot.bootstrap as b
ROOT=_PROJECT_ROOT;HERE=Path(__file__).resolve().parent
WORK=Path(b.__file__).resolve().parents[2]
HOST='10.240.169.190'
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
def main():
    assert (_project_file(_PROJECT_ROOT, HERE/'REAL-FACTORY-RESULT-001.json')).exists()
    assert json.loads((_project_file(_PROJECT_ROOT, HERE/'REAL-FACTORY-RESULT-001.json')).read_text())['all_original_deadlines_and_scores_exact']
    package=b._load_vip_testroom_manifest()
    directory=_project_file(_PROJECT_ROOT, HERE/'official-engineering-001');directory.mkdir(exist_ok=False)
    private=_project_file(_PROJECT_ROOT, ROOT/'.private/t179-wiring/official-engineering-001');private.mkdir(mode=0o700,exist_ok=False)
    raw=(_project_file(_PROJECT_ROOT, ROOT/'.private/portal-session/cookie.txt')).read_text().strip();cookie=raw if '=' in raw else 'majiang_sid='+raw
    payload={'m':2,'rounds':2,'base_score':1,'you_cai_bi_kao':False,'peng_timeout_sec':1,'chi_timeout_sec':1,'discard_timeout_sec':3,'timeout_min':30}
    save(directory/'CREATE-START.json',{'at_unix':time.time(),'payload':payload,'non_idempotent_attempts_allowed':1})
    with httpx.Client(verify=False,trust_env=False,timeout=40,headers={'Cookie':cookie}) as client:
        response=client.post('https://'+HOST+':18080/portal/api/test-rooms',json=payload)
        rawpath=private/'create-response.bin';rawpath.write_bytes(response.content);rawpath.chmod(0o600)
        save(directory/'CREATE-HTTP-RECEIPT.json',{'http_status':response.status_code,'raw_sha256':hashlib.sha256(response.content).hexdigest(),'raw_kept_private':True})
        assert response.status_code==200,'建房未确认成功；保留原件，不自动重复POST'
        room=response.json()
    assert room['room_id'].startswith('t_') and len(room['players'])==4
    slots=('qinglong','baihu','zhuque','xuanwu');identities=[]
    for slot,player in zip(slots,room['players']):
        token=private/(slot+'.token')
        with token.open('x') as stream:os.fchmod(stream.fileno(),0o600);stream.write(player['token'].strip()+'\n')
        identities.append({'slot':slot,'token_file':str(token),'strategy':b.VIP_S02_TESTROOM_STRATEGY,'expected_policy_release_id':package['release_package_id']})
    audit=_project_file(_PROJECT_ROOT, ROOT/'artifacts/sessions/t179-official-engineering-001/audit')
    assert not audit.exists()
    config={'mode':'test_room','base_url':'https://'+HOST+':18080','expected_tournament_id':room['room_id'],'known_guide_version':package['known_guide_version'],'audit_root':str(audit),'strategy':b.VIP_S02_TESTROOM_STRATEGY,'expected_policy_release_id':package['release_package_id'],'insecure_hosts':[HOST],'sse_enabled':True,'discard_pacing_enabled':False,'max_completed_batches':1,'identities':identities,'restart':{'max_restarts':0}}
    save(private/'room.json',config)
    save(directory/'PLAN.json',{'room_id':room['room_id'],'package_id':package['release_package_id'],'strategy':b.VIP_S02_TESTROOM_STRATEGY,'M':2,'Rounds':2,'audit_root':str(audit),'all_seats_same_configuration':True,'formula_unchanged':True,'full_M10_stress_not_claimed':True})
    with (directory/'STDOUT-STDERR.log').open('x') as logfile:
        player=subprocess.Popen([sys.executable,str(WORK/'scripts/run_test_room.py'),'--config',str(private/'room.json'),'--once'],cwd=WORK,stdout=logfile,stderr=subprocess.STDOUT,start_new_session=True)
        save(directory/'START.json',{'player_pid':player.pid,'at_unix':time.time(),'natural_end_only':True})
        print(json.dumps({'room_id':room['room_id'],'player_pid':player.pid,'M':2,'Rounds':2}),flush=True)
        result=player.wait()
    save(directory/'CHILD-TERMINAL.json',{'actual_exit_code':result,'controller_sent_termination_signal':False,'at_unix':time.time()})
    return result
if __name__=='__main__':raise SystemExit(main())
