"""两种新方向完成后按冻结父代对账，不与旧核心身份混算。"""

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
import argparse
from types import SimpleNamespace

import strong_seed_batch as b
import strong_seed_results as results
import diverse_proposal_batch as experiment
from compare_refinement_terminals import compare


def close(name):
    """核验完整256桌及同牌山终局；是否扩第二清单由预登记分流决定。"""
    manifest = b.read(experiment.OUT / 'manifest.json')
    parent = b.Path(manifest['parent'])
    assert b.digest((parent / 'candidate.py').read_bytes()) == manifest['parent_sha256']
    sub = experiment.OUT / name
    results.summarize(name, candidate_dir=sub, parent_specs={
        'frozen-route-parent': {'dir': parent.parent, 'source_sha256': manifest['parent_sha256']}})
    terminal = compare(SimpleNamespace(ROOT=experiment.OUT, NAME=name, PARENT=parent))
    b.write(sub / 'parent-terminal-comparison.json', terminal)
    closure = b.read(sub / 'batch-closure.json')
    paired = closure['versus_parents']['frozen-route-parent']
    keep = paired['equal_mix_low'] > 0 and all(s['mean_delta'] > 0 for s in closure['versus_v2'].values())
    decision = {'continue_second_seen_panel': keep,
        'reason': '固定开发分流条件满足' if keep else 'H/M对V2双正或对冻结父代差下界正条件未满足',
        'interval_kind': '平分识别区间，不是置信区间', 'release_eligible': False}
    b.write(sub / 'development-decision.json', decision)
    print(decision, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', choices=experiment.CONFIGS)
    close(parser.parse_args().name)
