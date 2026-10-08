"""两个预选共有分歧的完整首摸条件分布；唯一规则来源，无新策略或效果桌赛。"""

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
from collections import Counter
from dataclasses import asdict
from fractions import Fraction
from time import perf_counter

import followup_balance_diagnosis as diagnosis
import followup_quality_probe as material_source
from followup_rule_probe import hypothetical_observation
from hangma_bot.hangma.engine import HangmaRules
from hangma_bot.hangma.interface import CandidateFactKind, RuleCompleteness
from hangma_bot.hangma.public_tile_counts import count_public_tiles
from hangma_bot.kernel.actions import CANONICAL_TILE_ORDER, Discard
from hangma_bot.kernel.config import RuleConfig

b = diagnosis.b
OUT = b.HERE / "followup-balance-branch-probe-20260920"


def prepare():
    """每配置取双方最早共有分歧，不按摸牌分布筛选；先冻结至多140规则调用。"""
    assert not OUT.exists()
    diagnostic = b.read(diagnosis.OUT / "manifest.json")
    diagnosis.parent.guard.verify(diagnostic["runtime"])
    diagnosis.prior.verify_inputs(b.read(diagnosis.prior.OUT / "evaluation-plan.json"))
    summary = b.read(diagnosis.OUT / "summary.json")
    assert summary["status"] == "COMPLETE_PAIRED_DIAGNOSTIC_ONLY" and summary["full_tables"] == 8
    process = b.read(diagnosis.OUT / "process.json")
    assert process["returncode"] == 0 and not process["timed_out"] and not process["group_still_alive"]
    cases = []
    dependencies = [diagnosis.OUT / name for name in ("manifest.json", "summary.json", "process.json", "panel.json")]
    for direction in ("negative", "positive"):
        paths = [diagnosis.OUT / (direction + "-" + arm + "-diagnostic.json") for arm in ("baseline", "candidate")]
        dependencies += paths
        a, z = [b.read(path)["rows"] for path in paths]
        by_id = {r["window_id"]: r for r in z}
        chosen = next(r for r in a if r["window_id"] in by_id)
        other = by_id[chosen["window_id"]]
        assert chosen["candidate_audit"]["qualities"] == other["candidate_audit"]["qualities"]
        assert chosen["candidate_audit"]["ranking_rows"] == other["candidate_audit"]["ranking_rows"]
        path = diagnosis.OUT / "windows" / (chosen["window_id"] + ".json")
        request, hand, _, _ = material_source.material(b.read(path))
        audit = chosen["candidate_audit"]
        assert audit["status"] == "EVALUATED" and audit["changed"]
        keys = [audit["base_first"], audit["selected_first"]]
        facts = {c.action_key: c for c in request.rules.legal_candidates}
        target = [diagnosis.parent.policy.comparable_fact(facts[k]) for k in keys]
        assert target[0] == target[1] and target[0] is not None
        dependencies.append(path)
        cases.append({"direction": direction, "window_id": chosen["window_id"], "input": str(path),
            "actions": keys, "direct_shanten": target[0][0], "direct_support": target[0][1],
            "original_qualities": [q for q in audit["qualities"] if q["action_key"] in keys],
            "v2_total_gap": chosen["v2_total_gap"], "v2_part_differences": chosen["part_differences_new_minus_v2"],
            "round_no": request.observation.round_no, "snapshot_seq": request.observation.snapshot_seq,
            "remaining_tile_count": request.observation.remaining_tile_count,
            "visible_hand": [t.code for t in hand]})
    versions = diagnosis.natural.stage.contract_versions_block(b.read(b.ROUTE / "contracts/group-dev-v1.json"))
    OUT.mkdir()
    b.write(OUT / "manifest.json", {"schema": "followup-balance-branch-probe/1", "created_at_utc": b.search.utc_now(),
        "cases": cases, "input_digests": {str(p): b.digest(p.read_bytes()) for p in dependencies},
        "runtime": diagnosis.parent.guard.capture(source_paths=[*b.HERE.glob("*.py"), diagnosis.core.OUT / "ranking.py"]),
        "rule_config": {k: versions[k] for k in ("ruleset_version", "base_score", "you_cai_bi_kao")},
        "max_rule_calls": 140, "max_process_seconds": 120,
        "selection": "负、正配置各取基线顺序中双方最早共有分歧；只比较V2首选与实际候选首选，取舍前不计算后继分布",
        "hypothesis": "使用既有局部条件观察：先弃指定牌，再假设本人普通摸一张，其他公开信息暂时冻结。不是实际未来轮转，未模拟他家行为或真实牌墙。",
        "analysis": "唯一规则入口重算当前事实及所有正未见枚数首摸；合法弃牌按最小向听、最大公开有效枚数比较。推进/不推进分组报告，其他合法动作仅记录。",
        "units": "首摸权重为公开未见枚数，支持加权和单位枚²；归一化仅为条件计数代理，非校准概率或真实期望积分。",
        "model_calls": 0, "effect_tables": 0, "confirmation_roots": 0, "release_eligible": False})
    print("frozen two earliest shared differences", [(c["direction"], c["actions"]) for c in cases], flush=True)


def fact(candidate):
    """只允许完整合法弃牌牌效；未知事实拒绝视为零。"""
    f = candidate.facts
    assert isinstance(candidate.action, Discard) and f is not None
    assert f.fact_kind is CandidateFactKind.HAND_PROGRESS and f.completeness is RuleCompleteness.COMPLETE
    assert type(f.shanten_after) is int
    return {"action_key": candidate.action_key, "shanten": f.shanten_after,
        "support": sum(t.remaining_estimate for t in f.useful_tiles),
        "useful": {t.code: t.remaining_estimate for t in f.useful_tiles}}


def summarize(branches):
    """按结果向听分组给出完整加权直方图；各分组不混成同一效用。"""
    result = {}
    for q in sorted({r["best_shanten"] for r in branches}):
        subset = [r for r in branches if r["best_shanten"] == q]
        weight = sum(r["unseen_weight"] for r in subset)
        weighted = sum(r["unseen_weight"] * r["best_support"] for r in subset)
        average = Fraction(weighted, weight)
        variance = sum(Fraction(r["unseen_weight"], weight) * (r["best_support"] - average) ** 2 for r in subset)
        histogram = Counter()
        for row in subset:
            histogram[str(row["best_support"])] += row["unseen_weight"]
        result[str(q)] = {"first_draw_weight": weight, "weighted_support_sum": weighted,
            "weighted_mean_support": str(average), "weighted_population_variance": str(variance),
            "support_histogram_weighted": dict(sorted(histogram.items(), key=lambda x: int(x[0]))),
            "min_support": min(r["best_support"] for r in subset), "max_support": max(r["best_support"] for r in subset)}
    return result


def run():
    """枚举所有条件分支并复现原Q；记录其他动作而不宣称弃牌续接最优。"""
    plan = b.read(OUT / "manifest.json")
    diagnosis.parent.guard.verify(plan["runtime"])
    for path, digest in plan["input_digests"].items():
        assert b.digest(b.Path(path).read_bytes()) == digest
    assert not (OUT / "started.json").exists()
    b.write(OUT / "started.json", {"at_utc": b.search.utc_now()})
    rules = HangmaRules(RuleConfig(**plan["rule_config"]))
    count = 0
    started = perf_counter()
    reports = []
    def analyze(obs):
        nonlocal count
        count += 1
        assert count <= plan["max_rule_calls"]
        value = rules.analyze(obs)
        assert value.completeness is RuleCompleteness.COMPLETE and not value.issues, [asdict(x) for x in value.issues]
        return value
    for index, case in enumerate(plan["cases"], 1):
        request, full, _, unseen = material_source.material(b.read(b.Path(case["input"])))
        original = {c.action_key: c for c in request.rules.legal_candidates}
        fresh = {c.action_key: c for c in analyze(request.observation).legal_candidates}
        variants = []
        for key in case["actions"]:
            current = fact(original[key])
            assert current == fact(fresh[key])
            assert current["shanten"] == case["direct_shanten"] and current["support"] == case["direct_support"]
            assert all(unseen[code] == n for code, n in current["useful"].items())
            branches = []
            for code, weight in unseen.items():
                if weight <= 0:
                    continue
                obs = hypothetical_observation(request, full, original[key].action.tile.code, code)
                public = count_public_tiles(obs)
                assert all(v is not None for v in public)
                hand = Counter(t.code for t in obs.my_hand + (obs.drawn_tile,))
                actual_unseen = {c: max(0, 4 - hand[c] - public[i]) for i, c in enumerate(CANONICAL_TILE_ORDER)}
                expected_unseen = dict(unseen)
                expected_unseen[code] -= 1
                assert actual_unseen == expected_unseen
                begin = perf_counter()
                analysis = analyze(obs)
                elapsed = perf_counter() - begin
                choices = [fact(c) for c in analysis.legal_candidates if isinstance(c.action, Discard)]
                assert choices
                assert all(v == actual_unseen[t] for c in choices for t, v in c["useful"].items())
                best = min(choices, key=lambda c: (c["shanten"], -c["support"], c["action_key"]))
                directly_useful = code in current["useful"]
                assert best["shanten"] == current["shanten"] - int(directly_useful), (key, code, best, current)
                branches.append({"draw": code, "unseen_weight": weight, "directly_useful": directly_useful,
                    "best_shanten": best["shanten"], "best_support": best["support"],
                    "best_action_keys": [c["action_key"] for c in choices if (c["shanten"], c["support"]) == (best["shanten"], best["support"])],
                    "all_legal_discards": choices, "other_legal_actions": [c.action_key for c in analysis.legal_candidates if not isinstance(c.action, Discard)],
                    "rule_seconds": elapsed, "public_unseen_counts_verified": True})
            nonprogress = [r for r in branches if not r["directly_useful"]]
            progress = [r for r in branches if r["directly_useful"]]
            q_value = sum(r["unseen_weight"] * max(0, r["best_support"] - current["support"]) for r in nonprogress)
            old = next(q for q in case["original_qualities"] if q["action_key"] == key)
            assert q_value == old["improvement_weighted_sum"] and sum(r["unseen_weight"] for r in nonprogress) == old["nonprogress_weight"]
            assert sum(r["unseen_weight"] for r in progress) == current["support"]
            variants.append({"action_key": key, "current": current, "groups_by_shanten": summarize(branches),
                "q_reproduced": True, "q": q_value, "branches": branches})
        q = str(case["direct_shanten"] - 1)
        p0, p1 = [v["groups_by_shanten"][q] for v in variants]
        result = {"index": index, "case": case, "variants": variants,
            "direct_progress_weight_equal": p0["first_draw_weight"] == p1["first_draw_weight"],
            "direct_progress_weighted_support_different": p0["weighted_support_sum"] != p1["weighted_support_sum"],
            "direct_progress_support_distribution_different": p0["support_histogram_weighted"] != p1["support_histogram_weighted"],
            "model_calls": 0, "effect_tables": 0, "release_eligible": False}
        b.write(OUT / ("case-" + str(index) + ".json"), result)
        reports.append(result)
        print(case["direction"], [(v["action_key"], v["q"], v["groups_by_shanten"]) for v in variants], flush=True)
    diagnosis.parent.guard.verify(plan["runtime"])
    rows = [r for c in reports for v in c["variants"] for r in v["branches"]]
    b.write(OUT / "summary.json", {"status": "COMPLETE_CONDITIONAL_DISTRIBUTION_DIAGNOSTIC_ONLY", "cases": len(reports),
        "rule_calls": count, "conditional_draw_windows": len(rows), "legal_discard_facts": sum(len(r["all_legal_discards"]) for r in rows),
        "all_original_q_reproduced": all(v["q_reproduced"] for r in reports for v in r["variants"]),
        "direct_progress_mean_differences": sum(r["direct_progress_weighted_support_different"] for r in reports),
        "direct_progress_distribution_differences": sum(r["direct_progress_support_distribution_different"] for r in reports),
        "other_action_windows": sum(bool(r["other_legal_actions"]) for r in rows),
        "max_rule_seconds": max(r["rule_seconds"] for r in rows), "elapsed_seconds": perf_counter() - started,
        "model_calls": 0, "effect_tables": 0, "confirmation_roots": 0, "release_eligible": False,
        "limits": ["两个事后正负配置中预选最早共有分歧，不是一般性或因果结论", "普通本人续摸且其他公开信息冻结，不是完整未来轨迹", "合法弃牌牌效最优不代表包含其他合法动作的最佳续打", "计数权重不是牌墙概率，分布差异不是效果增益"]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    {"prepare": prepare, "run": run}[args.operation]()
