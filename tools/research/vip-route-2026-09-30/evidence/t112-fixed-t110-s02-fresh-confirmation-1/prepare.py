"""T110第二子开发通过后，冻结同公式在事前128未曝光来源的确认。

只核已有证据和种子登记，复用T103完整桌执行及读取工具。准备不生成
牌墙、不评分、不调用模型；弱对手组成直接沿用第一作者前的冻结文件。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t112-fixed-t110-s02-fresh-confirmation-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import platform
import sys

from hangma_bot.offline.scoring_sources import REPO_ROOT, source_manifest
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, load_vip_parents

HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1')
PILOT = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t110-compact-target-cost-joint-evolution-1/S02-natural-development-1')
BASE = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t103-joint-breadth-fresh-confirmation-1')


def sha(path):
    """读取实际字节摘要；大日志流读，不构造业务对象。"""
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for part in iter(lambda: stream.read(1 << 20), b''):
            value.update(part)
    return value.hexdigest()


def save(name, value):
    """只创建新文件，保留任何准备失败和既有费用。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def change(text, old, new):
    """只改已经核对的唯一模板位置；模板漂移时拒绝运行。"""
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    """验证完整开发终态后，登记四块、1024完整桌的固定确认计划。"""
    result = json.loads((_project_file(_PROJECT_ROOT, PILOT / 'CAMPAIGN-CLOSURE.json')).read_text())
    terminal = json.loads((_project_file(_PROJECT_ROOT, PILOT / 'ACTUAL-READBACK-TERMINAL.json')).read_text())
    handles = json.loads((_project_file(_PROJECT_ROOT, PILOT / 'ALL-PROCESS-HANDLES.json')).read_text())['processes']
    assert result['whole_batch_valid'] and not result['issues']
    assert result['predeclared_confirmation_start_screen_passed']
    assert result['observed_actual_tables'] == 128 and result['reused_prior_actual_tables'] == 128
    assert result['analysed_historically_executed_tables'] == 256
    assert result['observed_hands_in_readback'] == 2048 and result['duplicate_R18_tables_verified'] == 64
    assert result['normal_R18_fallbacks'] == 0
    assert terminal['verified_tool_terminal'] and terminal['exit_code'] == 0
    assert len(handles) == 8 and {h['block'] for h in handles} == set(range(1, 9))
    for handle in handles:
        received = json.loads((_project_file(_PROJECT_ROOT, PILOT / f"BLOCK-{handle['block']:02d}-TERMINAL.json")).read_text())
        assert received['verified_tool_terminal'] and received['exit_code'] == 0
        assert received['session_id'] == handle['session_id']
    artifact_manifest = json.loads((_project_file(_PROJECT_ROOT, PILOT / 'CLOSED-ARTIFACT-MANIFEST.json')).read_text())
    for member in artifact_manifest['members']:
        path = Path(member['path'])
        assert path.stat().st_size == member['bytes'] and sha(path) == member['sha256']
    evolution = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / 'EVOLUTION-PLAN.json')).read_text())
    assert evolution['confirmation']['actual_tables'] == 1024
    assert evolution['confirmation']['max_candidates'] == 1
    assert evolution['confirmation']['required'][0] == 'root-cluster lower95 net delta >0'
    pilot = json.loads((_project_file(_PROJECT_ROOT, PILOT / 'CAMPAIGN-PLAN.json')).read_text())
    batch_file = _project_file(_PROJECT_ROOT, AUTHOR / 'AUTHOR-BATCH.json')
    batch = VipEohBatch.read(batch_file)
    candidate = load_vip_parents([_project_file(_PROJECT_ROOT, AUTHOR / 'S02-model-output')], batch)[0]
    assert candidate['identity'] == pilot['formulas']['CHILD']
    assert candidate['identity']['candidate_id'] == '54d4029ba095572490c41406a481d73d27e350e385438b177013ce72f274b710'
    source_file = _project_file(_PROJECT_ROOT, AUTHOR / 'S02-model-output/candidate.py')
    reservation_file = _project_file(_PROJECT_ROOT, AUTHOR / 'FRESH-ROOTS-BEFORE-AUTHOR.json')
    reservation = json.loads(reservation_file.read_text())
    roots = reservation['reserved_confirmation']
    assert len(roots) == 128 and reservation['author_read_forbidden']
    assert reservation['worlds_generated'] == 0 and reservation['rounds'] == 8
    assert reservation['initial_scores'] == [0, 0, 0, 0]
    root_ids = [r['root_id'] for r in roots]
    seeds = {r['seed'] for r in roots}
    assert len(seeds) == len(set(root_ids)) == 128
    starts = sorted(p for p in E.glob('t*/**/START.json') if 'code_snapshot' not in p.parts)
    assert all('t110-compact-target-cost:reserved_confirmation:' not in p.read_text() for p in starts)
    # 自己的作者前组成含预留种子，属于冻结依据；不把它误判为已执行曝光。
    composition_files = sorted(p for p in E.glob('t*/**/COMPOSITIONS*.json')
        if 'code_snapshot' not in p.parts and p.parent != HERE and p != _project_file(_PROJECT_ROOT, AUTHOR / 'COMPOSITIONS.json'))
    prior_seeds = set()
    def collect(value):
        if isinstance(value, dict):
            if type(value.get('seed')) is int:
                prior_seeds.add(value['seed'])
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    for path in composition_files:
        collect(json.loads(path.read_text()))
    assert not seeds.intersection(prior_seeds)
    save('EXPOSURE-AND-SEED-CHECK.json', {
        'schema': 't112-bounded-exposure-check/1',
        'checked_start_files': {str(p): sha(p) for p in starts},
        'checked_composition_files': {str(p): sha(p) for p in composition_files},
        'own_prereservation_composition_excluded': str(_project_file(_PROJECT_ROOT, AUTHOR / 'COMPOSITIONS.json')),
        'confirmation_ids_absent_from_checked_start_files': True, 'seed_collision': False,
        'scope': 't* START and composition files excluding duplicate code snapshots; not exhaustive historical world index',
        'new_rules_scores_worlds_tables': 0})
    frozen_compositions = json.loads((_project_file(_PROJECT_ROOT, AUTHOR / 'COMPOSITIONS.json')).read_text())
    assert frozen_compositions['author_read_forbidden'] and frozen_compositions['worlds_generated'] == 0
    compositions = frozen_compositions['pools']['reserved_confirmation']
    assert [c['root_id'] for c in compositions] == root_ids
    assert [c['seed'] for c in compositions] == [r['seed'] for r in roots]
    assert all(c['weak_fraction_setting'] == .6 and c['paired_A_C_same_composition'] for c in compositions)
    save('COMPOSITIONS.json', {'schema': 't112-prereserved-confirmation-compositions/1',
        'roots': compositions, 'source_file': str(_project_file(_PROJECT_ROOT, AUTHOR / 'COMPOSITIONS.json')),
        'all_128_reserved_roots_used': True, 'rerolled': False, 'worlds_generated': 0})
    original_runner = (_project_file(_PROJECT_ROOT, BASE / 'run_block.py')).read_text()
    runner = change(original_runner, "match_id_prefix='t103-fixed-t101-fresh-confirmation'",
        "match_id_prefix='t112-fixed-t110-s02-fresh-confirmation'")
    runner = change(runner, "'schema':'t103-fresh-natural-confirmation-block-result/1'",
        "'schema':'t112-fresh-natural-confirmation-block-result/1'")
    runner = change(runner, "'scope':'t103_four_block1024table_campaign'",
        "'scope':'t112_four_block1024table_campaign'")
    original_reader = (_project_file(_PROJECT_ROOT, BASE / 'close_campaign.py')).read_text()
    reader = change(original_reader, "'schema':'t103-whole-fresh-natural-confirmation-result/1'",
        "'schema':'t112-whole-fresh-natural-confirmation-result/1'")
    for name, original, adapted in [('run_block.py', original_runner, runner),
                                    ('close_campaign.py', original_reader, reader)]:
        ast.parse(adapted)
        with (_project_file(_PROJECT_ROOT, HERE / name)).open('x') as stream:
            stream.write(adapted)
        with (_project_file(_PROJECT_ROOT, HERE / (name + '.diff'))).open('x') as stream:
            stream.write(''.join(difflib.unified_diff(original.splitlines(True), adapted.splitlines(True))))
    save('OUTCOME-READER-FREEZE.json', {'stage': 'before_actual_worlds',
        'files': {str(_project_file(_PROJECT_ROOT, HERE / 'close_campaign.py')): sha(_project_file(_PROJECT_ROOT, HERE / 'close_campaign.py'))}})
    source_roots = tuple(pilot['source_roots'])
    manifest = source_manifest(source_roots)
    manifest.update(candidate['identity']['source_manifest'])
    contract = _project_file(_PROJECT_ROOT, REPO_ROOT / candidate['identity']['contract_path'])
    manifest[candidate['identity']['contract_path']] = {'bytes': contract.stat().st_size, 'sha256': sha(contract)}
    assert manifest == json.loads((_project_file(_PROJECT_ROOT, PILOT / 'FROZEN-SOURCE-MANIFEST.json')).read_text())
    save('FROZEN-SOURCE-MANIFEST.json', manifest)
    prerequisites = [_project_file(_PROJECT_ROOT, PILOT / n) for n in ('CAMPAIGN-CLOSURE.json', 'ACTUAL-READBACK-TERMINAL.json',
        'ALL-PROCESS-HANDLES.json', 'CLOSED-ARTIFACT-MANIFEST.json', 'FROZEN-SOURCE-MANIFEST.json')]
    prerequisites += [_project_file(_PROJECT_ROOT, AUTHOR / n) for n in ('EVOLUTION-PLAN.json', 'COMPOSITIONS.json',
        'S02-ROOT-SOURCE-ACCEPTANCE.json', 'S02-public-probe/ROOT-READBACK.json',
        'S02-CONTINUATION-CLOSED-SUMMARY.json')]
    prerequisites += [reservation_file, batch_file, source_file, source_file.parent / 'generation.json']
    prerequisites += [_project_file(_PROJECT_ROOT, HERE / n) for n in ('prepare.py', 'run_block.py', 'run_block.py.diff',
        'close_campaign.py', 'close_campaign.py.diff', 'OUTCOME-READER-FREEZE.json',
        'EXPOSURE-AND-SEED-CHECK.json', 'COMPOSITIONS.json', 'FROZEN-SOURCE-MANIFEST.json')]
    pins = {str(p): sha(p) for p in prerequisites}
    plan = json.loads((_project_file(_PROJECT_ROOT, BASE / 'CAMPAIGN-PLAN.json')).read_text())
    plan.update(schema='t112-fixed-t110-s02-prereserved-confirmation-plan/1',
        created_at_utc=datetime.now(timezone.utc).isoformat(), candidate_identity=candidate['identity'],
        raw_source_file=str(source_file), generation_file=str(batch_file), source_roots=source_roots,
        prerequisite_sha256=pins, root_ids=root_ids, compositions_file=str(_project_file(_PROJECT_ROOT, HERE / 'COMPOSITIONS.json')),
        actual_weak_opponent_slots=sum(c['actual_weak_count'] for c in compositions),
        primary='complete-table T110 S02 minus registered R18 net score, clustered by128 independent mother roots',
        confidence={'method': 'mother-root bootstrap percentile', 'resamples': 20000, 'seed': 20261003112, 'interval': .95},
        development_selection='only eligible child of T110 two-author batch; S01 screen failed',
        development_candidate_tables=64, independent_confirmation_uses_development_outcomes=False,
        python=sys.version, python_executable=sys.executable, platform=platform.platform())
    assert plan['planned_actual_tables'] == 1024 and plan['planned_hands'] == 8192
    assert plan['offline_max_operations'] == batch.max_operations == 4800000
    save('CAMPAIGN-PLAN.json', plan)
    for block in range(1, 5):
        save(f'BLOCK-{block:02d}-PLAN.json', dict(plan, block=block,
            root_ids=root_ids[(block - 1) * 32:block * 32], planned_roots=32, independent_roots=32,
            paired_tables=128, planned_actual_tables=256, planned_hands=2048, planned_hands_per_arm=1024,
            wall_clock_limit_seconds=10800, step_limit=10000,
            scoring_input_capture={'max_view_json_bytes': 33554432, 'max_total_json_bytes': 17179869184,
                                   'max_unique_views': 100000},
            prerequisite_sha256=dict(pins, **{str(_project_file(_PROJECT_ROOT, HERE / 'CAMPAIGN-PLAN.json')): sha(_project_file(_PROJECT_ROOT, HERE / 'CAMPAIGN-PLAN.json'))})))
    print({'prepared': True, 'candidate': candidate['identity']['candidate_id'],
        'roots': 128, 'planned_tables': 1024, 'actual_weak_slots': plan['actual_weak_opponent_slots'],
        'formula_changed': False, 'new_models_rules_scores_worlds_tables': 0}, flush=True)


if __name__ == '__main__':
    main()
