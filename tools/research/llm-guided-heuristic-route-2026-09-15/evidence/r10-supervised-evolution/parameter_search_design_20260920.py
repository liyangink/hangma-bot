"""生成有界V2配置设计；只按已有请求去除重复行为，不运行新的效果桌赛。"""

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
import math
import random
from dataclasses import asdict, replace
from pathlib import Path

from hangma_bot.application.audit_codec import decision_request_from_json
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2
from hangma_bot.policy.interface import DecisionBudget
from hangma_bot.policy.weights_v1 import DEFAULT_WEIGHTS_V1


HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/parameter-search-design-20260920.json')
SEED = 2026092011  # 仅配置生成随机种子；不是效果评价牌山种子。
SPACE = {
    "effective_tile": (0.25, 4.0, "log2"),
    "claim_risk_peng": (0.0, 12.0, "linear"),
    "claim_risk_chi": (0.0, 20.0, "linear"),
    "feed_risk": (0.0, 12.0, "linear"),
    "safe_tile_bonus": (0.0, 6.0, "linear"),
    "style_adjust": (0.0, 8.0, "linear"),
}


def digest(path):
    """绑定设计源码和诊断输入；这些摘要不替代完整效果运行身份。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proposals():
    """先列7个可解释锚点，再列固定种子的64个六维分层配置。"""
    yield "anchor_effective_half", {"effective_tile": 0.5}
    yield "anchor_effective_double", {"effective_tile": 2.0}
    for key in tuple(SPACE)[1:]:
        yield "anchor_zero_" + key, {key: 0.0}
    rng = random.Random(SEED)
    strata = {}
    for key in SPACE:
        values = list(range(64))
        rng.shuffle(values)
        strata[key] = values
    for i in range(64):
        vector = {}
        for key, (low, high, scale) in SPACE.items():
            u = (strata[key][i] + rng.random()) / 64
            value = (2 ** (math.log2(low) + u * (math.log2(high) - math.log2(low)))
                     if scale == "log2" else low + u * (high - low))
            vector[key] = round(value, 6)
        yield "stratified_%02d" % i, vector


async def main():
    """从已有真实请求验证配置可执行并留至多24个不同排序；不挑选强度冠军。"""
    assert not OUT.exists(), "冻结设计不得覆盖"
    audit_path = _project_file(_PROJECT_ROOT, HERE / "parameter-surface-audit-20260920.json")
    audit = json.loads(audit_path.read_text())
    assert digest(_project_file(_PROJECT_ROOT, HERE / "parameter_surface_audit_20260920.py")) == audit["source_sha256"]
    requests = []
    for name, expected in audit["inputs"].items():
        path = Path(name)
        assert digest(path) == expected
        requests.append(decision_request_from_json(json.loads(path.read_text())["request"]))
    budget = DecisionBudget(1.0, 2.0, 3.0)  # 固定单调时钟用于行为检查，不用于时限验收。

    async def behavior(weights):
        """仅调用公开choose；完整排序、拒绝动作过滤和有限权重均须有效。"""
        policy = ComparableHeuristicPolicyV2(weights=weights, monotonic=lambda: 0.0)
        orders = []
        for request in requests:
            result = await policy.choose(request, budget)
            keys = [item.action_key for item in result.candidates]
            assert len(keys) == len(set(keys))
            assert [item.rank for item in result.candidates] == list(range(1, len(keys) + 1))
            assert not set(keys).intersection(item.action_key for item in request.rejected_attempts)
            orders.append(keys)
        signature = hashlib.sha256(json.dumps(orders, sort_keys=True).encode()).hexdigest()
        return orders, signature

    base = DEFAULT_WEIGHTS_V1
    base_orders, base_sig = await behavior(base)
    assert (await behavior(base))[0] == base_orders
    signatures = {base_sig}
    selected, skipped = [], []
    for label, vector in proposals():
        weights = replace(base, **vector)
        orders, signature = await behavior(weights)
        assert all(sorted(a) == sorted(b) for a, b in zip(orders, base_orders))
        if signature in signatures:
            skipped.append({"design_id": label, "reason": "DUPLICATE_ON_DIAGNOSTIC_REQUESTS"})
            continue
        signatures.add(signature)
        payload = asdict(weights)
        weight_sha = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        selected.append({"config_id": "v2_joint_%02d" % (len(selected) + 1),
                         "design_id": label, "weights": payload, "weights_sha256": weight_sha,
                         "behavior_sha256": signature,
                         "first_changes": sum(a[:1] != b[:1] for a, b in zip(orders, base_orders)),
                         "full_order_changes": sum(a != b for a, b in zip(orders, base_orders))})
        if len(selected) == 24:
            break
    checked_code = ("src/hangma_bot/policy/heuristic_v2.py",
                    "src/hangma_bot/policy/heuristic_v1.py",
                    "src/hangma_bot/policy/weights_v1.py")
    result = {
        "status": "CONFIGURATION_DESIGN_COMPLETE_NOT_EFFECT_EXECUTION_READY",
        "source_sha256": digest(Path(__file__)),
        "behavior_input_audit": str(audit_path), "behavior_input_audit_sha256": digest(audit_path),
        "policy_source_checks": {name: digest(_project_file(_PROJECT_ROOT, ROOT / name)) for name in checked_code},
        "generator_seed": SEED, "space": SPACE,
        "selection_rule": "7锚点后按固定64分层候选顺序，按91既有请求完整排序去重，留首24个非基线签名；不读取效果",
        "baseline_weights": asdict(base), "baseline_behavior_sha256": base_sig,
        "request_count": len(requests), "selected_count": len(selected),
        "selected": selected, "skipped": skipped,
        "limitations": "有限诊断请求去重不证明全域等价，也不证明自然改选频率或增强；未做在线时限验收。",
        "remaining_execution_requirements": ["独立研究策略身份及全生产依赖闭包", "来源根和费用计划",
                                              "结果平分口径及确定性选留规则", "恢复与默认V2差分验收"],
        "model_calls": 0, "new_effect_tables": 0, "confirmation_roots": 0,
        "strength_evidence": False, "release_eligible": False,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "selected": len(selected),
                      "skipped": len(skipped), "requests": len(requests),
                      "model_calls": 0, "new_effect_tables": 0}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
