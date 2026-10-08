"""纯读共同八根：重复A全座位路径一致，再对比旧父与T64子。

只消除两个VIP身份引起的离线game_id差异；不抹序号、手牌、
合法动作或其他公开事实。分歧仅定位到第一处，不自授单手因果。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t65-older-parent-common-qualifier-diagnosis-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
from collections import defaultdict
import gzip
import hashlib
import json
import statistics

HERE = Path(__file__).resolve().parent
CHILD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t64-second-joint-fresh-qualifier-pilot-1')


def normalize_ids(value):
    if isinstance(value, dict):
        return {k: '<common-table>' if k == 'game_id' else normalize_ids(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_ids(v) for v in value]
    return value


def read(folder):
    closed = json.loads((folder / 'CAMPAIGN-CLOSURE.json').read_text())
    assert closed['whole_batch_valid'] and closed['actual_started_tables'] == 64
    paths = defaultdict(list)
    endpoints = defaultdict(dict)
    original_A = {}
    for block in range(1, 5):
        out = folder / ('block-' + format(block, '02d'))
        with (out / 'results.jsonl').open() as stream:
            for line in stream:
                r = json.loads(line)
                pair = (r['scenario_id'], tuple(r['seat_permutation']))
                seat = pair[1][0]
                arm = 'C' if r['policy_ids_by_seat'][seat].startswith('vip:') else 'A'
                assert arm not in endpoints[pair]
                endpoints[pair][arm] = r['scores_after'][seat] - r['scores_before'][seat]
        with gzip.open(out / 'decisions.jsonl.gz', 'rt') as stream:
            for line in stream:
                r = json.loads(line)
                pair = (r['root_id'], tuple(r['permutation']))
                arm = 'C' if r['match_id'].rsplit(':vip:', 1)[-1] == closed['candidate_identity']['candidate_id'] else 'A'
                material = {k: r[k] for k in ('seat', 'observation', 'window_key', 'legal_action_keys', 'selected_action_key')}
                if arm == 'A':
                    original_A.setdefault(pair, []).append(material)
                paths[(pair, arm)].append(normalize_ids(material))
    return closed, endpoints, paths, original_A


def main():
    pclose, parent, ppaths, pA = read(HERE)
    cclose, child, cpaths, cA = read(CHILD)
    assert set(parent) == set(child) and len(parent) == 32
    root_deltas = defaultdict(list)
    divergences = []
    equal_C = 0
    equal_C_terminal = 0
    for pair in sorted(parent):
        assert pA[pair] == cA[pair], '重复R18完整公开路径不一致：' + str(pair)
        assert parent[pair]['A'] == child[pair]['A']
        root_deltas[pair[0]].append(child[pair]['C'] - parent[pair]['C'])
        equal_C_terminal += int(child[pair]['C'] == parent[pair]['C'])
        pp, cp = ppaths[(pair, 'C')], cpaths[(pair, 'C')]
        if pp == cp:
            equal_C += 1
            continue
        for index in range(max(len(pp), len(cp))):
            old = pp[index] if index < len(pp) else None
            new = cp[index] if index < len(cp) else None
            if old != new:
                same = old is not None and new is not None and all(old[k] == new[k] for k in ('seat', 'observation', 'window_key', 'legal_action_keys'))
                divergences.append({'root_id': pair[0], 'permutation': list(pair[1]),
                    'first_all_seat_row_index': index, 'same_visible_preaction_state': same,
                    'parent': old, 'child': new, 'C_minus_P_table_net': child[pair]['C'] - parent[pair]['C']})
                break
    means = {root: statistics.mean(values) for root, values in root_deltas.items()}
    net = statistics.mean(means.values())
    assert net == cclose['net_score_delta_per_table'] - pclose['net_score_delta_per_table']
    result = {'schema': 't65-common-parent-child-comparison/1', 'complete': True,
        'source_roots': 8, 'shared_pairs': 32, 'actual_new_tables_T65': 64,
        'repeated_A_full_public_tails_exact': 32, 'child_parent_complete_C_paths_equal': equal_C,
        'child_parent_focal_terminal_scores_equal': equal_C_terminal,
        'old_parent_minus_R18_mean': pclose['net_score_delta_per_table'],
        'child_minus_R18_mean': cclose['net_score_delta_per_table'], 'child_minus_old_parent_mean': net,
        'child_minus_old_parent_by_mother_root': means, 'first_public_divergences': divergences,
        'same_round_or_table_difference_not_single_action_causal_claim': True,
        'new_independent_roots_models_scores_worlds_tables_in_readback': 0,
        'not_confirmation_or_release': True,
        'source_close_sha256': {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (_project_file(_PROJECT_ROOT, HERE / 'CAMPAIGN-CLOSURE.json'), _project_file(_PROJECT_ROOT, CHILD / 'CAMPAIGN-CLOSURE.json'), _project_file(_PROJECT_ROOT, CHILD / 'ROOT-READBACK.json'))}}
    with (_project_file(_PROJECT_ROOT, HERE / 'COMMON-PARENT-CHILD-COMPARISON.json')).open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print({k: result[k] for k in ('complete', 'shared_pairs', 'repeated_A_full_public_tails_exact',
        'child_parent_complete_C_paths_equal', 'old_parent_minus_R18_mean', 'child_minus_old_parent_mean')})


if __name__ == '__main__':
    main()
