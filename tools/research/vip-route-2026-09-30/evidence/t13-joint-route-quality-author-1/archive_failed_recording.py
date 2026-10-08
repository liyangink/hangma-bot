"""封包已关闭的T13五根原件，逐成员读回；不删除原件，不重跑业务。"""

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
import gzip,hashlib,json,tarfile
from pathlib import Path
BASE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1')
SOURCE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/S01-natural-recording-16')
SEAL=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/natural-recording-closure-1/RAW-FIRST-SEAL.json')
OUT=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/natural-recording-archive-1')
seal=json.loads(SEAL.read_text())
assert seal['status']=='closed_partial_and_failed_originals_preserved'
OUT.mkdir(exist_ok=False)
archive=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t13-joint-route-quality-author-1/natural-recording-archive-1/original-files.tar.gz')
with archive.open('xb') as raw:
 with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=6) as gz:
  with tarfile.open(fileobj=gz,mode='w|') as tar:
   for filename,expected in sorted(seal['files'].items()):
    path=Path(filename);data=path.read_bytes()
    assert len(data)==expected['bytes'] and hashlib.sha256(data).hexdigest()==expected['sha256']
    relative=path.relative_to(SOURCE)
    info=tarfile.TarInfo(str(relative));info.size=len(data);info.mtime=0;info.mode=0o644
    import io
    tar.addfile(info,io.BytesIO(data))
verified=[]
with tarfile.open(archive,'r:gz') as tar:
 for member in tar:
  assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
  expected=seal['files'][str(_project_file(_PROJECT_ROOT, SOURCE/member.name))]
  data=tar.extractfile(member).read()
  assert len(data)==expected['bytes'] and hashlib.sha256(data).hexdigest()==expected['sha256']
  verified.append(member.name)
assert len(verified)==len(seal['files'])==seal['file_count']
receipt={'schema':'t13-failed-natural-recording-archive/1','status':'all_original_members_verified_readback',
 'source_dir':str(SOURCE.resolve()),'raw_seal_sha256':hashlib.sha256(SEAL.read_bytes()).hexdigest(),
 'member_count':len(verified),'raw_original_bytes':seal['bytes'],'archive_bytes':archive.stat().st_size,
 'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'members':verified,
 'raw_files_retained':True,'new_business_calls':0}
with (_project_file(_PROJECT_ROOT, OUT/'ARCHIVE.json')).open('x') as f:json.dump(receipt,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='members'},ensure_ascii=False))
