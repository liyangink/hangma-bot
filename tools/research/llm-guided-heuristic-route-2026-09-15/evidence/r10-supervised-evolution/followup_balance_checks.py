"""监督者批准的单份纯排序提案验收；不是任意原生模型代码执行入口。"""

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
import ast
import asyncio
import json
from collections import Counter
from dataclasses import asdict

import followup_quality_diagnosis as diagnosis
import followup_balance_policy as wrapper
from hangma_bot.policy.action_value_executor import static_check
from hangma_bot.policy.interface import DecisionBudget

b = diagnosis.b
OUT = b.HERE / "followup-balance-20260920"


def load_ranker():
    """只装载已逐行审查并绑定摘要的函数；静态限制能力，专用审查证明本份循环有界。"""
    path = OUT / "ranking.py"
    source = path.read_text()
    review = b.read(OUT / "source-review.json")
    assert review["source_sha256"] == b.digest(path.read_bytes())
    assert review["status"] == "PASS_BOUNDED_OFFLINE_RANKER" and review["boundedness_manually_verified"]
    tree = ast.parse(source)
    assert all(isinstance(node, ast.FunctionDef) for node in tree.body), "本次任务仅允许函数定义"
    assert "score_actions" not in {node.name for node in tree.body}
    # 复用公开静态能力检查；附加入口只供该检查器识别，不装载、不伪装正式评分候选。
    static_check(source + '\n\ndef score_actions(view):\n    return {"status": "ABSTAIN", "entries": [], "reason": "static check only"}\n')
    names = {"len": len, "range": range, "min": min, "max": max, "sum": sum, "abs": abs,
        "sorted": sorted, "tuple": tuple, "list": list, "dict": dict, "bool": bool, "int": int, "float": float,
        "enumerate": enumerate, "zip": zip, "all": all, "any": any, "round": round}
    namespace = {"__builtins__": names}
    exec(compile(tree, str(path), "exec"), namespace)
    return namespace["rank_followup"], review["source_sha256"]


def prepare():
    """冻结新提案、专用包装、旧真实输入与诊断输入，尚不执行新效果桌赛。"""
    assert not (OUT / "checks-plan.json").exists()
    ranker, digest = load_ranker()
    old = b.read(diagnosis.parent.OUT / "evaluation-plan.json")
    diagnosis.parent.verify_inputs(old)
    inputs = dict(b.read(diagnosis.parent.OUT / "manifest.json")["behavior_inputs"])
    for item in b.read(diagnosis.OUT / "panel.json")["windows"]:
        path = diagnosis.OUT / item["file"]
        inputs[str(path)] = b.digest(path.read_bytes())
    b.write(OUT / "checks-plan.json", {"schema": "followup-balance-checks/1", "created_at_utc": b.search.utc_now(),
        "source_sha256": digest, "review_sha256": b.digest((OUT / "source-review.json").read_bytes()),
        "inputs": inputs, "rule_config": b.read(diagnosis.parent.OUT / "manifest.json")["rule_config"],
        "runtime": diagnosis.parent.guard.capture(source_paths=[*b.HERE.glob("*.py"), OUT / "ranking.py"]),
        "max_process_seconds": 180, "model_calls": 1, "effect_tables": 0, "confirmation_roots": 0,
        "release_eligible": False, "scope": "只对专门审核过的一份纯函数做有界离线验证，不声明通用原生作者准入"})
    print("frozen behavior inputs", len(inputs), flush=True)


async def check():
    """公开choose对照父代/V2、开关消融、输入只读与坏排序器回退。"""
    plan = b.read(OUT / "checks-plan.json")
    diagnosis.parent.guard.verify(plan["runtime"])
    assert b.digest((OUT / "source-review.json").read_bytes()) == plan["review_sha256"]
    assert not (OUT / "checks-started.json").exists()
    b.write(OUT / "checks-started.json", {"at_utc": b.search.utc_now()})
    ranker, digest = load_ranker()
    config = diagnosis.parent.RuleConfig(**plan["rule_config"])
    policy = wrapper.BalancedFollowupPolicy(config, lambda: 0.0, ranker, digest)
    disabled = wrapper.BalancedFollowupPolicy(config, lambda: 0.0, ranker, digest, enabled=False)
    budget = DecisionBudget(1., 2., 3.)
    reports = []
    requests = {}
    for name, expected in plan["inputs"].items():
        path = b.Path(name)
        assert b.digest(path.read_bytes()) == expected
        request = b.behavior.decision_request_from_json(b.read(path)["request"])
        requests[name] = request
        baseline = await policy.inner.baseline.choose(request, budget)
        assert asdict(await disabled.choose(request, budget)) == asdict(baseline)
        actual = await policy.choose(request, budget)
        row = policy.audit[-1]
        assert row["status"] in ("EVALUATED", "NOT_APPLICABLE"), row
        assert sorted(c.action_key for c in actual.candidates) == sorted(c.action_key for c in baseline.candidates)
        assert [c.rank for c in actual.candidates] == list(range(1, len(actual.candidates) + 1))
        if row["status"] == "EVALUATED":
            n = len(row["qualities"])
            assert asdict(actual)["candidates"][n:] == asdict(baseline)["candidates"][n:]
            # 重复相同、独立复制的数值输入，原生函数不得跨调用改变输出或输入。
            rows, context = json.loads(json.dumps([row["ranking_rows"], row["ranking_context"]]))
            before = json.dumps([rows, context], sort_keys=True)
            assert ranker(rows, context) == row["ranking_order"]
            assert json.dumps([rows, context], sort_keys=True) == before
        else:
            assert asdict(actual) == asdict(baseline)
        reports.append({"input": name, **row})
    trigger = next(requests[r["input"]] for r in reports if r["status"] == "EVALUATED")
    expected = await policy.inner.baseline.choose(trigger, budget)
    def duplicate(rows, context):
        return [rows[0]["action_key"]] * len(rows)
    def missing(rows, context):
        return [r["action_key"] for r in rows[1:]]
    def mutate(rows, context):
        context["direct_support"] = -1
        return [r["action_key"] for r in rows]
    def raises(rows, context):
        raise ValueError("受控排序异常")
    fallback_checks = []
    for name, broken in (("重复输出", duplicate), ("漏项", missing), ("输入突变", mutate), ("异常", raises)):
        faulty = wrapper.BalancedFollowupPolicy(config, lambda: 0.0, broken, "test-only")
        assert asdict(await faulty.choose(trigger, budget)) == asdict(expected)
        assert faulty.audit[-1]["status"] == "ERROR_FALLBACK" and not faulty.audit[-1]["changed"]
        fallback_checks.append(name)
    diagnosis.parent.guard.verify(plan["runtime"])
    b.write(OUT / "behavior-results.json", reports)
    result = {"status": "PASS_OFFLINE_BEHAVIOR_ONLY", "requests": len(reports), "disabled_exact_v2": len(reports),
        "statuses": dict(Counter(r["status"] for r in reports)), "first_changes_from_v2": sum(r["changed"] for r in reports),
        "first_changes_from_parent": sum(r["selected_first"] != r["parent_selected_first"] for r in reports),
        "fallback_checks": fallback_checks, "model_calls": 1, "effect_tables": 0,
        "confirmation_roots": 0, "release_eligible": False}
    b.write(OUT / "checks.json", result)
    print(result, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "check"))
    args = parser.parse_args()
    prepare() if args.operation == "prepare" else asyncio.run(check())
