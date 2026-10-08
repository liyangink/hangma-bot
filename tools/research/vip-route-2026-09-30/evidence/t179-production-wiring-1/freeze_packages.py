"""冻结新测试房/自由赛包；必须在全部运行源码与验收收据闭合后执行。"""

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
import hashlib,json,shutil,sys
from pathlib import Path
import hangma_bot.bootstrap as b
ROOT=_PROJECT_ROOT
HERE=Path(__file__).resolve().parent
WORK=Path(b.__file__).resolve().parents[2]
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
    names=['review/vip-route-2026-09-30/evidence/t178-integrated-production-validation-1/PERFORMANCE-ACCEPTANCE.json','review/vip-route-2026-09-30/evidence/t179-production-wiring-1/'+('REGRESSION-PREPARATION.json' if len(sys.argv)>1 and sys.argv[1]=='provisional' else 'REGRESSION-CLOSED.json')]
    evidence={}
    for name in names:
        source=_project_file(_PROJECT_ROOT, ROOT/name);target=WORK/name
        target.parent.mkdir(parents=True,exist_ok=True)
        if source.resolve()!=target.resolve():shutil.copy2(source,target)
        evidence[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    packages={'testroom':b.build_vip_testroom_manifest(evidence),'free':b.build_vip_free_manifest(evidence)}
    for arm,package in packages.items():
        filename=b.VIP_S02_TESTROOM_MANIFEST if arm=='testroom' else b.VIP_S02_FREE_MANIFEST
        save(WORK/filename,package)
    free=json.loads((_project_file(_PROJECT_ROOT, ROOT/'configs/vip-s02-bounded-d1-v5.free-match.example.json')).read_text())
    free.update(strategy=b.VIP_S02_FREE_STRATEGY,expected_policy_release_id=packages['free']['release_package_id'],audit_root='artifacts/sessions/vip_s02_bounded_d1_free_v6/audit')
    save(WORK/'configs/vip-s02-bounded-d1-v6.free-match.example.json',free)
    test=json.loads((_project_file(_PROJECT_ROOT, ROOT/'configs/vip-s02-bounded-d1-v7.test-room.example.json')).read_text())
    test.update(strategy=b.VIP_S02_TESTROOM_STRATEGY,expected_policy_release_id=packages['testroom']['release_package_id'])
    for seat in test.get('identities',[]):
        seat['strategy']=b.VIP_S02_TESTROOM_STRATEGY;seat['expected_policy_release_id']=packages['testroom']['release_package_id']
    save(WORK/'configs/vip-s02-bounded-d1-v8.test-room.example.json',test)
    b._load_vip_free_manifest();b._load_vip_testroom_manifest()
    result={'package_ids':{arm:value['release_package_id'] for arm,value in packages.items()},'source_count':len(packages['free']['source_manifest']),'formula_sha256':b.VIP_S02_SOURCE_SHA256,'native_runtime':packages['free']['compiled_runtime'],'HTTP_calls':0,'formal_release':False}
    save(_project_file(_PROJECT_ROOT, HERE/('PROVISIONAL-PACKAGES.json' if len(sys.argv)>1 and sys.argv[1]=='provisional' else 'FROZEN-PACKAGES.json')),result)
    print(json.dumps({'package_ids':result['package_ids'],'source_count':result['source_count']}))
if __name__=='__main__':main()
