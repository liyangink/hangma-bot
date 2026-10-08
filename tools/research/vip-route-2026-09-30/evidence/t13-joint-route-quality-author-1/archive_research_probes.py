"""封存T13三份新研究额度探针的完整原件，包含源码快照，逐成员读回。"""

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
import json,gzip,tarfile,hashlib,io
from pathlib import Path
BASE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1')
NAMES=['S01-2400k-probe-1','S01-2400k-coverage-probe-1','S01-2400k-cross-source-probe-1']
OUT=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/research-probes-archive-1');OUT.mkdir(exist_ok=False)
files={}
for name in NAMES:
 directory=_project_file(_PROJECT_ROOT, BASE/name)
 s=json.loads((directory/'summary.json').read_text());assert s['status']=='probe_complete_not_admitted'
 for path in sorted(directory.rglob('*')):
  if not path.is_file():continue
  data=path.read_bytes();files[str(path.relative_to(BASE))]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
archive=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/research-probes-archive-1/original-files.tar.gz')
with archive.open('xb') as raw:
 with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=6) as gz:
  with tarfile.open(fileobj=gz,mode='w|') as tar:
   for name,expected in sorted(files.items()):
    data=(_project_file(_PROJECT_ROOT, BASE/name)).read_bytes();assert len(data)==expected['bytes'] and hashlib.sha256(data).hexdigest()==expected['sha256']
    info=tarfile.TarInfo(name);info.size=len(data);info.mtime=0;info.mode=0o644;tar.addfile(info,io.BytesIO(data))
seen=set()
with tarfile.open(archive,'r:gz') as tar:
 for member in tar:
  assert member.isfile() and member.name in files and member.name not in seen
  data=tar.extractfile(member).read();expected=files[member.name]
  assert len(data)==expected['bytes'] and hashlib.sha256(data).hexdigest()==expected['sha256'];seen.add(member.name)
assert seen==set(files)
receipt={'schema':'t13-research-probes-archive/1','status':'all_members_verified_readback','member_count':len(files),'raw_bytes':sum(v['bytes'] for v in files.values()),'archive_bytes':archive.stat().st_size,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'members':files,'raw_retained':True,'business_calls':0,'restoration_base':str(BASE),'restore_instruction':'Extract archive relative to restoration_base, keeping existing identical files; contains all probe source snapshots.'}
with (_project_file(_PROJECT_ROOT, OUT/'ARCHIVE.json')).open('x') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
print({k:v for k,v in receipt.items() if k!='members'})
