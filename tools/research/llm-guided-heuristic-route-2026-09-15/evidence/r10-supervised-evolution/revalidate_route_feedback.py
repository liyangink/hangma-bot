"""把原源码重准入及新评测接回公开M1反馈链；不伪造新的作者调用。"""

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)
import argparse

import strong_seed_batch as b
import route_executor_recovery as recovery
from hangma_bot.kernel.config import RuleConfig


def prepare():
    """建立明确标注来源重验证的父代登记，原生成记录和作者原答保持只读。"""
    plan = b.read(recovery.OUT / 'manifest.json')
    recovery.verify(plan)
    for name in recovery.NAMES:
        sub = recovery.OUT / name
        assert not (sub / 'generation').exists()
        source_path = b.Path(plan['sources'][name]['path'])
        origin = source_path.parent
        original = b.read(origin / 'record.json')
        parsed = b.read(origin / 'parsed.json')
        admission = b.read(sub / 'admission.json')
        assert admission['execution_safety_pass']
        assert parsed['code_sha256'] == b.digest(source_path.read_bytes())
        provenance = {'kind': 'existing_source_revalidated_after_executor_fix',
            'original_generation_dir': str(origin),
            'original_record_sha256': b.digest((origin / 'record.json').read_bytes()),
            'original_candidate_id': original['identity']['candidate_id'],
            'original_prompt_sha256': original['prompt']['sha256'],
            'admission_path': str(sub / 'admission.json'),
            'admission_sha256': b.digest((sub / 'admission.json').read_bytes()),
            'source_sha256': b.digest(source_path.read_bytes()), 'new_model_calls': 0,
            'note': '源码与原作者交付完全相同；只重建执行身份，非新生成，不改写旧成绩。'}
        generation = sub / 'generation'
        generation.mkdir()
        (generation / 'candidate.py').write_bytes(source_path.read_bytes())
        b.write(generation / 'parsed.json', parsed)
        b.write(generation / 'record.json', {
            'schema': original['schema'], 'operator': original['operator'],
            'backend': 'existing-source-revalidation-no-model-call',
            'created_at_utc': b.search.utc_now(), 'identity': admission['identity'],
            'prompt': original['prompt'], 'parse': original['parse'],
            'precheck': original['precheck'],
            'load': {'ok': True, 'supervised': True, 'evidence': str(sub / 'admission.json')},
            'revalidation': provenance,
            'note': '派生登记而非模型生成事件；prompt/parse仅描述原交付，准入取当前独立证据。'})
        binding = b.search.av_generate().av_parent_binding(generation)
        assert binding['candidate_id'] == admission['identity']['candidate_id']
        b.write(sub / 'revalidation-provenance.json', provenance)
        auth = b.unified_document(batch_label='feedback-recovery-' + name,
            authorization_id='r10-feedback-recovery-' + name,
            accounts={'tables_full': 4, 'tables_partial': 8, 'prefix_generation': 8},
            issued_by='lead', issued_at_utc=b.search.utc_now(), legacy_alias=False)
        auth['issuance_basis'] = '用户持续推进授权；新核心父代反馈所需的条件读数重评，零作者调用，额外至多4完整桌赛/来源'
        b.write(sub / 'feedback-authorization.json', auth)
        print(name, binding['candidate_id'], flush=True)


def conditional(name):
    """用真实模拟器运行条件续打，独立账本；不替换既有自然评测。"""
    plan = b.read(recovery.OUT / 'manifest.json')
    recovery.verify(plan)
    sub = recovery.OUT / name
    assert not (sub / 'feedback-conditional-started.json').exists()
    auth = b.read(sub / 'feedback-authorization.json')
    b.write(sub / 'feedback-conditional-started.json', {'at_utc': b.search.utc_now()})
    ledger = b.search.ActionValueLedger(sub / 'feedback-ledger.json',
        authorized_budgets=b.search.av_ledger_budgets_from_authorization(auth))
    runtime = b.search.av_opportunities().build_real_runtime(
        rules_config=RuleConfig(b.search.AV_CONDITIONAL_RULESET_VERSION, 1, False),
        rounds_per_game=b.search.AV_CONDITIONAL_ROUNDS_PER_GAME,
        seed=plan['panel_seed'], scenario_id='executor-recovery-feedback-' + name)
    result = b.search.run_av_evaluation(sub / 'conditional',
        b.Path(plan['sources'][name]['path']).read_text(), predicate='branch_open', opponent='H',
        ledger=ledger, admission=b.read(sub / 'admission.json'), authorization=auth,
        attempts_cap=8, panel_seed=plan['panel_seed'], prefix_source='v2_behavior', runtime=runtime)
    recovery.verify(plan)
    assert result['ok'], result.get('refused')
    assert result['identity']['candidate_id'] == b.read(sub / 'admission.json')['identity']['candidate_id']
    cost = b.read(sub / 'feedback-ledger.json')
    assert not any(r['status'] == 'reserved' for r in cost['reservations'])
    b.write(sub / 'feedback-conditional-closure.json', {'status': 'COMPLETE', 'spent': cost['spent'],
        'evaluation_id': result['identity']['evaluation_id'], 'model_calls': 0, 'release_eligible': False})
    print(name, 'conditional complete', cost['spent'], flush=True)


def feedback():
    """完整自然评测之后才生成新反馈，公开M1闸门逐项验证身份和来源。"""
    plan = b.read(recovery.OUT / 'manifest.json')
    recovery.verify(plan)
    assert (recovery.OUT / 'summary.json').exists()
    for name in recovery.NAMES:
        sub = recovery.OUT / name
        assert b.read(sub / 'feedback-conditional-closure.json')['status'] == 'COMPLETE'
        output = sub / 'summary/feedback.json'
        assert not output.exists()
        cid = b.read(sub / 'admission.json')['identity']['candidate_id']
        projected = b.search.build_three_segment_feedback(eval_dir=sub, candidate_cid=cid, parent_cid=None)
        b.write(output, projected)
        _, verdict = b.search._av_m1_feedback({'plan': {'parent_dir': str(sub / 'generation'), 'parent_candidate_id': cid}})
        b.write(sub / 'feedback-consumption-check.json', verdict)
        assert verdict['ok'], verdict
        print(name, 'feedback executable', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'conditional', 'feedback'])
    parser.add_argument('--name', choices=recovery.NAMES)
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare()
    elif args.action == 'feedback':
        feedback()
    elif args.name:
        conditional(args.name)
    else:
        parser.error('conditional需要name')
