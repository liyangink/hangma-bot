"""从四个已闭自然母根的首个共同公开观察分歧恢复单局起点。

选源只看无胡严格评分偏好，每母根 H 池最小换座序，不看赢家或终分。恢复函数原样复用
已验收 C 前缀实现；完整世界只供离线教师续打，候选只收公开观察。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t21-early-strict-choice-causal-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import gzip
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
CORE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t10-abc-implementation-preparation-1')
sys.path.insert(0, str(CORE))
from recover_natural_start import ROOT, canonical, fingerprint, read_json, require, window_id, frame_id

AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t19-maintained-ready-choice-author-1')
NATURAL = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t19-maintained-ready-choice-author-1/PARENT-natural-common-first2-32')
NATURALS = {
    str(NATURAL.resolve()): _project_file(_PROJECT_ROOT, HERE.parent / 't19-common-natural-closure-1/PARENT'),
    str((_project_file(_PROJECT_ROOT, AUTHOR / 'PARENT-natural-last2-opportunity-scout-32')).resolve()): _project_file(_PROJECT_ROOT, HERE.parent / 't19-last2-parent-scout-closure-1/PARENT'),
}
CID = 'b198e694fb46bb95cfac31b0d14a08744e018efb5f0966034b4015a31b05f655'
SELECTION = read_json(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-SELECTION.json'))
SELECTED = tuple((s['source']['pool'], s['source']['witness']['parent']['input_capture']['view_sha256'])
                 for s in SELECTION['rows'])


def source_material(pool, sha, bind):
    """纯读已登记 C 轨迹及实际完整输入；缓存父分不重复算，不贴动作金标。"""
    require(SELECTION['status'] == 'prepared_no_START_zero_business_calls', '登记类型不同')
    for name, digest in SELECTION['pins'].items():
        require(fingerprint(Path(name))['sha256'] == digest, '选源依据漂移: ' + name)
        bind(Path(name))
    choices = [s for s in SELECTION['rows'] if s['source']['pool'] == pool and
               s['source']['witness']['parent']['input_capture']['view_sha256'] == sha]
    require(len(choices) == 1, '登记当前输入不唯一')
    chosen = choices[0]; src, ranking = chosen['source'], chosen['ranking']
    selected = src['witness']['parent']; reference = src['witness']['R18']
    window = selected['window_key']; filename = Path(src['source_file']).resolve()
    raw = filename.parents[1]
    require(str(raw) in NATURALS and filename == raw / pool / 'decisions.jsonl.gz', '来源不在已闭两批')
    closure = NATURALS[str(raw)]
    seal, audit = read_json(closure / 'RAW-FIRST-SEAL.json'), read_json(closure / 'AUDIT.json')
    require(audit['accepted_engineering_chain'] and audit['tables'] == 32 and audit['candidate_id'] == CID
            and audit['raw_seal_sha256'] == fingerprint(closure / 'RAW-FIRST-SEAL.json')['sha256'], '真父来源未闭')
    for name, expected in seal['files'].items():
        require(fingerprint(Path(name)) == expected, '自然原件漂移: ' + name)
        bind(Path(name))
    require(src['status'] == 'first_same_public_action_divergence' and not src['witness']['current_legal_hu']
            and not ranking['exact_top_tie'] and src['witness']['white_count'] in (0, 1)
            and selected['selected_action_key'] != reference['selected_action_key'], '不是登记的无胡严格偏好')
    manifest = read_json(raw / 'manifest.json')
    require(manifest['candidate_identity']['candidate_id'] == CID and manifest['development_only']
            and not manifest['confirmation_claim'] and not manifest['published'], '来源身份不同')
    root, permutation = src['root_id'], src['permutation']
    group_path = raw / pool / ('group-' + hashlib.sha256(root.encode()).hexdigest()[:16] + '-' + ''.join(map(str, permutation)) + '.json')
    group = read_json(group_path); experiment = group['experiment']; match_id = window['game_id']
    require(experiment['seat_permutations'] == [permutation] and experiment['challenger']['policy_id'] == 'vip:' + CID
            and experiment['tournament_config'] == manifest['config'], 'C 装配不同')
    outcomes = [m['outcome'] for m in group['match_records'] if m['match_id'] == match_id]
    require(len(outcomes) == 1 and outcomes[0]['status'] == 'complete' and outcomes[0]['completed_hands'] == 8, '缺完整来源桌')
    groups, seen = [], set()
    for record in outcomes[0]['decisions']:
        key = window_id(record['window_key']); require(key not in seen, '窗口重复'); seen.add(key)
        if not groups or frame_id(groups[-1][0]['window_key']) != frame_id(record['window_key']):
            groups.append([])
        groups[-1].append(record)
    indexes = [i for i, rows in enumerate(groups) if any(window_id(r['window_key']) == window_id(window) for r in rows)]
    require(len(indexes) == 1, '目标帧不唯一'); groups = groups[:indexes[0] + 1]
    needed = {window_id(r['window_key']) for rows in groups for r in rows}; audit_rows = {}
    with gzip.open(filename, 'rt') as stream:
        for no, line in enumerate(stream, 1):
            row = json.loads(line)
            if row['match_id'] != match_id or window_id(row['window_key']) not in needed:
                continue
            key = window_id(row['window_key']); require(key not in audit_rows, '公开原件重复')
            audit_rows[key] = (row, no, hashlib.sha256(line.encode()).hexdigest())
    require(set(audit_rows) == needed, '缺四座前缀')
    receipts = []
    for records in groups:
        current = []
        for record in records:
            row, no, _ = audit_rows[window_id(record['window_key'])]
            require(row['window_key'] == record['window_key'] and row['policy_id'] == record['policy_id']
                    and row['selected_action_key'] == record['action_key'] and record['legal'] is True
                    and record['action_key'] in row['legal_action_keys'], '来源动作不同')
            current.append({k: row[k] for k in ('window_key', 'observation', 'legal_action_keys', 'policy_id')}
                           | {'action_key': record['action_key'], 'source_line': no})
        receipts.append(current)
    focal, no, line_sha = audit_rows[window_id(window)]
    require(focal['observation'] == selected['observation'] and focal['policy_id'] == 'vip:' + CID
            and focal['selected_action_key'] == selected['selected_action_key']
            and focal['scoring_execution']['input_capture']['view_sha256'] == sha
            and focal['scoring_execution']['input_capture']['saved_before_score']
            and no == selected['source_line'] and line_sha == selected['source_line_sha256'], '实际目标输入不同')
    cached = {e['action_key']: e['score'] for e in focal['candidates']}
    require(set(cached) == set(focal['legal_action_keys']) and 'hu' not in cached
            and cached[selected['selected_action_key']] > cached[reference['selected_action_key']]
            and sorted(cached, key=lambda k: (-cached[k], k))[0] == selected['selected_action_key'], '真实严格排序不同')
    found = None
    with gzip.open(raw / 'views.jsonl.gz', 'rt') as stream:
        for line in stream:
            record = json.loads(line)
            if record['view_sha256'] != sha:
                continue
            require(found is None and hashlib.sha256(canonical(record['view'])).hexdigest() == sha, '完整输入摘要不同')
            found = record
    require(found is not None, '原完整 DTO 缺失')
    seeds = [s for s in experiment['seeds'] if s['scenario_id'] == root]; require(len(seeds) == 1, '源 seed 不唯一')
    require(window['seat'] == permutation[0] and window['phase'] in ('draw', 'response_peng', 'response_chi') and window['round_no'] == 1, '不是登记的弃牌或吃碰窗口')
    spec = {'match_id': match_id, 'scenario_id': root, 'config': experiment['tournament_config'], 'seed': seeds[0]['seed'],
            'initial_dealer': permutation[experiment['initial_dealer']],
            'initial_scores': [experiment['initial_scores'][permutation.index(seat)] for seat in range(4)]}
    prefix = receipts[:-1]
    current_prefix = [rs for rs in prefix if rs[0]['window_key']['round_no'] == window['round_no']]
    for path in (closure / 'RAW-FIRST-SEAL.json', closure / 'AUDIT.json', _project_file(_PROJECT_ROOT, HERE / 'SOURCE-SELECTION.json'), Path(__file__)):
        bind(path)
    return {'source_kind': 'closed_actual_natural_C_window_prefix/2', 'source_C_full_DTO_sha256': sha,
        'source_C_cached_scores': cached, 'source_C_input_json_bytes': found['json_bytes'],
        'request_sha256': hashlib.sha256(canonical({k: focal[k] for k in ('observation', 'window_key', 'legal_action_keys')})).hexdigest(),
        'target_window': window, 'target_frame': receipts[-1], 'prefix': prefix, 'current_prefix': current_prefix, 'match_spec': spec,
        'value_limits': manifest['value_limits'], 'expected_math_backend': manifest['candidate_identity']['math_backend'],
        'policy_metadata': {n: manifest['policy_metadata'][n] for n in ['A'] + [f'H{i}' for i in (1, 2, 3)]},
        'source_selected_first': selected['selected_action_key'], 'reference_A_first': reference['selected_action_key'],
        'profile': 'ordinary_noHu_strict_preference_white'+str(src['witness']['white_count'])+'_'+window['phase'], 'mother_root': root, 'permutation': permutation,
        'source_is_not_A_panel_or_new_independent_root': True, 'selection_uses_terminal_score': False,
        'prefix_strategy_scoring_calls': 0}


def restore(*,root,rules,engine,batch,output,directory,event,call):
    """START后重放完整桌前缀，再在导入的本单局只重放本局前缀。"""
    from hangma_bot.kernel.config import RuleConfig,TimingConfig,TournamentConfig
    from hangma_bot.kernel.serialization import observation_to_json,window_key_to_json,window_key_from_json
    from hangma_bot.simulation.interface import MatchSpec,SimulationChoice
    from hangma_bot.offline.evaluate import frame_observation_summary
    from hangma_bot.simulation.artifacts import hand_math_runtime_metadata
    source=root['source'];raw=source['match_spec'];cfg=raw['config'];round_no=source['target_window']['round_no']
    config=TournamentConfig(cfg['max_games'],cfg['rounds_per_game'],RuleConfig(**cfg['rules']),TimingConfig(**cfg['timing']))
    backend=call('recovery:math_backend_reads',hand_math_runtime_metadata);expected=source['expected_math_backend']
    require(all(backend.get(k)==expected.get(k) for k in ('implementation','semantics_version','fallback_reason'))
            and backend.get('native_sha256')==(expected.get('native_binary') or {}).get('sha256'),'数学后端漂移')
    spec=MatchSpec(raw['match_id'],raw['scenario_id'],config,raw['seed'],raw['initial_dealer'],tuple(raw['initial_scores']))
    def check(frame,records):
        require(frame.blocked_reason is None and frame.final_scores is None,'前缀提前终局')
        require(canonical([window_key_to_json(d.window_key) for d in frame.decisions])==canonical([r['window_key'] for r in records]),'同期窗口错位')
        analyses=[]
        for decision,old in zip(frame.decisions,records):
            require(canonical(observation_to_json(decision.observation))==canonical(old['observation']),'完整公开观察不同')
            analysis=rules.analyze(decision.observation,route_limits=batch.route_limits)
            require(analysis.completeness.value=='complete' and sorted(c.action_key for c in analysis.legal_candidates)==sorted(old['legal_action_keys']),'合法集合不同')
            analyses.append(analysis)
        return analyses
    def replay(world,prefix,phase):
        for ordinal,records in enumerate(prefix,1):
            frame=call('recovery:world_frame_calls',engine.frame,world);analyses=check(frame,records);choices=[]
            for decision,old,analysis in zip(frame.decisions,records,analyses):
                matches=[c for c in analysis.legal_candidates if c.action_key==old['action_key']]
                require(len(matches)==1,'原动作不是唯一合法候选');choices.append(SimulationChoice(decision.window_key,matches[0].action))
            row={'event':'recovery_advance','phase':phase,'ordinal':ordinal,'revision':frame.revision,
                 'choices':[{'window_key':r['window_key'],'action_key':r['action_key']} for r in records]}
            event({**row,'status':'dispatch'});world=call('recovery:world_advance_calls',engine.advance,world,frame.revision,tuple(choices));event({**row,'status':'advanced'})
        frame=call('recovery:world_frame_calls',engine.frame,world);check(frame,source['target_frame']);return world,frame
    world=call('recovery:world_start_calls',engine.start,spec);world,frame=replay(world,source['prefix'],'original_match')
    hand=call('recovery:world_export_hand_calls',engine.export_hand,world,round_no)
    output.save(directory/'single-hand-teacher-origin.json',{'scope':'offline_teacher_full_world_only','hand':hand})
    single=call('recovery:world_import_calls',engine.from_replay,hand);single,target_frame=replay(single,source['current_prefix'],'single_hand')
    require(canonical([observation_to_json(d.observation) for d in frame.decisions])==canonical([observation_to_json(d.observation) for d in target_frame.decisions]),'单局转换改变公开观察')
    target=window_key_from_json(source['target_window']);snapshot={'observation_summary':frame_observation_summary(target_frame),
        'match_spec':{'match_id':raw['match_id']},'origin_match_spec':raw,'endpoint':'current_single_hand_end'}
    output.save(directory/'RECOVERY-RESULT.json',{'status':'recovered_actual_C_single_hand_start','source_kind':source['source_kind'],
        'whole_table_prefix_advance_calls':len(source['prefix']),'single_hand_prefix_advance_calls':len(source['current_prefix']),
        'target_window':source['target_window'],'all_seat_complete_observation_legal_set_and_window_checked':True,
        'score_calls':0,'stage_snapshot':snapshot,'not_new_independent_root':True})
    return single,target,snapshot
