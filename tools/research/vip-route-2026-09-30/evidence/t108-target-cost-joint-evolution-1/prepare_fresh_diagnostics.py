"""纯读已闭合开发集的两处首分歧，冻结父／子／R18同起点续打。

所有未来轨迹只保存为离线教师资料。作者只能读取PUBLIC-TARGETS和
公开评分输入；两个来源已经曝光，不再承担独立确认角色。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import gzip
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents

HERE = Path(__file__).resolve().parent
CAMPAIGN = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1/S01-natural-development-1')
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1/S01-continuation-root009')


def canonical(value):
    """保留所有事实与空值，仅规范JSON排序。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """流式绑定原件字节，不评规则或推进世界。"""
    import hashlib
    h = hashlib.sha256()
    size = 0
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            size += len(block)
            h.update(block)
    return {'bytes': size, 'sha256': h.hexdigest()}


def save(path, value):
    """只新建计划与原件；不覆盖失败或运行输出。"""
    with path.open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def normalize(value):
    """父子场次标识不同；仅移除game_id，其他观察事实必须相同。"""
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items() if k != 'game_id'}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def frame_key(window):
    """同一官方事件的响应座位合并为一个恢复帧。"""
    return tuple(window[k] for k in ('game_id', 'round_no', 'trigger_seq', 'phase'))


def main():
    """冻结两个已知结果开发来源；零模型、评分、规则或模拟调用。"""
    closure = json.loads((_project_file(_PROJECT_ROOT, CAMPAIGN / 'CAMPAIGN-CLOSURE.json')).read_text())
    terminal = json.loads((_project_file(_PROJECT_ROOT, CAMPAIGN / 'ACTUAL-READBACK-TERMINAL.json')).read_text())
    assert closure['whole_batch_valid'] and terminal['exit_code'] == 0
    assert not closure['predeclared_confirmation_start_screen_passed']
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json')
    batch = VipEohBatch.read(batch_file)
    parent_package = _project_file(_PROJECT_ROOT, HERE.parent / 't101-joint-breadth-recovery-author-1/S02-model-output')
    child_package = _project_file(_PROJECT_ROOT, HERE / 'S01-model-output')
    parent, child = load_vip_parents([parent_package, child_package], batch)
    runner = (_project_file(_PROJECT_ROOT, OLD / 'run_causal.py')).read_text()
    runner = runner.replace("    plan = json.loads((HERE/'RUN-PREPARED.json').read_text())",
        "    plan = json.loads((HERE/'RUN-PREPARED.json').read_text())\n"
        "    focal_seat = plan['focal_seat']\n"
        "    permutation = tuple(plan['permutation'])")
    runner = runner.replace("if t['arm'] == 'C'", "if t['arm'] == 'P'")
    runner = runner.replace("d['seat'] == 0", "d['seat'] == focal_seat")
    runner = runner.replace("'focal_seat':0", "'focal_seat':focal_seat")
    runner = runner.replace('                policies = [audited]',
        '                policies = [None] * 4\n                policies[focal_seat] = audited')
    assert runner.count('policies.append(VipDevelopmentAuditPolicy(') == 1
    runner = runner.replace('policies.append(VipDevelopmentAuditPolicy(',
                            'policies[permutation[i]] = VipDevelopmentAuditPolicy(')
    runner = runner.replace('declaration.policy_id, lambda c=other:dict(c), record))',
                            'declaration.policy_id, lambda c=other:dict(c), record)')
    runner = runner.replace("r['arm'] == 'C'", "r['arm'] == 'P'")
    runner = runner.replace("['score_delta'][0]", "['score_delta'][focal_seat]")
    runner = runner.replace('T108-known-case', 'T108-fresh-case')
    ast.parse(runner)
    old_plan = json.loads((_project_file(_PROJECT_ROOT, OLD / 'RUN-PREPARED.json')).read_text())
    jobs = []
    cases = [('root003-loss', 3, '0123', 1, 9), ('root030-gain', 30, '3012', 8, 16)]
    for name, serial, label, cb, pb in cases:
        out = _project_file(_PROJECT_ROOT, HERE / ('S01-fresh-' + name))
        out.mkdir(exist_ok=False)
        (out / 'run_causal.py').write_text(runner)
        (out / 'io_helpers.py').write_bytes((_project_file(_PROJECT_ROOT, OLD / 'io_helpers.py')).read_bytes())
        permutation = tuple(map(int, label))
        focal_seat = permutation[0]
        sources, records = {}, {}
        for arm, block in [('P', pb), ('C', cb)]:
            group_path = _project_file(_PROJECT_ROOT, CAMPAIGN / f'block-{block:02d}/group-{serial:03d}-{label}.json.gz')
            with gzip.open(group_path, 'rt') as stream:
                group = json.load(stream)
            identity = parent['identity'] if arm == 'P' else child['identity']
            original = next(r for r in group['match_records']
                            if r['match_id'].endswith('vip:' + identity['candidate_id']))
            records[arm] = original
            sources[arm] = (block, group_path)
        ds = [records[a]['outcome']['decisions'] for a in ('P', 'C')]
        first = next(i for i, (p, c) in enumerate(zip(*ds))
                     if normalize(p['window_key']) != normalize(c['window_key'])
                     or p['seat'] != c['seat'] or p['action_key'] != c['action_key'])
        pd, cd = ds[0][first], ds[1][first]
        assert normalize(pd['window_key']) == normalize(cd['window_key'])
        assert pd['seat'] == cd['seat'] == focal_seat
        assert pd['action_key'] == 'hu' and cd['action_key'].startswith('discard:')
        round_no, seq = pd['window_key']['round_no'], pd['window_key']['trigger_seq']
        traces, targets, wanted_views, source_paths = [], [], set(), []
        for arm in ('P', 'C'):
            block, group_path = sources[arm]
            source = _project_file(_PROJECT_ROOT, CAMPAIGN / f'block-{block:02d}')
            source_paths.extend([group_path, source / 'decisions.jsonl.gz', source / 'views.jsonl.gz',
                                 source / 'START.json', source / 'settlements.jsonl.gz'])
            mid = records[arm]['match_id']
            rows, full_target = [], None
            keys = ('window_key', 'observation', 'legal_action_keys', 'selected_action_key',
                    'seat', 'permutation', 'initial_dealer_physical')
            with gzip.open(source / 'decisions.jsonl.gz', 'rt') as stream:
                for line in stream:
                    if mid not in line:
                        continue
                    row = json.loads(line)
                    if row['match_id'] != mid:
                        continue
                    assert row['status'] == 'chosen'
                    rows.append({k: row[k] for k in keys})
                    if row['seat'] == focal_seat and row['window_key']['round_no'] == round_no and row['window_key']['trigger_seq'] == seq:
                        assert full_target is None
                        full_target = row
            expected = [(r['window_key'], r['action_key'], r['seat']) for r in records[arm]['outcome']['decisions']]
            assert [(r['window_key'], r['selected_action_key'], r['seat']) for r in rows] == expected
            assert full_target is not None and full_target['c_self_scored']
            receipt = full_target['scoring_calls'][0]
            assert receipt['status'] == 'SCORED' and receipt['input_capture']['saved_before_score']
            digest = receipt['input_capture']['view_sha256']
            wanted_views.add(digest)
            targets.append({'case': name, 'arm': arm, 'labels': ['first_parent_child_difference'],
                'match_id': mid, 'window_key': full_target['window_key'], 'observation': full_target['observation'],
                'white_count': full_target['white_count'], 'legal_action_keys': full_target['legal_action_keys'],
                'original_first': full_target['selected_action_key'], 'original_full_scores': full_target['candidates'],
                'view_sha256': digest, 'current_opportunity': full_target['current_opportunity']})
            frames = []
            for row in rows:
                if not frames or frame_key(frames[-1][0]['window_key']) != frame_key(row['window_key']):
                    frames.append([])
                frames[-1].append(row)
            start = json.loads((source / 'START.json').read_text())
            composition = next(r for r in start['opponent_compositions'] if r['root_id'].endswith(f':{serial:03d}'))
            traces.append({'case': name, 'arm': arm, 'match_id': mid, 'composition': composition,
                'permutation': list(permutation), 'initial_dealer': full_target['initial_dealer_physical'],
                'frames': frames, 'original_outcome': records[arm]['outcome'],
                'scope': 'offline teacher recovery only; forbidden author or online input'})
        assert normalize(targets[0]['observation']) == normalize(targets[1]['observation'])
        assert targets[0]['legal_action_keys'] == targets[1]['legal_action_keys']
        save(out / 'PUBLIC-TARGETS.json', {'targets': targets, 'independent_sources': 1,
            'source_kind': 'known development first difference; no frequency or gold-label claim'})
        with gzip.open(out / 'TEACHER-SOURCE-TRACES.json.gz', 'xb') as stream:
            stream.write(canonical({'traces': traces}) + b'\n')
        captured = set()
        with gzip.open(out / 'PUBLIC-VIEWS.jsonl.gz', 'xb') as output:
            for block, _ in sources.values():
                with gzip.open(_project_file(_PROJECT_ROOT, CAMPAIGN / f'block-{block:02d}/views.jsonl.gz'), 'rt') as stream:
                    for line in stream:
                        row = json.loads(line)
                        if row['view_sha256'] in wanted_views and row['view_sha256'] not in captured:
                            output.write(canonical(row) + b'\n')
                            captured.add(row['view_sha256'])
        assert captured == wanted_views
        settlement = None
        with gzip.open(_project_file(_PROJECT_ROOT, CAMPAIGN / f'block-{pb:02d}/settlements.jsonl.gz'), 'rt') as stream:
            for line in stream:
                row = json.loads(line)
                if row['match_id'] == records['P']['match_id'] and row['round_no'] == round_no:
                    assert settlement is None
                    settlement = row['settlement']
        assert settlement is not None
        files = [Path(__file__), out / 'run_causal.py', out / 'io_helpers.py', batch_file,
            out / 'TEACHER-SOURCE-TRACES.json.gz', out / 'PUBLIC-TARGETS.json', out / 'PUBLIC-VIEWS.jsonl.gz',
            parent_package / 'candidate.py', parent_package / 'generation.json',
            child_package / 'candidate.py', child_package / 'generation.json',
            _project_file(_PROJECT_ROOT, CAMPAIGN / 'CAMPAIGN-CLOSURE.json'), _project_file(_PROJECT_ROOT, CAMPAIGN / 'ACTUAL-READBACK-TERMINAL.json')] + source_paths
        plan = dict(old_plan, schema='t108-fresh-first-difference-continuation/1',
            focal_seat=focal_seat, permutation=list(permutation), mother_root=traces[0]['composition']['root_id'],
            hand_no=round_no, candidate_identity=parent['identity'], child_identity=child['identity'],
            targets=[{'name': 'first_difference', 'trigger_seq': seq, 'original_first': pd['action_key'],
                      'forced_first': cd['action_key'], 'reason': 'same observation parent hu versus child wait; no forcing'}],
            original_C_hand_net=settlement['score_delta'][focal_seat], original_C_hand_fan=settlement['fan'],
            max_continuations=3, raw_source_file=str(parent_package / 'candidate.py'),
            child_source_file=str(child_package / 'candidate.py'), generation_file=str(batch_file),
            files={str(p): pin(p) for p in files}, status='prepared_not_started',
            predecessor_results={'directory': str(CAMPAIGN), 'outcomes_not_transferred': True})
        save(out / 'RUN-PREPARED.json', plan)
        jobs.append({'directory': str(out), 'hand_no': round_no, 'trigger_seq': seq,
                     'focal_seat': focal_seat, 'continuations': 3, 'P_current_hand_net': plan['original_C_hand_net']})
    save(_project_file(_PROJECT_ROOT, HERE / 'S01-FRESH-DIAGNOSTIC-PREPARATION.json'), {'complete': True, 'jobs': jobs,
        'actual_models_scores_rules_worlds_tables': 0, 'independent_exposed_sources': 2})
    print({'prepared': True, 'jobs': jobs, 'business_calls': 0})


if __name__ == '__main__':
    main()
