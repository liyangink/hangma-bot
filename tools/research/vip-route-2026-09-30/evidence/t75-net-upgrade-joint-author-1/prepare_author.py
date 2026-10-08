"""纯文件准备下一联合提案，封公开反馈和新母源，不评分或推进世界。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from datetime import datetime, timezone
from pathlib import Path
import gzip
import hashlib
import json

from hangma_bot.offline.vip_eoh_generate import (
    VipEohBatch, load_vip_parents, run_vip_eoh_generate,
)

HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
PARENT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t62-earned-highfan-joint-revision-preparation-1')
CAUSAL = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t74-hu-versus-wait-common-parent-1/revision-3')


def canonical(value):
    """严格JSON字节只用于证据身份，不模拟数学评分。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def uniform(label):
    """标签派生固定随机数，只用于离线对手身份，非摸牌概率。"""
    return int.from_bytes(hashlib.sha256(label.encode()).digest()[:8], 'big') / 2**64


def main():
    closed = json.loads((_project_file(_PROJECT_ROOT, CAUSAL / 'ROOT-READBACK.json')).read_text())
    assert closed['complete'] and closed['source_stable']
    for name, digest in closed['files'].items():
        assert pin(_project_file(_PROJECT_ROOT, CAUSAL / name)) == digest, name
    selection = json.loads((_project_file(_PROJECT_ROOT, CAUSAL / 'SOURCE-SELECTION.json')).read_text())
    source_windows = {r['root_id']: r['source_window'] for r in selection['roots']}
    with gzip.open(_project_file(_PROJECT_ROOT, CAUSAL / 'views.jsonl.gz'), 'rt') as stream:
        views = {r['view_sha256']: r for r in map(json.loads, stream)}
    targets = {}
    with gzip.open(_project_file(_PROJECT_ROOT, CAUSAL / 'decisions.jsonl.gz'), 'rt') as stream:
        for row in map(json.loads, stream):
            if row['arm'] == 'P' and row['window_key'] == source_windows[row['root_id']]:
                assert row['focal_vip'] and row['c_self_scored']
                targets[row['root_id']] = row
    assert len(targets) == 18
    feedback_rows = []
    public_rows = []
    for result in closed['roots']:
        target = targets[result['root_id']]
        sha = target['scoring_execution']['input_capture']['view_sha256']
        assert hashlib.sha256(canonical(views[sha]['view'])).hexdigest() == sha
        feedback_rows.append({'result': result, 'public_observation': target['observation'],
                              'source_window': target['window_key'],
                              'original_full_scores_and_traces': target['candidates'],
                              'original_full_view_sha256': sha})
        public_rows.append({'root_id': result['root_id'], 'view_sha256': sha,
                            'view': views[sha]['view']})
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-TARGET-VIEWS.jsonl.gz'), 'xb') as stream:
        for row in public_rows:
            stream.write(canonical(row) + b'\n')
    save('PUBLIC-CAUSAL-FEEDBACK.json', {
        'schema': 't75-public-causal-author-feedback/1',
        'rows': feedback_rows, 'summary': closed['descriptive_stats'],
        'by_category': closed['by_public_category'],
        'scope': 'selected exposed windows; endpoints are teacher feedback, not natural probabilities or action gold labels',
        'hidden_world_or_future_tile_sequence_included': False,
    })
    permutations = [[(seat + turn) % 4 for seat in range(4)] for turn in range(4)]
    roots = {}
    for stage, count in [('pilot', 8), ('reserved_confirmation', 128)]:
        roots[stage] = []
        for index in range(1, count + 1):
            root_id = f't75-qualifier-{stage}:{index:03}'
            seed = int.from_bytes(hashlib.sha256((root_id + ':20261002:new-source').encode()).digest()[:8], 'big') % (2**63)
            roots[stage].append({'root_id': root_id, 'seed': seed, 'permutations': permutations})
    all_seeds = [r['seed'] for rows in roots.values() for r in rows]
    assert len(set(all_seeds)) == 136
    old_roots = json.loads((_project_file(_PROJECT_ROOT, EVIDENCE / 't59-qualifier-highfan-credit-author-1/FRESH-ROOTS-BEFORE-AUTHOR.json')).read_text())
    old_seeds = {r['seed'] for key in ['pilot', 'reserved_confirmation'] for r in old_roots[key]}
    assert not old_seeds.intersection(all_seeds)
    save('FRESH-ROOTS-BEFORE-AUTHOR.json', {
        'schema': 't75-new-source-before-author/1', **roots,
        'rounds': 8, 'initial_scores': [0, 0, 0, 0],
        'scope': 'no worlds generated; author must not read; confirmation withheld',
    })
    compositions = {}
    for stage, rows in roots.items():
        compositions[stage] = {}
        for fraction in [0.5, 0.6, 0.75]:
            items = []
            for row in rows:
                draws = [uniform(row['root_id'] + f':opponent:{seat}') for seat in [1, 2, 3]]
                weak_types = ['automatic_like' if uniform(row['root_id'] + f':weak-type:{seat}') < .5 else 'normal_v0' for seat in [1, 2, 3]]
                types = [weak if draw < fraction else 'r18' for draw, weak in zip(draws, weak_types)]
                items.append({**row, 'weak_fraction_setting': fraction,
                              'draw_uniforms': draws, 'opponent_types_logical_1_2_3': types,
                              'actual_weak_count': sum(t != 'r18' for t in types),
                              'paired_A_C_same_composition': True})
            compositions[stage][str(fraction)] = items
    save('COMPOSITIONS-BEFORE-AUTHOR.json', {
        'schema': 't75-compositions-before-author/1', **compositions,
        'main_weak_fraction': 0.6, 'weak_split_automatic_normal_v0': [0.5, 0.5],
        'human_prior_not_platform_measured': True, 'A_C_same_per_root_four_rotations': True,
    })
    raw_batch = json.loads((_project_file(_PROJECT_ROOT, PARENT / 'S02-generation.batch.json')).read_text())
    raw_batch['batch_id'] = 'vip-t75-net-upgrade-first-joint-author-20261002'
    raw_batch['budgets']['model_calls'] = 1
    save('S01-generation.batch.json', raw_batch)
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'S01-generation.batch.json')
    batch = VipEohBatch.read(batch_file)
    parents = load_vip_parents([_project_file(_PROJECT_ROOT, PARENT / 'S02-model-output')], batch)
    assert len(parents) == 1 and parents[0]['identity']['candidate_id'] == 'b3f133b8c6beb32d248a19d567808387d0af57d47f2c3f43103a04258034bef2'
    save('PARENTS-FROZEN.json', parents)
    feedback = (_project_file(_PROJECT_ROOT, HERE / 'FROZEN-FEEDBACK.txt')).read_text()
    emission = run_vip_eoh_generate(batch_file=batch_file, out_dir=_project_file(_PROJECT_ROOT, HERE / 'S01-prompt-emission'),
                                  operator='m1', parent_paths=(_project_file(_PROJECT_ROOT, PARENT / 'S02-model-output'),),
                                  feedback=feedback)
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'FROZEN-FEEDBACK.txt'), _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-TASK.txt'),
             _project_file(_PROJECT_ROOT, HERE / 'PUBLIC-CAUSAL-FEEDBACK.json'), _project_file(_PROJECT_ROOT, HERE / 'PUBLIC-TARGET-VIEWS.jsonl.gz'),
             _project_file(_PROJECT_ROOT, HERE / 'FRESH-ROOTS-BEFORE-AUTHOR.json'), _project_file(_PROJECT_ROOT, HERE / 'COMPOSITIONS-BEFORE-AUTHOR.json'),
             _project_file(_PROJECT_ROOT, HERE / 'PARENTS-FROZEN.json'), batch_file, _project_file(_PROJECT_ROOT, CAUSAL / 'ROOT-READBACK.json')]
    save('AUTHOR-PREPARATION-CLOSED.json', {
        'schema': 't75-net-upgrade-author-preparation/1', 'status': 'prepared_no_author',
        'operator': 'm1', 'proposal_number_in_new_joint_batch': 1,
        'max_new_proposals_in_joint_batch': 2, 'true_parent_candidate_id': parents[0]['identity']['candidate_id'],
        'prompt_sha256': emission['prompt_sha256'], 'frozen_files': {str(p): pin(p) for p in files},
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'actual_new_models_scores_rules_worlds_tables': 0,
    })
    print({'prepared': True, 'public_targets': 18, 'fresh_roots_reserved': 136,
           'new_models_scores_rules_worlds_tables': 0})


if __name__ == '__main__':
    main()
