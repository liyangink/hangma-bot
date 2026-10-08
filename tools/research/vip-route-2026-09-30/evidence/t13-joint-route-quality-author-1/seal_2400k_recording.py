"""T13新研究桌批自然结束后先封完整原件；不重评分或续打。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import json,hashlib
from pathlib import Path
BASE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1')
RAW=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/S01-natural-recording-2400k-16')
OUT=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/natural-2400k-closure-1/RAW-FIRST-SEAL.json')
s=json.loads((_project_file(_PROJECT_ROOT, RAW/'summary.json')).read_text())
assert s['status']=='development_complete_not_confirmed' and s['identity_stable'] is True
files={}
for path in sorted(RAW.rglob('*')):
 if not path.is_file():continue
 h=hashlib.sha256();size=0
 with path.open('rb') as f:
  while block:=f.read(1024*1024):h.update(block);size+=len(block)
 files[str(path.resolve())]={'bytes':size,'sha256':h.hexdigest()}
seal={'schema':'t13-natural-2400k-complete-raw-seal/1','status':'closed_complete_originals_preserved','actual_cli_exit_code':0,'file_count':len(files),'total_bytes':sum(x['bytes'] for x in files.values()),'bytes':sum(x['bytes'] for x in files.values()),'files':files,'before_root_full_stream_check':True}
with OUT.open('x') as f:json.dump(seal,f,ensure_ascii=False,indent=2);f.write('\n')
print({k:v for k,v in seal.items() if k!='files'})
