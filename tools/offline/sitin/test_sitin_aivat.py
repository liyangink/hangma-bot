# -*- coding: utf-8 -*-
"""sitin_aivat 单测：零期望玩具验证、确定性校正恒 0、信息分区、R 公式与
fit/测量根分离（v4 §12 步骤 2/3 的机器可核部分）。

真实引擎用例只跑**单局**（rounds_per_game=1）小场次（与 tests/offline 既有
做法一致，不构成桌赛实例、不进台账）；零期望的精确性证据来自玩具全置换
枚举，不靠样本均值。
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

import hashlib
import json
import math
from pathlib import Path

import pytest

import sitin_aivat as av
import sitin_natural_panel as natp
import sitin_stage as stage

REPO = av.REPO


# ---------------------------------------------------------------------------
# 步骤 2：零期望与确定性（可穷举）
# ---------------------------------------------------------------------------


def test_toy_verify_all_passes_default_wall():
    report = av.toy_verify_all()
    assert report["all_pass"], json.dumps(report["checks"], ensure_ascii=False)


def test_toy_zero_mean_exact_each_policy_small_wall():
    wall = ("A", "A", "B", "B", "C", "E", "F")
    for policy in ("pair_seeker", "hoarder", "discarder", "late_seeker"):
        stats = av.toy_enumerate(wall, 5, policy)
        assert stats["abs_mean_m"] < 1e-9, (policy, stats)
        assert stats["n_permutations"] > 1


def test_toy_deterministic_chance_correction_identically_zero():
    for policy in ("pair_seeker", "hoarder", "discarder", "late_seeker"):
        for perm in av.toy_distinct_permutations(("A",) * 10):
            run = av.toy_play(perm, 8, policy)
            assert abs(run["m"]) < 1e-12


def test_toy_identical_arms_correction_difference_zero():
    wall = ("A", "A", "B", "B", "C", "C", "E", "F")
    for perm in av.toy_distinct_permutations(wall)[:200]:
        left = av.toy_play(perm, 6, "pair_seeker")
        right = av.toy_play(perm, 6, "pair_seeker")
        assert abs((left["m"] - right["m"])) < 1e-12


def test_toy_paired_difference_zero_mean_exact():
    wall = ("A", "A", "B", "B", "C", "E", "F")
    perms = av.toy_distinct_permutations(wall)
    c = 0.3
    d_raw_sum = 0.0
    d_adj_sum = 0.0
    for perm in perms:
        cand = av.toy_play(perm, 5, "pair_seeker")
        base = av.toy_play(perm, 5, "hoarder")
        d_raw = cand["u"] - base["u"]
        d_raw_sum += d_raw
        d_adj_sum += d_raw - c * (cand["m"] - base["m"])
    assert abs(d_adj_sum - d_raw_sum) / len(perms) < 1e-9


def test_toy_z_is_policy_sensitive_on_same_root():
    wall = ("A", "A", "B", "B", "C", "C", "E", "F")
    sensitive = any(
        av.toy_play(perm, 6, "pair_seeker")["z"]
        != av.toy_play(perm, 6, "hoarder")["z"]
        for perm in av.toy_distinct_permutations(wall))
    assert sensitive  # Z 定义在实际摸牌序列上：同根不同策略可分叉


def test_draw_moment_arithmetic():
    moment = av.draw_moment(("A", "B"), {"A": 1, "B": 1, "C": 2}, "C")
    # W = {A:1, B:1, C:3}，|S∩W| = 1+1 = 2，|W| = 5 → p = 0.4；C ∉ S。
    assert moment.hit is False
    assert math.isclose(moment.p, 0.4)
    assert moment.wall_remaining == 5
    assert moment.effective_in_wall == 2
    hit = av.draw_moment(("A",), {"A": 0, "B": 2}, "A")
    assert hit.hit is True and math.isclose(hit.p, 1.0 / 3.0)


# ---------------------------------------------------------------------------
# 信息分区：侦察不改变任何决策（真实引擎单局 A/B 对拍）
# ---------------------------------------------------------------------------


def _single_round_versions_block() -> dict:
    contract = json.loads((_project_file(_PROJECT_ROOT, REPO / natp.DEFAULT_CONTRACT)).read_text(encoding="utf-8"))
    block = dict(stage.contract_versions_block(contract))
    block["rounds_per_game"] = 1  # 单局小场次：测试提速，不构成完整桌赛实例
    return block


def _baseline_policies(plan):
    from hangma_bot.application.deadline import ManualClock

    clock = ManualClock(start_monotonic=800.0, wait_scale=1.0)
    logical = natp.arm_logical_policies(
        arm="baseline", candidate_scorer=None,
        logical_participants=plan.logical_participants,
        opponent_policies=["weighted_heuristic_v2"] * 3, monotonic=clock.now)
    from hangma_bot.offline.evaluate import seat_policies_from
    return seat_policies_from(logical, plan.permutation, plan.logical_participants)


def test_engine_spy_does_not_change_any_decision():
    contract = json.loads((_project_file(_PROJECT_ROOT, REPO / natp.DEFAULT_CONTRACT)).read_text(encoding="utf-8"))
    plans = natp.build_seat_stage_plans(contract=contract, opponent="H",
                                        root_index=1, focal_seat=0,
                                        panel_seed=av.MEASURE_PANEL_SEED)
    versions = _single_round_versions_block()
    limits = natp.ValueAnalysisLimits()
    step_limit = int(contract["stop"]["step_limit"])
    for plan in plans[:1]:
        policies = _baseline_policies(plan)
        focal_seat = list(plan.seats()).index(natp.FOCAL_PARTICIPANT)
        plain = av.execute_table_with_spy(plan=plan, policies_by_seat=policies,
                                          versions_block=versions,
                                          step_limit=step_limit,
                                          value_limits=limits, focal_seat=None)
        spied = av.execute_table_with_spy(plan=plan, policies_by_seat=policies,
                                          versions_block=versions,
                                          step_limit=step_limit,
                                          value_limits=limits,
                                          focal_seat=focal_seat)
        # 同种子同策略：侦察必须零副作用（逐决策一致，信息分区无泄漏的
        # 行为级证据；策略输入不含 Z/牌墙真值由架构白名单保证）。
        assert plain["row"]["match_status"] == "complete"
        assert spied["row"]["match_status"] == plain["row"]["match_status"]
        assert spied["row"]["scores_by_seat"] == plain["row"]["scores_by_seat"]
        plain_keys = [d.action_key for d in plain["outcome"].decisions]
        spied_keys = [d.action_key for d in spied["outcome"].decisions]
        assert spied_keys == plain_keys
        assert spied["outcome"].steps == plain["outcome"].steps
        # 侦察统计不变量。
        aivat = spied["aivat"]
        assert aivat is not None and aivat["draws"] > 0
        assert aivat["focal_seat"] == focal_seat
        for data in aivat["rounds"].values():
            assert data["z"] <= data["draws"]
            assert all(0.0 <= p <= 1.0 for p in data["p_values"])
            assert all(h in (0, 1) for h in data["hits"])
            assert len(data["p_values"]) == data["draws"]
        assert math.isclose(aivat["m"], aivat["z"] - aivat["a"], abs_tol=1e-6)
        assert aivat["stats_ms"] >= 0.0


def test_policy_package_has_no_aivat_references():
    # 分区静态面：policy 模块不得引用 AIVAT/侦察（无泄漏通道）。
    for path in (_project_file(_PROJECT_ROOT, REPO / "src" / "hangma_bot" / "policy")).rglob("*.py"):
        assert "aivat" not in path.read_text(encoding="utf-8").lower(), path


# ---------------------------------------------------------------------------
# 步骤 3/5：c 冻结、fit/测量根分离、R 公式
# ---------------------------------------------------------------------------


def _sample(pair, root_id, d_raw, m_diff, cost_raw=2.0, cost_adj=4.0):
    return {"pair": pair, "root_id": root_id, "completeness": "complete",
            "resolved": True, "d_raw": d_raw, "m_diff": m_diff,
            "cost": {"cost_raw_sec": cost_raw, "cost_adjusted_sec": cost_adj,
                     "stats_ms": 10.0}}


def test_fit_c_pooled_ols_and_clip():
    samples = [_sample("p", "H-root01", 0.0, 0.0), _sample("p", "H-root01", 0.5, 1.0),
               _sample("p", "H-root02", 1.0, 2.0), _sample("p", "H-root02", 1.5, 3.0)]
    frozen = av.fit_c(samples)
    assert math.isclose(frozen["c"], 0.5, abs_tol=1e-6)
    negative = [_sample("p", "r1", 3.0, 0.0), _sample("p", "r2", 1.0, 1.0),
                _sample("p", "r3", 0.0, 2.0)]
    assert av.fit_c(negative)["c"] == 0.0


def test_fit_c_requires_enough_usable_samples():
    with pytest.raises(SystemExit):
        av.fit_c([_sample("p", "r1", 1.0, 1.0)])


def test_r_formula_numeric_case():
    # Δraw=[2,−2,2,−2]（Var=16/3），c=1 时 Δadj=[1,−1,1,−1]（Var=4/3），
    # cost_raw=2、cost_adj=4 → R = (16/3×2)/((4/3)×4) = 2。
    # 夹具按**来源根**单位（r1—r4 = 4 个独立根观测）：_r_core 会先做根聚合，
    # 同一 root_id 的多行不再是独立观测（口径修正见 test_root_* 用例）。
    samples = [_sample("p", "r1", 2.0, 1.0), _sample("p", "r2", -2.0, -1.0),
               _sample("p", "r3", 2.0, 1.0), _sample("p", "r4", -2.0, -1.0)]
    core = av._r_core(samples, c=1.0)
    assert math.isclose(core["var_delta_raw"], 16.0 / 3.0)
    assert math.isclose(core["var_delta_adjusted"], 4.0 / 3.0)
    assert math.isclose(core["r"], 2.0)
    assert core["target_estimate_diff"] == 0.0
    assert math.isclose(core["ci_width_ratio_adj_over_raw"], 0.5)


def test_cluster_bootstrap_r_reproducible_and_bounded():
    samples = ([_sample("p", "r1", 1.0, 0.2), _sample("p", "r1", -1.0, -0.2),
                _sample("p", "r2", 1.0, 0.8), _sample("p", "r2", -1.0, -0.8),
                _sample("p", "r3", 0.0, 0.0), _sample("p", "r3", 2.0, 0.5)])
    first = av._cluster_bootstrap_r(samples, c=1.0, n_boot=400, seed=7)
    second = av._cluster_bootstrap_r(samples, c=1.0, n_boot=400, seed=7)
    assert first == second
    assert first["lower95"] <= first["median"] <= first["upper95"]


def test_frozen_c_ok_separation_guard():
    fit_roots = av.measurement_root_ids(av.FIT_PANEL_SEED, av.FIT_MIX_ROOTS)
    measure_roots = av.measurement_root_ids(av.MEASURE_PANEL_SEED, av.MEASURE_MIX_ROOTS)
    assert set(fit_roots).isdisjoint(measure_roots)
    ok, _ = av.frozen_c_ok({"c": 0.25, "fit_root_seeds": fit_roots}, measure_roots)
    assert ok
    bad, _ = av.frozen_c_ok({"c": 0.25, "fit_root_seeds": measure_roots[:1]},
                            measure_roots)
    assert not bad
    missing, _ = av.frozen_c_ok({"c": 0.25}, measure_roots)
    assert not missing
    negative, _ = av.frozen_c_ok({"c": -1.0, "fit_root_seeds": fit_roots},
                                 measure_roots)
    assert not negative


def test_measure_refuses_without_frozen_c(tmp_path, monkeypatch):
    def fake_evidence_path(*parts):
        return tmp_path.joinpath(*parts)
    monkeypatch.setattr(av, "evidence_path", fake_evidence_path)
    authorization = _project_file(_PROJECT_ROOT, REPO / ".team-work/tasks/sitin-phase3-v4/llm-authorization.json")
    if not authorization.is_file():  # 授权文件不在时不做端到端拒绝测试
        pytest.skip("authorization file missing")
    with pytest.raises(SystemExit):
        av.cmd_measure(argparse_ns(authorization=str(authorization),
                                   contract_file=None))


def argparse_ns(**kwargs):
    import argparse
    return argparse.Namespace(**kwargs)


# ---------------------------------------------------------------------------
# 识别区间红线：未分辨样本不计点值、不平均、不删根
# ---------------------------------------------------------------------------


def test_unresolved_sample_excluded_not_averaged():
    def arm(u, u_low, u_high, unresolved, usable=True):
        return {"status": "complete" if usable else "error", "usable": usable,
                "error": None, "u": u, "u_low": u_low, "u_high": u_high,
                "unresolved": unresolved, "focal_stage_score": 0,
                "z": 3, "a": 2.9, "m": 0.1, "elapsed_ms": 1000.0,
                "stats_ms": 20.0, "overhead_ms": 1.0}

    resolved_arms = {"baseline": arm(0.0, 0.0, 0.0, False),
                     "candidate": arm(1.0, 1.0, 1.0, False)}
    sample = av.assemble_sample(pair_name="p", opponent="H", root_index=1,
                                root_seed=42, panel_seed=1, focal_seat=0,
                                arms=resolved_arms, table_ids=["t1", "t2"])
    assert sample["resolved"] and sample["d_raw"] == 1.0
    unresolved_arms = {"baseline": arm(None, 0.0, 1.0, True),
                       "candidate": arm(1.0, 1.0, 1.0, False)}
    sample2 = av.assemble_sample(pair_name="p", opponent="H", root_index=2,
                                 root_seed=43, panel_seed=1, focal_seat=1,
                                 arms=unresolved_arms, table_ids=["t3", "t4"])
    assert not sample2["resolved"] and sample2["d_raw"] is None
    assert sample2["arms"]["baseline"]["u_low"] == 0.0  # 区间原样保留
    assert sample2["arms"]["baseline"]["u_high"] == 1.0
    usable = av.usable_samples([sample, sample2])
    assert usable == [sample]  # 未分辨样本不计点值，但样本本身保留可数
    # 成本口径：cost_raw ≤ cost_adjusted（校正状态求值开销非负）。
    assert sample["cost"]["cost_raw_sec"] <= sample["cost"]["cost_adjusted_sec"]


def test_t16_invalid_root_marking(monkeypatch):
    # 候选臂失败 ⇒ 样本 invalid、数值保留（T16）；不进入统计。
    def arm(usable):
        return {"status": "complete" if usable else "error", "usable": usable,
                "error": None if usable else "RuntimeError: x", "u": None,
                "u_low": 0.0, "u_high": 1.0, "unresolved": True,
                "focal_stage_score": None, "z": 0, "a": 0.0, "m": 0.0,
                "elapsed_ms": 10.0, "stats_ms": 0.0, "overhead_ms": 0.0}
    arms = {"baseline": arm(True), "candidate": arm(False)}
    sample = av.assemble_sample(pair_name="p", opponent="H", root_index=1,
                                root_seed=1, panel_seed=1, focal_seat=0,
                                arms=arms, table_ids=["t"])
    assert sample["completeness"] == "invalid"
    assert av.usable_samples([sample]) == []


# ---------------------------------------------------------------------------
# 统计口径修正（评审 v4 §5）：统计单位 = 来源根，不是座位行
# ---------------------------------------------------------------------------


def _seat_row(pair="p", root_id="H-root01", seat=0, d_raw=0.0, m_diff=0.0,
              root_seed=7, opponent_mix="H", cost_raw=2.0, cost_adj=4.0,
              resolved=True, completeness="complete"):
    """一个座位行样本（字段对齐 assemble_sample 的最小可用子集）。"""

    return {"pair": pair, "root_id": root_id, "root_seed": root_seed,
            "opponent_mix": opponent_mix, "focal_seat": seat,
            "completeness": completeness, "resolved": resolved,
            "d_raw": d_raw, "m_diff": m_diff,
            "cost": {"cost_raw_sec": cost_raw, "cost_adjusted_sec": cost_adj,
                     "stats_ms": 10.0}}


def test_root_observations_aggregate_four_seats_into_one_root():
    rows = [_seat_row(seat=seat, d_raw=float(seat), m_diff=0.5 * seat,
                      cost_raw=1.0, cost_adj=2.0) for seat in range(4)]
    rows.append(_seat_row(root_id="M-root01", root_seed=9, opponent_mix="M",
                          seat=0, d_raw=-2.0, m_diff=-0.25,
                          cost_raw=3.0, cost_adj=3.5))
    observations = av.root_observations(rows)
    assert len(observations) == 2  # 4 座位 → 1 根观测；另一根 1 座位 → 1 根观测
    first = observations[0]
    assert first["n_seats"] == 4
    assert first["sample_kind"] == av.ROOT_OBSERVATION_KIND
    assert math.isclose(first["d_raw"], 1.5)  # 座位均值（不放大独立样本数）
    assert math.isclose(first["m_diff"], 0.75)
    assert math.isclose(first["cost"]["cost_raw_sec"], 4.0)  # 根成本 = 座位和
    assert math.isclose(first["cost"]["cost_adjusted_sec"], 8.0)
    # 幂等：根观测再聚合不变（一元素分组：均值=自身、和=自身）。
    assert av.root_observations(observations) == observations
    # 重复元素的方差计多次（_r_stat 不折叠重复；只有 _r_core 才聚合）——
    # bootstrap"同一根被抽中 k 次计 k 次"依赖这一契约。
    duplicated = av._r_stat([observations[0], observations[0], observations[1]],
                            c=0.0)
    unique = av._r_stat(observations, c=0.0)
    assert duplicated["n"] == 3 and unique["n"] == 2
    assert duplicated["var_delta_raw"] != unique["var_delta_raw"]
    # _r_core 固定走 root_observations → _r_stat（口径不可绕过）。
    assert av._r_core(rows, c=0.0) == av._r_stat(observations, c=0.0)


def test_root_observations_reject_unresolved_and_conflicting_seed():
    with pytest.raises(ValueError):
        av.root_observations([_seat_row(d_raw=None, m_diff=None, resolved=False)])
    with pytest.raises(ValueError):  # 同 root_id 不同 root_seed（评审 v4 Q7）
        av.root_observations([_seat_row(seat=0, root_seed=1),
                              _seat_row(seat=1, root_seed=2)])


def test_seat_row_unit_fixture_collapses_to_root_observation():
    # 口径回归：同一 root_id 的两行在旧实现里被当成两个独立观测（旧夹具
    # Var=16/3、R=2 正是这个错误单位的产物）。按来源根聚合后每根均值 0，
    # 根间方差为 0 ⇒ R 不可定义，不得再报出座位行口径的点值。
    samples = [_sample("p", "r1", 2.0, 1.0), _sample("p", "r1", -2.0, -1.0),
               _sample("p", "r2", 2.0, 1.0), _sample("p", "r2", -2.0, -1.0)]
    core = av._r_core(samples, c=1.0)
    assert core["n"] == 2 and core["n_seat_rows"] == 4
    assert core["var_delta_raw"] == 0.0
    assert core["r"] is None


def test_r_root_units_match_review_recalc():
    """与评审重算对拍：根聚合数值逐项等于 aivat-recalc.json（只读已有证据）。

    输入 SHA256 与重算脚本记录一致才比较——证据变化时本用例失败，不静默放过。
    """
    import hashlib

    measure_path = av.evidence_path("measure", "MEASUREMENT.json")
    recalc_path = av.ROUTE_DIR / "evidence/review-v4-2026-09-17/aivat-recalc.json"
    if not (measure_path.is_file() and recalc_path.is_file()):
        pytest.skip("AIVAT 测量证据或评审重算结果缺失")
    raw = measure_path.read_bytes()
    measurement = json.loads(raw.decode("utf-8"))
    recalc = json.loads(recalc_path.read_text(encoding="utf-8"))
    assert hashlib.sha256(raw).hexdigest() == recalc["input_sha256"]
    c = float(measurement["identity"]["c"])
    assert c == recalc["frozen_c_unchanged"]
    stats = av.r_measurement_report(measurement["samples"], c)
    assert stats["blocked"] is False and stats["n_excluded"] == 0
    assert stats["n_samples_total"] == recalc["n_rows"] == 48
    assert stats["statistics_unit"]["unit"] == "来源根"
    for pair, block in stats["per_pair"].items():
        ref = recalc["per_pair"][pair]["unstratified_root_diagnostic"]
        core, boot = block["core"], block["bootstrap"]
        assert core["n"] == ref["core"]["n_independent_roots"] == 6
        assert core["n_seat_rows"] == 24
        assert core["variance_unit"].startswith("来源根")
        assert math.isclose(core["var_delta_raw"], ref["core"]["var_raw"],
                            abs_tol=1e-6)
        assert math.isclose(core["var_delta_adjusted"], ref["core"]["var_adjusted"],
                            abs_tol=1e-6)
        assert math.isclose(core["r"], ref["core"]["r"], abs_tol=1e-6)
        assert math.isclose(core["cost_raw_sec"], ref["core"]["cost_raw"],
                            abs_tol=1e-6)
        assert math.isclose(core["cost_adjusted_sec"], ref["core"]["cost_adjusted"],
                            abs_tol=1e-6)
        assert math.isclose(boot["lower95"], ref["bootstrap"]["lower95"],
                            abs_tol=1e-6)
        assert math.isclose(boot["median"], ref["bootstrap"]["median"], abs_tol=1e-6)
        assert math.isclose(boot["upper95"], ref["bootstrap"]["upper95"],
                            abs_tol=1e-6)
        assert boot["degenerate"] == ref["bootstrap"]["degenerate_undefined_ratio"]
        assert boot["n_boot"] == ref["bootstrap"]["draws_with_defined_ratio"]
    # 评审 §5 的显式数字：0.216667 / 0.102628 / ≈2.10（方向与原报告相反，
    # 但 bootstrap 下界 < 1，不足以启用 ⇒ 维持停用）。
    i1 = stats["per_pair"]["i1-vs-v2"]
    assert math.isclose(i1["core"]["var_delta_raw"], 0.216667, abs_tol=1e-6)
    assert math.isclose(i1["core"]["var_delta_adjusted"], 0.102628, abs_tol=1e-6)
    assert math.isclose(i1["core"]["r"], 2.10, abs_tol=5e-3)
    assert i1["bootstrap"]["lower95"] < 1.0
    # 两对逐行相同 ⇒ 合并只是重复同一份数据，不增加独立信息。
    assert recalc["pairs_identical_on_delta_raw_and_m_diff"] is True
    # 合并口径修正（复审 R6 §5 M3）：12 个 (pair, root) 单元只含 6 个独立来源根，
    # 合并观测数必须是 6，不是 12（旧实现按 12 除 √n，区间被压窄 32.6%）。
    pooled = stats["pooled"]["core"]
    assert pooled["n"] == 6
    assert pooled["n_pair_root_cells"] == 12  # 单元数仍如实记录（只是不当作独立观测）
    assert math.isclose(pooled["ci95_halfwidth_raw"], 0.372450, abs_tol=1e-6)
    assert not math.isclose(pooled["ci95_halfwidth_raw"], 0.251106, abs_tol=1e-6)


def test_no_exclusion_keeps_point_estimates():
    """未排除时行为不变：仍然输出点值 R，并标注统计单位。"""

    rows = [_seat_row(root_id="H-root01", seat=seat, d_raw=float(seat % 2),
                      m_diff=0.25 * seat) for seat in range(4)]
    rows.append(_seat_row(root_id="H-root02", root_seed=8, seat=0,
                          d_raw=1.0, m_diff=0.5))
    rows.append(_seat_row(root_id="H-root02", root_seed=8, seat=1,
                          d_raw=-1.0, m_diff=-0.5))
    stats = av.r_measurement_report(rows, c=0.1)
    assert stats["blocked"] is False and stats["n_excluded"] == 0
    assert stats["n_usable"] == 6
    assert stats["per_pair"]["p"]["core"]["r"] is not None
    assert stats["pooled"]["core"]["n"] == 2  # 两个来源根观测
    assert stats["statistics_unit"]["n_root_observations"] == 2
    assert stats["per_root_costs"][0]["n_samples"] == 4


def test_excluded_rows_block_point_r():
    """存在被排除行时不再输出点值 R（评审 v4 §5 P2：保留原始行≠没有删根）。"""

    rows = [_seat_row(root_id="H-root01", seat=seat, d_raw=float(seat % 2),
                      m_diff=0.25 * seat) for seat in range(4)]
    rows.append(_seat_row(root_id="H-root02", root_seed=8, seat=0,
                          d_raw=1.0, m_diff=0.5))
    rows.append(_seat_row(root_id="H-root02", root_seed=8, seat=1,
                          d_raw=-1.0, m_diff=-0.5))
    unresolved = _seat_row(root_id="H-root03", root_seed=11, d_raw=None,
                           m_diff=None, resolved=False)
    blocked = av.r_measurement_report(rows + [unresolved], c=0.1)
    assert blocked["blocked"] is True and blocked["n_excluded"] == 1
    assert blocked["n_usable"] == 6 and blocked["n_samples_total"] == 7
    assert blocked["per_pair"] == {}
    assert blocked["pooled"]["core"] is None
    assert blocked["pooled"]["bootstrap"] is None
    assert "n_excluded=1" in blocked["block_reason"]
    assert "点值 R" in blocked["block_reason"]
    assert '"r":' not in json.dumps(blocked, ensure_ascii=False)  # 无点值泄漏


def test_report_command_blocks_point_value_and_honours_out(tmp_path, monkeypatch):
    """cmd_report：阻断时不写点值、verdict 不启用；--out 可另落修正版报告。"""

    monkeypatch.setattr(av, "evidence_path",
                        lambda *parts: tmp_path.joinpath(*parts))
    rows = [_seat_row(root_id="H-root01", seat=seat, d_raw=float(seat % 2),
                      m_diff=0.25 * seat) for seat in range(4)]
    rows.append(_seat_row(root_id="H-root02", root_seed=8, seat=0,
                          d_raw=1.0, m_diff=0.5))
    rows.append(_seat_row(root_id="H-root02", root_seed=8, seat=1,
                          d_raw=-1.0, m_diff=-0.5))
    rows.append(_seat_row(root_id="H-root03", root_seed=11, d_raw=None,
                          m_diff=None, resolved=False))
    (tmp_path / "measure").mkdir()
    (tmp_path / "fit").mkdir()
    (tmp_path / "measure" / "MEASUREMENT.json").write_text(json.dumps(
        {"schema": av.AIVAT_SCHEMA, "phase": "measure",
         "identity": {"c": 0.1, "panel_seed": 1, "mixes_roots": {"H": [1]}},
         "samples": rows}), encoding="utf-8")
    (tmp_path / "fit" / "C-FROZEN.json").write_text(json.dumps(
        {"schema": av.AIVAT_SCHEMA, "c": 0.1, "method": "test",
         "fit_root_seeds": [1, 2]}), encoding="utf-8")
    assert av.cmd_report(argparse_ns(out="R-REPORT-v2.json")) == 0
    assert not (tmp_path / "R-REPORT.json").exists()  # 原文件不被覆盖
    report = json.loads((tmp_path / "R-REPORT-v2.json").read_text(encoding="utf-8"))
    assert report["verdict"]["blocked"] is True
    assert report["verdict"]["pooled_r"] is None
    assert report["verdict"]["pooled_r_bootstrap_lower95"] is None
    assert report["verdict"]["n_excluded"] == 1
    assert report["verdict"]["recommendation"] == "disengage"
    assert report["statistics"]["per_pair"] == {}


# ---------------------------------------------------------------------------
# 合并区间口径修正（R6 复审 §5 M3）：合并统计单位是来源根，一根一票
# ---------------------------------------------------------------------------


def _pair_root_rows(pair, root_index, deltas, *, root_seed=None, cost_step=1.0):
    """一个策略对在一个来源根上的 4 个座位行（deltas 为逐座位 d_raw）。"""

    root_id = "H-root{0:02d}".format(root_index)
    seed = (100 + root_index) if root_seed is None else root_seed
    return [_seat_row(pair=pair, root_id=root_id, root_seed=seed, seat=seat,
                      d_raw=float(value), m_diff=0.5 * float(value),
                      cost_raw=cost_step, cost_adj=2.0 * cost_step)
            for seat, value in enumerate(deltas)]


def _merged_fixture(pair_names, roots=4):
    """多策略对 × 多来源根的座位行夹具（逐座位 d_raw 只由根号决定，对间相同）。"""

    rows = []
    for pair in pair_names:
        for index in range(1, roots + 1):
            rows.extend(_pair_root_rows(
                pair, index, (0.25 * index, -0.25 * index, 0.0, 0.5 * index)))
    return rows


def _load_frozen_measurement():
    """只读加载 batch7b 已冻结测量与评审重算（SHA256 对不上即失败，不静默放过）。"""

    measure_path = av.evidence_path("measure", "MEASUREMENT.json")
    recalc_path = av.ROUTE_DIR / "evidence/review-v4-2026-09-17/aivat-recalc.json"
    if not (measure_path.is_file() and recalc_path.is_file()):
        pytest.skip("AIVAT 测量证据或评审重算结果缺失")
    raw = measure_path.read_bytes()
    recalc = json.loads(recalc_path.read_text(encoding="utf-8"))
    assert hashlib.sha256(raw).hexdigest() == recalc["input_sha256"]
    return json.loads(raw.decode("utf-8")), recalc


def test_pooled_root_observations_aggregate_pairs_within_one_root():
    """根内各对先聚合：一根只留一个观测，成本按整根上全部策略对计。"""

    rows = _merged_fixture(("i1-vs-v2", "m1-vs-v2"), roots=2)
    pooled = av.pooled_root_observations(rows)
    assert len(pooled) == 2  # 2 根，不是 2 对 × 2 根 = 4
    first = pooled[0]
    assert first["pair"] == av.POOLED_PAIR_LABEL
    assert first["n_pairs"] == 2 and first["n_seats"] == 8
    assert math.isclose(first["d_raw"], 0.125)  # 根内各对等权：两对逐行相同 ⇒ 等于单对
    assert math.isclose(first["m_diff"], 0.0625)
    assert math.isclose(first["cost"]["cost_raw_sec"], 8.0)  # 整根上两对成本之和
    assert sorted(first["pair_d_raw"]) == ["i1-vs-v2", "m1-vs-v2"]
    # 再聚合只改诊断字段，不改变统计量（一根仍是一个观测）。
    assert av._r_stat(av.pooled_root_observations(pooled), c=0.1) == \
        av._r_stat(pooled, c=0.1)


def test_pooled_root_observations_reject_cross_pair_seed_conflict():
    """同一 root_id 跨策略对种子冲突 = 不是同一个随机世界，拒绝合并。"""

    rows = _pair_root_rows("i1-vs-v2", 1, (1.0, 2.0, 3.0, 4.0), root_seed=7)
    rows += _pair_root_rows("m1-vs-v2", 1, (1.0, 2.0, 3.0, 4.0), root_seed=8)
    with pytest.raises(ValueError):
        av.pooled_root_observations(rows)


def test_duplicate_pair_does_not_shrink_merged_interval():
    """验收：复制完全相同的策略对不得提高有效样本量或缩窄区间（复审 §5 M3）。"""

    fixture = _merged_fixture(("i1-vs-v2", "m1-vs-v2"), roots=4)
    single = av.r_measurement_report(
        [row for row in fixture if row["pair"] == "i1-vs-v2"], c=0.2)
    merged = av.r_measurement_report(fixture, c=0.2)
    one, two = single["pooled"]["core"], merged["pooled"]["core"]
    assert one["n"] == two["n"] == 4  # 独立来源根数不因复制策略对增加
    assert one["n_pair_root_cells"] == 4 and two["n_pair_root_cells"] == 8
    for key in ("var_delta_raw", "var_delta_adjusted", "ci95_halfwidth_raw",
                "ci95_halfwidth_adjusted", "r"):
        assert math.isclose(two[key], one[key], rel_tol=1e-12), key
    # 簇 bootstrap 同样不因复制策略对变窄（同一根的两对联动进出抽样）。
    one_boot, two_boot = single["pooled"]["bootstrap"], merged["pooled"]["bootstrap"]
    assert (two_boot["n_boot"], two_boot["degenerate"]) == \
        (one_boot["n_boot"], one_boot["degenerate"])
    for key in ("lower95", "median", "upper95"):
        assert math.isclose(two_boot[key], one_boot[key], rel_tol=1e-9), key


def test_merged_report_declares_estimand_and_unit_counts():
    """先定义估计目标再算区间：报告必须显式给出合并口径与有效根数。"""

    stats = av.r_measurement_report(_merged_fixture(("a", "b", "c"), roots=3), c=0.1)
    unit = stats["statistics_unit"]
    assert unit["n_root_observations"] == 3  # 独立来源根
    assert unit["n_pair_root_cells"] == 9
    assert unit["n_pairs"] == 3
    estimand = stats["pooled"]["estimand"]
    assert estimand["unit"] == "来源根"
    assert estimand["independent_unit_count"] == 3
    assert estimand["pair_root_cells"] == 9
    assert "复制完全相同" in estimand["duplicate_pair_invariance"]
    # 合并点估计 = 各根观测量均值（一根一票，与根内对数的权重无关）。
    observe = av.pooled_root_observations(_merged_fixture(("a", "b", "c"), roots=3))
    assert math.isclose(stats["pooled"]["core"]["mean_d_raw"],
                        sum(item["d_raw"] for item in observe) / len(observe),
                        abs_tol=1e-12)


def test_pooled_unit_matches_review_golden_numbers():
    """复审 §5 M3 金例：合并半宽 0.372450（旧口径 0.251106）、R = 2.1048。"""

    measurement, recalc = _load_frozen_measurement()
    assert recalc["pairs_identical_on_delta_raw_and_m_diff"] is True
    c = float(measurement["identity"]["c"])
    stats = av.r_measurement_report(measurement["samples"], c)
    pooled = stats["pooled"]["core"]
    assert pooled["n"] == 6 and pooled["n_pair_root_cells"] == 12
    assert stats["statistics_unit"]["n_root_observations"] == 6
    assert math.isclose(pooled["var_delta_raw"], 0.216666667, abs_tol=1e-6)
    assert math.isclose(pooled["ci95_halfwidth_raw"], 0.372450, abs_tol=1e-6)
    assert not math.isclose(pooled["ci95_halfwidth_raw"], 0.251106, abs_tol=1e-6)
    assert math.isclose(pooled["r"], 2.1048, abs_tol=1e-4)
    # 合并口径与单对口径在此数据上（两对逐行相同）必须一致。
    for block in stats["per_pair"].values():
        assert math.isclose(block["core"]["ci95_halfwidth_raw"],
                            pooled["ci95_halfwidth_raw"], abs_tol=1e-6)
        assert math.isclose(block["core"]["var_delta_raw"], pooled["var_delta_raw"],
                            abs_tol=1e-6)
    # 合并簇 bootstrap 与评审单对根簇诊断一致（评审重算独立复现同一数量）。
    boot = stats["pooled"]["bootstrap"]
    for pair in stats["per_pair"]:
        ref = recalc["per_pair"][pair]["unstratified_root_diagnostic"]["bootstrap"]
        assert math.isclose(boot["lower95"], ref["lower95"], abs_tol=1e-4)
        assert math.isclose(boot["upper95"], ref["upper95"], abs_tol=1e-4)


def test_single_pair_merged_equals_per_pair():
    """只有一对时合并口径退化为该对本身（口径一致性，不引入额外权重）。"""

    stats = av.r_measurement_report(_merged_fixture(("only-pair",), roots=5), c=0.3)
    pooled = stats["pooled"]["core"]
    per_pair = stats["per_pair"]["only-pair"]["core"]
    assert pooled["n"] == per_pair["n"] == 5
    for key in ("var_delta_raw", "var_delta_adjusted", "r", "cost_raw_sec",
                "cost_adjusted_sec", "ci95_halfwidth_raw",
                "ci95_halfwidth_adjusted", "mean_d_raw", "mean_d_adjusted"):
        assert pooled[key] == per_pair[key], key
    assert stats["pooled"]["bootstrap"] == stats["per_pair"]["only-pair"]["bootstrap"]
    assert stats["statistics_unit"]["n_pairs"] == 1



def test_report_command_emits_corrected_merged_halfwidth(tmp_path, monkeypatch):
    """端到端（夹具验证）：cmd_report 的 verdict 带修正后的合并半宽与根数。

    只读复制冻结测量到临时目录；不写任何既有证据，AIVAT 默认停用结论不变。
    """

    measurement, _ = _load_frozen_measurement()
    monkeypatch.setattr(av, "evidence_path",
                        lambda *parts: tmp_path.joinpath(*parts))
    step2_src = av.evidence_path("step2-toy-verification.json")
    (tmp_path / "measure").mkdir()
    (tmp_path / "fit").mkdir()
    (tmp_path / "measure" / "MEASUREMENT.json").write_text(
        json.dumps(measurement, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "fit" / "C-FROZEN.json").write_text(json.dumps(
        {"schema": av.AIVAT_SCHEMA, "c": measurement["identity"]["c"],
         "method": "fit-batch7（测试夹具）", "fit_root_seeds": [1, 2]}),
        encoding="utf-8")
    if step2_src.is_file():  # 步骤 2 全过也要走同一判据分支
        (tmp_path / "step2-toy-verification.json").write_text(
            step2_src.read_text(encoding="utf-8"), encoding="utf-8")
    assert av.cmd_report(argparse_ns(out="R-REPORT-merged-fix.json")) == 0
    assert not (tmp_path / "R-REPORT.json").exists()  # 冻结报告名不被占用
    report = json.loads((tmp_path / "R-REPORT-merged-fix.json").read_text(
        encoding="utf-8"))
    verdict = report["verdict"]
    assert math.isclose(verdict["pooled_ci95_halfwidth_raw"], 0.372450,
                        abs_tol=1e-6)
    assert verdict["n_independent_roots"] == 6
    assert math.isclose(verdict["pooled_r"], 2.1048, abs_tol=1e-4)
    # 判据与门槛不变：点估计达标但簇 bootstrap 下界 0.4034 < 1 ⇒ 维持停用。
    assert math.isclose(verdict["pooled_r_bootstrap_lower95"], 0.403385,
                        abs_tol=1e-4)
    assert verdict["blocked"] is False
    assert verdict["recommendation"] == "disengage"
    # 合并区间不得再出现缺陷值 0.251106（旧 (pair, root) 单元口径）。
    assert not math.isclose(verdict["pooled_ci95_halfwidth_raw"], 0.251106,
                            abs_tol=1e-6)


def test_pooled_estimand_is_one_root_one_vote_with_unequal_pairs():
    """根内各对等权：一根跑了 2 对、另一根只跑 1 对时按**根**平均（非按单元）。"""

    rows = _merged_fixture(("a", "b"), roots=1)  # H-root01：两对，根均值 0.125
    rows += _pair_root_rows("a", 2, (3.0, 3.0, 3.0, 3.0))  # H-root02：单对，根均值 3
    stats = av.r_measurement_report(rows, c=0.0)
    pooled = stats["pooled"]["core"]
    assert pooled["n"] == 2 and pooled["n_pair_root_cells"] == 3
    assert math.isclose(pooled["mean_d_raw"], (0.125 + 3.0) / 2, abs_tol=1e-12)
    assert not math.isclose(pooled["mean_d_raw"], (0.125 + 0.125 + 3.0) / 3,
                            abs_tol=1e-12)  # 不是按 (pair, root) 单元加权
    assert stats["pooled"]["estimand"]["independent_unit_count"] == 2
    assert stats["pooled"]["estimand"]["pair_root_cells"] == 3


# ---------------------------------------------------------------------------
# 平行桌执行器阶段账注入（P12：复审 §5 M1 的 AIVAT 同类缺口）
#
# 缺陷：execute_table_with_spy 调 drive_match 时未传 stage_situation →
# 平行桌执行器与自然面板修复前同病：第 2 桌起读不到已完成桌的阶段账。
# 契约与自然面板一致（单一实现 natp.build_stage_situation）：第 1 桌注入
# 空账（表头：stage_no=1、已完成 0 桌），第 2 桌起注入**已完成桌累计**，
# 按「参赛者身份 → 物理座位」映射，不含本桌结果。
# ---------------------------------------------------------------------------


def _contract_tables(tables: int) -> dict:
    """临时合同（只改内存副本）：tables_per_group = tables，3 桌可验换座累计。"""

    contract = json.loads((_project_file(_PROJECT_ROOT, REPO / natp.DEFAULT_CONTRACT)).read_text(encoding="utf-8"))
    group = dict(contract["group"])
    group["tables_per_group"] = int(tables)
    contract["group"] = group
    return contract


class _RecordingSpyExecutor:
    """记录型平行桌执行替身：记录每桌收到的 stage_situation，按脚本返回桌赛积分。

    0 真实桌赛（策略与阶段账编排是纯编排语义，不需要引擎参与）。
    """

    def __init__(self, scores_by_table):
        self.scores_by_table = {int(key): tuple(int(value) for value in values)
                                for key, values in scores_by_table.items()}
        self.calls = []

    def __call__(self, *, plan, policies_by_seat, versions_block, step_limit,
                 value_limits, focal_seat=None, stage_situation=None):
        table_no = len(self.calls) + 1
        self.calls.append({"table_no": table_no, "table_id": plan.table_id,
                           "seats": tuple(plan.seats()),
                           "stage_situation": stage_situation})
        scores = self.scores_by_table.get(table_no, (0, 0, 0, 0))
        return {
            "row": {"table_id": plan.table_id, "seed": int(plan.seed),
                    "match_status": "complete", "wall_ms": 1.0,
                    "scores_by_seat": list(scores), "result": {}},
            "aivat": {"focal_seat": (None if focal_seat is None else int(focal_seat)),
                      "draws": 0, "z": 0, "a": 0.0, "m": 0.0, "rounds": {},
                      "stats_ms": 0.0, "wrapper_overhead_ms": 0.0},
            "outcome": None}


def _run_aivat_arm(monkeypatch, executor, *, plans, contract, step_limit=1):
    """跑一臂（基线臂）：桌执行由 executor 承担（step_limit=1 仅够记录型替身）。"""

    monkeypatch.setattr(av, "execute_table_with_spy", executor)
    return av.run_arm_stage_aivat(
        arm="baseline", plans=list(plans), candidate_scorer=None,
        opponent_policies=["weighted_heuristic_v2"] * (stage.SEAT_COUNT - 1),
        versions_block=_single_round_versions_block(), step_limit=int(step_limit),
        value_limits=natp.ValueAnalysisLimits())


def test_aivat_arm_injects_completed_table_stage_account(monkeypatch):
    """红→绿：第 1 桌空账、第 2 桌起 = 已完成桌累计（按身份映射，不含本桌）。"""

    contract = _contract_tables(3)
    plans = natp.build_seat_stage_plans(contract=contract, opponent="H",
                                        root_index=1, focal_seat=0,
                                        panel_seed=av.MEASURE_PANEL_SEED)
    # 脚本积分（物理座位序）：三桌逐桌可判别（第 2、3 桌的账必须来自**前桌**）。
    scripted = {1: (10, -4, 2, 6), 2: (5, 5, 5, 5), 3: (7, -1, 3, -9)}
    executor = _RecordingSpyExecutor(scripted)
    record = _run_aivat_arm(monkeypatch, executor, plans=plans, contract=contract)
    assert record["status"] == "complete", record["error"]
    assert len(executor.calls) == 3
    assert [call["seats"] for call in executor.calls] == [
        ("focal", "opp-1", "opp-2", "opp-3"),
        ("opp-3", "focal", "opp-1", "opp-2"),
        ("opp-2", "opp-3", "focal", "opp-1")]

    totals, place_totals = {}, {}
    for index, plan in enumerate(plans):
        situation = executor.calls[index]["stage_situation"]
        assert situation is not None, "第 {0} 桌策略输入缺少阶段账".format(index + 1)
        assert situation.participant_ids_by_seat == tuple(plan.seats())
        assert situation.stage_table_no == index + 1
        assert situation.tables_completed == index
        assert situation.tables_in_stage == 3
        assert situation.rounds_per_game == 1
        assert situation.stage_scores_by_seat == tuple(
            totals.get(pid, 0) for pid in plan.seats())
        assert situation.place_points_by_seat == tuple(
            place_totals.get(pid, 0) for pid in plan.seats())
        scores = scripted[index + 1]
        points = stage.place_points_for_table(list(scores))
        for seat, participant in enumerate(plan.seats()):
            totals[participant] = totals.get(participant, 0) + int(scores[seat])
            place_totals[participant] = place_totals.get(participant, 0) + int(points[seat])

    # 第 1 桌：空阶段账（非 None 的表头：stage_no=1、已完成 0 桌、阶段 3 桌）。
    first = executor.calls[0]["stage_situation"]
    assert first.stage_scores_by_seat == (0, 0, 0, 0)
    assert first.place_points_by_seat == (0, 0, 0, 0)

    # 第 2 桌（换座后）：非空，且等于首桌账按身份映射到本桌物理座位。
    second = executor.calls[1]["stage_situation"]
    assert any(value != 0 for value in second.stage_scores_by_seat),         "第 2 桌阶段账仍为空（M1 同类缺陷复现）"
    assert second.stage_scores_by_seat == (6, 10, -4, 2)   # opp-3/focal/opp-1/opp-2
    assert second.place_points_by_seat == (1, 3, -3, -1)
    assert second.stage_scores_by_seat != tuple(scripted[2])  # 不含本桌结果

    # 第 3 桌：等于前两桌累计（三桌累计 ≠ 首桌账 ≠ 本桌结果）。
    third = executor.calls[2]["stage_situation"]
    assert third.stage_scores_by_seat == (7, 11, 15, 1)    # opp-2/opp-3/focal/opp-1
    assert third.place_points_by_seat == (-1, 1, 3, -3)
    assert third.stage_scores_by_seat != tuple(scripted[3])
    assert third.stage_scores_by_seat != second.stage_scores_by_seat


def test_aivat_arm_records_injected_projection_per_table(monkeypatch):
    """证据留存：每桌记录实际注入的投影 JSON（与自然面板同口径，可核）。"""

    contract = _contract_tables(2)
    plans = natp.build_seat_stage_plans(contract=contract, opponent="H",
                                        root_index=1, focal_seat=1,
                                        panel_seed=av.MEASURE_PANEL_SEED)
    executor = _RecordingSpyExecutor({1: (3, -6, 8, -5)})
    record = _run_aivat_arm(monkeypatch, executor, plans=plans, contract=contract)
    assert record["status"] == "complete", record["error"]
    tables = record["tables"]
    assert [table["table_id"] for table in tables] == [plan.table_id for plan in plans]
    # 既有字段逐项保留（R 口径读的就是这些字段）。
    for table, call in zip(tables, executor.calls):
        payload = table["stage_situation"]
        assert payload["stage_table_no"] == call["stage_situation"].stage_table_no
        assert payload["tables_completed"] == call["stage_situation"].tables_completed
        assert payload["stage_scores_by_seat"] == list(
            call["stage_situation"].stage_scores_by_seat)
        assert payload["place_points_by_seat"] == list(
            call["stage_situation"].place_points_by_seat)
    assert tables[0]["stage_situation"]["tables_completed"] == 0
    assert tables[1]["stage_situation"]["tables_completed"] == 1
    assert tables[1]["stage_situation"]["stage_scores_by_seat"] != list((3, -6, 8, -5))


def test_execute_table_with_spy_forwards_stage_situation_to_drive_match(monkeypatch):
    """真实执行路径：stage_situation 逐字转交 drive_match（默认 None 保持零变化）。"""

    contract = json.loads((_project_file(_PROJECT_ROOT, REPO / natp.DEFAULT_CONTRACT)).read_text(encoding="utf-8"))
    plan = natp.build_seat_stage_plans(contract=contract, opponent="H", root_index=1,
                                       focal_seat=0,
                                       panel_seed=av.MEASURE_PANEL_SEED)[0]
    situation = natp.build_stage_situation(
        plan=plan, table_no=2, tables_completed=1,
        totals={"focal": 15, "opp-1": 1, "opp-2": 7, "opp-3": 11},
        place_totals={"focal": 3, "opp-1": -3, "opp-2": -1, "opp-3": 1},
        rounds_per_game=1)
    seen = []

    class _Stop(Exception):
        pass

    async def fake_drive_match(**kwargs):
        seen.append(kwargs)
        raise _Stop()

    monkeypatch.setattr(av, "drive_match", fake_drive_match)
    policies = _baseline_policies(plan)

    def call(**extra):
        with pytest.raises(_Stop):
            av.execute_table_with_spy(
                plan=plan, policies_by_seat=policies,
                versions_block=_single_round_versions_block(), step_limit=1,
                value_limits=natp.ValueAnalysisLimits(),
                focal_seat=list(plan.seats()).index(natp.FOCAL_PARTICIPANT), **extra)

    call(stage_situation=situation)
    call()
    assert seen[0]["stage_situation"] is situation
    assert seen[1]["stage_situation"] is None  # 缺省 None：既有调用零变化
    assert seen[0]["engine"] is not seen[1]["engine"]  # 侦察包装仍按 focal_seat 生效


class _CompetitionProbe:
    """记录型策略包装：原样转发内层计划，只记录策略公开输入里的阶段账投影。"""

    def __init__(self, inner, *, policy_id="stage-account-probe"):
        self.policy_id = policy_id
        self._inner = inner
        self.windows = []

    async def choose(self, request, budget):
        plan = await self._inner.choose(request, budget)
        competition = request.competition
        self.windows.append({
            "game_id": str(request.window_key.game_id),
            "seat": int(request.observation.seat),
            "stage_no": competition.stage_no,
            "stage_total": competition.stage_total,
            "ranking_ids": tuple(str(entry.participant_id) for entry in competition.ranking),
            "ranking_scores": tuple(int(entry.total_score) for entry in competition.ranking),
            "ranking_games": tuple(int(entry.games_played) for entry in competition.ranking),
            "n_candidates": len(plan.candidates),
            "chosen": (plan.candidates[0].action_key if plan.candidates else None)})
        return plan


def test_real_drive_chain_delivers_stage_account_to_second_table_policy(monkeypatch):
    """端到端（真实引擎、单局缩小赛程）：第 2 桌策略请求里确有首桌阶段账。

    0 授权桌赛：本地模拟器单局小场次，不构成完整桌赛实例。
    """

    contract = json.loads((_project_file(_PROJECT_ROOT, REPO / natp.DEFAULT_CONTRACT)).read_text(encoding="utf-8"))
    plans = natp.build_seat_stage_plans(contract=contract, opponent="H",
                                        root_index=1, focal_seat=0,
                                        panel_seed=av.MEASURE_PANEL_SEED)
    plans = plans[:2]
    probe = _CompetitionProbe(stage.build_panel_policy("weighted_heuristic_v2",
                                                       lambda: 800.0))
    original = natp.arm_logical_policies

    def probe_arm(*, arm, candidate_scorer, logical_participants,
                  opponent_policies, monotonic):
        logical = original(arm=arm, candidate_scorer=candidate_scorer,
                           logical_participants=logical_participants,
                           opponent_policies=opponent_policies,
                           monotonic=monotonic)
        logical[natp.FOCAL_PARTICIPANT] = probe
        return logical

    monkeypatch.setattr(natp, "arm_logical_policies", probe_arm)
    record = _run_aivat_arm(monkeypatch, av.execute_table_with_spy, plans=plans,
                            contract=contract,
                            step_limit=int(contract["stop"]["step_limit"]))
    assert record["status"] == "complete", record["error"]
    first_id, second_id = plans[0].match_id, plans[1].match_id
    first_windows = [w for w in probe.windows if w["game_id"] == first_id]
    second_windows = [w for w in probe.windows if w["game_id"] == second_id]
    assert first_windows and second_windows, probe.windows[:3]
    # 第 1 桌：阶段账空（表头），桌内积分另行可见。
    assert all(w["stage_no"] == 1 and w["stage_total"] == 2 for w in first_windows)
    assert all(w["ranking_scores"] == (0, 0, 0, 0) for w in first_windows)
    assert all(w["ranking_games"] == (0, 0, 0, 0) for w in first_windows)
    # 第 2 桌：非空，且逐座位等于首桌结果按身份映射（换座后座位序不同）。
    first_scores = record["tables"][0]["scores_by_seat"]
    expected = {participant: int(first_scores[seat])
                for seat, participant in enumerate(plans[0].seats())}
    for window in second_windows:
        assert window["stage_no"] == 2
        assert window["ranking_ids"] == tuple(plans[1].seats())
        assert window["ranking_scores"] == tuple(
            expected[pid] for pid in plans[1].seats())
        # 非退化：已完成桌数 = 1 桌 × 每桌 1 局（首桌账即使积分全零也可判别）。
        assert window["ranking_games"] == (1, 1, 1, 1)


def test_stage_account_injection_is_inert_for_frozen_arm_policies(monkeypatch):
    """既有测量不受影响的行为级依据：注入对冻结臂策略集**不改变任何决策**。

    冻结臂（焦点=weighted_heuristic_v2、对手=合同 V2 族）不读
    DecisionRequest.competition；Z/A 也只经只读侦察包装统计。同种子同策略下
    注入与不注入逐决策、逐积分、逐 Z/A 一致 ⇒ 既有 batch7b 测量数值不需重算。
    """

    contract = json.loads((_project_file(_PROJECT_ROOT, REPO / natp.DEFAULT_CONTRACT)).read_text(encoding="utf-8"))
    plan = natp.build_seat_stage_plans(contract=contract, opponent="H", root_index=1,
                                       focal_seat=0,
                                       panel_seed=av.MEASURE_PANEL_SEED)[0]
    situation = natp.build_stage_situation(
        plan=plan, table_no=2, tables_completed=1,
        totals={"focal": 15, "opp-1": 1, "opp-2": 7, "opp-3": 11},
        place_totals={"focal": 3, "opp-1": -3, "opp-2": -1, "opp-3": 1},
        rounds_per_game=1)
    policies = _baseline_policies(plan)
    versions = _single_round_versions_block()
    limits = natp.ValueAnalysisLimits()
    step_limit = int(contract["stop"]["step_limit"])
    focal_seat = list(plan.seats()).index(natp.FOCAL_PARTICIPANT)

    def run(**extra):
        return av.execute_table_with_spy(
            plan=plan, policies_by_seat=policies, versions_block=versions,
            step_limit=step_limit, value_limits=limits, focal_seat=focal_seat, **extra)

    without = run()
    with_account = run(stage_situation=situation)
    assert without["row"]["match_status"] == "complete"
    assert with_account["row"]["scores_by_seat"] == without["row"]["scores_by_seat"]
    assert [d.action_key for d in with_account["outcome"].decisions] ==         [d.action_key for d in without["outcome"].decisions]
    assert with_account["outcome"].steps == without["outcome"].steps
    # 侦察统计（Z/A 口径）逐项不变；只排除挂钟耗时字段（stats_ms/包装开销
    # 天然逐次波动，不属于口径）。
    for key in ("focal_seat", "draws", "z", "a", "m", "rounds"):
        assert with_account["aivat"][key] == without["aivat"][key], key
    assert without["aivat"]["draws"] > 0


def _candidate_policies(plan, source_path):
    """候选臂装配（与 natp.run_arm_stage 同构）：焦点=ActionValuePolicy(候选评分器)。"""

    from hangma_bot.application.deadline import ManualClock
    from hangma_bot.offline.evaluate import seat_policies_from
    from hangma_bot.policy.action_value_seeds import ActionValueScorer

    scorer = ActionValueScorer("av-candidate",
                               Path(source_path).read_text(encoding="utf-8"))
    clock = ManualClock(start_monotonic=800.0, wait_scale=1.0)
    logical = natp.arm_logical_policies(
        arm="candidate", candidate_scorer=scorer,
        logical_participants=plan.logical_participants,
        opponent_policies=["weighted_heuristic_v2"] * (stage.SEAT_COUNT - 1),
        monotonic=clock.now)
    return seat_policies_from(logical, plan.permutation, plan.logical_participants)


def test_candidate_arm_real_policies_are_inert_to_injected_stage_account():
    """候选臂（batch7 i1 真实生成物）同样不因注入改变任何决策（只读既有证据）。

    依据：ActionValuePolicy 的竞争投影不消费 CompetitionContext（恒为空视图），
    候选评分器看不到阶段账；同种子下注入与不注入逐决策、逐积分、逐 Z/A 一致。
    """

    source = av.ROUTE_DIR / av.PAIR_SOURCES["i1-vs-v2"]
    if not source.is_file():
        pytest.skip("batch7 i1 候选源缺失（只读证据不在本机）")
    contract = json.loads((_project_file(_PROJECT_ROOT, REPO / natp.DEFAULT_CONTRACT)).read_text(encoding="utf-8"))
    plan = natp.build_seat_stage_plans(contract=contract, opponent="H", root_index=1,
                                       focal_seat=0,
                                       panel_seed=av.MEASURE_PANEL_SEED)[0]
    situation = natp.build_stage_situation(
        plan=plan, table_no=2, tables_completed=1,
        totals={"focal": 15, "opp-1": 1, "opp-2": 7, "opp-3": 11},
        place_totals={"focal": 3, "opp-1": -3, "opp-2": -1, "opp-3": 1},
        rounds_per_game=1)
    policies = _candidate_policies(plan, source)
    versions = _single_round_versions_block()
    limits = natp.ValueAnalysisLimits()
    step_limit = int(contract["stop"]["step_limit"])
    focal_seat = list(plan.seats()).index(natp.FOCAL_PARTICIPANT)

    def run(**extra):
        return av.execute_table_with_spy(
            plan=plan, policies_by_seat=policies, versions_block=versions,
            step_limit=step_limit, value_limits=limits, focal_seat=focal_seat, **extra)

    without = run()
    with_account = run(stage_situation=situation)
    assert without["row"]["match_status"] == "complete"
    assert with_account["row"]["scores_by_seat"] == without["row"]["scores_by_seat"]
    assert [d.action_key for d in with_account["outcome"].decisions] == \
        [d.action_key for d in without["outcome"].decisions]
    assert with_account["outcome"].steps == without["outcome"].steps
    for key in ("focal_seat", "draws", "z", "a", "m", "rounds"):
        assert with_account["aivat"][key] == without["aivat"][key], key


def test_competition_channel_is_unread_by_frozen_arm_policy_family():
    """静态面：冻结臂策略族（V2/V1/白防守）源码不引用 competition。

    M 情景的对手含 v1 与 v2_white_guard；策源不读竞争上下文 ⇒ 注入阶段账
    对冻结臂的行为无通道（与两条行为级一致性用例互为印证）。
    """

    policy_dir = _project_file(_PROJECT_ROOT, REPO / "src" / "hangma_bot" / "policy")
    for name in ("weighted_heuristic.py", "heuristic_v2.py", "heuristic_v1.py",
                 "white_discard_guard.py"):
        path = policy_dir / name
        if not path.is_file():
            continue
        assert "competition" not in path.read_text(encoding="utf-8").lower(), path


def test_panel_identity_declares_stage_projection_without_epoch_bump(tmp_path, monkeypatch):
    """产物身份留痕：panel.json 增列 stage_projection（只增不改、epoch 不 bump）。

    0 桌赛：根集为空（本用例只核对身份块与产物落盘，不启动任何桌赛）。
    """

    source = av.ROUTE_DIR / av.PAIR_SOURCES["i1-vs-v2"]
    if not source.is_file():
        pytest.skip("batch7 i1 候选源缺失（只读证据不在本机）")
    contract = json.loads((_project_file(_PROJECT_ROOT, REPO / natp.DEFAULT_CONTRACT)).read_text(encoding="utf-8"))
    monkeypatch.setattr(av, "evidence_path",
                        lambda *parts: tmp_path.joinpath(*parts))
    # P14：自然面板授权门已统一到 Q6 受信校验入口（sitin_search
    # .av_authorization_allows，operation=natural_panel，required={"tables_full": 1.0}）：
    # legacy 形态（authorized=true 且 batch==7）照样接受，但需声明本次操作所需账户额度。
    # 本用例 0 桌赛（根集为空），故按 gate 的最小需求给 1.0，不给夸张大值。
    product = av.run_pair_panel(
        pair_name="identity-probe", candidate_source=str(source), contract=contract,
        authorization={"authorized": True, "batch": 7,
                       "budgets": {"tables_full": 1.0}},
        panel_seed=av.MEASURE_PANEL_SEED,
        mixes_roots={"H": []}, phase="measure", ledger_path=None)
    identity = product["identity"]
    assert identity["stage_projection"] == natp.STAGE_ACCOUNT_MODE
    assert identity["panel_epoch"] == "aivat-measure-v1@identity-probe"  # 不 bump
    assert product["cost"]["tables_full_executed"] == 0
    on_disk = json.loads((tmp_path / "measure" / "identity-probe-measure" / "panel.json")
                         .read_text(encoding="utf-8"))
    assert on_disk["identity"] == identity
