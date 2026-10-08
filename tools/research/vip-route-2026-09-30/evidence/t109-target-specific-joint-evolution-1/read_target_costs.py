"""纯读冻结DTO和源码，核对新目标成本是否仍折平；不调用候选或规则。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t109-target-specific-joint-evolution-1'

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
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def canonical(value):
    """完整公开输入按原规范核摘要，未知与版本保持原样。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def main():
    """只重建已核源码中的一项排序成本，不把它当完整评分或效果证据。"""
    source = (_project_file(_PROJECT_ROOT, HERE / 'S01-model-output/candidate.py')).read_bytes()
    source_sha = hashlib.sha256(source).hexdigest()
    assert source_sha == '5b4db704e3f06abb50be249ca387a59ef6112b94a06f6b4a427d0be7602e47ec'
    tree = ast.parse(source.decode())
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ('OWNDISCARD', 'OWNWHITE', 'OWNTERMINAL'):
                constants[node.targets[0].id] = ast.literal_eval(node.value)
    assert constants == {'OWNDISCARD': 0.18, 'OWNWHITE': 0.32, 'OWNTERMINAL': 0.5}
    target_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'target_route')
    actual = next(n.value for n in target_fn.body if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == 'effort' for t in n.targets))
    expected = ast.parse('float(drawneed) + OWNDISCARD * float(naturaldrop) + OWNWHITE * float(whitedrop) + OWNTERMINAL * float(terminal)', mode='eval').body
    assert ast.dump(actual, include_attributes=False) == ast.dump(expected, include_attributes=False)
    totals = {'full_inputs': 0, 'waiting_nodes': 0, 'standard_predecessor_targets': 0,
              'nodes_with_different_target_draw_needs': 0,
              'different_need_nodes_still_all_same_effort': 0,
              'different_need_nodes_effort_distinguished': 0}
    examples = []
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'PUBLIC-PANEL-VIEWS.jsonl.gz'), 'rt') as stream:
        for row in map(json.loads, stream):
            assert hashlib.sha256(canonical(row['view'])).hexdigest() == row['view_sha256']
            totals['full_inputs'] += 1
            for node in row['view']['nodes']:
                waiting = node['waiting']
                if waiting is None:
                    continue
                totals['waiting_nodes'] += 1
                candidates = []
                for target in waiting['structure']['targets']:
                    if target['family'] != 'standard' or target['target_stage'] != 'waiting_predecessor':
                        continue
                    draw = target['target_natural_draw_lower_bound']
                    drop = target['target_natural_discard_lower_bound']
                    white = target['target_white_discard_lower_bound']
                    terminal = 1 if target['requires_terminal_draw'] else 0
                    assert all(type(v) is int and v >= 0 for v in (draw, drop, white, terminal))
                    effort = draw + constants['OWNDISCARD'] * drop + constants['OWNWHITE'] * white + constants['OWNTERMINAL'] * terminal
                    candidates.append({'retained_whites': target['retained_whites'], 'draw_need': draw,
                        'natural_drop': drop, 'white_drop': white, 'terminal': terminal, 'effort': effort})
                totals['standard_predecessor_targets'] += len(candidates)
                if len({r['draw_need'] for r in candidates}) > 1:
                    totals['nodes_with_different_target_draw_needs'] += 1
                    collapsed = len({r['effort'] for r in candidates}) == 1
                    totals['different_need_nodes_still_all_same_effort' if collapsed else 'different_need_nodes_effort_distinguished'] += 1
                    if len(examples) < 3:
                        examples.append({'input_sha256': row['view_sha256'], 'node_key': node['node_key'],
                            'natural_preparation_draw_need_reference_only': waiting['natural_preparation']['natural_draw_lower_bound'],
                            'targets': candidates})
    assert totals['full_inputs'] == 97
    result = {'schema': 't109-own-target-cost-algebra/1', 'complete': True,
        'candidate_source_sha256': source_sha, 'constants': constants, 'counts': totals, 'examples': examples,
        'scope': 'exact source expression and exposed DTO component reconstruction only; not full candidate score or strength',
        'new_rules_scores_models_worlds_tables': 0, 'universal_all_hand_theorem': False}
    with (_project_file(_PROJECT_ROOT, HERE / 'S01-OWN-TARGET-COST-ALGEBRA.json')).open('xb') as stream:
        stream.write(canonical(result) + b'\n')
    print({'component_readback_complete': True, **totals})


if __name__ == '__main__':
    main()
