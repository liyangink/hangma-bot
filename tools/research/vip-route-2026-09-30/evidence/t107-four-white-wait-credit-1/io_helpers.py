"""只供本次研究记录和身份核对的文件助手，不调用模型、规则或模拟。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t107-four-white-wait-credit-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
def canonical(value):
    """规范JSON保留空值、牌码、积分及时间语义。"""
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def pin(path):
    """绑定原始字节数与SHA256，不解压或修改原件。"""
    h=hashlib.sha256();size=0
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):
            h.update(b);size+=len(b)
    return {"bytes":size,"sha256":h.hexdigest()}
def save(path,value):
    """只创建新文件，拒绝覆盖旧失败或START。"""
    with Path(path).open("xb") as f:f.write(canonical(value)+b"\n")
