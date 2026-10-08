"""T19 同输入机械检查：复用245个已登记窗口及真父缓存，不重跑父评分。

prepare只读公开原件并冻结来源；execute用唯一规则实现重建精确typed
view，先完整保存，再真实评分。重复窗口仍占独立执行槽，不视为独立母根。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t19-same-input-mechanics-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t19-maintained-ready-choice-author-1')
T17 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t17-public-interruption-trade-author-1')
DIAG = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t18-natural-outcome-and-three-white-diagnostic-1')
PARENT_CID = 'b198e694fb46bb95cfac31b0d14a08744e018efb5f0966034b4015a31b05f655'


def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def read(path):
    return json.loads(path.read_bytes())


def pin(path):
    raw = path.read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def write(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canon(value) + b'\n')


def views(paths, wanted):
    """流式只留登记输入的完整原DTO；重复同SHA须逐字相等。"""
    found = {}
    for path in paths:
        with gzip.open(path, 'rt') as stream:
            for line in stream:
                row = json.loads(line)
                sha = row['view_sha256']
                if sha not in wanted:
                    continue
                dto = row.get('view', row.get('candidate_view'))
                assert hashlib.sha256(canon(dto)).hexdigest() == sha
                if sha in found:
                    assert canon(found[sha]) == canon(dto)
                else:
                    found[sha] = dto
    assert set(found) == wanted
    return found


def prepare():
    """按冻结的160旧窗口和85真实当前胡窗口原顺序登记，零业务调用。"""
    slots, files, view_files = [], {}, []

    def bind(path):
        path = path.resolve()
        files[str(path)] = pin(path)
        return path

    for group in ('S01-cross-source-probe-1', 'S01-new-A-probe-1'):
        directory = _project_file(_PROJECT_ROOT, T17 / group)
        manifest = read(bind(directory / 'manifest.json'))
        panel_path = bind(Path(manifest['panel_path']))
        panel = read(panel_path)
        cache = {}
        with bind(directory / 'results.jsonl').open() as stream:
            for line in stream:
                row = json.loads(line)
                if row['candidate_id'] != PARENT_CID:
                    continue
                assert row['status'] == 'scored'
                assert row['view_sha256_before'] == row['view_sha256_after']
                assert row['input_sha256'] not in cache
                cache[row['input_sha256']] = row
        assert len(cache) == len(panel['windows'])
        view_files.append(bind(directory / 'views.jsonl.gz'))
        bind(directory / 'RAW-FIRST-SEAL.json')
        for index, item in enumerate(panel['windows']):
            row = cache[item['input_sha256']]
            values = {e['action_key']: e['score'] for e in row['entries']}
            assert set(values) == set(item['legal_action_keys'])
            assert row['ordered_action_keys'] == sorted(values, key=lambda k: (-values[k], k))
            slots.append({'slot_no': len(slots) + 1, 'source_group': group,
                'source_index': index, 'observation': item['observation'],
                'window_key': item['window_key'], 'view_sha256': row['view_sha256_before'],
                'cached_parent_scores': values, 'cached_parent_first': row['preferred_action_key'],
                'source_input_sha256': item['input_sha256'], 'source_origins': row['origins']})
    assert len(slots) == 160
    current = read(bind(_project_file(_PROJECT_ROOT, DIAG / 'ALL-C-CURRENT-HU-PUBLIC-INPUTS.json')))
    assert len(current['rows']) == 85
    for index, row in enumerate(current['rows']):
        assert row['input_capture']['saved_before_score']
        values = {e['action_key']: e['score'] for e in row['actual_scored_candidates']}
        assert set(values) == set(row['all_legal_action_keys'])
        assert sorted(values, key=lambda k: (-values[k], k))[0] == row['selected_action_key']
        slots.append({'slot_no': len(slots) + 1, 'source_group': 'all_actual_T17_current_Hu',
            'source_index': index, 'observation': row['public_observation'],
            'window_key': row['window_key'], 'view_sha256': row['input_capture']['view_sha256'],
            'cached_parent_scores': values, 'cached_parent_first': row['selected_action_key'],
            'source_origins': {k: row[k] for k in ('pool', 'root_id', 'permutation', 'round_no',
                'source_file', 'source_line', 'source_line_sha256')}})
    view_files.append(bind(_project_file(_PROJECT_ROOT, T17 / 'S01-natural-development-64/views.jsonl.gz')))
    bind(_project_file(_PROJECT_ROOT, E / 't17-natural-closure-2/AUDIT.json'))
    bind(_project_file(_PROJECT_ROOT, E / 't17-natural-closure-2/RAW-FIRST-SEAL.json'))
    for name in ('S01-generation.batch.json', 'EVALUATION-PLAN.json'):
        bind(_project_file(_PROJECT_ROOT, AUTHOR / name))
    bind(_project_file(_PROJECT_ROOT, T17 / 'S01-model-output/candidate.py'))
    bind(_project_file(_PROJECT_ROOT, T17 / 'S01-model-output/generation.json'))
    bind(Path(__file__))
    wanted = {s['view_sha256'] for s in slots}
    original = views(view_files, wanted)
    assert len(slots) == 245
    for slot in slots:
        assert set(slot['cached_parent_scores']) == {a['action_key'] for a in original[slot['view_sha256']]['actions']}
    write('SLOTS.json', slots)
    bind(_project_file(_PROJECT_ROOT, HERE / 'SLOTS.json'))
    write('PREPARED.json', {'schema': 't19-same-input-mechanical-prepared/1',
        'status': 'prepared_zero_business_calls', 'files': files,
        'view_files': [str(p) for p in view_files], 'window_slots': 245,
        'unique_inputs': len(wanted), 'planned_child_scores': 245, 'new_parent_scores': 0,
        'cached_parent_scores': 245, 'max_operations': 2400000,
        'wall_clock_seconds': 1200,
        'capture_limits': {'max_unique_views': 245, 'max_view_json_bytes': 64*1024**2,
                           'max_total_json_bytes': 2*1024**3},
        'selection': 'all registered 160 old panel windows plus all 85 actual T17 root-current-Hu windows; no outcome filtering',
        'protected': 'no root legal Hu OR current zero whites: all numeric scores equal actual parent',
        'parent_candidate_id': PARENT_CID, 'candidate_package': str((_project_file(_PROJECT_ROOT, AUTHOR/'S01-model-output')).resolve()),
        'rule_calls': 0, 'projection_calls': 0, 'world_calls': 0, 'model_calls': 0,
        'review': 'same typed contract and production capture; root ordinary checks; no new independent review',
        'not_confirmation_or_release': True})
    print(json.dumps({'status': 'prepared', 'slots': 245, 'unique_inputs': len(wanted),
                      'business_calls': 0}))


def execute():
    """全245槽真实子代评分；失败保留原槽，父旧分明示缓存，不复评分。"""
    prepared = read(_project_file(_PROJECT_ROOT, HERE / 'PREPARED.json'))
    start = read(_project_file(_PROJECT_ROOT, HERE / 'ROOT-START.json'))
    assert start['status'] == 'START' and start['prepared_sha256'] == pin(_project_file(_PROJECT_ROOT, HERE/'PREPARED.json'))['sha256']
    for path, expected in {**prepared['files'], **start['candidate_files']}.items():
        assert pin(Path(path)) == expected, path
    from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents
    from hangma_bot.offline.scoring_input_capture import ScoringInputCapture, ScoringInputCaptureLimits
    from hangma_bot.policy.action_value_executor import ActionValueExecutor
    from hangma_bot.hangma.engine import HangmaRules
    from hangma_bot.kernel.serialization import observation_from_json, window_key_from_json
    from hangma_bot.kernel.observation import CompetitionContext
    from hangma_bot.policy.interface import DecisionRequest
    from hangma_bot.policy.route_vip_heuristic import build_vip_route_scoring_view
    batch = VipEohBatch.read(_project_file(_PROJECT_ROOT, AUTHOR / 'S01-generation.batch.json'))
    child = load_vip_parents([Path(prepared['candidate_package'])], batch)[0]
    assert child['identity']['candidate_id'] == start['candidate_id']
    assert [p['identity']['candidate_id'] for p in read(Path(prepared['candidate_package'])/'generation.json')['parents']] == [PARENT_CID]
    executor = ActionValueExecutor(child['source'], max_operations=batch.max_operations)
    rules = HangmaRules(batch.rule_config)
    slots = read(_project_file(_PROJECT_ROOT, HERE / 'SLOTS.json'))
    original = views([Path(p) for p in prepared['view_files']], {s['view_sha256'] for s in slots})
    began = time.monotonic()
    counters = {'dispatched': 0, 'rules_analyze': 0, 'projections': 0, 'scored': 0}
    completed, errors = [], []
    with (_project_file(_PROJECT_ROOT, HERE/'views.jsonl.gz')).open('x+b') as view_stream, (_project_file(_PROJECT_ROOT, HERE/'SCORES.jsonl')).open('xb') as stream:
        capture = ScoringInputCapture(view_stream, limits=ScoringInputCaptureLimits(**prepared['capture_limits']))
        try:
            for slot in slots:
                if time.monotonic()-began >= prepared['wall_clock_seconds']:
                    raise RuntimeError('registered_wall_clock_budget')
                row = {'slot_no': slot['slot_no'], 'source_group': slot['source_group'],
                       'source_index': slot['source_index'], 'view_sha256': slot['view_sha256'],
                       'cached_parent_scores': slot['cached_parent_scores'],
                       'cached_parent_first': slot['cached_parent_first'], 'status': 'dispatched'}
                stream.write(canon(row)+b'\n'); stream.flush(); counters['dispatched'] += 1
                try:
                    obs = observation_from_json(slot['observation'])
                    window = window_key_from_json(slot['window_key'])
                    counters['rules_analyze'] += 1
                    analysis = rules.analyze(obs, route_limits=batch.route_limits)
                    request = DecisionRequest(obs, CompetitionContext('t19-same-input-mechanics/1', None, None, None,
                        None, (), 0), analysis, 't19-probe:'+str(slot['slot_no']), window.trigger_seq, window, ())
                    counters['projections'] += 1
                    typed = build_vip_route_scoring_view(request, batch.rule_config, limits=batch.projection_limits)
                    dto = typed.candidate_view()
                    assert canon(dto) == canon(original[slot['view_sha256']]), 'exact typed DTO reconstruction mismatch'
                    receipt = capture.store(dto)
                    row['input_capture'] = asdict(receipt)
                    assert receipt.saved_before_score and receipt.view_sha256 == slot['view_sha256']
                    tick = time.monotonic()
                    result = executor.score_vip_route(typed)
                    row['score_monotonic_seconds'] = time.monotonic()-tick
                    assert result.status == 'SCORED'
                    values = {entry.action_key: entry.score for entry in result.entries}
                    assert set(values) == set(slot['cached_parent_scores'])
                    assert all(math.isfinite(value) for value in values.values())
                    assert executor.last_operation_count <= prepared['max_operations']
                    assert hashlib.sha256(canon(typed.candidate_view())).hexdigest() == slot['view_sha256']
                    counters['scored'] += 1
                    order = sorted(values, key=lambda k: (-values[k], k))
                    ctx, white = dto['visible_state'], dto['tile_order'][-1]
                    whites = ctx['my_hand'].count(white) + int(ctx['drawn_tile'] == white)
                    current_hu = any(a['action_key'] == 'hu' for a in dto['actions'])
                    protected = not current_hu or whites == 0
                    assert not protected or values == slot['cached_parent_scores'], 'pointwise protected input changed'
                    if current_hu:
                        assert values['hu'] == slot['cached_parent_scores']['hu'], 'immediate Hu payment score changed'
                    row.update(status='scored', scores=values, entries=[{'action_key': e.action_key,
                        'score': e.score, 'trace': dict(e.trace)} for e in result.entries],
                        operations=executor.last_operation_count, first=order[0], current_hu=current_hu,
                        white_count=whites, wall_remaining=ctx['remaining_tile_count'], protected=protected,
                        score_changed=values != slot['cached_parent_scores'],
                        first_changed=order[0] != slot['cached_parent_first'])
                    completed.append(row)
                except BaseException as exc:
                    row.update(status='failed_original_slot_retained', error=type(exc).__name__+': '+str(exc),
                               operations=executor.last_operation_count)
                    errors.append({k: row[k] for k in ('slot_no', 'status', 'error')})
                stream.write(canon(row)+b'\n'); stream.flush()
        finally:
            capture.finish()
            costs = capture.costs
            write('CAPTURE-COSTS.json', costs)
    files_stable = all(pin(Path(p)) == expected for p, expected in {**prepared['files'], **start['candidate_files']}.items())
    result = {'schema': 't19-same-input-mechanical-result/1',
        'status': 'closed_not_strength_confirmation' if not errors and files_stable and costs['terminal']['terminal_valid'] else 'failed_slots_retained',
        'candidate_id': child['identity']['candidate_id'], 'parent_candidate_id': PARENT_CID,
        'planned_slots': 245, 'completed_slots': len(completed), 'failed_slots': errors,
        'actual_calls': counters, 'new_parent_scores': 0, 'cached_parent_score_slots': 245,
        'world_calls': 0, 'model_calls': 0, 'files_stable': files_stable,
        'max_operations_observed': max((r['operations'] for r in completed), default=0),
        'protected_slots': sum(r['protected'] for r in completed),
        'score_changed_slots': sum(r['score_changed'] for r in completed),
        'first_changed_slots': sum(r['first_changed'] for r in completed),
        'changed_choices': [{k: r[k] for k in ('slot_no','source_group','source_index','cached_parent_first',
            'first','white_count','wall_remaining')} for r in completed if r['first_changed']],
        'elapsed_monotonic_seconds': time.monotonic()-began,
        'capture_terminal': costs['terminal'], 'scores_file': pin(_project_file(_PROJECT_ROOT, HERE/'SCORES.jsonl')),
        'no_independence_or_strength_claim': True, 'new_independent_reviews': 0}
    write('RESULT.json', result)
    print(json.dumps({k: result[k] for k in ('status','completed_slots','failed_slots','protected_slots',
        'first_changed_slots','score_changed_slots','max_operations_observed','elapsed_monotonic_seconds')}))
    assert result['status'] == 'closed_not_strength_confirmation', 'mechanical batch incomplete'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare','execute'])
    mode = parser.parse_args().mode
    prepare() if mode == 'prepare' else execute()
