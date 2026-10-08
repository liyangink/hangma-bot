"""可信项目输入的排列等价原型；只复用本投影已完成节点，不返回旧状态。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t88-native-execution-prototype-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import asyncio
from dataclasses import fields
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from hangma_bot.application.deadline import BudgetPolicy, SystemClock
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma import public_tile_counts as public
from hangma_bot.hangma.route_transition import ConditionalIdentity, ConditionalPhase, ConditionalRouteState, GivenDrawAnalysis
from hangma_bot.kernel.actions import Tile
from hangma_bot.kernel.observation import CompetitionContext, PublicMeld
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy import route_vip_heuristic as vip

HERE = Path(__file__).resolve().parent


def raw(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def save(path, value):
    with path.open('xb') as stream:
        stream.write(raw(value) + b'\n')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


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


async def main():
    out = _project_file(_PROJECT_ROOT, HERE / 'canonical-choices')
    out.mkdir(exist_ok=False)
    evidence = HERE.parent
    author = evidence / 't75-net-upgrade-joint-author-1'
    t80 = evidence / 't80-witness-capacity-failure-diagnostic-1'
    t84 = evidence / 't84-public-shape-dispatch-1'
    batch = VipEohBatch.read(author / 'S01-generation.batch.json')
    source = (author / 'S01-model-output/candidate.py').read_text()
    identity = batch.identity(source)
    reference = json.loads((t84 / 'failed-response/CLOSURE.json').read_text())
    assert identity == reference['python_parent_runtime_identity']
    fixture = json.loads((t80 / 'FAILED-PUBLIC-WINDOW.json').read_text())['actual_failed_row']
    overlay = module('t88_canonical_overlay', _project_file(_PROJECT_ROOT, HERE / 'native_overlay.py'))
    capture_type = module('t88_canonical_capture', t80 / 'probe.py').Capture
    original_projection = vip._Projection
    with overlay.installed() as execution:
        base = vip._Projection
        prototype = make_projection(base)
        save(out / 'PLAN.json', dict(schema='t88-canonical-choices-prototype/1',
              actual_rules_choose_budget=1, execution_identity=execution,
              script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              candidate_authors_worlds_tables=0, production_changes=0,
              scope='仅可信规范给定杠补分析，同投影已完成节点；未授生产缓存资格', admission=False))
        obs = observation_from_json(fixture['observation'])
        window = window_key_from_json(fixture['window_key'])
        rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
        request = DecisionRequest(obs, CompetitionContext('t88-canonical', None, None, None, None, (), 0),
                                  rules, 't88-canonical', window.trigger_seq, window, ())
        policy = vip.RouteVipHeuristicPolicy(batch.rule_config, source=source,
                     max_operations=batch.max_operations, projection_limits=batch.projection_limits)
        vip._Projection = prototype
        try:
            clock = SystemClock()
            begin = clock.now()
            budget = BudgetPolicy().build(begin, 1)
            with gzip.open(out / 'ACTUAL-INPUTS.jsonl.gz', 'xb') as stream:
                capture = capture_type(policy.executor, stream)
                policy.executor = capture
                plan = await policy.choose(request, budget)
            elapsed = clock.now() - begin
        finally:
            vip._Projection = base
        scores = [dict(key=c.action_key, score=c.total_score, trace=c.score_trace) for c in plan.candidates]
        assert raw(scores) == raw(reference['scores'])
        assert capture.input_sha == reference['input_sha256']
        assert capture.last_operation_count == reference['operations']
        instance, = prototype.instances
        result = dict(schema='t88-canonical-choices-result/1', status='SCORED', scores=scores,
              input_sha256=capture.input_sha, operations=capture.last_operation_count,
              actual_rules_attempts=1, actual_choose_attempts=1, actual_full_inputs=capture.calls,
              key_seconds=instance.key_seconds, calls=instance.calls, hits=instance.hits,
              misses=instance.misses, bypasses=instance.bypasses,
              canonicalized_suffixes=instance.canonicalized_suffixes,
              cache_entries=len(instance.completed_choices), input_guard_entries=len(instance.input_guard.values),
              expanded_nodes=len(instance.nodes), branches=instance.branch_count,
              witnesses=instance.witness_count, target_distances=instance.target_distance_count,
              elapsed_seconds=elapsed, capture_seconds=capture.seconds,
              compute_minus_capture_seconds=elapsed - capture.seconds,
              before_original_fallback=clock.now() <= budget.fallback_deadline_monotonic,
              full_input_scores_traces_operations_exact=True,
              source_stable=batch.identity(source) == identity,
              production_changes=0, candidate_authors_worlds_tables=0, admission=False)
        save(out / 'CLOSURE.json', result)
        print({key: value for key, value in result.items() if key != 'scores'}, flush=True)
    assert vip._Projection is original_projection


if __name__ == '__main__':
    asyncio.run(main())
