"""后备实验：当前杠补完整枚举，后继杠的更远补牌明确保持未知。

只在T129原样优化仍未过原时限后启用。不是数学等价优化，不沿用S02
强度信用；必须另身份评测。不会限制真实连续杠：下一权威动作窗口
重新从深度零分析。根合法动作不删，预估结果绝不作为盲执行计划。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t129-s02-grouped-optimization-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from contextlib import contextmanager
import hashlib
from pathlib import Path


def make_projection(base, max_replacement_depth, stats):
    """只限制条件图里的补牌层数，深度为单次投影的嵌套层数。"""
    if type(max_replacement_depth) is not int or max_replacement_depth < 1:
        raise ValueError('至少完整评估当前动作的一次杠补')

    class BoundedChainProjection(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._chain_depth = 0

        def replacement_key(self, state):
            original = super().replacement_key(state)
            return None if original is None else (self._chain_depth, original)

        def choices_key(self, analysis, followup_keys):
            original = super().choices_key(analysis, followup_keys)
            return None if original is None else (self._chain_depth, original)

        def replacement(self, state, key):
            from hangma_bot.policy.route_vip_heuristic import RouteHeuristicResearchError
            from hangma_bot.hangma.route_transition import ConditionalPhase
            if (state.phase is not ConditionalPhase.REPLACEMENT_DRAW or state.structural_only
                    or state.wall_remaining is None or state.wall_remaining <= 20):
                # 保留原错误类别/次序。不得把非法状态冒充预算未知。
                return super().replacement(state, key)
            if self._chain_depth >= max_replacement_depth:
                if not self.compatible_codes(state):
                    raise RouteHeuristicResearchError('MECHANICAL_GAP', '合法杠没有公开相容补牌码')
                stats['bounded_successors'] += 1
                return self.add(key, 'unknown_draw', waiting=self.waiting(state, qualification=False),
                    pending='replacement_draw_not_expanded_after_depth:' + str(max_replacement_depth),
                    uncertainty='计算预算限制：后继杠已合法，但更远补牌及成胡资格未展开；下一权威窗重新判断')
            self._chain_depth += 1
            stats['max_observed_expanded_depth'] = max(stats['max_observed_expanded_depth'], self._chain_depth)
            try:
                return super().replacement(state, key)
            finally:
                self._chain_depth -= 1

    return BoundedChainProjection


@contextmanager
def installed(max_replacement_depth=1):
    """研究组合根显式启用，退出恢复；默认生产/原样差分都不调用。"""
    from hangma_bot.policy import route_vip_heuristic as vip
    original = vip._Projection
    stats = {'bounded_successors': 0, 'max_observed_expanded_depth': 0, 'restored': False}
    vip._Projection = make_projection(original, max_replacement_depth, stats)
    identity = {'schema': 'vip-bounded-followup-gang-research/1',
        'max_replacement_depth': max_replacement_depth,
        'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'current_root_legal_set_preserved': True, 'future_qualification_explicitly_unknown': True,
        'mathematical_equivalence_claim': False, 'strength_admission': False}
    try:
        yield identity, stats
    finally:
        vip._Projection = original
        stats['restored'] = vip._Projection is original
