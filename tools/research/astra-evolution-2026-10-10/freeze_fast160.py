"""为独立快速版冻结新的完整阶段预算，不继承旧版本强度或启动池。

沿用原数值门，重绑真实候选与导出/native来源。每个新阶段根仍包含
十桌各十六单局、四个相关换座变体；声明和门写入新目录，拒绝覆盖。
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import time


BASE_GATES_SHA256 = '20d8ee9a89bdb9105cf42bc20223d529f084b7121c043950ea63bd1b80776e81'


def digest(data: bytes) -> str:
    """只计算内容摘要，不作为强度或发布资格。"""
    return hashlib.sha256(data).hexdigest()


def canonical(data: dict) -> bytes:
    """与候选实际身份编码保持一致，拒绝NaN。"""
    return json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def build_declaration(base: dict, frozen: dict, candidate_dir: Path, *, created_at: float) -> dict:
    """以原完整声明生成新根；规则、预算及数值门不做结果驱动变更。

只返回新值，不改原声明或冻结件。候选与执行身份须能从实际证明重算。
"""
    proof = frozen['actual_source_proof']
    identity = proof['candidate_identity']
    if (digest(canonical(identity)) != frozen['candidate_id']
            or proof['candidate_id'] != frozen['candidate_id']
            or digest(canonical(proof)) != frozen['execution_id']):
        raise ValueError('快速版实际候选或执行身份不闭合')
    if (base['candidate']['params'] != frozen['params']
            or identity['params'] != frozen['params']):
        raise ValueError('快速版不能改变事前算法参数或原预算')
    if (base['tables_per_stage'] != 10 or base['rounds_per_table'] != 16
            or base['seat_variants'] != [0, 1, 2, 3]):
        raise ValueError('基础声明不是完整十桌十六单局真四席')
    if (base['phase'] not in ('dev', 'confirm')
            or base['opponent_pool'] not in ('homogeneous', 'mixed')):
        raise ValueError('基础阶段或对手池不支持')
    count = 4 if base['phase'] == 'dev' else 8
    if len(base['stage_roots']) != count or len(set(base['stage_roots'])) != count:
        raise ValueError('原声明根数不完整')
    if not 1 <= base['workers'] <= base['cpu_cores'] * 80 // 100:
        raise ValueError('重进程超过80%核心')
    required = {'paired_continuation_policy.py', 'paired_continuation_model.py',
                'export_adapter.py', 'native_binding.py', 'assembly.py'}
    if set(frozen['runtime_files']) != required:
        raise ValueError('快速版缺实际模型、导出、native绑定或装配来源')
    if (frozen['runtime_files']['paired_continuation_policy.py'] != identity['factory_sha256']
            or frozen['runtime_files']['paired_continuation_model.py'] != identity['model_sha256']
            or frozen['runtime_files']['export_adapter.py'] != identity['export_adapter_sha256']
            or frozen['runtime_files']['native_binding.py'] != identity['native_binding_sha256']
            or frozen['runtime_files']['assembly.py'] != proof['assembly_sha256']):
        raise ValueError('快速版运行文件与实际身份不一致')
    declaration = copy.deepcopy(base)
    pool, phase = base['opponent_pool'], base['phase']
    declaration['created_at_unix_seconds'] = created_at  # Unix墙上时钟秒，只作冻结时间
    declaration['stage_roots'] = [f'astra-paired-cont-fast-v2-{phase}-{pool}-20261010-{i:04d}'
                                  for i in range(1, count + 1)]
    if set(declaration['stage_roots']) & set(base['stage_roots']):
        raise ValueError('新快速版不得重用旧效果根')
    paths = {n: str((candidate_dir / n).resolve()) for n in required}
    declaration['candidate'] = {
        'kind': 'factory', 'factory_path': paths['paired_continuation_policy.py'],
        'factory_sha256': identity['factory_sha256'],
        'expected_candidate_id': frozen['candidate_id'],
        'auxiliary_files': {paths[n]: frozen['runtime_files'][n]
                            for n in ('paired_continuation_model.py', 'export_adapter.py', 'native_binding.py')},
        'params': copy.deepcopy(frozen['params'])}
    declaration['frozen_files'].update({paths[n]: h for n, h in frozen['runtime_files'].items()})
    declaration['candidate_hypothesis'] = (
        '冻结配对P0续行参数及实际原预算；精确导出可能减少截止保父，但行为覆盖变化须独立效果验证')
    declaration['evaluated_parent_policy_tag'] = 'P0'
    declaration['native_binding_identity'] = copy.deepcopy(identity['actual_native_binding'])
    declaration['candidate_freeze_execution_id'] = frozen['execution_id']
    declaration['inherits_v1_effect_or_release_admission'] = False
    declaration['strength_claim'] = False
    return declaration


def main() -> None:
    """验原件后只冻结四份声明和原数值门；不启动评估、匹配或发布。"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-root', type=Path, required=True)
    parser.add_argument('--candidate-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    frozen_path = args.candidate_dir / 'FROZEN.json'
    delivery_path = args.candidate_dir / 'DELIVERY.json'
    frozen = json.loads(frozen_path.read_bytes())
    delivery = json.loads(delivery_path.read_bytes())
    if delivery['candidate_id'] != frozen['candidate_id'] or delivery['execution_id'] != frozen['execution_id']:
        raise ValueError('交付与实际冻结身份不同')
    for name, sha in delivery['files'].items():
        if digest((args.candidate_dir / name).read_bytes()) != sha:
            raise ValueError('快速版交付文件漂移: ' + name)
    gates_path = args.base_root / 'PC-V1-GATES.json'
    if digest(gates_path.read_bytes()) != BASE_GATES_SHA256:
        raise ValueError('基础效果门不是已冻结的原数值门')
    gates = json.loads(gates_path.read_bytes())
    built = {}
    created_at = time.time()
    for phase in ('DEV', 'CONFIRM'):
        for pool in ('HOMOGENEOUS', 'MIXED'):
            source = args.base_root / f'PC-V1-{phase}-{pool}-DECLARATION.json'
            if gates['declarations'].get(str(source.resolve())) != digest(source.read_bytes()):
                raise ValueError('基础声明不是原事前门绑定原文')
            base = json.loads(source.read_bytes())
            built[f'PC-FAST-V2-{phase}-{pool}-DECLARATION.json'] = build_declaration(
                base, frozen, args.candidate_dir, created_at=created_at)
    if {d['workers'] for d in built.values()} != {10}:
        raise ValueError('本次事前声明须统一为十个重进程，不能另增池')
    methods = {str(p.resolve()): digest(p.read_bytes())
               for p in (Path(__file__), Path(__file__).with_name('gate160.py'),
                         Path(__file__).with_name('distribution160.py'), frozen_path, delivery_path)}
    for declaration in built.values():
        declaration['frozen_files'].update(methods)
    # 在写输出前核全部旧、新来源；不得以旧候选被冻结为由忽略工具/runtime漂移。
    for declaration in built.values():
        for path, sha in declaration['frozen_files'].items():
            if digest(Path(path).read_bytes()) != sha:
                raise ValueError('阶段冻结来源漂移: ' + path)
    args.out.mkdir(parents=True, exist_ok=False)
    pins = {}
    for name, declaration in built.items():
        path = args.out / name
        data = json.dumps(declaration, ensure_ascii=False, indent=2).encode() + b'\n'
        with path.open('xb') as stream:
            stream.write(data)
        pins[str(path.resolve())] = digest(data)
    new_gates = copy.deepcopy(gates)
    new_gates.update(candidate_id=frozen['candidate_id'], declarations=pins,
                     created_at_unix_seconds=created_at, inherits_v1_strength=False,
                     original_gate_sha256=digest(gates_path.read_bytes()))
    target = args.out / 'PC-FAST-V2-GATES.json'
    target.write_text(json.dumps(new_gates, ensure_ascii=False, indent=2) + '\n')
    receipt = {'schema': 'paired-fast-v2-stage-freeze/1', 'created_at_unix_seconds': created_at,
               'candidate_id': frozen['candidate_id'], 'candidate_execution_id': frozen['execution_id'],
               'builder_sha256': digest(Path(__file__).read_bytes()),
               'candidate_frozen_sha256': digest(frozen_path.read_bytes()),
               'candidate_delivery_sha256': digest(delivery_path.read_bytes()),
               'original_gates_sha256': digest(gates_path.read_bytes()),
               'new_gates_sha256': digest(target.read_bytes()), 'declarations': pins,
               'additional_frozen_methods': methods,
               'development_roots': 8, 'confirmation_roots_if_original_development_gate_passes': 16,
               'workers': 10, 'effect_processes_started': 0, 'production_admission': False,
               'current_v1_confirmation_unchanged': True, 'free_match_activated': False}
    (args.out / 'FREEZE-RECEIPT.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: receipt[k] for k in ('candidate_id', 'development_roots',
          'confirmation_roots_if_original_development_gate_passes', 'effect_processes_started')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
