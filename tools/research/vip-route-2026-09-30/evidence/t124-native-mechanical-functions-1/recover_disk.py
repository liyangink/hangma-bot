"""只删除四份已封存且Git字节完全相同的临时重复tar，不删原始证据。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t124-native-mechanical-functions-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
REPO=_PROJECT_ROOT
BASE=_project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
PAIRS=[
    ('/private/tmp/hangma-t6-closed-opportunity-evaluation-20261001/S01/source-evidence.tar.gz',
     't6-absolute-route-credit-1/closed-opportunity-evaluation-archive/S01/chunk-index.json'),
    ('/private/tmp/hangma-t6-closed-opportunity-evaluation-20261001/S02/source-evidence.tar.gz',
     't6-absolute-route-credit-1/closed-opportunity-evaluation-archive/S02/chunk-index.json'),
    ('/private/tmp/vip-t8-natural64-20261001-S01F/source-evidence.tar.gz',
     't8-bounded-natural-geometry-1/closed-natural64-evidence-archive/S01F/chunk-index.json'),
    ('/private/tmp/vip-t8-natural64-20261001-S02/source-evidence.tar.gz',
     't8-bounded-natural-geometry-1/closed-natural64-evidence-archive/S02/chunk-index.json')]


def hash_file(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1<<20),b''):digest.update(data)
    return digest.hexdigest()


def git_hash(path):
    """流式验证HEAD实际blob；不把tracked标志当作内容已经封存。"""
    name=path.relative_to(REPO).as_posix()
    process=subprocess.Popen(['git','cat-file','blob','HEAD:'+name],
        cwd=REPO,stdout=subprocess.PIPE)
    digest=hashlib.sha256();size=0
    for data in iter(lambda:process.stdout.read(1<<20),b''):
        digest.update(data);size+=len(data)
    assert process.wait()==0,name
    return size,digest.hexdigest()


def main():
    """所有四包验证完成后才逐件删除；任一差异则保留全部原包。"""
    assert not (_project_file(_PROJECT_ROOT, HERE/'DISK-RECOVERY.json')).exists()
    rows=[]
    for filename,index_name in PAIRS:
        temporary=Path(filename);index_path=_project_file(_PROJECT_ROOT, BASE/index_name)
        assert temporary.is_file() and not temporary.is_symlink()
        before=temporary.stat()
        index=json.loads(index_path.read_text())
        assert git_hash(index_path)==(index_path.stat().st_size,hash_file(index_path))
        manifest=index_path.parent/index['manifest_name']
        assert git_hash(manifest)==(index['manifest_bytes'],index['manifest_sha256'])
        joined=hashlib.sha256();size=0;chunks=[]
        for entry in index['chunks']:
            chunk=index_path.parent/entry['name']
            assert chunk.parent==index_path.parent and not chunk.is_symlink()
            assert entry['offset']==size
            assert chunk.stat().st_size==entry['bytes'] and hash_file(chunk)==entry['sha256']
            assert git_hash(chunk)==(entry['bytes'],entry['sha256'])
            with chunk.open('rb') as stream:
                for data in iter(lambda:stream.read(1<<20),b''):joined.update(data)
            size+=entry['bytes'];chunks.append(chunk.relative_to(REPO).as_posix())
        assert (size,joined.hexdigest())==(index['archive_bytes'],index['archive_sha256'])
        assert before.st_size==size and hash_file(temporary)==joined.hexdigest()
        after=temporary.stat()
        assert (before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns)
        rows.append({'temporary_path':str(temporary),'bytes':size,
            'sha256':joined.hexdigest(),'recovery_index':index_path.relative_to(REPO).as_posix(),
            'git_chunks':chunks,'git_blob_bytes_verified':True,
            'inode':after.st_ino,'mtime_ns':after.st_mtime_ns})
    with (_project_file(_PROJECT_ROOT, HERE/'DISK-RECOVERY-VERIFIED-BEFORE.json')).open('x') as stream:
        json.dump({'schema':'verified-temp-archive-duplicates/1','items':rows,
            'all_four_verified_before_deletion':True},stream,ensure_ascii=False,indent=2);stream.write('\n')
    for row in rows:
        path=Path(row['temporary_path']);now=path.stat()
        assert (now.st_ino,now.st_size,now.st_mtime_ns)==(row['inode'],row['bytes'],row['mtime_ns'])
        path.unlink()
        row['deleted_verified_temporary_duplicate']=True
    with (_project_file(_PROJECT_ROOT, HERE/'DISK-RECOVERY.json')).open('x') as stream:
        json.dump({'schema':'verified-temp-archive-recovery/1','items':rows,
            'freed_bytes':sum(row['bytes'] for row in rows),
            'original_repository_evidence_deleted':False,
            'actual_rule_choose_score_world_table_calls':0},stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({'deleted_duplicates':len(rows),'freed_bytes':sum(row['bytes'] for row in rows)},ensure_ascii=False))


if __name__=='__main__':main()
