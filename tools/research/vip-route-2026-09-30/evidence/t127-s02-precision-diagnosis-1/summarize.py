"""精细诊断读回：只读取原证据，不新增规则、评分、世界或桌赛。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t127-s02-precision-diagnosis-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter
import json
from pathlib import Path
import re

import diagnose as base

HERE = Path(__file__).resolve().parent


def native_summary(path):
    """按完整调用树计算独占栈计数；不叠加递归累计、不当作CPU指令计数。"""
    text = path.read_text()
    graph = text.split('Call graph:\n', 1)[1].split('Total number in stack', 1)[0]
    pattern = re.compile(r'^([ +!|:`]*)(\d+) (.+)$')
    stack, nodes = [], []
    for line in graph.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        prefix, count, label = match.groups()
        depth = len(prefix)
        while stack and stack[-1]['depth'] >= depth:
            stack.pop()
        node = {'depth': depth, 'count': int(count), 'label': label,
                'children_count': 0, 'parent': stack[-1] if stack else None}
        if stack:
            stack[-1]['children_count'] += int(count)
        stack.append(node)
        nodes.append(node)
    leaves, phases, operations = Counter(), Counter(), Counter()
    active_samples = 0
    for node in nodes:
        own = node['count'] - node['children_count']
        assert own >= 0, node
        if not own:
            continue
        path_labels, cursor = [], node
        while cursor:
            path_labels.append(cursor['label'])
            cursor = cursor['parent']
        lineage = '\n'.join(path_labels)
        idle = any(token in lineage for token in ('time_sleep ', 'nanosleep ', 'kevent ', 'waitpid '))
        if idle:
            phases['idle_or_wait'] += own
            continue
        active_samples += own
        label = node['label']
        symbol = label.split('  (in ', 1)[0].split(' (in ', 1)[0]
        leaves[symbol] += own
        if '_t88_projection.' in lineage or '_t88_transition.' in lineage:
            phase = 'graph_construction'
        elif '_t88_plain.' in lineage:
            phase = 'input_conversion'
        elif '_t118_candidate.' in lineage or '_t89_runtime.' in lineage or '_t88_executor.' in lineage:
            phase = 'formula_and_executor'
        elif '_t120_codec.' in lineage or 'libz.1.dylib' in lineage or '_json.' in lineage:
            phase = 'encoding_or_compression'
        else:
            phase = 'unclassified_python_or_harness'
        phases[phase] += own
        if '_grouped_native.' in label:
            operation = 'C_hand_math'
        elif any(token in label for token in ('dealloc', 'Malloc', 'Free ', 'Realloc', 'malloc', 'PyTuple_New', 'PyDict_New', '_PyTuple_Resize', 'PyList_New')):
            operation = 'allocation_or_release'
        elif any(token in label for token in ('gc_collect', 'visit_', 'update_refs', 'deduce_unreachable', 'subtract_refs')):
            operation = 'garbage_collection'
        elif any(token in label for token in ('GetAttr', 'getattr', 'tuplehash', 'tuplesubscript', 'tuplecontains', 'PyDict_', 'lookdict', 'richcompare')):
            operation = 'object_lookup_hash_or_comparison'
        elif '_PyEval_' in label:
            operation = 'Python_bytecode_evaluation'
        elif any(token in label for token in ('Vectorcall', 'vectorcall', 'type_call', 'slot_tp_init', 'Generator_', 'gen_iternext')):
            operation = 'function_object_or_generator_dispatch'
        else:
            operation = 'other_native_or_generated_work'
        operations[operation] += own
    roots = sum(node['count'] for node in nodes if node['parent'] is None)
    assert sum(phases.values()) == roots
    return {'native_report_sha256': base.sha(path), 'all_stack_samples': roots,
            'non_idle_samples': active_samples, 'phase_exclusive_samples': dict(phases),
            'leaf_operation_exclusive_samples': dict(operations),
            'top_active_leaf_symbols': leaves.most_common(35),
            'graph_coverage_observed': phases['graph_construction'] > 0,
            'time_distribution_is_sampling_estimate_not_latency_or_hardware_counters': True,
            'phase_classification_uses_native_ancestor_symbols_and_has_unclassified_samples': True}


def main():
    """核对所有实际调用、完整输入和工具终态，再汇总精确与未知边界。"""
    base.static_check()
    modes = ['baseline', 'timers', 'memory', 'sample', 'depth', 'sample2', 'sample_aligned']
    costs = Counter()
    rows = []
    for mode in modes:
        result = base.read(_project_file(_PROJECT_ROOT, HERE / ('actual-' + mode) / 'CLOSURE.json'))
        assert result['full_math_exact'] and not result['issues'], mode
        assert result['capture']['terminal']['terminal_valid'], mode
        assert result['source_and_production_changes'] == 0
        costs.update(result['actual_costs'])
        rows.extend(dict(row, mode=mode) for row in result['rows'])
    assert len(rows) == 9
    assert costs['rule_attempts'] == costs['choose_attempts'] == costs['direct_score_attempts'] == 9
    assert costs['failed_score_attempts'] == costs['reference_score_attempts'] == 0
    tools = base.read(_project_file(_PROJECT_ROOT, HERE / 'ACTUAL-TOOLS.json'))
    for mode, receipt in tools.items():
        terminals = [receipt.get('terminal'), receipt.get('launch')] + receipt.get('polls', [])
        assert any(value and value.get('exit_code') == 0 for value in terminals), mode
    sample = native_summary(_project_file(_PROJECT_ROOT, HERE / 'actual-sample_aligned/NATIVE-SAMPLE.txt'))
    base.save(_project_file(_PROJECT_ROOT, HERE / 'NATIVE-SAMPLE-READBACK.json'), sample)
    memory = base.read(_project_file(_PROJECT_ROOT, HERE / 'actual-memory/MEMORY-GC.json'))
    depth = base.read(_project_file(_PROJECT_ROOT, HERE / 'actual-depth/CONSTRUCTOR-STATEMENTS.json'))
    gc_events = depth['gc_events_without_tracemalloc']
    timers = base.read(_project_file(_PROJECT_ROOT, HERE / 'actual-depth/FUNCTION-TIMERS.json'))['per_case'][0]['rows']
    baseline = next(row for row in rows if row['mode'] == 'baseline')
    summary = {'schema': 't127-precision-diagnosis-stage/1',
        'actual_costs': dict(costs), 'all_nine_complete_inputs_scores_traces_operations_exact': True,
        'new_algorithm_optimizations_authors_worlds_tables': 0,
        'uninstrumented_baseline': baseline,
        'deep_selected_boundaries': timers,
        'statement_hotspots': sorted(depth['segments'].items(), key=lambda item: -item[1]['inclusive_ns']),
        'traced_memory_boundaries': [{key: value for key, value in row.items() if key != 'top_retained_or_net_differences'} for row in memory['boundaries']],
        'gc_without_tracemalloc': {'collections': len(gc_events),
            'total_pause_seconds': sum(row['duration_ns'] or 0 for row in gc_events) / 1e9,
            'max_pause_seconds': max(row['duration_ns'] or 0 for row in gc_events) / 1e9},
        'native_sampling': sample,
        'first_native_sample_exit255_preserved': True,
        'second_native_sample_coverage_insufficient_preserved': True,
        'hardware_cache_miss_instruction_bandwidth_counters': 'not_measured',
        'latency_improvement_claim': False, 'deadline_admission': False, 'online_admission': False,
        'goal_was_paused_at_readback_no_automatic_evolution_resumed': True}
    base.save(_project_file(_PROJECT_ROOT, HERE / 'STAGE-CLOSURE.json'), summary)
    print(json.dumps({'closed': True, 'actual_complete_scores': 9,
        'native_samples': sample['all_stack_samples'], 'non_idle_samples': sample['non_idle_samples'],
        'phase_samples': sample['phase_exclusive_samples'],
        'operation_samples': sample['leaf_operation_exclusive_samples']}))


if __name__ == '__main__':
    main()
