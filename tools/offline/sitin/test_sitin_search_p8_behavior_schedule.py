# -*- coding: utf-8 -*-
"""P8 专属测试（R7 修复批次）：A3 行为签名与专长通道 + A4 调度事件与下一步报告。

复审条目：R6-IMPLEMENTATION-REVIEW-2026-09-17 §4 A3 / §4 A4（均 P2 级）。
本文件只覆盖 P8 工作包；A2 见 test_sitin_search_p7_challenge_atomicity.py。

A3 覆盖（v4 §7.3、§9.1—9.4）：
  - 行为步骤从**冻结可见观察集**计算首选动作签名 + 未知掩码签名（不是只查本目录
    候选身份）；源码去重与行为去重**分别记录**；
  - 每候选显式持有**待评价场景矩阵**（八谓词子场景 × H/M），缺格标"输入不足"；
  - 按**完整根身份**增量合并：同候选补 M 情景 / 补代价侧 / 补新根不丢已有证据；
  - 源码不同但动作相同者不重复占探索席；专长必须机会/代价两侧齐备才入席。

A4 覆盖（v4 §9.3）：
  - 提案历史保留不可变完整事件（parent/channel/family/operator/终态/失败标记）；
  - 计划与报告由**同一事件序列**生成；先计入本次终态，再生成 next package；
  - 连续 ≥5 提案的 3×M1+1×I1 节奏、空通道跳转、父代最少使用；
  - "报告计划 == 实际计划"端到端逐提案对照。

预算红线：纯数据夹具 + mock 生成 + 替身桌赛（零真实桌赛、不调真实 LLM、
不消耗授权账目）。
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
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import sitin_search as search  # noqa: E402
import sitin_archive as sa  # noqa: E402

TOKEN = {"authorized": True, "batch": 7,
         "budgets": {"tokens_input": 100000, "tokens_output": 200000,
                     "tables_full": 256, "prefix_generation": 64}}


def _sample(root, mix, cid, d, *, scenario="normal", cost=1.0):
    """一条双臂样本（点值 U）：候选 U=d、基线 U=0。"""

    return {"source_root_id": root, "scenario": scenario, "opponent_mix": mix,
            "candidate_id": cid, "root_role": "core", "invalid": False,
            "cost": cost,
            "arms": {"baseline": {"candidate_id": search.AV_BASELINE_ID, "u": 0.0},
                     "candidate": {"candidate_id": cid, "u": float(d)}}}


def _normal(cid, roots, d=0.5):
    """正常面板样本：roots = [(root_id, mix)]。"""

    return [_sample(root, mix, cid, d) for root, mix in roots]


def _family(cid, family, kind, roots, d=0.5):
    return [_sample(root, mix, cid, d, scenario="{0}_{1}".format(family, kind))
            for root, mix in roots]


H2 = (("h1", "H"), ("h2", "H"))
M2 = (("m1", "M"), ("m2", "M"))


def _sig(*actions, missing=()):
    """行为签名：冻结窗口上的首选动作 + 未知掩码。"""

    return {"windows": [
        {"window_id": "w{0}".format(i),
         "action_key": (None if i in missing else action),
         "missing": i in missing}
        for i, action in enumerate(actions)]}


def _write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + chr(10),
                          encoding="utf-8")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ===========================================================================
# A3 · 行为签名与专长通道
# ===========================================================================


def test_a3_behavior_step_computes_signature_from_frozen_views(tmp_path):
    """行为步骤必须从**冻结可见观察集**算首选动作签名 + 未知掩码签名，
    并把源码去重与行为去重**分别记录**（不是只查本目录候选身份）。"""

    from hangma_bot.policy.action_value_seeds import SEEDS

    run_root = Path(tmp_path) / "run"
    (run_root / "archive").mkdir(parents=True, exist_ok=True)
    _write_json(run_root / "archive" / "av-archive.json",
                {"entries": {}, "slots": {"overall": []}})
    state = {"run_id": "r1", "iteration_no": 1, "iter_dir": str(run_root / "iterations" / "iter-01"),
             "status": "ADMITTED", "step_history": [],
             "identity": {"candidate_id": "candidate-x"},
             "admission": {"coverage": "PASS"},
             "candidate_source": SEEDS["efficiency_seed"].source}
    Path(state["iter_dir"]).mkdir(parents=True, exist_ok=True)

    search._step_behavior(state, run_root)

    behavior = state["behavior"]
    signature = behavior.get("behavior_signature")
    assert signature is not None, behavior
    windows = signature["windows"]
    assert windows, signature
    # 冻结可见观察集：每个窗口都有首选动作（或显式未知掩码），不是空签名。
    assert all("window_id" in row and "action_key" in row and "missing" in row
               for row in windows)
    assert any(row["action_key"] for row in windows)
    assert signature["view_set"] == list(search.AV_BEHAVIOR_VIEWS)
    assert set(signature["unknown_mask"]) == set(search.AV_BEHAVIOR_VIEWS)
    assert isinstance(signature["digest"], str) and len(signature["digest"]) == 64
    # 源码去重与行为去重分别记录。
    assert behavior["source_fingerprint"] == "candidate-x"
    assert behavior["source_duplicate_in_archive"] is False
    assert behavior["behavior_duplicate_in_archive"] is False
    assert behavior["behavior_duplicate_of"] == []


def test_a3_same_behavior_different_source_does_not_take_exploration_seat():
    """源码不同但动作相同者不重复占探索席（§9.2 规则 3/4）。"""

    def entry(cid, signature, d=None):
        samples = _normal(cid, H2 + M2, d) if d is not None else []
        return sa.build_archive_entry(cid, samples, safety="PASS", min_roots=1,
                                      behavior_signature=signature)

    seated = entry("A", _sig("discard:1w", "pass"), 0.5)   # 占整体席（唯一有效果证据）
    dup1 = entry("D1", _sig("discard:1w", "pass"))         # 与 A 行为完全相同
    dup2 = entry("D2", _sig("discard:1w", "pass"))         # 与 A 行为完全相同
    other = entry("C", _sig("pass", "discard:2b"))         # 行为不同
    archive = sa.update_archive([seated, dup1, dup2, other])

    assert archive["slots"]["overall"] == ["A"]
    assert archive["slots"]["exploration"] == ["C"]
    # 重复者被显式记录（不是静默丢弃）：谁与谁同行为可事后核对。
    duplicates = archive["behavior_duplicates"]
    assert duplicates["D1"] == ["A"] and duplicates["D2"] == ["A"]
    pool = archive["selection_report"]["exploration"]["pool"]
    assert "D1" not in pool and "D2" not in pool
    assert archive["selection_report"]["exploration"][
        "excluded_behavior_duplicates"] == {"D1": ["A"], "D2": ["A"]}


def test_a3_family_seat_requires_open_and_cost_sides():
    """专长必须机会/代价两侧齐备才入席（缺一侧不填零争席）。"""

    open_only = sa.merge_archive_entry(None, "spec",
                                       _family("spec", "branch", "open", H2 + M2))
    assert open_only["family"]["branch"]["complete"] is False
    assert sa.update_archive([open_only])["slots"]["branch"] == []

    both = sa.merge_archive_entry(open_only, "spec",
                                  _family("spec", "branch", "cost", H2 + M2))
    assert both["family"]["branch"]["complete"] is True
    assert sa.update_archive([both])["slots"]["branch"] == ["spec"]


def test_a3_incremental_merge_never_loses_existing_evidence():
    """同候选补 M 情景 / 补代价侧 / 补新根都不丢已有证据（前后对比实测）。"""

    h_only = sa.merge_archive_entry(None, "cand", _normal("cand", H2))
    assert sorted(h_only["normal_evaluations"]) == ["h1", "h2"]
    assert h_only["overall"] is None            # 缺 M 层：声明混合不可算，不填零

    both_mixes = sa.merge_archive_entry(h_only, "cand", _normal("cand", M2, 0.25))
    assert sorted(both_mixes["normal_evaluations"]) == ["h1", "h2", "m1", "m2"]
    assert both_mixes["overall"]["sort_value"] is not None
    merge = both_mixes["evidence_merge"]
    assert sorted(merge["added"]) == ["m1", "m2"]
    assert sorted(merge["preserved"]) == ["h1", "h2"]   # 本批未触及的旧根显式保留
    # 对照现状缺陷：把新样本直接喂 build_archive_entry 会丢掉已有根。
    naive = sa.build_archive_entry("cand", _normal("cand", M2, 0.25), safety="PASS",
                                   min_roots=1)
    assert sorted(naive["normal_evaluations"]) == ["m1", "m2"]   # h1/h2 静默丢失

    # 补新根：旧根全部保留。
    more = sa.merge_archive_entry(both_mixes, "cand", _normal("cand", (("h3", "H"),), 0.5))
    assert sorted(more["normal_evaluations"]) == ["h1", "h2", "h3", "m1", "m2"]
    # 同一根的新数据不覆盖已有证据（补齐而不覆盖）。
    rerun = sa.merge_archive_entry(more, "cand", _normal("cand", H2, -0.9))
    assert rerun["normal_evaluations"]["h1"]["d_low"] == more["normal_evaluations"]["h1"]["d_low"]
    assert sorted(rerun["evidence_merge"]["retained"]) == ["h1", "h2"]
    assert sorted(rerun["evidence_merge"]["preserved"]) == ["h3", "m1", "m2"]
    # 补代价侧：机会侧证据仍在，家族值才齐备。
    open_only = sa.merge_archive_entry(both_mixes, "cand",
                                       _family("cand", "baotou", "open", H2 + M2))
    assert open_only["family"]["baotou"]["complete"] is False
    complete = sa.merge_archive_entry(open_only, "cand",
                                      _family("cand", "baotou", "cost", H2 + M2))
    assert complete["family"]["baotou"]["complete"] is True
    assert sorted(complete["family_evaluations"]["baotou_open"]) == ["h1", "h2", "m1", "m2"]
    assert sorted(complete["normal_evaluations"]) == ["h1", "h2", "m1", "m2"]


def test_a3_manifest_incomplete_batch_cannot_rank_until_complete_rerun():
    """Q4 不回退：增量合并后，清单不完整的批次不得让面板进排序；
    后续完整批次覆盖同一格后恢复可排序。"""

    broken = _sample("h2", "H", "cand", 0.5)
    broken["arms"]["candidate"]["usable"] = False          # 整根失效（单臂失败）
    first = sa.merge_archive_entry(None, "cand", _normal("cand", (("h1", "H"),))
                                   + [broken])
    assert first["evidence_manifest"]["normal|H"] is False
    assert first["overall"] is None            # 清单不完整：不得进排序（不填零）
    assert first["evaluation_matrix"]["normal"]["H"]["n_roots"] == 1

    second = sa.merge_archive_entry(first, "cand",
                                    _normal("cand", H2) + _normal("cand", M2, 0.25))
    assert second["evidence_manifest"]["normal|H"] is True
    assert second["overall"]["sort_value"] is not None

def test_a3_scenario_matrix_marks_input_gap_not_known():
    """每候选显式持有待评价场景矩阵；缺格标"输入不足"，不伪装成已知。"""

    entry = sa.merge_archive_entry(None, "cand", _normal("cand", H2 + M2))
    matrix = entry["evaluation_matrix"]
    assert matrix["normal"]["H"]["status"] == "known"
    assert matrix["normal"]["H"]["n_roots"] == 2
    assert matrix["normal"]["M"]["status"] == "known"
    for family in sa.FAMILIES:
        for kind in ("open", "cost"):
            cell = matrix["{0}_{1}".format(family, kind)]["H"]
            assert cell["status"] == "input_gap"
            assert "输入不足" in cell["reason"]
            assert cell["n_roots"] == 0
    summary = entry["matrix_summary"]
    assert summary["known_cells"] == 2
    assert summary["input_gap_cells"] == 16
    # 配额不足（1/2 根）也是输入不足，不当已知。
    thin = sa.merge_archive_entry(None, "cand2", _normal("cand2", (("h1", "H"),)))
    cell = thin["evaluation_matrix"]["normal"]["H"]
    assert cell["status"] == "input_gap" and cell["n_roots"] == 1
    assert "配额" in cell["reason"]


# ===========================================================================
# A4 · 调度事件与下一步报告
# ===========================================================================


ARCHIVE_IDS = {"overall": ["A", "B"], "branch": ["F"], "exploration": ["C", "D"],
               "chain": [], "four_white": [], "baotou": []}


def _sched_archive():
    """调度夹具：整体席 A/B、专长席 F(branch)、探索席 C/D。"""

    entries = {}
    for cid, d in (("A", 0.9), ("B", 0.8), ("F", 0.1)):
        entries[cid] = sa.build_archive_entry(cid, _normal(cid, H2 + M2, d),
                                              safety="PASS", min_roots=1)
    for cid in ("C", "D"):
        entries[cid] = sa.build_archive_entry(cid, _normal(cid, H2 + M2, -0.5),
                                              safety="PASS", min_roots=1)
    archive = sa.update_archive(list(entries.values()))
    archive["slots"] = {channel: list(ids) for channel, ids in ARCHIVE_IDS.items()}
    return archive


def _event(proposal_no, plan, *, status="ITERATION_COMPLETE", failed=False,
           iter_dir=None):
    """按计划构造一条不可变提案事件（A4 事件序列的形状）。"""

    return {"schema": search.AV_PROPOSAL_EVENT_SCHEMA,
            "proposal_no": proposal_no,
            "run_id": "run-{0}".format(proposal_no),
            "iteration_no": proposal_no,
            "iter_dir": str(iter_dir or ("/tmp/iter-{0:02d}".format(proposal_no))),
            "operator": plan["operator"],
            "planned_operator": plan["operator"],
            "parent_candidate_id": plan.get("parent_candidate_id"),
            "channel": plan.get("channel"), "family": plan.get("family"),
            "candidate_id": "cand-{0}".format(proposal_no),
            "status": status, "failed": failed, "duplicate": False,
            "recorded_at_utc": "2026-09-17T00:00:{0:02d}Z".format(proposal_no)}


def test_a4_event_ledger_round_trip_preserves_full_fields(tmp_path):
    """提案事件必须保留 parent/channel/family/operator/终态/失败标记，
    并被 _av_plan_history 原样读出（历史投影不再丢字段）。"""

    run_root = Path(tmp_path) / "run"
    (run_root / "archive").mkdir(parents=True, exist_ok=True)
    event = _event(2, {"operator": "M1", "parent_candidate_id": "A",
                       "channel": "overall", "family": None}, failed=False)
    search.av_proposal_event_append(run_root, event)
    history = search._av_plan_history(run_root)
    assert len(history) == 1
    row = history[0]
    for key, value in (("operator", "M1"), ("parent_candidate_id", "A"),
                       ("channel", "overall"), ("status", "ITERATION_COMPLETE")):
        assert row.get(key) == value, (key, row)
    # 失败/重复的提案同样留在事件序列里（占用提案预算）。
    search.av_proposal_event_append(run_root, _event(
        3, {"operator": "I1", "parent_candidate_id": None, "channel": None,
            "family": None}, status="REJECTED", failed=True))
    history = search._av_plan_history(run_root)
    # 序号按链上位置重编（next_generation_plan 用位置号）；原始记录号留档可核。
    assert [row["proposal_no"] for row in history] == [1, 2]
    assert [row["recorded_proposal_no"] for row in history] == [2, 3]
    assert history[1]["failed"] is True


def test_a4_least_used_parent_and_rhythm_from_event_sequence(tmp_path):
    """连续 ≥5 提案：3×M1+1×I1 节奏、空通道跳转、通道内最少使用父代，
    全部由**同一事件序列**驱动。"""

    run_root = Path(tmp_path) / "run"
    (run_root / "archive").mkdir(parents=True, exist_ok=True)
    archive = _sched_archive()
    plans = []
    for index in range(7):
        history = search._av_plan_history(run_root)
        plan = sa.next_generation_plan(archive, history)
        plans.append(plan)
        search.av_proposal_event_append(run_root, _event(index + 1, plan))

    assert [plan["operator"] for plan in plans] == [
        "I1", "M1", "M1", "M1", "I1", "M1", "M1"]
    # 通道循环：整体→专长（空家族跳到 branch 席）→整体→（I1）→专长→探索。
    assert [plan["channel"] for plan in plans] == [
        None, "overall", "specialty", "overall", None, "specialty", "exploration"]
    assert plans[2]["family"] == "branch"
    # 通道内最少被使用：整体席第一次 A、第二次必须换成未用过的 B。
    assert [plan["parent_candidate_id"] for plan in plans if plan["channel"] == "overall"] \
        == ["A", "B"]


def test_a4_least_used_parent_counterexample_states_backed(tmp_path):
    """纯数据反例：历史用 A 当过一次父代 → 下一次必须选未使用的 B（不再重复 A）。
    历史由**落盘迭代状态 + 事件**生成。"""

    run_root = Path(tmp_path) / "run"
    # 历史：提案 2 = M1@overall 用 A；提案 3 = M1@specialty 用 F（专长席）。
    for index, (channel, family, parent) in ((2, ("overall", None, "A")),
                                            (3, ("specialty", "branch", "F"))):
        iter_dir = run_root / "iterations" / "iter-{0:02d}".format(index)
        iter_dir.mkdir(parents=True, exist_ok=True)
        _write_json(iter_dir / "state.json", {
            "schema": search.AV_ITERATION_STATE_SCHEMA,
            "run_id": "run-{0}".format(index), "iteration_no": index,
            "status": "ITERATION_COMPLETE",
            "created_at_utc": "2026-09-17T00:00:0{0}Z".format(index),
            "step_history": [], "identity": {"candidate_id": "child-{0}".format(index)},
            "iter_dir": str(iter_dir),
            "plan": {"operator": "m1", "seed_name": "efficiency_seed",
                     "archive_in": {"planned_operator": "M1",
                                    "planned_channel": channel,
                                    "planned_family": family,
                                    "planned_parent_candidate_id": parent,
                                    "proposal_no": index}},
        })
    archive = _sched_archive()
    history = search._av_plan_history(run_root)
    assert [row["parent_candidate_id"] for row in history] == ["A", "F"]
    assert [row["channel"] for row in history] == ["overall", "specialty"]
    plan = sa.next_generation_plan(archive, history)
    assert plan["operator"] == "M1" and plan["channel"] == "overall"
    assert plan["parent_candidate_id"] == "B"
    # 对照反例：丢掉 channel 字段的历史（旧投影形态）会重复选已用过的 A。
    blind = [{key: row[key] for key in ("operator", "parent_candidate_id", "family")}
             for row in history]
    assert sa.next_generation_plan(archive, blind)["parent_candidate_id"] != "B"


# ---------------------------------------------------------------------------
# A4 端到端：报告计划 == 实际计划（连续 6 个提案）
# ---------------------------------------------------------------------------


class _FakeDrive:
    """替身桌赛驱动（0 真实桌赛）：按焦点臂给确定性分数，语义与 v4/P6 测试同源。

    焦点座位候选臂 +12、基线臂 -10（按 seed 微扰）→ 候选臂 U=1、基线臂 U=0，
    保证组内晋级目标可算（否则样本 uncomputable，档案无根）。
    """

    def __call__(self, *, plan, policies_by_seat, versions_block, step_limit,
                 value_limits):
        seats = list(plan.seats())
        focal_idx = seats.index("natural:focal") if "natural:focal" in seats \
            else seats.index("focal")
        focal_policy = policies_by_seat[focal_idx]
        is_candidate = str(getattr(focal_policy, "policy_id", "")).startswith(
            "action_value")
        offset = plan.seed % 7 - 3
        scores = []
        for seat in range(4):
            if seat == focal_idx:
                scores.append(12 + offset if is_candidate else -10 + offset)
            else:
                scores.append(2 - seat + (offset if seat % 2 else -offset))
        return {"table_id": plan.table_id, "seed": int(plan.seed),
                "match_status": "complete", "wall_ms": 1.0,
                "scores_by_seat": scores, "result": {}}


def _variant_seed(index):
    """第 index 个变体源码：同一牌效逻辑 + 唯一常量 → 不同源码身份。"""

    from hangma_bot.policy.action_value_seeds import EFFICIENCY_SEED

    lines = EFFICIENCY_SEED.source.splitlines()
    head, body = lines[:2], lines[2:]
    return "\n".join(head + ['VARIANT_TAG = "variant-{0}"'.format(index)] + body)


def _patch_seed(monkeypatch, index):
    from hangma_bot.policy import action_value_seeds as seeds

    spec = seeds.SeedSpec(name="efficiency_seed", source=_variant_seed(index),
                          mechanism=dict(seeds.EFFICIENCY_SEED_MECHANISM))
    monkeypatch.setitem(seeds.SEEDS, "efficiency_seed", spec)


def _run_mock_iteration(run_root, index, monkeypatch):
    """跑一个 mock 迭代（变体源码 → 不同源码身份）；返回最新状态。"""

    _patch_seed(monkeypatch, index)
    result = search.run_av_evolution(
        run_root, generation_mode="mock", seed_name="efficiency_seed",
        authorization=TOKEN, natural_roots=1, natural_seats=1)
    assert result.get("terminal") == "ITERATION_COMPLETE", result
    return search.av_state_load(search.av_latest_state_path(run_root))


def test_a3_chain_entries_carry_signature_and_behavior_dedup(tmp_path, monkeypatch):
    """端到端：行为签名随条目落档；源码不同但动作相同者不重复占探索席。"""

    import sitin_natural_panel as natural

    monkeypatch.setattr(natural, "execute_natural_table", _FakeDrive(), raising=True)
    run_root = Path(tmp_path) / "chain" / "iter-01"
    states = [_run_mock_iteration(run_root, index, monkeypatch) for index in range(3)]
    ids = [state["identity"]["candidate_id"] for state in states]
    assert len(set(ids)) == 3                       # 三个源码身份确实不同
    archive = _read_json(run_root / "archive" / "av-archive.json")
    for cid in ids:
        signature = archive["entries"][cid]["behavior_signature"]
        assert signature is not None, cid
        assert signature["view_set"] == list(search.AV_BEHAVIOR_VIEWS)
        assert len(signature["windows"]) == len(search.AV_BEHAVIOR_VIEWS)
        assert archive["entries"][cid]["behavior_digest"]
    # 变体源码只多了个常量 → 三者行为完全相同：被挤在候补位者不占探索席。
    pool_seated = set(archive["selection_report"]["overall"][index]["candidate_id"]
                      for index in range(2))
    leftover = sorted(set(ids) - pool_seated)
    assert len(leftover) == 1, (pool_seated, ids)
    assert leftover[0] not in archive["slots"]["exploration"]
    assert archive["behavior_duplicates"] == {leftover[0]: sorted(pool_seated)}
    assert archive["slots"]["exploration"] == []
    # A2：挑战未提交（0 个新刷新根）→ 在原席保持，只在候选池累积。
    assert archive["slots"]["overall"] == [ids[0]]
    assert set(archive["entries"]) == set(ids)
    # 第三个迭代的行为步：源码身份不同，但行为与在案席者相同 → 分别记录。
    behavior = states[2]["behavior"]
    assert behavior["source_duplicate_in_archive"] is False   # 源码身份不同
    assert behavior["behavior_duplicate_in_archive"] is True
    assert behavior["behavior_duplicate_of"]
    assert behavior["behavior_signature"]["unknown_mask"]

def test_a4_batch_report_next_package_matches_next_iteration(tmp_path, monkeypatch):
    """端到端：连续 6 个提案，每个提案的 batch-report.next_task_package 必须与
    下一迭代**实际执行的计划**逐项一致（复审 R6 实测：声明 M1 实跑 I1）。"""

    import sitin_natural_panel as natural

    monkeypatch.setattr(natural, "execute_natural_table", _FakeDrive(), raising=True)
    run_root = Path(tmp_path) / "chain" / "iter-01"
    reports = []
    actual = []
    for index in range(6):
        _patch_seed(monkeypatch, index)
        result = search.run_av_evolution(
            run_root, generation_mode="mock", seed_name="efficiency_seed",
            authorization=TOKEN, natural_roots=1, natural_seats=1)
        assert result.get("terminal") == "ITERATION_COMPLETE", result
        state = search.av_state_load(search.av_latest_state_path(run_root))
        report = _read_json(Path(state["iter_dir"]) / "batch-report.json")
        reports.append(report["next_task_package"])
        archive_in = state["plan"]["archive_in"]
        actual.append({"operator": archive_in.get("planned_operator"),
                       "parent_candidate_id": archive_in.get("planned_parent_candidate_id"),
                       "channel": archive_in.get("planned_channel")})

    assert len(reports) == 6
    # 逐提案对照：第 k 个提案声明的下一步 == 第 k+1 个提案实际执行的计划。
    for index in range(5):
        expected = reports[index]
        got = actual[index + 1]
        assert (expected["operator"], expected["parent_candidate_id"],
                expected["channel"]) == (got["operator"],
                                         got["parent_candidate_id"], got["channel"]), \
            ("提案 {0} 报告计划与实际计划不一致".format(index + 1), expected, got)
    # 3×M1 + 1×I1 节奏（提案 1 固定 I1）：2/3/4 = M1，5 = I1，6 = M1。
    assert [row["operator"] for row in actual] == [
        "I1", "M1", "M1", "M1", "I1", "M1"]


def test_a4_failed_proposal_consumes_budget(tmp_path):
    """失败提案同样占用提案额度：被拒迭代后的下一个提案号连着数上去。"""

    run_root = Path(tmp_path) / "run"
    for index, status in ((1, "ITERATION_COMPLETE"), (2, "REJECTED")):
        iter_dir = run_root / "iterations" / "iter-{0:02d}".format(index)
        iter_dir.mkdir(parents=True, exist_ok=True)
        _write_json(iter_dir / "state.json", {
            "schema": search.AV_ITERATION_STATE_SCHEMA,
            "run_id": "run-{0}".format(index), "iteration_no": index,
            "status": status,
            "created_at_utc": "2026-09-17T00:00:0{0}Z".format(index),
            "step_history": [], "identity": {"candidate_id": "cand-{0}".format(index)},
            "iter_dir": str(iter_dir), "rejection": ({"reason": "生成失败"}
                                                      if status == "REJECTED" else None),
            "plan": {"operator": "i1", "archive_in": {"planned_operator": "I1",
                                                      "proposal_no": index}},
        })
    history = search._av_plan_history(run_root)
    assert [row["proposal_no"] for row in history] == [1, 2]
    assert history[1]["operator"] == "I1" and history[1]["failed"] is True
    plan = sa.next_generation_plan(_sched_archive(), history)
    assert plan["proposal_no"] == 3 and plan["operator"] == "M1"
    # 重复提案同样占额度：记一条 duplicate 事件后，提案号继续往前走。
    duplicate_event = _event(3, {"operator": "I1", "parent_candidate_id": None,
                                 "channel": None, "family": None},
                             status="ITERATION_COMPLETE", iter_dir="/tmp/iter-03")
    duplicate_event["duplicate"] = True
    search.av_proposal_event_append(run_root, duplicate_event)
    history = search._av_plan_history(run_root)
    assert len(history) == 3 and sum(1 for row in history if row["duplicate"]) == 1
    plan = sa.next_generation_plan(_sched_archive(), history)
    assert plan["proposal_no"] == 4 and plan["operator"] == "M1"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))