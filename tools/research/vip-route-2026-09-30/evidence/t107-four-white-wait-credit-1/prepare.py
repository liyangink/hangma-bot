"""纯读009的原C完整桌，冻结两个四白窗口的同起点检验。

恢复轨迹汇合各席自己的观察，只供离线教师。候选及后续作者仅能读取
PUBLIC-TARGETS中的焦点观察和评分。已知结果来源不授留出或自然概率。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t107-four-white-wait-credit-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
import difflib
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAMPAIGN = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t103-joint-breadth-fresh-confirmation-1')
PUBLIC = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t105-confirmation-opportunity-diagnosis-1')
PREVIOUS = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t106-first-width-and-hu-credit-1')


def canonical(value):
    """规范JSON不改写牌码、空值、积分或时间字段。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """流式原件身份，单位字节；不解压或推进模拟。"""
    h = hashlib.sha256()
    size = 0
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
            size += len(block)
    return {'bytes': size, 'sha256': h.hexdigest()}


def save(name, value):
    """只新建产物，禁止覆盖冻结准备或失败记录。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def main():
    closed = json.loads((_project_file(_PROJECT_ROOT, CAMPAIGN / 'CAMPAIGN-CLOSURE.json')).read_text())
    assert closed['whole_batch_valid']
    campaign_plan = json.loads((_project_file(_PROJECT_ROOT, CAMPAIGN / 'CAMPAIGN-PLAN.json')).read_text())
    cid = campaign_plan['candidate_identity']['candidate_id']
    root = 't97-natural-preparation:reserved_confirmation:009'
    source = _project_file(_PROJECT_ROOT, CAMPAIGN / 'block-01/decisions.jsonl.gz')
    group_file = _project_file(_PROJECT_ROOT, CAMPAIGN / 'block-01/group-009-0123.json.gz')
    manifest = json.loads((_project_file(_PROJECT_ROOT, CAMPAIGN / 'CLOSED-ARTIFACT-MANIFEST.json')).read_text())['files']
    assert pin(source) == manifest['block-01/decisions.jsonl.gz']
    assert pin(group_file) == manifest['block-01/group-009-0123.json.gz']
    with gzip.open(group_file, 'rt') as stream:
        group = json.load(stream)
    original = next(r for r in group['match_records'] if r['match_id'].endswith('vip:' + cid))
    expected = original['outcome']['decisions']
    keys = ('window_key', 'observation', 'legal_action_keys', 'selected_action_key',
            'seat', 'permutation', 'initial_dealer_physical')
    records = []
    with gzip.open(source, 'rt') as stream:
        for line in stream:
            if original['match_id'] not in line:
                continue
            row = json.loads(line)
            if row['match_id'] != original['match_id']:
                continue
            assert row['status'] == 'chosen' and row['selected_action_key'] in row['legal_action_keys']
            records.append({k: row[k] for k in keys})
            if len(records) == len(expected):
                break
    assert [(r['window_key'], r['selected_action_key'], r['seat']) for r in records] == [
        (r['window_key'], r['action_key'], r['seat']) for r in expected]
    frames = []
    for row in records:
        key = tuple(row['window_key'][k] for k in ('game_id', 'round_no', 'trigger_seq', 'phase'))
        previous_key = None if not frames else tuple(frames[-1][0]['window_key'][k] for k in
                                                    ('game_id', 'round_no', 'trigger_seq', 'phase'))
        if previous_key != key:
            frames.append([])
        frames[-1].append(row)
    start = json.loads((_project_file(_PROJECT_ROOT, CAMPAIGN / 'block-01/START.json')).read_text())
    composition = next(r for r in start['opponent_compositions'] if r['root_id'] == root)
    trace = {'arm': 'C', 'match_id': original['match_id'], 'composition': composition,
             'permutation': [0, 1, 2, 3], 'initial_dealer': 0, 'frames': frames,
             'original_outcome': original['outcome'], 'scope': 'offline teacher only; forbidden author input'}
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'TEACHER-SOURCE-TRACES.json.gz'), 'xb') as stream:
        stream.write(canonical({'traces': [trace]}) + b'\n')
    public = json.loads((_project_file(_PROJECT_ROOT, PUBLIC / 'PUBLIC-TARGETS.json')).read_text())
    targets = [r for r in public['four_white_targets'] if r['match_id'] == original['match_id']
               and r['window_key']['phase'] == 'draw']
    assert sorted(r['window_key']['trigger_seq'] for r in targets) == [761, 785]
    assert all(r['white_count'] == 4 for r in targets)
    save('PUBLIC-TARGETS.json', {'targets': targets, 'source_kind': 'known_outcome_development',
                               'independent_sources': 1})
    for name in ('run_causal.py', 'io_helpers.py'):
        text = (_project_file(_PROJECT_ROOT, PREVIOUS / name)).read_text().replace('T106', 'T107').replace('t106', 't107')
        text = text.replace('第33来源早期宽度及当前胡分解', '第9来源四白当前胡及等待代价')
        ast.parse(text)
        (_project_file(_PROJECT_ROOT, HERE / name)).write_text(text)
    reader = (_project_file(_PROJECT_ROOT, PREVIOUS / 'readback-v2.py')).read_text()
    ast.parse(reader)
    (_project_file(_PROJECT_ROOT, HERE / 'readback.py')).write_text(reader)
    delta = ''.join(difflib.unified_diff((_project_file(_PROJECT_ROOT, PREVIOUS / 'run_causal.py')).read_text().splitlines(True),
                                       (_project_file(_PROJECT_ROOT, HERE / 'run_causal.py')).read_text().splitlines(True),
                                       fromfile='T106/run_causal.py', tofile='T107/run_causal.py'))
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'ADAPTATION-DIFF.diff.gz'), 'xb') as stream:
        stream.write(delta.encode())
    plan = json.loads((_project_file(_PROJECT_ROOT, PREVIOUS / 'RUN-PREPARED.json')).read_text())
    plan.update(schema='t107-known-four-white-wait-credit/1', mother_root=root, hand_no=3,
                original_C_hand_net=40, original_C_hand_fan=4, status='prepared_not_started',
                targets=[{'name': 'early_four_white_current_hu', 'trigger_seq': 761,
                          'original_first': 'discard:6w', 'forced_first': 'hu',
                          'reason': '当前两番可胡；只改为立即兑现，随后固定C，检验等待到四番的条件代价'},
                         {'name': 'later_four_white_continue', 'trigger_seq': 785,
                          'original_first': 'hu', 'forced_first': 'discard:8w',
                          'reason': '当前四番立即胡；仅改为原C最高非胡合法动作，随后固定C，不强制多手等待或财飘'}],
                scope='one known four-white development source; single-action effect, not whole waiting-policy value',
                predecessor_results={'T103_current_hand_net': 40, 'T103_current_hand_fan': 4,
                                     'waiting_effect_unknown': True},
                candidate_identity=campaign_plan['candidate_identity'],
                generation_file=campaign_plan['generation_file'], raw_source_file=campaign_plan['raw_source_file'])
    inputs = [source, group_file, _project_file(_PROJECT_ROOT, CAMPAIGN / 'CAMPAIGN-CLOSURE.json'),
              _project_file(_PROJECT_ROOT, CAMPAIGN / 'ACTUAL-READBACK-TERMINAL.json'), _project_file(_PROJECT_ROOT, PUBLIC / 'EXTRACTION-CLOSURE.json'),
              _project_file(_PROJECT_ROOT, PUBLIC / 'PUBLIC-TARGETS.json'), _project_file(_PROJECT_ROOT, PREVIOUS / 'ROOT-READBACK.json'),
              _project_file(_PROJECT_ROOT, PREVIOUS / 'ACTUAL-READBACK-V2-TERMINAL.json'),
              Path(plan['generation_file']), Path(plan['raw_source_file'])]
    inputs += [_project_file(_PROJECT_ROOT, HERE / n) for n in ('prepare.py', 'run_causal.py', 'io_helpers.py', 'readback.py',
                                  'ADAPTATION-DIFF.diff.gz', 'PUBLIC-TARGETS.json', 'TEACHER-SOURCE-TRACES.json.gz')]
    plan['files'] = {str(f.resolve()): pin(f) for f in inputs}
    save('RUN-PREPARED.json', plan)
    assert pin(source) == manifest['block-01/decisions.jsonl.gz']
    save('PREPARATION-READBACK.json', {'prepared': True, 'source_full_table_decisions': len(records),
         'source_frames': len(frames), 'targets': len(targets), 'known_independent_sources': 1,
         'new_models_rules_scores_worlds_tables': 0, 'source_decisions': pin(source)})
    print({'prepared': True, 'source_decisions': len(records), 'max_continuations': 6,
           'known_independent_sources': 1, 'new_business_calls': 0}, flush=True)


if __name__ == '__main__':
    main()
