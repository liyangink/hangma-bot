"""后续确认执行的依赖冻结检查；不补签历史身份，也不签发确认资格。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
from pathlib import Path
import sys
import strong_seed_batch as batch
import confirmation_pairing as pairing
from hangma_bot.simulation import shuffle


def capture(*, source_paths):
    """重算生产依赖闭包与调用方明确列出的实验脚本/候选字节。

    source_paths必须包含实际运行入口及其证据目录辅助脚本；生产工具闭包由
    av_frozen_manifest负责。未登记的外部脚本不在保证范围，不允许据此宣称发布。
    返回值必须在执行前保存，恢复及每臂调用前重新核对。
    """
    paths={Path(p).resolve() for p in source_paths}
    paths.update((Path(__file__).resolve(),Path(pairing.__file__).resolve()))
    manifest=batch.search.av_frozen_manifest()
    return {'schema':'confirmation-execution-identity/1','python_version':sys.version,
        'production_manifest':manifest,
        'production_digest':batch.search.av_frozen_manifest_digest(manifest),
        'explicit_sources':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},
        'release_eligible':False}


def verify(stored):
    """对比当前依赖和冻结原件；拒绝存档损坏或任意已登记源码变化。"""
    if stored.get('schema')!='confirmation-execution-identity/1':
        raise ValueError('未知执行身份版本')
    fresh=capture(source_paths=stored['explicit_sources'])
    if fresh!=stored:
        raise ValueError('执行依赖或冻结身份漂移；禁止继续旧运行')
    return stored['production_digest']


def verify_root_runtime(root):
    """校验计划摘要及当前发牌/赛程实现，防止旧摘要自洽但运行时已变。"""
    body=dict(root);digest=body.pop('root_content_digest')
    if pairing.draft.digest(body)!=digest:
        raise ValueError('根计划内容摘要不符')
    expected={'deal_algorithm':shuffle.DEAL_ALGORITHM,'python_version':sys.version,
        'source_sha256':{name:hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            for name,module in [('shuffle',shuffle),('stage',pairing.natural.stage),('plan_builder',pairing)]}}
    if root['runtime_identity']!=expected:
        raise ValueError('根计划绑定的发牌/赛程运行身份已变化')
