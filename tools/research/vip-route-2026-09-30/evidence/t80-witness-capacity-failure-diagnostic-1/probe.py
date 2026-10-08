"""一次真实规则分析和choose复现容量故障；计数探针不用于延迟结论。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t80-witness-capacity-failure-diagnostic-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
import asyncio
import gzip
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

from hangma_bot.application.deadline import BudgetPolicy, SystemClock
from hangma_bot.hangma import hand_analysis
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.kernel.observation import CompetitionContext
from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
from hangma_bot.offline.vip_eoh_generate import VipEohBatch
from hangma_bot.policy.interface import DecisionRequest
from hangma_bot.policy import route_vip_heuristic as vip

HERE = Path(__file__).resolve().parent
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1')


def raw(value):
    """规范JSON保存真实输入，不使用宽松浮点或隐藏世界。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def save(path, value):
    with path.open('xb') as stream:
        stream.write(raw(value) + b'\n')


class Capture:
    """只在实际执行器已收到完整图时保存输入；建图失败不能补造输入。"""
    def __init__(self, original, archive):
        self.original, self.archive = original, archive
        self.calls, self.seconds, self.input_sha = 0, 0.0, None

    @property
    def last_operation_count(self):
        return self.original.last_operation_count

    @last_operation_count.setter
    def last_operation_count(self, value):
        self.original.last_operation_count = value

    def score_vip_route(self, view):
        begin = time.monotonic()
        dto = view.candidate_view()
        self.input_sha = hashlib.sha256(raw(dto)).hexdigest()
        self.archive.write(raw({'view_sha256': self.input_sha, 'view': dto}) + b'\n')
        self.archive.flush()
        self.seconds += time.monotonic() - begin
        self.calls += 1
        return self.original.score_vip_route(view)


async def main(mode):
    out = _project_file(_PROJECT_ROOT, HERE / mode)
    out.mkdir(exist_ok=False)
    fixture = json.loads((_project_file(_PROJECT_ROOT, HERE / 'FAILED-PUBLIC-WINDOW.json')).read_text())
    original = fixture['actual_failed_row']
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, AUTHOR / 'S01-generation.batch.json'))
    source = (_project_file(_PROJECT_ROOT, AUTHOR / 'S01-model-output/candidate.py')).read_text()
    identity = batch.identity(source)
    save(out / 'START.json', {'mode': mode, 'runtime_identity': identity,
         'original_candidate_id': original['policy_id'],
         'fixture_sha256': hashlib.sha256(raw(fixture)).hexdigest(),
         'actual_choose_budget': 1, 'actual_rules_budget': 1,
         'projection_limits_unchanged': True, 'source_unchanged': True,
         'new_models_worlds_tables': 0, 'online_admission': False})
    histogram, legal_by_shanten = Counter(), Counter()
    original_witness = vip.analyze_waiting_hu_witness
    if mode == 'instrumented':
        def observed(state, tile, **kwargs):
            result = original_witness(state, tile, **kwargs)
            summary = hand_analysis.analyse_hand(state.concealed, state.meld_count)
            after = next(t.shanten_after for t in summary.useful_tiles if t.code == tile.code)
            histogram[(summary.shanten, after)] += 1
            if result.legal_hu:
                legal_by_shanten[(summary.shanten, after)] += 1
            assert summary.shanten == 0 or not result.legal_hu
            return result
        vip.analyze_waiting_hu_witness = observed
    observation = observation_from_json(original['observation'])
    key = window_key_from_json(original['window_key'])
    policy = vip.RouteVipHeuristicPolicy(batch.rule_config, source=source,
                 max_operations=batch.max_operations, projection_limits=batch.projection_limits)
    begin, cpu = time.monotonic(), time.process_time()
    rules = HangmaRules(batch.rule_config).analyze(observation, route_limits=batch.route_limits)
    assert {c.action_key for c in rules.legal_candidates} == set(original['legal_action_keys'])
    request = DecisionRequest(observation, CompetitionContext('t80-public-repro', None, None,
                              None, None, (), 0), rules, 't80-repro', key.trigger_seq, key, ())
    rules_seconds = time.monotonic() - begin
    budget = BudgetPolicy().build(SystemClock().now(), 1.0)
    result = {'mode': mode, 'rules_complete': True, 'rules_seconds': rules_seconds,
              'legal_keys': sorted(original['legal_action_keys']), 'choose_attempts': 1,
              'actual_rules_attempts': 1, 'status': 'not_scored', 'error': None}
    with gzip.open(out / 'ACTUAL-INPUTS.jsonl.gz', 'xb') as stream:
        capture = Capture(policy.executor, stream)
        policy.executor = capture
        wall, choose_cpu = time.monotonic(), time.process_time()
        try:
            plan = await policy.choose(request, budget)
            result['status'] = 'SCORED'
            result['full_legal_outputs'] = set(result['legal_keys']) == {c.action_key for c in plan.candidates}
            result['degraded_reasons'] = list(plan.degraded_reasons)
            result['scores'] = [{'key': c.action_key, 'score': c.total_score, 'trace': c.score_trace}
                                for c in plan.candidates]
        except Exception as exc:
            result['status'] = 'FAILED'
            result['error'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            vip.analyze_waiting_hu_witness = original_witness
        result.update({'choose_wall_seconds': time.monotonic()-wall,
             'choose_cpu_seconds': time.process_time()-choose_cpu,
             'capture_seconds': capture.seconds, 'actual_full_inputs': capture.calls,
             'input_sha256': capture.input_sha, 'operations': policy.executor.last_operation_count,
             'witness_histogram': [{'shanten': s, 'after': a, 'calls': n}
                                   for (s,a),n in sorted(histogram.items())],
             'legal_hu_histogram': [{'shanten': s, 'after': a, 'calls': n}
                                    for (s,a),n in sorted(legal_by_shanten.items())],
             'instrumented_time_not_production_latency': mode == 'instrumented',
             'new_models_worlds_tables': 0, 'online_admission': False})
    save(out / 'CLOSURE.json', result)
    print({k: result[k] for k in ('status','error','actual_full_inputs','operations',
                                  'choose_wall_seconds','witness_histogram','legal_hu_histogram')})
    if result['status'] != 'SCORED':
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', required=True)
    asyncio.run(main(parser.parse_args().mode))
