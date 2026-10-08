"""纯读三个已曝光正反来源及四白窗口，不进行评分、规则分析或模拟。

公开产物只含焦点依法可见观察。各席观察汇合后的恢复轨迹仅供离线
教师，禁止交给候选作者或线上策略。按已知结局选样不授留出信用。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t105-confirmation-opportunity-diagnosis-1'

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
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def canonical(value):
    """规范JSON不改写牌码、空值、积分或时间基准。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    """流式绑定原字节，单位字节；不会解压或推进世界。"""
    h = hashlib.sha256()
    size = 0
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            size += len(block)
            h.update(block)
    return {'bytes': size, 'sha256': h.hexdigest()}


def save(path, value):
    """只新建文件；已有失败或执行记录不覆盖。"""
    with Path(path).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def frame_key(window):
    """按官方模拟窗口标识合帧，保留每席各自合法观察。"""
    return tuple(window[k] for k in ('game_id', 'round_no', 'trigger_seq', 'phase'))


def main():
    started = time.monotonic()
    plan = json.loads((_project_file(_PROJECT_ROOT, HERE / 'PLAN.json')).read_text())
    for name, value in plan['files'].items():
        assert pin(name) == value, name
    campaign = Path(plan['campaign_directory'])
    result = json.loads((campaign / 'CAMPAIGN-CLOSURE.json').read_text())
    assert result['whole_batch_valid'] and not result['net_positive_interval']
    assert result['candidate_identity']['candidate_id'] == plan['candidate_id']
    teacher_keys = ('window_key', 'observation', 'legal_action_keys',
                    'selected_action_key', 'seat', 'permutation', 'initial_dealer_physical')
    matches, wanted, focal = {}, {}, {}
    for case in plan['cases']:
        with gzip.open(case['group_file'], 'rt') as stream:
            group = json.load(stream)
        arms = {}
        for record in group['match_records']:
            arm = 'C' if record['match_id'].endswith('vip:' + plan['candidate_id']) else 'A'
            assert arm not in arms and case['root_id'] in record['match_id']
            arms[arm] = record
            match_id = record['match_id']
            matches[match_id] = (case, arm, record)
            wanted[match_id], focal[match_id] = [], []
        assert set(arms) == {'A', 'C'}
    four_white = []
    for block in range(1, 5):
        source = campaign / f'block-{block:02d}' / 'decisions.jsonl.gz'
        relevant = [mid for mid, (case, _, _) in matches.items() if case['block'] == block]
        lines_seen = 0
        with gzip.open(source, 'rt') as stream:
            for line in stream:
                lines_seen += 1
                if lines_seen % 10000 == 0:
                    assert time.monotonic() - started < plan['wall_seconds']
                is_four = '"white_count":4' in line or '"white_count": 4' in line
                if not is_four and not any(mid in line for mid in relevant):
                    continue
                row = json.loads(line)
                if row['match_id'] in wanted:
                    case, arm, _ = matches[row['match_id']]
                    assert row['status'] == 'chosen' and row['selected_action_key'] in row['legal_action_keys']
                    wanted[row['match_id']].append({k: row[k] for k in teacher_keys})
                    if row['seat'] == 0 and row['window_key']['round_no'] == case['round_no']:
                        focal[row['match_id']].append(row)
                if is_four and row['policy_id'] == 'vip:' + plan['candidate_id']:
                    assert row['c_self_scored'] and not row['degraded_reasons']
                    four_white.append(row)
                    assert len(four_white) <= plan['max_four_white_windows']
        print({'block': block, 'pure_read_lines': lines_seen,
               'four_white_windows_so_far': len(four_white)}, flush=True)
    assert len(four_white) == plan['expected_four_white_windows']
    targets, traces = [], []

    def public_target(row, labels, case_name):
        """只导出本座观察与实际评分；不导出其他座位或未来牌墙。"""
        is_c = row['policy_id'] == 'vip:' + plan['candidate_id']
        digest = None
        if is_c:
            assert row['c_self_scored'] and len(row['scoring_calls']) == 1
            call = row['scoring_calls'][0]
            assert call['status'] == 'SCORED' and call['input_capture']['saved_before_score']
            digest = call['input_capture']['view_sha256']
        return {'case': case_name, 'arm': 'C' if is_c else 'A', 'labels': labels,
                'match_id': row['match_id'], 'window_key': row['window_key'],
                'observation': row['observation'], 'white_count': row['white_count'],
                'legal_action_keys': row['legal_action_keys'],
                'original_first': row['selected_action_key'],
                'original_full_scores': row['candidates'], 'view_sha256': digest,
                'current_opportunity': row['current_opportunity']}

    for mid, (case, arm, original) in matches.items():
        actual = [(r['window_key'], r['selected_action_key'], r['seat']) for r in wanted[mid]]
        expected = [(r['window_key'], r['action_key'], r['seat']) for r in original['outcome']['decisions']]
        assert actual == expected, (case['name'], arm)
        rows = focal[mid]
        draws = [r for r in rows if r['phase'] == 'draw']
        assert draws, (case['name'], arm)
        selected = {}

        def select(row, label):
            key = canonical(row['window_key']).decode()
            selected.setdefault(key, (row, []))[1].append(label)

        select(draws[0], 'opening_draw')
        select(draws[-1], 'last_draw')
        claims = [i for i, r in enumerate(rows) if r['selected_action_key'].startswith(('chi:', 'peng:'))]
        if claims:
            after = next((r for r in rows[claims[0] + 1:] if r['phase'] == 'draw'), None)
            if after is not None:
                select(after, 'first_draw_after_first_claim')
        hu = [r for r in rows if 'hu' in r['legal_action_keys']]
        if hu:
            select(hu[0], 'first_legal_current_hu')
            select(hu[-1], 'last_legal_current_hu')
        multi = next((r for r in draws if r['white_count'] >= 2), None)
        if multi is not None:
            select(multi, 'first_multi_white_draw')
        targets.extend(public_target(row, labels, case['name']) for row, labels in selected.values())
        frames = []
        for row in wanted[mid]:
            if not frames or frame_key(frames[-1][0]['window_key']) != frame_key(row['window_key']):
                frames.append([])
            frames[-1].append(row)
        start = json.loads((campaign / f"block-{case['block']:02d}" / 'START.json').read_text())
        composition = next(r for r in start['opponent_compositions'] if r['root_id'] == case['root_id'])
        traces.append({'case': case['name'], 'arm': arm, 'match_id': mid,
                       'composition': composition, 'permutation': [0, 1, 2, 3],
                       'initial_dealer': 0, 'frames': frames, 'original_outcome': original['outcome'],
                       'scope': 'offline teacher recovery only; forbidden author or online input'})
    assert len(targets) <= plan['max_selected_public_targets']
    four_targets = [public_target(r, ['observed_four_white'], 'four_white_coverage') for r in four_white]
    needed = {r['view_sha256'] for r in targets + four_targets if r['view_sha256'] is not None}
    captured = set()
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'ORIGINAL-C-VIEWS.jsonl.gz'), 'xb') as output:
        for block in range(1, 5):
            with gzip.open(campaign / f'block-{block:02d}' / 'views.jsonl.gz', 'rt') as stream:
                for line in stream:
                    row = json.loads(line)
                    digest = row['view_sha256']
                    if digest not in needed:
                        continue
                    raw = canonical(row['view'])
                    assert hashlib.sha256(raw).hexdigest() == digest and len(raw) == row['json_bytes']
                    assert digest not in captured
                    captured.add(digest)
                    output.write(canonical(row) + b'\n')
    assert captured == needed
    save(_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-TARGETS.json'), {'source_kind': 'known_outcome_development',
         'independent_selected_sources': 3, 'targets': targets, 'four_white_targets': four_targets,
         'actual_new_models_rules_scores_worlds_tables': 0})
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'TEACHER-SOURCE-TRACES.json.gz'), 'xb') as output:
        output.write(canonical({'traces': traces, 'scope': 'teacher only; never author input'}) + b'\n')
    for name, value in plan['files'].items():
        assert pin(name) == value, name
    summary = [{'case': r['case'], 'arm': r['arm'], 'labels': r['labels'],
                'window_key': r['window_key'], 'first': r['original_first'],
                'white_count': r['white_count'], 'current_opportunity': r['current_opportunity'],
                'remaining_tiles': r['observation']['remaining_tile_count'],
                'dealer_seat': r['observation'].get('dealer_seat'),
                'hand': r['observation']['my_hand'], 'drawn_tile': r['observation']['drawn_tile']}
               for r in targets + four_targets]
    save(_project_file(_PROJECT_ROOT, HERE / 'EXTRACTION-CLOSURE.json'), {'complete': True, 'selected_teacher_traces': len(traces),
         'selected_public_targets': len(targets), 'four_white_windows': len(four_white),
         'captured_original_views': len(captured), 'targets': summary,
         'source_files': plan['files'], 'new_models_rules_scores_worlds_tables': 0,
         'fresh_confirmation': False, 'elapsed_monotonic_seconds': time.monotonic() - started,
         'output_files': {n: pin(_project_file(_PROJECT_ROOT, HERE / n)) for n in ('PUBLIC-TARGETS.json',
                          'ORIGINAL-C-VIEWS.jsonl.gz', 'TEACHER-SOURCE-TRACES.json.gz')}})
    print({'complete': True, 'selected_targets': len(targets),
           'four_white_windows': len(four_white), 'business_calls': 0}, flush=True)


if __name__ == '__main__':
    main()
