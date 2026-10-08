"""评分和正反续打闭合后冻结16新母源完整桌，复用已验T102量具。"""

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
from datetime import datetime, timezone
import argparse
import ast
import difflib
import gzip
import hashlib
import json
from pathlib import Path

from hangma_bot.offline.scoring_sources import REPO_ROOT, source_manifest
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents

HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
BASE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t102-joint-breadth-fresh-pilot-1')
SOURCE_ROOTS = ('hangma_bot.offline.qualifier_opponents', 'hangma_bot.offline.evaluate',
    'hangma_bot.offline.vip_route_development', 'hangma_bot.offline.vip_evaluation',
    'hangma_bot.offline.scoring_input_capture')


def sha(path):
    """冻结实际字节；完整桌不能混用生成身份和执行身份。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    """只新建计划，失败费用和原证据保留。"""
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main(slot):
    """第一份子／父分别对同R18，16母源四换座，共256桌／2048单局。"""
    assert slot == 'S01', '第二份需单独准备父结果复用，不能重算已闭父代'
    public = json.loads((_project_file(_PROJECT_ROOT, HERE / 'S01-public-probe/ROOT-READBACK.json')).read_text())
    assert public['complete'] and public['actual_tool_terminal']['exit_code'] == 0
    assert public['behavior_changed'], '无实际动作变化，不启动新自然桌'
    continuation = json.loads((_project_file(_PROJECT_ROOT, HERE / 'S01-CONTINUATION-PREPARATION.json')).read_text())
    assert continuation['complete'] and continuation['current_hand_continuations'] == 18
    tails = []
    for job in continuation['jobs']:
        path = Path(job['directory'])
        read = json.loads((path / 'ROOT-READBACK.json').read_text())
        assert read['complete'] and read['actual_tool_terminal']['exit_code'] == 0
        assert not read['forced_first_reconciliations']
        tails.extend([path / 'ROOT-READBACK.json', path / 'CAUSAL-CLOSURE.json'])
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json')
    batch = VipEohBatch.read(batch_file)
    child_path = _project_file(_PROJECT_ROOT, HERE / 'S01-model-output')
    parent_path = Path(json.loads((_project_file(_PROJECT_ROOT, HERE / 'PARENT-IDENTITY.json')).read_text())['path'])
    child, parent = load_vip_parents([child_path, parent_path], batch)
    assert child['identity'] == public['candidate_identity']
    for field in ('source_manifest', 'params', 'math_backend'):
        assert child['identity'][field] == parent['identity'][field]
    reservation = json.loads((_project_file(_PROJECT_ROOT, HERE / 'FRESH-ROOTS-BEFORE-AUTHOR.json')).read_text())
    assert reservation['worlds_generated'] == 0 and reservation['author_read_forbidden']
    roots = reservation['fresh_development']
    compositions = json.loads((_project_file(_PROJECT_ROOT, HERE / 'COMPOSITIONS.json')).read_text())['pools']['fresh_development']
    assert len(roots) == len(compositions) == 16
    assert [r['root_id'] for r in roots] == [r['root_id'] for r in compositions]
    out = _project_file(_PROJECT_ROOT, HERE / 'S01-natural-development-1')
    out.mkdir(exist_ok=False)
    save(out / 'COMPOSITIONS.json', {'roots': compositions, 'author_pre_frozen': True,
        'worlds_generated_in_preparation': 0, 'composition_or_result_selection': False})
    old_runner = (_project_file(_PROJECT_ROOT, BASE / 'run_block.py')).read_text()
    runner = old_runner.replace('t102-fixed-formula-fresh-pilot', 't110-target-specific-shared-fresh-pilot')
    runner = runner.replace('t102-fresh-natural-pilot-block-result', 't110-fresh-natural-pilot-block-result')
    assert runner.count("plan['variant']=='T101'") == 1
    runner = runner.replace("plan['variant']=='T101'", "plan['variant']=='CHILD'")
    old_reader = (_project_file(_PROJECT_ROOT, BASE / 'close_pilot.py')).read_text()
    reader = old_reader.replace('T101', 'CHILD').replace('T97', 'PARENT')
    relative = "OLD=HERE.parent/'t93-fixed-formula-fresh-natural-confirmation-1/close_campaign.py'"
    assert reader.count(relative) == 1
    reader = reader.replace(relative, 'OLD=Path(' + repr(str(_project_file(_PROJECT_ROOT, E / 't93-fixed-formula-fresh-natural-confirmation-1/close_campaign.py'))) + ')')
    reader = reader.replace('t102-whole-three-formula-pilot-result', 't110-whole-three-formula-pilot-result')
    for name, before, after in [('run_block.py', old_runner, runner), ('close_pilot.py', old_reader, reader)]:
        ast.parse(after)
        (out / name).write_text(after)
        with gzip.open(out / (name + '-ADAPTATION.diff.gz'), 'xb') as stream:
            stream.write(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True))).encode())
    helper = _project_file(_PROJECT_ROOT, E / 't93-fixed-formula-fresh-natural-confirmation-1/close_campaign.py')
    save(out / 'OUTCOME-READER-FREEZE.json', {'stage': 'before_new_actual_tables',
        'files': {str(p): sha(p) for p in [out / 'close_pilot.py', helper]}})
    manifest = source_manifest(SOURCE_ROOTS)
    manifest.update(child['identity']['source_manifest'])
    contract = _project_file(_PROJECT_ROOT, REPO_ROOT / child['identity']['contract_path'])
    manifest[child['identity']['contract_path']] = {'sha256': sha(contract), 'bytes': contract.stat().st_size}
    save(out / 'FROZEN-SOURCE-MANIFEST.json', manifest)
    inputs = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'EVOLUTION-PLAN.json'), _project_file(_PROJECT_ROOT, HERE / 'FRESH-ROOTS-BEFORE-AUTHOR.json'),
        _project_file(_PROJECT_ROOT, HERE / 'COMPOSITIONS.json'), _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-PREPARATION-CLOSED.json'),
        out / 'COMPOSITIONS.json', out / 'run_block.py', out / 'close_pilot.py',
        out / 'OUTCOME-READER-FREEZE.json', out / 'FROZEN-SOURCE-MANIFEST.json',
        _project_file(_PROJECT_ROOT, HERE / 'S01-public-probe/ROOT-READBACK.json'), batch_file,
        child_path / 'candidate.py', child_path / 'generation.json',
        parent_path / 'candidate.py', parent_path / 'generation.json', *tails]
    pins = {str(p): sha(p) for p in inputs}
    plan = {'schema': 't110-three-formula-development-plan/1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'stage': 'author-pre-reserved development; not independent confirmation',
        'formulas': {'CHILD': child['identity'], 'PARENT': parent['identity']},
        'generation_file': str(batch_file), 'source_roots': SOURCE_ROOTS, 'prerequisite_sha256': pins,
        'root_ids': [r['root_id'] for r in roots], 'independent_roots': 16,
        'rotations_per_root': 4, 'rounds': 8, 'planned_actual_tables': 256, 'planned_hands': 2048,
        'blocks': 8, 'roots_per_block': 4, 'duplicate_R18_tables_actually_run': 64,
        'duplicate_baseline_charged_but_not_independent': True,
        'compositions_file': str(out / 'COMPOSITIONS.json'), 'main_weak_fraction_setting': 0.6,
        'actual_weak_opponent_slots': sum(r['actual_weak_count'] for r in compositions),
        'total_logical_opponent_slots': 48,
        'confidence': {'method': 'mother-root bootstrap percentile', 'resamples': 20000,
            'seed': 20261003110, 'interval': 0.95, 'scope': '16-root development descriptive only'},
        'primary': ['CHILD minus registered R18', 'CHILD minus actual formal T101 parent'],
        'confirmation_start_screen': 'both positive mean net and actual highfan increments on >=2 roots; all engineering and repeated A exact',
        'inspection': 'progress/cost/fault only until all8 actual handles terminal; no midbatch tuning or source append',
        'failure': 'first engineering fault stops new pairs globally; active pairs finish; original256 denominator retained',
        'official_settlement_multiplier': 1, 'ordinary_loss_allowed_if_real_highfan_net_covers': True,
        'offline_max_operations': batch.max_operations, 'normal_C_r18_fallback_allowed': False,
        'logical_clock_not_deadline_evidence': True, 'old_admission_or_results_transferred': False,
        'new_author_calls': 0, 'confirmation_claim': False, 'published': False,
        'reserved_confirmation_roots_not_started': 128,
        'research_native_graph_meter_or_payload_overlays_used': False,
        'new_models_rules_scores_worlds_tables_in_preparation': 0}
    save(out / 'CAMPAIGN-PLAN.json', plan)
    for block in range(1, 9):
        variant = 'CHILD' if block <= 4 else 'PARENT'
        ordinal = (block - 1) % 4
        package = child_path if variant == 'CHILD' else parent_path
        save(out / f'BLOCK-{block:02d}-PLAN.json', dict(plan, block=block, variant=variant,
            candidate_identity=plan['formulas'][variant], raw_source_file=str(package / 'candidate.py'),
            root_ids=plan['root_ids'][ordinal * 4:ordinal * 4 + 4], planned_roots=4,
            independent_roots=4, planned_actual_tables=32, planned_hands=256,
            wall_clock_limit_seconds=3600, step_limit=10000,
            scoring_input_capture={'max_view_json_bytes': 33554432,
                'max_total_json_bytes': 2147483648, 'max_unique_views': 12000},
            prerequisite_sha256=dict(pins, **{str(out / 'CAMPAIGN-PLAN.json'): sha(out / 'CAMPAIGN-PLAN.json')})))
    print({'prepared': True, 'fresh_mother_roots': 16, 'actual_tables_planned': 256,
        'actual_weak_slots': plan['actual_weak_opponent_slots'], 'new_worlds_scores_tables': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', choices=('S01', 'S02'), required=True)
    main(parser.parse_args().slot)
