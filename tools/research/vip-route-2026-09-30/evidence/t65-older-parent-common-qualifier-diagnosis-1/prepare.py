"""固定T64全部八根，补旧T51同来源完整桌；不选成功源，不生成新公式。

64桌费用包括32旧父桌和32重跑A；同ID只用于隔离的离线实验目录，
不访问平台。重复A用于核验完整路径，不能当32个新独立样本。
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
from datetime import datetime, timezone
import hashlib
import json

HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t51-t48-same-formula-efficiency-author-1')
CHILD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t64-second-joint-fresh-qualifier-pilot-1')
ENGINEERING = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t49-qualifier-opponent-behavior-1')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def save(name, value):
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    child = json.loads((_project_file(_PROJECT_ROOT, CHILD / 'CAMPAIGN-PLAN.json')).read_text())
    seal = json.loads((_project_file(_PROJECT_ROOT, CHILD / 'ROOT-READBACK.json')).read_text())
    assert seal['complete'] and seal['actual_tables'] == 64
    for name, digest in seal['files'].items():
        path = _project_file(_PROJECT_ROOT, CHILD / name)
        assert path.stat().st_size == digest['bytes'] and sha(path) == digest['sha256'], name
    pointer = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / 'CURRENT-RESEARCH-CANDIDATE-PACKAGE.json')).read_text())
    probe = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / pointer['probe_closure'])).read_text())
    assert probe['complete_all_windows'] and probe['candidate_identity'] == pointer['candidate_identity']
    assert pointer['candidate_identity']['candidate_id'] == '39325684bcedad953cb858198d06b2ebe85dbd08943bad583f2ea3593ee7415c'
    prerequisite = [_project_file(_PROJECT_ROOT, AUTHOR / 'CURRENT-RESEARCH-CANDIDATE-PACKAGE.json'), _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_batch']),
        _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_package'] / 'generation.json'), _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_package'] / 'candidate.py'),
        _project_file(_PROJECT_ROOT, AUTHOR / pointer['probe_closure']), _project_file(_PROJECT_ROOT, AUTHOR / 'RECOVERY-NATURAL-EQUIVALENCE-CLOSURE.json'),
        _project_file(_PROJECT_ROOT, CHILD / 'CAMPAIGN-PLAN.json'), _project_file(_PROJECT_ROOT, CHILD / 'CAMPAIGN-CLOSURE.json'), _project_file(_PROJECT_ROOT, CHILD / 'ROOT-READBACK.json'),
        Path(child['compositions_file']), _project_file(_PROJECT_ROOT, ENGINEERING / 'smoke-1/summary.json'),
        _project_file(_PROJECT_ROOT, ENGINEERING / 'PILOT-ROOT-CLOSE-AUDIT.json'), Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'pilot_block.py'),
        _project_file(_PROJECT_ROOT, HERE / 'close_campaign.py'), _project_file(_PROJECT_ROOT, HERE / 'root_readback.py')]
    pins = {str(p.resolve()): sha(p) for p in prerequisite}
    plan = dict(child)
    plan.update(schema='t65-fixed-old-parent-common-source-plan/1',
        created_at_utc=datetime.now(timezone.utc).isoformat(), candidate_identity=pointer['candidate_identity'],
        compared_child_identity=child['candidate_identity'], prerequisite_sha256=pins,
        primary='old T51 minus R18 and T64 child minus old T51 on all same8 roots; descriptive development only',
        stage='all eight already exposed T64 roots; repeated A counts as real cost, not new independent sample',
        seed_history='exact T64 full8 roots/compositions/permutations/prefix; no outcome-selected append',
        known_T64_net_mean=-0.75, known_T64_root_interval=[-15.0, 13.1875],
        repeated_baseline_tables=32, old_parent_tables=32, same_match_id_prefix_in_isolated_offline_outputs=True,
        new_authors=0, reserved_confirmation_roots_not_consumed=128)
    save('CAMPAIGN-PLAN.json', plan)
    for block in range(1, 5):
        item = json.loads((_project_file(_PROJECT_ROOT, CHILD / ('BLOCK-' + format(block, '02d') + '-PLAN.json'))).read_text())
        item.update(schema='t65-common-old-parent-block-plan/1', prerequisite_sha256=pins,
            scope='all T64 exposed roots; old parent diagnostic and repeated A reproduction, not confirmation')
        save('BLOCK-' + format(block, '02d') + '-PLAN.json', item)
    print({'prepared': True, 'fixed_already_exposed_roots': 8, 'old_parent_tables': 32,
           'repeated_A_tables': 32, 'new_models_worlds_tables_in_preparation': 0})


if __name__ == '__main__':
    main()
