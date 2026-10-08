"""离线后继原型的公开choose验收；固定真实输入、独立存档算术与显式回退。"""

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
import asyncio
from collections import Counter
from dataclasses import asdict, replace
from time import perf_counter

import followup_quality_policy as candidate
import followup_rule_probe as proof
import confirmation_execution_identity as guard
from hangma_bot.kernel.config import RuleConfig
from hangma_bot.policy.interface import DecisionBudget, RejectedAttempt

b = proof.b
OUT = b.HERE / "followup-quality-prototype-20260920"


def prepare():
    """固定已有诊断输入及研究执行身份；不是自主作者准入或正式候选晋升。"""
    assert not OUT.exists()
    panel = b.HERE / "selfdraw-tempo-diagnostic-20260920/panel.json"
    paths = [panel.parent / item["file"] for item in b.read(panel)["windows"]]
    for folder in ("batch03-known-root-diagnostic",):
        extra = b.HERE / folder / "panel.json"
        paths += [extra.parent / item["file"] for item in b.read(extra)["windows"]]
    paths = list(dict.fromkeys(paths))
    proof_manifest = b.read(proof.OUT / "manifest.json")
    guard.verify(proof_manifest["runtime"])
    OUT.mkdir()
    b.write(OUT / "manifest.json", {
        "schema": "offline-followup-quality-prototype/1", "created_at_utc": b.search.utc_now(),
        "source": str(b.Path(candidate.__file__)), "source_sha256": b.digest(b.Path(candidate.__file__).read_bytes()),
        "author": "root监督者根据已核验机制编写离线原型；没有额外模型调用，不记为Terra/GLM自主提案",
        "profile": candidate.PROFILE, "rule_config": proof_manifest["rule_config"],
        "behavior_inputs": {str(path): b.digest(path.read_bytes()) for path in paths},
        "proof_inputs": {str(proof.previous.OUT / ("case-" + str(i) + ".json")):
                         b.digest((proof.previous.OUT / ("case-" + str(i) + ".json")).read_bytes()) for i in (1, 2, 3)},
        "runtime": guard.capture(source_paths=[*b.HERE.glob("*.py")]),
        "mechanism": "仅V2首选所在连续同直接向听/支持弃牌前缀；无财神/无链/非抓打圈且向听>=1。Q=sum(未见首摸枚数*max(0,同向听最优合法弃牌支持-当前支持))，只取非当前有效牌。Q降序，平分留V2；其他动作不变",
        "failure_policy": "增强未知、额度耗尽或错误整次回退V2并记状态；不部分使用已算完动作",
        "max_check_process_seconds": 180, "model_calls": 0, "confirmation_roots": 0,
        "release_eligible": False, "formal_scoring_contract_changed": False,
    })
    print("frozen", len(paths), "real behavior inputs", flush=True)


async def checks():
    """从公开choose验证完整计划、开关消融、排序边界和部分分析失败退路。"""
    plan = b.read(OUT / "manifest.json")
    guard.verify(plan["runtime"])
    assert not (OUT / "checks-started.json").exists()
    b.write(OUT / "checks-started.json", {"at_utc": b.search.utc_now()})
    config = RuleConfig(**plan["rule_config"])
    enabled = candidate.FollowupQualityPolicy(config, lambda: 0.0)
    disabled = candidate.FollowupQualityPolicy(config, lambda: 0.0, enabled=False)
    budget = DecisionBudget(1.0, 2.0, 3.0)
    reports = []
    requests = {}
    started = perf_counter()
    for name, digest in plan["behavior_inputs"].items():
        path = b.Path(name)
        assert b.digest(path.read_bytes()) == digest
        request = b.behavior.decision_request_from_json(b.read(path)["request"])
        requests[name] = request
        baseline = await enabled.baseline.choose(request, budget)
        off = await disabled.choose(request, budget)
        assert asdict(off) == asdict(baseline), "关闭机制必须严格复现V2完整输出"
        enhanced = await enabled.choose(request, budget)
        audit = enabled.audit[-1]
        assert sorted(c.action_key for c in enhanced.candidates) == sorted(c.action_key for c in baseline.candidates)
        assert [c.rank for c in enhanced.candidates] == list(range(1, len(enhanced.candidates) + 1))
        assert all(c.action_key not in {a.action_key for a in request.rejected_attempts} for c in enhanced.candidates)
        changed_keys = {r["action_key"] for r in audit["qualities"]}
        if audit["status"] == "EVALUATED":
            count = len(changed_keys)
            assert asdict(replace(enhanced, candidates=enhanced.candidates[count:])) == asdict(replace(baseline, candidates=baseline.candidates[count:]))
        else:
            assert asdict(enhanced) == asdict(baseline)
        assert audit["status"] not in ("ERROR_FALLBACK", "FACT_FALLBACK", "COST_FALLBACK"), audit
        reports.append({"input": name, **audit})
    arithmetic = []
    cases = b.read(proof.OUT / "manifest.json")["cases"]
    for index, case in enumerate(cases):
        path = proof.previous.OUT / ("case-" + str(index + 1) + ".json")
        assert b.digest(path.read_bytes()) == plan["proof_inputs"][str(path)]
        rows = {r["action_key"]: r for r in next(r for r in reports if r["input"] == case["input"])["qualities"]}
        for variant in b.read(path)["variants"]:
            key = variant["action"]
            assert key in rows, ("既有数学对照必须实际触发", key)
            expected = sum(v["unseen_copies"] * max(0, v["best_math_discard"]["support"] - case["direct_support"])
                           for v in variant["branches"] if not v["directly_useful"])
            assert rows[key]["improvement_weighted_sum"] == expected
            arithmetic.append({"action": key, "case": index + 1, "expected": expected, "passed": True})
    trigger = next(requests[r["input"]] for r in reports if r["status"] == "EVALUATED")
    baseline = await enabled.baseline.choose(trigger, budget)
    boundaries = []
    for label, request in (
        ("抓打圈不增强", replace(trigger, observation=replace(trigger.observation, rule_state=replace(trigger.observation.rule_state, catch_play=True)))),
        ("动作链不增强", replace(trigger, observation=replace(trigger.observation, rule_state=replace(trigger.observation.rule_state, chain_count=1)))),
        ("牌墙末段不增强", replace(trigger, observation=replace(trigger.observation, remaining_tile_count=21))),
        ("牌墙未知不增强", replace(trigger, observation=replace(trigger.observation, remaining_tile_count=None))),
    ):
        actual = await enabled.choose(request, budget)
        expected = await enabled.baseline.choose(request, budget)
        assert asdict(actual) == asdict(expected) and enabled.audit[-1]["status"] == "NOT_APPLICABLE"
        boundaries.append(label)
    old_limit = candidate.PROFILE["max_rule_calls"]
    try:
        candidate.PROFILE["max_rule_calls"] = 1
        actual = await enabled.choose(trigger, budget)
        assert asdict(actual) == asdict(baseline) and enabled.audit[-1]["status"] == "COST_FALLBACK"
        assert enabled.audit[-1]["rule_calls"] == 1
        boundaries.append("部分分析后额度耗尽整次回退V2")
    finally:
        candidate.PROFILE["max_rule_calls"] = old_limit
    class FailingRules:
        def analyze(self, observation):
            raise RuntimeError("受控错误注入")
    failing = candidate.FollowupQualityPolicy(config, lambda: 0.0)
    failing.rules = FailingRules()
    assert asdict(await failing.choose(trigger, budget)) == asdict(baseline)
    assert failing.audit[-1]["status"] == "ERROR_FALLBACK"
    boundaries.append("规则调用异常回退且显式记错")
    rejected = replace(trigger, rejected_attempts=(RejectedAttempt(baseline.candidates[0].action_key, "test", 1, trigger.observation.snapshot_seq),))
    actual = await enabled.choose(rejected, budget)
    assert baseline.candidates[0].action_key not in [c.action_key for c in actual.candidates]
    boundaries.append("已拒绝动作不会被增强重新引入")
    guard.verify(plan["runtime"])
    b.write(OUT / "behavior-results.json", reports)
    b.write(OUT / "checks.json", {"status": "PASS_OFFLINE_PROTOTYPE_ONLY", "requests": len(reports),
        "disabled_exact_v2": len(reports), "outcomes": dict(Counter(r["status"] for r in reports)),
        "first_changes": sum(r["changed"] for r in reports), "arithmetic": arithmetic, "boundaries": boundaries,
        "rule_calls": sum(r["rule_calls"] for r in reports), "max_elapsed_seconds": max(r["elapsed_seconds"] for r in reports),
        "elapsed_seconds": perf_counter() - started, "model_calls": 0, "effect_tables": 0,
        "confirmation_roots": 0, "release_eligible": False})
    print("checks", b.read(OUT / "checks.json"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "check"))
    args = parser.parse_args()
    prepare() if args.operation == "prepare" else asyncio.run(checks())
