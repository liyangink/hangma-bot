"""为真实候选冻结原T101／整段新公式／R18续打，不再强制一手后回旧策略。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t108-target-cost-joint-evolution-1'

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
import difflib
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents

HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')


def pin(path):
    """只读原始字节身份，不评规则或评分。"""
    raw = Path(path).read_bytes()
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def save(path, value):
    """计划只新建；两个已知源是开发，不回收为确认。"""
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def replace_once(text, old, new):
    """对已核旧工具精确改接候选来源，匹配错误立即终止。"""
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main(slot):
    """机械全部完成后，冻结两来源四目标共12条整段当前单局续打。"""
    probe = _project_file(_PROJECT_ROOT, HERE / (slot + '-public-probe'))
    actual = json.loads((probe / 'CLOSURE.json').read_text())
    terminal = json.loads((probe / 'ACTUAL-TOOL-TERMINAL.json').read_text())
    assert actual['complete'] and terminal['verified_tool_terminal'] and terminal['exit_code'] == 0
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json')
    batch = VipEohBatch.read(batch_file)
    package = _project_file(_PROJECT_ROOT, HERE / (slot + '-model-output'))
    child = load_vip_parents([package], batch)[0]
    assert child['identity'] == actual['candidate_identity']
    parent_package = _project_file(_PROJECT_ROOT, E / 't101-joint-breadth-recovery-author-1/S02-model-output')
    parent = load_vip_parents([parent_package], batch)[0]
    old_runner = (_project_file(_PROJECT_ROOT, E / 't107-four-white-wait-credit-1/run_causal.py')).read_text()
    runner = old_runner
    runner = replace_once(runner, 'from hangma_bot.offline.forced_action import ForceFirstActionPolicy\n', '')
    runner = replace_once(runner, "    need(batch.identity(source) == plan['candidate_identity'], '当前执行身份不同')",
         "    need(batch.identity(source) == plan['candidate_identity'], '父执行身份不同')\n"
         "    child_source = Path(plan['child_source_file']).read_text()\n"
         "    need(batch.identity(child_source) == plan['child_identity'], '子执行身份不同')")
    runner = replace_once(runner, "            for arm in ('P','F','A'):", "            for arm in ('P','C','A'):")
    runner = replace_once(runner,
         "                fresh = call('runtime_constructor', build_qualifier_runtime, batch, source,\n",
         "                active_source = child_source if arm == 'C' else source\n"
         "                fresh = call('runtime_constructor', build_qualifier_runtime, batch, active_source,\n")
    runner = replace_once(runner,
         "                forced = ForceFirstActionPolicy(audited, target_window=target_window,\n"
         "                    forced_action_key=target['forced_first'], policy_id=policy_id+':T107:F') if arm == 'F' else None\n"
         "                policies = [forced if forced is not None else audited]",
         "                policies = [audited]")
    runner = replace_once(runner,
         "                if arm == 'F':\n"
         "                    need(forced.force_count == 1 and own[0].action_key == target['forced_first'], '首手干预未恰好一次')\n", '')
    runner = replace_once(runner, "                if arm != 'A':\n                    known = next",
         "                if arm == 'P':\n                    known = next")
    runner = replace_once(runner, "                    'forced_first_count':0 if forced is None else forced.force_count,",
         "                    'forced_first_count':0,")
    runner = replace_once(runner,
         "                'F_minus_P':per_target['F']['focal_net_score']-per_target['P']['focal_net_score'],",
         "                'C_minus_P':per_target['C']['focal_net_score']-per_target['P']['focal_net_score'],")
    runner = replace_once(runner,
         "            'scope':'two known-source interventions: early width choice and current hu versus wait; no frequency/deadline/strength/publication claim',",
         "            'scope':'known-source whole child formula continuation versus original parent and R18; no frequency/deadline/strength/publication claim',")
    runner = runner.replace('T107', 'T108').replace('t107-', 't108-')
    ast.parse(runner)
    jobs = []
    for old_name, label in [('t106-first-width-and-hu-credit-1', 'root033'),
                            ('t107-four-white-wait-credit-1', 'root009')]:
        old = _project_file(_PROJECT_ROOT, E / old_name)
        plan = json.loads((old / 'RUN-PREPARED.json').read_text())
        assert plan['candidate_identity'] == parent['identity']
        out = _project_file(_PROJECT_ROOT, HERE / (slot + '-continuation-' + label))
        out.mkdir(exist_ok=False)
        (out / 'run_causal.py').write_text(runner)
        (out / 'io_helpers.py').write_bytes((old / 'io_helpers.py').read_bytes())
        for name in ('TEACHER-SOURCE-TRACES.json.gz', 'PUBLIC-TARGETS.json'):
            (out / name).write_bytes((old / name).read_bytes())
        with gzip.open(out / 'ADAPTATION-DIFF.diff.gz', 'xb') as stream:
            stream.write(''.join(difflib.unified_diff(old_runner.splitlines(True), runner.splitlines(True),
                         fromfile='T107/run_causal.py', tofile='T108/run_causal.py')).encode())
        files = [Path(__file__), out / 'run_causal.py', out / 'io_helpers.py',
             out / 'TEACHER-SOURCE-TRACES.json.gz', out / 'PUBLIC-TARGETS.json',
             probe / 'CLOSURE.json', probe / 'ACTUAL-TOOL-TERMINAL.json', batch_file,
             package / 'candidate.py', package / 'generation.json',
             parent_package / 'candidate.py', parent_package / 'generation.json',
             old / 'ROOT-READBACK.json']
        plan.update(schema='t108-whole-child-known-case-plan/1', arms=['P', 'C', 'A'],
             scope='exposed development whole formula continuation; no first-action forcing',
             generation_file=str(batch_file), raw_source_file=str(parent_package / 'candidate.py'),
             child_source_file=str(package / 'candidate.py'), child_identity=child['identity'],
             files={str(p): pin(p) for p in files}, status='prepared_not_started',
             predecessor_results={'directory': str(old), 'outcomes_not_transferred': True},
             force_first_action=False, published=False, fresh_result_blind_confirmation=False)
        save(out / 'RUN-PREPARED.json', plan)
        jobs.append({'directory': str(out), 'targets': len(plan['targets']), 'continuations': plan['max_continuations']})
    save(_project_file(_PROJECT_ROOT, HERE / (slot + '-CONTINUATION-PREPARATION.json')), {'complete': True, 'jobs': jobs,
         'actual_new_models_rules_scores_worlds_tables': 0, 'independent_exposed_sources': 2,
         'fresh_natural_strength': False, 'full_child_formula_every_focal_decision': True})
    print({'prepared': True, 'jobs': len(jobs), 'whole_child_continuations': 4,
           'total_continuations': 12, 'new_models_rules_scores_worlds_tables': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', choices=('S01', 'S02'), required=True)
    main(parser.parse_args().slot)
