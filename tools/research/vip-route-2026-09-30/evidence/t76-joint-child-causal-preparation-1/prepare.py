"""候选签收后准备18窗子代/共同父代诊断；只读证据，不执行世界。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t76-joint-child-causal-preparation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from pathlib import Path
import gzip
import hashlib
import json
import sys

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents

HERE = Path(__file__).resolve().parent
EVIDENCE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
T74 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t74-hu-versus-wait-common-parent-1/revision-3')
T75 = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1')


def canonical(value):
    """规范JSON字节用于严格来源身份，不改写旧证据。"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def pin(path):
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(path, value):
    with Path(path).open('xb') as stream:
        stream.write(canonical(value) + b'\n')


def main():
    old = json.loads((_project_file(_PROJECT_ROOT, T74 / 'ROOT-READBACK.json')).read_text())
    child_readback = json.loads((_project_file(_PROJECT_ROOT, T75 / 'ROOT-READBACK.json')).read_text())
    assert old['complete'] and child_readback['complete']
    for directory, closed in [(T74, old), (T75, child_readback)]:
        for name, digest in closed['files'].items():
            assert pin(directory / name) == digest, name
    old_plan = json.loads((_project_file(_PROJECT_ROOT, T74 / 'PREPARED.json')).read_text())
    for name, digest in old_plan['files'].items():
        assert pin(name) == digest, name
    batch_file = _project_file(_PROJECT_ROOT, T75 / 'S01-generation.batch.json')
    batch = VipEohBatch.read(batch_file)
    parent_package = _project_file(_PROJECT_ROOT, EVIDENCE / 't62-earned-highfan-joint-revision-preparation-1/S02-model-output')
    child_package = _project_file(_PROJECT_ROOT, T75 / 'S01-model-output')
    parent, child = (load_vip_parents([package], batch)[0] for package in [parent_package, child_package])
    assert parent['identity'] == old_plan['parent_identity']
    assert child['identity'] == child_readback['candidate_identity']
    scored = json.loads((_project_file(_PROJECT_ROOT, T75 / 'PUBLIC-PROBE-CLOSURE.json')).read_text())
    assert scored['complete_all_windows']
    by_root = {row['label']: row for row in scored['rows'] if row['label'].startswith('t74:')}
    assert len(by_root) == 18
    with gzip.open(_project_file(_PROJECT_ROOT, T74 / 'SOURCE-MATERIALS.json.gz'), 'rt') as stream:
        original = json.load(stream)['roots']
    roots = []
    actual_arm_budget = 18
    for root in original:
        row = by_root[root['root_id']]
        assert row['view_sha256'] == root['expected_input_sha256']
        child_first = row['first_action']
        expected_child_scores = {entry['action_key']: {'score': entry['score'], 'trace': entry['trace']}
                                 for entry in row['scores']}
        assert child_first in expected_child_scores
        closed_directory = _project_file(_PROJECT_ROOT, T74 / root['root_id'].replace(':', '-'))
        baseline = json.loads((closed_directory / 'ROOT-RESULT.json').read_text())
        # 首手相同后续同父时，旧P/F已是完全相同的真实路径，显式别名省重复。
        if child_first == root['parent_first']:
            alias = {'source_arm': 'P', 'directory': str(closed_directory),
                     'actual_new_execution': False, 'first_action': child_first}
        elif child_first == root['forced_first']:
            alias = {'source_arm': 'F', 'directory': str(closed_directory),
                     'actual_new_execution': False, 'first_action': child_first}
        else:
            alias = None
            actual_arm_budget += 1
        roots.append({**root, 'child_first': child_first,
                      'expected_child_scores': expected_child_scores,
                      'parent_closed_reference': baseline['results']['P'],
                      'common_parent_B_alias': alias})
    assert len(roots) == 18 and 18 <= actual_arm_budget <= 36
    save(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-SELECTION.json'), {
        'schema': 't76-same18-child-causal-selection/1', 'windows': 18, 'mothers': 16,
        'selection_rule': 'all unchanged 18 T74 action-before-selected sources; no choice by new child endpoint',
        'child_endpoint_used_for_selection': False,
        'roots': [{'root_id': root['root_id'], 'child_first': root['child_first'],
                   'common_parent_B_alias': root['common_parent_B_alias']} for root in roots],
        'planned_actual_C_arms': 18, 'planned_actual_B_arms': actual_arm_budget - 18,
        'old_reference_arms_not_counted_as_new_executions': 36,
        'new_rules_scores_worlds_tables_models': 0,
    })
    with gzip.open(_project_file(_PROJECT_ROOT, HERE / 'SOURCE-MATERIALS.json.gz'), 'xb') as stream:
        stream.write(canonical({'schema': 't76-private-recovery-material/1', 'roots': roots}) + b'\n')
    files = dict(old_plan['files'])
    sources = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'SOURCE-SELECTION.json'), _project_file(_PROJECT_ROOT, HERE / 'SOURCE-MATERIALS.json.gz'),
               _project_file(_PROJECT_ROOT, HERE / 'run.py'), _project_file(_PROJECT_ROOT, T74 / 'ROOT-READBACK.json'), _project_file(_PROJECT_ROOT, T75 / 'ROOT-READBACK.json'),
               _project_file(_PROJECT_ROOT, T75 / 'PUBLIC-PROBE-CLOSURE.json'), batch_file]
    for package in [parent_package, child_package]:
        sources.extend(package / name for name in ['candidate.py', 'generation.json', 'batch.json'])
    for root in roots:
        directory = _project_file(_PROJECT_ROOT, T74 / root['root_id'].replace(':', '-'))
        sources.extend(directory / name for name in ['ROOT-RESULT.json', 'P-RESULT.json', 'F-RESULT.json',
                                                     'P-outcome.json', 'F-outcome.json'])
    files.update({str(path): pin(path) for path in sources})
    save(_project_file(_PROJECT_ROOT, HERE / 'PREPARED.json'), {
        'schema': 't76-child-common-parent-preparation/1', 'status': 'prepared_no_START',
        'python_version': sys.version, 'batch_file': str(batch_file),
        'parent_package': str(parent_package), 'child_package': str(child_package),
        'parent_identity': parent['identity'], 'child_identity': child['identity'],
        'files': files, 'windows': 18, 'mothers': 16,
        'arm_order': ['C', 'B'], 'planned_actual_C_arms': 18,
        'planned_actual_B_arms': actual_arm_budget - 18,
        'budgets': {**old_plan['budgets'], 'max_continuations': actual_arm_budget},
        'normal_r18_fallback_allowed': False, 'new_natural_tables_or_sources': 0,
        'new_rules_scores_worlds_tables_models': 0,
    })
    print({'prepared': True, 'actual_C_arms': 18, 'actual_B_arms': actual_arm_budget - 18,
           'aliases_B': 36 - actual_arm_budget, 'new_business_calls': 0})


if __name__ == '__main__':
    main()
