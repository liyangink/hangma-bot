"""只封T22作者前已冻结的源码快照；保留原字节，不含运行中的作者输出。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t22-claim-route-opportunity-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
import gzip
import hashlib
import json
import tarfile

HERE=Path(__file__).resolve().parent
ROOT=_PROJECT_ROOT
E=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')


def pin(path):
    raw=path.read_bytes()
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def main():
    groups=('S01-prompt-emission/code_snapshot',)
    E=HERE
    assert json.loads((_project_file(_PROJECT_ROOT, HERE/'ROOT-AUTHOR-START.json')).read_bytes())['status']=='START'
    files=sorted(p for name in groups for p in (_project_file(_PROJECT_ROOT, E/name)).rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts)
    members=[{'path':str(p.relative_to(ROOT)),**pin(p)} for p in files]
    destination=_project_file(_PROJECT_ROOT, HERE/'frozen-code-snapshot-full.tar.gz')
    with destination.open('xb') as stream:
        with gzip.GzipFile(filename='',mode='wb',fileobj=stream,mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode='w|') as archive:
                for p, expected in zip(files,members):
                    assert pin(p)=={k:expected[k] for k in ('bytes','sha256')}
                    archive.add(p,arcname=expected['path'],recursive=False)
    with tarfile.open(destination,'r:gz') as archive:
        recovered=archive.getmembers()
        assert [m.name for m in recovered]==[m['path'] for m in members]
        for info,expected in zip(recovered,members):
            raw=archive.extractfile(info).read()
            assert len(raw)==expected['bytes'] and hashlib.sha256(raw).hexdigest()==expected['sha256']
    receipt={'schema':'t22-frozen-code-snapshot-archive/1','status':'closed_all_members_readback',
             'archive':pin(destination),'members':members,'file_count':len(members),
             'original_bytes':sum(m['bytes'] for m in members),'new_business_calls':0,
             'running_author_outputs_included':False,'tool':pin(Path(__file__))}
    with (_project_file(_PROJECT_ROOT, HERE/'FROZEN-CODE-SNAPSHOT-ARCHIVE.json')).open('x') as stream:
        json.dump(receipt,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({k:receipt[k] for k in ('status','file_count','original_bytes','archive')}))


if __name__=='__main__':main()
