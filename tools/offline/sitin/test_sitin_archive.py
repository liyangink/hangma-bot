# -*- coding: utf-8 -*-
"""sitin_archive（C2）测试：根级配对统计、8 席档案、panel_epoch 替换、调度与提名。

权威行为 SEARCH-SPACE-REDESIGN-2026-09-16.md §8.1/§8.3/§9.1—§9.3/§14：

- T10：同源多窗/换座只算一个统计根；伪独立样本（同根拆两条）拒绝；
- T11：机会专长即使总体未显著提高仍能入档当父代；反例（代价子场景差）同报；
- T12：挑战者只补部分身份 → 原 epoch 原席保持 + pending 暂存；全体补齐 →
  原子提交新 epoch 统一重排；不同样本集不直接争冠军；
- 统计：无效样本不补零、status 分类、U 区间上下界两套、自比较 d=0、H/M
  分层+声明混合、机会家族 1/2 冻结混合、两子场景原值都在；
- 档案：资格拒绝（安全 FAIL/缺子场景/V2）、排序并列 tiebreak 链、探索席
  最小距离最大化迭代选择、多席单存；
- 调度：序列确定性、空通道跳过、档案空→I1；
- 提名：≤0 不提名、预算不足 pending、成功冻结包完整性；
- 与 evaluation_statistics 的复用边界：mean-of-means 语义一致（真实
  MatchResult 夹具对拍 clustered_bootstrap_ci 点估计）。

预算红线：全部构造 JSON 夹具，零模拟、零桌赛。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import json

import pytest

import sitin_archive as sa

try:
    from pathlib import Path
except ImportError:  # pragma: no cover
    Path = None


# ---------------------------------------------------------------------------
# 夹具构造
# ---------------------------------------------------------------------------


def mk_sample(root, scenario, mix, cid, cand_u, base_u, *,
              baseline_cid="V2_BASE", invalid=False, cost=1.0, role="core"):
    """构造一条 C1 面板双臂样本记录。

    cand_u/base_u：数值点 U，或 (u_low, u_high) 区间元组。
    """
    def arm(cid_self, u):
        if isinstance(u, tuple):
            return {"candidate_id": cid_self, "u_low": float(u[0]), "u_high": float(u[1])}
        return {"candidate_id": cid_self, "u": float(u)}

    return {
        "source_root_id": root,
        "scenario": scenario,
        "opponent_mix": mix,
        "candidate_id": cid,
        "root_role": role,
        "invalid": invalid,
        "arms": {
            "baseline": arm(baseline_cid, base_u),
            "candidate": arm(cid, cand_u),
        },
        "cost": cost,
    }


def window_samples(root, scenario, mix, cid, window_ds, **kwargs):
    """一个根上多窗口样本：window_ds 每窗为配对差（-1/0/1）或 (cand_u, base_u) 元组。"""
    out = []
    for d in window_ds:
        if isinstance(d, tuple):
            cand_u, base_u = d
        else:
            cand_u = 1 if d > 0 else 0
            base_u = 1 if d < 0 else 0
        out.append(mk_sample(root, scenario, mix, cid, cand_u, base_u, **kwargs))
    return out


def panel_samples(cid, scenario, mix, root_ds, **kwargs):
    """一个 (场景×混合) 面板的样本：root_ds = {根 id: [各窗 d]}。"""
    out = []
    for root, window_ds in root_ds.items():
        out.extend(window_samples(root, scenario, mix, cid, window_ds, **kwargs))
    return out


def normal_both_mixes(cid, h_root_ds, m_root_ds, **kwargs):
    """正常面板 H/M 双层样本（声明混合需要两层齐备）。"""
    return (panel_samples(cid, "normal", "H", h_root_ds, **kwargs)
            + panel_samples(cid, "normal", "M", m_root_ds, **kwargs))


def family_samples(cid, family, open_h, open_m, cost_h, cost_m, **kwargs):
    """某家族机会/代价两子场景 H/M 双层样本。"""
    out = []
    for kind, h_ds, m_ds in (("open", open_h, open_m), ("cost", cost_h, cost_m)):
        sub = "{0}_{1}".format(family, kind)
        out.extend(panel_samples(cid, sub, "H", h_ds, **kwargs))
        out.extend(panel_samples(cid, sub, "M", m_ds, **kwargs))
    return out


def get_panel(stats, cid, scenario, mix):
    return stats["by_candidate"][cid]["panels"][scenario]["panels"][mix]


def sig(*actions):
    """行为签名：固定可见窗口上 action_key 序列（全在场，无缺失）。"""
    return {"windows": [
        {"window_id": "w{0}".format(i), "action_key": a, "missing": False}
        for i, a in enumerate(actions)
    ]}


# ---------------------------------------------------------------------------
# 统计（§8.1）
# ---------------------------------------------------------------------------


class TestPairedStageStatistics:
    def test_invalid_sample_not_zero_filled_invalid_only(self):
        bad = mk_sample("r1", "normal", "H", "c1", 1.0, 0.0)
        bad["arms"]["candidate"]["usable"] = False
        bad["arms"]["candidate"]["error"] = "续打未完成"
        stats = sa.paired_stage_statistics([bad])
        panel = get_panel(stats, "c1", "normal", "H")
        assert panel["status"] == "invalid_only"
        assert panel["n_roots"] == 0
        assert panel["mean_delta"] is None  # 不补零
        # 原始记录保留（即使候选退出）。
        assert stats["invalid_count"] == 1
        assert stats["invalid_records"][0]["source_root_id"] == "r1"

    def test_uncomputable_status_when_u_missing(self):
        sample = mk_sample("r1", "normal", "H", "c1", 1.0, 0.0)
        del sample["arms"]["baseline"]["u"]
        stats = sa.paired_stage_statistics([sample])
        panel = get_panel(stats, "c1", "normal", "H")
        assert panel["status"] == "uncomputable"
        assert panel["mean_delta"] is None
        assert stats["uncomputable_count"] == 1
        assert stats["uncomputable_records"][0]["source_root_id"] == "r1"

    def test_insufficient_below_min_roots_no_fake_interval(self):
        samples = panel_samples("c1", "normal", "H", {"r1": [1]})
        stats = sa.paired_stage_statistics(samples)
        panel = get_panel(stats, "c1", "normal", "H")
        assert panel["status"] == "insufficient"
        assert panel["n_roots"] == 1
        assert panel["standard_error"] is None  # 单根无根间标准误，不伪造零误差
        assert panel["interval_95"] is None

    def test_u_interval_gives_conservative_bound_sets(self):
        # 候选 U=[0,1]、基线 U=[0,1]（非自比较）：保守配对差 d_low=-1、d_high=+1。
        samples = [
            mk_sample("r1", "normal", "H", "c1", (0, 1), (0, 1)),
            mk_sample("r2", "normal", "H", "c1", (0, 1), (0, 1)),
        ]
        stats = sa.paired_stage_statistics(samples)
        panel = get_panel(stats, "c1", "normal", "H")
        assert panel["status"] == "ok"
        bounds = panel["delta_bounds"]
        assert bounds["mean_delta_low"] == -1.0
        assert bounds["mean_delta_high"] == 1.0
        assert bounds["mean_delta_low"] < panel["mean_delta"] < bounds["mean_delta_high"]
        assert bounds["unresolved_roots"] == 2
        # 上下界两套统计齐备（区间端点各自的 se/interval 也在）。
        assert bounds["standard_error_low"] is not None
        assert bounds["interval_95_high"] is not None

    def test_self_comparison_d_zero_even_with_intervals(self):
        # §2 self_comparison：两臂同 candidate_id，U 区间也不得变成 [-1,1]。
        samples = [
            mk_sample("r1", "normal", "H", "c1", (0, 1), (0, 1), baseline_cid="c1"),
            mk_sample("r2", "normal", "H", "c1", 1.0, 1.0, baseline_cid="c1"),
        ]
        stats = sa.paired_stage_statistics(samples)
        panel = get_panel(stats, "c1", "normal", "H")
        assert panel["self_comparison"] is True
        assert panel["mean_delta"] == 0.0
        assert panel["standard_error"] == 0.0
        assert panel["interval_95"] == [0.0, 0.0]
        assert panel["delta_bounds"]["mean_delta_low"] == 0.0
        assert panel["delta_bounds"]["mean_delta_high"] == 0.0

    def test_t10_same_root_multiple_windows_single_statistical_root(self):
        # 根 r1 三窗（d=1,1,0 → 根均值 2/3）+ 根 r2 一窗（d=1）→ n_roots=2。
        samples = (panel_samples("c1", "normal", "H", {"r1": [1, 1, 0], "r2": [1]})
                   + panel_samples("c1", "normal", "M", {"r3": [1], "r4": [1]}))
        stats = sa.paired_stage_statistics(samples)
        panel_h = get_panel(stats, "c1", "normal", "H")
        assert panel_h["n_roots"] == 2
        assert panel_h["n_samples"] == 4
        # 等权按根：mean((1+1+0)/3, 1) = 5/6；按窗伪独立会是 3/4。
        assert panel_h["mean_delta"] == pytest.approx(5.0 / 6.0)
        assert panel_h["mean_delta"] != pytest.approx(0.75)

    def test_t10_pseudo_independent_split_rejected(self):
        # 同根拆两条（d=+1 与 d=-1）不等于两根：n_roots 仍为 1，根内先平均。
        split = panel_samples("c1", "normal", "H", {"r1": [1, -1]})
        stats = sa.paired_stage_statistics(split)
        panel = get_panel(stats, "c1", "normal", "H")
        assert panel["n_roots"] == 1
        assert panel["mean_delta"] == 0.0
        assert panel["standard_error"] is None
        # 真两根同样本量：n_roots=2 且有根间标准误。
        real = panel_samples("c1", "normal", "H", {"r1": [1], "r2": [-1]})
        stats2 = sa.paired_stage_statistics(real)
        panel2 = get_panel(stats2, "c1", "normal", "H")
        assert panel2["n_roots"] == 2
        assert panel2["standard_error"] == pytest.approx(1.0)

    def test_hm_stratified_and_declared_mix(self):
        samples = (panel_samples("c1", "normal", "H", {"h1": [1, 0], "h2": [1, 0]})
                   + panel_samples("c1", "normal", "M", {"m1": [1, 1], "m2": [1, 1]}))
        stats = sa.paired_stage_statistics(samples)
        block = stats["by_candidate"]["c1"]["panels"]["normal"]
        assert block["panels"]["H"]["mean_delta"] == 0.5
        assert block["panels"]["M"]["mean_delta"] == 1.0
        declared = block["declared_mix"]
        assert declared["weights"] == {"H": 0.5, "M": 0.5}
        assert declared["mean_delta"] == pytest.approx(0.75)
        assert declared["status"] == "ok"

    def test_declared_mix_missing_side_is_none_not_reweighted(self):
        samples = panel_samples("c1", "normal", "H", {"h1": [1], "h2": [1]})
        stats = sa.paired_stage_statistics(samples)
        declared = stats["by_candidate"]["c1"]["panels"]["normal"]["declared_mix"]
        assert declared["mean_delta"] is None  # 不改权重、不用单侧冒充混合
        assert declared["status"] == "missing_mix"

    def test_family_frozen_mix_and_both_subscenario_values(self):
        samples = family_samples("c1", "branch",
                                 open_h={"oh1": [1, 0], "oh2": [1, 0]},
                                 open_m={"om1": [1, 0], "om2": [1, 0]},
                                 cost_h={"ch1": [0, -1], "ch2": [0, 0]},
                                 cost_m={"cm1": [0, 0], "cm2": [0, 0]})
        stats = sa.paired_stage_statistics(samples)
        family = stats["by_candidate"]["c1"]["family_development_values"]["branch"]
        assert family["open"]["declared_mix_value"] == pytest.approx(0.5)
        # cost：H 面板根均值 (-0.5+0)/2=-0.25，M 面板 0 → 声明混合 -0.125。
        assert family["cost"]["declared_mix_value"] == pytest.approx(-0.125)
        assert family["value"] == pytest.approx(0.5 * 0.5 + 0.5 * (-0.125))
        assert family["complete"] is True

    def test_family_value_none_when_subscenario_missing(self):
        samples = family_samples("c1", "chain",
                                 open_h={"oh1": [1, 1]}, open_m={"om1": [1, 1]},
                                 cost_h={}, cost_m={})
        stats = sa.paired_stage_statistics(samples)
        family = stats["by_candidate"]["c1"]["family_development_values"]["chain"]
        assert family["value"] is None  # 缺代价子场景：不填零合成家族值
        assert family["cost"]["declared_mix_value"] is None
        assert family["complete"] is False

    def test_unknown_scenario_and_mix_classified_invalid(self):
        bad_scenario = mk_sample("r1", "mystery", "H", "c1", 1.0, 0.0)
        bad_mix = mk_sample("r2", "normal", "X", "c1", 1.0, 0.0)
        stats = sa.paired_stage_statistics([bad_scenario, bad_mix])
        assert stats["invalid_count"] == 2
        # 无效样本保留在候选面板下但零根：不产生任何统计值。
        panels = stats["by_candidate"]["c1"]["panels"]
        assert set(panels) == {"normal"}  # "mystery" 场景整组不可用
        assert panels["normal"]["panels"] == {}  # mix=X 不形成 H/M 面板
        assert panels["normal"]["declared_mix"]["status"] == "missing_mix"


# ---------------------------------------------------------------------------
# 复用边界：与 evaluation_statistics 的 mean-of-means 语义一致
# ---------------------------------------------------------------------------


class TestEvaluationStatisticsReuse:
    def _match_results(self):
        """构造与 C2 夹具等价的复式配对 MatchResult（真实 evaluation_statistics 输入）。"""
        from hangma_bot.offline.evaluation_results import MatchResult, RuntimeCounts

        # 每窗配对差：r1 窗差 +1、0（根均值 0.5）；r2 窗差 -1、+1（根均值 0）。
        spec = {"r1": [1, 0], "r2": [-1, 1]}
        rows = []
        for scenario, window_ds in spec.items():
            for index, d in enumerate(window_ds):
                pair_id = "{0}-w{1}".format(scenario, index)
                cand_score = 1 if d > 0 else 0
                base_score = 1 if d < 0 else 0
                for policy, score in (("V2_BASE", base_score), ("CAND", cand_score)):
                    rows.append(MatchResult(
                        evaluation_schema_version=1,
                        result_id="{0}-{1}".format(pair_id, policy),
                        source_kind="simulation",
                        scenario_id=scenario,
                        pair_id=pair_id,
                        game_key=None,
                        config=None,
                        policy_ids_by_seat=(policy, "opp", "opp", "opp"),
                        seat_permutation=(0, 1, 2, 3),
                        expected_hands=8,
                        completed_hands=8,
                        scores_before=(0, 0, 0, 0),
                        scores_after=(score, 5, 3, -8),
                        official_ranks=None,
                        status="complete",
                        invalid_reasons=(),
                        runtime_counts=RuntimeCounts(),
                        versions=(),
                        source_refs=(),
                    ))
        return rows

    def test_mean_of_means_matches_clustered_bootstrap_point_estimate(self):
        from hangma_bot.offline.evaluation_statistics import (
            clustered_bootstrap_ci,
            metric_fn_for,
            pair_matches,
        )

        c2_samples = panel_samples("CAND", "normal", "H", {"r1": [1, 0], "r2": [-1, 1]})
        stats = sa.paired_stage_statistics(c2_samples)
        panel = get_panel(stats, "CAND", "normal", "H")

        results = self._match_results()
        outcome = pair_matches(results, baseline_policy_id="V2_BASE",
                               challenger_policy_id="CAND")
        assert len(outcome.pairs) == 4
        assert not outcome.unpaired_reasons
        bootstrap = clustered_bootstrap_ci(
            outcome.pairs, "V2_BASE", "CAND",
            metric_fn_for("table_score_delta"),
            metric_name="table_score_delta", n_resamples=100, seed=7)

        # 复用点锁死：同数据下根级等权 mean-of-means 与聚类 Bootstrap 点估计一致，
        # 且抽样单位数一致（根数 == scenario 数）。
        assert panel["mean_delta"] == pytest.approx(bootstrap.point_estimate)
        assert panel["mean_delta"] == pytest.approx(0.25)
        assert panel["n_roots"] == bootstrap.n_scenarios == 2

    def test_excluded_metric_not_zero_filled_consistent_discipline(self):
        # evaluation_statistics：指标缺失只计数排除不补零；本模块 uncomputable 同纪律。
        sample = mk_sample("r1", "normal", "H", "c1", 1.0, 0.0)
        sample["arms"]["baseline"].pop("u")
        stats = sa.paired_stage_statistics([sample])
        panel = get_panel(stats, "c1", "normal", "H")
        assert panel["status"] == "uncomputable"
        assert panel["n_roots"] == 0
        assert panel["mean_delta"] is None  # 不补零：缺事实只计数
        assert stats["uncomputable_count"] == 1
        assert stats["uncomputable_records"][0]["source_root_id"] == "r1"


# ---------------------------------------------------------------------------
# 档案（§9.1/§9.2）
# ---------------------------------------------------------------------------


def entry_with_overall(cid, h_root_ds, m_root_ds, *, cost=1.0, **kwargs):
    samples = normal_both_mixes(cid, h_root_ds, m_root_ds, cost=cost)
    return sa.build_archive_entry(cid, samples, **kwargs)


class TestArchive:
    def test_v2_baseline_never_occupies(self):
        v2 = entry_with_overall("weighted_heuristic_v2", {"h1": [1, 1]}, {"m1": [1, 1]},
                                kind="v2_baseline")
        archive = sa.update_archive([v2])
        assert all("weighted_heuristic_v2" not in ids for ids in archive["slots"].values())
        assert "weighted_heuristic_v2" in archive["ineligible"]
        assert archive["distinct_candidates"] == []

    def test_safety_fail_excluded(self):
        bad = entry_with_overall("c1", {"h1": [1, 1]}, {"m1": [1, 1]},
                                 safety={"status": "FAIL"})
        archive = sa.update_archive([bad])
        assert archive["slots"]["overall"] == []
        assert "非 PASS" in archive["ineligible"]["c1"]
        assert "FAIL" in archive["ineligible"]["c1"]

    def test_effect_failure_unresolved_excluded(self):
        broken = entry_with_overall("c1", {"h1": [1, 1]}, {"m1": [1, 1]},
                                    effect_failure_unresolved=True)
        archive = sa.update_archive([broken])
        assert archive["slots"]["overall"] == []
        assert "效果执行故障未修复" in archive["ineligible"]["c1"]

    def test_t11_specialist_seated_despite_negative_overall(self):
        # 总体 -0.5（未显著）但 branch 两子场景强 → 占 branch 席可当父代；
        # 整体席另有两名更优者，专长者不因总体未显著被挤掉家族席。
        specialist = sa.build_archive_entry(
            "spec",
            normal_both_mixes("spec", {"h1": [-1, 0]}, {"m1": [-1, 0]})
            + family_samples("spec", "branch",
                             open_h={"oh1": [1, 0]}, open_m={"om1": [1, 0]},
                             cost_h={"ch1": [1, 0]}, cost_m={"cm1": [1, 0]}))
        generalist = entry_with_overall("gen", {"h1": [1, 0]}, {"m1": [1, 0]})
        runner_up = entry_with_overall("gen2", {"h1": [1, 0]}, {"m1": [0, 0]})
        archive = sa.update_archive([specialist, generalist, runner_up])
        assert archive["slots"]["branch"] == ["spec"]
        assert "spec" not in archive["slots"]["overall"]
        assert archive["slots"]["overall"] == ["gen", "gen2"]
        # spec 可当父代：专长通道调度能取到它（第 2 次 M1 是专长位）。
        plans = []
        history = []
        for _ in range(3):
            plan = sa.next_generation_plan(archive, history)
            plans.append(plan)
            history.append({k: plan[k] for k in ("operator", "parent_candidate_id",
                                                 "channel", "family")})
        assert plans[2]["operator"] == "M1"
        assert plans[2]["channel"] == "specialty"
        assert plans[2]["family"] == "branch"
        assert plans[2]["parent_candidate_id"] == "spec"

    def test_t11_counterexample_subscenario_reported_not_masked(self):
        # 机会 +0.5 / 代价 -0.25：家族值 = 两者各 1/2，原值同时可见。
        spec = sa.build_archive_entry(
            "spec2",
            family_samples("spec2", "baotou",
                           open_h={"oh1": [1, 0]}, open_m={"om1": [1, 0]},
                           cost_h={"ch1": [0, -1]}, cost_m={"cm1": [0, 0]}))
        archive = sa.update_archive([spec])
        row = archive["selection_report"]["family"]["baotou"][0]
        assert row["candidate_id"] == "spec2"
        assert row["open_value"] == pytest.approx(0.5)
        assert row["cost_value"] == pytest.approx(-0.25)
        assert row["value"] == pytest.approx(0.125)

    def test_family_slot_requires_both_subscenarios_no_zero_fill(self):
        partial = sa.build_archive_entry(
            "onlyopen",
            family_samples("onlyopen", "chain",
                           open_h={"oh1": [1, 1]}, open_m={"om1": [1, 1]},
                           cost_h={}, cost_m={}),
            behavior_signature=sig("a", "b"))
        archive = sa.update_archive([partial])
        assert archive["slots"]["chain"] == []  # 缺代价子场景不填零争席
        # 可保留探索身份：有行为签名即入探索池。
        assert "onlyopen" in archive["slots"]["exploration"]

    def test_overall_tiebreak_unknown_ratio_then_cost(self):
        unresolved_arm = ((0, 1), 0.0)  # d_point .5 / d_low 0（未分辨）
        def roots_for(pattern):
            h, m = {}, {}
            for i, kind in enumerate(pattern):
                if kind == "U":
                    h["h{0}".format(i)] = [unresolved_arm]
                    m["m{0}".format(i)] = [unresolved_arm]
                else:
                    h["h{0}".format(i)] = [kind]
                    m["m{0}".format(i)] = [kind]
            return h, m

        # 三者 sort_value 同为 0.5：c1 未知比例 0.5；c2/c3 未知比例 0.25，
        # c3 成本更低 → 期望排序 [c3, c2, c1]，前二入席。
        c1 = entry_with_overall("c1", *roots_for([1, 1, "U", "U"]))
        c2 = entry_with_overall("c2", *roots_for([1, 1, "U", 0]), cost=2.0)
        c3 = entry_with_overall("c3", *roots_for([1, 1, "U", 0]), cost=1.0)
        archive = sa.update_archive([c1, c2, c3])
        assert archive["slots"]["overall"] == ["c3", "c2"]
        report = archive["selection_report"]["overall"]
        assert [r["candidate_id"] for r in report] == ["c3", "c2", "c1"]

    def test_family_tiebreak_by_candidate_id(self):
        left = sa.build_archive_entry(
            "bbb", family_samples("bbb", "four_white",
                                  open_h={"o": [1]}, open_m={"o": [1]},
                                  cost_h={"c": [0]}, cost_m={"c": [0]}))
        right = sa.build_archive_entry(
            "aaa", family_samples("aaa", "four_white",
                                  open_h={"o": [1]}, open_m={"o": [1]},
                                  cost_h={"c": [0]}, cost_m={"c": [0]}))
        archive = sa.update_archive([left, right])
        assert archive["slots"]["four_white"] == ["aaa"]

    def test_exploration_farthest_first_iterative_selection(self):
        # 无任何已入档席位者：首轮以池内最大距离作种子分；X/Y 同分 1.0 →
        # 证据同 → candidate_id 字典序取 X；次轮 Y（对 X 最小距离 1.0 最大）。
        entries = [
            sa.build_archive_entry("X", [], behavior_signature=sig("A", "A", "A")),
            sa.build_archive_entry("Y", [], behavior_signature=sig("B", "B", "B")),
            sa.build_archive_entry("Z", [], behavior_signature=sig("A", "A", "B")),
        ]
        archive = sa.update_archive(entries)
        assert archive["slots"]["exploration"] == ["X", "Y"]
        steps = archive["selection_report"]["exploration"]["steps"]
        assert steps[0]["scores"]["Z"] == pytest.approx(2.0 / 3.0)
        assert steps[1]["scores"]["Z"] == pytest.approx(1.0 / 3.0)

    def test_exploration_seeded_by_seated_signatures(self):
        # 有已入档席位者 S（签名 AAA）：Y 对 S 距离 1.0 最大先入，次轮 Z（1/3）> X（0）。
        seated = entry_with_overall("S", {"h": [1, 1]}, {"m": [1, 1]},
                                    behavior_signature=sig("A", "A", "A"))
        pool = [
            sa.build_archive_entry("X", [], behavior_signature=sig("A", "A", "A")),
            sa.build_archive_entry("Y", [], behavior_signature=sig("B", "B", "B")),
            sa.build_archive_entry("Z", [], behavior_signature=sig("A", "A", "B")),
        ]
        archive = sa.update_archive([seated] + pool)
        assert archive["slots"]["exploration"] == ["Y", "Z"]

    def test_exploration_tie_prefers_less_evidence_then_id(self):
        wide = sa.build_archive_entry("P", [], behavior_signature=sig("A", "A"),
                                      )
        narrow = sa.build_archive_entry("Q", [], behavior_signature=sig("A", "A"))
        wide["evidence_count"] = 5
        narrow["evidence_count"] = 1
        archive = sa.update_archive([wide, narrow])
        # 全同签名 → 距离全 0：并列取证据较少者 Q——但**同一种行为只占一个探索名额**
        # （P13 / 复审 A4r：两个探索席不得同行为），故第二席留空而非由 P 填满。
        # 判据未放宽：并列裁决仍必须落在证据较少者（若按 candidate_id 取，会选中 P）。
        assert archive["slots"]["exploration"] == ["Q"]
        assert archive["behavior_duplicates"] == {"P": ["Q"]}
        sources = archive["selection_report"]["exploration"][
            "excluded_behavior_duplicate_sources"]
        assert sources == {"P": {"basis": sa.EXPLORATION_DUPLICATE_BASIS,
                                 "digest": narrow["behavior_digest"],
                                 "owners": ["Q"]}}, sources
        # 两个候选的签名摘要确实相同（排除依据就是它）。
        assert wide["behavior_digest"] == narrow["behavior_digest"]

    def test_multislot_single_storage(self):
        champion = sa.build_archive_entry(
            "champ",
            normal_both_mixes("champ", {"h": [1, 1]}, {"m": [1, 1]})
            + family_samples("champ", "branch",
                             open_h={"o": [1, 1]}, open_m={"o": [1, 1]},
                             cost_h={"c": [1, 1]}, cost_m={"c": [1, 1]}))
        archive = sa.update_archive([champion])
        assert "champ" in archive["slots"]["overall"]
        assert archive["slots"]["branch"] == ["champ"]
        # 多席单存：entries 只有一份，distinct 计数不重复。
        assert list(archive["entries"]) == ["champ"]
        assert archive["distinct_candidates"] == ["champ"]

    def test_no_data_no_self_reported_value_fill(self):
        phantom = sa.build_archive_entry("ghost", [], self_reported_value=99.0)
        archive = sa.update_archive([phantom])
        assert all("ghost" not in ids for ids in archive["slots"].values())
        assert archive["distinct_candidates"] == []

    def test_entry_records_root_level_evaluations(self):
        entry = entry_with_overall("c1", {"h1": [1, 0]}, {"m1": [1]})
        assert set(entry["normal_evaluations"]) == {"h1", "m1"}
        assert entry["normal_evaluations"]["h1"]["d_point"] == pytest.approx(0.5)
        assert entry["overall"]["sort_value"] == pytest.approx(0.75)
        assert entry["overall"]["unknown_ratio"] == 0.0


# ---------------------------------------------------------------------------
# panel_epoch 与挑战替换（§9.2；T12）
# ---------------------------------------------------------------------------


def rec(d, mix=None):
    return {"d_point": float(d), "d_low": float(d), "d_high": float(d),
            "unknown": False, "opponent_mix": mix, "cost": 1.0}


NORMAL_CORE = [
    {"root_id": "n1", "opponent_mix": "H"}, {"root_id": "n2", "opponent_mix": "H"},
    {"root_id": "n3", "opponent_mix": "M"}, {"root_id": "n4", "opponent_mix": "M"},
]
NORMAL_REFRESH = [
    {"root_id": "f1", "opponent_mix": "H"}, {"root_id": "f2", "opponent_mix": "H"},
    {"root_id": "f3", "opponent_mix": "M"}, {"root_id": "f4", "opponent_mix": "M"},
]


def incumbent_entry(cid="inc", core_values=(0.5, 0.5, 0.0, 0.0)):
    return {
        "candidate_id": cid, "kind": "action_value_v1",
        "safety": {"status": "PASS"}, "effect_failure_unresolved": False,
        "overall": {"sort_value": 0.25, "unknown_ratio": 0.0, "total_cost": 4.0},
        "family": {}, "behavior_signature": None, "evidence_count": 4,
        "normal_evaluations": {
            root["root_id"]: rec(value, root["opponent_mix"])
            for root, value in zip(NORMAL_CORE, core_values)
        },
        "family_evaluations": {},
    }


def challenger_entry(cid="ch", core_values=(0.75, 0.75, 0.75, 0.75),
                    store_evals=True):
    entry = incumbent_entry(cid, core_values)
    entry["normal_evaluations"] = {
        root["root_id"]: rec(value, root["opponent_mix"])
        for root, value in zip(NORMAL_CORE, core_values)
    } if store_evals else {}
    return entry


def challenge_archive():
    inc = incumbent_entry()
    ch = challenger_entry()
    return {
        "schema": sa.ARCHIVE_SCHEMA,
        "slots": {"overall": ["inc"], "exploration": []},
        "entries": {"inc": inc, "ch": ch},
        "exploration_queue": [],
    }


class TestChannelEpochChallenge:
    def test_build_epoch_marks_dev_roots_not_confirmation_eligible(self):
        # Q2：开发核心根正是开发通道用过的根——不再默认确认可用；刷新根同理。
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE,
                                       refresh_roots=NORMAL_REFRESH, epoch_no=2)
        assert epoch["roots"][0]["usage"] == "development_core"
        refresh_ids = {r["root_id"] for r in epoch["roots"] if r["role"] == "refresh"}
        assert refresh_ids == {"f1", "f2", "f3", "f4"}
        assert sa.confirmation_eligible_roots(epoch) == []
        for row in epoch["roots"]:
            assert row["usage"] in ("development_core", "development_refresh")
            assert row["confirmation_eligible"] is False

    def test_build_epoch_requires_both_mixes(self):
        with pytest.raises(ValueError, match="缺对手情景"):
            sa.build_channel_epoch("normal", [
                {"root_id": "n1", "opponent_mix": "H"},
                {"root_id": "n2", "opponent_mix": "H"},
            ])

    def test_t12_partial_identity_keeps_epoch_and_slots_pending(self):
        archive = challenge_archive()
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)
        ch_evals = dict(challenger_entry()["normal_evaluations"])
        for root in NORMAL_REFRESH:  # 挑战者刷新根已评估
            ch_evals[root["root_id"]] = rec(1.0, root["opponent_mix"])
        result = sa.apply_challenge(
            archive, epoch, "ch", {"ch": ch_evals}, refresh_roots=NORMAL_REFRESH)
        # 原席者 inc 缺 4 条刷新根 → 部分完成：原 epoch 原席保持，pending 暂存。
        assert result["status"] == "pending_partial"
        assert result["phase"] == "phase2"
        assert result["archive"]["slots"]["overall"] == ["inc"]
        assert result["epoch"]["epoch"] == 1
        pending = result["pending"]
        assert pending["challenger_id"] == "ch"
        assert set(pending["missing"]) == {"inc"}
        assert len(pending["missing"]["inc"]) == 4
        assert pending["received"]["ch"]["f1"]["d_low"] == 1.0  # 暂存不丢弃

    def test_t12_challenger_phase1_missing_is_pending(self):
        # 挑战者档案里没有存量核心根评估，本次只补 1/4 个当前根。
        archive = challenge_archive()
        archive["entries"]["ch"] = challenger_entry(store_evals=False)
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)
        partial = {"ch": {"n1": rec(0.9, "H")}}
        result = sa.apply_challenge(archive, epoch, "ch", partial,
                                    refresh_roots=NORMAL_REFRESH)
        assert result["status"] == "pending_partial"
        assert result["phase"] == "phase1"
        assert result["missing"]["ch"] == ["n2", "n3", "n4"]
        assert result["archive"]["slots"]["overall"] == ["inc"]
        assert result["pending"]["received"]["ch"]["n1"]["d_low"] == 0.9

    def test_t12_full_completion_commits_new_epoch_atomically(self):
        archive = challenge_archive()
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)
        ch_evals = dict(challenger_entry()["normal_evaluations"])
        inc_evals = dict(incumbent_entry()["normal_evaluations"])
        for root in NORMAL_REFRESH:
            ch_evals[root["root_id"]] = rec(1.0, root["opponent_mix"])
            inc_evals[root["root_id"]] = rec(0.0, root["opponent_mix"])
        result = sa.apply_challenge(
            archive, epoch, "ch",
            {"ch": ch_evals, "inc": inc_evals}, refresh_roots=NORMAL_REFRESH)
        assert result["status"] == "committed"
        assert result["epoch_after"] == 2
        new_epoch = result["new_epoch"]
        assert {r["root_id"] for r in new_epoch["roots"]} == {
            "n1", "n2", "n3", "n4", "f1", "f2", "f3", "f4"}
        # 原子重排：挑战者 0.875 > 原席者 0.25 → 新座次 [ch, inc]。
        assert result["archive"]["slots"]["overall"] == ["ch", "inc"]
        ch_value = next(r for r in result["ranking"] if r["candidate_id"] == "ch")
        assert ch_value["sort_value"] == pytest.approx(0.875)
        # 刷新根/核心根都是开发根：永不流入确认集（Q2）。
        assert sa.confirmation_eligible_roots(new_epoch) == []
        usages = {row["root_id"]: row["usage"] for row in new_epoch["roots"]}
        assert usages["n1"] == "development_core" and usages["f4"] == "development_refresh"
        assert result["archive"]["entries"]["ch"]["normal_evaluations"]["f4"]["d_low"] == 1.0

    def test_t12_different_sample_sets_do_not_compete_directly(self):
        archive = challenge_archive()
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)
        # 挑战者只在 epoch 外多余根 rx 上有数据：不算阶段 1 完成，多余根不参与排序。
        result = sa.apply_challenge(
            archive, epoch, "ch", {"ch": {"rx": rec(5.0, "H")}},
            refresh_roots=NORMAL_REFRESH)
        assert result["status"] == "pending_partial"
        assert result["archive"]["slots"]["overall"] == ["inc"]
        assert any("多余根" in note for note in result["notes"])

    def test_challenge_budget_insufficient_keeps_slots_and_queues(self):
        archive = challenge_archive()
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)
        ch_evals = dict(challenger_entry()["normal_evaluations"])
        for root in NORMAL_REFRESH:
            ch_evals[root["root_id"]] = rec(1.0, root["opponent_mix"])
        result = sa.apply_challenge(
            archive, epoch, "ch", {"ch": ch_evals}, refresh_roots=NORMAL_REFRESH,
            budget=1)  # 还差原席者 4 条刷新评估 > 预算
        assert result["status"] == "budget_insufficient"
        assert result["archive"]["slots"]["overall"] == ["inc"]
        assert result["exploration_queue"] == ["ch"]

    def test_challenge_not_promising_keeps_slots_without_refresh(self):
        archive = challenge_archive()
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)
        weak = challenger_entry("weak", (0.0, 0.0, 0.0, 0.0))  # 0.0 < 0.25
        archive["entries"]["weak"] = weak
        result = sa.apply_challenge(
            archive, epoch, "weak", {"weak": weak["normal_evaluations"]},
            refresh_roots=NORMAL_REFRESH)
        assert result["status"] == "not_promising"
        assert result["archive"]["slots"]["overall"] == ["inc"]

    def test_family_channel_challenge_commit(self):
        core = ([{"root_id": "o_h1", "opponent_mix": "H", "sub_scenario": "branch_open"},
                 {"root_id": "o_h2", "opponent_mix": "H", "sub_scenario": "branch_open"},
                 {"root_id": "o_m1", "opponent_mix": "M", "sub_scenario": "branch_open"},
                 {"root_id": "o_m2", "opponent_mix": "M", "sub_scenario": "branch_open"},
                 {"root_id": "c_h1", "opponent_mix": "H", "sub_scenario": "branch_cost"},
                 {"root_id": "c_h2", "opponent_mix": "H", "sub_scenario": "branch_cost"},
                 {"root_id": "c_m1", "opponent_mix": "M", "sub_scenario": "branch_cost"},
                 {"root_id": "c_m2", "opponent_mix": "M", "sub_scenario": "branch_cost"}])
        refresh = [
            {"root_id": "ro_{0}".format(i), "opponent_mix": "H" if i < 2 else "M",
             "sub_scenario": "branch_open"} for i in range(4)
        ] + [
            {"root_id": "rc_{0}".format(i), "opponent_mix": "H" if i < 2 else "M",
             "sub_scenario": "branch_cost"} for i in range(4)
        ]
        epoch = sa.build_channel_epoch("branch", core)

        def fam_evals(open_d, cost_d):
            out = {"branch_open": {}, "branch_cost": {}}
            for root in core:
                sub = root["sub_scenario"]
                value = open_d if sub.endswith("open") else cost_d
                out[sub][root["root_id"]] = rec(value, root["opponent_mix"])
            for root in refresh:
                out[root["sub_scenario"]][root["root_id"]] = rec(
                    open_d if root["sub_scenario"].endswith("open") else cost_d,
                    root["opponent_mix"])
            return out

        incumbent = incumbent_entry("fbase")
        incumbent["family_evaluations"] = fam_evals(1.0, 0.0)  # 家族值 0.5
        challenger = challenger_entry("fchall")
        challenger["family_evaluations"] = fam_evals(1.0, 1.0)  # 家族值 1.0
        archive = {"schema": sa.ARCHIVE_SCHEMA,
                   "slots": {"branch": ["fbase"], "overall": [], "exploration": []},
                   "entries": {"fbase": incumbent, "fchall": challenger},
                   "exploration_queue": []}
        result = sa.apply_challenge(
            archive, epoch, "fchall",
            {"fchall": challenger["family_evaluations"],
             "fbase": incumbent["family_evaluations"]},
            refresh_roots=refresh)
        assert result["status"] == "committed"
        assert result["archive"]["slots"]["branch"] == ["fchall"]
        winner = next(r for r in result["ranking"] if r["candidate_id"] == "fchall")
        assert winner["sort_value"] == pytest.approx(1.0)

    def test_family_refresh_batch_validation(self):
        epoch = sa.build_channel_epoch("branch", [
            {"root_id": "o_h1", "opponent_mix": "H", "sub_scenario": "branch_open"},
            {"root_id": "o_m1", "opponent_mix": "M", "sub_scenario": "branch_open"},
            {"root_id": "c_h1", "opponent_mix": "H", "sub_scenario": "branch_cost"},
            {"root_id": "c_m1", "opponent_mix": "M", "sub_scenario": "branch_cost"},
        ])
        archive = {"schema": sa.ARCHIVE_SCHEMA, "slots": {"branch": ["x"]},
                   "entries": {"x": incumbent_entry("x")}, "exploration_queue": []}
        bad_batch = [{"root_id": "z1", "opponent_mix": "H",
                      "sub_scenario": "branch_open"}] * 3
        with pytest.raises(ValueError, match="4 根"):
            sa.apply_challenge(archive, epoch, "x", {"x": {}}, refresh_roots=bad_batch)

    def test_challenge_plan_reports_two_phases(self):
        archive = challenge_archive()
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)
        plan = sa.challenge_plan(archive, epoch, "ch", refresh_roots=NORMAL_REFRESH)
        assert plan["phase1_challenger_roots"] == ["n1", "n2", "n3", "n4"]
        assert plan["phase2_participants"] == ["ch", "inc"]
        assert plan["phase2_refresh_roots"] == NORMAL_REFRESH


# ---------------------------------------------------------------------------
# 父代与算子调度（§9.3）
# ---------------------------------------------------------------------------


def scheduling_archive(*, with_families=True, with_exploration=True):
    ids = {"overall": ["o1", "o2"], "exploration": ["e1"] if with_exploration else []}
    if with_families:
        ids.update({"branch": ["b1"], "chain": ["c1x"], "four_white": ["f1"], "baotou": ["b2"]})
    else:
        ids.update({"branch": [], "chain": [], "four_white": [], "baotou": []})
    entries = {cid: {"candidate_id": cid, "kind": "action_value_v1",
                     "safety": {"status": "PASS"},
                     "effect_failure_unresolved": False}
               for members in ids.values() for cid in members}
    return {"schema": sa.ARCHIVE_SCHEMA, "slots": ids, "entries": entries,
            "exploration_queue": []}


def drive_plans(archive, n):
    history = []
    plans = []
    for _ in range(n):
        plan = sa.next_generation_plan(archive, history)
        plans.append(plan)
        history.append({
            "operator": plan["operator"],
            "parent_candidate_id": plan["parent_candidate_id"],
            "channel": plan["channel"],
            "family": plan["family"],
            "status": "generated",  # 失败/重复同样计数：状态不影响序列
        })
    return plans


class TestScheduling:
    def test_first_proposal_is_i1_with_seeds(self):
        archive = scheduling_archive()
        for seed in sa.SEED_IDS:
            archive["entries"][seed] = {
                "candidate_id": seed, "kind": "seed",
                "safety": {"status": "PASS"}, "effect_failure_unresolved": False}
        archive["slots"]["overall"] = ["efficiency_seed", "route_value_seed"]
        plan = sa.next_generation_plan(archive, [])
        assert plan["operator"] == "I1"
        assert plan["parent_candidate_id"] is None
        assert plan["initialization"]["seeds"] == ["efficiency_seed", "route_value_seed"]

    def test_operator_sequence_3m1_1i1_and_failures_consume_quota(self):
        plans = drive_plans(scheduling_archive(), 12)
        operators = [p["operator"] for p in plans]
        assert operators == ["I1"] + ["M1", "M1", "M1", "I1"] * 2 + ["M1", "M1", "M1"]
        # 失败/重复也消耗额度：把状态改成 failed 重放，序列推进不变。
        archive = scheduling_archive()
        history = [
            {**{k: plan[k] for k in ("operator", "parent_candidate_id",
                                     "channel", "family")}, "status": "failed"}
            for plan in plans
        ]
        assert sa.next_generation_plan(archive, history)["operator"] == "I1"

    def test_channel_cycle_and_family_rotation(self):
        plans = drive_plans(scheduling_archive(), 15)
        m1 = [p for p in plans if p["operator"] == "M1"]
        assert len(m1) == 11
        assert [p["channel"] for p in m1] == [
            "overall", "specialty", "overall", "specialty", "exploration",
            "overall", "specialty", "overall", "specialty", "exploration",
            "overall",
        ]
        assert [p["family"] for p in m1 if p["channel"] == "specialty"] == [
            "branch", "chain", "four_white", "baotou"]
        # 通道内最少被使用优先，并列 candidate_id：
        overall_parents = [p["parent_candidate_id"] for p in m1 if p["channel"] == "overall"]
        assert overall_parents == ["o1", "o2", "o1", "o2", "o1"]

    def test_least_used_then_id_tiebreak(self):
        archive = scheduling_archive(with_families=False, with_exploration=False)
        history = [
            {"operator": "I1"},
            {"operator": "M1", "parent_candidate_id": "o1", "channel": "overall",
             "family": None, "status": "ok"},
        ]
        plan = sa.next_generation_plan(archive, history)
        assert plan["operator"] == "M1" and plan["channel"] == "overall"
        assert plan["parent_candidate_id"] == "o2"  # o1 已用 1 次
        fresh = sa.next_generation_plan(archive, [{"operator": "I1"}])
        assert fresh["parent_candidate_id"] == "o1"  # 全未用 → 字典序

    def test_empty_specialty_skips_to_next_nonempty(self):
        archive = scheduling_archive(with_families=False)
        plans = drive_plans(archive, 7)
        m1 = [p for p in plans if p["operator"] == "M1"]
        # 循环位 specialty 为空 → 跳到 5 循环的下一位（overall / exploration）；
        # 循环位置按 M1 调用序固定，跳过不推进轮转计数。
        assert [p["channel"] for p in m1] == [
            "overall", "overall", "overall", "exploration", "exploration"]
        assert all(p["family"] is None for p in m1)

    def test_empty_archive_falls_back_to_i1(self):
        plan = sa.next_generation_plan({}, [{"operator": "M1", "channel": "overall",
                                             "parent_candidate_id": "x",
                                             "family": None, "status": "ok"}] * 5)
        assert plan["operator"] == "I1"
        assert "档案空" in plan["reason"]
        seated_less = {"entries": {"x": {"candidate_id": "x"}},
                       "slots": {"overall": [], "exploration": []}}
        assert sa.next_generation_plan(seated_less, [])["operator"] == "I1"

    def test_slot_usage_after_increments_chosen_parent(self):
        archive = scheduling_archive(with_families=False, with_exploration=False)
        plan = sa.next_generation_plan(archive, [{"operator": "I1"}])
        assert plan["slot_usage_after"]["overall"]["o1"] == 1
        assert plan["slot_usage_after"]["overall"].get("o2", 0) == 0

    def test_pure_function_deterministic(self):
        archive = scheduling_archive()
        history = drive_plans(archive, 6)
        history = [{k: p[k] for k in ("operator", "parent_candidate_id",
                                      "channel", "family")} for p in history]
        first = sa.next_generation_plan(archive, history)
        second = sa.next_generation_plan(archive, history)
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# ---------------------------------------------------------------------------
# 提名（§8.3）
# ---------------------------------------------------------------------------


def nomination_archive():
    strong = incumbent_entry("strong", (0.8, 0.8, 0.6, 0.6))   # 0.7
    weak = incumbent_entry("weak", (0.2, 0.2, 0.0, 0.0))       # 0.1
    return {"schema": sa.ARCHIVE_SCHEMA,
            "slots": {"overall": ["strong"], "exploration": []},
            "entries": {"strong": strong, "weak": weak},
            "exploration_queue": []}


class TestNomination:
    def test_no_positive_candidate_not_nominated(self):
        archive = nomination_archive()
        both_negative = incumbent_entry("neg", (-0.5, -0.5, -0.5, -0.5))
        archive["entries"]["neg"] = both_negative
        del archive["entries"]["strong"], archive["entries"]["weak"]
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)
        result = sa.nominate_candidate(archive, epoch, budget=8,
                                       extra_evaluations={"neg": both_negative["normal_evaluations"]})
        assert result["nominated"] is False
        assert result["reason"] == "no_positive_candidate"
        assert result["v2_virtual_paired_value"] == 0.0
        v2_row = [r for r in result["ranking_view_with_v2"]
                  if r["candidate_id"] == sa.V2_BASELINE_IDS[0]]
        assert v2_row and v2_row[0]["sort_value"] == 0.0 and v2_row[0]["virtual"] is True

    def test_budget_pending_reports_all_candidates_not_excluding_expensive(self):
        archive = nomination_archive()
        del archive["entries"]["strong"]["normal_evaluations"]["n4"]  # strong 缺 1 根
        archive["entries"]["weak"]["normal_evaluations"] = {}         # weak 缺全部 4 根
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)
        # 预算 2 < 需 5 → pending；missing_detail 必须同时列出两个候选
        #（不偷偷排除昂贵候选）。
        result = sa.nominate_candidate(archive, epoch, budget=2)
        assert result["nominated"] is False
        assert result["status"] == "nomination_pending_budget"
        assert set(result["missing_detail"]) == {"strong", "weak"}
        assert result["missing_detail"]["strong"] == ["n4"]
        assert len(result["missing_detail"]["weak"]) == 4

    def test_budget_covered_but_data_missing_is_caller_error(self):
        archive = nomination_archive()
        del archive["entries"]["strong"]["normal_evaluations"]["n4"]
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)
        with pytest.raises(ValueError, match="补齐结果缺失"):
            sa.nominate_candidate(archive, epoch, budget=99)

    def test_success_freezes_complete_package(self):
        archive = nomination_archive()
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)
        result = sa.nominate_candidate(archive, epoch, budget=1)
        assert result["nominated"] is True
        assert result["candidate_id"] == "strong"
        frozen = result["frozen"]
        assert frozen["pool"] == ["strong", "weak"]
        assert frozen["epoch"]["root_ids"] == ["n1", "n2", "n3", "n4"]
        # Q2：epoch 根全部为开发根——确认可用集为空（开发根 ≠ 未消费确认根）。
        assert frozen["epoch"]["confirmation_eligible_roots"] == []
        assert [r["candidate_id"] for r in frozen["ranking"]] == ["strong", "weak"]
        assert frozen["ranking"][0]["sort_value"] == pytest.approx(0.7)
        # 冻结包稳定：同输入两次调用 source_ref 一致（先冻结再看确认数据）。
        again = sa.nominate_candidate(archive, epoch, budget=1)
        assert again["source_ref"] == result["source_ref"]

    def test_ranking_uses_only_epoch_roots(self):
        archive = nomination_archive()
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)
        extra = {"weak": {
            "n1": rec(0.9, "H"), "n2": rec(0.9, "H"),
            "n3": rec(0.9, "M"), "n4": rec(0.9, "M"),
            "rx": rec(99.0, "H"),  # epoch 外多余根
        }}
        result = sa.nominate_candidate(archive, epoch, budget=0,
                                       extra_evaluations=extra)
        assert result["nominated"] is True
        assert result["candidate_id"] == "weak"
        assert any("多余根" in note for note in result["notes"])
        assert result["frozen"]["ranking"][0]["sort_value"] == pytest.approx(0.9)

    def test_non_normal_epoch_rejected(self):
        archive = nomination_archive()
        epoch = sa.build_channel_epoch("branch", [
            {"root_id": "o_h1", "opponent_mix": "H", "sub_scenario": "branch_open"},
            {"root_id": "o_m1", "opponent_mix": "M", "sub_scenario": "branch_open"},
            {"root_id": "c_h1", "opponent_mix": "H", "sub_scenario": "branch_cost"},
            {"root_id": "c_m1", "opponent_mix": "M", "sub_scenario": "branch_cost"},
        ])
        with pytest.raises(ValueError, match="正常通道"):
            sa.nominate_candidate(archive, epoch)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCli:
    @pytest.mark.parametrize("command", ["statistics", "update-archive", "next-plan", "nominate"])
    def test_help_exits_zero(self, command, capsys):
        with pytest.raises(SystemExit) as exc:
            sa.main([command, "--help"])
        assert exc.value.code == 0
        assert command in capsys.readouterr().out

    def test_statistics_end_to_end(self, tmp_path):
        samples = normal_both_mixes("c1", {"h1": [1, 0]}, {"m1": [1]})
        path = tmp_path / "samples.json"
        path.write_text(json.dumps(samples), encoding="utf-8")
        out = tmp_path / "stats.json"
        code = sa.main(["statistics", "--samples", str(path), "--out", str(out)])
        assert code == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["schema"] == sa.STATISTICS_SCHEMA
        assert payload["by_candidate"]["c1"]["panels"]["normal"]["panels"]["H"]["n_roots"] == 1

    def test_update_archive_and_next_plan_end_to_end(self, tmp_path):
        samples = (normal_both_mixes("a", {"h1": [1, 1]}, {"m1": [1, 1]})
                   + family_samples("b", "branch", {"o": [1]}, {"o": [1]},
                                    {"c": [0]}, {"c": [0]}))
        samples_path = tmp_path / "samples.json"
        samples_path.write_text(json.dumps(samples), encoding="utf-8")
        signatures = tmp_path / "sigs.json"
        signatures.write_text(json.dumps({"b": sig("x", "y")}), encoding="utf-8")
        archive_out = tmp_path / "archive.json"
        assert sa.main(["update-archive", "--samples", str(samples_path),
                        "--signatures", str(signatures), "--out", str(archive_out)]) == 0
        archive = json.loads(archive_out.read_text(encoding="utf-8"))
        assert archive["slots"]["overall"] == ["a"]
        assert archive["slots"]["branch"] == ["b"]

        history = tmp_path / "history.json"
        history.write_text(json.dumps([
            {"operator": "I1", "parent_candidate_id": None,
             "channel": None, "family": None, "status": "ok"},
        ]), encoding="utf-8")
        plan_out = tmp_path / "plan.json"
        assert sa.main(["next-plan", "--archive", str(archive_out),
                        "--history", str(history), "--out", str(plan_out)]) == 0
        plan = json.loads(plan_out.read_text(encoding="utf-8"))
        assert plan["operator"] == "M1" and plan["channel"] == "overall"

    def test_nominate_end_to_end(self, tmp_path):
        archive = nomination_archive()
        archive_path = tmp_path / "archive.json"
        archive_path.write_text(json.dumps(archive), encoding="utf-8")
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)
        epoch_path = tmp_path / "epoch.json"
        epoch_path.write_text(json.dumps(epoch), encoding="utf-8")
        code = sa.main(["nominate", "--archive", str(archive_path),
                        "--epoch", str(epoch_path), "--budget", "1"])
        assert code == 0


# ---------------------------------------------------------------------------
# 回归：batch7 真实样本（build_archive_entry 身份不符 fail-closed）
# ---------------------------------------------------------------------------

BATCH7_EVAL = (_project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/batch7/eval'))


def _batch7_samples(name):
    """复刻 batch8 收集逻辑：scenario=normal、opponent_mix=H/M、r2 目录根加后缀。"""
    samples = []
    for mix in ("H", "M"):
        for sub in ("natural-" + mix, "natural-" + mix + "-r2"):
            directory = _project_file(_PROJECT_ROOT, BATCH7_EVAL / name / sub)
            suffix = "-r2" if sub.endswith("-r2") else ""
            for line in (directory / "samples.jsonl").read_text(
                    encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                row["scenario"] = "normal"
                row["opponent_mix"] = mix
                if suffix:
                    for key in ("root_id", "source_root_id"):
                        if row.get(key):
                            row[key] = row[key] + suffix
                samples.append(row)
    return samples


@pytest.mark.skipif(not BATCH7_EVAL.exists(), reason="batch7 证据样本不在本检出")
class TestBatch7RealSamplesRegression:
    def test_real_samples_build_entries_cover_all_four_roots(self):
        # 两候选（种子 eff + 生成 i1）各跑 build_archive_entry：identity 取自样本行
        # 本身（不手工转写，防 63/64 字符事故重演），normal_evaluations 必须覆盖
        # 全部 4 个来源根（H/M × 原批/r2 批）且 overall 非空。
        for name in ("efficiency_seed-6d9c1d59", "i1-766712b6"):
            if not (_project_file(_PROJECT_ROOT, BATCH7_EVAL / name)).exists():
                pytest.skip("batch7 候选目录缺失：{0}".format(name))
            samples = _batch7_samples(name)
            actual_ids = {row["candidate_id"] for row in samples}
            assert len(actual_ids) == 1
            cid = actual_ids.pop()
            entry = sa.build_archive_entry(cid, samples, min_roots=1)
            expected_roots = {row["source_root_id"] for row in samples}
            assert len(expected_roots) == 4
            assert set(entry["normal_evaluations"]) == expected_roots
            assert entry["overall"] is not None
            assert entry["overall"]["n_roots"] == 4

    def test_identity_mismatch_fails_closed_not_silent_empty(self):
        # 复现事故形状：把真实 identity 抄错一个字符（模拟 63/64 转写丢失）后
        # 调用必须立即 ValueError 并报出样本实际身份，而不是返回空条目让下游
        # 误报 nomination_pending_budget。
        samples = _batch7_samples("efficiency_seed-6d9c1d59")
        actual_id = samples[0]["candidate_id"]
        corrupted = actual_id[:53] + actual_id[54:]  # 去掉一位 → 与事故同形
        assert corrupted != actual_id
        with pytest.raises(ValueError, match="不在所给样本中"):
            sa.build_archive_entry(corrupted, samples, min_roots=1)

    def test_empty_samples_still_build_phantom_entry(self):
        # 既有语义保持：零样本条目（注册未评估）不触发身份报错。
        entry = sa.build_archive_entry("ghost", [], min_roots=1)
        assert entry["normal_evaluations"] == {}
        assert entry["overall"] is None


# ---------------------------------------------------------------------------
# R4 返工（REVIEW-V4 Q2/Q4/Q6/Q7/Q9）：每项独立拒绝反例
# ---------------------------------------------------------------------------


def seat_sample(root, mix, cid, seat, *, baseline_ok=True, cand_u=1.0, base_u=0.0):
    """带冻结期望清单的座位样本（Q4 形状；baseline_ok=False 注入基线臂失败）。"""
    sample = mk_sample(root, "normal", mix, cid, cand_u, base_u)
    sample["focal_anchor_seat"] = seat
    sample["root_expected"] = {"seats": 4, "arms": ["baseline", "candidate"],
                               "tables_per_arm": 2}
    if not baseline_ok:
        sample["arms"]["baseline"]["usable"] = False
        sample["arms"]["baseline"]["error"] = "注入基线臂失败（Q4 夹具）"
    return sample


class TestR4ReviewHardening:
    # ---- Q4：任一臂失败/漏行 → 整根失效，不得用剩余座位算选择值 ----

    def test_q4_single_baseline_failure_gates_whole_root(self):
        # 评审复现形状：1 个基线座位失败 + 3 个完好座位 → 整根失效（不是 3 窗均值）。
        samples = [seat_sample("r1", "H", "c1", seat,
                               baseline_ok=(seat != 1)) for seat in range(4)]
        samples += [seat_sample("r2", "H", "c1", seat) for seat in range(4)]
        stats = sa.paired_stage_statistics(samples, min_roots=1)
        panel = get_panel(stats, "c1", "normal", "H")
        assert panel["n_invalid_roots"] == 1
        assert panel["invalid_roots"][0]["root_id"] == "r1"
        assert any("invalid样本" in reason
                   for reason in panel["invalid_roots"][0]["reasons"])
        assert panel["manifest_complete"] is False
        # 失效根不计入：n_roots 只剩 r2；mean_delta 只来自 r2（恒 +1）。
        assert panel["n_roots"] == 1
        assert panel["roots"] == ["r2"]
        assert panel["mean_delta"] == 1.0
        # 失败座位原始记录保留（不删失败根，不冒充可用）。
        assert panel["n_invalid_samples"] == 1
        assert stats["invalid_records"][0]["focal_anchor_seat"] == 1

    def test_q4_missing_seat_row_gates_root(self):
        # 期望 4 座位只交 3 行 → 清单不符，整根失效。
        samples = [seat_sample("r1", "H", "c1", seat) for seat in (0, 1, 2)]
        stats = sa.paired_stage_statistics(samples, min_roots=1)
        panel = get_panel(stats, "c1", "normal", "H")
        assert panel["n_roots"] == 0
        assert any("清单不符" in reason for reason in
                   panel["invalid_roots"][0]["reasons"])

    def test_q4_manifest_incomplete_blocks_archive_and_nomination(self):
        # 清单未补齐 → 该候选该面板不得进档案排序/提名（overall=None）。
        samples = [seat_sample("r1", "H", "c1", seat,
                               baseline_ok=(seat != 2)) for seat in range(4)]
        samples += [seat_sample("m1", "M", "c1", seat) for seat in range(4)]
        entry = sa.build_archive_entry("c1", samples, min_roots=1,
                                       behavior_signature=sig("a"))
        # 失效根 r1 不进根级评估记录；完好的 M 根保留（原始事实不删）。
        assert "r1" not in entry["normal_evaluations"]
        assert set(entry["normal_evaluations"]) == {"m1"}
        assert entry["overall"] is None  # Q4 闸门：不进排序/提名/效果结论
        archive = sa.update_archive([entry])
        assert all("c1" not in ids or key == "exploration"
                   for key, ids in archive["slots"].items())

    def test_q4_complete_manifest_panel_stays_eligible(self):
        samples = [seat_sample("r1", "H", "c1", seat) for seat in range(4)]
        samples += [seat_sample("m1", "M", "c1", seat) for seat in range(4)]
        stats = sa.paired_stage_statistics(samples, min_roots=1)
        for mix in ("H", "M"):
            panel = get_panel(stats, "c1", "normal", mix)
            assert panel["manifest_complete"] is True
            assert panel["n_roots"] == 1

    # ---- Q6：只接受绑定当前完整身份的安全 PASS ----

    def _bare_entry(self, safety, cid="q6c", **kwargs):
        return sa.build_archive_entry(
            cid,
            normal_both_mixes(cid, {"h": [1, 1]}, {"m": [1, 1]}),
            safety=safety, behavior_signature=sig("x"), **kwargs)

    def test_q6_unknown_safety_never_seated(self):
        # 评审复现形状：UNKNOWN + 行为签名 → 不得占探索席（也不得任何席）。
        archive = sa.update_archive([self._bare_entry({"status": "UNKNOWN"})])
        assert all("q6c" not in ids for ids in archive["slots"].values())
        assert "UNKNOWN" in archive["ineligible"]["q6c"]

    def test_q6_missing_and_none_safety_rejected(self):
        for safety in (None, {}, {"status": None}, "PASS_EXPIRED"):
            entry = self._bare_entry(safety, cid="q6b" + str(len(str(safety))))
            archive = sa.update_archive([entry])
            assert all(entry["candidate_id"] not in ids
                       for ids in archive["slots"].values()), safety

    def test_q6_stale_or_mismatched_bound_pass_rejected(self):
        stale = self._bare_entry({"status": "PASS", "stale": True}, cid="q6s")
        mismatch = self._bare_entry({"status": "PASS", "bound_candidate_id": "other"},
                                    cid="q6m")
        archive = sa.update_archive([stale, mismatch])
        assert "过期" in archive["ineligible"]["q6s"]
        assert "不符" in archive["ineligible"]["q6m"]

    def test_q6_bound_pass_matching_identity_seated(self):
        ok_entry = self._bare_entry({"status": "PASS", "bound_candidate_id": "q6ok"},
                                    cid="q6ok")
        archive = sa.update_archive([ok_entry])
        assert "q6ok" in archive["slots"]["overall"]

    # ---- Q7：统计器拒绝同 ID 不同内容的根 ----

    def test_q7_same_root_id_different_digest_rejected(self):
        good = seat_sample("r1", "H", "c1", 0)
        good["root_content_digest"] = "d1"
        clash = seat_sample("r1", "H", "c1", 1)
        clash["root_content_digest"] = "d2"
        with pytest.raises(ValueError, match="根身份碰撞"):
            sa.paired_stage_statistics([good, clash], min_roots=1)

    def test_q7_same_digest_passes_and_recorded(self):
        samples = [seat_sample("r1", "H", "c1", seat) for seat in range(4)]
        for sample in samples:
            sample["root_content_digest"] = "d1"
        stats = sa.paired_stage_statistics(samples, min_roots=1)
        panel = get_panel(stats, "c1", "normal", "H")
        assert panel["root_rows"][0]["root_content_digest"] == "d1"
        assert panel["n_roots"] == 1

    # ---- Q2：根用途三分区（独立冻结清单；确认根文件级分离） ----

    def test_q2_manifest_partitions_exclusive(self):
        with pytest.raises(ValueError, match="互斥"):
            sa.build_root_usage_manifest(development_core=["a"], confirmation=["a"])
        manifest = sa.build_root_usage_manifest(
            development_core=["d1", "d2"], development_refresh=["f1"],
            confirmation=["c1"])
        assert manifest["usage"]["confirmation"] == ["c1"]

    def test_q2_confirmation_root_only_via_manifest(self):
        usage = {"n1": "development_core", "n2": "confirmation",
                 "n3": "development_core", "n4": "development_core"}
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE,
                                       usage_manifest=usage)
        assert sa.confirmation_eligible_roots(epoch) == ["n2"]
        by_id = {row["root_id"]: row for row in epoch["roots"]}
        assert by_id["n2"]["confirmation_eligible"] is True
        assert by_id["n1"]["confirmation_eligible"] is False

    def test_q2_unlisted_root_fails_closed(self):
        usage = {"n1": "development_core"}  # n2..n4 未列入
        with pytest.raises(ValueError, match="不在用途清单中"):
            sa.build_channel_epoch("normal", NORMAL_CORE, usage_manifest=usage)

    def test_q2_file_level_separation_from_manifest_file(self, tmp_path):
        manifest = sa.build_root_usage_manifest(
            development_core=["n1", "n3", "n4"], development_refresh=[],
            confirmation=["n2"])
        path = tmp_path / "root-usage.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        # 生成侧读取：确认根名不得进入其内存。
        dev_view = sa.load_root_usage_manifest(path, include_confirmation=False)
        assert "n2" not in dev_view and set(dev_view) == {"n1", "n3", "n4"}
        # 确认侧读取：完整三分区。
        full_view = sa.load_root_usage_manifest(path)
        assert full_view["n2"] == "confirmation"
        # epoch 走清单文件路径：只有 n2 确认可用。
        epoch = sa.build_channel_epoch(
            "normal", NORMAL_CORE, usage_manifest_path=path,
            include_confirmation_roots=True)
        assert sa.confirmation_eligible_roots(epoch) == ["n2"]

    # ---- Q9：提交即持久化；重启重载后提名不再缺根 ----

    def test_q9_multi_refresh_persist_reload_nominate_no_missing(self, tmp_path):
        import pathlib

        archive = challenge_archive()
        epoch = sa.build_channel_epoch("normal", NORMAL_CORE)

        def commit(challenger, refresh_roots, out_dir):
            # 全部参与重排身份（原席者+挑战者）都补齐刷新根（§9.2/Q9）。
            seated = list(archive.get("slots", {}).get("overall") or [])
            evals = {}
            for cid in sorted(set(seated) | {challenger["candidate_id"]}):
                merged = dict(archive["entries"][cid]["normal_evaluations"])
                for root in refresh_roots:
                    merged[root["root_id"]] = rec(
                        1.0 if cid == challenger["candidate_id"] else 0.0,
                        root["opponent_mix"])
                evals[cid] = merged
            return sa.apply_challenge(
                archive, epoch, challenger["candidate_id"], evals,
                refresh_roots=refresh_roots, persist_dir=pathlib.Path(out_dir))

        result1 = commit(challenger_entry("ch"), NORMAL_REFRESH, tmp_path / "c1")
        assert result1["status"] == "committed"
        assert result1["persisted"]["commit_summary"].endswith("commit-summary.json")

        # 进程重启模拟：从盘上重载档案与 epoch，再由第二名挑战者二次刷新。
        archive = json.loads((tmp_path / "c1" / "archive.json").read_text(encoding="utf-8"))
        epoch = json.loads((tmp_path / "c1" / "epoch.json").read_text(encoding="utf-8"))
        assert epoch["epoch"] == 2 and len(epoch["roots"]) == 8
        challenger2 = challenger_entry("ch2", (0.9, 0.9, 0.9, 0.9))
        # 新挑战者必须补齐 epoch 2 的全部当前根（n1..n4 + 首批刷新 f1..f4）。
        for root in NORMAL_REFRESH:
            challenger2["normal_evaluations"][root["root_id"]] = rec(
                0.8, root["opponent_mix"])
        archive["entries"]["ch2"] = challenger2
        refresh2 = [{"root_id": "g{0}".format(i),
                     "opponent_mix": "H" if i < 2 else "M"} for i in range(4)]
        result2 = commit(challenger2, refresh2, tmp_path / "c2")
        assert result2["status"] == "committed"
        assert result2["epoch_after"] == 3

        # 重启重载后提名：所有参与者根覆盖完整——不再缺根误报。
        archive = json.loads((tmp_path / "c2" / "archive.json").read_text(encoding="utf-8"))
        epoch = json.loads((tmp_path / "c2" / "epoch.json").read_text(encoding="utf-8"))
        nomination = sa.nominate_candidate(archive, epoch, budget=0)
        assert nomination.get("status") != "nomination_pending_budget"
        assert nomination["nominated"] is True
        # ch2 全根集（n=0.9/f=0.8/g=1.0）高于 ch（g 批为 0）与 inc——重排后冠军。
        assert nomination["candidate_id"] == "ch2"
        assert nomination["sort_value"] == pytest.approx(0.9)
        summary = json.loads((tmp_path / "c2" / "commit-summary.json")
                             .read_text(encoding="utf-8"))
        assert all(not rows["roots_missing"]
                   for rows in summary["participants"].values())


# ---------------------------------------------------------------------------
# P18 NEXTACTION：提案历史完整性（§9.3 计数口径；run7「重算 = 自报 = 实际」）
# ---------------------------------------------------------------------------


def proposal_history_row(no, operator, *, run_id="run7", iteration_no=None,
                        iter_dir=None, source="event", channel=None, family=None,
                        parent=None, failed=False, duplicate=False,
                        status="ITERATION_COMPLETE"):
    """一条**生产同形**提案历史行（_av_plan_history 的输出形状）。"""

    return {
        "proposal_no": no,
        "recorded_proposal_no": no,
        "operator": operator,
        "planned_operator": operator,
        "applied_operator": operator.lower(),
        "parent_candidate_id": parent,
        "channel": channel,
        "family": family,
        "candidate_id": "cand-{0}".format(no),
        "status": status,
        "terminal_status": status,
        "failed": failed,
        "duplicate": duplicate,
        "iter_dir": iter_dir or "/run7/iterations/iter-{0:02d}".format(no),
        "run_id": run_id,
        "iteration_no": no if iteration_no is None else iteration_no,
        "created_at_utc": "2026-09-18T17:{0:02d}:00Z".format(no),
        "source": source,
    }


RUN7_HISTORY = [proposal_history_row(1, "I1"),
                proposal_history_row(2, "M1", channel="overall", parent="o1",
                                     duplicate=True)]


class TestProposalHistoryIntegrity:
    """P18：`proposal_no = 已消费提案数 + 1` 的合同必须**可判**，坏历史不得给貌似合理的答案。

    ​④ 条覆盖：① 正常序列（重算 = 实际）② 失败迭代（照样占额度）③ 重复项（同提案重复登记）
    ④ 缺项/断层（具名报错，不用位置号硬凑）。
    """

    def test_normal_sequence_recompute_matches_run7_reading(self):
        """① 正常序列：2 条已消费提案 → 下一步 proposal 3 / M1 / 专长 branch。

        该形状即 run7 冻结根的读数（iter-02 自报 == iter-03 实际 state.plan == 程序重算；
        只读复算见 evidence/v4-impl/r9-fixes/P18-nextaction/probes/probe_run7_recompute.py）。
        """

        archive = scheduling_archive()
        plan = sa.next_generation_plan(archive, RUN7_HISTORY)
        assert plan["proposal_no"] == 3
        assert plan["operator"] == "M1"
        assert plan["channel"] == "specialty" and plan["family"] == "branch"
        assert plan["parent_candidate_id"] == "b1"
        check = plan["history_check"]
        assert (check["records_in"], check["proposals"]) == (2, 2), check
        assert check["integrity"] == "verified", check
        assert check["duplicate_proposals"] == 1, check   # 行为重复的提案照样占额度

    def test_block_structure_and_failed_proposals_consume_quota(self):
        """①b 块结构 3×M1+1×I1；② 失败迭代照样消耗提案额度（§9.3）。"""

        archive = scheduling_archive()
        history = []
        operators = []
        for index in range(9):
            plan = sa.next_generation_plan(archive, history)
            operators.append(plan["operator"])
            history.append(proposal_history_row(index + 1, plan["operator"],
                                                channel=plan["channel"],
                                                family=plan["family"],
                                                parent=plan["parent_candidate_id"]))
        assert operators == ["I1"] + ["M1", "M1", "M1", "I1"] * 2
        # 失败/重复不改变位次：把第 2、3 条标成失败重放，序列完全不变。
        failed_history = [dict(row, failed=(row["proposal_no"] in (2, 3)))
                          for row in history]
        failed_plan = sa.next_generation_plan(archive, failed_history)
        assert failed_plan["proposal_no"] == 10
        assert failed_plan["operator"] == "M1"      # 位次照旧：(10−2)%4=0 → 块内 M1
        assert failed_plan["history_check"]["failed_proposals"] == 2
        assert failed_plan["history_check"]["proposals"] == 9

    def test_duplicate_registration_of_one_proposal_is_counted_once(self):
        """③ 重复项：同一提案登记两次（事件账本 + 状态投影）→ 只计一次。

        跨目录搬运后事件账本里的 iter_dir 仍指原路径、状态投影用当前路径，两条记录都在；
        按位置计数会每轮多算一步（run7 的 5/I1 重算读数即此形态），故折叠为一条并留档。
        """

        archive = scheduling_archive()
        doubled = []
        for row in RUN7_HISTORY:
            doubled.append(row)
            doubled.append(dict(row, iter_dir="/copied" + row["iter_dir"],
                                source="state_projection",
                                created_at_utc="2026-09-19T00:00:00Z"))
        plan = sa.next_generation_plan(archive, doubled)
        check = plan["history_check"]
        assert (check["records_in"], check["proposals"]) == (4, 2), check
        assert len(check["collapsed_same_proposal"]) == 2, check
        assert plan["proposal_no"] == 3 and plan["operator"] == "M1"
        # 与「只有 2 条」的历史给出同一计划（history_check 之外逐字节一致）。
        plain = sa.next_generation_plan(archive, RUN7_HISTORY)
        assert ({key: value for key, value in plan.items() if key != "history_check"}
                == {key: value for key, value in plain.items()
                    if key != "history_check"})

    def test_conflicting_duplicate_identity_is_a_named_error(self):
        """③b 同一身份但内容互相矛盾 → 具名报错（不猜哪条为准）。"""

        row = proposal_history_row(2, "M1", channel="overall", parent="o1")
        conflict = dict(row, operator="I1", channel=None, parent_candidate_id=None,
                        iter_dir="/copied" + row["iter_dir"],
                        source="state_projection")
        with pytest.raises(ValueError) as error:
            sa.next_generation_plan(scheduling_archive(),
                                    [proposal_history_row(1, "I1"), row, conflict])
        assert "互相矛盾" in str(error.value), str(error.value)

    def test_gapped_proposal_numbers_are_a_named_error(self):
        """④ 缺项：记录号断层 → 具名报错；跨链后半段（从 >1 起仍连续）不误报。

        「缺项」在本合同里是**不可判**的：缺了哪次提案无法从产物还原，位置号硬凑会把
        算子位次算错。因此可判的断层必须报错，不可判的（无记录号的旧历史）标 unverified。
        """

        archive = scheduling_archive()
        with pytest.raises(ValueError) as error:
            sa.next_generation_plan(archive, [proposal_history_row(1, "I1"),
                                              proposal_history_row(3, "M1",
                                                                   channel="overall",
                                                                   parent="o1")])
        assert "缺项或编号断层" in str(error.value), str(error.value)
        # 跨运行链只持有后半段：[2, 3] 连续 → 不误报，按位置号推进。
        tail = [proposal_history_row(2, "I1"),
                proposal_history_row(3, "M1", channel="overall", parent="o1")]
        plan = sa.next_generation_plan(archive, tail)
        assert plan["proposal_no"] == 3
        assert plan["history_check"]["integrity"] == "verified"
        # 无记录号/无身份的旧历史：不猜，标 unverified（可判的部分已判）。
        legacy = [{"operator": "I1"},
                  {"operator": "M1", "channel": "overall",
                   "parent_candidate_id": "o1", "family": None}]
        legacy_plan = sa.next_generation_plan(archive, legacy)
        assert legacy_plan["proposal_no"] == 3
        assert legacy_plan["history_check"]["integrity"] == "unverified"