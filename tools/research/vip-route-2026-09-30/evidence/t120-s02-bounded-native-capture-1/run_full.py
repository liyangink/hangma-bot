"""当前S02原生执行加有界完整记录；不改公式、公开容量或全动作覆盖。

调用路径来自 T114 剖析工具，业务变化是已验源码的原生执行及已完成条件节点复用。整图捕获
计入原返回预算，所有分数、解释、输入摘要和操作数必须等同 T113。
局部通过不授有界计算服务、并发或官方发布资格。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t120-s02-bounded-native-capture-1'

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
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
T113 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t113-t110-s02-deadline-preparation-1')
OUT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t120-s02-bounded-native-capture-1/actual-full-1')


def canonical(value):
    """完整数据使用规范 JSON 字节；浮点分数不得用容差替代。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    """只创建新收据，保留第一次执行和任何失败。"""
    with Path(path).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def prepare():
    """零业务调用静态核验；复用原冻结核验，不执行其计时入口。"""
    plan = read(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json'))
    if plan['runner_sha256'] != sha(Path(__file__)):
        raise ValueError('剖析脚本漂移')
    for path, expected in plan['frozen_files'].items():
        if sha(path) != expected:
            raise ValueError('剖析参考漂移：' + path)
    helper_path = _project_file(_PROJECT_ROOT, T113 / 'run_deadline_corrected.py')
    spec = importlib.util.spec_from_file_location('t113_profile_reference', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    original_plan, cases, freeze = helper.static_check()
    if original_plan['candidate_identity'] != plan['candidate_identity']:
        raise ValueError('不是独立确认的 S02 原身份')
    prior = read(_project_file(_PROJECT_ROOT, T113 / 'actual-direct-2/CLOSURE.json'))
    if not prior['mathematical_complete'] or prior['local_full_calculation_deadline_pass']:
        raise ValueError('缺少既有数学通过且时限失败的基线')
    confirmation = read(helper.CONFIRMATION / 'ROOT-HIGHFAN-READBACK.json')
    if not confirmation['independent_strength_signal_passed']:
        raise ValueError('缺少独立增强信号')
    if plan['labels'] != ['original-T80-failed-response', 'old:public:20']:
        raise ValueError('剖析输入范围变更')
    return plan, cases, freeze, prior, helper




async def execute(plan, cases, freeze, prior, helper):
    """最多两次规则分析与两次完整 choose；没有追加参考、模型或桌赛。"""
    runtime = helper.RUNTIME
    sys.path[:0] = [str(runtime), str(runtime / 'src')]
    from hangma_bot.application.deadline import BudgetPolicy, SystemClock
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.offline.vip_eoh_generate import VipEohBatch
    from hangma_bot.policy.interface import DecisionRequest
    from hangma_bot.policy.route_vip_heuristic import RouteVipHeuristicPolicy

    batch = VipEohBatch.read(helper.AUTHOR / 'AUTHOR-BATCH.json')
    source = (helper.AUTHOR / 'S02-model-output/candidate.py').read_text(encoding='utf-8')
    identity = batch.identity(source)
    if identity != plan['candidate_identity']:
        raise ValueError('实际候选或原生数学后端漂移')
    OUT.mkdir(exist_ok=False)
    helper.OUT = OUT  # 捕获器的输出路径显式转到新实验；不写原证据。
    save(_project_file(_PROJECT_ROOT, OUT / 'START.json'), {'started_at_utc': datetime.now(timezone.utc).isoformat(),
         'runner_sha256': sha(Path(__file__)), 'plan_sha256': sha(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')),
         'base_candidate_identity': identity, 'research_execution_identity': plan['research_execution_identity'],
         'max_choose_attempts': 2,
         'max_score_attempts': 2, 'research_variant_is_not_official_deadline_admission': True})
    costs = dict.fromkeys(helper.COUNTERS, 0)
    clock, budgets = SystemClock(), BudgetPolicy()
    policy = RouteVipHeuristicPolicy(batch.rule_config, source=source,
        max_operations=batch.max_operations, projection_limits=batch.projection_limits)
    native_type = type(policy.executor._fn).__name__
    if native_type != 'cython_function_or_method':
        raise ValueError('当前S02没有实际装配编译函数')
    save(_project_file(_PROJECT_ROOT, OUT / 'ACTUAL-NATIVE-FUNCTION.json'), {'type': native_type,
        'source_sha256': identity['source_sha256'], 'compiled_current_S02': True})
    rows, issues = [], []
    with (_project_file(_PROJECT_ROOT, OUT / 'ACTUAL-INPUTS.jsonl.gz')).open('x+b') as stream:
        capture = ScoringInputCapture(stream,
            limits=ScoringInputCaptureLimits.from_json(freeze['capture_limits']))
        executor = helper.CaptureExecutor(policy.executor, capture, costs, 'direct')
        policy.executor = executor
        for ordinal, label in enumerate(plan['labels'], 1):
            raw = cases[label]
            expected = next(row for row in prior['rows'] if row['label'] == label)
            obs = observation_from_json(raw['observation'])
            key = window_key_from_json(raw['window_key'])
            executor.label = label
            begin = clock.now()
            budget = budgets.build(begin, 1.0 if obs.phase.startswith('response_') else 3.0)
            row = {'ordinal': ordinal, 'label': label, 'status': 'not_scored', 'actual_function_type': native_type}
            try:
                costs['rule_attempts'] += 1
                rules = HangmaRules(batch.rule_config).analyze(obs, route_limits=batch.route_limits)
                rules_end = clock.now()
                request = DecisionRequest(obs,
                    CompetitionContext('T110-S02-public-probe', None, None, None, None, (), 0),
                    rules, label, key.trigger_seq, key, ())
                costs['choose_attempts'] += 1
                chosen = await policy.choose(request, budget)
                ready = clock.now()
                if len(executor.calls) != ordinal or chosen.degraded_reasons:
                    raise ValueError('未完整独立评分或发生降级')
                call = executor.calls[-1]
                actual = [{'action_key': c.action_key, 'score': c.total_score,
                           'trace': c.score_trace['detail']} for c in chosen.candidates]
                order = lambda entries: sorted(entries, key=lambda e: e['action_key'])
                exact = (call['input_capture']['view_sha256'] == expected['actual_input_sha256']
                    and call['operations'] == expected['operations']
                    and canonical(order(actual)) == canonical(order(expected['actual_scores']))
                    and set(e['action_key'] for e in actual)
                        == {c.action_key for c in rules.legal_candidates})
                row.update(status='SCORED', exact_input_all_scores_traces_operations=exact,
                    operations=call['operations'], chosen_action_key=chosen.candidates[0].action_key,
                    input_sha256=call['input_capture']['view_sha256'],
                    ready_before_fallback=ready <= budget.fallback_deadline_monotonic,
                    ready_before_latest_send=ready <= budget.latest_send_at_monotonic,
                    elapsed_wall_seconds=ready - begin,
                    rules_wall_seconds=rules_end - begin,
                    pre_score_wall_seconds=call['input_ready_monotonic'] - rules_end,
                    capture_wall_seconds=call['capture_wall_seconds'],
                    score_wall_seconds=call['score_wall_seconds'])
                if not exact:
                    raise ValueError('完整原始参考不等价')
            except BaseException as exc:
                row.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
                issues.append(row['error'])
            finally:
                save(_project_file(_PROJECT_ROOT, OUT / f'CHOOSE-{ordinal:02d}.json'), row)
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
            if issues:
                break
        capture_costs = capture.finish()
    if not capture_costs['terminal']['terminal_valid']:
        issues.append('完整输入捕获终态无效')
    helper.static_check()
    if batch.identity(source) != identity:
        issues.append('运行后身份漂移')
    complete = (not issues and len(rows) == 2 and costs['rule_attempts'] == 2
        and costs['choose_attempts'] == 2 and costs['direct_score_attempts'] == 2
        and costs['reference_score_attempts'] == 0 and costs['failed_score_attempts'] == 0
        and all(r['exact_input_all_scores_traces_operations'] for r in rows))
    save(_project_file(_PROJECT_ROOT, OUT / 'CLOSURE.json'), {'schema': 't120-s02-bounded-capture-full-result/1',
        'base_candidate_identity': identity, 'research_execution_identity': plan['research_execution_identity'],
        'full_math_exact': complete,
        'local_two_input_deadline_pass': complete and all(r['ready_before_fallback'] for r in rows),
        'actual_costs': costs, 'rows': rows, 'issues': issues,
        'capture': capture_costs, 'new_models_worlds_tables': 0,
        'deadline_admission': False, 'online_admission': False, 'published': False})
    return 0 if complete else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-only', action='store_true')
    mode.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    prepared = prepare()
    if args.check_only:
        print(json.dumps({'static_valid': True, 'max_rule_choose_score_attempts': 2,
            'actual_business_calls': 0, 'research_not_official_deadline_admission': True}))
        return 0
    sys.path[:0] = [str(prepared[-1].RUNTIME), str(prepared[-1].RUNTIME / 'src')]
    from native_overlay import installed
    with installed() as overlay:
        if overlay != prepared[0]['research_execution_identity']['overlay']:
            raise ValueError('缓存装配与冻结身份不符')
        return asyncio.run(execute(*prepared))


if __name__ == '__main__':
    raise SystemExit(main())
