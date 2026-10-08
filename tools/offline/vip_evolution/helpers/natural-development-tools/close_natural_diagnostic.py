"""整批自然终态后只读配对32桌；不评分、不续桌、不读取confirmation。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = '.private/t199-four-step-execution/natural-development-tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

from collections import Counter
import fcntl
import gzip
import json
from pathlib import Path
import statistics

from common import HERE, ROOT, PLAN, pin, save, unchanged, true_degradations


def read(path):
    """原件严格JSON；只能在整批controller自然闭合后调用此诊断。"""
    return json.loads(Path(path).read_text())


def metrics(closed):
    """焦点座位实际结算；支付为正数，庄闲指该单局自家座位身份。"""
    task = closed['task']; own = task['focal_physical_seat']; result = Counter()
    result.update({key: 0 for key in (
        'hands', 'net', 'gross_income', 'gross_payment', 'ordinary_hu', 'high_fan_hu',
        'ordinary_income', 'high_fan_income', 'ordinary_payment', 'high_fan_payment',
        'draws', 'dealer_hands', 'nondealer_hands', 'dealer_net', 'nondealer_net',
        'dealer_hu', 'nondealer_hu', 'dealer_income', 'nondealer_income',
        'dealer_payment', 'nondealer_payment', 'payment_to_dealer', 'payment_to_nondealer')})
    previous = list(task['initial_scores'])
    assert len(closed['natural_settlements']) == 8
    for round_no, row in enumerate(closed['natural_settlements'], 1):
        assert row['evidence'] == 'public_export_hand_settlement'
        assert row['focal_physical_seat'] == own and row['root_id'] == task['root_id']
        settle = row['settlement']; delta = settle['score_delta'][own]
        assert settle['round_no'] == round_no and settle['coverage'] == 'settlement_only'
        assert settle['scores_before'] == previous and sum(settle['score_delta']) == 0
        assert [before + value for before, value in zip(previous, settle['score_delta'])] == settle['scores_after']
        previous = settle['scores_after']; result['hands'] += 1; result['net'] += delta
        position = 'dealer' if own == settle['dealer_seat'] else 'nondealer'
        result[position + '_hands'] += 1; result[position + '_net'] += delta
        result['gross_income'] += max(delta, 0); result['gross_payment'] += max(-delta, 0)
        result[position + '_income'] += max(delta, 0); result[position + '_payment'] += max(-delta, 0)
        if settle['is_draw']:
            assert settle['winner_seat'] is None and not any(settle['score_delta'])
            result['draws'] += 1
            continue
        assert type(settle['fan']) is int and settle['fan'] >= 1
        kind = 'ordinary' if settle['fan'] < 4 else 'high_fan'
        if settle['winner_seat'] == own:
            assert delta > 0
            result[kind + '_hu'] += 1; result[kind + '_income'] += delta; result[position + '_hu'] += 1
        else:
            assert delta <= 0
            result[kind + '_payment'] += -delta
            result['payment_to_dealer' if settle['winner_seat'] == settle['dealer_seat'] else 'payment_to_nondealer'] += -delta
    assert previous == closed['final_scores_seat_order_0_1_2_3']
    assert result['net'] == previous[own] - task['initial_scores'][own]
    assert result['net'] == result['gross_income'] - result['gross_payment']
    assert result['net'] == result['ordinary_income'] + result['high_fan_income'] - result['ordinary_payment'] - result['high_fan_payment']
    return dict(result)


def verified_receipt(path, task, plan_pin):
    """逐桌已发生的完整R8和原件pin；不将prefix或失败计作完整桌。"""
    closed = read(path)
    assert closed['complete'] is True and closed['task'] == task and closed['plan_pin'] == plan_pin
    assert closed['source_and_map_stable'] is True and closed['started_table_instances'] == 1
    assert closed['completed_hands'] == 8 and closed['outcome_status'] == 'complete'
    assert all(type(value) is int and value == 0 for value in closed['runtime_counts'].values())
    assert closed['scoring_failed_calls'] == closed['audit_sink_failed_calls'] == 0
    terminal = closed['capture']['terminal']
    assert terminal['terminal_valid'] is True
    assert all(pin(path.parent / name) == expected for name, expected in closed['raw_files'].items())
    return closed


def audited_choices(path, closed, plan):
    """流式核实际全座行和A根改选；parent_first只表示同输入父排序，不是新P0续打。"""
    count = focal_count = 0; changes = []; scopes = Counter(); information = Counter()
    own = closed['task']['focal_physical_seat']
    with gzip.open(path, 'rt') as stream:
        for line in stream:
            row = json.loads(line); count += 1
            assert row['status'] == 'chosen' and row['selected_action_key'] in row['legal_action_keys']
            assert row['original_reasons_preserved'] is True and not row['true_degradation_reasons']
            assert not true_degradations(row['degraded_reasons'], row['policy_id'], plan,
                focal=row['seat'] == own, observation=row['observation'])
            obs = row['observation']
            assert all(event['seq'] <= obs['consumed_seq'] for event in obs['public_history'])
            assert all(not event['tiles'] for event in obs['public_history']
                if event['kind'] == 'tile_drawn' and event['seat'] != obs['seat'])
            if row['seat'] != own:
                information.update(row['degraded_reasons']); continue
            focal_count += 1
            assert row['policy_id'] == plan['focal_policy_id'] and row['c_self_scored'] is True
            assert len(row['scoring_calls']) == 1
            call = row['scoring_calls'][0]
            assert call['actual_score_calls'] == 1 and call['score_completed'] is True and call['full_legal_keys'] is True
            first = row['candidates'][0]; trace = first['trace']; order = trace['root_selection']
            assert trace['t199_binding_id'] == plan['binding_id'] and trace['scoring_branch'] == 'parent'
            assert order['selected_first'] == row['selected_action_key']
            assert type(order['applied']) is bool and order['applied'] == (order['parent_first'] != order['selected_first'])
            scopes[order['scope']] += 1
            if order['applied']:
                parent = next(c for c in row['candidates'] if c['action_key'] == order['parent_first'])
                assert parent['score'] == first['score'] == order['top_score']
                assert order['graph_choices'] == 'parent_inherited'
                changes.append({'table_no': closed['task']['table_no'], 'root_id': closed['task']['root_id'],
                    'rotation': closed['task']['rotation'], 'seat': own, 'window_key': row['window_key'],
                    'decision_id': row['decision_id'], 'parent_first': order['parent_first'],
                    'selected_first': order['selected_first'], 'scope': order['scope'], 'equal_score': first['score'],
                    'input_capture': call['input_capture'], 'graph_choices': order['graph_choices']})
    assert count == closed['all_seat_window_count'] and focal_count == closed['focal_score_calls']
    return count, focal_count, changes, scopes, information


def main():
    """只在原32全自然closed后汇总；保存不覆盖，失败不启动新计算桌。"""
    # 第一读仅为全批终态，任何未闭合都在读取桌成绩前失败。
    controller = read(_project_file(_PROJECT_ROOT, HERE / 'CONTROLLER-CLOSED.json')); pilot = read(_project_file(_PROJECT_ROOT, HERE / 'PILOT-CLOSED.json'))
    assert controller['complete'] is True and pilot['complete'] is True
    assert controller['all_our_worker_slots_released'] and pilot['all_our_worker_slots_released']
    assert not (_project_file(_PROJECT_ROOT, HERE / 'STOP-NEW-TABLES.json')).exists()
    plan = read(PLAN); plan_pin = pin(PLAN)
    assert controller['plan_pin'] == pilot['plan_pin'] == plan_pin and unchanged(plan)
    assert controller['planned_table_instances'] == 31 and pilot['planned_table_instances'] == 1
    composite = Path(plan['composite_origins_path'])
    assert pin(composite) == plan['composite_origins_pin'] and read(composite)['complete'] is True
    worker_rows = []
    for path in sorted((_project_file(_PROJECT_ROOT, HERE / 'workers')).glob('*/CLOSED.json')):
        row = read(path)
        assert row['complete'] and row['slot_released'] and row['priorities']['nice_actual'] == 19
        assert row['priorities']['io_policy_actual'] == 3 and row['priorities']['low_IO_actual'] is True
        worker_rows.append({'path': str(path), 'pin': pin(path), 'pid': row['pid'], 'priorities': row['priorities']})
    assert len(worker_rows) == 5
    slots = []
    # 仅只读探测原共享槽已释放；若其它任务已取得槽，记录busy而不阻挡其工作。
    for path in plan['slot_paths']:
        with open(path, 'r') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(stream, fcntl.LOCK_UN)
                slots.append({'path': path, 'free_at_probe': True})
            except BlockingIOError:
                slots.append({'path': path, 'free_at_probe': False, 'scope': 'possibly_other_research_owner; our terminal receipts prove release'})
    totals = {'candidate': Counter(), 'reference': Counter()}; tables = []; roots = {}; changes = []
    counts = Counter(); scopes = Counter(); information = Counter(); inputs = {str(PLAN): plan_pin,
        str(composite): pin(composite), str(_project_file(_PROJECT_ROOT, HERE / 'PILOT-CLOSED.json')): pin(_project_file(_PROJECT_ROOT, HERE / 'PILOT-CLOSED.json')),
        str(_project_file(_PROJECT_ROOT, HERE / 'CONTROLLER-CLOSED.json')): pin(_project_file(_PROJECT_ROOT, HERE / 'CONTROLLER-CLOSED.json'))}
    for task in plan['tasks']:
        no = task['table_no']; path = _project_file(_PROJECT_ROOT, HERE / 'tables' / f'table-{no:04d}' / 'CLOSED.json')
        candidate = verified_receipt(path, task, plan_pin)
        assert candidate['candidate_binding_id'] == plan['binding_id'] and candidate['selected_variant'] == 'A-H0'
        assert candidate['forced_first_actions'] == 0 and candidate['natural_full_table'] is True
        loaded = candidate['loaded_paths']
        assert loaded['t199_natural_comparator'] == plan['comparator']['path']
        assert all(Path(value).resolve().is_relative_to(_project_file(_PROJECT_ROOT, ROOT / 'src'))
            for name, value in loaded.items() if name == 'hangma_bot' or name.startswith('hangma_bot.'))
        for name in ('runtime_policy', 't199_natural_comparator', 't199_natural_measurement'):
            assert loaded[name] in plan['files'] and pin(loaded[name]) == plan['files'][loaded[name]]
        origin = plan['composite_references'][str(no)]; reference_path = Path(origin['closed_path'])
        origin_plan_path = Path(origin['origin_plan_path'])
        assert pin(reference_path) == origin['closed_pin'] and pin(origin_plan_path) == origin['origin_plan_pin']
        origin_plan = read(origin_plan_path)
        for field in ('candidate_identity', 'compiled_runtime', 'rules_source_hash', 'runtime_files', 'tasks', 'roots', 'compositions'):
            assert origin_plan[field] == plan[field], field
        assert origin['task'] == task
        reference = verified_receipt(reference_path, task, origin['origin_plan_pin'])
        current = metrics(candidate); baseline = metrics(reference)
        delta = {key: current[key] - baseline[key] for key in current}
        windows, focal, actual_changes, row_scopes, notes = audited_choices(path.parent / 'decisions.jsonl.gz', candidate, plan)
        counts['all_seat_windows'] += windows; counts['focal_score_calls'] += focal
        scopes.update(row_scopes); information.update(notes); changes.extend(actual_changes)
        for arm, result in (('candidate', current), ('reference', baseline)): totals[arm].update(result)
        row = {'table_no': no, 'task': task, 'candidate': current, 'reference': baseline, 'delta': delta,
            'actual_root_changes': len(actual_changes), 'candidate_closed_path': str(path), 'candidate_closed_pin': pin(path),
            'reference_closed_path': str(reference_path), 'reference_closed_pin': pin(reference_path),
            'candidate_raw_files': candidate['raw_files'], 'reference_raw_files': reference['raw_files'],
            'actual_loaded_comparator': loaded['t199_natural_comparator'], 'all_seat_windows': windows, 'focal_score_calls': focal}
        tables.append(row); roots.setdefault(task['root_id'], []).append(row)
        inputs[str(path)] = pin(path); inputs[str(reference_path)] = pin(reference_path)
    assert len(tables) == 32 and len(roots) == 8 and all(len(rows) == 4 for rows in roots.values())
    mothers = []
    for root_id, rows in sorted(roots.items()):
        assert sorted(row['task']['rotation'] for row in rows) == [0, 1, 2, 3]
        mother = {'root_id': root_id, 'table_nos': [row['table_no'] for row in rows],
            'focal_seats': [row['task']['focal_physical_seat'] for row in rows], 'actual_root_changes': sum(row['actual_root_changes'] for row in rows)}
        for arm in ('candidate', 'reference', 'delta'):
            summed = {key: sum(row[arm][key] for row in rows) for key in totals['candidate']}
            mother[arm + '_sum_four_tables'] = summed
            mother[arm + '_mean_per_table'] = {key: value / 4 for key, value in summed.items()}
        mothers.append(mother)
    total_delta = {key: totals['candidate'][key] - totals['reference'][key] for key in totals['candidate']}
    net_mothers = [row['delta_mean_per_table']['net'] for row in mothers]
    estimate = statistics.mean(net_mothers); sem = statistics.stdev(net_mothers) / (8 ** .5)
    summary = {'schema': 't199-A-H0-fixed-natural-development-closed/1', 'complete': True,
        'plan_path': str(PLAN), 'plan_pin': plan_pin, 'binding_id': plan['binding_id'], 'selected_variant': 'A-H0',
        'candidate_identity': plan['candidate_identity'], 'compiled_runtime': plan['compiled_runtime'],
        'parent_execution_id': plan['parent_execution_id'], 'runtime_root': str(ROOT), 'rules_source_hash': plan['rules_source_hash'],
        'selected_source': plan['selected_source'], 'comparator': plan['comparator'],
        'actual_tables': 32, 'pilot_reused_tables': 1, 'remaining_tables': 31, 'actual_completed_hands': 256,
        'focal_score_calls': counts['focal_score_calls'], 'all_seat_windows': counts['all_seat_windows'],
        'reference_rescores': 0, 'forced_first_actions': 0, 'all_our_worker_slots_released': True,
        'slot_release_probe': slots, 'worker_receipts': worker_rows, 'source_and_map_stable': unchanged(plan),
        'runtime_counts': {key: 0 for key in plan['zero_runtime_counts_required']},
        'ordinary_definition': '自家自然胡fan<4；非draw', 'high_fan_definition': '自家自然胡fan>=4',
        'payment_definition': '自家score_delta负值的绝对值；按实际赢家fan及庄闲分账，不推测点炮/自摸来源',
        'dealer_definition': '各单局public settlement.dealer_seat==焦点实际座位；自家身份与赢家身份分别记账',
        'totals_32_tables': {**{key: dict(value) for key, value in totals.items()}, 'delta': total_delta},
        'paired_mother_summary': {'independent_unit': '预冻结母样本；每母4换座平均，n=8', 'n': 8,
            'mean_net_delta_per_table': estimate, 'median_mother_net_delta': statistics.median(net_mothers),
            'positive_mothers': sum(value > 0 for value in net_mothers), 'negative_mothers': sum(value < 0 for value in net_mothers),
            'zero_mothers': sum(value == 0 for value in net_mothers), 'descriptive_standard_error': sem,
            'descriptive_t95_interval_df7': [estimate - 2.364624251 * sem, estimate + 2.364624251 * sem],
            'interval_assumption': '母样本独立及配对差均值近似t；小型固定开发诊断，不用于候选优胜/发布',
            'leave_one_mother_out_mean_range': [min((sum(net_mothers)-value)/7 for value in net_mothers), max((sum(net_mothers)-value)/7 for value in net_mothers)]},
        'mothers': mothers, 'tables': tables, 'actual_root_change_count': len(changes),
        'actual_changed_tables': sum(row['actual_root_changes'] > 0 for row in tables), 'scope_counts': dict(scopes),
        'original_opponent_information_notes_retained_counts': dict(information), 'actual_changes': changes,
        'paired_table_net_tails_descriptive_only': [{key: row[key] for key in ('table_no','delta','actual_root_changes')}
            for row in sorted(tables, key=lambda item: abs(item['delta']['net']), reverse=True)[:5]],
        'input_receipt_pins': inputs, 'close_script_pin': pin(Path(__file__)),
        'strength_admission': False, 'original_deadline_admitted': False, 'real_HTTP_admitted': False,
        'expansion_16_32_or_confirmation_allowed': False, 'HTTP_calls': 0, 'LLM_calls': 0,
        'qualification': '原固定8母×4换座、A-H0自然完整单臂诊断；不据中途/单桌/尾部选新源或扩样；与已保存P0完整桌配对，未做确认池'}
    assert summary['source_and_map_stable'] and totals['candidate']['hands'] == totals['reference']['hands'] == 256
    assert total_delta['net'] == total_delta['ordinary_income'] + total_delta['high_fan_income'] - total_delta['ordinary_payment'] - total_delta['high_fan_payment']
    save(_project_file(_PROJECT_ROOT, HERE / 'NATURAL-DIAGNOSTIC-CLOSED.json'), summary)
    print(json.dumps({'complete': True, 'tables': 32, 'hands': 256, 'net_delta_sum': total_delta['net'],
        'mother_mean_net_delta_per_table': estimate, 'ordinary_hu_delta': total_delta['ordinary_hu'],
        'high_fan_hu_delta': total_delta['high_fan_hu'], 'actual_root_changes': len(changes),
        'focal_score_calls': counts['focal_score_calls'], 'all_seat_windows': counts['all_seat_windows'],
        'slots_released': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
