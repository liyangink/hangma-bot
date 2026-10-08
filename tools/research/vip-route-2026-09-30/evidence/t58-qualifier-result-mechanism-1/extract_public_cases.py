"""从已关闭T52的真实决策记录抽开发窗，不评分或用未来信息扩充观察。

自然窗按当前可见状态分层、每母根先取最小摘要，再跨根选16窗。
稀有兑现及错过例按结果选为诊断素材，明确不当独立确认或动作金标。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t58-qualifier-result-mechanism-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAMPAIGN = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t52-fixed-qualifier-unexposed-long-1')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def short_row(row, *, category, source_path):
    """只保存原本座依法可见观察、原窗口及原实际排名；不含模拟完整世界。"""
    return {'category': category, 'source_file': str(source_path),
        'root_id': row['root_id'], 'decision_id': row['decision_id'],
        'match_id': row['match_id'], 'observation': row['observation'],
        'window_key': row['window_key'], 'white_count': row['white_count'],
        'current_opportunity': row['current_opportunity'],
        'selected_action_key': row['selected_action_key'],
        'actual_recorded_candidates': row['candidates'],
        'c_self_scored': row['c_self_scored']}


def main():
    closure_path = _project_file(_PROJECT_ROOT, CAMPAIGN / 'CAMPAIGN-CLOSURE.json')
    closure = json.loads(closure_path.read_text())
    assert closure['whole_batch_valid'] and closure['actual_started_tables'] == 1024
    paths = [_project_file(_PROJECT_ROOT, CAMPAIGN / f'block-{i:02}/decisions.jsonl.gz') for i in range(1,5)]
    counts = [('multiwhite-small-hu',4), ('multiwhite-nonhu',6),
              ('zero-white-nonhu',2), ('one-white-nonhu',2), ('response',2)]
    rare_targets = [(89,7,'1230'), (92,6,'0123'), (116,7,'0123'),
                    (15,2,'0123'), (95,1,'2301')]
    frozen = {str(path): sha(path) for path in [Path(__file__), closure_path, *paths]}
    save('PUBLIC-EXTRACTION-PLAN.json', {'schema': 't58-public-extraction/1',
        'frozen_files': frozen, 'natural_stratum_limits': counts,
        'rare_result_selected_development_paths': rare_targets,
        'natural_selection': 'current-visible criteria, min decision digest per root and stratum, then digest roots without reuse',
        'actual_new_score_graph_world_table_model_calls': 0,
        'existing128_confirmation_roots_now_exposed': True})
    best = {category:{} for category,_ in counts}
    rare_rows = {}
    rare_seen_whites = {}
    counter = Counter()
    for path in paths:
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            for line in stream:
                counter['raw_rows'] += 1
                # 先用固定字节标记跳过无关大行，解析后仍复核所有结构条件。
                is_candidate = '"c_self_scored": true' in line
                relevant_rare = any(f't48-qualifier-confirmation:{root:03}' in line for root,_,_ in rare_targets)
                if not is_candidate and not relevant_rare:
                    continue
                row = json.loads(line)
                if row['seat'] != row['focal_physical_seat']:
                    continue
                observation = row['observation']
                assert observation['seat'] == row['seat']
                counter['focal_parsed_rows'] += 1
                if is_candidate:
                    assert row['c_self_scored'] and ':vip:' in row['match_id']
                    counter['candidate_self_scored_rows'] += 1
                    whites = row['white_count']
                    wall = observation['remaining_tile_count']
                    phase = row['phase']
                    opportunity = row['current_opportunity']
                    category = None
                    if type(wall) is int and wall >= 36:
                        if phase == 'draw':
                            if (whites >= 2 and opportunity['legal_hu'] and
                                opportunity['immediate_fans'] and max(opportunity['immediate_fans']) <= 2):
                                category = 'multiwhite-small-hu'
                            elif not opportunity['legal_hu']:
                                category = 'multiwhite-nonhu' if whites >= 2 else 'zero-white-nonhu' if whites == 0 else 'one-white-nonhu'
                        elif phase.startswith('response_') and whites >= 1:
                            category = 'response'
                    if category:
                        counter['eligible:' + category] += 1
                        digest = hashlib.sha256(row['decision_id'].encode()).hexdigest()
                        old = best[category].get(row['root_id'])
                        if old is None or digest < old[0]:
                            best[category][row['root_id']] = (digest, short_row(row, category=category, source_path=path))
                for root, round_no, rotation in rare_targets:
                    if (row['root_id'] != f't48-qualifier-confirmation:{root:03}' or
                        observation['round_no'] != round_no or ''.join(map(str,row['permutation'])) != rotation):
                        continue
                    arm = 'C' if ':vip:' in row['match_id'] else 'A'
                    key = f'{root:03}:{round_no}:{rotation}:{arm}'
                    bucket = rare_rows.setdefault(key, [])
                    high = rare_seen_whites.get(key,-1)
                    reason = 'first-focal-observation' if not bucket else 'current-legal-hu' if row['current_opportunity']['legal_hu'] else 'new-white-inventory' if row['white_count'] > high else None
                    rare_seen_whites[key] = max(high,row['white_count'])
                    if reason:
                        bucket.append(short_row(row, category=reason, source_path=path))
        print({'source_block': path.parent.name, 'raw_rows_read': counter['raw_rows'],
               'candidate_self_scored_rows': counter['candidate_self_scored_rows']}, flush=True)
    used, selected, strata = set(), [], {}
    for category, maximum in counts:
        rows = sorted(best[category].values(), key=lambda item:item[0])
        found = []
        for digest,row in rows:
            if row['root_id'] not in used:
                used.add(row['root_id'])
                row['selection_digest'] = digest
                found.append(row)
                if len(found) == maximum:
                    break
        strata[category] = len(found)
        selected.extend(found)
    assert counter['raw_rows'] == closure['decision_windows']
    assert len(selected) == len(used) == 16 and all(strata[k] == v for k,v in counts)
    assert len(rare_rows) == 10 and all(rows for rows in rare_rows.values())
    stable = all(sha(Path(path)) == digest for path,digest in frozen.items())
    assert stable
    save('NATURAL-PUBLIC-CASES.json', {'schema':'t58-natural-public-development-cases/1',
        'selection_counts':strata, 'independent_roots':len(used), 'cases':selected,
        'scope':'development from already exposed confirmation, no terminal-outcome criterion or action gold label'})
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'RARE-PUBLIC-PREFIXES.json.gz'),'xb') as stream:
        stream.write(canonical({'schema':'t58-result-selected-public-prefixes/1',
            'paths':rare_rows, 'scope':'current-visible prefixes, result-selected diagnostics, A/C may differ in starting dealer/hand'}) + b'\n')
    save('PUBLIC-EXTRACTION-CLOSURE.json', {'schema':'t58-public-extraction-closure/1',
        'complete':True, 'source_stable':stable, 'raw_rows':dict(counter),
        'natural_cases':16,'natural_independent_roots':16,'stratum_counts':strata,
        'rare_paths':10,'rare_recorded_windows':sum(len(r) for r in rare_rows.values()),
        'actual_new_score_graph_world_table_model_calls':0,'strength_or_online_admission':False})
    print({'complete':True,'natural_cases':16,'independent_roots':16,'rare_paths':10},flush=True)


if __name__ == '__main__':
    main()
