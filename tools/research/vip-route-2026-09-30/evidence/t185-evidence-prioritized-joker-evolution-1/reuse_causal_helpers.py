"""只复用T182已闭合的公开模拟接口助手，不改变其文件或全局配置。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t185-evidence-prioritized-joker-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import importlib.util
import sys
from common import OLD

# 原助手的相邻模块只定义纯证据函数；导入不启动实验或访问凭据。
sys.path.append(str(OLD))
spec = importlib.util.spec_from_file_location("t185_existing_causal_helpers", OLD / "run_causal.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
EndpointEngine = module.EndpointEngine
recover = module.recover
unchanged = module.unchanged
