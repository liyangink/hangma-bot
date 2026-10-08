"""冻结有限等待模型的资格修正：存在当前合法胡时整体保留原等胡计划。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/big-hand-paths-2026-09-09'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from finite_wait import FiniteWaitingPolicy


class GuardedFiniteWaitingPolicy(FiniteWaitingPolicy):
    """即使原等胡已经选成弃牌，也不让普通等待排序再覆盖该选择。

首版烟测只检查已选动作是否 Hu，不能表达“有合法 Hu 但增强选择弃牌”。
本文件单独保留修正，旧烟测代码与哈希不覆盖；仍为研究专用逻辑时钟。
"""
    async def choose(self,request,budget):
        if any(c.action_key=='hu' for c in request.rules.legal_candidates):
            return await self.base.choose(request,budget)
        return await super().choose(request,budget)
