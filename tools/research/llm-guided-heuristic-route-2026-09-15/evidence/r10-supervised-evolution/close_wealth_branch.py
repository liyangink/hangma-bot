"""关闭生产财神分支变异：核对同根三父代、共同V2臂及逐桌终局。"""

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
import strong_seed_batch as b
import strong_seed_results as results
import branch_wealth_batch as experiment
from compare_refinement_terminals import compare


if __name__ == '__main__':
    sub = experiment.ROOT / experiment.NAME
    parents = {name: {'dir': b.BATCH / name,
                     'source_sha256': b.read(b.BATCH / name / 'manifest.json')['source_sha256']}
               for name in ('parent-a', 'parent-b')}
    parents['direct-hard-terra-parent'] = {
        'dir': experiment.PARENT.parent,
        'source_sha256': b.digest((experiment.PARENT / 'candidate.py').read_bytes())}
    results.summarize(experiment.NAME, candidate_dir=sub, parent_specs=parents)
    result = compare(experiment)
    b.write(sub / 'parent-terminal-comparison.json', result)
    print({'equal_terminal_tables': result['equal_terminal_tables'],
           'candidate_runtime_counts': result['candidate_runtime_counts']})
