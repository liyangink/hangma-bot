"""当前S02的已完成条件节点复用原型；本进程退出恢复，冻结源码不变。

复用旧T88原型的精确实现，只缓存同一投影已完整构造的节点引用；
不返回旧条件状态、不减少合法根或替换规则结果。当前数学必须另验。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t116-s02-completed-choice-cache-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from contextlib import contextmanager
from dataclasses import fields
import hashlib
import inspect
import json
from pathlib import Path
import time
from hangma_bot.hangma import public_tile_counts as public
from hangma_bot.hangma.route_transition import ConditionalIdentity, ConditionalPhase, ConditionalRouteState, GivenDrawAnalysis
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import PublicMeld


class OwnedIdentity:
    """强持有规范冻结原件；仅相同原件命中，不把编号复用当成相同值。"""

    def __init__(self, value):
        self.value = value

    def __hash__(self):
        return id(self.value)

    def __eq__(self, other):
        return type(other) is OwnedIdentity and self.value is other.value


def make_projection(base):
    class CanonicalProjection(base):
        """只诊断规范补牌分析；畸形输入及未证明范围仍执行原路径。"""
        instances = []

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.completed_choices = {}
            self.input_guard = public._PublicInputGuard()
            self.calls = self.hits = self.misses = self.bypasses = 0
            self.canonicalized_suffixes = 0
            self.key_seconds = 0.0
            self.instances.append(self)

        def public_key(self, state):
            view, root = state.public_view, state.root_public_view
            if (type(view) is not public.PublicTileView or type(root) is not public.PublicTileView
                    or not self.input_guard.valid(root, public.PublicTileView)
                    or not self.input_guard.valid(view, public.PublicTileView)):
                return None
            group = view.melds[state.seat]
            boundary = len(root.melds[state.seat])
            start = len(group)
            while start > boundary:
                meld = group[start - 1]
                if (type(meld) is not PublicMeld or meld.kind != 'gang_an'
                        or meld.seat != state.seat or meld.from_seat is not None
                        or len(meld.tiles) != 4 or any(type(tile) is not Tile for tile in meld.tiles)
                        or len({tile.code for tile in meld.tiles}) != 1 or meld.tiles[0].code == '白'):
                    break
                start -= 1
            canonical_melds = view.melds
            if len(group) - start > 1 and not any(
                    claim.seat == state.seat and claim.meld_index >= start for claim in view.claim_evidence):
                normalized = group[:start] + tuple(sorted(group[start:], key=lambda meld: meld.tiles[0].code))
                rows = list(view.melds)
                rows[state.seat] = normalized
                canonical_melds = tuple(rows)
                self.canonicalized_suffixes += 1
            result = []
            for field in fields(view):
                value = getattr(view, field.name)
                if field.name == 'melds':
                    value = canonical_melds
                elif field.name == 'public_history':
                    value = OwnedIdentity(value)
                result.append((field.name, value))
            return tuple(result)

        def choices_key(self, analysis, followup_keys):
            state = analysis.source_state
            identity = state.identity
            if (type(analysis) is not GivenDrawAnalysis or type(state) is not ConditionalRouteState
                    or state.phase is not ConditionalPhase.DRAW_ACTION
                    or state.last_draw_replacement is not True or state.catch_restricted is not False
                    or type(identity) is not ConditionalIdentity or type(identity.path) is not tuple
                    or any(type(label) is not str for label in identity.path)
                    or type(identity.ruleset_version) is not str
                    or type(state.concealed) is not tuple or not state.concealed
                    or any(type(tile) is not Tile or type(tile.code) is not str for tile in state.concealed)
                    or type(state.drawn_tile) is not Tile or state.concealed[-1] != state.drawn_tile
                    or type(state.seat) is not int or state.seat not in range(4)
                    or analysis.issues or not analysis.legal_candidates):
                return None
            view_key = self.public_key(state)
            if view_key is None:
                return None
            values = []
            for field in fields(state):
                if field.name == 'identity':
                    value = (False, identity.ruleset_version)
                elif field.name == 'concealed':
                    value = tuple(sorted(tile.code for tile in state.concealed))
                elif field.name == 'drawn_tile':
                    # 原analyse_given_self_draw已验证末项并产生全合法动作/当前结算。
                    # apply_legal_draw_discard与followup_gang不读摸牌码，且会消费它。
                    value = 'already-analyzed-normative-replacement-draw'
                elif field.name == 'root_public_view':
                    value = OwnedIdentity(state.root_public_view)
                elif field.name == 'public_view':
                    value = view_key
                else:
                    value = getattr(state, field.name)
                values.append((field.name, value))
            extra = (tuple((item.action_key, item.action) for item in analysis.legal_candidates),
                     analysis.immediate_settlement, analysis.issues, analysis.local_witness_only,
                     tuple(sorted((followup_keys or {}).items())))
            signature = (tuple(values), extra)
            try:
                hash(signature)
            except TypeError:
                return None
            return signature

        def action_choices(self, analysis, key, *, followup_keys=None):
            self.calls += 1
            begin = time.monotonic()
            signature = self.choices_key(analysis, followup_keys)
            self.key_seconds += time.monotonic() - begin
            if signature is None:
                self.bypasses += 1
                return super().action_choices(analysis, key, followup_keys=followup_keys)
            previous = self.completed_choices.get(signature)
            if previous is not None:
                self.hits += 1
                return previous
            self.misses += 1
            result = super().action_choices(analysis, key, followup_keys=followup_keys)
            if len(self.completed_choices) < self.limits.max_nodes:
                self.completed_choices[signature] = result
            return result

    return CanonicalProjection

@contextmanager
def installed():
    """串行研究装配，原件恢复后只保存缓存诊断，不访问官方或模型。"""
    from hangma_bot.policy import route_vip_heuristic as vip
    original = vip._Projection
    projection = make_projection(original)
    overlay = {'schema': 't116-s02-completed-choice-cache/1',
        'original_projection_sha256': hashlib.sha256(inspect.getsource(original).encode()).hexdigest(),
        'normal_formula_changed': False, 'production_changes': 0, 'online_admission': False}
    vip._Projection = projection
    try:
        yield overlay
    finally:
        vip._Projection = original
        rows = [{'calls': x.calls, 'hits': x.hits, 'misses': x.misses,
                 'bypasses': x.bypasses, 'entries': len(x.completed_choices),
                 'canonicalized_suffixes': x.canonicalized_suffixes,
                 'key_seconds': x.key_seconds, 'expanded_nodes': len(x.nodes),
                 'branches': x.branch_count, 'witnesses': x.witness_count,
                 'target_distances': x.target_distance_count}
                for x in projection.instances]
        path = _project_file(_PROJECT_ROOT, Path(__file__).resolve().parent / 'actual-full-1/CACHE-STATS.json')
        if path.parent.exists():
            with path.open('x') as stream:
                json.dump({'rows': rows, 'original_binding_restored': vip._Projection is original},
                          stream, sort_keys=True, indent=2)
                stream.write('\n')
