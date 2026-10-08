"""机械和整段续打闭合后，冻结32新母源的子／真父／R18完整桌开发。"""

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
    """核实际文件摘要；生成阶段和执行阶段的身份不能混用。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    """冻结计划只创建；实例费用与独立母源分开计数。"""
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def change(text, old, new):
    """只接受已核原工具中的明确位置，模板漂移直接失败。"""
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main(slot):
    """32母源×四换座×两策略×两配对，512实际桌；留出128源不启动。"""
    probe = _project_file(_PROJECT_ROOT, HERE / (slot + '-public-probe'))
    public = json.loads((probe / 'ROOT-READBACK.json').read_text())
    assert public['complete'] and public['actual_tool_terminal']['exit_code'] == 0
    causal_files = []
    for label in ('root033', 'root009'):
        path = _project_file(_PROJECT_ROOT, HERE / (slot + '-continuation-' + label))
        actual = json.loads((path / 'ROOT-READBACK.json').read_text())
        assert actual['complete'] and actual['actual_tool_terminal']['exit_code'] == 0
        assert not actual['forced_first_reconciliations']
        causal_files.extend([path / 'ROOT-READBACK.json', path / 'CAUSAL-CLOSURE.json'])
    batch_file = _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-BATCH.json')
    batch = VipEohBatch.read(batch_file)
    child_package = _project_file(_PROJECT_ROOT, HERE / (slot + '-model-output'))
    parent_package = _project_file(_PROJECT_ROOT, E / 't101-joint-breadth-recovery-author-1/S02-model-output')
    child, parent = load_vip_parents([child_package, parent_package], batch)
    assert child['identity'] == public['candidate_identity']
    assert child['identity']['source_manifest'] == parent['identity']['source_manifest']
    assert child['identity']['params'] == parent['identity']['params']
    reserved = json.loads((_project_file(_PROJECT_ROOT, HERE / 'FRESH-ROOTS-BEFORE-AUTHOR.json')).read_text())
    roots = reserved['fresh_development']
    assert len(roots) == 32 and reserved['worlds_generated'] == 0 and reserved['author_read_forbidden']
    compositions = json.loads((_project_file(_PROJECT_ROOT, HERE / 'COMPOSITIONS.json')).read_text())['pools']['fresh_development']
    assert [r['root_id'] for r in compositions] == [r['root_id'] for r in roots]
    out = _project_file(_PROJECT_ROOT, HERE / (slot + '-natural-development-1'))
    out.mkdir(exist_ok=False)
    save(out / 'COMPOSITIONS.json', {'roots': compositions, 'author_pre_frozen': True,
         'worlds_generated_in_preparation': 0, 'composition_or_result_selection': False})
    old_runner = (_project_file(_PROJECT_ROOT, BASE / 'run_block.py')).read_text()
    runner = old_runner.replace('choices=range(1,9)', 'choices=range(1,17)')
    assert runner != old_runner
    runner = runner.replace('t102-fixed-formula-fresh-pilot', 't108-target-cost-shared-fresh-pilot')
    runner = runner.replace('t102-fresh-natural-pilot-block-result', 't108-fresh-natural-pilot-block-result')
    runner = runner.replace("plan['variant']=='T101'", "plan['variant']=='CHILD'")
    runner = runner.replace('eight_block256table_pilot', 'sixteen_block512table_pilot')
    runner = runner.replace('保留256分母', '保留512分母')
    ast.parse(runner)
    (out / 'run_block.py').write_text(runner)
    old_reader = (_project_file(_PROJECT_ROOT, BASE / 'close_pilot.py')).read_text()
    reader = old_reader.replace('T101', 'CHILD').replace('T97', 'PARENT')
    reader = change(reader, "OLD=HERE.parent/'t93-fixed-formula-fresh-natural-confirmation-1/close_campaign.py'",
                    'OLD=Path(' + repr(str(_project_file(_PROJECT_ROOT, E / 't93-fixed-formula-fresh-natural-confirmation-1/close_campaign.py'))) + ')')
    reader = change(reader, 'assert len(handles)==8', 'assert len(handles)==16')
    reader = reader.replace('range(1,9)', 'range(1,17)')
    reader = change(reader, "assert duplicate_tables==64 and len(outcomes['CHILD'])==len(outcomes['PARENT'])==128",
                    "assert duplicate_tables==128 and len(outcomes['CHILD'])==len(outcomes['PARENT'])==256")
    reader = change(reader, 'assert len(seen_hands)==2048', 'assert len(seen_hands)==4096')
    reader = change(reader, "for c in costs)==256", "for c in costs)==512")
    reader = change(reader, "all(len(pairs[v])==64", "all(len(pairs[v])==128")
    reader = change(reader, "for x in realized[v][a].values())==512", "for x in realized[v][a].values())==1024")
    reader = reader.replace("'planned_actual_tables':256", "'planned_actual_tables':512")
    reader = reader.replace("'independent_roots':16", "'independent_roots':32")
    reader = reader.replace("'schema':'t102-whole-three-formula-pilot-result/1'", "'schema':'t108-whole-three-formula-pilot-result/1'")
    reader = reader.replace('sixteen new development roots', 'thirty-two pre-author development roots')
    ast.parse(reader)
    (out / 'close_pilot.py').write_text(reader)
    for name, before, after in [('RUNNER-DIFF.diff.gz', old_runner, runner), ('READER-DIFF.diff.gz', old_reader, reader)]:
        with gzip.open(out / name, 'xb') as stream:
            stream.write(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True))).encode())
    helper = _project_file(_PROJECT_ROOT, E / 't93-fixed-formula-fresh-natural-confirmation-1/close_campaign.py')
    save(out / 'OUTCOME-READER-FREEZE.json', {'stage': 'before_new_actual_tables',
         'files': {str(p): sha(p) for p in [out / 'close_pilot.py', helper]}})
    manifest = source_manifest(SOURCE_ROOTS)
    manifest.update(child['identity']['source_manifest'])
    contract = _project_file(_PROJECT_ROOT, REPO_ROOT / child['identity']['contract_path'])
    manifest[child['identity']['contract_path']] = {'sha256': sha(contract), 'bytes': contract.stat().st_size}
    save(out / 'FROZEN-SOURCE-MANIFEST.json', manifest)
    files = [Path(__file__), _project_file(_PROJECT_ROOT, HERE / 'EVOLUTION-PLAN.json'), _project_file(_PROJECT_ROOT, HERE / 'FRESH-ROOTS-BEFORE-AUTHOR.json'),
         _project_file(_PROJECT_ROOT, HERE / 'COMPOSITIONS.json'), _project_file(_PROJECT_ROOT, HERE / 'AUTHOR-PREPARATION-CLOSED.json'),
         out / 'COMPOSITIONS.json', out / 'run_block.py', out / 'close_pilot.py',
         out / 'OUTCOME-READER-FREEZE.json', out / 'FROZEN-SOURCE-MANIFEST.json',
         probe / 'ROOT-READBACK.json', probe / 'CLOSURE.json', batch_file,
         child_package / 'candidate.py', child_package / 'generation.json',
         parent_package / 'candidate.py', parent_package / 'generation.json', *causal_files]
    pins = {str(p): sha(p) for p in files}
    plan = {'schema': 't108-three-formula-development-plan/1', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
         'stage': 'pre-author reserved fresh development, not confirmation',
         'formulas': {'CHILD': child['identity'], 'PARENT': parent['identity']},
         'generation_file': str(batch_file), 'source_roots': SOURCE_ROOTS, 'prerequisite_sha256': pins,
         'root_ids': [r['root_id'] for r in roots], 'independent_roots': 32, 'rotations_per_root': 4, 'rounds': 8,
         'planned_actual_tables': 512, 'planned_hands': 4096, 'blocks': 16, 'roots_per_block': 4,
         'duplicate_R18_tables_actually_run': 128, 'duplicate_baseline_charged_but_not_independent': True,
         'compositions_file': str(out / 'COMPOSITIONS.json'), 'main_weak_fraction_setting': 0.6,
         'actual_weak_opponent_slots': sum(r['actual_weak_count'] for r in compositions),
         'total_logical_opponent_slots': 96,
         'confidence': {'method': 'mother-root bootstrap percentile', 'resamples': 20000,
             'seed': 20261003108, 'interval': 0.95, 'scope': '32-root development descriptive only'},
         'primary': ['CHILD minus registered R18', 'CHILD minus true parent T101'],
         'confirmation_start_screen': 'both positive mean net, both actual highfan increments positive on >=2 sources; all engineering and duplicate A exact',
         'inspection': 'progress/cost/fault only until all16 actual handles terminal; no midbatch tuning or source append',
         'failure': 'first engineering fault stops new pairs globally; active pairs finish; original512 denominator retained',
         'official_settlement_multiplier': 1, 'ordinary_loss_allowed_if_real_highfan_net_covers': True,
         'offline_max_operations': batch.max_operations, 'normal_C_r18_fallback_allowed': False,
         'logical_clock_not_deadline_evidence': True, 'old_admission_or_results_transferred': False,
         'new_author_calls': 0, 'confirmation_claim': False, 'published': False,
         'reserved_confirmation_roots_not_started': 128, 'research_native_graph_meter_or_payload_overlays_used': False,
         'new_models_rules_scores_worlds_tables_in_preparation': 0}
    save(out / 'CAMPAIGN-PLAN.json', plan)
    for block in range(1, 17):
        variant = 'CHILD' if block <= 8 else 'PARENT'
        ordinal = (block - 1) % 8
        package = child_package if variant == 'CHILD' else parent_package
        save(out / f'BLOCK-{block:02d}-PLAN.json', dict(plan, block=block, variant=variant,
             candidate_identity=plan['formulas'][variant], raw_source_file=str(package / 'candidate.py'),
             root_ids=plan['root_ids'][ordinal * 4:ordinal * 4 + 4], planned_roots=4,
             independent_roots=4, planned_actual_tables=32, planned_hands=256,
             wall_clock_limit_seconds=3600, step_limit=10000,
             scoring_input_capture={'max_view_json_bytes': 33554432, 'max_total_json_bytes': 2147483648, 'max_unique_views': 12000},
             prerequisite_sha256=dict(pins, **{str(out / 'CAMPAIGN-PLAN.json'): sha(out / 'CAMPAIGN-PLAN.json')})))
    print({'prepared': True, 'fresh_mother_roots': 32, 'actual_tables_planned': 512,
           'actual_weak_slots': plan['actual_weak_opponent_slots'], 'logical_opponent_slots': 96,
           'new_worlds_scores_tables': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--slot', choices=('S01', 'S02'), required=True)
    main(parser.parse_args().slot)
