"""复用v1已核纯文件材料，只补执行依赖和清理守卫；不重选来源或开世界。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t74-hu-versus-wait-common-parent-1/revision-2'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
import hashlib,json,sys
HERE=Path(__file__).resolve().parent
REPO=_PROJECT_ROOT

def canonical(value):
    """规范化审计JSON，不改变玩家观察、动作或结果。"""
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def pin(path):
    """流式内容身份，字节为单位。"""
    h=hashlib.sha256();size=0
    with Path(path).open('rb') as stream:
        for piece in iter(lambda:stream.read(1<<20),b''):h.update(piece);size+=len(piece)
    return {'sha256':h.hexdigest(),'bytes':size}

def save(path,value):
    """新建收据；错误、START及结果不自动覆盖。"""
    with Path(path).open('xb') as stream:stream.write(canonical(value)+b'\n')

def main():
    original=HERE.parent
    old=json.loads((original/'PREPARED.json').read_text())
    assert old['status']=='prepared_no_START' and not (original/'START.json').exists()
    assert old['python_version']==sys.version
    for name,digest in old['files'].items():assert pin(name)==digest,name
    for name in ['SOURCE-SELECTION.json','SOURCE-MATERIALS.json.gz']:
        with (_project_file(_PROJECT_ROOT, HERE/name)).open('xb') as target:target.write((original/name).read_bytes())
    files=dict(old['files'])
    for path in [Path(__file__),_project_file(_PROJECT_ROOT, HERE/'run.py'),_project_file(_PROJECT_ROOT, HERE/'SOURCE-SELECTION.json'),_project_file(_PROJECT_ROOT, HERE/'SOURCE-MATERIALS.json.gz'),
                 original/'PREPARED.json',original/'PRESTART-REVIEW-DECISION.json',_project_file(_PROJECT_ROOT, REPO/'src/hangma_bot/offline/forced_action.py')]:
        files[str(path.resolve())]=pin(path)
    assert all(pin(name)==digest for name,digest in files.items())
    new=dict(old,schema='t74-hu-wait-common-parent-prepared/2',files=files,
             prior_preparation_sha256=pin(original/'PREPARED.json')['sha256'],
             fixes=['explicit new first-action dependency pin','independent stream/capture cleanup; preserve primary error and partial counts'],
             source_selection_unchanged=True)
    save(_project_file(_PROJECT_ROOT, HERE/'PREPARED.json'),new)
    print({'prepared_revision':2,'windows':18,'mothers':16,'max_continuations':36,'new_business_calls':0})
if __name__=='__main__':main()
