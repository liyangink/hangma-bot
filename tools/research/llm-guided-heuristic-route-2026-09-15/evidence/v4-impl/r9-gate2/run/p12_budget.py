#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P12 · G2：比较预算**从待执行实例集合生成**（先看见全部缺边，再谈额度）。

裁定原文（R9-ACCEPTANCE-AND-Q1-Q7-RULING §4.3 / §5 G2）：

> 预算应从**待执行实例集合**生成：候选/在席者 × 其缺失的核心根与刷新根 × 座位 × 评价臂 ×
> 阶段终点，并区分已完成可复用项、共享基线、前缀发现、截取续打、完整桌赛和失败费用。
> 先保证一项比较能够闭合，再分配额外新根发现预算。扩大探针额度不会补齐当前缺失的评价。
> 上一版自然面板公式中"根数"的含义也须消歧：……统一写
> `Σ情景(该情景根数 × 换座数 × 2臂 × 每阶段桌数)`；例如 H/M 合计 8 根、4 座、2 臂、
> 2 桌是 **128** 个完整桌实例，不是 256。此算例仅解释计数，不授权该规模；条件续打和
> 补评另按清单计。

以及 §6 步骤 2 的停止条件：
> 纯数据即可检验，不先跑桌赛。预算预检必须看见完整比较所有缺边，**不以扩大封顶代替漏算修复**。

本模块提供：

- `natural_panel_table_count`：自然面板完整桌实例的**唯一**计算公式（消歧 + 自检样例）；
- `build_execution_set`：待执行实例集合（每行带 `kind`、`basis`、`planned_tables`）；
- `comparison_gap`：完整比较**尚未闭合的边**（逐条列出，不靠数量估算）；
- `preflight_budget`：开跑前预检（缺边 + 逐账户需求 + 封顶关系），缺边未闭合即拒绝开跑。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-gate2/run'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

#: 待执行实例集合的行类型（裁定 §4.3 要求逐类区分；名字即口径）。
KIND_REUSABLE = "reusable_completed"
KIND_SHARED_BASELINE = "shared_baseline"
KIND_PREFIX_DISCOVERY = "prefix_discovery"
KIND_CUT_CONTINUATION = "cut_continuation"
KIND_FULL_TABLES = "full_tables"
KIND_FAMILY_CORE_REVIEW = "family_core_root_review"
KIND_FAMILY_REFRESH = "family_refresh_root"
KIND_FAMILY_OLD_ROOT = "family_old_root_review"
#: 共同根比较的**指定旧根重评**（intent=reevaluate_registered_root）：
#: 与"新根发现"（discover_new_root）分开计——前者是必要比较边，后者是额外新根发现。
KIND_FAMILY_REEVAL = "family_reevaluation"
KIND_FAILURE = "failure_allowance"

KINDS: Tuple[str, ...] = (KIND_REUSABLE, KIND_SHARED_BASELINE,
                          KIND_PREFIX_DISCOVERY, KIND_CUT_CONTINUATION,
                          KIND_FULL_TABLES, KIND_FAMILY_CORE_REVIEW,
                          KIND_FAMILY_REEVAL, KIND_FAMILY_REFRESH,
                          KIND_FAMILY_OLD_ROOT, KIND_FAILURE)


def natural_panel_table_count(*, buckets: Sequence[Mapping[str, Any]]
                              ) -> Dict[str, Any]:
    """自然面板完整桌实例数 = `Σ情景(该情景根数 × 换座数 × 2 臂 × 每阶段桌数)`。

    **口径消歧（裁定 §4.3）**：`buckets` 是**已经分好桶**的 (情景 × 迭代) 清单，
    每桶的 `roots` 是该桶的根数；桶的根数之和就是"合计根数"。
    `Σ(root_instances × 换座 × 2 臂 × 每阶段桌数)` 才是权威口径；
    把合计根数**再乘一次情景数**得到的是复审公式的**保守上界**（256），不是权威值（128）。
    两套数字都报，以 `authoritative` 为准。
    """

    per_bucket: List[Dict[str, Any]] = []
    total = 0
    root_instances = 0
    scenarios: List[str] = []
    for row in buckets:
        roots = int(row.get("roots") or 0)
        seats = int(row.get("seats") or 0)
        arms = int(row.get("arms") or 2)
        tables = int(row.get("tables_per_stage") or 0)
        value = roots * seats * arms * tables
        root_instances += roots
        if str(row.get("scenario")) not in scenarios:
            scenarios.append(str(row.get("scenario")))
        total += value
        per_bucket.append({"scenario": row.get("scenario"),
                           "iteration": row.get("iteration"),
                           "roots": roots, "seats": seats, "arms": arms,
                           "tables_per_stage": tables, "tables": value,
                           "basis": ("该桶根数 {0} × 换座 {1} × {2} 臂 × 每阶段 "
                                     "{3} 桌".format(roots, seats, arms, tables))})
    seats_any = int(buckets[0].get("seats") if buckets else 0)
    tables_any = int(buckets[0].get("tables_per_stage") if buckets else 0)
    conservative = (root_instances * max(1, len(scenarios)) * seats_any * 2 * tables_any)
    return {
        "schema": "sitin-gate2-natural-tables/1",
        "authoritative": total,
        "authoritative_formula": "Σ情景(该情景根数 × 换座数 × 2 臂 × 每阶段桌数)",
        "root_instances_total": root_instances,
        "n_scenarios": len(scenarios),
        "per_bucket": per_bucket,
        "conservative_upper_bound_if_multiply_scenarios_again": conservative,
        "disambiguation": ("桶已按情景（× 迭代）分好时不得再乘情景数："
                           "合计根数 × 情景数 × 换座 × 2 臂 × 每阶段桌数 是保守上界"),
        "note": "本算例只解释计数，不授权规模（裁定 §4.3）",
    }


def reference_case_check() -> Dict[str, Any]:
    """裁定 §4.3 的算例自检：H/M 合计 8 根 / 4 座 / 2 臂 / 2 桌 = **128**（不是 256）。"""

    buckets = [{"scenario": mix, "iteration": iteration, "roots": 2, "seats": 4,
                "arms": 2, "tables_per_stage": 2}
               for iteration in (1, 2) for mix in ("H", "M")]
    counted = natural_panel_table_count(buckets=buckets)
    return {
        "root_instances_total": counted["root_instances_total"],
        "authoritative_tables": counted["authoritative"],
        "expected_authoritative": 128,
        "conservative_upper_bound": counted[
            "conservative_upper_bound_if_multiply_scenarios_again"],
        "expected_conservative": 256,
        "ok": (counted["root_instances_total"] == 8
               and counted["authoritative"] == 128
               and counted["conservative_upper_bound_if_multiply_scenarios_again"] == 256),
        "note": ("8 根（2 情景 × 2 根 × 2 迭代）/ 4 座 / 2 臂 / 2 桌 ⇒ 128；"
                 "把 8 根再乘情景数得到 256 是保守上界（生产分解以 128 为准）"),
    }


# ===========================================================================
# 待执行实例集合
# ===========================================================================


def _load_run_state(run_root: Path) -> Dict[str, Any]:
    import p12_reconcile as R  # 同目录模块（只读）
    state: Dict[str, Any] = {"iterations": {}, "family_roots": {},
                             "natural_panels": {}}
    for label, state_path in R.state_files(Path(run_root)):
        payload = R.read_json(state_path) or {}
        state["iterations"][label] = {"status": payload.get("status"),
                                      "stop_reason": payload.get("stop_reason"),
                                      "iter_dir": str(state_path.parent),
                                      "candidate_id": ((payload.get("identity") or {})
                                                       .get("candidate_id"))}
    accounting = R.production_accounting(Path(run_root))
    state["family_roots"] = accounting.get("family_roots") or {}
    state["natural_panels"] = accounting.get("natural_panels") or {}
    # 生产自己报的"缺哪些根"（family_fill.missing）：只作为**对照**，不作为需求集合。
    missing: Dict[str, List[str]] = {}
    for label, state_path in R.state_files(Path(run_root)):
        payload = R.read_json(state_path) or {}
        block = ((payload.get("family_fill") or {}).get("missing") or {})
        if isinstance(block, Mapping):
            for cid, roots in block.items():
                missing.setdefault(str(cid), [])
                missing[str(cid)].extend(str(root) for root in (roots or ()))
    state["family_missing"] = missing
    return state


def build_execution_set(*, plan: Mapping[str, Any], run_root: Optional[Path] = None
                        ) -> Dict[str, Any]:
    """从**待执行实例集合**出发生成比较需求（不是从封顶反推）。

    计划侧给出全部需求；给了运行根目录时，把**已经完成可核**的实例标成
    `reusable_completed`（复用只记引用，不重复计费），其余仍是待执行。
    """

    import p12_reconcile as R
    expected = R.plan_expected_instances(plan)
    completed: Dict[str, Dict[str, Any]] = {}
    if run_root is not None:
        join = R.reconcile_instances(Path(run_root), plan)
        for channel in R.CHANNELS:
            for item in ((join.get("channels") or {}).get(channel) or {}).get(
                    "items") or ():
                if str(item.get("terminal")) == R.TERMINAL_COMPLETED:
                    completed[_purpose_key(channel, item)] = item
    rows: List[Dict[str, Any]] = []
    for row in expected:
        channel = row["channel"]
        purpose = row.get("root_purpose") or _purpose_of(channel)
        key = _purpose_key(channel, row)
        done = completed.get(key)
        rows.append({
            "kind": (KIND_REUSABLE if done else _kind_of(
                channel, purpose, category=str(row.get("category") or ""))),
            "category": row.get("category"),
            "channel": channel, "iteration": row.get("iteration"),
            "candidate_slot": row.get("plan_candidate_slot"),
            "opponent_mix": row.get("opponent_mix"),
            "source_root_id": row.get("source_root_id"),
            "root_index": row.get("root_index"), "seat": row.get("seat"),
            "arm": row.get("arm"), "schedule": row.get("schedule"),
            "planned_tables": float(row.get("planned_tables") or 0.0),
            "tables": 0.0 if done else float(row.get("planned_tables") or 0.0),
            "reuse_reference": (None if not done else {
                "instance_key": done.get("key"),
                "evidence": "运行产物里该冻结实例已完成且可核（复用只记引用）"}),
            "basis": row.get("expansion"),
        })
    summary: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        bucket = summary.setdefault(str(row["kind"]), {"n_instances": 0,
                                                       "planned_tables": 0.0,
                                                       "tables_due": 0.0})
        bucket["n_instances"] += 1
        bucket["planned_tables"] = round(
            bucket["planned_tables"] + float(row["planned_tables"]), 6)
        bucket["tables_due"] = round(bucket["tables_due"] + float(row["tables"]), 6)
    allowance = _failure_allowance(plan)
    summary[KIND_FAILURE] = allowance["summary"]
    tables_due = round(sum(float(bucket["tables_due"]) for name, bucket in summary.items()
                           if name != KIND_FAILURE), 6)
    return {
        "schema": "sitin-gate2-execution-set/1",
        "iterations": [str(item.get("iteration_label"))
                       for item in (plan.get("iterations") or ())],
        "rows": rows, "summary": summary,
        "tables_due_excluding_failure_allowance": tables_due,
        "failure_allowance": allowance,
        "natural_tables": natural_panel_table_count(
            buckets=_natural_buckets(plan)),
        "note": ("待执行实例集合 = 计划全集 − 已完成可核（复用只记引用）；"
                 "逐类区分共享基线/前缀发现/截取续打/完整桌赛/核心根复评/刷新根发现/"
                 "指定旧根重评/失败余量"),
    }


def _natural_buckets(plan: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """自然面板的 (情景 × 迭代) 分桶：**每桶根数取该迭代自己的 `natural_roots`**。

    为什么不能再用 plan_config 的单一值：第二候选为了满足**整体通道刷新批 4 根**
    （不在当前 epoch 的自然根）会把自然面板从每情景 2 根扩到 4 根（补 H3/H4、M3/M4）。
    用单一值会把权威桌数少算（P20 实测：192 被算成 128），从而与计划自报值不符。
    """

    cfg = plan.get("plan_config") or {}
    fallback_roots = int(cfg.get("natural_roots") or 0)
    seats = int(cfg.get("natural_seats") or 0)
    tables = int(cfg.get("tables_per_group") or 0)
    iterations = list(plan.get("iterations") or ()) or [{}]
    buckets: List[Dict[str, Any]] = []
    for position, spec in enumerate(iterations, start=1):
        roots = int(spec.get("natural_roots") or fallback_roots)
        for mix in ("H", "M"):
            buckets.append({"scenario": mix, "iteration": position, "roots": roots,
                            "seats": int(spec.get("natural_seats") or seats),
                            "arms": 2, "tables_per_stage": tables})
    return buckets


def _purpose_of(channel: str) -> str:
    import p12_reconcile as R
    if channel == R.CHANNEL_SHARED_BASELINE:
        return "shared_baseline"
    if channel == R.CHANNEL_CONDITIONAL:
        return "prefix_discovery"
    if channel == R.CHANNEL_FAMILY:
        return "family_core_root_review"
    return "natural_full_tables"


def _kind_of(channel: str, purpose: str, *, category: str = "") -> str:
    import p12_reconcile as R
    if channel == R.CHANNEL_CONDITIONAL:
        # 条件通道有两类账目口径：前缀生成（tables_partial）与截取后完整续打（tables_full）。
        return (KIND_CUT_CONTINUATION if category == "conditional_full"
                else KIND_PREFIX_DISCOVERY)
    if channel == R.CHANNEL_FAMILY:
        if purpose == "family_old_root_review":
            return KIND_FAMILY_OLD_ROOT
        if purpose == "family_reevaluation":
            return KIND_FAMILY_REEVAL
        if purpose == "family_refresh_root":
            return KIND_FAMILY_REFRESH
        return KIND_FAMILY_CORE_REVIEW
    if channel == R.CHANNEL_SHARED_BASELINE:
        return KIND_SHARED_BASELINE
    return KIND_FULL_TABLES


def _purpose_key(channel: str, item: Mapping[str, Any]) -> str:
    """复用判定的键：与冻结实例键同口径（候选之外每一维都在）。

    家族根的完整身份在运行期才解析：家族键只保留 **cell × 根序号 × 臂**，
    根 id/种子不进键（身份另有判据单独核），否则计划侧与运行侧永远对不上。
    """

    import p12_reconcile as R
    family = str(channel) == R.CHANNEL_FAMILY
    return R.instance_key(
        iteration=item.get("iteration"), channel=channel,
        mix=item.get("opponent_mix"),
        root_id=(None if family else item.get("source_root_id")),
        root_index=item.get("root_index"),
        root_seed=(None if family else item.get("root_seed")),
        seat=item.get("seat", 0), arm=item.get("arm"),
        schedule=item.get("schedule"),
        cell=(item.get("sub_scenario")
              or R.sub_scenario_of_root(item.get("source_root_id"))))


def _failure_allowance(plan: Mapping[str, Any]) -> Dict[str, Any]:
    cfg = plan.get("plan_config") or {}
    family_cfg = ((plan.get("frozen_inputs") or {}).get("family_config") or {})
    pconf = plan.get("plan_config") or {}
    rerun_roots = int(pconf.get("rerun_roots") or 0)
    natural_root_tables = (int(cfg.get("natural_roots") or 0)
                           * int(cfg.get("natural_seats") or 0) * 2
                           * int(cfg.get("tables_per_group") or 0))
    family_root_tables = float(family_cfg.get("tables_per_family_evaluation") or 4.0)
    per_root = max(float(natural_root_tables), float(family_root_tables))
    return {
        "whole_root_reruns": rerun_roots,
        "natural_root_tables": float(natural_root_tables),
        "family_root_tables": family_root_tables,
        "summary": {"n_instances": rerun_roots,
                    "planned_tables": round(rerun_roots * per_root, 6),
                    "tables_due": round(rerun_roots * per_root, 6),
                    "basis": ("失败余量按较贵的整根口径折算（自然整根 {0} 桌 / "
                              "家族整根 {1} 桌）".format(natural_root_tables,
                                                          family_root_tables))},
        "note": ("失败重试有真实成本（裁定 §5 G1）：余量按整根重跑计，"
                 "不从「未发生」里扣"),
    }


# ===========================================================================
# 完整比较的缺边
# ===========================================================================


def comparison_gap(*, plan: Mapping[str, Any], run_root: Path) -> Dict[str, Any]:
    """完整共同根比较**尚未闭合的边**（逐条列出；不靠数量估算、不靠封顶掩盖）。"""

    import p12_reconcile as R
    run_state = _load_run_state(Path(run_root))
    core_roots = [dict(row) for row in (plan.get("frozen_root_list") or ())]
    tables_per_group = int((plan.get("plan_config") or {}).get("tables_per_group") or 2)
    # 覆盖来源 = **家族根评价产物**（不是登记行数、也不是实例条数）：
    # 只有"某个候选在某个核心根上有可核评价"才算那条比较边闭合。
    products = R.family_evaluation_products(Path(run_root))
    # 候选集合取**运行里出现过的候选**（状态/台账/产物并集），不是"有评价产物的候选"：
    # 挑战者一条评价都没有时也必须出现在缺边清单里（否则"完整比较"会假绿）。
    candidates: Dict[str, Dict[str, Any]] = {}
    for candidate in R.run_candidates(Path(run_root)):
        candidates.setdefault(str(candidate), {"completed": set(), "failed": set(),
                                               "evaluations": 0})
    for row in products:
        cid = str(row.get("candidate_id") or "")
        bucket = candidates.setdefault(cid, {"completed": set(), "failed": set(),
                                             "evaluations": 0})
        bucket["evaluations"] += 1
        mark_cell = "{0}|{1}|{2}".format(row.get("sub_scenario"),
                                         row.get("opponent_mix"),
                                         row.get("root_index"))
        for arm in (row.get("arms") or ("baseline", "candidate")):
            if row.get("ok") and row.get("arms_complete"):
                bucket["completed"].add("{0}|{1}".format(mark_cell, arm))
            else:
                bucket["failed"].add("{0}|{1}".format(mark_cell, arm))
    missing_edges: List[Dict[str, Any]] = []
    per_candidate: List[Dict[str, Any]] = []
    for cid, bucket in sorted(candidates.items()):
        if not cid:
            continue
        need: List[Dict[str, Any]] = []
        for root in core_roots:
            for arm in ("baseline", "candidate"):
                mark = "{0}|{1}|{2}|{3}".format(root.get("sub_scenario"),
                                                root.get("opponent_mix"),
                                                root.get("root_index"), arm)
                if mark in bucket["completed"]:
                    continue
                need.append({
                    "candidate_id": cid, "sub_scenario": root.get("sub_scenario"),
                    "opponent_mix": root.get("opponent_mix"),
                    "root_index": root.get("root_index"),
                    "root_id": root.get("root_id"), "root_seed": root.get("root_seed"),
                    "seat": 0, "arm": arm,
                    "endpoint": "conditional_stage:{0}_tables".format(tables_per_group),
                    "planned_tables": float(tables_per_group),
                    "kind": (KIND_FAMILY_CORE_REVIEW
                             if mark not in bucket["failed"]
                             else KIND_FAMILY_CORE_REVIEW),
                    "basis": ("共同根比较要求：在席者与挑战者都要在该核心根上有可核评价"
                              "（{0}臂）".format(arm)),
                    "prior_failure_recorded": mark in bucket["failed"]})
        core_marks = {"{0}|{1}|{2}|{3}".format(root.get("sub_scenario"),
                                               root.get("opponent_mix"),
                                               root.get("root_index"), arm)
                      for root in core_roots for arm in ("baseline", "candidate")}
        missing_edges.extend(need)
        per_candidate.append({"candidate_id": cid,
                              "evaluations_recorded": bucket["evaluations"],
                              "core_edges_total": len(core_marks),
                              "core_edges_completed": len(core_marks & bucket["completed"]),
                              "core_roots_missing": len({
                                  row["sub_scenario"] + "|" + str(row["opponent_mix"])
                                  + "|" + str(row["root_index"]) for row in need}),
                              "core_edges_missing": len(need),
                              "tables_missing": round(sum(
                                  float(row["planned_tables"]) for row in need), 6)})
    # 指定旧根重评与新刷新根发现分开算（裁定 §4.1；根用途不得混成一个清单）。
    old_root_edges = [row for row in R.plan_expected_instances(plan)
                      if row.get("root_purpose") == "family_old_root_review"]
    refresh_edges = [row for row in R.plan_expected_instances(plan)
                     if row.get("root_purpose") == "family_refresh_root"]
    done_mark = {(row.get("sub_scenario"), row.get("opponent_mix"),
                  row.get("root_index"))
                 for row in products if row.get("ok") and row.get("arms_complete")}
    done_keys = {
        R.instance_key(iteration=row.get("iteration"), channel=R.CHANNEL_FAMILY,
                       mix=row.get("opponent_mix"), root_id=None,
                       root_index=row.get("root_index"), root_seed=None, seat=0,
                       arm=arm, schedule="conditional_stage:{0}_tables".format(
                           tables_per_group), cell=row.get("sub_scenario"))
        for row in products if row.get("ok") and row.get("arms_complete")
        for arm in ("baseline", "candidate")}
    old_missing = [row for row in old_root_edges if _purpose_key(
        row["channel"], row) not in done_keys]
    refresh_missing = [row for row in refresh_edges if _purpose_key(
        row["channel"], row) not in done_keys]
    # 「指定旧根」的运行期根由**条件通道**承担时，家族通道自然没有行：
    # 这不是"没跑成"，而是"由别的通道的可核产物承担"（basis 具名 + 产物路径 + 摘要状态）。
    coverage = R.cross_channel_coverage(Path(run_root))
    roots_by_iter = R.conditional_roots_by_iteration(Path(run_root))
    candidates_by_iter: Dict[str, str] = {}
    for label, state_path in R.state_files(Path(run_root)):
        state = R.read_json(state_path) or {}
        candidate = str((state.get("identity") or {}).get("candidate_id") or "")
        if candidate:
            candidates_by_iter[str(R._ordinal(label))] = candidate
    old_covered: List[Dict[str, Any]] = []
    old_uncovered: List[Dict[str, Any]] = []
    for row in old_missing:
        verdict = R.declaration_coverage(
            _purpose_key(row["channel"], row), row["channel"], plan_row=row,
            run_root=Path(run_root), coverage=coverage, roots_by_iter=roots_by_iter,
            candidates_by_iter=candidates_by_iter)
        if verdict:
            old_covered.append(dict({
                "iteration": row.get("iteration"), "arm": row.get("arm"),
                "sub_scenario": row.get("sub_scenario"),
                "opponent_mix": row.get("opponent_mix"),
                "planned_tables": row.get("planned_tables")}, **verdict))
        else:
            old_uncovered.append(row)
    return {
        "schema": "sitin-gate2-comparison-gap/1",
        "core_roots": len(core_roots),
        "candidates_seen": sorted(candidates),
        "per_candidate": per_candidate,
        "missing_core_edges": missing_edges,
        "missing_core_tables": round(sum(float(row["planned_tables"])
                                         for row in missing_edges), 6),
        "old_root_review": {"total": len(old_root_edges),
                            "missing": len(old_uncovered),
                            "missing_rows": old_uncovered[:10],
                            "covered_by_other_channel": old_covered[:10],
                            "covered_count": len(old_covered),
                            "basis_note": ("运行期才解析的「指定旧根」声明：若同一候选在"
                                           "**同一完整根**上已有可核评价（本运行落在条件通道），"
                                           "该义务由该产物承担（basis=conditional_channel_product，"
                                           "路径与摘要状态在 covered 行里）")},
        "refresh_root_discovery": {"total": len(refresh_edges),
                                   "missing": len(refresh_missing),
                                   "missing_rows": refresh_missing[:10]},
        "production_stop": sorted({
            "{0}:{1}".format(label, (state or {}).get("stop_reason"))
            for label, state in (run_state.get("iterations") or {}).items()
            if (state or {}).get("stop_reason")}),
        "production_reported_missing": run_state.get("family_missing") or {},
        "production_missing_undercount_note": (
            "生产的 family_fill.missing 是**它自己的口径**；与本模块的逐键覆盖可能不一致"
            "（本次 P9c 证据副本实测：挑战者缺 8 个核心根，生产只列 7 条 ⇒ "
            "预算预检必须以逐键覆盖为准，不能引用生产清单当需求集合）"),
        "seats_per_root": 1,
        "note": ("完整比较 = 每个候选在每个核心根上都有可核评价（2 臂）；"
                 "缺边逐条列出，不用「多出多少条记录」估算，也不靠抬高封顶掩盖"),
    }


#: 待执行实例集合的 kind → 账本账户（预检把「封顶」与「授权」按各自口径分开比）。
KIND_ACCOUNT: Dict[str, str] = {
    KIND_FULL_TABLES: "tables_full",
    KIND_SHARED_BASELINE: "tables_full",
    KIND_CUT_CONTINUATION: "tables_full",
    KIND_FAMILY_CORE_REVIEW: "tables_full",
    KIND_FAMILY_REEVAL: "tables_full",
    KIND_FAMILY_REFRESH: "tables_full",
    KIND_FAMILY_OLD_ROOT: "tables_full",
    KIND_PREFIX_DISCOVERY: "tables_partial",
    KIND_REUSABLE: "tables_full",
    KIND_FAILURE: "tables_full",
}


def authorized_accounts(plan: Mapping[str, Any]) -> Dict[str, float]:
    """授权额度（**与封顶是两个不同的概念**）。

    `tables_full` = 计划里挂在 tables_full 账户上的类目之和（**含失败重跑余量**）：
    natural_full + conditional_full + family_fill + failure_rerun_allowance。
    计划文档写明：余量 64 已含在 tables_full 264 授权内（tables_full 口径可执行 200 +
    余量 64 = 264）⇒ "余量"要相对**授权**判，**不能与 cap 相加**。
    """

    cats = {str(row.get("category")): row for row in
            ((plan.get("budget") or {}).get("by_category") or ())}

    def _tables(name: str) -> float:
        return float((cats.get(name) or {}).get("planned_tables") or 0.0)

    return {"tables_full": round(_tables("natural_full") + _tables("conditional_full")
                                 + _tables("family_fill")
                                 + _tables("failure_rerun_allowance"), 6)}


def required_reevaluation_declarations(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """纯数据判据：**挑战者的共同根比较必须逐条发出"指定旧根重评"声明**。

    为什么必须有这条（run5 实测）：计划的 `family_refresh` 只有 discover 行时，
    挑战者在在席者的核心根上**永远没有评价** ⇒ 共同根比较补不齐（缺边 16 条 / 32 桌）；
    而点了**已登记**的根却不写 intent ⇒ 生产按 discover 解释并**整格拒绝**
    （`root_intent_ambiguous_registered_root`），run5 因此停在
    `family_refresh_declaration_unfulfillable/family_refresh_declaration_unfillable`。

    判据（逐条都必须成立，任一不成立即 FAIL）：
    1. 计划里除第一个候选以外的每个迭代，对**冻结核心根清单**的每一根，
       都要有一条 `intent=reevaluate_registered_root` 的声明（按 子场景 × 情景 × 根序号 对齐）；
    2. 该声明的冻结描述符必须**逐字一致**（root_id / root_seed 与冻结清单相同）；
    3. 不得把核心根声明成 `discover_new_root`（那正是会被拒绝/静默换根的写法）。
    """

    frozen = [dict(row) for row in (plan.get("frozen_root_list") or ())]
    core = {(str(row.get("sub_scenario")), str(row.get("opponent_mix")),
             int(row.get("root_index") or 0)): row for row in frozen}
    iterations = list(plan.get("iterations") or ())
    problems: List[Dict[str, Any]] = []
    per_iteration: List[Dict[str, Any]] = []
    for position, spec in enumerate(iterations):
        if position == 0:
            continue                     # 第一候选：核心根由它自己物化（discover 正确）
        label = str(spec.get("iteration_label"))
        decls = [dict(row) for row in (spec.get("family_refresh") or ())]
        reeval = {(str(row.get("sub_scenario")), str(row.get("opponent_mix")),
                   int(row.get("root_index") or -1)): row
                  for row in decls
                  if str(row.get("intent")) == "reevaluate_registered_root"
                  and row.get("root_index") is not None}
        discover_named_core = sorted(
            "{0}|{1}|root{2:03d}".format(sub, mix, idx) for (sub, mix, idx) in core
            if (any(str(row.get("intent")) != "reevaluate_registered_root"
                    and int(row.get("root_index") or -1) == idx
                    and str(row.get("sub_scenario")) == sub
                    and str(row.get("opponent_mix")) == mix for row in decls)))
        missing = sorted("{0}|{1}|root{2:03d}".format(sub, mix, idx)
                         for (sub, mix, idx) in core if (sub, mix, idx) not in reeval)
        descriptor_mismatch = []
        for (sub, mix, idx), row in sorted(reeval.items()):
            expect = core.get((sub, mix, idx))
            if expect is None:
                continue
            if (str(row.get("root_id")) != str(expect.get("root_id"))
                    or int(row.get("root_seed") or -1) != int(
                        expect.get("root_seed") or -2)):
                descriptor_mismatch.append({
                    "cell": "{0}|{1}|root{2:03d}".format(sub, mix, idx),
                    "declared": [row.get("root_id"), row.get("root_seed")],
                    "frozen": [expect.get("root_id"), expect.get("root_seed")]})
        old_root_rows = [row for row in decls if row.get("root_index") is None]
        old_root_intent_ok = all(
            str(row.get("intent")) == "reevaluate_registered_root"
            for row in old_root_rows) and bool(old_root_rows)
        per_iteration.append({
            "iteration": label,
            "n_declarations": len(decls),
            "n_reevaluate": sum(1 for row in decls
                                if str(row.get("intent")) == "reevaluate_registered_root"),
            "n_discover": sum(1 for row in decls
                              if str(row.get("intent")) == "discover_new_root"),
            "core_roots_required": len(core),
            "core_roots_declared_reevaluate": len(reeval),
            "missing_core_reevaluations": missing,
            "core_roots_declared_discover": discover_named_core,
            "descriptor_mismatch": descriptor_mismatch,
            "old_root_row_present": bool(old_root_rows),
            "old_root_intent_ok": old_root_intent_ok,
        })
        for name, items in (("missing_core_reevaluations", missing),
                            ("core_roots_declared_discover", discover_named_core),
                            ("descriptor_mismatch", descriptor_mismatch)):
            if items:
                problems.append({"iteration": label, "kind": name, "items": items[:20]})
        if not old_root_intent_ok:
            problems.append({"iteration": label, "kind": "old_root_intent_not_reevaluate",
                             "items": [{"n_rows": len(old_root_rows),
                                        "intents": sorted({str(row.get("intent"))
                                                           for row in old_root_rows})}]})
    return {"schema": "sitin-gate2-reevaluation-declarations/1",
            "core_roots": len(core), "per_iteration": per_iteration,
            "problems": problems, "ok": not problems,
            "note": ("挑战者必须对在席者的每个核心根发 intent="
                     "reevaluate_registered_root 且逐字带冻结描述符；"
                     "把核心根写成 discover 或漏发都会让共同根比较永远补不齐")}


def refresh_batch_declarations(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """纯数据判据：**刷新批**（P19 的真实缺口）是否已列进计划并被声明。

    生产 `_validate_refresh_roots` 对**每个受影响子场景**要求刷新批 = 4 根 H2/M2；
    整体（normal）通道同样要求 4 根（不在当前 epoch 的自然根）。两类都要在计划里看得见：

    - **整体通道**：epoch 由第一候选的自然根建立（每情景 `natural_roots[0]` 根）；
      第二候选的自然根必须**多出 ≥2 根/情景**（补 H3/H4、M3/M4）⇒ 新增 4 根 H2/M2；
    - **家族通道**：每个受影响子场景的刷新批 = `discover_new_root` 声明数 +
      运行期解析的「指定旧根」行（该根已登记但不在 epoch，生产实测把它计入刷新批）
      = 4 根 H2/M2。
    """

    iterations = list(plan.get("iterations") or ())
    problems: List[Dict[str, Any]] = []
    # —— 整体通道 ——
    normal: Dict[str, Any] = {"ok": False, "new_roots_per_mix": [],
                              "declared_roots": 0}
    if len(iterations) >= 2:
        first_roots = int(iterations[0].get("natural_roots") or 0)
        rest = [int(spec.get("natural_roots") or 0) for spec in iterations[1:]]
        delta = max(rest) - first_roots
        normal = {"ok": delta >= 2, "epoch_roots_per_mix": first_roots,
                  "challenger_roots_per_mix": max(rest) if rest else 0,
                  "delta_per_mix": delta, "new_roots_per_mix": delta * 2,
                  "declared_roots": delta * 2,
                  "basis": ("epoch 由第一候选的自然根建立；第二候选多出 {0} 根/情景 ⇒ "
                            "新增 {1} 根（要求 4 根 H2/M2）").format(delta, delta * 2)}
        if not normal["ok"]:
            problems.append({"channel": "normal", "kind": "refresh_batch_short",
                             "reading": normal})
    else:
        problems.append({"channel": "normal", "kind": "missing_second_iteration"})
    # —— 家族通道 ——
    family_by_sub: Dict[str, Dict[str, Any]] = {}
    for position, spec in enumerate(iterations):
        if position == 0:
            continue
        for sub in sorted({str(row.get("sub_scenario"))
                           for row in (spec.get("family_refresh") or ())}):
            cells: Dict[str, int] = {"H": 0, "M": 0}
            declared: List[Dict[str, Any]] = []
            for row in (spec.get("family_refresh") or ()):
                if str(row.get("sub_scenario")) != sub:
                    continue
                if (str(row.get("intent")) == "discover_new_root"
                        or row.get("root_index") is None):
                    cells[str(row.get("opponent_mix"))] = cells.get(
                        str(row.get("opponent_mix")), 0) + 1
                    declared.append({"opponent_mix": row.get("opponent_mix"),
                                     "root_index": row.get("root_index"),
                                     "intent": row.get("intent"),
                                     "resolution": ("runtime_old_root"
                                                    if row.get("root_index") is None
                                                    else "static")})
            family_by_sub["{0}|{1}".format(spec.get("iteration_label"), sub)] = {
                "counts": cells, "n_declared": len(declared), "declared": declared,
                "ok": cells == {"H": 2, "M": 2}, "required": {"H": 2, "M": 2}}
    for key, row in sorted(family_by_sub.items()):
        if not row["ok"]:
            problems.append({"channel": "family", "cell": key,
                             "kind": "refresh_batch_short", "reading": row})
    return {"schema": "sitin-gate2-refresh-batch/1",
            "normal": normal, "family": family_by_sub,
            "problems": problems, "ok": not problems,
            "note": ("刷新批（整体 4 根 + 家族每受影响子场景 4 根 H2/M2）必须在计划里"
                     "看得见：这是评审 §3 第 3 步的必要比较边，不得放进 deferred，"
                     "也不得与「探索性新根发现」混为一谈")}


def deferred_declarations(plan: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """**顺延的声明**（因封顶排不下而没排进本批）：逐格给出实例与桌数，供如实记 INSUFFICIENT。"""

    out: List[Dict[str, Any]] = []
    for spec in (plan.get("iterations") or ()):
        for row in (spec.get("deferred_declarations") or ()):
            if row.get("scheduled"):
                continue
            n_decl = int(row.get("n_declarations") or 0)
            out.append({"iteration": spec.get("iteration_label"),
                        "sub_scenario": row.get("sub_scenario"),
                        "opponent_mix": row.get("opponent_mix"),
                        "intent": row.get("intent"),
                        "n_declarations": n_decl,
                        "n_instances": n_decl * 2,       # 每声明 2 臂
                        "tables": float(row.get("tables") or 0.0),
                        "reason": row.get("reason")})
    return out


def preflight_budget(*, plan: Mapping[str, Any], run_root: Optional[Path] = None,
                     cap: Optional[float] = None,
                     authorization: Optional[Mapping[str, float]] = None
                     ) -> Dict[str, Any]:
    """开跑前预检：**先看见完整比较的所有缺边**，再看额度是否够；缺边未闭合即拒绝开跑。

    **两个口径分开表述**（2026-09-18 run4 后修订）：
    - **封顶 cap**：管**实际执行上限**（跨账户的可执行桌数）⇒ 待执行桌数 ≤ cap；
    - **授权 authorization**：管**可用额度**（按账户）⇒ 待执行(tables_full 口径) +
      失败重跑余量 ≤ 该账户授权额度。
    **仍然不许抬高封顶**：这里只是把两个口径分清，不改变 cap 的取值来源。
    """

    execution = build_execution_set(plan=plan, run_root=run_root)
    gap = comparison_gap(plan=plan, run_root=run_root) if run_root else None
    budget = plan.get("budget") or {}
    cap_default = float(budget.get("executable_planned_tables_default_cap")
                        or budget.get("executable_planned_tables") or 0.0)
    tables_due = float(execution["tables_due_excluding_failure_allowance"])
    allowance = float((execution.get("failure_allowance") or {}).get(
        "summary", {}).get("tables_due") or 0.0)
    checks: List[Dict[str, Any]] = []
    checks.append({"name": "natural_formula_matches_ruling",
                   "ok": execution["natural_tables"]["authoritative"]
                   == float(budget.get("authoritative_natural_tables")
                            or execution["natural_tables"]["authoritative"]),
                   "status": None,
                   "detail": ("自然面板权威桌数 {0}（Σ情景(该情景根数×换座×2臂×每阶段桌数)）；"
                              "计划权威值 {1}；保守上界 {2}".format(
                                  execution["natural_tables"]["authoritative"],
                                  budget.get("authoritative_natural_tables"),
                                  execution["natural_tables"][
                                      "conservative_upper_bound_if_multiply_scenarios_again"]))})
    if gap is not None:
        checks.append({"name": "complete_comparison_edges_present",
                       "ok": not gap["missing_core_edges"],
                       "detail": ("完整共同根比较缺边 {0} 条（{1} 桌）：{2}".format(
                           len(gap["missing_core_edges"]), gap["missing_core_tables"],
                           json.dumps(gap["per_candidate"], ensure_ascii=False))) + (
                               "；生产停止原因 " + ",".join(gap["production_stop"])
                               if gap["production_stop"] else "")})
        checks.append({"name": "old_root_review_and_refresh_split",
                       "ok": True,
                       "detail": ("指定旧根重评 {0} 条（缺 {1}）与新刷新根发现 {2} 条"
                                  "（缺 {3}）分开计：两类不得混成一个清单").format(
                                      gap["old_root_review"]["total"],
                                      gap["old_root_review"]["missing"],
                                      gap["refresh_root_discovery"]["total"],
                                      gap["refresh_root_discovery"]["missing"])})
    cap_value = float(cap) if cap is not None else cap_default
    missing_edges = bool(gap and gap.get("missing_core_edges"))
    # —— 两个口径分开：封顶（实际执行上限） vs 授权（可用额度） ——
    due_by_account: Dict[str, float] = {}
    for row in (execution.get("rows") or ()):
        account = KIND_ACCOUNT.get(str(row.get("kind")), "tables_full")
        due_by_account[account] = round(
            due_by_account.get(account, 0.0) + float(row.get("tables") or 0.0), 6)
    tables_full_due = float(due_by_account.get("tables_full") or 0.0)
    tables_partial_due = float(due_by_account.get("tables_partial") or 0.0)
    authorized = dict(authorization or authorized_accounts(plan))
    auth_tables_full = float(authorized.get("tables_full") or 0.0)
    # —— 刷新批齐备性（P19 的真实缺口：整体 4 根 + 家族每子场景 4 根） ——
    refresh = refresh_batch_declarations(plan)
    checks.append({
        "name": "refresh_batch_declared", "ok": bool(refresh["ok"]),
        "insufficient": False,
        "detail": ("刷新批声明（必要比较边）：整体通道 {0}；家族 {1}；问题 {2} 项 ⇒ {3}"
                   ).format(json.dumps(refresh["normal"], ensure_ascii=False),
                            json.dumps({key: row["counts"] for key, row in
                                        refresh["family"].items()}, ensure_ascii=False),
                            len(refresh["problems"]),
                            "齐备" if refresh["ok"] else "**缺声明**（刷新批交付不了）"),
        "problems": refresh["problems"][:6]})
    # —— 共同根比较的声明齐备性（纯数据；run5 的 P1 根因就在这里） ——
    reeval = required_reevaluation_declarations(plan)
    checks.append({
        "name": "required_reevaluation_declared", "ok": bool(reeval["ok"]),
        "insufficient": False,
        "detail": ("挑战者共同根比较的「指定旧根重评」声明：核心根 {0} 个；逐迭代 "
                   "{1}；问题 {2} 项 ⇒ {3}").format(
                       reeval["core_roots"],
                       json.dumps([{key: row[key] for key in
                                    ("iteration", "n_reevaluate", "n_discover",
                                     "core_roots_declared_reevaluate", "old_root_intent_ok")}
                                   for row in reeval["per_iteration"]],
                                  ensure_ascii=False),
                       len(reeval["problems"]),
                       "齐备" if reeval["ok"] else
                       "**缺声明/用途写错**（共同根比较补不齐）"),
        "problems": reeval["problems"][:10]})
    # —— 顺延的声明：已登记则按"签收缩小后的子流程"处理（**非必达**），不是未闭合缺边 ——
    # 判决口径（Lead 2026-09-18 定）：完整比较的**必达项** = 在席者与挑战者的**共同核心根边**；
    # 探索性新根发现（discover_new_root）若在 plan.iterations[].deferred_declarations 里
    # 显式登记为 scheduled=false，则它是**已登记的 scope 收缩**：记 NOT_APPLICABLE（不计入
    # 通过率、也不冒充通过），全部读数（声明/实例/桌数/逐格原因）原样保留。
    # 未登记却排不下（例如临时加了一批声明）仍按 INSUFFICIENT 拦住开跑。
    tables_per_group_guess = int((plan.get("plan_config") or {}).get(
        "tables_per_group") or 2)
    deferred = deferred_declarations(plan)
    if deferred:
        registered = all(row.get("reason") for row in deferred)
        checks.append({
            "name": "declarations_within_cap",
            "ok": True, "applicable": not registered, "insufficient": False,
            "detail": ("封顶 {0:.0f} 内排不下的声明 {1} 条（{2} 实例 / {3:.0f} 桌）：{4}"
                       "⇒ {5}").format(
                           cap_value,
                           sum(row["n_declarations"] for row in deferred),
                           sum(row["n_instances"] for row in deferred),
                           sum(row["tables"] for row in deferred),
                           json.dumps(deferred, ensure_ascii=False),
                           ("已在计划的 deferred_declarations 里**显式登记为顺延**："
                            "按裁定「可签收缩小后的子流程」处理 ⇒ NOT_APPLICABLE"
                            "（非必达；scope 收缩见 scope 字段；不抬高封顶）"
                            if registered else
                            "**未登记**的顺延 ⇒ 记 INSUFFICIENT 并拦住开跑")),
            "deferred": deferred, "registered_deferral": registered})
    checks.append({
        "name": "complete_comparison_must_pass",
        "ok": bool(reeval["ok"]) and tables_full_due <= cap_value + 1e-9,
        "insufficient": False,
        "detail": ("**完整比较的必达项**（在席者与挑战者的**共同核心根边**）：计划侧声明 {0}"
                   "（{1} 个核心根 × 2 臂 = {2} 实例 / {3} 桌）；执行侧由运行后的 "
                   "comparison_gap 复核（挑战者的 core_edges_completed 必须 = 16/16）"
                   ).format("齐备" if reeval["ok"] else "**不齐备**",
                            reeval["core_roots"], reeval["core_roots"] * 2,
                            reeval["core_roots"] * 2 * tables_per_group_guess)})
    checks.append({
        "name": "cap_covers_pending_execution",
        # 封顶是**tables_full 账户**的上限（执行器的红线就在这个账户上比）；
        # 跨账户总量（含 tables_partial 的前缀桌）另列一行，不混进这个判据。
        "ok": tables_full_due <= cap_value + 1e-9,
        "insufficient": False,
        "detail": ("**执行口径（封顶）**：待执行 tables_full {0:.0f} 桌 ≤ 封顶 {1:.0f} 桌"
                   "（跨账户总量另有 {2:.0f} 桌，含 tables_partial 前缀桌：{3:.0f} 桌）。"
                   "封顶管**实际执行上限**，不等于授权额度；抬高封顶仍然禁止").format(
                       tables_full_due, cap_value, tables_due, tables_partial_due)})
    auth_need = round(tables_full_due + allowance, 6)
    auth_ok = auth_need <= auth_tables_full + 1e-9
    checks.append({
        "name": "authorization_covers_pending_plus_allowance", "ok": auth_ok,
        "insufficient": not auth_ok,
        "detail": ("**授权口径（额度）**：待执行 tables_full {0:.0f} 桌 + 失败重跑余量 "
                   "{1:.0f} 桌 = {2:.0f} 桌 ≤ 授权 tables_full {3:.0f} 桌（余量**已含在**"
                   "授权内，不与封顶相加）。不足则记 INSUFFICIENT：缩小声称范围或另作"
                   "明确授权，不得减少正式比较配额后仍称正式通过").format(
                       tables_full_due, allowance, auth_need, auth_tables_full)})
    if missing_edges:
        cap_row = {"name": "cap_not_used_to_hide_missing_edges", "ok": False,
                   "insufficient": False,
                   "detail": ("完整比较仍有缺边（{0} 条 / {1} 桌）：此时**不允许**用"
                              "抬高封顶代替漏算修复 —— 扩额只会把同一处漏算跑得更久。"
                              "封顶 {2:.0f} 桌 / 授权 tables_full {3:.0f} 桌").format(
                                  len(gap.get("missing_core_edges") or ()),
                                  gap.get("missing_core_tables"), cap_value,
                                  auth_tables_full)}
    else:
        cap_row = {"name": "cap_not_used_to_hide_missing_edges", "ok": True,
                   "insufficient": False,
                   "detail": (("既有产物的完整比较缺边已闭合（{0} 条）：不得以抬高封顶"
                               "代替漏算修复").format(0) if gap is not None else
                              "**本次是全新运行（还没有既有产物）**：完整比较缺边在运行后"
                              "由 comparison_gap 复核（必达：挑战者 core_edges_completed = "
                              "16/16）；本判据只在有缺边时才可能为红，现在没有可读的缺边"
                              "既不是通过也不是失败")}
    checks.append(cap_row)
    for row in checks:
        row.setdefault("insufficient", False)
        row["status"] = ("FAIL" if not row["ok"] and not row["insufficient"]
                         else "INSUFFICIENT" if row["insufficient"]
                         else "PASS")
    ok = all(bool(row["ok"]) for row in checks
             if row.get("applicable", True))
    status = ("FAIL" if any(row["status"] == "FAIL" for row in checks)
              else "INSUFFICIENT" if any(row["status"] == "INSUFFICIENT"
                                         for row in checks) else "PASS")
    # scope：显式登记的顺延 = 签收范围收缩（诚实标注，不冒充完整范围）
    deferred_scope = [row for row in deferred]
    scope = ("full" if not deferred_scope else
             "shrunk:new_root_discovery(声明 {0} / 实例 {1} / 桌 {2})".format(
                 sum(row["n_declarations"] for row in deferred_scope),
                 sum(row["n_instances"] for row in deferred_scope),
                 round(sum(row["tables"] for row in deferred_scope), 3)))
    return {
        "schema": "sitin-gate2-budget-preflight/2",
        "ok": ok, "status": status, "missing_edges": missing_edges,
        "scope": scope,
        "execution_set_summary": execution["summary"],
        "tables_due": tables_due, "failure_allowance_tables": allowance,
        # 两个口径分开报：cap = 实际执行上限；authorization = 可用额度（按账户）。
        "cap": cap_value, "cap_source": ("caller" if cap is not None
                                         else "plan_executable_default"),
        "tables_due_by_account": due_by_account,
        "authorization": {"tables_full": auth_tables_full,
                          "source": ("caller" if authorization is not None
                                     else "plan.by_category（含失败重跑余量）"),
                          "pending_plus_allowance": auth_need},
        "cap_rule": ("封顶 cap 管**实际执行上限**（跨账户）；授权 authorization 管**可用"
                     "额度**（按账户）。余量相对授权判、不与封顶相加；抬高封顶仍禁止"),
        "comparison_gap": gap,
        "reevaluation_declarations": reeval,
        "refresh_batch": refresh,
        "deferred_declarations": deferred,
        "checks": checks,
        "refusal": (None if ok else
                    "拒绝开跑：完整比较仍有未闭合的边（或计数口径不符），"
                    "或额度不足以覆盖完整集合 —— 先补齐缺边/修口径/缩小声称范围，"
                    "不得以扩大封顶代替漏算修复"),
        "note": ("本预检只读计划与既有产物：0 桌、0 费用、0 模型调用"),
    }


def sample_report(*, plan_path: Path, run_roots: Sequence[Path],
                  cap: Optional[float] = None) -> Dict[str, Any]:
    """一键样例：裁定 §4.3 算例自检 + 待执行集合 + 逐运行根缺边预检（全部只读）。"""

    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    per_run: List[Dict[str, Any]] = []
    for run_root in run_roots:
        root = Path(run_root)
        entry: Dict[str, Any] = {"run_root": str(root),
                                 "layout": _layout(root)}
        if entry["layout"] == "run_root":
            entry["preflight"] = preflight_budget(plan=plan, run_root=root, cap=cap)
        else:
            # 证据副本：没有完整台账，只出**共同根覆盖**读数（不冒充计划全集 join）。
            entry["comparison_gap"] = comparison_gap(plan=plan, run_root=root)
            entry["note"] = ("证据副本形态：只有家族评价产物与状态文件，"
                            "不出「计划全集逐键对账」（那需要该次运行自己的计划与台账）")
        per_run.append(entry)
    return {"schema": "sitin-gate2-budget-sample/2",
            "reference_case": reference_case_check(),
            "plan_path": str(plan_path), "per_run": per_run,
            "note": "只读：0 桌、0 费用、0 模型调用"}


def _layout(root: Path) -> str:
    import p12_reconcile as R
    return R.layout_of(Path(root))


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="P12 预算生成器样例（只读：计划 + 既有产物）")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--run-root", action="append", default=[],
                        help="可重复：逐个出缺边读数")
    parser.add_argument("--cap", type=float, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    report = sample_report(plan_path=Path(args.plan),
                           run_roots=[Path(item) for item in args.run_root],
                           cap=args.cap)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    case = report["reference_case"]
    print("自然面板口径算例：8 根 / 4 座 / 2 臂 / 2 桌 × 2 迭代 = {0}（保守上界 {1}）"
          " ⇒ {2}".format(case["authoritative_tables"], case["conservative_upper_bound"],
                          "OK" if case["ok"] else "FAIL"))
    for entry in report["per_run"]:
        print("== {0}（形态 {1}）".format(entry["run_root"], entry["layout"]))
        if "preflight" in entry:
            pre = entry["preflight"]
            print("   状态 {0}；待执行 {1} 桌 + 失败余量 {2} 桌；封顶 {3}".format(
                pre.get("status"), pre.get("tables_due"),
                pre.get("failure_allowance_tables"), pre.get("cap")))
            for row in pre["checks"]:
                print("   [{0}] {1}｜{2}".format(row.get("status", "?"),
                                                row["name"], row["detail"][:180]))
        else:
            gap = entry["comparison_gap"]
            print("   共同根覆盖 {0}；缺边 {1} 条（{2} 桌）；生产停止 {3}".format(
                json.dumps(gap["per_candidate"], ensure_ascii=False),
                len(gap["missing_core_edges"]), gap["missing_core_tables"],
                json.dumps(gap["production_stop"], ensure_ascii=False)))
            print("   生产自报缺口（仅对照）：{0}".format(json.dumps(
                {key[:12]: len(value) for key, value in
                 (gap.get("production_reported_missing") or {}).items()},
                ensure_ascii=False)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
