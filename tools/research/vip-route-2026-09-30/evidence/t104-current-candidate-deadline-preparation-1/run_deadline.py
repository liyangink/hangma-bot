"""固定T101的本地完整计算计时；静态检查不导入或执行业务模块。

真实执行须先有T103四个工具终态、完整读回终态及预登记强度信号。
计时从规则分析前开始，包含整图记录，不扣除记录开销授时限通过。
本脚本不访问官方平台，不生成世界，不修改公式，也不自动发布。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t104-current-candidate-deadline-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import ast
import asyncio
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t101-joint-breadth-recovery-author-1')
CONFIRMATION = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t103-joint-breadth-fresh-confirmation-1')
RUNTIME = Path('/Users/liyang/.codex/worktrees/t54-public-count-cache/hangma-bot')
OUT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t104-current-candidate-deadline-preparation-1/actual-direct-1')
COUNTERS = ('rule_attempts', 'choose_attempts', 'direct_score_attempts',
            'reference_score_attempts', 'failed_score_attempts')


def canonical(value):
    """公开输入、全部分值和解释按完整规范字节比较，不使用浮点容差。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(path):
    """文件按实际字节计算SHA，不改写任何冻结材料。"""
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    """独占创建收据；原执行目录存在时不覆盖、不重试至通过。"""
    with Path(path).open('xb') as stream:
        stream.write(canonical(value) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())


def static_check():
    """仅核JSON、源码字节和语法；不装载候选，不分析规则，不评分。"""
    plan = read(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json'))
    cases = read(_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-REQUESTS.json'))['cases']
    freeze = read(_project_file(_PROJECT_ROOT, HERE / 'EXECUTABLE-FREEZE.json'))
    if freeze['runner_sha256'] != sha(Path(__file__)):
        raise ValueError('可执行脚本与冻结摘要不符')
    if freeze['plan_sha256'] != sha(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')):
        raise ValueError('原准备计划漂移')
    if freeze['candidate_identity'] != plan['candidate_identity']:
        raise ValueError('执行冻结没有绑定当前候选身份')
    for name, expected in plan['frozen_files'].items():
        if sha(name) != expected:
            raise ValueError('准备输入漂移：' + name)
    for name, expected in freeze['runtime_source_manifest'].items():
        path = _project_file(_PROJECT_ROOT, RUNTIME / name)
        if path.stat().st_size != expected['bytes'] or sha(path) != expected['sha256']:
            raise ValueError('运行源码漂移：' + name)
    original = read(_project_file(_PROJECT_ROOT, HERE / 'FROZEN-ENGINEERING-SOURCE-MANIFEST.json'))
    if any(freeze['runtime_source_manifest'].get(k) != v for k, v in original.items()):
        raise ValueError('运行冻结未完整承接原工程源码清单')
    source = _project_file(_PROJECT_ROOT, AUTHOR / 'S02-model-output/candidate.py')
    if sha(source) != plan['candidate_identity']['source_sha256']:
        raise ValueError('候选原源码漂移')
    ast.parse(source.read_text(encoding='utf-8'))
    ast.parse(Path(__file__).read_text(encoding='utf-8'))
    by_label = {case['label']: case for case in cases}
    order = plan['ordered_direct_choose_requests']
    if len(by_label) != 7 or plan['max_direct_choose_attempts'] != 8:
        raise ValueError('公开请求分母不符')
    if len(order) != 8 or len(by_label) != plan['unique_public_requests']:
        raise ValueError('公开请求分母不符')
    if set(order) != set(by_label) or order[0] != order[-1]:
        raise ValueError('请求顺序或同输入暖态不符')
    missing = [r['label'] for r in cases if r['known_T101_actual_entries'] is None]
    if missing != ['original-T80-failed-response'] or plan['max_new_reference_score_attempts'] != 1:
        raise ValueError('缺失参考数量不符')
    for case in cases:
        entries = case['known_T101_actual_entries']
        if entries is not None:
            keys = [r['action_key'] for r in entries]
            if len(set(keys)) != len(keys) or not keys:
                raise ValueError('既有参考合法键异常')
            if any(type(r['score']) not in (int, float) or not math.isfinite(r['score']) for r in entries):
                raise ValueError('既有参考包含非有限分值')
            if type(case['known_T101_operations']) is not int or not case['known_complete_view_sha256']:
                raise ValueError('既有完整参考缺计量或输入摘要')
    return plan, by_label, freeze


def activation_check(plan):
    """先核实际终态再读成绩；未终态时绝不提前开卷确认批收益。"""
    terminal_paths = [_project_file(_PROJECT_ROOT, CONFIRMATION / f'BLOCK-{i:02d}-TERMINAL.json') for i in range(1, 5)]
    reader_path = _project_file(_PROJECT_ROOT, CONFIRMATION / 'ACTUAL-READBACK-TERMINAL.json')
    if not all(p.exists() for p in terminal_paths) or not reader_path.exists():
        return {'ready': False, 'reason': 'waiting_actual_T103_process_and_readback_terminals',
                'confirmation_outcomes_read': False}
    handles = read(_project_file(_PROJECT_ROOT, CONFIRMATION / 'PROCESS-HANDLES.json'))['processes']
    if len(handles) != 4:
        raise ValueError('确认进程数量不符')
    for path, handle in zip(terminal_paths, handles):
        actual = read(path)
        if (actual['block'] != handle['block'] or actual['session_id'] != handle['session_id']
                or type(actual['exit_code']) is not int or actual['exit_code'] != 0
                or actual['verified_tool_terminal'] is not True):
            raise ValueError('确认进程缺有效实际工具终态')
    reader = read(reader_path)
    if type(reader['exit_code']) is not int or reader['exit_code'] != 0 or reader['verified_tool_terminal'] is not True:
        raise ValueError('确认读取器缺有效实际工具终态')
    closed = read(_project_file(_PROJECT_ROOT, CONFIRMATION / 'CAMPAIGN-CLOSURE.json'))
    confirmation_plan = read(_project_file(_PROJECT_ROOT, CONFIRMATION / 'CAMPAIGN-PLAN.json'))
    if (closed['whole_batch_valid'] is not True or closed['issues']
            or closed['candidate_identity'] != plan['candidate_identity']
            or closed['observed_hands_in_this_readback'] != 8192
            or closed['planned_independent_roots'] != 128):
        raise ValueError('确认批不完整或身份不一致')
    if not closed['net_positive_interval'] or closed['root_cluster_percentile_95'][0] <= 0:
        return {'ready': False, 'reason': 'T103_no_predeclared_positive_interval',
                'confirmation_outcomes_read': True}
    candidate_policy_id = 'vip:' + plan['candidate_identity']['candidate_id']
    highfan = defaultdict(lambda: {'A': 0, 'C': 0})
    seen = set()
    for block in range(1, 5):
        with gzip.open(_project_file(_PROJECT_ROOT, CONFIRMATION / f'block-{block:02d}/settlements.jsonl.gz'), 'rt') as stream:
            for line in stream:
                row = json.loads(line)
                key = (row['match_id'], row['round_no'])
                if key in seen or row['root_id'] not in confirmation_plan['root_ids']:
                    raise ValueError('确认结算重复或未知来源')
                seen.add(key)
                s, seat = row['settlement'], row['focal_physical_seat']
                if not s['is_draw'] and s['winner_seat'] == seat and s['fan'] >= 4:
                    arm = 'C' if row['match_id'].endswith(candidate_policy_id) else 'A'
                    highfan[row['root_id']][arm] += s['score_delta'][seat]
    bands = closed['realized_mutually_exclusive_bands']
    if len(seen) != 8192:
        raise ValueError('确认结算单局分母不符')
    for arm in ('A', 'C'):
        expected = sum(bands[arm][k]['score'] for k in ('own_4_to7', 'own_8_to15', 'own_ge16'))
        if sum(v[arm] for v in highfan.values()) != expected:
            raise ValueError('确认大牌分账不符')
    net = sum(v['C'] - v['A'] for v in highfan.values())
    positive_roots = sum(v['C'] > v['A'] for v in highfan.values())
    if net <= 0 or positive_roots < 2:
        return {'ready': False, 'reason': 'T103_no_cross_source_positive_highfan_signal',
                'confirmation_outcomes_read': True}
    processes = subprocess.run(['ps', '-axo', 'pid=,command='], check=True,
                               capture_output=True, text=True).stdout.splitlines()
    table_pids = [int(line.split(None, 1)[0]) for line in processes
                  if 'run_block.py' in line and 'python' in line.lower()]
    if table_pids:
        return {'ready': False, 'reason': 'known_table_runner_still_live',
                'live_table_pids': table_pids, 'confirmation_outcomes_read': True}
    return {'ready': True, 'T103_closure_sha256': sha(_project_file(_PROJECT_ROOT, CONFIRMATION / 'CAMPAIGN-CLOSURE.json')),
            'actual_reader_terminal': reader, 'actual_process_terminals': [read(p) for p in terminal_paths],
            'highfan_net_gain': net, 'positive_highfan_source_roots': positive_roots,
            'parallel_table_check': 'ps: no Python run_block.py; project campaign processes terminal'}


class CaptureExecutor:
    """评分前完整录图并记实际调用；不改变评分、节点、操作计量或预算。"""

    def __init__(self, original, capture, costs, kind):
        self.original, self.capture, self.costs, self.kind = original, capture, costs, kind
        self.label = None
        self.calls = []

    @property
    def last_operation_count(self):
        return self.original.last_operation_count

    @last_operation_count.setter
    def last_operation_count(self, value):
        self.original.last_operation_count = value

    def score_vip_route(self, view):
        wall, cpu = time.monotonic(), time.process_time()
        receipt = self.capture.store(view.candidate_view())
        call = {'label': self.label, 'kind': self.kind, 'input_capture': asdict(receipt),
                'capture_wall_seconds': time.monotonic() - wall,
                'capture_cpu_seconds': time.process_time() - cpu, 'actual_score_attempts': 0,
                'status': 'not_scored'}
        self.calls.append(call)
        with (_project_file(_PROJECT_ROOT, OUT / 'SCORE-ATTEMPTS.jsonl')).open('ab') as stream:
            stream.write(canonical(call) + b'\n'); stream.flush()
        if not receipt.saved_before_score or receipt.error is not None:
            raise ValueError('实际评分前完整输入未保存')
        self.costs[self.kind + '_score_attempts'] += 1
        call['actual_score_attempts'] = 1
        try:
            result = self.original.score_vip_route(view)
            call.update(status=result.status, operations=self.last_operation_count,
                        entries=[{'action_key': e.action_key, 'score': e.score, 'trace': dict(e.trace)}
                                 for e in result.entries])
            return result
        except Exception as exc:
            self.costs['failed_score_attempts'] += 1
            call.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
            raise
        finally:
            save(_project_file(_PROJECT_ROOT, OUT / f'SCORE-{len(self.calls):02d}-{self.kind}.json'), call)


def equal_reference(row, expected):
    """完整动作、分值、解释、输入SHA与操作数必须全部相同。"""
    order = lambda entries: sorted(entries, key=lambda x: x['action_key'])
    return (row['actual_input_sha256'] == expected['known_complete_view_sha256']
            and row['operations'] == expected['known_T101_operations']
            and canonical(order(row['actual_scores'])) == canonical(order(expected['known_T101_actual_entries'])))


async def execute(plan, cases, freeze, activation):
    """唯一真实入口；最多八次choose和一次补参考，失败保留且不新增重复。"""
    sys.path[:0] = [str(RUNTIME), str(_project_file(_PROJECT_ROOT, RUNTIME / 'src'))]
    from hangma_bot.application.deadline import BudgetPolicy, SystemClock
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.offline.vip_eoh_generate import VipEohBatch
    from hangma_bot.policy.action_value_executor import ActionValueExecutor
    from hangma_bot.policy.interface import DecisionRequest
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy, build_vip_route_scoring_view

    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, AUTHOR / 'S02-generation.batch.json'))
    source = (_project_file(_PROJECT_ROOT, AUTHOR / 'S02-model-output/candidate.py')).read_text(encoding='utf-8')
    identity = batch.identity(source)
    if identity != plan['candidate_identity']:
        raise ValueError('实际运行依赖或原生数学后端身份漂移')
    OUT.mkdir(exist_ok=False)
    save(_project_file(_PROJECT_ROOT, OUT / 'START.json'), {'schema': 't104-direct-full-calculation-start/1',
        'started_at_utc': datetime.now(timezone.utc).isoformat(), 'activation': activation,
        'candidate_identity': identity, 'runner_sha256': sha(Path(__file__)),
        'freeze_sha256': sha(_project_file(_PROJECT_ROOT, HERE / 'EXECUTABLE-FREEZE.json')), 'ordered_choose_requests': plan['ordered_direct_choose_requests'],
        'actual_choose_budget': 8, 'new_reference_score_budget': 1,
        'reference_runs_after_all_choose_to_avoid_pre_warming_first_request': True,
        'capture_limits': freeze['capture_limits'], 'new_models_worlds_tables': 0,
        'scope': 'local direct rules+graph+capture+choose; no HTTP/SSE/POST, concurrent service or admission'})
    costs = dict.fromkeys(COUNTERS, 0)
    rows, issues = [], []
    clock, budgets = SystemClock(), BudgetPolicy()
    startup = time.monotonic()
    policy = RouteVipHeuristicPolicy(batch.rule_config, source=source,
        max_operations=batch.max_operations, projection_limits=batch.projection_limits)
    startup_seconds = time.monotonic() - startup
    limits = ScoringInputCaptureLimits.from_json(freeze['capture_limits'])
    with (_project_file(_PROJECT_ROOT, OUT / 'ACTUAL-INPUTS.jsonl.gz')).open('x+b') as stream:
        capture = ScoringInputCapture(stream, limits=limits)
        executor = CaptureExecutor(policy.executor, capture, costs, 'direct')
        policy.executor = executor
        for ordinal, label in enumerate(plan['ordered_direct_choose_requests'], 1):
            raw = cases[label]
            obs, key = observation_from_json(raw['observation']), window_key_from_json(raw['window_key'])
            executor.label = label
            span = 1.0 if obs.phase.startswith('response_') else 3.0
            begin, cpu = clock.now(), time.process_time()
            budget = budgets.build(begin, span)
            timer_at = []
            timer = asyncio.get_running_loop().call_later(0.01, lambda: timer_at.append(clock.now()))
            row = {'ordinal': ordinal, 'label': label, 'phase': obs.phase,
                   'span_seconds': span, 'status': 'not_scored',
                   'budget_seconds': {'enhancement': budget.enhancement_deadline_monotonic - begin,
                       'fallback': budget.fallback_deadline_monotonic - begin,
                       'latest_send': budget.latest_send_at_monotonic - begin}}
            try:
                costs['rule_attempts'] += 1
                rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                row['rules_wall_seconds'] = clock.now() - begin
                request = DecisionRequest(obs, CompetitionContext('T101-public-probe', None, None, None, None, (), 0),
                                          rules, label, key.trigger_seq, key, ())
                costs['choose_attempts'] += 1
                before_calls = len(executor.calls)
                chosen = await policy.choose(request, budget)
                ready, cpu_ready = clock.now(), time.process_time()
                row.update(elapsed_wall_seconds=ready - begin, elapsed_cpu_seconds=cpu_ready - cpu,
                           ready_before_fallback=ready <= budget.fallback_deadline_monotonic,
                           ready_before_latest_send=ready <= budget.latest_send_at_monotonic)
                if len(executor.calls) != before_calls + 1 or chosen.degraded_reasons:
                    raise ValueError('choose没有一次完整自身评分或发生降级')
                call = executor.calls[-1]
                actual = [{'action_key': c.action_key, 'score': c.total_score, 'trace': c.score_trace['detail']}
                          for c in chosen.candidates]
                keys = [c['action_key'] for c in actual]
                if len(keys) != len(set(keys)) or set(keys) != {c.action_key for c in rules.candidates}:
                    raise ValueError('未覆盖全部合法动作')
                if any(type(c['score']) not in (int, float) or not math.isfinite(c['score']) for c in actual):
                    raise ValueError('非有限分值')
                if keys != [c['action_key'] for c in sorted(actual, key=lambda c: (-c['score'], c['action_key']))]:
                    raise ValueError('返回次序不符')
                row.update(status='SCORED', actual_scores=actual, operations=call['operations'],
                           actual_input_sha256=call['input_capture']['view_sha256'], input_capture=call['input_capture'],
                           capture_wall_seconds=call['capture_wall_seconds'], capture_cpu_seconds=call['capture_cpu_seconds'])
                if raw['known_T101_actual_entries'] is not None:
                    row['exact_all_legal_scores_traces_input_operations'] = equal_reference(row, raw)
                    if not row['exact_all_legal_scores_traces_input_operations']:
                        raise ValueError('与既有真实完整参考不等价')
                else:
                    row['exact_all_legal_scores_traces_input_operations'] = None
            except Exception as exc:
                row.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
                issues.append(row['error'])
            finally:
                await asyncio.sleep(0.012)
                timer.cancel()
                row['event_loop_timer_lag_seconds'] = max(0.0, timer_at[0] - begin - 0.01) if timer_at else None
                save(_project_file(_PROJECT_ROOT, OUT / f'CHOOSE-{ordinal:02d}.json'), row)
                rows.append(row)
                print({k: row.get(k) for k in ('ordinal', 'label', 'status', 'elapsed_wall_seconds',
                                             'ready_before_fallback', 'event_loop_timer_lag_seconds', 'error')}, flush=True)
            if issues:
                break
        if not issues and len(rows) == 8:
            raw = cases['original-T80-failed-response']
            reference = CaptureExecutor(ActionValueExecutor(source, max_operations=batch.max_operations,
                max_local_collection_size=batch.projection_limits.max_nodes), capture, costs, 'reference')
            reference.label = raw['label']
            try:
                costs['rule_attempts'] += 1
                obs, key = observation_from_json(raw['observation']), window_key_from_json(raw['window_key'])
                rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                request = DecisionRequest(obs, CompetitionContext('T101-public-probe', None, None, None, None, (), 0),
                                          rules, raw['label'], key.trigger_seq, key, ())
                view = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                result = reference.score_vip_route(view)
                call = reference.calls[-1]
                expected = {'known_complete_view_sha256': call['input_capture']['view_sha256'],
                            'known_T101_operations': call['operations'], 'known_T101_actual_entries': call['entries']}
                target = next(r for r in rows if r['label'] == raw['label'])
                target['exact_all_legal_scores_traces_input_operations'] = result.status == 'SCORED' and equal_reference(target, expected)
                if not target['exact_all_legal_scores_traces_input_operations']:
                    raise ValueError('原故障响应的真实新参考不等价')
                save(_project_file(_PROJECT_ROOT, OUT / 'NEW-REFERENCE-READBACK.json'), expected)
            except Exception as exc:
                issues.append(type(exc).__name__ + ': ' + str(exc))
        capture_costs = capture.finish()
        terminal = capture_costs['terminal']
        if not terminal['terminal_valid']:
            issues.append('完整评分输入捕获终态无效')
    try:
        static_check()
        if batch.identity(source) != identity:
            raise ValueError('运行后候选身份漂移')
    except Exception as exc:
        issues.append(type(exc).__name__ + ': ' + str(exc))
    complete = (not issues and len(rows) == 8 and costs['choose_attempts'] == 8
                and costs['direct_score_attempts'] == 8 and costs['reference_score_attempts'] == 1
                and all(r['status'] == 'SCORED' and r['exact_all_legal_scores_traces_input_operations'] for r in rows))
    deadline = complete and all(r['ready_before_fallback'] for r in rows)
    closed = {'schema': 't104-direct-full-calculation-result/1', 'candidate_identity': identity,
              'mathematical_complete': complete, 'local_full_calculation_deadline_pass': deadline,
              'event_loop_lag_is_diagnostic_not_official_standard': True,
              'actual_costs': costs, 'scoring_input_capture': capture_costs,
              'policy_initialization_wall_seconds_outside_per_window_timer': startup_seconds,
              'rows': rows, 'issues': issues, 'published': False, 'online_admission': False,
              'new_models_worlds_tables': 0,
              'scope': 'seven development public inputs, one warm repeat; no global/runtime service/official timing gate'}
    save(_project_file(_PROJECT_ROOT, OUT / 'CLOSURE.json'), closed)
    print({'mathematical_complete': complete, 'local_full_calculation_deadline_pass': deadline,
           'actual_costs': costs, 'issues': issues}, flush=True)
    return 0 if deadline else 1


def main():
    """check-only可随时纯读；execute只有冻结确认门通过才创建实际目录。"""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-only', action='store_true')
    mode.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    plan, cases, freeze = static_check()
    activation = activation_check(plan)
    if args.check_only:
        print(json.dumps({'static_valid': True, 'public_unique_requests': len(cases),
                          'max_choose_attempts': 8, 'max_new_reference_attempts': 1,
                          'activation': activation, 'actual_rules_scores_choose_worlds_tables': 0}, ensure_ascii=False))
        return 0
    if not activation['ready']:
        print(json.dumps(activation, ensure_ascii=False))
        return 2
    return asyncio.run(execute(plan, cases, freeze, activation))


if __name__ == '__main__':
    raise SystemExit(main())
