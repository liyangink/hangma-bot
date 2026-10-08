"""T22 同输入机械检查：复用245窗口及8实际起点，读T19真父缓存，不重跑父评分。

prepare只读公开原件并冻结来源；execute用唯一规则实现重建精确typed
view，先完整保存，再真实评分。重复窗口仍占独立执行槽，不视为独立母根。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t22-same-input-mechanics-2'

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
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t22-claim-route-opportunity-author-1')
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t19-same-input-mechanics-1')
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t19-maintained-ready-choice-author-1/S01-model-output')
T17 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t17-public-interruption-trade-author-1')
DIAG = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t18-natural-outcome-and-three-white-diagnostic-1')
PARENT_CID = '4d5a5ca4dcf513de941f35212ce63445c1db0c1caf51050f196f53638754d341'


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
    """纯读245完整观察与8实际起点、真T19缓存；不伪造后续typed输入。"""
    files = {}
    def bind(path):
        path = path.resolve(); files[str(path)] = pin(path); return path
    old_result = read(bind(_project_file(_PROJECT_ROOT, OLD / 'RESULT.json')))
    assert old_result['status'] == 'closed_not_strength_confirmation'
    assert old_result['candidate_id'] == PARENT_CID and old_result['completed_slots'] == 245
    cache = {}
    with bind(_project_file(_PROJECT_ROOT, OLD / 'SCORES.jsonl')).open() as stream:
        for line in stream:
            row = json.loads(line)
            if row['status'] == 'scored':
                assert row['slot_no'] not in cache; cache[row['slot_no']] = row
    slots = read(bind(_project_file(_PROJECT_ROOT, OLD / 'SLOTS.json')))
    assert len(cache) == len(slots) == 245
    for slot in slots:
        cached = cache[slot['slot_no']]
        assert cached['view_sha256'] == slot['view_sha256']
        slot['cached_parent_scores'] = cached['scores']
        slot['cached_parent_first'] = cached['first']
        slot['cache_candidate_id'] = PARENT_CID
    view_files = [bind(_project_file(_PROJECT_ROOT, OLD / 'views.jsonl.gz'))]
    for name in ('t20-early-tie-causal', 't21-early-strict-choice-causal'):
        directory = _project_file(_PROJECT_ROOT, E / (name + '-preparation-1'))
        closed = read(bind(_project_file(_PROJECT_ROOT, E / (name + '-closure-1') / 'ROOT-CLOSED-CHECK.json')))
        assert closed['status'] == 'accepted_engineering_only' and closed['complete_single_hand_continuations'] == 40
        plan = read(bind(directory / 'PREPARED.json'))
        bind(directory / 'COSTS-AND-RESULT.json')
        view_files.append(bind(directory / 'views.jsonl.gz'))
        targets = {}
        with bind(directory / 'calls-and-choices.jsonl').open() as stream:
            for line in stream:
                row = json.loads(line)
                if row['event'] == 'score_call' and row['arm'] == 'Sol-C' and row['variant'] == 'original_C_start':
                    root = next(r for r in plan['roots'] if r['root_id'] == row['root_id'])
                    if row['window_key'] == root['source']['target_window']:
                        targets[row['root_id']] = row
        assert len(targets) == 4
        for index, root in enumerate(plan['roots']):
            source = root['source']; row = targets[root['root_id']]
            assert row['input_capture']['saved_before_score']
            assert row['input_capture']['view_sha256'] == source['source_C_full_DTO_sha256']
            original = next(r for r in source['target_frame'] if r['window_key'] == source['target_window'])
            values = {e['action_key']:e['score'] for e in row['scores']['entries']}
            assert values == source['source_C_cached_scores'] and 'hu' not in values
            assert set(values) == set(original['legal_action_keys'])
            slots.append({'slot_no':len(slots)+1,'source_group':name+'_actual_initial', 'source_index':index,
                'observation':original['observation'],'window_key':original['window_key'],
                'view_sha256':row['input_capture']['view_sha256'], 'cached_parent_scores':values,
                'cached_parent_first':row['ranking'][0], 'cache_candidate_id':PARENT_CID,
                'source_origins':{'root_id':root['root_id'],'mother_root':root['mother_root'],'cache_arm':'Sol-C',
                    'actual_cache_file':str((directory/'calls-and-choices.jsonl').resolve())}})
    for name in ('S01-generation.batch.json','EVALUATION-PLAN.json'):bind(_project_file(_PROJECT_ROOT, AUTHOR/name))
    for name in ('candidate.py','generation.json'):bind(_project_file(_PROJECT_ROOT, PARENT/name))
    bind(Path(__file__))
    wanted = {slot['view_sha256'] for slot in slots}
    original = views(view_files, wanted)
    assert len(slots) == 253
    for slot in slots:
        assert set(slot['cached_parent_scores']) == {a['action_key'] for a in original[slot['view_sha256']]['actions']}
    write('SLOTS.json', slots); bind(_project_file(_PROJECT_ROOT, HERE/'SLOTS.json'))
    write('PREPARED.json',{'schema':'t22-same-input-mechanical-prepared/1','status':'prepared_zero_business_calls',
        'files':files,'view_files':[str(p) for p in view_files],'window_slots':253,'unique_inputs':len(wanted),
        'planned_child_scores':253,'new_parent_scores':0,'cached_parent_scores':253,'max_operations':2400000,
        'wall_clock_seconds':1200,'capture_limits':{'max_unique_views':253,'max_view_json_bytes':64*1024**2,
            'max_total_json_bytes':2*1024**3},'selection':'all245 old registered windows plus all8 closed T20/T21 actual initial inputs; no endpoint filtering',
        'protected':'all legal roots except root chi/peng with no current legal Hu; all currentHu roots exact T19',
        'parent_candidate_id':PARENT_CID,'candidate_package':str((_project_file(_PROJECT_ROOT, AUTHOR/'S01-model-output-replay2')).resolve()),
        'first_followup_DTOs':'not reconstructed from partial visible fields; actual same-start continuation captures full typed inputs',
        'rule_calls':0,'projection_calls':0,'world_calls':0,'model_calls':0,
        'review':'same typed contract and production capture; root ordinary checks; no new independent review',
        'not_confirmation_or_release':True})
    print(json.dumps({'status':'prepared','slots':253,'unique_inputs':len(wanted),'business_calls':0}))


def execute():
    """全253槽真实子代评分；失败保留原槽，父旧分明示缓存，不复评分。"""
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
                    request = DecisionRequest(obs, CompetitionContext('t22-same-input-mechanics/1', None, None, None,
                        None, (), 0), analysis, 't22-probe:'+str(slot['slot_no']), window.trigger_seq, window, ())
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
                    allowed = {a['action_key'] for a in dto['actions'] if not current_hu and a['action_type'] in ('chi', 'peng')}
                    protected_keys = set(values) - allowed
                    protected = not allowed
                    assert all(values[k] == slot['cached_parent_scores'][k] for k in protected_keys), 'pointwise protected root changed'
                    if current_hu:
                        assert values['hu'] == slot['cached_parent_scores']['hu'], 'immediate Hu payment score changed'
                    row.update(status='scored', scores=values, entries=[{'action_key': e.action_key,
                        'score': e.score, 'trace': dict(e.trace)} for e in result.entries],
                        operations=executor.last_operation_count, first=order[0], current_hu=current_hu,
                        white_count=whites, wall_remaining=ctx['remaining_tile_count'], protected=protected,
                        protected_keys=sorted(protected_keys), allowed_claim_keys=sorted(allowed),
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
    result = {'schema': 't22-same-input-mechanical-result/1',
        'status': 'closed_not_strength_confirmation' if not errors and files_stable and costs['terminal']['terminal_valid'] else 'failed_slots_retained',
        'candidate_id': child['identity']['candidate_id'], 'parent_candidate_id': PARENT_CID,
        'planned_slots': 253, 'completed_slots': len(completed), 'failed_slots': errors,
        'actual_calls': counters, 'new_parent_scores': 0, 'cached_parent_score_slots': 253,
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
