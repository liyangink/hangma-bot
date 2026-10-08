"""只读核查现有V2参数接口能否改变真实排序；不是优化、强度评测或候选晋升。"""

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
import asyncio
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1
from hangma_bot.policy.interface import DecisionBudget

HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/parameter-surface-audit-20260920.json')


def sha(path):
    """文件内容摘要用于绑定本次只读输入和核查源码。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    """固定每参数零/低值及双倍值，在既有请求上观察排序，不消费新效果样本。"""
    assert not OUT.exists(), '已有记录不覆盖'
    plan_path = _project_file(_PROJECT_ROOT, HERE / 'followup-balance-20260920/checks-plan.json')
    inputs = json.loads(plan_path.read_text())['inputs']
    requests = []
    unique_views = set()
    for name, expected in inputs.items():
        path = Path(name)
        assert sha(path) == expected
        obj = json.loads(path.read_text())
        requests.append(decision_request_from_json(obj['request']))
        unique_views.add(obj['candidate_view_sha256'])
    base = DEFAULT_WEIGHTS_V1
    fields = ('effective_tile', 'claim_risk_peng', 'claim_risk_chi',
              'feed_risk', 'safe_tile_bonus', 'style_adjust')
    variants = [('baseline', base)]
    for field in fields:
        initial = getattr(base, field)
        low = initial * .5 if field == 'effective_tile' else 0.0
        variants.extend([(field + '_low', replace(base, **{field: low})),
                         (field + '_double', replace(base, **{field: initial * 2.0}))])
    budget = DecisionBudget(1.0, 2.0, 3.0)
    baseline_plans = []
    output = []
    signatures = set()
    for label, weights in variants:
        policy = ComparableHeuristicPolicyV2(weights=weights, monotonic=lambda: 0.0)
        orders = []
        first_changes = all_changes = 0
        for i, request in enumerate(requests):
            plan = await policy.choose(request, budget)
            order = [c.action_key for c in plan.candidates]
            if label == 'baseline':
                baseline_plans.append(plan)
                assert asdict(await policy.choose(request, budget)) == asdict(plan)
            reference = baseline_plans[i]
            old = [c.action_key for c in reference.candidates]
            assert sorted(order) == sorted(old)
            assert [c.rank for c in plan.candidates] == list(range(1, len(order) + 1))
            assert plan.decision_id == reference.decision_id and plan.window_key == reference.window_key
            assert all(c.action_key not in {r.action_key for r in request.rejected_attempts} for c in plan.candidates)
            first_changes += order[:1] != old[:1]
            all_changes += order != old
            orders.append(order)
        sig = hashlib.sha256(json.dumps(orders, sort_keys=True).encode()).hexdigest()
        signatures.add(sig)
        output.append({'configuration': label, 'weights': asdict(weights),
                       'first_changes': first_changes, 'full_order_changes': all_changes,
                       'behavior_sha256': sig})
    result = {'status': 'COMPLETE_EXISTING_PARAMETER_SURFACE_DIAGNOSTIC',
              'input_plan': str(plan_path), 'input_plan_sha256': sha(plan_path),
              'source_sha256': sha(Path(__file__)), 'inputs': inputs,
              'requests': len(requests), 'unique_candidate_views': len(unique_views),
              'configurations_including_control': len(variants),
              'distinct_order_signatures': len(signatures), 'results': output,
              'purpose': '确认既有可信策略权重接缝可执行及触达；不选择最优配置，不评价效果。',
              'limitations': '输入是既有挑选诊断窗口，改选率不是自然频率；未做动作时限/全域边界验收。',
              'model_calls': 0, 'new_tables': 0, 'confirmation_roots': 0,
              'selection_eligible': False, 'release_eligible': False}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('inputs','results')}, ensure_ascii=False))
    print(json.dumps([{k:r[k] for k in ('configuration','first_changes','full_order_changes')} for r in output],ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
