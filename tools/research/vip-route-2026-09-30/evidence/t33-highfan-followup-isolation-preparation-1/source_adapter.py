"""T33 纯读已闭 T32 来源，按已验收方法恢复原条件世界与公开前缀。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t33-highfan-followup-isolation-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
CORE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t10-abc-implementation-preparation-1')
NESTED = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t23-discard-route-trade-preparation-1')
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(NESTED))
from recover_natural_start import canonical, fingerprint, read_json, require
from nested_source_recovery import restore_nested_start

OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t32-new-multiwhite-source-preparation-1')
CLOSED = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t32-new-multiwhite-closure-1')


def source_materials(bind):
    """只读四个已登记分歧的全座位记录；不评分、不推进、不重新采暗牌。"""
    selected = read_json(_project_file(_PROJECT_ROOT, HERE / 'PLAN.json'))
    plan = read_json(_project_file(_PROJECT_ROOT, OLD / 'PREPARED.json'))
    closed = read_json(_project_file(_PROJECT_ROOT, CLOSED / 'ROOT-CLOSED-CHECK.json'))
    seal = read_json(_project_file(_PROJECT_ROOT, CLOSED / 'RAW-FIRST-SEAL.json'))
    require(selected['status'] == 'pure_preparation_no_START' and selected['continuations_upper'] == 20,
            '不是原四窗登记')
    require(fingerprint(Path(selected['source_path']))['sha256'] == selected['source_sha256'], '登记分歧漂移')
    require(closed['status'] == 'accepted_engineering_only' and closed['complete_single_hand_continuations'] == 80,
            'T32 未完整闭合')
    require(closed['raw_seal_sha256'] == fingerprint(_project_file(_PROJECT_ROOT, CLOSED / 'RAW-FIRST-SEAL.json'))['sha256'], 'T32 封条不同')
    for path, expected in {**plan['files'], **plan['runtime_files'], **seal['files']}.items():
        require(fingerprint(Path(path)) == expected, 'T32 来源漂移: ' + path)
        bind(Path(path))
    for path in (_project_file(_PROJECT_ROOT, HERE / 'PLAN.json'), Path(selected['source_path']), _project_file(_PROJECT_ROOT, OLD / 'PREPARED.json'),
                 _project_file(_PROJECT_ROOT, CLOSED / 'ROOT-CLOSED-CHECK.json'), _project_file(_PROJECT_ROOT, CLOSED / 'RAW-FIRST-SEAL.json'),
                 _project_file(_PROJECT_ROOT, NESTED / 'nested_source_recovery.py'), _project_file(_PROJECT_ROOT, CORE / 'run_abc_diagnostic.py')):
        bind(path)
    wanted = {(row['root_id'], row['variant']) for row in selected['sources']}
    advances = {key: [] for key in wanted}
    choices, scores = {}, {}
    with (_project_file(_PROJECT_ROOT, OLD / 'calls-and-choices.jsonl')).open() as stream:
        for line in stream:
            row = json.loads(line)
            key = row['root_id'], row.get('variant')
            if key not in wanted:
                continue
            window = canonical(row['window_key']) if 'window_key' in row else None
            if row.get('arm') == 'Sol-C' and row['event'] == 'advance' and row['status'] == 'advanced':
                advances[key].append(row)
            elif row.get('arm') == 'Sol-C' and row['event'] == 'policy_choose':
                require((*key, window) not in choices and row['status'] == 'chosen', '原公开窗口重复或失败')
                choices[*key, window] = row
            elif row.get('arm') in ('Sol-C', 'S02-C') and row['event'] == 'score_call' and row['kind'] == 'C':
                score_key = (*key, row['arm'], window)
                require(score_key not in scores and row['status'] == 'SCORED'
                        and row['input_capture']['saved_before_score'], '源评分失败或重复')
                scores[score_key] = row
    roots = []
    for item in selected['sources']:
        key = item['root_id'], item['variant']
        base = next(root for root in plan['roots'] if root['root_id'] == key[0])
        ordinal = next(i for i, root in enumerate(plan['roots'], 1) if root['root_id'] == key[0])
        common_file = _project_file(_PROJECT_ROOT, OLD / f'root-{ordinal:02d}' / key[1] / 'COMMON-START.json')
        common = read_json(common_file)
        bind(common_file)
        sample = common['sample_key'] if key[1] != 'original' else None
        if sample is not None:
            require(sample == plan['hidden_sample_namespace'] + ':hidden:1:' + key[0], '不是原隐藏键')
        entries = advances[key]
        matches = [i for i, entry in enumerate(entries)
                   if any(c['window_key'] == item['window_key'] for c in entry['choices'])]
        require(len(matches) == 1, '原目标推进帧不唯一')
        cut = matches[0]

        def records(entry):
            result = []
            for choice in entry['choices']:
                row = choices[*key, canonical(choice['window_key'])]
                require(row['selected_action_key'] == choice['action_key']
                        and choice['action_key'] in row['legal_action_keys'], '源选择不等合法推进')
                result.append({'window_key': choice['window_key'], 'observation': row['observation'],
                               'legal_action_keys': row['legal_action_keys'], 'action_key': choice['action_key']})
            return result

        targets = records(entries[cut])
        target = next(row for row in targets if row['window_key'] == item['window_key'])
        require(target['observation'] == item['complete_public_observation']
                and target['legal_action_keys'] == item['legal_action_keys'], '完整登记观察或合法集不同')
        cached = {}
        for arm in ('Sol-C', 'S02-C'):
            actual = scores[*key, arm, canonical(target['window_key'])]
            require(actual['input_capture']['view_sha256'] == item['left_view_sha256'], '真父或子原完整输入不同')
            cached[arm] = {e['action_key']: e['score'] for e in actual['scores']['entries']}
        actual = scores[*key, 'Sol-C', canonical(target['window_key'])]
        require(actual['ranking'][0] == target['action_key'] == item['left_action'], '原首选不是登记左臂')
        prefix = [{'revision': entry['revision'], 'records': records(entry), 'source_advanced_row': entry}
                  for entry in entries[:cut]]
        nested = {'source_kind': 'closed_T32_C_subsequent_public_start', 'base_sample_key': sample,
                  'prefix': prefix, 'target_records': targets, 'target_revision': entries[cut]['revision'],
                  'target_window': target['window_key'], 'focal_observation': target['observation'],
                  'nested_request_sha256': hashlib.sha256(canonical({k: target[k] for k in
                      ('observation', 'window_key', 'legal_action_keys')})).hexdigest(),
                  'original_T32_root_id': key[0], 'original_T32_variant': key[1],
                  'original_advance_cut': cut}
        material = {'match_spec': {'match_id': key[0]}, 'value_limits': read_json(_project_file(_PROJECT_ROOT, OLD / 'CONTROL-TEMPLATES.json'))['value_limits'],
                    'source_kind': nested['source_kind'], 'target_window': target['window_key'],
                    'source_C_full_DTO_sha256': actual['input_capture']['view_sha256'],
                    'source_C_input_json_bytes': actual['input_capture']['json_bytes'],
                    'source_C_cached_scores': cached['Sol-C'], 'source_parent_cached_scores': cached['S02-C'],
                    'source_selected_first': target['action_key'], 'target_frame': targets,
                    'expected_current_hu': 'hu' in target['legal_action_keys']}
        roots.append({'root_id': key[0] + ':T33:' + str(target['window_key']['trigger_seq']),
                      'mother_root': key[0], 'source_kind': nested['source_kind'], 'profile': base['profile'],
                      'base_root': base, 'source': material, 'nested_start': nested,
                      'pool': base['pool'], 'permutation': base['permutation'],
                      'policy_metadata': base['policy_metadata'], 'logical_labels': base['logical_labels'],
                      'hidden_sample_namespace': 'unused_exact_recorded_T32_world',
                      'selection_uses_terminal_score': True, 'known_positive_development_not_confirmation': True})
    require(len(roots) == 4 and len({r['mother_root'] for r in roots}) == 3, '来源分母漂移')
    return roots, plan


def restore(*, root, rules, engine, batch, output, directory, event, call):
    """用原 T10 条件导入和 T23 嵌套恢复；教师暗牌只留在离线世界。"""
    from run_abc_diagnostic import build_control_start
    controls = read_json(_project_file(_PROJECT_ROOT, OLD / 'CONTROL-TEMPLATES.json'))
    prior = directory / 'base-source'
    prior.mkdir(exist_ok=False)
    # 旧导入器使用 call 记账；此包装明确归入恢复费用，不改其执行语义。
    def recovery_call(name, fn, *args, **kwargs):
        return call('recovery:' + name, fn, *args, **kwargs)
    world, old_target, snapshot = build_control_start(root['base_root'], controls, rules, engine, batch,
        output, prior, event, recovery_call, lambda name: recovery_call(name, lambda: None))
    return restore_nested_start(root=root, world=world, old_target=old_target, rules=rules, engine=engine,
        batch=batch, stage_snapshot=snapshot, focal=root['source']['target_window']['seat'],
        event=event, call=call, output=output, directory=directory)
