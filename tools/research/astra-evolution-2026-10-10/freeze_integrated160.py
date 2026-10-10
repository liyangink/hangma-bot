"""冻结可执行集成候选的新阶段、实际运行根和一槽至十槽资源计划。

原数值门与参数不变，研究版收益不迁入新身份。这里只生成新声明；
正常启动和正式发布仍由该隔离组合根拒绝draft并等待完整准入。
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import time

BASE_GATE_SHA = '20d8ee9a89bdb9105cf42bc20223d529f084b7121c043950ea63bd1b80776e81'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def integrated_declaration(base, delivery, manifest, *, schedule, created_at):
    """新实际身份配独立新根，不改原件、公式参数、门或整桌维度。"""
    identity = manifest['source_identity']
    if (delivery['candidate_id'] != manifest['candidate_id']
            or hashlib.sha256(canonical(identity)).hexdigest() != delivery['candidate_id']
            or delivery['execution_id'] != manifest['execution_id']):
        raise ValueError('集成候选实际身份不闭合')
    execution = {'schema': 'paired-integrated-execution/1', 'candidate_id': delivery['candidate_id'],
        'source_identity': identity, 'audit': 'bounded-runtime-audit-revision-003',
        'clock': 'SystemClock host monotonic seconds', 'compute_settings': manifest['compute_settings'],
        'execution_identity_does_not_grant_admission': True}
    if hashlib.sha256(canonical(execution)).hexdigest() != delivery['execution_id']:
        raise ValueError('集成实际执行身份不闭合')
    if (delivery['startup_admitted'] is not False or delivery['strength_admission'] is not False
            or delivery['effects_inherited'] is not False
            or manifest['startup_admitted'] is not False or manifest['strength_admission'] is not False):
        raise ValueError('新集成候选不得继承或提前授准入')
    if (base['candidate']['params'] != delivery['algorithm_params']
            or identity['params'] != delivery['algorithm_params']
            or base['rules_hash'] != delivery['rules_source_hash']
            or identity['rules_source_hash'] != delivery['rules_source_hash']):
        raise ValueError('参数、原预算或唯一规则不一致')
    if (base['tables_per_stage'] != 10 or base['rounds_per_table'] != 16
            or base['seat_variants'] != [0, 1, 2, 3] or base['workers'] != 10):
        raise ValueError('须完整十桌十六单局真四席，上限十槽')
    phase, pool = base['phase'], base['opponent_pool']
    if phase not in ('dev', 'confirm') or pool not in ('homogeneous', 'mixed'):
        raise ValueError('阶段或池不匹配')
    n = 4 if phase == 'dev' else 8
    if len(base['stage_roots']) != n or len(set(base['stage_roots'])) != n:
        raise ValueError('完整独立根缺漏')
    d = copy.deepcopy(base)
    d.update(created_at_unix_seconds=created_at, runtime_root=delivery['runtime_root'],
        stage_roots=[f'astra-paired-integrated-{delivery["candidate_id"][:12]}-{phase}-{pool}-20261010-{i:04d}'
                     for i in range(1, n + 1)], worker_schedule=copy.deepcopy(schedule),
        candidate_execution_id=delivery['execution_id'], evaluated_parent_policy_tag='P0',
        inherits_v1_or_fast_v2_effect=False, strength_claim=False)
    if set(d['stage_roots']) & set(base['stage_roots']):
        raise ValueError('集成候选不得重用旧根')
    d['candidate'] = {'kind': 'factory', 'factory_path': delivery['factory_path'],
        'factory_sha256': delivery['factory_sha256'], 'expected_candidate_id': delivery['candidate_id'],
        'auxiliary_files': {str(Path(delivery['runtime_root']) / p): h
                            for p, h in identity['runtime_source_manifest'].items()},
        'params': copy.deepcopy(delivery['algorithm_params'])}
    d['candidate_hypothesis'] = '最终组合根注入同一冻结配对P0续行；精确导出与有限审计在原预算内，独立效果不继承'
    return d


def main():
    """核完整交付、核心原件和实际新运行根，只写全新预算目录。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-root', type=Path, required=True)
    parser.add_argument('--draft-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    gate_path = args.base_root / 'PC-V1-GATES.json'
    if sha(gate_path) != BASE_GATE_SHA:
        raise ValueError('原数值门已漂移')
    gates = json.loads(gate_path.read_text())
    delivery_path = args.draft_dir / 'DELIVERY.json'
    frozen_path = args.draft_dir / 'FROZEN.json'
    delivery = json.loads(delivery_path.read_text())
    frozen = json.loads(frozen_path.read_text())
    for name, h in delivery['files'].items():
        if sha(args.draft_dir / name) != h:
            raise ValueError('集成交付漂移: ' + name)
    runtime = Path(delivery['runtime_root']).resolve()
    factory = Path(delivery['factory_path']).resolve()
    if not factory.is_relative_to(runtime / 'src') or sha(factory) != delivery['factory_sha256']:
        raise ValueError('离线工厂不是本新运行根的实际来源')
    package = next(iter(frozen['packages'].values()))
    manifest_path = runtime / package['path']
    if sha(manifest_path) != package['file_sha256']:
        raise ValueError('草稿包漂移')
    manifest = json.loads(manifest_path.read_text())
    actual_files = {str(p.resolve()): sha(p) for p in runtime.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc' and p.name != '.DS_Store'}
    methods = {str(p.resolve()): sha(p) for p in (
        Path(__file__), Path(__file__).with_name('stage160_adaptive.py'),
        Path(__file__).with_name('gate160.py'), Path(__file__).with_name('distribution160.py'),
        delivery_path, frozen_path)}
    schedule = {'initial_workers': 1, 'released_workers': 10, 'source_exec_session_id': 35427,
        'source_pipeline_path': str((args.base_root / 'pc_v1_after_development.py').resolve()),
        'source_pipeline_sha256': sha(args.base_root / 'pc_v1_after_development.py'),
        'source_state_path': str((args.base_root / 'PC-V1-AFTER-DEVELOPMENT.json').resolve()),
        'source_candidate_id': gates['candidate_id'], 'source_gates_sha256': BASE_GATE_SHA,
        'release_file': str((args.out / 'CPU-RELEASE.json').resolve())}
    created_at = time.time()
    declarations = {}
    for phase in ('DEV', 'CONFIRM'):
        for pool in ('HOMOGENEOUS', 'MIXED'):
            source = args.base_root / f'PC-V1-{phase}-{pool}-DECLARATION.json'
            if gates['declarations'].get(str(source.resolve())) != sha(source):
                raise ValueError('基础声明不是事前原件')
            d = integrated_declaration(json.loads(source.read_text()), delivery, manifest,
                schedule=schedule, created_at=created_at)
            d['frozen_files'].update(actual_files)
            d['frozen_files'].update(methods)
            for path, h in d['frozen_files'].items():
                if sha(path) != h:
                    raise ValueError('新旧冻结来源漂移: ' + path)
            declarations[f'PC-INTEGRATED-{phase}-{pool}-DECLARATION.json'] = d
    args.out.mkdir(parents=True, exist_ok=False)
    pins = {}
    for name, declaration in declarations.items():
        path = args.out / name
        path.write_text(json.dumps(declaration, ensure_ascii=False, indent=2) + '\n')
        pins[str(path.resolve())] = sha(path)
    new_gates = copy.deepcopy(gates)
    new_gates.update(candidate_id=delivery['candidate_id'], declarations=pins,
        created_at_unix_seconds=created_at, inherits_old_effect=False, original_gate_sha256=BASE_GATE_SHA)
    out = args.out / 'PC-INTEGRATED-GATES.json'
    out.write_text(json.dumps(new_gates, ensure_ascii=False, indent=2) + '\n')
    receipt = {'schema': 'paired-integrated-stage-freeze/1', 'candidate_id': delivery['candidate_id'],
        'execution_id': delivery['execution_id'], 'new_gates_sha256': sha(out), 'declarations': pins,
        'actual_runtime_files': len(actual_files), 'source_methods': methods, 'worker_schedule': schedule,
        'development_roots': 8, 'confirmation_roots_if_development_passes': 16,
        'effect_started': False, 'startup_admitted': False, 'strength_admission': False}
    (args.out / 'FREEZE-RECEIPT.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: receipt[k] for k in ('candidate_id', 'actual_runtime_files', 'development_roots',
        'confirmation_roots_if_development_passes', 'effect_started')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
