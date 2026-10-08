"""机械与行为检查后复用四个已闭合正反来源，冻结整段新策略续打。"""

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
import argparse
import ast
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents

HERE = Path(__file__).resolve().parent
OLD = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1')


def pin(path):
    """绑定实际恢复材料及策略源码，不将历史结果迁移给新策略。"""
    raw = Path(path).read_bytes()
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def save(path, value):
    """只创建本批新计划；单位为当前单局续打，不冒充完整桌。"""
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main(slot):
    """保留正、负、零四来源六目标，共18条父／子／R18续打。"""
    probe = _project_file(_PROJECT_ROOT, HERE / (slot + '-public-probe'))
    public = json.loads((probe / 'ROOT-READBACK.json').read_text())
    assert public['complete'] and public['actual_tool_terminal']['exit_code'] == 0
    assert public['behavior_changed'], '没有实际首选变化，不开昂贵新续打'
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json')
    batch = VipEohBatch.read(batch_file)
    package = _project_file(_PROJECT_ROOT, HERE / (slot + '-model-output'))
    child = load_vip_parents([package], batch)[0]
    parent_package = Path(json.loads((_project_file(_PROJECT_ROOT, HERE / 'PARENT-IDENTITY.json')).read_text())['path'])
    parent = load_vip_parents([parent_package], batch)[0]
    assert child['identity'] == public['candidate_identity']
    jobs = []
    for label in ('continuation-root033', 'continuation-root009', 'fresh-root003-loss', 'fresh-root030-gain'):
        original = _project_file(_PROJECT_ROOT, OLD / ('S02-' + label))
        old_read = json.loads((original / 'ROOT-READBACK.json').read_text())
        assert old_read['complete'] and old_read['actual_tool_terminal']['exit_code'] == 0
        plan = json.loads((original / 'RUN-PREPARED.json').read_text())
        assert plan['candidate_identity'] == parent['identity']
        out = _project_file(_PROJECT_ROOT, HERE / (slot + '-' + label))
        out.mkdir(exist_ok=False)
        # 整段子策略入口已经在T108实际核验。原样复用，不强制首手或续打回旧策略。
        names = ('run_causal.py', 'io_helpers.py', 'readback.py',
                 'TEACHER-SOURCE-TRACES.json.gz', 'PUBLIC-TARGETS.json')
        for name in names:
            (out / name).write_bytes((original / name).read_bytes())
            if name.endswith('.py'):
                ast.parse((out / name).read_text())
        plan.update(schema='t110-whole-child-known-cases/1', generation_file=str(batch_file),
            raw_source_file=str(parent_package / 'candidate.py'),
            child_source_file=str(package / 'candidate.py'), child_identity=child['identity'],
            status='prepared_not_started',
            scope='T109 whole child on exposed original starts; no first-action forcing or causal action gold',
            predecessor_results={'directory': str(original), 'outcomes_not_transferred': True},
            published=False, fresh_result_blind_confirmation=False, force_first_action=False)
        sources = [Path(__file__), batch_file, _project_file(_PROJECT_ROOT, HERE / 'EVOLUTION-PLAN.json'),
            _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-PREPARATION-CLOSED.json'),
            package / 'candidate.py', package / 'generation.json',
            parent_package / 'candidate.py', parent_package / 'generation.json',
            probe / 'ROOT-READBACK.json', probe / 'ACTUAL-READBACK-TERMINAL.json',
            original / 'RUN-PREPARED.json', original / 'ROOT-READBACK.json',
            *[out / name for name in names]]
        plan['files'] = {str(p): pin(p) for p in sources}
        save(out / 'RUN-PREPARED.json', plan)
        jobs.append({'directory': str(out), 'targets': len(plan['targets']),
                     'continuations': plan['max_continuations']})
    assert sum(j['continuations'] for j in jobs) == 18
    save(_project_file(_PROJECT_ROOT, HERE / (slot + '-CONTINUATION-PREPARATION.json')), {'complete': True, 'jobs': jobs,
        'independent_exposed_sources': 4, 'targets': 6, 'current_hand_continuations': 18,
        'actual_new_models_rules_scores_worlds_tables': 0, 'historical_results_transferred': False,
        'full_child_formula_every_focal_decision': True, 'fresh_natural_strength': False})
    print({'prepared': True, 'jobs': 4, 'current_hand_continuations': 18, 'new_business_calls': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', choices=('S01', 'S02'), required=True)
    main(parser.parse_args().slot)
