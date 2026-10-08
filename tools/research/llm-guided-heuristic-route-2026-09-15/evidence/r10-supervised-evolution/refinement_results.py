"""核对真实M1与其直接父代、既有父代A及工程种子B的同根结果。"""

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
import strong_seed_batch as batch
import strong_seed_results as results
import refinement_batch as refinement


if __name__ == '__main__':
    parents = {
        name: {'dir': batch.BATCH / name,
               'source_sha256': batch.read(batch.BATCH / name / 'manifest.json')['source_sha256']}
        for name in ['parent-a', 'parent-b']
    }
    direct = batch.BATCH / 'hard-terra-max'
    state = batch.search.av_state_load(batch.search.av_latest_state_path(direct / 'run'))
    closure = batch.read(direct / 'batch-closure.json')
    parents['direct-hard-terra-parent'] = {
        'dir': batch.Path(state['iter_dir']),
        'source_sha256': closure['candidate_source_sha256'],
    }
    results.summarize(refinement.NAME,
                      candidate_dir=refinement.ROOT / refinement.NAME,
                      parent_specs=parents)
