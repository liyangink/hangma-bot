"""只生成隔离工程补丁与计划；本程序不修改main或工作区源码。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t54-public-count-native-cache-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = _PROJECT_ROOT
WORKTREE = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')
BASE = '732c5492762865a3d27cc2afed30de769d2a6be0'


def main():
    names = ('src/hangma_bot/hangma/public_tile_counts.py',
             'src/hangma_bot/policy/route_vip_heuristic.py')
    changes = {}
    for name in names:
        before = (_project_file(_PROJECT_ROOT, REPO / name)).read_text()
        assert (_project_file(_PROJECT_ROOT, WORKTREE / name)).read_text() == before
        changes[name] = [before, before]
    count_name, policy_name = names
    old = changes[count_name][0]
    imports = ('from contextlib import contextmanager\nfrom contextvars import ContextVar\n'
               'from types import UnionType\nfrom threading import RLock\n')
    after = old.replace('from collections import Counter, defaultdict\n',
                        'from collections import Counter, defaultdict\n' + imports, 1)
    after = after.replace('from typing import Optional, Tuple\n',
                          'from typing import Optional, Tuple, Union, get_args, get_origin, get_type_hints\n', 1)
    marker = 'def _count_public_tiles_from_view(view: PublicTileView, *, legacy_four_meld: bool) -> PublicTileCounts:'
    assert after.count(marker) == 1
    block = (_project_file(_PROJECT_ROOT, HERE / 'cache_block.py.txt')).read_text()
    after = after.replace(marker, block + marker.replace('_count_public', '_compute_public'), 1)
    # 历史解析仍只是解析缓存；新完整结果键不能省略本视图的其他字段。
    after = after.replace('# 所以只缓存历史解析，绝不缓存公开计数、未见容量或对当前副露的匹配结果。',
                          '# 这层只复用历史解析；上层完整结果缓存另绑定本视图全部字段，容量仍重算。', 1)
    changes[count_name][1] = after
    before = changes[policy_name][0]
    after = before.replace('from hangma_bot.hangma.interface import RuleCompleteness\n',
        'from hangma_bot.hangma.interface import RuleCompleteness\n'
        'from hangma_bot.hangma.public_tile_counts import public_count_result_scope\n', 1)
    wrapper = '''def build_vip_route_scoring_view(
    request: DecisionRequest, config: RuleConfig, *,
    limits: Optional[VipRouteProjectionLimits] = None,
) -> VipRouteScoringView:
    """在独占公开计数作用域内投影全合法根；输入、完整图和异常语义不变。"""

    with public_count_result_scope():
        return _build_vip_route_scoring_view(request, config, limits=limits)


'''
    marker = 'def build_vip_route_scoring_view(\n'
    assert after.count(marker) == 1
    after = after.replace(marker, wrapper + 'def _build_vip_route_scoring_view(\n', 1)
    changes[policy_name][1] = after
    patch = []
    frozen = {}
    for name, (before, after) in changes.items():
        ast.parse(after, filename=name)
        patch.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                         fromfile='a/' + name, tofile='b/' + name))
        frozen[name] = {'base_sha256': hashlib.sha256(before.encode()).hexdigest(),
                        'proposed_sha256': hashlib.sha256(after.encode()).hexdigest()}
    raw = ''.join(patch).encode()
    with (_project_file(_PROJECT_ROOT, HERE / 'SOURCE-PROPOSAL.patch')).open('xb') as stream:
        stream.write(raw)
    plan = {'schema': 't54-native-public-count-cache-plan/1', 'base_commit': BASE,
            'worktree': str(WORKTREE), 'main_source_modified': False,
            'source_patch_sha256': hashlib.sha256(raw).hexdigest(), 'files': frozen,
            'engineering_not_new_mathematical_formula': True,
            'new_model_world_table_calls': 0,
            'scope': 'isolated engineering implementation and public-behavior/equivalence verification; no T52 outcomes or source changes',
            'policy': 'scope only around synchronous whole graph; original unseen and all rule/projection facts unchanged',
            'planned_actual_public_score_pipelines': 22,
            'planned_actual_natural_score_pipelines': 192,
            'scope_tests': 'public count interfaces; strict typed deep shapes, full key, close/reset, nested/thread/task contexts',
            'admission_or_deadline_credit': False}
    with (_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')).open('x') as stream:
        json.dump(plan, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print({'prepared_patch': True, 'files': len(changes), 'main_source_modified': False})


if __name__ == '__main__':
    main()
