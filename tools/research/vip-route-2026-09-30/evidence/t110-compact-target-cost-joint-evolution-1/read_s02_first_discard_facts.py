"""只读已闭开发的同起点事实，区分改弃牌与已证实牌效增强。

不评分、不重算规则、不复打、不读取T112确认成绩。自然准备距离只
对应不借白的面子准备，不含将；公开未见库存含他家暗牌，不是牌山概率。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1'

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


def facts(waiting):
    """摘取同一规则源已给事实，不把未知库存补成零或概率。"""
    preparation = waiting['natural_preparation']
    structure = waiting['structure']
    return {
        'standard_shanten': structure['standard_shanten'],
        'seven_pairs_shanten': structure['seven_pairs_shanten'],
        'natural_pair_count': structure['natural_pair_count'],
        'natural_set_draw_lower_bound': preparation['natural_draw_lower_bound'],
        'natural_set_discard_lower_bound': preparation['natural_discard_lower_bound'],
        'natural_set_improvement_code_width': waiting['natural_preparation_code_width'],
        'standard_useful_codes': waiting['standard_useful_codes'],
        'legal_hu_code_width': waiting['legal_hu_code_width'],
        'whites_held': structure['whites_held'],
        'condition_baotou': waiting['baotou'], 'condition_chain_count': waiting['chain_count'],
        'qualification_scope': waiting['qualification_scope'],
        'qualification_missing_reason': waiting['qualification_missing_reason'],
    }


def main():
    """按16源固定代表逐一读事实，只有距离相同时单独统计自然准备宽度。"""
    path = _project_file(_PROJECT_ROOT, HERE / 'S02-PUBLIC-FIRST-CASES.json')
    cases = json.loads(path.read_text())['cases']
    views_path = _project_file(_PROJECT_ROOT, HERE / 'S02-PUBLIC-FIRST-CASE-VIEWS.jsonl.gz')
    with gzip.open(views_path, 'rt') as stream:
        views = {row['view_sha256']: row['view'] for row in map(json.loads, stream)}
    counts, rows = Counter(), []
    for case in cases:
        assert case['public_prefix_equal'] and case['not_optimal_action_gold']
        assert case['arms']['P']['view_sha256'] == case['arms']['C']['view_sha256']
        view = views[case['arms']['P']['view_sha256']]
        nodes = {n['node_key']: n for n in view['nodes']}
        actions = {a['action_key']: a for a in view['actions']}
        chosen = {arm: case['arms'][arm]['first_action'] for arm in ('P', 'C')}
        row = {'label': case['label'], 'current_Hu_legal': 'hu' in case['legal_action_keys'],
               'parent_action': chosen['P'], 'child_action': chosen['C'], 'waiting_facts': {}}
        for arm, action in chosen.items():
            node = nodes[actions[action]['node_key']]
            row['waiting_facts'][arm] = facts(node['waiting']) if node['waiting'] is not None else None
        if all(action.startswith('discard:') for action in chosen.values()):
            counts['discard_to_discard_representative_roots'] += 1
            p, c = row['waiting_facts']['P'], row['waiting_facts']['C']
            assert p is not None and c is not None
            same = p['standard_shanten'] == c['standard_shanten'] and (
                p['natural_set_draw_lower_bound'] == c['natural_set_draw_lower_bound'])
            row['same_standard_shanten_and_natural_preparation_distance'] = same
            if same:
                counts['same_distance_representative_roots'] += 1
                delta = c['natural_set_improvement_code_width'] - p['natural_set_improvement_code_width']
                row['natural_preparation_width_delta_at_same_distance'] = delta
                counts['natural_preparation_width_' + ('larger' if delta > 0 else 'smaller' if delta < 0 else 'same')] += 1
            else:
                counts['distance_changed_no_width_only_label'] += 1
        elif chosen['P'] == 'hu' and chosen['C'].startswith('discard:'):
            counts['hu_to_wait_representative_roots'] += 1
            c = row['waiting_facts']['C']
            assert c is not None
            ready = c['standard_shanten'] == 0 or c['seven_pairs_shanten'] == 0
            row['structural_tenpai_preserved_after_child_discard'] = ready
            counts['hu_to_wait_structural_tenpai_preserved' if ready else 'hu_to_wait_structural_tenpai_lost'] += 1
        else:
            counts['claim_change_representative_roots'] += 1
        rows.append(row)
    result = {'scope': 'all16 fixed-order first-case development representatives; not all changed decisions or causal outcomes',
        'input_sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (path, views_path)},
        'counts': dict(counts), 'cases': rows, 'new_rules_scores_models_worlds_tables': 0,
        'confirmation_outcomes_read': False, 'formula_changed': False,
        'limits': ['natural preparation is ordinary natural sets without a pair or white borrowing',
                   'same ordinary and natural distance does not guarantee equal seven-pairs or target opportunity',
                   'structural tenpai is not a guarantee of lawful future Hu or a correct wait',
                   'width is a factual support view, not a probability or verified net gain']}
    with (_project_file(_PROJECT_ROOT, HERE / 'S02-FIRST-DISCARD-FACTS.json')).open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print({'counts': dict(counts), 'new_business_calls': 0, 'confirmation_outcomes_read': False}, flush=True)


if __name__ == '__main__':
    main()
