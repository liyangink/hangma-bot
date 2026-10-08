"""记录到达相同最终节点的条件状态差异；实际规则与choose各最多一次。"""

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
from collections import Counter
from dataclasses import fields
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import time

from hangma_bot.application.deadline import BudgetPolicy, SystemClock
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
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


async def main():
    out = _project_file(_PROJECT_ROOT, HERE / 'duplicate-choices')
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
    overlay = module('t88_duplicate_overlay', _project_file(_PROJECT_ROOT, HERE / 'native_overlay.py'))
    capture_type = module('t88_duplicate_capture', t80 / 'probe.py').Capture
    original_projection = vip._Projection
    with overlay.installed() as execution:
        base = vip._Projection

        class ObservedProjection(base):
            instances = []

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.first_choices = {}
                self.duplicates = 0
                self.state_diffs = Counter()
                self.public_diffs = Counter()
                self.analysis_diffs = Counter()
                self.signatures = Counter()
                self.examples = []
                self.instances.append(self)

            def action_choices(self, analysis, key, *, followup_keys=None):
                result = super().action_choices(analysis, key, followup_keys=followup_keys)
                first = self.first_choices.get(result)
                if first is None:
                    self.first_choices[result] = analysis
                    return result
                self.duplicates += 1
                changed = []
                for field in fields(analysis.source_state):
                    if field.name == 'identity':
                        continue
                    before = getattr(first.source_state, field.name)
                    after = getattr(analysis.source_state, field.name)
                    if before != after:
                        changed.append(field.name)
                        self.state_diffs[field.name] += 1
                        if field.name in ('public_view', 'root_public_view') and before is not None and after is not None:
                            for subfield in fields(before):
                                if getattr(before, subfield.name) != getattr(after, subfield.name):
                                    self.public_diffs[field.name + '.' + subfield.name] += 1
                for field in fields(analysis):
                    if field.name != 'source_state' and getattr(first, field.name) != getattr(analysis, field.name):
                        self.analysis_diffs[field.name] += 1
                self.signatures['+'.join(changed) or '(only identity)'] += 1
                if len(self.examples) < 12 and changed:
                    item = dict(node_key=result, changed=changed)
                    for label, state in [('first', first.source_state), ('later', analysis.source_state)]:
                        item[label] = dict(concealed=[tile.code for tile in state.concealed],
                              drawn_tile=None if state.drawn_tile is None else state.drawn_tile.code,
                              my_peng_codes=list(state.my_peng_codes),
                              own_melds=[] if state.public_view is None else [
                                   dict(kind=meld.kind, tiles=[tile.code for tile in meld.tiles],
                                        seat=meld.seat, from_seat=meld.from_seat)
                                   for meld in state.public_view.melds[state.seat]])
                    self.examples.append(item)
                return result

        save(out / 'PLAN.json', dict(schema='t88-duplicate-choices-diagnostic/1',
              actual_rules_choose_budget=1, execution_identity=execution,
              script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              new_candidate_authors_worlds_tables=0, production_changes=0,
              diagnostic_timing_not_latency=True, admission=False))
        obs = observation_from_json(fixture['observation'])
        window = window_key_from_json(fixture['window_key'])
        rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
        request = DecisionRequest(obs, CompetitionContext('t88-diff', None, None, None, None, (), 0),
                                  rules, 't88-diff', window.trigger_seq, window, ())
        policy = vip.RouteVipHeuristicPolicy(batch.rule_config, source=source,
                     max_operations=batch.max_operations, projection_limits=batch.projection_limits)
        vip._Projection = ObservedProjection
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
        instance, = ObservedProjection.instances
        result = dict(schema='t88-duplicate-choices-result/1', status='SCORED',
              scores=scores, input_sha256=capture.input_sha, operations=capture.last_operation_count,
              actual_rules_attempts=1, actual_choose_attempts=1, actual_full_inputs=capture.calls,
              unique_choices=len(instance.first_choices), duplicate_choices=instance.duplicates,
              state_field_diffs=dict(instance.state_diffs), public_field_diffs=dict(instance.public_diffs),
              analysis_field_diffs=dict(instance.analysis_diffs), signatures=dict(instance.signatures),
              examples=instance.examples, elapsed_seconds=elapsed,
              diagnostic_timing_not_latency=True, full_input_scores_traces_operations_exact=True,
              production_changes=0, candidate_authors_worlds_tables=0, admission=False)
        save(out / 'CLOSURE.json', result)
        print({key: value for key, value in result.items() if key not in ('scores', 'examples')}, flush=True)
    assert vip._Projection is original_projection


if __name__ == '__main__':
    asyncio.run(main())
