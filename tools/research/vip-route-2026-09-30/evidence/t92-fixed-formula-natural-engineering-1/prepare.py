"""冻结修复后的执行身份与两个新牌山种子；不评分、不生成世界、不开桌。

原作者包的严格装载拒绝原样保存。此处只允许公开离线构造器使用原公式，
不伪造新模型回复，不授父代准入，也不继承旧身份的强度成绩。
"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/vip-route-2026-09-30/evidence/t92-fixed-formula-natural-engineering-1'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import platform
import shutil
import sys
import traceback

from hangma_bot.hangma._standard import backend_info
from hangma_bot.offline.qualifier_opponents import freeze_qualifier_compositions
from hangma_bot.offline.scoring_sources import REPO_ROOT, source_manifest, write_code_snapshot
from hangma_bot.offline.vip_eoh_generate import VipEohBatch, VipEohError, load_vip_parents

HERE = Path(__file__).resolve().parent
E = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence')
AUTHOR = _project_file(_PROJECT_ROOT, 'review/vip-route-2026-09-30/evidence/t75-net-upgrade-joint-author-1')
SOURCE_SHA = 'f6da2d82eabaf0b95ada0c836d18df582e670a8336bf6a4d61955e62ca13955e'
CURRENT_ID = '180f69045d019774cd7704dc151e8f674382eaed9462e8c16ef4ee6aa6b58e75'
SOURCE_ROOTS = (
    'hangma_bot.offline.qualifier_opponents', 'hangma_bot.offline.evaluate',
    'hangma_bot.offline.vip_route_development', 'hangma_bot.offline.vip_evaluation',
    'hangma_bot.offline.scoring_input_capture',
)


def sha(path):
    """文件字节摘要；用于冻结源码与已保存原件。"""
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(name, data):
    """准备件只新建，失败原件和旧结果不能被覆盖。"""
    with (_project_file(_PROJECT_ROOT, HERE / name)).open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def main():
    pointer_path = _project_file(_PROJECT_ROOT, AUTHOR / 'CURRENT-CANDIDATE-PACKAGE.json')
    pointer = json.loads(pointer_path.read_text())
    generation_file = _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_batch'])
    package = _project_file(_PROJECT_ROOT, AUTHOR / pointer['relative_package'])
    source_file = package / 'candidate.py'
    source = source_file.read_text(encoding='utf-8')
    assert sha(source_file) == SOURCE_SHA
    batch = VipEohBatch.read(generation_file)
    identity = batch.identity(source)
    assert identity['candidate_id'] == CURRENT_ID
    old_identity = pointer['candidate_identity']
    try:
        load_vip_parents([package], batch)
    except VipEohError as exc:
        assert str(exc) == '父代源码、合同、依赖或额度与当前逐字节身份不一致'
        with (_project_file(_PROJECT_ROOT, HERE / 'OLD-PACKAGE-REJECTION.log')).open('x') as stream:
            stream.write(traceback.format_exc())
        rejection = {'rejected': True, 'error': type(exc).__name__ + ': ' + str(exc)}
    else:
        raise AssertionError('预期旧身份被拒；不能隐式迁移旧门禁')
    fields = sorted(k for k in set(identity) | set(old_identity) if identity.get(k) != old_identity.get(k))
    old_manifest = old_identity['source_manifest']
    changed = sorted(k for k in set(old_manifest) | set(identity['source_manifest'])
                     if old_manifest.get(k) != identity['source_manifest'].get(k))
    save('EXECUTION-IDENTITY.json', {
        'schema': 't92-fixed-source-fresh-engineering-identity/1',
        'role': 'raw_source_offline_engineering_not_eoh_parent_or_published_candidate',
        'candidate_identity': identity, 'old_candidate_identity': old_identity,
        'source_sha256': SOURCE_SHA, 'old_package_load': rejection,
        'changed_identity_fields': fields, 'changed_source_manifest_paths': changed,
        'old_admission_or_results_transferred': False, 'new_author_calls': 0,
        'new_rule_choose_scores_worlds_tables': 0,
    })
    # 命名空间、顺序和哈希算法事前固定，不按对手组成或收益挑种子。
    namespace = 't92-fixed-t75-engineering-newroots-20261003-v1'
    roots = [{'root_id': f't92-fixed-t75-engineering:{i:03d}',
              'seed': int.from_bytes(hashlib.sha256(f'{namespace}:{i}'.encode()).digest()[:8], 'big') & ((1 << 63)-1)}
             for i in (1, 2)]
    prior_paths = [_project_file(_PROJECT_ROOT, AUTHOR / 'FRESH-ROOTS-BEFORE-AUTHOR.json'),
                   _project_file(_PROJECT_ROOT, AUTHOR / 'COMPOSITIONS-BEFORE-AUTHOR.json'),
                   _project_file(_PROJECT_ROOT, E / 't49-qualifier-opponent-behavior-1/COMPOSITIONS-BEFORE-TABLES.json')]
    seen = set()
    def collect(value):
        if isinstance(value, dict):
            if type(value.get('seed')) is int:
                seen.add(value['seed'])
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)
    for path in prior_paths:
        collect(json.loads(path.read_text()))
    assert not seen.intersection(r['seed'] for r in roots)
    compositions = freeze_qualifier_compositions(roots, 0.6)
    save('COMPOSITIONS.json', {'schema': 't92-engineering-compositions/1', 'roots': compositions,
        'seed_namespace': namespace, 'seed_algorithm': 'first8bytes SHA256(namespace:ordinal), unsigned & (2^63-1)',
        'selected_ordinals': [1, 2], 'composition_or_outcome_selection': False,
        'checked_prior_seed_files': {str(p): sha(p) for p in prior_paths},
        'checked_prior_distinct_seeds': len(seen), 'prior_seed_collision': False,
        'scope': 'new namespace plus listed prior freezes only; not a claim of exhaustive historical seed indexing',
        'new_worlds_tables': 0})
    manifest = source_manifest(SOURCE_ROOTS)
    manifest.update(identity['source_manifest'])
    contract = _project_file(_PROJECT_ROOT, REPO_ROOT / identity['contract_path'])
    manifest[identity['contract_path']] = {'sha256': sha(contract), 'bytes': contract.stat().st_size}
    snapshot = _project_file(_PROJECT_ROOT, HERE / 'frozen-execution')
    snapshot.mkdir(exist_ok=False)
    write_code_snapshot(snapshot, manifest)
    for relative, digest in manifest.items():
        copied = snapshot / 'code_snapshot' / relative
        assert copied.stat().st_size == digest['bytes'] and sha(copied) == digest['sha256'], relative
    native = backend_info()
    native_file = Path(native['native_path']) if native['native_path'] else None
    if native_file is not None:
        native_dir = snapshot / 'native-backend'
        native_dir.mkdir()
        shutil.copyfile(native_file, native_dir / native_file.name)
        binary = identity['math_backend']['native_binary']
        assert sha(native_dir / native_file.name) == binary['sha256']
    save('FROZEN-SOURCE-MANIFEST.json', manifest)
    prerequisites = [pointer_path, generation_file, package / 'generation.json', source_file,
                     _project_file(_PROJECT_ROOT, HERE / 'EXECUTION-IDENTITY.json'), _project_file(_PROJECT_ROOT, HERE / 'OLD-PACKAGE-REJECTION.log'),
                     _project_file(_PROJECT_ROOT, HERE / 'COMPOSITIONS.json'), _project_file(_PROJECT_ROOT, HERE / 'FROZEN-SOURCE-MANIFEST.json'),
                     _project_file(_PROJECT_ROOT, HERE / 'prepare.py'), _project_file(_PROJECT_ROOT, HERE / 'run_engineering.py'), _project_file(_PROJECT_ROOT, HERE / 'ADAPTATION-DIFF.diff')]
    save('PLAN.json', {
        'schema': 't92-fixed-formula-complete-table-engineering-plan/1',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'stage': 'engineering_preflight_not_strength_confirmation_or_admission',
        'candidate_identity': identity, 'raw_source_file': str(source_file),
        'generation_file': str(generation_file), 'source_roots': SOURCE_ROOTS,
        'prerequisite_sha256': {str(p.resolve()): sha(p) for p in prerequisites},
        'compositions_file': str(_project_file(_PROJECT_ROOT, HERE / 'COMPOSITIONS.json')),
        'root_ids': [r['root_id'] for r in roots], 'planned_roots': 2,
        'rotations_per_root': 4, 'rounds': 8, 'paired_tables': 8,
        'planned_actual_tables': 16, 'planned_hands': 128, 'planned_hands_per_arm': 64,
        'wall_clock_limit_seconds': 7200, 'step_limit': 10000,
        'main_weak_fraction_setting': 0.6,
        'actual_weak_opponent_slots': sum(r['actual_weak_count'] for r in compositions),
        'total_logical_opponent_slots': 6,
        'scoring_input_capture': {'max_view_json_bytes': 33554432,
                                'max_total_json_bytes': 2147483648, 'max_unique_views': 100000},
        'offline_max_operations': batch.max_operations,
        'formula_and_limits_held_fixed': True, 'normal_C_r18_fallback_allowed': False,
        'rules_source': str(REPO_ROOT), 'source_kind': 'simulation',
        'python': sys.version, 'python_executable': sys.executable, 'platform': platform.platform(),
        'math_backend': native,
        'research_native_graph_meter_or_payload_overlays_used': False,
        'inspection': 'progress/cost/fault only until terminal; no midbatch outcome-driven tuning',
        'failure': 'stop new pairs on first engineering fault; retain full16 denominator and actual costs',
        'official_settlement_multiplier': 1,
        'ordinary_loss_allowed_if_real_cumulative_highfan_net_covers': True,
        'logical_clock_not_deadline_evidence': True,
        'old_admission_or_results_transferred': False,
        'confirmation_claim': False, 'published': False,
        'new_model_rules_choose_scores_worlds_tables_in_preparation': 0,
    })
    print({'prepared': True, 'execution_id': identity['candidate_id'], 'planned_actual_tables': 16,
           'actual_weak_slots': sum(r['actual_weak_count'] for r in compositions),
           'new_worlds_tables_scores': 0})


if __name__ == '__main__':
    main()
