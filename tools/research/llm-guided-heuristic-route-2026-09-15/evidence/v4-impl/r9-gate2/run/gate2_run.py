#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""坐隐 v4 · 关口二（无模型、封顶的真实整链验收）· **执行器**。

严格按 R8 复审 §7「关口二」的六个步骤执行，每一步都用**生产入口**，并逐步对账。
本文件**不实现任何牌局逻辑**：它只负责装配、注入、对账与报告。

## 六步 → 真实入口函数（逐条）

| 步 | 验收动作 | 真实入口（生产实现） | 命令行等价物 |
| --- | --- | --- | --- |
| 1 | 新目录/新身份/新账本/空档案；显式启用一个家族 | sitin_search.run_av_evolution(..., family_channel=, family_refresh=) → av_start_iteration（冻结身份 + 预留上界 + 落 RESERVED） | 无（CLI 缺 --family-channel/--family-refresh；见 gaps） |
| 2 | 普通条件入口生成至少一个根；该根进家族登记；第二候选补评同根 | _step_conditional → sitin_search.run_av_evaluation(prefix_source=v2_behavior) → sitin_opportunities.build_panel → generate_opportunity；登记在 _av_record_family_roots；补评在 _av_family_run_evaluation → _av_conditional_root_panel | evolve-action-value --prefix-source v2_behavior（部分等价） |
| 3 | 第一候选建立正常席与家族首席；第二候选补旧根 + 新刷新根 | _step_archive → _av_commit_archive / _av_commit_family；_step_refresh_fill → _av_family_fill → _av_commit_slots | evolve-action-value（其余参数同开轮） |
| 4 | 不同签名可占探索席 / 同签名不可重复占 / 保席不冻结探索更新 | sitin_archive.select_exploration_seat + rebase_exploration_seat；提交点 sitin_search._av_commit_slots | 无（读产物 + 确定性探针） |
| 5 | 受控中断 + 冷接手恢复 | av_fault_point("natural:<mix>:after_result_before_settle") 注入 → 冷恢复走 sitin_search.run_av_machine_resume / CLI resume（入口自算冻结清单再推进） | resume --run-dir <run> --run-id <id> |
| 6 | 原生反馈 → M1 任务包（不调模型） | _step_summarize → build_three_segment_feedback（summary/feedback.json）；M1 生成步 _av_generation_packet → pending/m1/prompt.txt（delegate 停等，exit 4） | evolve-action-value（delegate，不写 envelope） |

## 为什么每步都开新进程

- **冷接手必须是真的冷**：中断用 os._exit 硬退出（不刷 Python 层缓冲、不留内存状态），
  恢复在**另一个进程**里从盘上状态起飞；
- 每个 worker 进程进入任何真实副作用之前，av_verify_run_identity 会自行重算冻结清单
  并逐面比对（S2/P3），因此「新进程」不是形式，而是身份门槛的触发点。

## 受控中断的触发（环境变量或控制文件）

生产 av_fault_point() 默认是**空实现**，没有环境变量开关。执行器在 worker 进程内把
sitin_search.av_fault_point 换成读触发源的挂钩：

- 环境变量 GATE2_INTERRUPT_AT（点名注入点，如 natural:H:after_result_before_settle）；
- 或控制文件（--interrupt-control，内容为注入点名或 JSON {"fault_point": ...}）。

命中即写标记文件（os.write + fsync，不经 Python 缓冲）并 os._exit(97)。
这只在演练子进程里生效，**不改任何既有源码**。

## 输出

- <evidence>/run/<run-id>/gate2-run.json：机器可读（逐步结果、逐实例对账、断言、缺口）；
- <evidence>/run/<run-id>/gate2-run.md：人能读（逐步清单、逐实例对账表、失败与差异原因、
  **分支可达性与真实效果优劣分别记录**）。

## 纪律

零模型调用（生成只经 delegate 文件通道，envelope 内容来自冻结种子/确定性夹具）、
零网络；不 commit；不改既有源码与既有 evidence；解释器 .venv/bin/python；
运行根目录用 artifacts/gate2-accept/<run-id>/，绝不复用既有运行目录。
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

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

HERE = Path(__file__).resolve()
#: P12 接线模块（同目录）：状态词表、逐键对账、预算生成器、授权双形态校验。
#: 它们都只读、纯数据；本文件不再自己实现这四件事的下位判据。
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))
import p12_authorization as AUTH12       # noqa: E402
import p12_budget as BUDGET12            # noqa: E402
import p12_reconcile as REC12            # noqa: E402
import p12_status as STATUS12            # noqa: E402
#: 本文件在 <repo>/review/<实验目录>/evidence/v4-impl/r9-gate2/run/ 下。
REPO_ROOT = _PROJECT_ROOT
REVIEW_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
TOOLS_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/tools')
GATE2_DIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/v4-impl/r9-gate2')
RUN_SCHEMA = "sitin-gate2-run/1"
INTERRUPT_EXIT_CODE = 97

#: 本包默认批次/运行标签（复审 §7 关口二：新目录、新身份、新账本；不得复用历史批次）。
DEFAULT_BATCH_LABEL = "gate2-20260918"
#: 历史批次标签前缀：**显式拒绝**（前缀匹配，避免漏掉同族的其他写法）。
HISTORICAL_LABEL_PREFIXES = ("batch7", "batch-7", "rep1", "rep2", "r6", "r7", "r8")

#: 为什么授权文件里仍然保留 batch=7：
#: 生产 _step_natural 的门是
#:   authorization["authorized"] is True **and** authorization["batch"] == 7
#: （sitin_opportunities 的 v2 前缀路由同规格），也就是说 batch=7 是**平台侧的历史门值**，
#: 不是本包的运行标签，删掉它会让自然面板直接落 INPUT_GAP。
#: 本包用独立的 batch_label（默认 gate2-20260918）做运行标识：它进授权文件、运行目录、
#: 报告与全部产物，历史标签一律拒绝——两者不得混为一谈。


def resolve_cap(*, requested: Optional[float], cap_default: float) -> float:
    """解析 tables_full 封顶：缺省 = 计划可执行桌数；**调用方不得抬高上限**。

    为什么拒绝更大的值：复审 §7 关口二要求"封顶"；接受一个更大的上限等于在
    运行前就把封顶取消，后面的红线检查再准也没有意义。要更大规模必须先改计划
    参数并重跑 gate2_plan.py（计划变了，身份也跟着变）。
    """

    if requested is None:
        return float(cap_default)
    value = float(requested)
    if value > float(cap_default) + 1e-9:
        raise SystemExit(
            "拒绝 --max-tables {0:.1f} > 计划可执行桌数 {1:.1f}：封顶不得高于计划"
            "（复审 §7 关口二要求「封顶」；放大上限等于取消封顶）。"
            "如需更大规模，请先改计划参数并重跑 gate2_plan.py。".format(
                value, float(cap_default)))
    if value < 0:
        raise SystemExit("--max-tables 不能为负：{0:.1f}".format(value))
    return value


def validate_batch_label(label: Any) -> str:
    """批次/运行标签校验：非空、无路径分隔符/空白、且**不得**是历史批次标签。"""

    text = str(label or "").strip()
    if not text:
        raise SystemExit("--batch-label 不能为空（它进授权文件、运行目录、报告与全部产物）")
    lowered = text.lower()
    for prefix in HISTORICAL_LABEL_PREFIXES:
        if lowered == prefix or lowered.startswith(prefix):
            raise SystemExit(
                "拒绝历史批次标签 {0!r}（命中 {1!r}）：复审 §7 关口二要求"
                "新目录、新身份、新账本，不得复用 rep1/rep2/batch7b 等历史证据；"
                "请用本包默认标签 {2} 或另起一个未使用过的标签".format(
                    text, prefix, DEFAULT_BATCH_LABEL))
    if any(char in text for char in ("/", "\\", "\0", " ", "\n", "\t")):
        raise SystemExit("批次标签不能含路径分隔符/空白：{0!r}".format(text))
    return text


# ===========================================================================
# 授权派生与开跑前预检（preflight）
#
# 为什么必须有这一层：2026-09-18 的全量六步跑到第 3 步才炸在
# LedgerOverAuthorized（prefix_generation 授权 4.0，已被 iter1 的
# 「1 次条件评价 + 3 次家族根评价」用光）。**每次 run_av_evaluation 调用都各占
# 1.0 prefix_generation 与 ≤ attempts_cap 桌 tables_partial**，而旧派生只按
# 「迭代数 + 2」拍了一个 4.0 —— 这类错误本该在开跑前被挡住。
# 现在：逐账户需求**从计划 by_category 直接映射**（缺类目即报错，不静默丢弃），
# 并在写任何运行目录之前逐账户核对。
# ===========================================================================

#: 计划类别 → 账本账户（显式映射；**每个计划类别都必须在这里出现**）。
#: 一个类别可以映射到多个账户（family_fill 既占 tables_full，也占
#: tables_partial 与 prefix_generation），因此用「账户 → 类目」表示，反向检查用。
ACCOUNT_CATEGORY_MAP: Dict[str, Tuple[str, ...]] = {
    "tables_full": ("natural_full", "conditional_full", "family_fill",
                    "failure_rerun_allowance"),
    "tables_partial": ("conditional_prefix_partial", "family_fill"),
    "prefix_generation": ("conditional_prefix_partial", "family_fill"),
    "tokens_input": (),
    "tokens_output": (),
    "confirm_reserved": (),
}
#: 不产生任何账目需求、但必须显式登记为"已覆盖"的类别（0 桌也要说清楚）。
ZERO_DEMAND_CATEGORIES: Tuple[str, ...] = ("interrupt_drill",)


def derive_accounts(plan: Mapping[str, Any],
                    prod: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """逐账户需求派生：**从计划 by_category 直接映射**，每一项都带口径。

    口径（全部可从计划或生产常量核对，不含拍脑袋的常数）：

    - `tables_full` = 四类完整桌的计划桌数之和（含失败重跑余量）；
      在途上界（自然面板单情景预留 = 每情景根×座位×2 臂×每阶段桌数）另算并验证被覆盖；
    - `tables_partial` = 条件评价的前缀上界（每次 ≤ attempts_cap 桌）× 条件评价次数
      + 家族根评价每次 1 桌（生产 `_av_conditional_root_panel` 对显式根**只跑一次**）
      + 单次评价在途上界 + 失败重跑同源余量；
    - `prefix_generation` = **每次 run_av_evaluation 调用各 1.0**：
      条件评价次数 + 家族根评价次数 + 在途 1 + 失败重跑同源余量；
    - `tokens_*` = 0（零模型调用）；`confirm_reserved` = 0（确认账本包不动用）。
    """

    budget = plan.get("budget") or {}
    cats = {str(row.get("category")): row for row in (budget.get("by_category") or ())}
    cfg = ((plan.get("frozen_inputs") or {}).get("family_config") or {})
    pconf = plan.get("plan_config") or {}
    iterations = len(plan.get("iterations") or ())
    rerun_roots = int(pconf.get("rerun_roots") or 0)
    attempts_cap = int(cfg.get("prefix_attempts_cap") or 8)
    n_cond = iterations                       # 每次迭代一次条件评价
    n_family = int((cats.get("family_fill") or {}).get("n_instances") or 0)
    n_eval = n_cond + n_family
    # 家族补根**按轮重试**（_av_family_fill 每轮由仍未物化的声明驱动）：
    # 每一轮都会为每个仍未补上的根**各再来一次评价** ⇒ 每次评价各占 1.0
    # prefix_generation 与 1 桌 tables_partial（2026-09-18 run2 实测：8 条声明根
    # 第一轮全评一遍、第二轮重试第一项时撞 TaskAlreadySettled）。
    # 轮数上界取生产常量 AV_REFRESH_FILL_MAX_ROUNDS；取不到时按 6 记并标注来源。
    fill_rounds_max = 6
    fill_rounds_source = "fallback:6（未装载生产常量）"
    if prod and prod.get("search") is not None:
        raw = getattr(prod["search"], "AV_REFRESH_FILL_MAX_ROUNDS", None)
        if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
            fill_rounds_max = int(raw)
            fill_rounds_source = ("production:"
                                  "sitin_search.AV_REFRESH_FILL_MAX_ROUNDS")
    n_family_attempts = n_family * fill_rounds_max
    natural_roots = int(pconf.get("natural_roots") or 0)
    natural_seats = int(pconf.get("natural_seats") or 0)
    tables_per_group = int(pconf.get("tables_per_group") or 0)
    # 自然面板按**情景逐个**预留：单次在途上界 = 根 × 座位 × 2 臂 × 每阶段桌数。
    natural_inflight = float(natural_roots * natural_seats * 2 * tables_per_group)

    def _tables(category: str) -> float:
        return float((cats.get(category) or {}).get("planned_tables") or 0.0)

    def _instances(category: str) -> int:
        return int((cats.get(category) or {}).get("n_instances") or 0)

    mapping_rows: List[Dict[str, Any]] = []
    for account, names in ACCOUNT_CATEGORY_MAP.items():
        for name in names:
            row = cats.get(name)
            mapping_rows.append({
                "category": name,
                "account": account,
                "present_in_plan": row is not None,
                "n_instances": _instances(name),
                "planned_tables": _tables(name),
            })
    for name in ZERO_DEMAND_CATEGORIES:
        mapping_rows.append({
            "category": name, "account": "(无账目需求)",
            "present_in_plan": name in cats, "n_instances": _instances(name),
            "planned_tables": _tables(name)})

    # —— 未映射的类目：显式报错，绝不静默丢弃 ——
    mapped = {name for names in ACCOUNT_CATEGORY_MAP.values() for name in names}
    mapped |= set(ZERO_DEMAND_CATEGORIES)
    unmapped = sorted(set(cats) - mapped)
    if unmapped:
        raise SystemExit(
            "计划里有类目未映射到账本账户：{0}。请在 ACCOUNT_CATEGORY_MAP 里显式登记"
            "它对应的账户（或登记为 0 需求），否则额度会静默少算。".format(unmapped))

    tables_full_terms = [
        {"category": "natural_full", "tables": _tables("natural_full"),
         "basis": "计划桌数全额（合法计划类目）"},
        {"category": "conditional_full", "tables": _tables("conditional_full"),
         "basis": "计划桌数全额（截取后续打）"},
        {"category": "family_fill", "tables": _tables("family_fill"),
         "basis": "计划桌数全额（声明根命中时的上界：每根 2 臂×每阶段桌数）"},
        {"category": "failure_rerun_allowance",
         "tables": _tables("failure_rerun_allowance"),
         "basis": "失败整根重跑余量（**已含在 tables_full 授权内**）"},
    ]
    tables_full_demand = sum(term["tables"] for term in tables_full_terms)

    tables_partial_terms = [
        {"source": "conditional_prefix_partial",
         "value": float(n_cond * attempts_cap),
         "basis": "条件评价 {0} 次 × 前缀上界 {1} 桌/次（attempts_cap）".format(
             n_cond, attempts_cap)},
        {"source": "family_fill",
         "value": float(n_family_attempts),
         "basis": ("家族根评价 {0} 次 × 最多 {1} 轮重试 × 1 桌"
                   "（显式根只跑一次前缀；轮数上界 {2}）").format(
                       n_family, fill_rounds_max, fill_rounds_source)},
        {"source": "in_flight_headroom", "value": float(attempts_cap),
         "basis": "单次评价的在途预留上界（预留 8 后才会结算，必须留得下）"},
        {"source": "rerun_slack", "value": float(rerun_roots),
         "basis": "失败重跑同源余量：{0} 整根 × 1 桌前缀".format(rerun_roots)},
    ]
    tables_partial_demand = sum(term["value"] for term in tables_partial_terms)

    prefix_terms = [
        {"source": "conditional_prefix_partial", "value": float(n_cond),
         "basis": "条件评价 {0} 次 × 每次 1.0（run_av_evaluation 固定预留）".format(n_cond)},
        {"source": "family_fill", "value": float(n_family_attempts),
         "basis": ("家族根评价 {0} 次 × 最多 {1} 轮重试 × 每次 1.0"
                   "（同一条 run_av_evaluation；轮数上界 {2}）").format(
                       n_family, fill_rounds_max, fill_rounds_source)},
        {"source": "in_flight_headroom", "value": 1.0,
         "basis": "单次评价的在途预留（1.0）"},
        {"source": "rerun_slack", "value": float(rerun_roots),
         "basis": "失败重跑同源余量：{0} 整根 × 1 次前缀生成".format(rerun_roots)},
    ]
    prefix_demand = sum(term["value"] for term in prefix_terms)

    tokens = {"tokens_input": 0.0, "tokens_output": 0.0, "confirm_reserved": 0.0}
    accounts = {
        "tables_full": tables_full_demand,
        "tables_partial": tables_partial_demand,
        "prefix_generation": prefix_demand,
        **tokens,
    }

    cross_checks = [
        {"name": "tables_full 已含失败重跑余量",
         "ok": tables_full_terms[-1]["tables"] > 0,
         "reading": ("余量 {0:.0f} 桌在 tables_full 授权内；"
                     "tables_full 口径的可执行 = {1:.0f}，"
                     "计划可执行 {2:.0f} 是**跨账户**总量 = tables_full {1:.0f} + "
                     "tables_partial {3:.0f}").format(
                         _tables("failure_rerun_allowance"),
                         tables_full_demand - _tables("failure_rerun_allowance"),
                         float(budget.get("executable_planned_tables") or 0.0),
                         _tables("conditional_prefix_partial"))},
        {"name": "tables_full 在途上界被授权覆盖",
         "ok": tables_full_demand >= natural_inflight,
         "reading": "自然面板单情景在途预留 {0:.0f} 桌 ≤ 授权 {1:.0f}".format(
             natural_inflight, tables_full_demand)},
        {"name": "两轮迭代累计（不是单次迭代）",
         "ok": n_cond == iterations and n_family >= iterations,
         "reading": ("条件评价 {0} 次（= 迭代数 {1}）、家族根评价 {2} 次（按两候选累计）"
                     ).format(n_cond, iterations, n_family)},
        {"name": "中断演练与冷恢复路径",
         "ok": "interrupt_drill" in cats,
         "reading": ("计划已登记中断演练类目；演练本身**额外需求 0 桌**"
                     "（结果已在盘上 → 采用并结算）；冷恢复重跑的是同一批实例，"
                     "其额度已在上面的累计里，报告用「中断前后 tables_full 增量 = "
                     "被中断情景实际执行数」实测核对")},
        {"name": "每次评价各占 1.0 prefix_generation",
         "ok": prefix_demand >= n_eval,
         "reading": "评价 {0} 次（条件 {1} + 家族 {2}）⇒ prefix_generation 需求 ≥ {0}".format(
             n_eval, n_cond, n_family)},
    ]
    return {
        "schema": "sitin-gate2-account-derivation/1",
        "iterations": iterations, "n_conditional_evaluations": n_cond,
        "n_family_evaluations": n_family, "n_evaluations": n_eval,
        "attempts_cap": attempts_cap, "rerun_roots": rerun_roots,
        "fill_rounds_max": fill_rounds_max, "fill_rounds_source": fill_rounds_source,
        "n_family_attempts_max": n_family_attempts,
        "natural_inflight_tables": natural_inflight,
        "mapping_table": mapping_rows,
        "account_terms": {"tables_full": tables_full_terms,
                          "tables_partial": tables_partial_terms,
                          "prefix_generation": prefix_terms},
        "accounts": accounts,
        "cross_checks": cross_checks,
        "note": ("额度是**上限**不是支出：未使用的授权不会被消耗（账本按实际结算）。"
                 "上界口径宁可宽一点，也不要在跑到一半时被 LedgerOverAuthorized 拦住。"),
    }


def preflight(plan: Mapping[str, Any], *, supplied: Optional[Mapping[str, Any]] = None,
              prod: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """开跑前预检：派生账户需求 → 逐账户核对 → 不满足即拒绝开跑（点名账户与差额）。

    **本函数必须在写任何运行目录之前调用**：2026-09-18 的全量六步之所以跑到第 3 步
    才炸，就是因为没有这一步。`supplied` 给出外部授权额度时，逐账户核对
    「需求 ≤ 授权」，不足即 SystemExit（点名账户、需求、授权、差额）。
    """

    # supplied 允许两种形状：直接是账户额度映射，或整份授权令牌（额度在 "budgets" 下）。
    # 后者曾被漏解，导致 main 的第一道预检把"外部授权不足"看成"未提供授权"而放行，
    # 直到 Gate2Runner 构造时才拒绝（虽然运行目录仍未创建，但会留下误导性的 preflight.json）。
    if isinstance(supplied, Mapping) and isinstance(supplied.get("budgets"), Mapping):
        supplied = dict(supplied.get("budgets") or {})
    derivation = derive_accounts(plan, prod=prod)
    verdicts: List[Dict[str, Any]] = []
    problems: List[Dict[str, Any]] = []
    for account, demand in sorted(derivation["accounts"].items()):
        limit = None
        if supplied is not None:
            try:
                limit = float(dict(supplied).get(account))
            except (TypeError, ValueError):
                limit = None
        if limit is None:
            verdicts.append({"account": account, "demand": float(demand),
                             "authorized": None, "verdict": "self_derived",
                             "note": "未提供外部授权：本包按派生需求写授权"})
            continue
        ok = float(demand) <= limit + 1e-9
        verdicts.append({"account": account, "demand": float(demand),
                         "authorized": limit,
                         "verdict": "within_authorization" if ok else "over_authorization",
                         "shortfall": (0.0 if ok else round(float(demand) - limit, 6))})
        if not ok:
            problems.append(verdicts[-1])
    crossed = [row for row in derivation["cross_checks"] if not row["ok"]]
    result = {
        "schema": "sitin-gate2-preflight/1",
        "at_utc": utc_now(),
        "batch_label": plan.get("batch_label"),
        "derivation": derivation,
        "verdicts": verdicts,
        "cross_checks": derivation["cross_checks"],
        "ok": not problems and not crossed,
        "problems": problems,
        "failed_cross_checks": crossed,
    }
    if problems or crossed:
        detail = "；".join(
            "{0}: 需求 {1:.1f} > 授权 {2:.1f}（差 {3:.1f}）".format(
                row["account"], row["demand"], row["authorized"], row["shortfall"])
            for row in problems) or "；".join(
                "{0}: {1}".format(row["name"], row["reading"]) for row in crossed)
        raise SystemExit(
            "开跑前预检不通过，拒绝创建任何运行目录：{0}。"
            "请修正计划参数或授权额度后重跑（不要靠抬高 --max-tables 绕过）。".format(detail))
    return result


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, payload: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                    encoding="utf-8")
    return path


def read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sha256_file(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _git(*args: str) -> Optional[str]:
    try:
        out = subprocess.run(("git",) + args, cwd=str(REPO_ROOT), check=False,
                             capture_output=True, text=True)
    except OSError:
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def capture_tree_state() -> Dict[str, Any]:
    """运行前的树状态（candidate_id 随树内容变化，取证前提）。"""

    files: Dict[str, Optional[str]] = {}
    for path in (sorted(TOOLS_DIR.glob("*.py"))
                 + sorted((_project_file(_PROJECT_ROOT, REPO_ROOT / "src/hangma_bot")).rglob("*.py"))):
        files[str(path.relative_to(REPO_ROOT))] = sha256_file(path)
    for name in ("contracts/group-dev-v1.json", "contracts/action-value-v1.json"):
        path = _project_file(_PROJECT_ROOT, REVIEW_DIR / name)
        files["review/llm-guided-heuristic-route-2026-09-15/" + name] = sha256_file(path)
    return {
        "git_head": _git("rev-parse", "HEAD"),
        "git_dirty_paths": sorted(
            line for line in (_git("status", "--porcelain") or "").splitlines() if line),
        "n_files": len(files),
        "files_sha256": files,
        "tree_digest": hashlib.sha256(json.dumps(
            files, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "captured_at_utc": utc_now(),
    }


def load_production() -> Dict[str, Any]:
    """装载生产模块（worker 与编排都要用；tools 目录进 sys.path）。"""

    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    import sitin_search as search  # noqa: E402
    import sitin_archive as archive  # noqa: E402
    import sitin_generate as generate  # noqa: E402
    return {"search": search, "archive": archive, "generate": generate}


# ===========================================================================
# 受控中断：把生产 av_fault_point 换成读环境变量/控制文件的挂钩
# ===========================================================================


def _interrupt_target(spec: Mapping[str, Any]) -> Optional[str]:
    env = str(os.environ.get("GATE2_INTERRUPT_AT") or "").strip()
    if env:
        return env
    control = spec.get("interrupt_control")
    if control and Path(control).is_file():
        raw = Path(control).read_text(encoding="utf-8").strip()
        if raw.startswith("{"):
            payload = json.loads(raw)
            return str(payload.get("fault_point") or "").strip() or None
        return raw or None
    explicit = str(spec.get("interrupt_at") or "").strip()
    return explicit or None


def install_interrupt_hook(search: Any, spec: Mapping[str, Any]) -> Optional[str]:
    """安装中断挂钩；返回本次生效的注入点名（None = 不注入）。"""

    target = _interrupt_target(spec)
    if not target:
        return None
    marker = str(spec.get("interrupt_marker") or "")
    exit_code = int(spec.get("interrupt_exit_code") or INTERRUPT_EXIT_CODE)

    def hook(name: str, **fields: Any) -> None:
        if str(name) != target:
            return
        payload = {"fault_point": str(name), "step_id": fields.get("step_id"),
                   "mix": fields.get("mix"), "pid": os.getpid(),
                   "run_root": spec.get("run_root"), "at_utc": utc_now(),
                   "note": ("结果已落盘、结算/状态尚未完成处的受控中断；"
                            "os._exit 硬退出以模拟真实崩溃")}
        if marker:
            path = Path(marker)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            try:
                os.write(fd, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)
        os._exit(exit_code)

    search.av_fault_point = hook
    return target


# ===========================================================================
# worker：在独立进程里执行一步真实调用
# ===========================================================================


def _worker_write(spec: Mapping[str, Any], payload: Dict[str, Any]) -> None:
    out = spec.get("worker_result")
    if out:
        write_json(Path(out), payload)


def run_worker(spec: Mapping[str, Any]) -> int:
    """worker 进程主入口：装载生产模块 → 装挂钩 → 执行一步 → 落结果。"""

    action = str(spec.get("action"))
    prod = load_production()
    search = prod["search"]
    started = time.monotonic()
    payload: Dict[str, Any] = {"action": action, "ok": False, "pid": os.getpid(),
                               "started_at_utc": utc_now()}
    try:
        target = install_interrupt_hook(search, spec)
        payload["interrupt_target"] = target
        if action == "evolve":
            authorization = (read_json(Path(spec["authorization_path"]))
                             if spec.get("authorization_path") else None)
            evolve = dict(spec.get("evolve") or {})
            result = search.run_av_evolution(
                Path(spec["run_root"]),
                generation_mode=evolve.get("generation_mode", "delegate"),
                seed_name=evolve.get("seed_name", "efficiency_seed"),
                predicate=evolve.get("predicate", "branch_open"),
                opponent=evolve.get("opponent", "H"),
                authorization=authorization,
                reply_envelope=(Path(spec["reply_envelope"])
                                if spec.get("reply_envelope") else None),
                natural_roots=int(evolve.get("natural_roots", 1)),
                natural_seats=int(evolve.get("natural_seats", 1)),
                prefix_source=evolve.get("prefix_source", "v2_behavior"),
                panel_seed=int(evolve.get("panel_seed") or 0) or 20260916,
                stop_after=evolve.get("stop_after"),
                archive_path=(Path(spec["archive_path"])
                              if spec.get("archive_path") else None),
                family_channel=evolve.get("family_channel"),
                family_refresh=list(evolve.get("family_refresh") or ()))
            payload.update({"ok": True, "result": _jsonable(result),
                            "waiting_for_reply": bool(result.get("waiting_for_reply")),
                            "terminal": result.get("terminal"),
                            "status": (result.get("state") or {}).get("status"),
                            "stopped_after": result.get("stopped_after"),
                            "refused": result.get("refused")})
        elif action == "resume":
            authorization = (read_json(Path(spec["authorization_path"]))
                             if spec.get("authorization_path") else None)
            result = search.run_av_machine_resume(
                Path(spec["run_root"]), run_id=str(spec["run_id"]),
                identity=(read_json(Path(spec["identity_path"]))
                          if spec.get("identity_path") else None),
                authorization=authorization)
            payload.update({"ok": bool(result.get("ok")),
                            "result": _jsonable(result),
                            "refused": result.get("refused"),
                            "identity_refused": result.get("identity_refused"),
                            "terminal": result.get("terminal"),
                            "status": result.get("status")})
        elif action == "probe_same_signature":
            payload.update(_probe_same_signature(prod, spec))
        else:
            payload.update({"ok": False,
                            "error": "未知 worker action {0!r}".format(action)})
    except SystemExit as error:  # 生产入口用 SystemExit 表达授权缺口
        payload.update({"ok": False, "error": "SystemExit: {0}".format(error),
                        "system_exit": True})
    except BaseException as error:  # noqa: BLE001 - worker 必须落盘失败原因
        payload.update({"ok": False,
                        "error": "{0}: {1}".format(type(error).__name__, error)})
    payload["elapsed_sec"] = round(time.monotonic() - started, 3)
    payload["finished_at_utc"] = utc_now()
    _worker_write(spec, payload)
    return 0 if payload.get("ok") else 3


def _jsonable(value: Any) -> Any:
    """把结果里的 Path 等不可序列化对象转成字符串（只做投影，不改语义）。"""

    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _probe_same_signature(prod: Mapping[str, Any],
                          spec: Mapping[str, Any]) -> Dict[str, Any]:
    """确定性可达性证明：相同行为签名**不能**重复占探索席。

    为什么必须单独证明：真实链里两个候选的签名不同（这正是「不同签名可占探索席」
    那一半），同签名分支在真实运行中**不可达**。这里直接喂两个同签名的合成条目给
    **生产选择器** sitin_archive.select_exploration_seat，断言孪生被排除并登记
    （excluded_behavior_duplicates），而不是改真实结果或放宽断言。
    """

    archive = prod["archive"]
    # 签名形状按生产口径：behavior_signature_digest 只读 windows 的
    # (window_id, action_key, missing)，不重算分数（R8 §5 M2 反例的纪律）。
    signature_a = {"windows": [{"window_id": "win-1", "action_key": "discard:1w",
                                "missing": False}]}
    signature_b = {"windows": [{"window_id": "win-1", "action_key": "hu",
                                "missing": False}]}
    incumbent = "incumbent-fixture-0001"
    twin = "twin-fixture-0002"
    other = "other-fixture-0003"

    def entry(cid: str, sig: Mapping[str, Any]) -> Dict[str, Any]:
        # 资格口径来自 _slot_eligibility：safety.status 必须 PASS、非 V2 基线、
        # 无未修复故障；选择排序用的代价走确定性口径 cost.budget_units。
        return {"candidate_id": cid, "kind": "candidate",
                "safety": {"status": "PASS", "bound_candidate_id": cid},
                "effect_failure_unresolved": False,
                "behavior_signature": dict(sig),
                "cost": {"budget_units": 8.0, "elapsed_ms": 1000.0},
                "root_expected": {"arms": ["baseline", "candidate"],
                                  "tables_per_arm": 2}}

    entries = [entry(incumbent, signature_a), entry(twin, signature_a),
               entry(other, signature_b)]
    committed: Dict[str, List[str]] = {"overall": [incumbent], "exploration": []}
    for family in archive.FAMILIES:
        committed[family] = []
    selection = archive.select_exploration_seat(entries, committed_seats=committed)
    seated = list(selection.get("slots") or ())
    report = dict(selection.get("report") or {})
    excluded = dict(report.get("excluded_behavior_duplicates") or ())

    signatures_by_cid = {str(item.get("candidate_id")): sig for item, sig in (
        (entry(incumbent, signature_a), signature_a),
        (entry(twin, signature_a), signature_a),
        (entry(other, signature_b), signature_b),
        (entry("twin-fixture-0004", signature_a), signature_a),
        (entry("distinct-fixture-0005", signature_a), signature_a))}

    def _signature_of(cid: str) -> Optional[str]:
        sig = signatures_by_cid.get(str(cid))
        return (archive.behavior_signature_digest(sig) if sig is not None else None)

    # —— A4r 两侧构造（原文：`每选入一个候选，排除其同行为候选并记录重复来源；
    #    无第二种行为就空第二席`）——
    # ① 候选池里**只剩两条同签名**（都在席外）⇒ 第二探索席必须为空（最多 1 席）。
    twin_second = "twin-fixture-0004"
    selection_twins = archive.select_exploration_seat(
        [entry(twin, signature_a), entry(twin_second, signature_a)],
        committed_seats=committed)
    seated_twins = list(selection_twins.get("slots") or ())
    # ② 候选池里有**两条异签名**（都在席外）⇒ 两席都要占，且两席签名互不相同。
    distinct_second = "distinct-fixture-0005"
    selection_distinct = archive.select_exploration_seat(
        [entry(other, signature_b), entry(distinct_second, signature_a)],
        committed_seats=committed)
    seated_distinct = list(selection_distinct.get("slots") or ())
    distinct_signatures = [_signature_of(cid) for cid in seated_distinct]
    return {
        "ok": True,
        "probe": "same_signature_duplicate_cannot_take_exploration_seat",
        "seated_exploration": seated,
        "excluded_behavior_duplicates": sorted(excluded),
        "excluded_seated": list(report.get("excluded_seated") or ()),
        "slot_selection_version": report.get("slot_selection_version"),
        "twin_excluded": twin in excluded,
        "twin_not_seated": twin not in seated,
        "different_signature_seated": other in seated,
        # A4r 两侧读数
        "twins_only_seated": seated_twins,
        "twins_only_second_seat_empty": len(seated_twins) <= 1,
        "distinct_pair_seated": seated_distinct,
        "distinct_pair_seats_both_filled": len(seated_distinct) == 2,
        "distinct_pair_signatures_unique": (
            len(distinct_signatures) == len({sig for sig in distinct_signatures
                                             if sig})),
        "note": ("确定性可达性证明（合成条目 + 生产选择器）；不是真实效果证据，"
                 "也不改动任何真实结果"),
    }


# ===========================================================================
# 产物读取器（对账用；全部只读）
# ===========================================================================


def iter_dirs(run_root: Path) -> List[Path]:
    iterations = Path(run_root) / "iterations"
    return sorted(iterations.glob("iter-*")) if iterations.is_dir() else []


def latest_state_path(run_root: Path) -> Optional[Path]:
    for iter_dir in reversed(iter_dirs(run_root)):
        path = iter_dir / "state.json"
        if path.is_file():
            return path
    return None


def read_state(path: Path) -> Dict[str, Any]:
    return read_json(Path(path)) or {}


def read_ledger(run_root: Path) -> Dict[str, Any]:
    return read_json(Path(run_root) / "av-ledger.json") or {}


def ledger_rows(ledger: Mapping[str, Any], *, step_prefix: str = "",
                account: Optional[str] = None) -> List[Dict[str, Any]]:
    rows = []
    for row in (ledger.get("reservations") or ()):
        if step_prefix and not str(row.get("step_id") or "").startswith(step_prefix):
            continue
        if account and str(row.get("account")) != account:
            continue
        rows.append(dict(row))
    return rows


def ledger_readings(ledger: Mapping[str, Any], *,
                    account: str = "tables_full") -> Dict[str, Any]:
    """账本**两个口径分开**读：`settled`（已结算）与 `inflight`（在途预留）。

    为什么必须分开（2026-09-18 run4 实测的口径缺陷）：
    - 生产 `ActionValueLedger._reserve_locked` 在**预留时**就写 `charged = amount`
      （保守计费：在途那笔也带金额）；
    - 生产 `ActionValueLedger.spent()` 的口径是"已结算 **+** 在途预留"（授权校验用，
      见 `reserve` 里的 `committed = self.spent(account)`）；
    - 旧 `ledger_spent()` 对**所有**行求和 ⇒ 它读到的其实是"已结算 + 在途"，
      却被当作"已结算"，随后再 `+ inflight` ⇒ **同一笔在途被计两次**
      （run4：真实已结算 104 + 在途 32 → 旧口径报 settled 136，再 +32 ⇒ 虚高 32）。

    本函数把两口径显式分开，并保留 `committed`（= settled + inflight，生产授权口径）
    供对拍。**封顶红线只用 settled + inflight（各一次）**。
    """

    settled = 0.0
    inflight = 0.0
    superseded_settled = 0.0
    settled_rows: List[Dict[str, Any]] = []
    inflight_rows: List[Dict[str, Any]] = []
    for row in (ledger.get("reservations") or ()):
        if str(row.get("account")) != str(account):
            continue
        status = str(row.get("status"))
        charged = float(row.get("charged") or 0.0)
        if status == "settled":
            settled = round(settled + charged, 6)
            if row.get("superseded"):
                superseded_settled = round(superseded_settled + charged, 6)
            settled_rows.append(dict(row))
        elif status == "reserved":
            inflight = round(inflight + float(row.get("amount") or charged or 0.0), 6)
            inflight_rows.append(dict(row))
    return {"account": account, "settled": settled, "inflight": inflight,
            "committed": round(settled + inflight, 6),
            "superseded_settled": superseded_settled,
            "settled_rows": settled_rows, "inflight_rows": inflight_rows,
            "note": ("settled=已结算（含失败重试保留的 superseded 费用）；"
                     "inflight=在途预留；committed=生产授权口径（两者之和）；"
                     "封顶红线 = settled + inflight + 本次新增计划，**不得**把在途加两次")}


def ledger_spent(ledger: Mapping[str, Any]) -> Dict[str, float]:
    """**已结算**（settled）读数（按账户）。

    旧实现对**所有**行求和（等价于生产授权口径"已结算+在途"）；2026-09-18 起改为
    **只算已结算**，在途单列 `ledger_readings()`：两个口径混在一起正是 run4 假红线的成因。
    """

    out: Dict[str, float] = {}
    for row in (ledger.get("reservations") or ()):
        if str(row.get("status")) != "settled":
            continue
        account = str(row.get("account"))
        out[account] = round(out.get(account, 0.0) + float(row.get("charged") or 0.0), 6)
    return out


def ledger_committed(ledger: Mapping[str, Any]) -> Dict[str, float]:
    """**已结算 + 在途**（生产授权口径 `ActionValueLedger.spent()` 的同口径读数）。"""

    out: Dict[str, float] = {}
    for account in ("tables_full", "tables_partial", "prefix_generation",
                    "tokens_input", "tokens_output", "confirm_reserved"):
        out[account] = ledger_readings(ledger, account=account)["committed"]
    return out


def redline_accounting(*, ledger: Mapping[str, Any], planned: float, cap: float,
                       scope_channels: Sequence[str] = (),
                       scope_candidate12: str = "",
                       adoptable_steps: Optional[Mapping[str, bool]] = None,
                       account: str = "tables_full") -> Dict[str, Any]:
    """封顶红线的**纯函数**口径（可离线重放；不读盘、不写盘）。

    规则（修后的口径）：

    1. `settled` = 已结算行之和；`inflight` = 在途预留之和 —— **各计一次**，不互加两次；
    2. 本次调用的 `planned` 是计划量；若其中一部分工作**已经完成且可核**
       （非 superseded 的已结算行）或**在途且盘上有结果证据**（会被"采用并结算"），
       这部分**不再新增 planned**（`overlap` 扣除）；
    3. `sum = settled + inflight + max(0, planned − overlap)`；`sum > cap` 即 exceeds_cap；
    4. 同时记录 `worst_case_sum = settled + inflight + planned`：
       当它超封顶而 `sum` 不超时，说明本判定**依赖"采用盘上结果"**；
       此时要求每个被扣减的在途步都有 `adoptable_steps[step_id] is True` 的证据，
       否则**不许扣减**（红线不得被改废）。
    """

    readings = ledger_readings(ledger, account=account)
    adoptable_steps = dict(adoptable_steps or {})
    overlap_rows: List[Dict[str, Any]] = []
    overlap = 0.0
    for row in readings["settled_rows"]:
        if row.get("superseded"):
            continue                     # 失败重试成本：已计入 settled，**不**抵扣计划量
        if not _step_in_scope(row.get("step_id"), scope_channels, scope_candidate12):
            continue
        charged = float(row.get("charged") or 0.0)
        overlap = round(overlap + charged, 6)
        overlap_rows.append({"step_id": row.get("step_id"), "status": "settled",
                             "reason": "已完成且可核（非 superseded）⇒ 本次不新增计划量",
                             "charged": charged})
    for row in readings["inflight_rows"]:
        step_id = str(row.get("step_id"))
        if not _step_in_scope(step_id, scope_channels, scope_candidate12):
            continue
        if not adoptable_steps.get(step_id):
            continue                     # 无盘上证据 ⇒ 可能重跑 ⇒ 不得抵扣
        amount = float(row.get("amount") or 0.0)
        overlap = round(overlap + amount, 6)
        overlap_rows.append({"step_id": step_id, "status": "reserved",
                             "reason": "在途且结果已在盘上 ⇒ 恢复按「采用并结算」转已结算，"
                                       "不新增计划量",
                             "charged": amount})
    planned_new = round(max(0.0, float(planned) - overlap), 6)
    settled = readings["settled"]
    inflight = readings["inflight"]
    total = round(settled + inflight + planned_new, 6)
    worst = round(settled + inflight + float(planned), 6)
    verdict = "within_cap" if total <= float(cap) + 1e-9 else "exceeds_cap"
    if verdict == "within_cap" and worst > float(cap) + 1e-9 and overlap > 0:
        verdict = "within_cap_with_adoption"
    return {"settled": settled, "inflight": inflight,
            "committed": readings["committed"],
            "superseded_settled": readings["superseded_settled"],
            "planned_this_call": round(float(planned), 6),
            "overlap_deducted": overlap, "overlap_rows": overlap_rows,
            "planned_new": planned_new, "sum": total, "worst_case_sum": worst,
            "worst_case_exceeds_cap": worst > float(cap) + 1e-9,
            "cap": round(float(cap), 6), "verdict": verdict}


def _step_in_scope(step_id: Any, channels: Sequence[str],
                   candidate12: str) -> bool:
    """该账步是否属于本次调用声明的范围（通道 + 候选身份前 12 位）。"""

    step = str(step_id or "")
    if candidate12 and candidate12 not in step:
        return False
    if not channels:
        return False
    channel = REC12.classify_ledger_step(step)
    return str(channel) in {str(item) for item in channels}


def read_instances(run_root: Path) -> Dict[str, Any]:
    return read_json(Path(run_root) / "instances.json") or {"instances": {}}


def read_archive(run_root: Path) -> Dict[str, Any]:
    return read_json(Path(run_root) / "archive" / "av-archive.json") or {}


def read_family_roots(run_root: Path) -> Dict[str, Any]:
    return read_json(Path(run_root) / "archive" / "family-roots.json") or {}


def read_family_epochs(run_root: Path) -> Dict[str, Any]:
    return read_json(Path(run_root) / "archive" / "family-epochs.json") or {}


def _instance_status_counts(instances: Mapping[str, Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in (instances.get("instances") or {}).values():
        attempts = row.get("attempts") or []
        status = str(attempts[-1].get("status")) if attempts else "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _instances_for_split(instances: Mapping[str, Any], *, candidate_id: str,
                         mix: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for key, row in (instances.get("instances") or {}).items():
        if candidate_id and str(row.get("candidate_id")) != candidate_id:
            continue
        if mix and str(row.get("opponent_mix")) != mix:
            continue
        out[str(key)] = dict(row)
    return out


def collect_prior_consumption(run_roots: Sequence[str]) -> Dict[str, Any]:
    """把**已经发生过**的运行消耗如实记进来（不因为失败就当没发生）。

    读每个先前运行目录的 `av-ledger.json`（只读），汇总各账户已结算/在途读数，
    并列出该运行根下的迭代终态 —— "这次失败花掉了多少真实桌数"必须能在同一份报告里看到。
    """

    rows: List[Dict[str, Any]] = []
    totals: Dict[str, float] = {}
    for raw in run_roots:
        root = Path(str(raw))
        ledger = read_ledger(root)
        spent = ledger_spent(ledger)
        statuses: Dict[str, Any] = {}
        for iter_dir in iter_dirs(root):
            state = read_state(iter_dir / "state.json")
            statuses[iter_dir.name] = {
                "status": state.get("status"),
                "stop_reason": state.get("stop_reason"),
                "natural_tables": ((state.get("natural") or {})
                                   .get("tables_full_executed")),
            }
        row = {
            "run_root": str(root),
            "exists": root.is_dir(),
            "spent": spent,
            "authorized": dict(ledger.get("authorized_budgets") or {}),
            "iterations": statuses,
            "batch_label": (read_json(root / "batch-label.json") or {}).get("batch_label"),
            "note": ("先前运行的**真实消耗**（失败不等于没花钱）：已结算 + 在途，"
                     "按账户分别列出"),
        }
        rows.append(row)
        for account, value in spent.items():
            totals[account] = round(totals.get(account, 0.0) + float(value or 0.0), 6)
    return {"schema": "sitin-gate2-prior-consumption/1", "runs": rows,
            "totals": totals,
            "note": ("新增运行的实际消耗另计；本栏只记**先前**运行，避免把两次运行"
                     "混成一笔账")}


def collect_double_billing(ledger: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """重复计费判据：同一 (step_id, account) 出现多条**非 superseded 的 settled** 行。"""

    seen: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for row in (ledger.get("reservations") or ()):
        if str(row.get("status")) != "settled" or row.get("superseded"):
            continue
        seen.setdefault((str(row.get("step_id")), str(row.get("account"))),
                        []).append(dict(row))
    return [{"step_id": key[0], "account": key[1], "rows": value}
            for key, value in sorted(seen.items()) if len(value) > 1]


def collect_instance_conflicts(run_root: Path) -> List[Dict[str, Any]]:
    conflicts: List[Dict[str, Any]] = []
    for iter_dir in iter_dirs(run_root):
        payload = read_json(iter_dir / "instances.json") or {}
        for row in (payload.get("conflicts") or ()):
            conflicts.append(dict(row, iter_dir=str(iter_dir)))
    run_level = read_instances(run_root)
    for row in (run_level.get("conflicts") or ()):
        conflicts.append(dict(row, iter_dir="run-level"))
    return conflicts


def collect_fake_completions(run_root: Path) -> List[Dict[str, Any]]:
    """假完成判据：completed 尝试的结果摘要必须能**按生产 schema 重算**一致。

    旧口径（只查"摘要非空 + 路径存在"）被裁定 §5 G1 明确否决：把结果文件改一个值、
    保留原摘要，旧检查仍绿。现在交给 `p12_reconcile.collect_fake_completions`：
    自然面板按**嵌套臂结果块**的 canonical_json sha256 重算，家族/条件评价按
    **整文件 sha256** 重算（两种 schema 不混用）；不一致即红。
    """

    return REC12.collect_fake_completions(Path(run_root))


# ===========================================================================
# 判定行（每条都可复跑；不靠人眼看）
# ===========================================================================


def check(name: str, ok: bool, detail: str, *, applicable: bool = True,
          insufficient: bool = False, **extra: Any) -> Dict[str, Any]:
    """一条可复跑判定行（**四词状态**：PASS / INSUFFICIENT / FAIL / NOT_APPLICABLE）。

    - `applicable=False` = 本条判据在**本次运行范围**内不成立（例如只跑 1,2 步时的
      整链判据、或家族登记要等档案步才落盘）。它**不是"通过"**：报告里显式渲染成
      NOT_APPLICABLE 并给原因，且不计入通过率——绝不把"没跑到"写成"通过"。
    - `insufficient=True` = 预算/见证/材料不足（裁定 §3）：**既不是 FAIL 也不是
      PASS**，报告里渲染成 INSUFFICIENT。它同样不构成通过。
    """

    row = {"name": name, "ok": bool(ok), "applicable": bool(applicable),
           "insufficient": bool(insufficient), "detail": detail}
    row.update(extra)
    row["status"] = STATUS12.check_status(row)
    return row


def all_ok(rows: Sequence[Mapping[str, Any]]) -> bool:
    return all(bool(row.get("ok")) for row in rows
               if row.get("applicable", True))


def unified_acceptance(*, reconciliation: Mapping[str, Any],
                       steps: Sequence[Mapping[str, Any]],
                       mode: str = "signoff",
                       diagnostic_scope: Optional[str] = None) -> Dict[str, Any]:
    """**唯一出口**：`acceptance.ok` 当且仅当 `signoff.chain.status == PASS`。

    复审「最终状态统一」：旧实现里 `ok = reconciliation_ok AND steps_ok`，而
    `signoff.chain` 取各组最差者——两者可以不一致（能力覆盖组 N/A、某个读数组
    INSUFFICIENT 时旧式 ok 仍可为真）。现在两者只有一个出口：
    `ok ⟺ chain == PASS`；分项读数照旧列出，但**不得单独当成签收结论**。

    诊断模式（显式不同的模式与范围）运行时：`ok` 恒为 False 且
    `exit.signoff_eligible=False`——诊断运行不构成关口二签收。
    """

    signoff = dict(reconciliation.get("signoff") or {})
    chain = dict(signoff.get("chain") or {})
    chain_status = str(chain.get("status") or "")
    rule = ("唯一出口：acceptance.ok 当且仅当 signoff.chain.status == PASS；"
            "分项读数（reconciliation_ok / steps_ok / 各组状态）只是读数，"
            "不得单独当成签收结论")
    exit_info = {
        "rule": rule, "chain_status": chain_status,
        "reconciliation_ok": bool(reconciliation.get("ok")),
        "steps_ok": all_ok([row for row in steps if not row.get("skipped")]),
        "groups": [{"group": group.get("group"), "status": group.get("status")}
                   for group in (signoff.get("groups") or ())],
        "scope": chain.get("scope"),
        "signoff_eligible": True,
    }
    if str(mode) == "diagnostic":
        exit_info["rule"] = rule + (
            "；本报告是**诊断运行（非签收）**，范围 {0}：不构成关口二签收、"
            "不得当作完整签收链".format(diagnostic_scope))
        exit_info["signoff_eligible"] = False
    return {"ok": (chain_status == STATUS12.PASS and str(mode) != "diagnostic"),
            "signoff_status": chain_status, "signoff_chain": chain, "exit": exit_info}


# ===========================================================================
# 执行器：逐步推进 + 逐步对账
# ===========================================================================


class Gate2Runner:
    """关口二执行器。每个真实调用都在**独立子进程**里发生（冷接手是真的冷）。"""

    def __init__(self, *, plan: Mapping[str, Any], run_root: Path, out_dir: Path,
                 args: Any) -> None:
        self.plan = plan
        self.run_root = Path(run_root)
        self.out_dir = Path(out_dir)
        self.worker_dir = self.out_dir / "workers"
        self.worker_dir.mkdir(parents=True, exist_ok=True)
        self.args = args
        self.batch_label = validate_batch_label(
            getattr(args, "batch_label", None)
            or plan.get("batch_label") or DEFAULT_BATCH_LABEL)
        self.workers: List[Dict[str, Any]] = []
        self.steps: List[Dict[str, Any]] = []
        self.gaps: List[Dict[str, Any]] = []
        self.branches: Dict[str, Any] = {}
        self.effects: Dict[str, Any] = {}
        self.auth_path = self.run_root / "gate2-authorization.json"
        self.auth_archive = (self.out_dir / "authorization"
                             / "{0}-authorization.json".format(self.batch_label))
        self.redline_log = self.out_dir / "budget-redline.jsonl"
        self.tree_state_before = capture_tree_state()
        #: 封顶默认值 = 计划的可执行桌数；**永不高于**它（调用方传更大值即拒绝）。
        self.cap_default = float(
            plan["budget"].get("executable_planned_tables_default_cap")
            or plan["budget"].get("executable_planned_tables") or 0.0)
        self.cap = resolve_cap(requested=getattr(args, "max_tables", None),
                              cap_default=self.cap_default)
        #: 开跑前预检结果（逐账户需求 → 授权核对）；main 已先跑过一次，
        #: 这里重算只为了把同一份派生写进授权文件与报告（同一函数、同一输入 ⇒ 同结果）。
        # 生产常量（AV_REFRESH_FILL_MAX_ROUNDS 等）只读装载：轮数上界必须来自生产，
        # 不能由本包写死。
        try:
            _prod = load_production()
        except Exception:  # noqa: BLE001 - 缺件时由 derive_accounts 标注 fallback
            _prod = None
        self.derivation = derive_accounts(plan, prod=_prod)
        self.preflight = preflight(plan, supplied=getattr(args, "supplied_budgets", None),
                                   prod=_prod)
        self.prior_consumption = collect_prior_consumption(
            getattr(args, "prior_runs", ()) or ())
        #: G2 预算预检：从**待执行实例集合**出发，先看见完整比较的所有缺边。
        #: 只读计划与既有产物（0 桌 / 0 费用）；缺边清单进报告与签收。
        try:
            self.budget_preflight = BUDGET12.preflight_budget(
                plan=plan, run_root=(Path(run_root) if Path(run_root).is_dir()
                                     else None), cap=self.cap)
        except Exception as error:  # noqa: BLE001 - 预算预检失败不得吞掉运行
            self.budget_preflight = {
                "ok": False, "refusal": "预算预检异常：{0}: {1}".format(
                    type(error).__name__, error), "checks": []}

    # ---------------------------------------------------------------- 基础设施
    def gap(self, level: str, what: str, impact: str = "") -> None:
        self.gaps.append({"level": level, "what": what, "impact": impact})

    def authorization(self) -> Dict[str, Any]:
        """授权令牌 + 开发账户额度（**由计划反推**，不是凭感觉给数）。

        `batch` 与 `batch_label` 是**两个不同的东西**：
        - `batch: 7` 是生产侧的**历史门值**（`_step_natural` 的判据就是
          `authorized is True and batch == 7`），删掉它自然面板直接落 INPUT_GAP；
        - `batch_label`（默认 `{0}`）才是**本包的运行/批次标识**：进授权文件、
          运行目录、报告与全部产物，历史标签（batch7*/rep1/rep2/r6*/r7*/r8*）一律拒绝。
        把两者混为一谈正是"验收记录与 batch7b 混淆"的成因，这里显式分开。
        """.format(DEFAULT_BATCH_LABEL)

        # 逐账户额度**从计划 by_category 直接映射**（derive_accounts）：
        # 不再有任何"迭代数 + 2"这类拍出来的常数。
        derivation = self.derivation
        accounts = dict(derivation["accounts"])
        token = {
            "schema": "sitin-gate2-authorization/1",
            # —— 运行/批次标识（本包权威标签）——
            "batch_label": self.batch_label,
            "run_label": self.batch_label,
            "artifact_label_note": ("本标签写进授权文件、运行目录、报告与全部产物；"
                                    "历史标签一律拒绝"),
            # —— 生产侧历史门值（自然面板/ v2 前缀路由的判据，不可改名）——
            "authorized": True, "batch": 7,
            "batch_note": ("batch=7 是生产 _step_natural 的历史门值"
                           "（authorized is True and batch == 7），不是本包运行标签；"
                           "本包运行标签见 batch_label"),
            "note": ("关口二封顶预算：逐账户额度由**计划 by_category 直接映射**"
                     "（见 derivation.account_terms，每项都带口径）；"
                     "额度是上限不是支出，未使用部分不会被消耗；"
                     "模型 token 记 0（零模型调用）；确认账本不动用（confirm_reserved=0）"),
            "budgets": {
                "tokens_input": float(accounts.get("tokens_input") or 0.0),
                "tokens_output": float(accounts.get("tokens_output") or 0.0),
                "tables_full": float(accounts.get("tables_full") or 0.0),
                "tables_partial": float(accounts.get("tables_partial") or 0.0),
                "prefix_generation": float(accounts.get("prefix_generation") or 0.0),
                "confirm_reserved": float(accounts.get("confirm_reserved") or 0.0),
            },
            "derivation": {
                "source": "gate2-plan budget / by_category（逐类目映射）",
                "iterations": derivation["iterations"],
                "n_conditional_evaluations": derivation["n_conditional_evaluations"],
                "n_family_evaluations": derivation["n_family_evaluations"],
                "n_evaluations": derivation["n_evaluations"],
                "attempts_cap": derivation["attempts_cap"],
                "rerun_roots": derivation["rerun_roots"],
                "mapping_table": derivation["mapping_table"],
                "account_terms": derivation["account_terms"],
                "cross_checks": derivation["cross_checks"],
                "cap_default": self.cap_default,
                "cap_effective": self.cap,
            },
            "plan_source": {"path": str(getattr(self.args, "plan_path", "") or ""),
                            "schema": self.plan.get("schema"),
                            "batch_label": self.plan.get("batch_label")},
        }
        # —— 授权形态对齐（Q6／裁定 §2）——
        # 授权文档统一成 Lead 定义的 `sitin-authorization/1`（字段名照写）；
        # 生产侧 P11 落地前仍需要 legacy 门值（authorized/batch=7/budgets），
        # 因此同一份文档**带 legacy 兼容字段**（同值、不新增第二份额度），
        # 由 p12_authorization 校验并给出 authorization_form 供审计。
        authorization_id = "{0}-{1}".format(
            self.batch_label,
            hashlib.sha256(json.dumps(
                {"batch": self.batch_label, "accounts": accounts,
                 "plan": str(getattr(self.args, "plan_path", "") or "")},
                ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16])
        token.update(AUTH12.unified_document(
            batch_label=self.batch_label, authorization_id=authorization_id,
            accounts=token["budgets"], issued_by="lead",
            issued_at_utc=utc_now()))
        token["budgets"] = dict(token.get("allowed_accounts") or token["budgets"])
        self.authorization_check = AUTH12.validate(
            token, expected_batch_label=self.batch_label,
            required_operations=("natural_panel", "conditional_prefix",
                                 "family_fill", "conditional_refill", "evaluate",
                                 "summarize"))
        token["authorization_form"] = self.authorization_check["authorization_form"]
        return token

    def archive_authorization(self) -> Dict[str, Any]:
        """把授权文件与「谁授权了多少算力」留档到**证据目录**（不只留在运行目录）。"""

        token = read_json(self.auth_path) or {}
        write_json(self.auth_archive, token)
        record = {
            "schema": "sitin-gate2-authorization-archive/1",
            "batch_label": self.batch_label,
            "at_utc": utc_now(),
            "run_root": str(self.run_root),
            "run_root_token_path": str(self.auth_path),
            "evidence_token_path": str(self.auth_archive),
            "token_sha256": sha256_file(self.auth_archive),
            "budgets": dict(token.get("budgets") or {}),
            # 审计必读：本批用的是**哪一种授权形态**（legacy / sitin-authorization/1 /
            # 同文档双形态），以及统一校验的结论（allow 清单、账户、签发人、时间）。
            "authorization_form": token.get("authorization_form"),
            "authorization_check": getattr(self, "authorization_check", None),
            "derivation": dict(token.get("derivation") or {}),
            "cap_default": self.cap_default,
            "cap_effective": self.cap,
            "note": ("证据目录留档副本：授权额度与封顶都由计划反推，任何一步的"
                     "「已结算 + 在途 + 本次计划 ≤ 封顶」读数追加在同目录 "
                     "budget-redline.jsonl"),
        }
        write_json(self.out_dir / "authorization-archive.json", record)
        return record

    def call_worker(self, spec: Dict[str, Any], *, timeout: int = 10800) -> Dict[str, Any]:
        """起子进程执行 worker；返回 worker 的结果卡片（含中断判定）。"""

        tag = str(spec["tag"])
        spec = dict(spec)
        spec.setdefault("run_root", str(self.run_root))
        # 封顶红线：每一次真实推进之前都先记账并比较（读数落 evidence 的 jsonl）。
        # budget_scope 声明"本次计划量覆盖哪一批工作"（通道 + 候选身份），
        # 用来把已经完成可核/在途且在盘上的部分从计划量里扣掉（不重复计）。
        if spec.get("budget_planned") is not None:
            scope = dict(spec.get("budget_scope") or {})
            card_guard = self.budget_guard(
                planned_tables=float(spec["budget_planned"]), where=tag,
                scope_channels=tuple(scope.get("channels") or ()),
                scope_candidate12=str(scope.get("candidate12") or ""))
            spec["budget_guard"] = card_guard
        result_path = self.worker_dir / (tag + ".result.json")
        spec["worker_result"] = str(result_path)
        spec_path = self.worker_dir / (tag + ".spec.json")
        write_json(spec_path, spec)
        started = time.monotonic()
        env = dict(os.environ)
        if spec.get("interrupt_at"):
            env["GATE2_INTERRUPT_AT"] = str(spec["interrupt_at"])
        else:
            env.pop("GATE2_INTERRUPT_AT", None)
        proc = subprocess.run(
            [self.args.python, str(HERE), "--worker", str(spec_path)],
            cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
            timeout=timeout)
        card = {
            "tag": tag, "action": spec.get("action"),
            "spec_path": str(spec_path), "returncode": proc.returncode,
            "elapsed_sec": round(time.monotonic() - started, 3),
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
            "interrupted_at": spec.get("interrupt_at"),
        }
        marker = spec.get("interrupt_marker")
        card["interrupt_marker_hit"] = bool(
            marker and Path(str(marker)).is_file())
        card["interrupted"] = bool(card["interrupt_marker_hit"]
                                  and proc.returncode == INTERRUPT_EXIT_CODE)
        payload = read_json(result_path)
        if payload is not None:
            card["worker"] = payload
        self.workers.append(card)
        return card

    # ---------------------------------------------------------------- 工具
    def latest(self) -> Tuple[Optional[Path], Dict[str, Any]]:
        path = latest_state_path(self.run_root)
        return path, (read_state(path) if path else {})

    def chain_complete(self) -> bool:
        """整链判据是否适用：**已跑过的迭代**都到终态。

        注意第 6 步会在最后**新开**一个迭代并停在「等回复」（RESERVED + prompt_emitted），
        因此不能只看最后一个迭代的状态：那样会把整链判据全部误判成 N/A
        （2026-09-18 run3 实测踩过这个坑）。判据：
        - 除末尾外的每个迭代都必须是 ITERATION_COMPLETE 或已具名终态；
        - 末尾允许是刚开、正在等模型回复的交接件（step6 的 M1 任务包）；
        - 至少有一个迭代真的走到了 ITERATION_COMPLETE。
        """

        entries: List[Tuple[str, Dict[str, Any]]] = []
        for iter_dir in iter_dirs(self.run_root):
            entries.append((iter_dir.name, read_state(iter_dir / "state.json")))
        if not entries:
            return False
        done = 0
        last_name = entries[-1][0]
        for name, state in entries:
            status = str(state.get("status"))
            if status == "ITERATION_COMPLETE":
                done += 1
                continue
            phase = ((state.get("generation") or {}).get("phase"))
            if (name == last_name and status == "RESERVED"
                    and phase == "prompt_emitted"):
                continue          # step6 的 M1 交接件：合法末态
            if status in ("REJECTED", "INPUT_GAP", "BUDGET_EXHAUSTED",
                          "EXECUTION_FAILED"):
                continue          # 已具名终态：不算「未跑完」
            return False
        return done >= 1

    def second_candidate_declared(self) -> bool:
        """计划里是否声明了第二候选迭代及其家族刷新批（计时/单候选计划没有）。"""

        iterations = list(self.plan.get("iterations") or ())
        if len(iterations) < 2:
            return False
        return bool(iterations[1].get("family_refresh"))

    def archive_step_reached(self) -> bool:
        """档案步是否已跑到（家族根登记/席位在档案步落盘）。"""

        _path, state = self.latest()
        return str(state.get("status")) in (
            "ARCHIVE_COMMITTED", "ITERATION_COMPLETE") or (
            self.run_root / "archive" / "family-roots.json").is_file()

    def budget_guard(self, *, planned_tables: float, where: str,
                     scope_channels: Sequence[str] = (),
                     scope_candidate12: str = "") -> Dict[str, Any]:
        """封顶红线：**已结算 + 在途 + 本次新增计划 ≤ 封顶**（缺省 = 计划可执行桌数）。

        口径（2026-09-18 run4 修正）：
        - `settled` = 只算**已结算**行；`inflight` = 在途预留 —— 两者**各计一次**
          （旧实现对所有行求和，等价于"已结算+在途"，再 `+ inflight` 就是在途算两次）；
        - `planned` 里**已经完成且可核**（非 superseded 已结算）或**在途且结果已在盘上**
          的部分不再新增（`overlap` 扣除）——恢复"采用并结算"时不该再按计划量算一遍；
        - 扣减只认**盘上证据**：在途步必须能在运行目录里找到已执行的结果
          （自然=natural-<mix>/panel.json；条件=conditional/evaluation.json；
          家族=family/*/evaluation.json），否则一律不扣（红线不得被改废）；
        - 行里同时记 `worst_case_sum`（不扣减时的和）与 `verdict`；
          依赖采用时 verdict=`within_cap_with_adoption`，reconcile 会要求证据齐备。

        每条读数都记进证据目录的 `budget-redline.jsonl`（口径、证据与比较结果一起留档），
        因此「谁授权了多少算力、哪一步用掉了多少」可事后审计，不靠内存。
        """

        ledger = read_ledger(self.run_root)
        adoptable: Dict[str, bool] = {}
        readings = ledger_readings(ledger, account="tables_full")
        for row in readings["inflight_rows"]:
            step_id = str(row.get("step_id"))
            adoptable[step_id] = self._step_result_on_disk(step_id)
        accounting = redline_accounting(
            ledger=ledger, planned=planned_tables, cap=self.cap,
            scope_channels=scope_channels, scope_candidate12=scope_candidate12,
            adoptable_steps=adoptable)
        row = {
            "schema": "sitin-gate2-budget-redline/1",
            "batch_label": self.batch_label,
            "at_utc": utc_now(),
            "where": where,
            "account": "tables_full",
            "scope_channels": list(scope_channels),
            "scope_candidate12": scope_candidate12,
            "cap": round(self.cap, 6),
            "cap_source": ("caller" if getattr(self.args, "max_tables", None)
                           is not None else "plan_executable_default"),
            **{key: accounting[key] for key in (
                "settled", "inflight", "committed", "superseded_settled",
                "planned_this_call", "overlap_deducted", "overlap_rows",
                "planned_new", "sum", "worst_case_sum", "worst_case_exceeds_cap",
                "verdict")},
        }
        with self.redline_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        if accounting["sum"] > self.cap:
            raise SystemExit(
                "封顶红线：{0} 处 tables_full 已结算 {1:.1f} + 在途 {2:.1f} + "
                "本次新增计划 {3:.1f}（计划 {4:.1f} − 已完成可复用 {5:.1f}）"
                "= {6:.1f} > 封顶 {7:.1f}（来源：{8}）：停止（不超限执行）".format(
                    where, accounting["settled"], accounting["inflight"],
                    accounting["planned_new"], accounting["planned_this_call"],
                    accounting["overlap_deducted"], accounting["sum"], self.cap,
                    row["cap_source"]))
        return row

    def _step_result_on_disk(self, step_id: str) -> bool:
        """该账步的结果是否**已在盘上且已执行**（"采用并结算"的证据）。

        只读运行目录；找不到证据就返回 False（**不允许**无证据扣减）。
        """

        kind = REC12.classify_ledger_step(step_id)
        parts = str(step_id).split(":")
        mix = parts[2] if kind == "natural" and len(parts) > 2 else ""
        for iter_dir in iter_dirs(self.run_root):
            if kind == "natural":
                payload = read_json(iter_dir / ("natural-" + mix) / "panel.json") or {}
                executed = float((payload.get("cost") or {}).get(
                    "tables_full_executed") or 0.0)
                identity_mix = str((payload.get("identity") or {}).get("opponent_mix"))
                if executed > 0 and identity_mix == mix:
                    return True
            elif kind == "conditional":
                payload = read_json(iter_dir / "conditional" / "evaluation.json") or {}
                executed = float((payload.get("panel") or {}).get(
                    "tables_full_executed") or 0.0)
                if executed > 0:
                    return True
            elif kind == "family":
                for path in sorted((iter_dir / "family").glob("*/evaluation.json")):
                    payload = read_json(path) or {}
                    if payload.get("samples"):
                        return True
        return False

    def iteration_candidate12(self, iteration_label: str) -> str:
        """某迭代的候选身份（前 12 位）——账步范围限定用（不参与任何判定）。"""

        ordinals = REC12.plan_iteration_ordinals(self.plan)
        wanted = ordinals.get(str(iteration_label), REC12._ordinal(iteration_label))
        for iter_dir in iter_dirs(self.run_root):
            state = read_state(iter_dir / "state.json")
            label = str(state.get("iteration_no") or REC12._ordinal(iter_dir.name))
            if label != wanted:
                continue
            candidate = str((state.get("identity") or {}).get("candidate_id") or "")
            if candidate:
                return candidate[:12]
            payload = read_json(iter_dir / "instances.json") or {}
            for row in (payload.get("instances") or {}).values():
                if row.get("candidate_id"):
                    return str(row["candidate_id"])[:12]
        return ""

    def planned_tables_of(self, *, category: Optional[str] = None,
                          iteration: Optional[str] = None) -> float:
        """计划里某个（类别 × 迭代）的计划桌数——封顶检查的输入，取自计划而非估算。"""

        total = 0.0
        for row in self.plan.get("instances") or ():
            if category and str(row.get("category")) != str(category):
                continue
            if iteration and str(row.get("iteration")) != str(iteration):
                continue
            total += float(row.get("planned_tables") or 0.0)
        return total

    def natural_half(self, iteration: str) -> float:
        """一个情景（H 或 M）在该迭代的自然面板桌数 = 自然面板总桌数 / 2。"""

        return self.planned_tables_of(category="natural_full",
                                      iteration=iteration) / 2.0

    def wait_for_prompt(self, state: Mapping[str, Any]) -> Optional[Path]:
        phase = ((state.get("generation") or {}).get("phase"))
        pending = (state.get("generation") or {}).get("pending_dir")
        if phase != "prompt_emitted" or not pending:
            return None
        path = Path(str(pending)) / "prompt.txt"
        return path if path.is_file() else None

    def envelope_origin(self, prod: Mapping[str, Any]) -> str:
        """取**生产白名单**里的夹具来源（`format_fixture`），并核对计划里的声明。

        为什么必须取生产常量而不是自己写字面量：`sitin_generate.load_reply_envelope`
        是**唯一**的封套校验点（见下面 `write_envelope` 的说明），白名单改了而我们
        自己写死字符串，第一轮就会像 2026-09-17 那次干跑一样在摄入时才炸。
        为什么只能是 `format_fixture`：我们确实没有调用模型，这是人工构造的格式夹具；
        用 `delegated_model_reply` 等于把夹具写成"模型回复"，属于伪造血缘，**绝对不许**。
        """

        generate = prod["generate"]
        allowed = tuple(getattr(generate, "ORIGINS", ()) or ())
        fixture = str(getattr(generate, "ORIGIN_FIXTURE", "format_fixture"))
        if not allowed or fixture not in allowed:
            raise SystemExit(
                "生产封套白名单不可用或缺少夹具来源：ORIGINS={0!r}，"
                "ORIGIN_FIXTURE={1!r}".format(list(allowed), fixture))
        declared = str((self.plan.get("plan_config", {}).get("candidates") or [{}])[0]
                       .get("origin") or "")
        if declared and declared != fixture:
            self.gap(
                "P2",
                "计划里的 candidate_origin {0!r} 不在生产封套白名单 {1} 里；"
                "执行器改用生产常量 {2!r}（诚实取值：夹具不是模型输出）".format(
                    declared, list(allowed), fixture),
                "计划与执行器的来源声明不一致：执行器以生产白名单为准，"
                "计划应同步把 --candidate-origin 改成 format_fixture")
        self.branches.setdefault("envelope", {}).update(
            {"origin": fixture, "declared_in_plan": declared or None,
             "allowed": list(allowed),
             "required_fields": list(getattr(generate, "_ORIGIN_REQUIRED", {}).get(
                 fixture, ()) or ())})
        return fixture

    def write_envelope(self, *, state: Mapping[str, Any], seed_name: str) -> Path:
        """把**固定材料**写进模型回复这一接缝（唯一允许被替换的接缝）。

        封套字段**严格对齐生产校验**（`sitin_generate.load_reply_envelope`，
        唯一校验点，逐项见下）：
        - `schema` = `sitin-generation-reply/1`；
        - `origin` ∈ `sitin_generate.ORIGINS`，本包固定取 `format_fixture`；
        - `format_fixture` 必填 `author`/`purpose`（非空）；
        - `format_fixture` **不得**携带 `provider`/`model`（这里直接不写这两个键）；
        - `prompt_sha256` 必须与本次提示词逐字节一致。
        """

        from hangma_bot.policy.action_value_seeds import SEEDS
        prod = load_production()
        generate = prod["generate"]
        origin = self.envelope_origin(prod)
        seed = SEEDS[seed_name]
        fence = chr(96) * 3
        reply = ("{" + seed_name + " 机制（关口二确定性夹具：只替换模型回复这一接缝）}"
                 "\n\n" + fence + "json\n"
                 + json.dumps({key: seed.mechanism[key]
                               for key in generate.AV_MECHANISM_FIELDS},
                              ensure_ascii=False)
                 + "\n" + fence + "\n\n" + fence + "python\n" + seed.source
                 + fence + "\n")
        envelope_path = Path(str(state["iter_dir"])) / "reply-envelope.json"
        write_json(envelope_path, {
            "schema": str(getattr(generate, "REPLY_FILE_SCHEMA",
                                  "sitin-generation-reply/1")),
            # 诚实取值：本包没有调用任何模型，这是人工构造的格式夹具。
            "origin": origin,
            "author": "gate2_run.py（关口二验收装配；确定性固定材料，非模型输出）",
            "purpose": ("关口二无模型整链验收：只替换「外部模型回复」这一处接缝，"
                        "生产本地模拟器实执行的桌赛/根生成/台账/选席/反馈投影一律不被替换"),
            "prompt_sha256": (state.get("generation") or {}).get("prompt_sha256"),
            "reply": reply,
            "captured_at_utc": utc_now(),
            "seed_name": seed_name,
            "note": ("生产本地模拟器实执行的桌赛、根生成、台账、选席、反馈投影都没有被替换；"
                     "被替换的只有外部模型回复这一处接缝（复审 §7 关口二口径）"),
            "provenance_note": ("origin=format_fixture（人工夹具，取证强度 "
                                "human-authored-fixture）；**不得**带 provider/model"),
        })
        return envelope_path

    def resolve_old_root(self) -> Optional[Dict[str, Any]]:
        """第二候选「补旧根」：从 family-roots.json 解析第一候选条件根的身份。"""

        roots = read_family_roots(self.run_root)
        first_sub = self.plan["iterations"][0]["predicate"]
        for channel, block in (roots.get("channels") or {}).items():
            for row in ((block or {}).get("roots") or ()):
                if str(row.get("sub_scenario")) != first_sub:
                    continue
                if str(row.get("source") or "").startswith("conditional"):
                    return dict(row)
        # 兜底：取该子场景下**最小根序号**的第一条（条件根即前缀首次命中根）。
        candidates = [dict(row) for channel, block in (roots.get("channels") or {}).items()
                      for row in ((block or {}).get("roots") or ())
                      if str(row.get("sub_scenario")) == first_sub]
        return sorted(candidates, key=lambda item: int(item.get("root_index") or 0))[0] \
            if candidates else None

    # ---------------------------------------------------------------- 第 1 步
    def step1_fresh_identity_and_family(self) -> Dict[str, Any]:
        """新目录 / 新身份 / 新账本 / 空档案 + 显式启用一个家族。"""

        pre_existing = sorted(str(path.relative_to(self.run_root))
                              for path in self.run_root.rglob("*")) \
            if self.run_root.is_dir() else []
        self.run_root.mkdir(parents=True, exist_ok=True)
        write_json(self.out_dir / "tree-state-before.json", self.tree_state_before)
        # —— 批次/运行标签：进运行目录、证据目录、授权文件与报告（不只是文件名）——
        label_block = {
            "schema": "sitin-gate2-batch-label/1", "batch_label": self.batch_label,
            "at_utc": utc_now(), "run_root": str(self.run_root),
            "run_id": getattr(self.args, "run_id", None),
            "plan_schema": self.plan.get("schema"),
            "plan_batch_label": self.plan.get("batch_label"),
            "rejected_historical_prefixes": list(HISTORICAL_LABEL_PREFIXES),
            "note": ("复审 §7 关口二：新目录、新身份、新账本；历史标签"
                     "（batch7*/rep1/rep2/r6*/r7*/r8*）一律拒绝，不得与旧证据混同"),
        }
        write_json(self.run_root / "batch-label.json",
                   dict(label_block, scope="run_root"))
        write_json(self.out_dir / "batch-label.json",
                   dict(label_block, scope="evidence"))
        write_json(self.auth_path, self.authorization())
        self.archive_authorization()
        spec = self.plan["iterations"][0]
        evolve = {"generation_mode": "delegate",
                  "seed_name": spec["candidate_seed_name"],
                  "predicate": spec["predicate"], "opponent": spec["opponent"],
                  "prefix_source": spec["prefix_source"],
                  "natural_roots": spec["natural_roots"],
                  "natural_seats": spec["natural_seats"],
                  "panel_seed": spec["panel_seed"],
                  "family_channel": spec["family_channel"],
                  "family_refresh": spec["family_refresh"],
                  "stop_after": None}
        card = self.call_worker({"tag": "step1-open", "action": "evolve",
                                 "authorization_path": str(self.auth_path),
                                 # 封顶红线必须覆盖**每一步真实花钱的 worker**：
                                 # 2026-09-19 最小自测实测，旧实现 step1-open 不带
                                 # `budget_planned` ⇒ 完全绕过红线，在 `--max-tables 12`
                                 # 下仍跑出 64 桌自然面板 + 6 桌条件评价。
                                 "budget_planned": self.planned_tables_of(
                                     category="natural_full", iteration="cand1")
                                 + self.planned_tables_of(category="family_fill",
                                                          iteration="cand1"),
                                 "budget_scope": {"channels": ["natural", "family"],
                                                  "candidate12": self.iteration_candidate12(
                                                      "cand1")},
                                 "evolve": evolve})
        state_path, state = self.latest()
        prompt = self.wait_for_prompt(state) if state else None
        identity = dict(state.get("identity") or {})
        ledger = read_ledger(self.run_root)
        checks = [
            check("new_run_root", not pre_existing,
                  "运行根目录先前为空：{0}".format(pre_existing[:3] or "是"),
                  pre_existing=pre_existing[:10]),
            check("empty_archive", not (self.run_root / "archive" / "av-archive.json").is_file(),
                  "开轮前无档案（空档案 ⇒ next_generation_plan 返回 I1）"),
            check("new_ledger_zero_spent", ledger.get("reservations") is not None
                  and ledger_spent(ledger).get("tables_full", 0.0) == 0.0,
                  "新账本已建立且 tables_full 已结算为 0"),
            check("identity_frozen", bool(identity.get("frozen_manifest_digest"))
                  and bool(identity.get("contract_sha256")),
                  "开轮冻结清单摘要与合同摘要都已落盘"),
            check("family_channel_enabled",
                  str((state.get("plan") or {}).get("family_channel")) ==
                  str(spec["family_channel"]),
                  "plan.family_channel = {0}".format(
                      (state.get("plan") or {}).get("family_channel"))),
            check("family_refresh_declared",
                  len((state.get("plan") or {}).get("family_refresh") or ())
                  == len(spec["family_refresh"]),
                  "开轮声明 {0} 条刷新根（与计划逐条同数）".format(len(spec["family_refresh"]))),
            check("delegate_prompt_emitted", prompt is not None,
                  "delegate 文件通道已产交接件（不调模型）：{0}".format(prompt)),
            check("batch_label_recorded",
                  (read_json(self.run_root / "batch-label.json") or {}).get("batch_label")
                  == self.batch_label
                  and (read_json(self.out_dir / "batch-label.json") or {}).get(
                      "batch_label") == self.batch_label,
                  "批次/运行标签 {0} 已写进运行目录、证据目录、授权文件与报告".format(
                      self.batch_label)),
            check("authorization_archived_to_evidence",
                  bool(self.auth_archive.is_file())
                  and (read_json(self.auth_archive) or {}).get("batch_label")
                  == self.batch_label,
                  "授权文件留档：{0}".format(self.auth_archive)),
            check("worker_ok", bool(card.get("worker", {}).get("ok")),
                  "worker 退出码 {0}".format(card.get("returncode"))),
        ]
        refs = ((self.plan.get("frozen_inputs") or {}).get("manifest_refs") or {})
        plan_digest = (refs.get("manifest") or {}).get("digest")
        run_digest = identity.get("frozen_manifest_digest")
        tree_changed = (self.plan.get("tree_state", {}).get("tree_digest")
                        != self.tree_state_before.get("tree_digest"))
        # 逐字段比对：只在计划**声明过的**字段上比（archive_in / parent_dir 由生产在
        # 开轮时决定，不属计划声明范围）。"摘要不同"必须能归因，不能一律推给"树变了"。
        declared_block = dict(refs.get("plan_block") or {})
        run_block = dict(state.get("plan") or {})
        field_diff = {key: {"plan": value, "run": run_block.get(key)}
                      for key, value in declared_block.items()
                      if json.dumps(value, ensure_ascii=False, sort_keys=True)
                      != json.dumps(run_block.get(key), ensure_ascii=False,
                                    sort_keys=True)}
        blocks_match = bool(declared_block) and not field_diff
        if plan_digest == run_digest:
            reason = "计划与运行的冻结清单摘要一致"
        elif field_diff:
            reason = "计划块与运行块字段不同：{0}".format(
                sorted(field_diff.keys()))
        elif tree_changed:
            reason = "计划块与运行块一致，但树状态在计划生成后变化过（工具/源码字节不同）"
        else:
            reason = ("计划块与运行块一致、树状态也一致，摘要却不同——"
                      "需要人工定位（这是不可归因的不一致）")
        checks.append(check(
            "plan_run_identity_consistent",
            plan_digest == run_digest or blocks_match,
            "计划清单摘要 {0} / 运行清单摘要 {1}｜{2}".format(
                str(plan_digest)[:16], str(run_digest)[:16], reason),
            plan_manifest_digest=plan_digest, run_manifest_digest=run_digest,
            tree_changed_since_plan=tree_changed, plan_block_declared=bool(declared_block),
            plan_block_diff=field_diff))
        if not (plan_digest == run_digest or blocks_match):
            self.gap("P1", "计划与运行的清单身份不可归因地不一致",
                     "{0}：不得把两者当作同一次验收".format(reason))
        elif plan_digest != run_digest:
            self.gap("P2", "计划摘要与运行摘要不同但已归因：{0}".format(reason),
                     "同一计划块在不同树上会得到不同摘要；对账以**运行摘要**为准，"
                     "报告已并列两个摘要")
        return {"step": 1, "name": "新目录/新身份/新账本/空档案 + 显式启用家族",
                "entry": ("sitin_search.run_av_evolution → av_start_iteration"
                          "（family_channel/family_refresh 只能经进程内参数）"),
                "worker": card, "state_status": state.get("status"),
                "run_id": state.get("run_id"), "iter_dir": state.get("iter_dir"),
                "checks": checks, "ok": all_ok(checks)}

    # ---------------------------------------------------------------- 第 2 步
    def _conditional_sample(self, iter_dir: Path) -> Dict[str, Any]:
        payload = read_json(Path(iter_dir) / "conditional" / "evaluation.json") or {}
        samples = list(payload.get("samples") or ())
        return dict(samples[0]) if samples else {}

    def step2_conditional_root(self) -> Dict[str, Any]:
        """普通条件入口生成至少一个根，并核对它进了家族登记（同身份/同种子）。"""

        _, state = self.latest()
        envelope = self.write_envelope(state=state,
                                       seed_name=self.plan["iterations"][0]
                                       ["candidate_seed_name"])
        spec = self.plan["iterations"][0]
        card = self.call_worker({
            "tag": "step2-conditional", "action": "evolve",
            "authorization_path": str(self.auth_path),
            "budget_planned": self.planned_tables_of(
                category="conditional_prefix_partial", iteration="cand1")
            + self.planned_tables_of(category="conditional_full", iteration="cand1"),
            "budget_scope": {"channels": ["conditional"],
                             "candidate12": self.iteration_candidate12("cand1")},
            "evolve": {"generation_mode": "delegate",
                       "seed_name": spec["candidate_seed_name"],
                       "predicate": spec["predicate"], "opponent": spec["opponent"],
                       "prefix_source": spec["prefix_source"],
                       "natural_roots": spec["natural_roots"],
                       "natural_seats": spec["natural_seats"],
                       "panel_seed": spec["panel_seed"],
                       "stop_after": "CONDITIONAL_EVALUATED"}})
        _, state = self.latest()
        iter_dir = Path(str(state.get("iter_dir")))
        sample = self._conditional_sample(iter_dir)
        descriptor = dict(sample.get("root_descriptor") or {})
        roots = read_family_roots(self.run_root)
        registered = [dict(row) for channel, block in (roots.get("channels") or {}).items()
                      for row in ((block or {}).get("roots") or ())]
        match = [row for row in registered
                 if str(row.get("root_id")) == str(sample.get("source_root_id"))]
        conditional = dict(state.get("conditional") or {})
        # Q3：把"可重算"与"已对拍一致"分成两个结论（缺失见证记 INSUFFICIENT）。
        verdict = self._requirement_digest_verdict(sample)
        checks = [
            check("conditional_evaluated",
                  str(state.get("status")) in ("CONDITIONAL_EVALUATED",
                                               "NATURAL_EVALUATED", "SUMMARIZED",
                                               "ARCHIVE_COMMITTED",
                                               "ITERATION_COMPLETE"),
                  "状态 {0}".format(state.get("status"))),
            check("conditional_n_samples", int(conditional.get("n_samples") or 0) >= 1,
                  "条件面板产出样本 {0} 条（至少一个根）".format(
                      conditional.get("n_samples"))),
            check("conditional_real_runtime",
                  str(conditional.get("execution_kind")) == "real_runtime",
                  "执行类别 {0}（替身/夹具一律不合格）".format(
                      conditional.get("execution_kind"))),
            check("root_descriptor_present", bool(descriptor.get("root_id")),
                  "样本带唯一根描述符：{0}".format(descriptor.get("root_id"))),
            check("root_generator_matches_plan",
                  str(descriptor.get("generator")) ==
                  str(self.plan["frozen_inputs"]["family_config"]["prefix_generator"]),
                  "生成器 {0}".format(descriptor.get("generator"))),
            check("root_registered_in_family_registry", bool(match),
                  ("该根已进入 archive/family-roots.json（{0} 行）".format(len(match))
                   if self.archive_step_reached() else
                   "家族根登记在**档案步**落盘；本次运行只到 {0}，本条判据不适用"
                   "（不是通过）".format(state.get("status"))),
                  applicable=self.archive_step_reached()),
            check("root_seed_consistent",
                  bool(match) and int(match[0].get("root_seed") or -1)
                  == int(sample.get("root_seed") or -2),
                  ("登记种子 {0} / 样本种子 {1}".format(
                      (match[0].get("root_seed") if match else None),
                      sample.get("root_seed")) if self.archive_step_reached() else
                   "同上：登记行尚未落盘，本判据在本次运行范围内不适用"),
                  applicable=self.archive_step_reached()),
            check("requirement_digest_recomputable",
                  bool(verdict.get("recomputable")),
                  "根要求摘要可由冻结参数重算：recomputable={0}；重算值 {1}".format(
                      verdict.get("recomputable"),
                      str(verdict.get("recomputed"))[:16])),
            check("requirement_digest_matched",
                  bool(verdict.get("matched")),
                  "根要求摘要**与真实记录逐字一致**：matched={0}；记录值 {1}；"
                  "见证(RootWitness)存在={2}｜{3}".format(
                      verdict.get("matched"),
                      str(verdict.get("recorded"))[:16],
                      verdict.get("witness_present"), verdict.get("reason")),
                  insufficient=(verdict.get("status") == STATUS12.INSUFFICIENT),
                  witness_present=verdict.get("witness_present")),
            # 已知缺口（不是本次接线失败）：普通条件入口不落盘内容摘要/截取窗口。
            # 记为 N/A + gap，绝不当成"通过"，也不让它把接线结论染成失败。
            check("root_content_digest_persisted",
                  bool(sample.get("root_content_digest")),
                  "内容摘要已落盘={0}（普通条件入口当前**不落盘**该字段；"
                  "已知缺口，见 gaps——判据本身不适用，不是通过）".format(
                      bool(sample.get("root_content_digest"))),
                  applicable=False),
            check("worker_ok", bool(card.get("worker", {}).get("ok")),
                  "worker 退出码 {0}".format(card.get("returncode"))),
        ]
        if not sample.get("root_content_digest"):
            self.gap(
                "P1",
                ("普通条件入口（build_panel/generate_opportunity）**不落盘**截取窗口与根内容"
                 "摘要：evaluation.json 只有投影后的 panel 块与 samples，snapshot 留在内存。"),
                ("第 2 步「实际种子、前缀、窗口与内容摘要一致」只能靠**补评侧**的持久读数 + "
                 "冻结参数重算来判，不能两个持久产物对拍；窗口形状本身事后不可复算。"))
        self.branches["conditional_root"] = {
            "root_id": sample.get("source_root_id"),
            "root_index": sample.get("root_index"),
            "root_seed": sample.get("root_seed"),
            "generator": descriptor.get("generator"),
            "sub_scenario": descriptor.get("sub_scenario"),
            "opponent_mix": descriptor.get("opponent_mix"),
            "root_content_digest": sample.get("root_content_digest"),
            "root_registered": bool(match),
        }
        return {"step": 2, "name": "普通条件入口生成至少一个根 → 家族登记",
                "entry": ("_step_conditional → run_av_evaluation(prefix_source=v2_behavior)"
                          " → sitin_opportunities.build_panel/generate_opportunity；"
                          "登记在 _av_record_family_roots"),
                "worker": card, "conditional_root": self.branches["conditional_root"],
                "checks": checks, "ok": all_ok(checks)}

    # ---------------------------------------------------------------- 第 3 步
    def _seats(self) -> Dict[str, Any]:
        archive = read_archive(self.run_root)
        return dict(archive.get("slots") or {})

    def _refresh_batch_gap(self, *, by_sub: Mapping[str, Mapping[str, int]],
                           reeval_by_sub: Mapping[str, int]) -> Dict[str, Any]:
        """新刷新批（阶段 2）的**条件性**缺口读数：触发条件 + 需求 + 交付 + 缺口。

        依据原文：
        - SEARCH-SPACE-REDESIGN §537：`挑战者先补齐该通道当前全部根；**均值有望入席时**，
          预留新刷新批，并给本次参加通道重排的所有身份补齐……每受影响子场景刷新 4 根，
          整体刷新 4 根，H/M 配额均衡；不足预算则保持原席`；
        - sitin_archive.challenge_plan §9.2：阶段 2`仅当有望入席`；
          sitin_archive._validate_refresh_roots：整体 4 根；家族每子场景 4 根、H/M 各 2；
          有望入席 = **挑战者排序值 ≥ 原席者最小排序值（同根集比较）**。

        因此本判据不是"批次必须存在"，而是：**触发时**批次必须齐备（否则 INSUFFICIENT 并列缺口）；
        **未触发**时如实记 PASS 并写明条件数字（分支未触发，不是对批次齐备的确认）。
        """

        archive = read_archive(self.run_root)
        slots = dict(archive.get("slots") or {})
        selection = dict(archive.get("selection_report") or {})
        overall_rows = [dict(row) for row in (selection.get("overall") or ())]
        family_name = str((self.plan.get("frozen_inputs", {}).get("family_config") or {})
                          .get("family") or "branch")
        family_rows = [dict(row) for row in ((selection.get("family") or {})
                                            .get(family_name) or ())]
        normal_epoch = read_json(self.run_root / "archive" / "normal-epoch.json") or {}
        normal_roots_file = read_json(self.run_root / "archive" / "normal-roots.json") or {}
        family_epochs = (read_json(self.run_root / "archive" / "family-epochs.json")
                         or {}).get("channels") or {}
        family_registry = read_json(self.run_root / "archive" / "family-roots.json") or {}

        def _ids(rows: Any) -> List[str]:
            return [str(row.get("root_id")) for row in (rows or ())
                    if isinstance(row, Mapping) and row.get("root_id")]

        # 交付口径 = 生产自己的批口径（sitin_search._av_family_refresh_batch）：
        # **已登记且不在当前 epoch**的根 = 本通道可用的新刷新批。
        normal_delivered = sorted(set(_ids(normal_roots_file.get("roots")))
                                  - set(_ids(normal_epoch.get("roots"))))
        channel_epoch = dict(family_epochs.get(family_name) or {})
        family_delivered = sorted(
            {root_id for _channel, block in (family_registry.get("channels") or {}).items()
             for root_id in _ids((block or {}).get("roots"))}
            - set(_ids(channel_epoch.get("roots"))))

        # 触发条件（**数字必须在读数里**）：挑战者排序值 ≥ 在席者最小排序值（同根集比较）。
        def _criterion(rows: List[Dict[str, Any]], seat_ids: List[str]) -> Dict[str, Any]:
            seated = [float(row["sort_value"]) for row in rows
                      if str(row.get("candidate_id")) in seat_ids
                      and row.get("sort_value") is not None]
            challengers = [{"candidate_id": str(row.get("candidate_id")),
                            "value": float(row["sort_value"])} for row in rows
                           if str(row.get("candidate_id")) not in seat_ids
                           and row.get("sort_value") is not None]
            best = min(challengers, key=lambda row: row["value"]) if challengers else None
            verdict = (None if not seated or best is None
                       else best["value"] >= min(seated))
            return {"threshold_incumbent_min": (min(seated) if seated else None),
                    "challenger": best, "promising": verdict}

        overall_ids = [str(cid) for cid in (slots.get("overall") or ())]
        family_ids = [str(cid) for cid in (slots.get(family_name) or ())]
        overall_criterion = _criterion(overall_rows, overall_ids)
        family_criterion = _criterion(family_rows, family_ids)
        triggered = bool(overall_criterion.get("promising")
                         or family_criterion.get("promising"))

        # 需求（每受影响子场景 4 根 H2/M2；整体 4 根 H2/M2）与缺口。
        declared_sub: List[str] = sorted({
            str(row.get("sub_scenario")) for row in (self.plan.get("instances") or ())
            if str(row.get("category")) == "family_fill" and row.get("sub_scenario")})
        family_requirement = {sub: {"H": 2, "M": 2} for sub in declared_sub}
        family_gap: List[Dict[str, Any]] = []
        for sub, need in family_requirement.items():
            delivered = {mix: sum(1 for root_id in family_delivered
                                  if "{0}:".format(sub) in root_id
                                  and ":{0}:s".format(mix) in root_id)
                         for mix in ("H", "M")}
            missing_roots = sum(max(0, need[mix] - delivered[mix]) for mix in ("H", "M"))
            declared_now = dict(by_sub.get(sub) or {})
            if missing_roots:
                family_gap.append({
                    "sub_scenario": sub, "required": dict(need), "delivered": delivered,
                    "declared_in_plan": declared_now, "missing_roots": missing_roots,
                    "missing_instances": missing_roots * 2, "missing_tables": missing_roots * 4})
        normal_need = {"H": 2, "M": 2}
        normal_delivered_counts = {
            mix: sum(1 for root_id in normal_delivered if "-{0}-".format(mix) in root_id)
            for mix in ("H", "M")}
        normal_missing_roots = sum(max(0, normal_need[mix] - normal_delivered_counts[mix])
                                   for mix in ("H", "M"))
        normal_gap = ({"required": normal_need, "delivered": normal_delivered_counts,
                       "missing_roots": normal_missing_roots,
                       "missing_instances": normal_missing_roots * 8,
                       "missing_tables": normal_missing_roots * 16}
                      if normal_missing_roots else None)

        missing_declarations: List[Dict[str, Any]] = []
        if triggered:
            if normal_gap:
                missing_declarations.append(dict({"channel": "normal"}, **normal_gap))
            for row in family_gap:
                missing_declarations.append(dict({"channel": family_name}, **row))

        producer = {"overall_challenge": dict(archive.get("challenge") or {}),
                    "family_challenge": dict(archive.get("family_challenge") or {})}
        numbers = {
            "trigger": {"criterion": "挑战者排序值 ≥ 在席者最小排序值（同根集比较）",
                        "overall": overall_criterion, "family": family_criterion,
                        "triggered": triggered},
            "requirement": {"normal_roots": 4, "family_roots_per_sub_scenario": 4,
                            "affected_sub_scenarios": declared_sub},
            "delivered": {"normal_roots": normal_delivered,
                          "family_roots": family_delivered,
                          "declared_discover_in_plan": dict(by_sub),
                          "reevaluation_declarations": dict(reeval_by_sub)},
            "producer_verdict": producer}
        if not triggered:
            detail = ("新刷新批**条件未触发**（{0}）：整体通道 挑战者 {1} vs 在席者最小 {2}；"
                      "家族 {3} 通道 挑战者 {4} vs 在席者最小 {5} ⇒ 本计划不为新刷新批"
                      "预留配额（§537 阶段 2 不进入）。该判据按条件性判定记 PASS，"
                      "**不是**对刷新批齐备的确认；交付读数：整体 {6} 根 / 家族 {7} 根").format(
                          numbers["trigger"]["criterion"],
                          json.dumps(overall_criterion, ensure_ascii=False),
                          json.dumps(overall_criterion.get("threshold_incumbent_min")),
                          family_name, json.dumps(family_criterion, ensure_ascii=False),
                          json.dumps(family_criterion.get("threshold_incumbent_min")),
                          len(normal_delivered), len(family_delivered))
        elif missing_declarations:
            detail = ("新刷新批**条件已触发**（{0}）但批次不齐 ⇒ INSUFFICIENT："
                      "整体刷新批 {1}/{2} 根（缺 {3} 根 / {4} 实例 / {5} 桌）；"
                      "家族通道逐子场景 {6}；本迭代新根发现声明 {7}（重评 {8} 不进配额）；"
                      "生产自报：{9}").format(
                          json.dumps({"overall": overall_criterion,
                                      "family": family_criterion}, ensure_ascii=False),
                          len(normal_delivered), 4,
                          (normal_gap or {}).get("missing_roots"),
                          (normal_gap or {}).get("missing_instances"),
                          (normal_gap or {}).get("missing_tables"),
                          json.dumps(family_gap, ensure_ascii=False),
                          json.dumps(by_sub, ensure_ascii=False),
                          json.dumps(reeval_by_sub, ensure_ascii=False),
                          json.dumps(producer, ensure_ascii=False)[:220])
        else:
            detail = ("新刷新批**条件已触发且批次齐备**：整体 {0}/4 根；家族 {1}（声明 {2}）。"
                      "触发条件：{3}").format(
                          len(normal_delivered), json.dumps(family_delivered, ensure_ascii=False),
                          json.dumps(by_sub, ensure_ascii=False),
                          json.dumps({"overall": overall_criterion,
                                      "family": family_criterion}, ensure_ascii=False))
        return {"trigger": numbers["trigger"], "requirement": numbers["requirement"],
                "delivered": numbers["delivered"], "producer_verdict": producer,
                "family_gap": family_gap, "normal_gap": normal_gap,
                "missing_declarations": missing_declarations,
                "missing_tables": sum(int(row.get("missing_tables") or 0)
                                      for row in missing_declarations),
                "missing_instances": sum(int(row.get("missing_instances") or 0)
                                         for row in missing_declarations),
                "detail": detail}

    def _second_iteration_spec(self) -> Optional[Dict[str, Any]]:
        iterations = list(self.plan.get("iterations") or ())
        if len(iterations) < 2:
            return None
        spec = dict(iterations[1])
        old = self.resolve_old_root()
        if old is None:
            self.gap("P1", "第二候选的「补旧根」无法解析",
                     "family-roots.json 里没有第一候选条件根：第二候选刷新批会缺一条")
            return spec
        resolved = []
        for decl in spec["family_refresh"]:
            decl = dict(decl)
            if decl.get("root_index") is None:
                decl.update({"sub_scenario": old.get("sub_scenario"),
                             "opponent_mix": old.get("opponent_mix"),
                             "root_index": int(old.get("root_index")),
                             "root_id": old.get("root_id"),
                             "root_seed": old.get("root_seed"),
                             "resolved_from": "iteration_1_conditional_root"})
            resolved.append(decl)
        spec["family_refresh"] = resolved
        spec["resolved_old_root"] = old
        return spec

    def step3_seats(self, *, with_interrupt: bool) -> Dict[str, Any]:
        """第一候选建立正常席与家族首席；第二候选补旧根 + 完成新刷新根。"""

        checks: List[Dict[str, Any]] = []
        spec = self.plan["iterations"][0]
        if self.args.steps_include(3) or self.args.steps_include(5):
            card = self.call_worker({
                "tag": "step3-iter1-complete", "action": "evolve",
                "authorization_path": str(self.auth_path),
                "budget_planned": self.planned_tables_of(
                    category="natural_full", iteration="cand1")
                + self.planned_tables_of(category="family_fill", iteration="cand1"),
                "budget_scope": {"channels": ["natural", "family"],
                                 "candidate12": self.iteration_candidate12("cand1")},
                "evolve": {"generation_mode": "delegate",
                           "seed_name": spec["candidate_seed_name"],
                           "predicate": spec["predicate"],
                           "opponent": spec["opponent"],
                           "prefix_source": spec["prefix_source"],
                           "natural_roots": spec["natural_roots"],
                           "natural_seats": spec["natural_seats"],
                           "panel_seed": spec["panel_seed"], "stop_after": None}})
        else:
            card = {"skipped": True}
        _, state = self.latest()
        seats = self._seats()
        epochs = read_family_epochs(self.run_root)
        iter_dir = Path(str(state.get("iter_dir")))
        report = read_json(iter_dir / "batch-report.json") or {}
        scoped = self.second_candidate_declared()
        scope_note = ("" if scoped else
                      "；本计划未声明第二候选的家族刷新批（计时/单候选），"
                      "本判据在本次运行范围内不适用（不是通过）")
        checks.extend([
            check("iteration_1_terminal",
                  str(state.get("status")) == "ITERATION_COMPLETE",
                  "第一候选迭代终态 {0}".format(state.get("status"))),
            check("normal_seat_established", bool(seats.get("overall")),
                  "正常席（overall）={0}{1}".format(seats.get("overall"), scope_note),
                  applicable=scoped or bool(seats.get("overall"))),
            check("family_chief_seat_established",
                  bool(seats.get(str(self.plan["frozen_inputs"]["family_config"]["family"]))),
                  "家族首席席（{0}）={1}{2}".format(
                      self.plan["frozen_inputs"]["family_config"]["family"],
                      seats.get(str(self.plan["frozen_inputs"]["family_config"]
                                    ["family"])), scope_note),
                  applicable=scoped),
            check("family_epoch_committed", bool(epochs),
                  "家族 epoch 已建立/刷新：{0}{1}".format(
                      sorted(epochs.keys())[:3] or "无", scope_note),
                  applicable=scoped),
            check("batch_report_present", bool(report.get("next_task_package")),
                  "批末报告含 next_task_package（停止原因与下一动作可复算）",
                  applicable=scoped),
        ])
        # —— 第二候选：开轮（含运行时解析出来的补旧根声明） ——
        spec2 = self._second_iteration_spec() if scoped else {}
        self.branches["second_iteration_declarations"] = spec2.get("family_refresh")
        self.branches["old_root_resolution"] = spec2.get("resolved_old_root")
        if scoped and (self.args.steps_include(3) or self.args.steps_include(5)):
            card2 = self.call_worker({
                "tag": "step3-iter2-open", "action": "evolve",
                "authorization_path": str(self.auth_path),
                # 同上：第二候选开轮同样花钱，必须进封顶红线（否则又绕开 cap）。
                "budget_planned": self.planned_tables_of(
                    category="natural_full", iteration="cand2")
                + self.planned_tables_of(category="family_fill", iteration="cand2"),
                "budget_scope": {"channels": ["natural", "family"],
                                 "candidate12": self.iteration_candidate12("cand2")},
                "evolve": {"generation_mode": "delegate",
                           "seed_name": spec2["candidate_seed_name"],
                           "predicate": spec2["predicate"],
                           "opponent": spec2["opponent"],
                           "prefix_source": spec2["prefix_source"],
                           "natural_roots": spec2["natural_roots"],
                           "natural_seats": spec2["natural_seats"],
                           "panel_seed": spec2["panel_seed"],
                           "family_channel": spec2["family_channel"],
                           "family_refresh": spec2["family_refresh"],
                           "stop_after": None}})
            _, state2 = self.latest()
            envelope = self.write_envelope(state=state2,
                                           seed_name=spec2["candidate_seed_name"])
            card3 = self.call_worker({
                "tag": "step3-iter2-conditional", "action": "evolve",
                "authorization_path": str(self.auth_path),
                "reply_envelope": str(envelope),
                "budget_planned": self.planned_tables_of(
                    category="conditional_prefix_partial", iteration="cand2")
                + self.planned_tables_of(category="conditional_full", iteration="cand2"),
                "budget_scope": {"channels": ["conditional"],
                                 "candidate12": self.iteration_candidate12("cand2")},
                "evolve": {"generation_mode": "delegate",
                           "seed_name": spec2["candidate_seed_name"],
                           "predicate": spec2["predicate"],
                           "opponent": spec2["opponent"],
                           "prefix_source": spec2["prefix_source"],
                           "natural_roots": spec2["natural_roots"],
                           "natural_seats": spec2["natural_seats"],
                           "panel_seed": spec2["panel_seed"],
                           "stop_after": "CONDITIONAL_EVALUATED"}})
        else:
            card2 = card3 = {"skipped": True}
        _, state2 = self.latest()
        declared = (state2.get("plan") or {}).get("family_refresh") or []
        # H2/M2 配额只约束**新根发现**子集（生产 `_validate_refresh_roots` 校验的是
        # 刷新批=新根集）：指定旧根重评行不进配额，否则"共同根比较"会被 4 根配额挡掉
        # （2026-09-18 run6 实测：把重评行算进配额会误报 branch_open H3/M2）。
        by_sub: Dict[str, Dict[str, int]] = {}
        reeval_by_sub: Dict[str, int] = {}
        for row in declared:
            sub = str(row.get("sub_scenario"))
            if str(row.get("intent") or "") == "reevaluate_registered_root":
                reeval_by_sub[sub] = reeval_by_sub.get(sub, 0) + 1
                continue
            bucket = by_sub.setdefault(sub, {"H": 0, "M": 0})
            bucket[str(row.get("opponent_mix"))] += 1
        refresh_gap = self._refresh_batch_gap(by_sub=by_sub,
                                              reeval_by_sub=reeval_by_sub)
        checks.extend([
            check("second_candidate_opened",
                  int(state2.get("iteration_no") or 0) == 2,
                  "第二次迭代编号 {0}{1}".format(state2.get("iteration_no"), scope_note),
                  applicable=scoped),
            # 裁决依据：SEARCH-SPACE-REDESIGN §537 / sitin_archive.challenge_plan §9.2 两阶段——
            # **挑战者先补齐该通道当前全部根**；**均值有望入席时**才预留新刷新批
            # （"有望入席 = 挑战者排序值 ≥ 原席者最小排序值（同根集比较）"）。
            # 因此本判据是**条件性**的：未触发 ⇒ PASS 并写明条件数字；触发而批次不齐
            # ⇒ INSUFFICIENT 并逐项列出缺口（实例/桌）。
            check("refresh_declarations_balanced",
                  not refresh_gap["missing_declarations"],
                  refresh_gap["detail"],
                  applicable=scoped,
                  insufficient=bool(refresh_gap["missing_declarations"]),
                  trigger=refresh_gap["trigger"], gap=refresh_gap),
            check("old_root_declared_for_refill",
                  any(row.get("resolved_from") == "iteration_1_conditional_root"
                      for row in declared),
                  "补旧根声明已解析为具体根序号（开轮时由 family-roots.json 解析）"
                  + scope_note,
                  applicable=scoped),
            check("worker_ok_iter1", bool(card.get("worker", {}).get("ok"))
                  or card.get("skipped"),
                  "worker 退出码 {0}".format(card.get("returncode"))),
            check("worker_ok_iter2", bool(card3.get("worker", {}).get("ok"))
                  or card3.get("skipped"),
                  "worker 退出码 {0}{1}".format(card3.get("returncode"), scope_note),
                  applicable=scoped or bool(card3.get("skipped"))),
        ])
        result = {"step": 3, "name": "第一候选正常席/家族首席；第二候选补旧根 + 新刷新根",
                  "entry": ("_step_archive → _av_commit_archive/_av_commit_family；"
                            "_step_refresh_fill → _av_family_fill → _av_commit_slots"),
                  "second_candidate_scoped": scoped,
                  "workers": [card, card2, card3], "checks": checks,
                  "ok": all_ok(checks), "finalized": not scoped}
        if scoped and not with_interrupt:
            result = self.finalize_second_candidate(result)
        return result

    def finalize_second_candidate(self, step3: Dict[str, Any]) -> Dict[str, Any]:
        """第二候选走完（自然面板 + 补根 + 提交），并核对补旧根逐字一致。"""

        spec2 = self._second_iteration_spec() or {}
        _, state_now = self.latest()
        if str(state_now.get("status")) == "ITERATION_COMPLETE":
            # 第 5 步的冷恢复已经把这一轮走完：**绝不再开一次**（否则会开出新迭代，
            # 把 M1 任务包挤到下一轮，计划与实际的迭代数就对不上）。
            card = {"skipped": True,
                    "reason": "第二候选迭代已由冷恢复走到 ITERATION_COMPLETE"}
        elif self.args.steps_include(3) or self.args.steps_include(5):
            card = self.call_worker({
                "tag": "step3-iter2-complete", "action": "evolve",
                "authorization_path": str(self.auth_path),
                "budget_planned": self.planned_tables_of(
                    category="natural_full", iteration="cand2")
                + self.planned_tables_of(category="family_fill", iteration="cand2"),
                "budget_scope": {"channels": ["natural", "family"],
                                 "candidate12": self.iteration_candidate12("cand2")},
                "evolve": {"generation_mode": "delegate",
                           "seed_name": spec2.get("candidate_seed_name"),
                           "predicate": spec2.get("predicate"),
                           "opponent": spec2.get("opponent"),
                           "prefix_source": spec2.get("prefix_source"),
                           "natural_roots": spec2.get("natural_roots"),
                           "natural_seats": spec2.get("natural_seats"),
                           "panel_seed": spec2.get("panel_seed")}})
        else:
            card = {"skipped": True}
        _, state = self.latest()
        iter_dir = Path(str(state.get("iter_dir")))
        seats = self._seats()
        epochs = read_family_epochs(self.run_root)
        roots = read_family_roots(self.run_root)
        registered = [dict(row) for channel, block in (roots.get("channels") or {}).items()
                      for row in ((block or {}).get("roots") or ())]
        old = (self.branches.get("old_root_resolution") or {})
        # `指定旧根`的证据：**复用 P12 的同一实现**（条件通道可核覆盖 + RootWitness）。
        # 2026-09-19 run8 实测：旧实现只 glob 家族目录 ⇒ 同根评价落在条件通道时全判 FAIL
        # （7 条判据同因），与已裁定口径冲突。
        # 挑战者身份：取"条件通道里承载该旧根的那次迭代"的候选（运行期解析的根绑定到需求项），
        # 不用 latest()——最后一个迭代可能是等回复的 M1 迭代（无候选身份）。
        ordinal = (REC12.plan_iteration_ordinals(self.plan).get(
            str((self._second_iteration_spec() or {}).get("iteration_label")))
            or str(state.get("iteration_no") or ""))
        roots_by_iter = REC12.conditional_roots_by_iteration(Path(self.run_root))
        bound = dict(roots_by_iter.get(str(ordinal)) or {})
        candidate_id = (str(bound.get("candidate_id") or "")
                        if str(bound.get("root_id")) == str(old.get("root_id"))
                        else str((state.get("identity") or {}).get("candidate_id") or ""))
        refill = self._designated_root_evidence(
            candidate_id=candidate_id, root_id=str(old.get("root_id") or ""))
        refill_verdict = dict(refill.get("requirement_verdict") or {})
        legacy_refill = self._refill_identity(iter_dir, str(old.get("root_id") or ""))
        generation = self.branches.get("conditional_root") or {}
        refill_note = ("basis={0}；产物 {1}（迭代 {2}）；臂 {3}；摘要 {4}".format(
            refill.get("basis"), refill.get("product_path"),
            refill.get("product_iteration"), refill.get("covered_arms"),
            refill.get("digest_state")) if refill.get("present") else
            "该完整根在条件通道**没有**可核产物（同一候选 + 同一根 + 两臂完整可用 + "
            "摘要登记重算一致，四者缺一即不算承担）")
        scoped = self.second_candidate_declared()
        note = ("" if scoped else
                "；本计划未声明第二候选的家族刷新批（计时/单候选），本判据不适用（不是通过）")
        checks = list(step3.get("checks") or [])
        checks.extend([
            check("iteration_2_terminal",
                  str(state.get("status")) == "ITERATION_COMPLETE",
                  "第二候选迭代终态 {0}{1}".format(state.get("status"), note),
                  applicable=scoped),
            check("refresh_roots_materialized",
                  len(registered) >= len(self.plan["frozen_root_list"]),
                  "家族根登记 {0} 条（核心清单 {1} 根 + 刷新根）{2}".format(
                      len(registered), len(self.plan["frozen_root_list"]), note),
                  applicable=scoped),
            check("refill_old_root_present", bool(refill.get("present")),
                  "指定旧根的可核产物（由其它通道承担）：{0}{1}".format(refill_note, note),
                  applicable=scoped, refill=refill, legacy_family_refill=legacy_refill),
            check("refill_root_id_matches_generation",
                  bool(refill.get("present"))
                  and str(refill.get("root_id")) == str(generation.get("root_id")),
                  "补评根身份 {0} / 生成根身份 {1}（**完整根身份**比对，不用根序号兜底）{2}"
                  .format(refill.get("root_id"), generation.get("root_id"), note),
                  applicable=scoped),
            check("refill_seed_matches_generation",
                  bool(refill.get("present"))
                  and refill.get("root_seed") == generation.get("root_seed"),
                  "补评种子 {0} / 生成种子 {1}（逐字相等才叫同一座牌山）{2}".format(
                      refill.get("root_seed"), generation.get("root_seed"), note),
                  applicable=scoped),
            check("refill_requirement_digest_recomputable",
                  bool(refill.get("present"))
                  and bool(refill_verdict.get("recomputable")),
                  "补评侧要求摘要**可重算**：recomputable={0}（按冻结参数重算；可重算不等于"
                  "已对拍）{1}".format(refill_verdict.get("recomputable"), note),
                  applicable=scoped),
            check("refill_requirement_digest_matched",
                  bool(refill.get("present")) and bool(refill_verdict.get("matched")),
                  "补评侧要求摘要与**真实记录**逐字一致：matched={0}｜记录来源 {1}｜{2}{3}"
                  .format(refill_verdict.get("matched"),
                          refill_verdict.get("witness_source") or "样本/RootWitness",
                          refill_verdict.get("reason"), note),
                  applicable=scoped,
                  insufficient=(bool(refill.get("present"))
                                and refill_verdict.get("status")
                                == STATUS12.INSUFFICIENT),
                  witness_present=refill_verdict.get("witness_present")),
            check("refill_root_witness_present",
                  bool(refill.get("witness", {}).get("present")),
                  "补评侧**内容见证**（RootWitness {0}）已落盘：content_digest={1}；"
                  "字段集（裁定 §4.2）：根描述/实际 seed/前缀摘要/窗口键/观察摘要/内容摘要/"
                  "序列化版本{2}".format(
                      str(refill.get("witness", {}).get("serialization_version")),
                      str(refill.get("root_content_digest"))[:16], note),
                  applicable=scoped,
                  insufficient=not bool(refill.get("witness", {}).get("present"))),
            check("refill_content_digest_persisted",
                  bool(refill.get("root_content_digest")),
                  "补评侧内容摘要已落盘：{0}{1}".format(
                      str(refill.get("root_content_digest"))[:16], note),
                  applicable=scoped,
                  insufficient=not bool(refill.get("root_content_digest"))),
            # P19：该判据改为**消费 RootWitness**（P16 已升到 /2：含截取窗口键与逐字段摘要）。
            # 见证在场 + 绑定通过（要求摘要对拍不为 False、种子与描述符一致、窗口键齐备）⇒ PASS；
            # 见证缺失或不匹配 ⇒ FAIL（不是 N/A，也不是"事后不可复算"的自我豁免）。
            check("window_digest_basis_available",
                  bool(refill.get("witness", {}).get("present"))
                  and bool(refill.get("cut_window_key"))
                  and refill.get("witness", {}).get("requirement_matched") is True
                  and refill.get("witness", {}).get("seed_matches_descriptor") is not False,
                  "截取窗口读数**由该次评价的根见证承担**（存在 + 绑定通过 = 要求摘要重算一致"
                  "且窗口键齐备）：witness={0}｜绑定迭代 {1}｜cut_window_key={2}｜"
                  "prefix_sha256={3}｜observation_summary_sha256={4}｜要求摘要 matched={5}｜"
                  "seed_matches_descriptor={6}｜其它迭代同根见证 {7}{8}".format(
                      refill.get("witness", {}).get("serialization_version"),
                      refill.get("witness", {}).get("bound_to_iteration"),
                      json.dumps(refill.get("cut_window_key"), ensure_ascii=False),
                      str(refill.get("witness", {}).get("prefix_sha256"))[:16],
                      str(refill.get("witness", {}).get(
                          "observation_summary_sha256"))[:16],
                      refill.get("witness", {}).get("requirement_matched"),
                      refill.get("witness", {}).get("seed_matches_descriptor"),
                      json.dumps(refill.get("witness", {}).get(
                          "other_iteration_witnesses") or [], ensure_ascii=False)[:120], note),
                  applicable=scoped,
                  witness=refill.get("witness")),
            check("second_candidate_seats_present",
                  bool(seats.get("overall")) and bool(seats.get(
                      str(self.plan["frozen_inputs"]["family_config"]["family"]))),
                  "第二候选后席位：overall={0}；探索席={1}{2}".format(
                      seats.get("overall"), seats.get("exploration"), note),
                  applicable=scoped),
            check("epoch_status_recorded",
                  bool(epochs),
                  "epoch 状态：{0}{1}".format(
                      {key: (value or {}).get("status") if isinstance(value, Mapping)
                       else value for key, value in list(epochs.items())[:3]}, note),
                  applicable=scoped),
            check("worker_ok", bool(card.get("worker", {}).get("ok"))
                  or card.get("skipped"),
                  "worker 退出码 {0}".format(card.get("returncode"))),
        ])
        step3 = dict(step3)
        step3.update({"finalize_worker": card, "checks": checks, "ok": all_ok(checks),
                      "finalized": True, "refill": refill,
                      "second_candidate_branch": self._branch_verdict(seats, epochs)})
        return step3

    def _root_witnesses(self) -> Dict[str, List[Dict[str, Any]]]:
        """本运行的 RootWitness 索引（按来源根；只读，缓存在实例上）。"""

        cached = getattr(self, "_witness_cache", None)
        if cached is None:
            cached = REC12.witnesses_by_root(self.run_root)
            self._witness_cache = cached
        return cached

    def _requirement_digest_verdict(self, sample: Mapping[str, Any]) -> Dict[str, Any]:
        """根要求摘要 —— **两个结论分开**（裁定 §4.2），并优先采用真实 RootWitness。

        - `recomputable`：能不能按**冻结参数**（生成器 × 子场景 × 情景 × 面板种子 ×
          根序号）重算出要求摘要。这只是"可重算"，**不是**"已对拍一致"。
        - `matched`：**真实记录**（样本字段或 P11 的 RootWitness）里的要求摘要与重算值逐字相等。
          - 样本字段缺失但附属文件里有见证 ⇒ 用见证比对（Q3：等价持久证据，来自真实运行）；
          - 两者都没有 ⇒ `matched=False` 且状态 INSUFFICIENT（**不是 PASS，也不是 FAIL**）。

        旧实现在 recorded 缺失时返回 `bool(expected)` —— 把"可重算"当成了"已对拍一致"，
        这正是裁定 §4.2 点名要拆开的两个结论。
        """

        # 条件通道的样本带 root_descriptor；家族/补评样本**不带**，只有身份串 ⇒
        # 从身份串还原唯一描述符（否则"可重算"这一半会被误判成不可重算）。
        descriptor = dict(sample.get("root_descriptor")
                          or REC12.descriptor_from_root_id(
                              sample.get("source_root_id")))
        verdict: Dict[str, Any] = {
            "recomputable": False, "matched": False, "status": STATUS12.FAIL,
            "recomputed": None, "recorded": sample.get("root_requirement_digest"),
            "witness_present": bool(sample.get("root_content_digest")),
            "reason": "",
        }
        if not descriptor.get("root_id"):
            verdict["reason"] = "样本不带唯一根描述符 ⇒ 无法按冻结参数重算"
            return verdict
        prod = load_production()
        try:
            expected = prod["search"].av_family_root_requirement_digest(
                prefix_source="v2_behavior",
                predicate=str(descriptor.get("sub_scenario")),
                opponent_mix=str(descriptor.get("opponent_mix")),
                panel_seed=int(descriptor.get("panel_seed")),
                root_index=int(descriptor.get("root_index")))
        except Exception as error:  # noqa: BLE001 - 重算失败即判不成立（不静默通过）
            verdict["reason"] = "要求摘要重算失败：{0}: {1}".format(
                type(error).__name__, error)
            return verdict
        verdict["recomputable"] = bool(expected)
        verdict["recomputed"] = expected
        recorded = sample.get("root_requirement_digest")
        witness_source = None
        if recorded is None:
            # Q3：样本字段缺失时，优先用 **RootWitness 附属文件**（P11）里的真实记录。
            hits = (self._root_witnesses().get(str(sample.get("source_root_id")) or "")
                    or self._root_witnesses().get(str(descriptor.get("root_id")) or "")
                    or [])
            for hit in hits:
                witness = dict(hit.get("witness") or {})
                if witness.get("requirement_digest"):
                    recorded = witness.get("requirement_digest")
                    witness_source = hit.get("_sidecar")
                    verdict["witness"] = REC12.witness_verdict(
                        hit, recomputed_requirement=expected)
                    break
        if recorded is None:
            verdict["status"] = STATUS12.INSUFFICIENT
            verdict["reason"] = ("可重算，但结果产物与 RootWitness 附属文件里都**没有**"
                                 "真实记录的要求摘要：记 INSUFFICIENT，不写成通过")
            return verdict
        if witness_source:
            verdict["witness_source"] = witness_source
            verdict["witness_present"] = True
        verdict["recorded"] = recorded
        verdict["matched"] = str(recorded) == str(expected)
        verdict["status"] = (STATUS12.PASS if verdict["matched"] else STATUS12.FAIL)
        verdict["reason"] = ("{0}与冻结参数重算值逐字一致".format(
            "RootWitness 记录值" if witness_source else "样本记录值") if verdict["matched"]
            else "{0}与冻结参数重算值不一致".format(
                "RootWitness 记录值" if witness_source else "样本记录值"))
        return verdict

    def _requirement_digest_matches(self, sample: Mapping[str, Any]) -> bool:
        """兼容旧调用点：**只有"已对拍一致"才为真**（可重算不算）。

        保留这个薄封装是为了不让旧判据名静默变成"通过"；新代码一律用
        `_requirement_digest_verdict` 拿两个结论。
        """

        return bool(self._requirement_digest_verdict(sample).get("matched"))

    def _designated_root_evidence(self, *, candidate_id: str,
                                  root_id: str) -> Dict[str, Any]:
        """`指定旧根`的证据汇总（**单一来源**：条件通道可核覆盖 + RootWitness 对拍）。

        裁定依据：P15/P18 已裁定`指定旧根由**条件通道**的同候选 + 同完整根可核产物承担`
        （`basis=conditional_channel_product`）。本方法只调 **P12 的同一实现**
        （`REC12.conditional_coverage_verdict`）取身份/可核性，要求摘要与内容见证则
        复用执行器自己的 `_requirement_digest_verdict`（样本缺字段时自动落到 RootWitness
        的真实记录，绝不把"可重算"当成"已对拍"）。
        """

        coverage = REC12.cross_channel_coverage(Path(self.run_root))
        arms = ["baseline", "candidate"]
        per_arm = {arm: REC12.conditional_coverage_verdict(
            coverage=coverage, candidate_id=str(candidate_id), root_id=str(root_id),
            arm=arm) for arm in arms}
        covered_arms = [arm for arm, verdict in per_arm.items() if verdict]
        hits = list(REC12.witnesses_by_root(Path(self.run_root)).get(str(root_id)) or [])
        # 同一根可能有多次捕获的见证（迭代 1 生成、迭代 2 补评）：优先取**承担该义务的那次
        # 评价所在迭代**的见证（sidecar 路径含 iter-NN），否则退回第一条。
        product_iteration = ((per_arm.get(covered_arms[0]) or {}).get("product_iteration")
                             if covered_arms else None)
        marker = None
        if product_iteration:
            marker = ("iter-{0:02d}".format(int(product_iteration))
                      if str(product_iteration).isdigit() else str(product_iteration))
        same_iteration = [hit for hit in hits
                          if marker and marker in str(hit.get("_sidecar") or "")]
        other_iteration = [hit for hit in hits if hit not in same_iteration]
        # **严格绑定**：判据消费的是"承担该义务的那次评价"所在迭代的见证；
        # 其它迭代的同根见证只作读数（informational），不据此判 PASS，
        # 否则"把见证删掉"这类反例会被更早的捕获顶掉（P19 反例 M4 实测）。
        strict_hits = same_iteration or (hits if not marker else [])
        witness = (REC12.witness_verdict(strict_hits[0]) if strict_hits else
                   {"present": False, "matched": None, "content_digest": None,
                    "requirement_digest": None, "cut_window_key": None,
                    "reason": ("承担该义务的迭代（{0}）没有 RootWitness 附属文件".format(
                        marker) if marker else "该根没有 RootWitness 附属文件")})
        witness["bound_to_iteration"] = (marker if strict_hits else None)
        witness["other_iteration_witnesses"] = [
            {"sidecar": hit.get("_sidecar"),
             "content_digest": str((hit.get("witness") or {}).get("content_digest"))[:16]}
            for hit in other_iteration]
        descriptor = dict(REC12.descriptor_from_root_id(root_id) or {})
        if hits:
            descriptor = descriptor or dict(
                (hits[0].get("witness") or {}).get("root_descriptor") or {})
        digest_verdict = self._requirement_digest_verdict({
            "source_root_id": str(root_id), "root_descriptor": descriptor,
            "root_requirement_digest": None,
            "root_content_digest": witness.get("content_digest")})
        # 严格见证**自身**的要求摘要对拍（与冻结参数重算值比）：这是"绑定通过"的一半。
        # 注意：`_requirement_digest_verdict` 会在产物缺记录时回退到**任意**同根见证，
        # 因此窗口判据必须用严格见证自己的比对结果（P19 反例 M5 实测）。
        if witness.get("present"):
            recomputed = digest_verdict.get("recomputed")
            recorded = witness.get("requirement_digest")
            witness["requirement_recomputed"] = recomputed
            witness["requirement_matched"] = (None if not recomputed or not recorded
                                              else str(recorded) == str(recomputed))
        first = per_arm.get(covered_arms[0]) if covered_arms else {}
        return {"present": len(covered_arms) == len(arms),
                "covered_arms": covered_arms, "per_arm": per_arm,
                "basis": (first or {}).get("basis"),
                "channel": (first or {}).get("channel"),
                "product_path": (first or {}).get("product_path"),
                "product_iteration": (first or {}).get("product_iteration"),
                "digest_state": (first or {}).get("digest_state"),
                "root_id": (first or {}).get("root_id") or root_id,
                "root_index": (first or {}).get("root_index"),
                "root_seed": (first or {}).get("root_seed"),
                "sub_scenario": (first or {}).get("sub_scenario"),
                "opponent_mix": (first or {}).get("opponent_mix"),
                "root_descriptor": descriptor,
                # 见证口径（P16 的 sitin-root-witness/2）：内容摘要 + 截取窗口键 + 前缀/观察摘要
                "witness": witness,
                "root_content_digest": witness.get("content_digest"),
                "cut_window_key": witness.get("cut_window_key"),
                "cut_window_digest_basis": bool(witness.get("content_digest")
                                                and witness.get("cut_window_key")),
                "root_requirement_digest": digest_verdict.get("recorded"),
                "requirement_verdict": digest_verdict}

    def _refill_identity(self, iter_dir: Path, root_id: str) -> Dict[str, Any]:
        """从**家族补根评价产物**取回该根的种子/窗口/内容摘要（旧口径，仅作对照读数）。

        保留原因：家族通道若真的落了该根的补评产物，读数应与条件通道口径一致
        （"同一根的可核产物"不因通道不同而改变结论）；本方法不再单独充当判据来源。
        """

        for path in sorted((Path(iter_dir) / "family").glob("*/evaluation.json")):
            payload = read_json(path) or {}
            samples = list(payload.get("samples") or ())
            hit = [sample for sample in samples
                   if str(sample.get("source_root_id")) == str(root_id)]
            if not hit:
                continue
            sample = dict(hit[0])
            digest = str(sample.get("root_content_digest") or "")
            return {"path": str(path), "root_id": sample.get("source_root_id"),
                    "root_index": sample.get("root_index"),
                    "root_seed": sample.get("root_seed"),
                    "root_descriptor": dict(sample.get("root_descriptor") or {}),
                    "root_requirement_digest": sample.get("root_requirement_digest"),
                    "root_content_digest": sample.get("root_content_digest"),
                    # 内容摘要按构造**含** cut_window 形状键（av_family_root_content_digest
                    # 的 content.cut_window）：窗口本身不单独落盘，这里登记的是"摘要里
                    # 含窗口"的可判定事实，不冒充窗口读数。
                    "cut_window_digest_basis": bool(digest),
                    "tables_full_executed": (payload.get("panel") or {}).get(
                        "tables_full_executed")}
        return {}

    def _branch_verdict(self, seats: Mapping[str, Any],
                        epochs: Mapping[str, Any]) -> Dict[str, Any]:
        """分支可达性：**实际走到的分支**照实记录（保席是合格结果）。"""

        archive = read_archive(self.run_root)
        report = archive.get("selection_report") or {}
        kept = bool(report.get("seats_kept") or report.get("kept"))
        promoted = bool(report.get("promoted") or report.get("replaced"))
        exploration = list(seats.get("exploration") or ())
        return {
            "promotion_observed": promoted,
            "seats_kept_observed": kept or (not promoted),
            "exploration_seat_filled": bool(exploration),
            "exploration_seat": exploration,
            "note": ("真实效果未必胜出：**保席是合格结果**。晋升成功分支另外用"
                     "确定性产物证明可达（见 step4 的同签名探针与档案不变量），"
                     "不为展示晋升篡改真实结果。"),
        }

    # ---------------------------------------------------------------- 第 4 步
    def step4_exploration_seats(self) -> Dict[str, Any]:
        """探索席三条：不同签名可占 / 相同签名不可重复占 / 保席不冻结探索更新。"""

        prod = load_production()
        archive_mod = prod["archive"]
        archive = read_archive(self.run_root)
        seats = dict(archive.get("slots") or {})
        # 选择器吃的是**条目序列**（每条自带 candidate_id），不是键控映射。
        entry_rows = [dict(row) for row in (archive.get("entries") or {}).values()]
        entry_by_id = {str(row.get("candidate_id")): row for row in entry_rows}
        committed = {channel: list(seats.get(channel) or ())
                     for channel in ("overall", "exploration") + tuple(archive_mod.FAMILIES)}
        # ① 相对**提交后在案席位**复算探索席（口径 v2，不是面板视角拼接）。
        recomputed = archive_mod.select_exploration_seat(
            entry_rows,
            {key: value for key, value in committed.items() if key != "exploration"})
        expected_exploration = list(recomputed.get("slots") or ())
        recompute_report = dict(recomputed.get("report") or {})
        exploration_report = dict((archive.get("selection_report") or {})
                                  .get("exploration") or {})

        def _digest(cid: str) -> Optional[str]:
            return archive_mod.behavior_signature_digest(
                (entry_by_id.get(str(cid)) or {}).get("behavior_signature"))

        seated_signatures = {_digest(cid) for channel, cids in committed.items()
                             if channel != "exploration" for cid in cids}
        seated_signatures.discard(None)
        exploration_signatures = [sig for sig in
                                  (_digest(cid) for cid in (seats.get("exploration") or ()))
                                  if sig]
        probe = self.call_worker({"tag": "step4-same-signature-probe",
                                 "action": "probe_same_signature"})
        probe_payload = dict(probe.get("worker") or {})
        checks = [
            check("slot_selection_version_v2",
                  str(archive.get("slot_selection_version"))
                  == str(getattr(archive_mod, "SLOT_SELECTION_VERSION", None)),
                  "档案席位口径 {0}".format(archive.get("slot_selection_version"))),
            check("exploration_recomputed_from_committed",
                  sorted(expected_exploration)
                  == sorted(str(cid) for cid in (seats.get("exploration") or ())),
                  "探索席与「相对提交后在案席位」复算一致：{0}".format(
                      expected_exploration)),
            # 裁决依据（R9-ACCEPTANCE-AND-Q1-Q7-RULING §5 A4r，原文）：
            # `两个探索席之间仍可能同签名 …每选入一个候选，排除其同行为候选并记录重复来源；
            #  **无第二种行为就空第二席**；缓存和血缘仍保留`。因此**不是**要求所有在案席位
            # 互不同签名（两候选同签名 ⇒ 挑战者被规则 4 排除、探索席为空，是**正确结果**），
            # 真正的不变量是：**同一行为签名不得同时占据两个探索席**。
            check("no_duplicate_signature_in_exploration_seats",
                  len(exploration_signatures) == len(set(exploration_signatures)),
                  "两个探索席之间不得同签名（A4r 原文）：探索席 {0}｜签名 {1}｜"
                  "同签名排除记录 {2}｜在案席位签名 {3}（两候选同签名时空探索席=正确结果，"
                  "不记 FAIL）".format(
                      seats.get("exploration"), exploration_signatures,
                      json.dumps(exploration_report.get(
                          "excluded_behavior_duplicates") or {}, ensure_ascii=False)[:160],
                      sorted(sig[:12] for sig in seated_signatures))),
            check("exploration_signatures_distinct_from_seats",
                  not (set(exploration_signatures) & seated_signatures),
                  "探索席签名与在案席位无交集"),
            check("different_signature_can_take_exploration_seat",
                  bool(probe_payload.get("different_signature_seated")),
                  "不同签名条目能占探索席（生产选择器实测）"),
            check("same_signature_cannot_take_exploration_seat",
                  bool(probe_payload.get("twin_excluded"))
                  and bool(probe_payload.get("twin_not_seated")),
                  "同签名孪生被排除并登记（excluded_behavior_duplicates）"),
            # A4r 两侧构造（原文）：同签名只剩两条 ⇒ **第二探索席必须为空**；
            # 有异签名 ⇒ 两席都占且两席签名互不相同。
            check("exploration_seats_unique_signature_probe",
                  bool(probe_payload.get("twins_only_second_seat_empty"))
                  and bool(probe_payload.get("distinct_pair_seats_both_filled"))
                  and bool(probe_payload.get("distinct_pair_signatures_unique")),
                  "构造反例（生产选择器 + 合成条目）：同签名两候选 ⇒ 席位 {0}（第二席为空={1}）；"
                  "异签名候选 ⇒ 席位 {2}（两席都占={3}；签名互不相同={4}）".format(
                      probe_payload.get("twins_only_seated"),
                      probe_payload.get("twins_only_second_seat_empty"),
                      probe_payload.get("distinct_pair_seated"),
                      probe_payload.get("distinct_pair_seats_both_filled"),
                      probe_payload.get("distinct_pair_signatures_unique"))),
            # 判据口径（2026-09-18 run3 修正）：**"探索席非空"不是**"保席不冻结探索更新"的判据。
            # 正解 = 保席分支下仍然发生了"相对提交后在案席位"的**重算**，且探索席与重算结果一致；
            # 当候选池里只剩"与在案席位同行为签名的孪生"时，空探索席是**规则 4 的正确结果**。
            check("seats_kept_does_not_freeze_exploration",
                  bool(exploration_report.get("slot_selection_version"))
                  and sorted(expected_exploration)
                  == sorted(str(cid) for cid in (seats.get("exploration") or ()))
                  and "excluded_seated" in exploration_report,
                  "保席分支下仍重算了探索席（口径 {0}；排除集 {1}；同签名排除 {2}）"
                  "⇒ 探索席={3}".format(
                      exploration_report.get("slot_selection_version"),
                      list(exploration_report.get("excluded_seated") or ()),
                      json.dumps(exploration_report.get(
                          "excluded_behavior_duplicates") or {}, ensure_ascii=False)[:120],
                      seats.get("exploration"))),
        ]
        self.branches["exploration_probe"] = probe_payload
        self.branches["exploration_recompute_report"] = recompute_report
        self.branches["excluded_behavior_duplicates"] = dict(
            recompute_report.get("excluded_behavior_duplicates") or {})
        return {"step": 4, "name": "探索席三条（不同签名可占 / 同签名不可重复占 / 保席不冻结）",
                "entry": ("sitin_archive.select_exploration_seat + "
                          "rebase_exploration_seat；提交点 sitin_search._av_commit_slots"),
                "committed_seats": committed, "recomputed_exploration": expected_exploration,
                "recompute_report": recompute_report,
                "probe": probe_payload, "checks": checks, "ok": all_ok(checks)}

    # ---------------------------------------------------------------- 第 5 步
    def step5_interrupt_and_cold_resume(self) -> Dict[str, Any]:
        """「结果已落盘、结算/状态尚未完成」处受控中断 → 冷接手恢复。"""

        target = str(self.args.interrupt_at or
                     self.plan["plan_config"].get("interrupt_at") or
                     "natural:H:after_result_before_settle")
        mix = "M" if ":M:" in target else "H"
        ledger_before = read_ledger(self.run_root)
        instances_before = read_instances(self.run_root)
        spent_before = ledger_spent(ledger_before)
        digest_before = {
            str(path.relative_to(self.run_root)): sha256_file(path)
            for path in sorted(self.run_root.rglob("*")) if path.is_file()}
        marker = self.out_dir / "interrupt-marker.json"
        spec2 = self._second_iteration_spec() or {}
        injection = self.call_worker({
            "tag": "step5-inject", "action": "evolve",
            "authorization_path": str(self.auth_path),
            "interrupt_at": target, "interrupt_marker": str(marker),
            # 注入点在 natural:<mix> 上：本调用只会新执行**一个情景**的桌就被杀掉，
            # 因此按半量计（另一半由冷恢复执行），否则累计口径会虚高触发假红线。
            "budget_planned": self.natural_half("cand2"),
            "budget_scope": {"channels": ["natural"],
                             "candidate12": self.iteration_candidate12("cand2")},
            "evolve": {"generation_mode": "delegate",
                       "seed_name": spec2.get("candidate_seed_name"),
                       "predicate": spec2.get("predicate"),
                       "opponent": spec2.get("opponent"),
                       "prefix_source": spec2.get("prefix_source"),
                       "natural_roots": spec2.get("natural_roots"),
                       "natural_seats": spec2.get("natural_seats"),
                       "panel_seed": spec2.get("panel_seed")}}, timeout=10800)
        _, state_after_kill = self.latest()
        iter_dir = Path(str(state_after_kill.get("iter_dir")))
        panel_path = iter_dir / ("natural-" + mix) / "panel.json"
        panel = read_json(panel_path) or {}
        step_prefix = "natural:{0}:{1}:".format(
            str((state_after_kill.get("identity") or {}).get("candidate_id") or "")[:12],
            mix)
        rows = ledger_rows(read_ledger(self.run_root), step_prefix=step_prefix,
                           account="tables_full")
        on_disk = bool((panel.get("cost") or {}).get("tables_full_executed"))
        unsettled = [row for row in rows if str(row.get("status")) == "reserved"]
        checks = [
            check("interrupt_hit_the_fault_point",
                  bool(injection.get("interrupted")),
                  "注入点 {0} 命中并 os._exit({1})，退出码 {2}".format(
                      target, INTERRUPT_EXIT_CODE, injection.get("returncode"))),
            check("result_landed_before_interrupt", on_disk,
                  "{0} 面板结果已在盘上（tables_full_executed={1}）".format(
                      mix, (panel.get("cost") or {}).get("tables_full_executed"))),
            check("settlement_not_completed", bool(unsettled),
                  "该步账行仍为在途（未结算）{0} 行 / 共 {1} 行".format(
                      len(unsettled), len(rows))),
            check("state_not_advanced",
                  str(state_after_kill.get("status")) != "ITERATION_COMPLETE",
                  "中断时状态仍为 {0}（未完成）".format(state_after_kill.get("status"))),
        ]
        # —— 真实冷接手：**新进程** + 生产恢复入口（入口自算冻结清单再推进） ——
        resume = self.call_worker({
            "tag": "step5-cold-resume", "action": "resume",
            "authorization_path": str(self.auth_path),
            "budget_planned": self.natural_half("cand2")
            + self.planned_tables_of(category="family_fill", iteration="cand2"),
            # 冷恢复的计划量覆盖 cand2 的自然面板与家族补根：其中已在途/已完成的部分
            # 不再新增（"采用并结算"），因此带上范围声明（通道 + 候选身份）。
            "budget_scope": {"channels": ["natural", "family"],
                             "candidate12": self.iteration_candidate12("cand2")},
            "run_id": str(state_after_kill.get("run_id") or "")}, timeout=10800)
        _, state_after = self.latest()
        ledger_after = read_ledger(self.run_root)
        spent_after = ledger_spent(ledger_after)
        attempts = ((state_after.get("natural") or {}).get("attempts") or {}).get(mix) or {}
        executed = int((panel.get("cost") or {}).get("tables_full_executed") or 0)
        charged_rows = ledger_rows(ledger_after, step_prefix=step_prefix,
                                   account="tables_full")
        settled_total = sum(float(row.get("charged") or 0.0) for row in charged_rows)
        digest_after = {
            str(path.relative_to(self.run_root)): sha256_file(path)
            for path in sorted(self.run_root.rglob("*")) if path.is_file()}
        preserved = [name for name, digest in digest_before.items()
                     if name.startswith("natural-" + ("M" if mix == "H" else "H"))
                     and digest_after.get(name) == digest]
        checks.extend([
            check("cold_resume_ok", bool(resume.get("worker", {}).get("ok")),
                  "冷恢复退出码 {0}；run_id={1}".format(
                      resume.get("returncode"), state_after_kill.get("run_id"))),
            check("resume_did_not_rerun_interrupted_mix",
                  str(attempts.get("reuse") or "") in ("reconciled_result_on_disk",
                                                       "checkpoint"),
                  "该情景采用盘上结果（reuse={0}，attempt_no={1}）".format(
                      attempts.get("reuse"), attempts.get("attempt_no"))),
            check("no_double_billing_on_resume",
                  settled_total == float(executed),
                  "该情景 tables_full 结算合计 {0:.1f} = 实际执行 {1}（零重复计费）".format(
                      settled_total, executed)),
            check("completed_evidence_preserved",
                  (bool(preserved) or mix == "H"),
                  "恢复未丢失已完成证据（逐字节不变文件 {0} 个）".format(len(preserved))),
            check("iteration_finished_after_resume",
                  str(state_after.get("status")) == "ITERATION_COMPLETE",
                  "恢复后迭代终态 {0}".format(state_after.get("status"))),
            check("still_within_budget",
                  self.args.max_tables is None
                  or spent_after.get("tables_full", 0.0) <= float(self.args.max_tables),
                  "tables_full 累计 {0}".format(spent_after.get("tables_full"))),
        ])
        self.effects["interrupt_drill"] = {
            "fault_point": target, "mix": mix,
            "tables_executed_at_interrupt": executed,
            "tables_full_before": spent_before.get("tables_full"),
            "tables_full_after": spent_after.get("tables_full"),
            "instances_before": len((instances_before.get("instances") or {})),
            "instances_after": len((read_instances(self.run_root).get("instances") or {})),
            "reused_result": attempts.get("reuse"),
        }
        return {"step": 5, "name": "结果已落盘/结算未完成处受控中断 + 冷接手恢复",
                "entry": ("av_fault_point 注入（子进程内替换）+ "
                          "sitin_search.run_av_machine_resume / CLI resume"),
                "injection": injection, "resume": resume, "checks": checks,
                "ok": all_ok(checks)}

    # ---------------------------------------------------------------- 第 6 步
    def step6_feedback_and_m1_package(self) -> Dict[str, Any]:
        """原生反馈 → M1 任务包读取核对（只生成可审核任务包，不调模型）。"""

        prod = load_production()
        card = self.call_worker({"tag": "step6-m1-package", "action": "evolve",
                                 "authorization_path": str(self.auth_path),
                                 "evolve": {"generation_mode": "delegate",
                                            "seed_name": "efficiency_seed",
                                            "predicate": self.plan["iterations"][0]["predicate"],
                                            "opponent": self.plan["iterations"][0]["opponent"],
                                            "prefix_source": self.plan["iterations"][0]["prefix_source"],
                                            "natural_roots": self.plan["iterations"][0]["natural_roots"],
                                            "natural_seats": self.plan["iterations"][0]["natural_seats"],
                                            "panel_seed": self.plan["iterations"][0]["panel_seed"]}})
        _, state = self.latest()
        iter_dir = Path(str(state.get("iter_dir")))
        plan_block = dict(state.get("plan") or {})
        prompt_path = self.wait_for_prompt(state)
        prompt_text = (prompt_path.read_text(encoding="utf-8")
                       if prompt_path is not None else "")
        parent_dir = plan_block.get("parent_dir")
        feedback_path = (Path(str(parent_dir)).parent / "summary" / "feedback.json"
                         if parent_dir else None)
        feedback = read_json(feedback_path) if feedback_path else {}
        statistics = read_json(Path(str(parent_dir)).parent / "summary" / "statistics.json") \
            if parent_dir else {}
        checks = [
            check("m1_operator_scheduled", str(plan_block.get("operator")) == "m1",
                  "本轮算子 {0}（档案有席位 ⇒ M1 + 父代）".format(plan_block.get("operator"))),
            check("parent_bound", bool(parent_dir),
                  "父代目录 {0}".format(parent_dir)),
            check("parent_feedback_executable",
                  bool((feedback or {}).get("executable"))
                  and not list((feedback or {}).get("refusals") or ()),
                  "父代三段反馈 executable={0}".format((feedback or {}).get("executable"))),
            check("m1_package_emitted", prompt_path is not None,
                  "可审核任务包 {0}（delegate 停等，未调用任何模型）".format(prompt_path)),
            check("no_feedback_refusal", not state.get("feedback_refusal"),
                  "未触发 AvFeedbackRefused"),
            check("numbers_match_statistics",
                  self._numbers_in_text(prompt_text, statistics),
                  "任务包里的数字能在 summary/statistics.json 中找到同源读数"),
            check("confirmation_data_not_visible",
                  not any(token in prompt_text.lower()
                          for token in ("confirmation_eligible", "root_usage",
                                        "confirm_budget", "确认结果")),
                  "确认用途/确认预算/确认结果均未进入任务包"),
            check("evidence_locators_present",
                  str(prompt_path and str(iter_dir)) is not None
                  and ("summary" in prompt_text or "feedback" in prompt_text
                       or "证据" in prompt_text),
                  "任务包带证据定位（产物路径/定位指针）"),
        ]
        self.effects["m1_package"] = {
            "prompt_path": str(prompt_path), "prompt_sha256":
                sha256_file(prompt_path) if prompt_path else None,
            "parent_dir": parent_dir,
            "feedback_executable": (feedback or {}).get("executable"),
            "feedback_status": (feedback or {}).get("status"),
        }
        return {"step": 6, "name": "原生反馈 → M1 任务包读取核对（不调模型）",
                "entry": ("_step_summarize → sitin_feedback.build_three_segment_feedback；"
                          "M1 生成步 _av_generation_packet → pending/m1/prompt.txt"),
                "worker": card, "checks": checks, "ok": all_ok(checks)}

    @staticmethod
    def _numbers_in_text(text: str, statistics: Any) -> bool:
        """任务包里的数字必须能在统计产物里找到同源读数（不做模糊匹配）。"""

        if not isinstance(statistics, Mapping):
            return False
        values = set()

        def walk(node: Any) -> None:
            if isinstance(node, Mapping):
                for item in node.values():
                    walk(item)
            elif isinstance(node, (list, tuple)):
                for item in node:
                    walk(item)
            elif isinstance(node, (int, float)) and not isinstance(node, bool):
                values.add(round(float(node), 6))

        walk(statistics)
        if not values:
            return False
        hits = 0
        for token in text.replace(",", " ").split():
            try:
                number = float(token.strip("%（）(),；;：:"))
            except ValueError:
                continue
            if round(number, 6) in values:
                hits += 1
        return hits > 0

    # ---------------------------------------------------------------- 步骤分派
    def run_step(self, number: int) -> Dict[str, Any]:
        """按步号执行（供 run_all 与单步复跑共用同一入口）。"""

        if int(number) == 1:
            return self.step1_fresh_identity_and_family()
        if int(number) == 2:
            return self.step2_conditional_root()
        if int(number) == 3:
            return self.step3_seats(with_interrupt=self.args.steps_include(5))
        if int(number) == 4:
            return self.step4_exploration_seats()
        if int(number) == 5:
            return self.step5_interrupt_and_cold_resume()
        if int(number) == 6:
            return self.step6_feedback_and_m1_package()
        raise SystemExit("未知步骤号 {0}".format(number))

    def prior_steps(self) -> Dict[str, Any]:
        """只读复算时的**能力覆盖来源**：原运行报告里的逐步判定行（0 桌）。

        为什么需要：`--recheck` 只复算对账，不重跑步骤 ⇒ `self.steps` 为空。
        但"能力覆盖"不能被渲染成 NOT_APPLICABLE —— 那些步骤**确实执行过**，
        证据就在原运行的 `gate2-run.json` 里。因此读原报告并**显式标注来源**，
        与"本次真的跑了"区分开（`executed_in_this_invocation=false`）。
        """

        candidates = [self.out_dir / "gate2-run.json",
                      _project_file(_PROJECT_ROOT, GATE2_DIR / "run" / Path(self.run_root).name / "gate2-run.json")]
        for path in candidates:
            if not path.is_file():
                continue
            report = read_json(path) or {}
            steps = [row for row in (report.get("steps") or ())]
            if steps:
                return {"source": str(path), "steps": steps,
                        "executed_in_this_invocation": False}
        return {"source": None, "steps": [], "executed_in_this_invocation": False}

    # ------------------------------------------- 必要能力：从最终产物重算（Q4/复审 C2）
    def _conditional_root_from_products(self) -> Dict[str, Any]:
        """从**最终产物**读第 2 步的根读数（不依赖执行期内存，只读）。"""

        for iter_dir in iter_dirs(self.run_root):
            payload = read_json(iter_dir / "conditional" / "evaluation.json") or {}
            for sample in (payload.get("samples") or ()):
                if not isinstance(sample, Mapping):
                    continue
                descriptor = dict(sample.get("root_descriptor") or {})
                root_id = str(sample.get("source_root_id")
                              or descriptor.get("root_id") or "")
                if not root_id:
                    continue
                seed = sample.get("root_seed")
                if seed is None:
                    seed = descriptor.get("root_seed")
                return {"iter_dir": iter_dir, "path": iter_dir / "conditional"
                        / "evaluation.json", "sample": dict(sample),
                        "root_id": root_id, "root_seed": seed,
                        "root_content_digest": sample.get("root_content_digest"),
                        "descriptor": descriptor}
        return {}

    def _recompute_conditional_root_check(self, name: str,
                                          read: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """重算第 2 步的`根已进家族登记 / 种子一致 / 内容摘要已落盘`三条。

        读数规则（**区分检查器误分类与旧产物确实缺摘要**）：

        - 登记表**不存在** ⇒ INSUFFICIENT（档案步没落盘，登记不可核），不是 N/A；
        - 登记表存在而该根不在表里 ⇒ FAIL（根没进登记）；
        - 内容摘要：样本自带 ⇒ PASS（来源=样本字段）；否则看该根的 RootWitness
          （P11 附属文件）的 `content_digest` ⇒ PASS（来源具名）；两者都没有
          ⇒ INSUFFICIENT（旧产物确实缺摘要，不事后自签一个期望摘要）。
        """

        roots = read_family_roots(self.run_root)
        rows = [dict(row) for _channel, block in (roots.get("channels") or {}).items()
                for row in ((block or {}).get("roots") or ())]
        match = [row for row in rows
                 if str(row.get("root_id")) == str(read.get("root_id"))]
        registry_present = bool(rows)
        if name == "root_registered_in_family_registry":
            if not registry_present:
                return check(name, False,
                             "档案步未落盘（archive/family-roots.json 无登记行）⇒ "
                             "登记不可核：记 INSUFFICIENT（不是 N/A，也不是通过）",
                             insufficient=True,
                             final_product_source="archive/family-roots.json")
            return check(name, bool(match),
                         "最终产物重算：{0} 在家族登记表里{1}（{2} 行）".format(
                             read.get("root_id"), "存在" if match else "**不存在**",
                             len(rows)),
                         final_product_source="archive/family-roots.json")
        if name == "root_seed_consistent":
            if not registry_present or not match:
                return check(name, False,
                             "没有可核的登记行 ⇒ 种子一致性记 INSUFFICIENT",
                             insufficient=True,
                             final_product_source="archive/family-roots.json")
            ok = int(match[0].get("root_seed") or -1) == int(read.get("root_seed") or -2)
            return check(name, ok,
                         "最终产物重算：登记种子 {0} / 样本种子 {1}".format(
                             match[0].get("root_seed"), read.get("root_seed")),
                         final_product_source="archive/family-roots.json")
        if name == "root_content_digest_persisted":
            if read.get("root_content_digest"):
                return check(name, True,
                             "样本自带根内容摘要 {0}".format(
                                 str(read.get("root_content_digest"))[:16]),
                             final_product_source="conditional/evaluation.json#samples")
            hits = REC12.witnesses_by_root(Path(self.run_root)).get(
                str(read.get("root_id")) or "") or []
            witness = dict((hits[0].get("witness") if hits else {}) or {})
            if witness.get("content_digest"):
                return check(name, True,
                             "内容摘要已落盘（来源=RootWitness 附属文件 "
                             "root-witnesses.jsonl）：{0}；见证记录的要求摘要 {1}"
                             "（一致性由本步 requirement_digest_matched 另判）".format(
                                 str(witness.get("content_digest"))[:16],
                                 str(witness.get("requirement_digest"))[:16]),
                             final_product_source="conditional/root-witnesses.jsonl")
            return check(name, False,
                         "**旧产物确实缺内容摘要**：样本没有 root_content_digest，"
                         "该根也没有 RootWitness ⇒ 记 INSUFFICIENT（不事后自签期望摘要）",
                         insufficient=True,
                         final_product_source="conditional/evaluation.json + witnesses 均缺")
        return None

    def recompute_necessary_capabilities(self, steps: Sequence[Mapping[str, Any]]
                                         ) -> Tuple[List[Dict[str, Any]],
                                                    Dict[str, Any]]:
        """从最终产物重算**必要能力**（复审：N/A 不得永久卡住；缺摘要留 INSUFFICIENT）。

        当前重算范围：第 2 步`普通条件入口生成至少一个根 → 家族登记`的三条——
        执行该步时档案步还没跑，旧实现把它们写成 `applicable=False`（N/A）并被永久卡住；
        签收时用最终产物（family-roots.json / root-witnesses.jsonl）重算，读数分列
        PASS / INSUFFICIENT / FAIL。
        """

        out = [dict(row) for row in steps]
        report: Dict[str, Any] = {"schema": "sitin-gate2-necessary-capabilities/1",
                                 "steps_seen": [row.get("step") for row in out],
                                 "read_from": "最终产物（只读）", "recomputed": [],
                                 "unresolved_not_applicable": [], "note": ""}
        read = self._conditional_root_from_products()
        for index, row in enumerate(out):
            if int(row.get("step") or 0) != 2 or not read:
                continue
            checks = [dict(item) for item in (row.get("checks") or ())]
            changed = []
            for position, item in enumerate(checks):
                name = str(item.get("name"))
                fresh = self._recompute_conditional_root_check(name, read)
                if fresh is None:
                    continue
                fresh.update({
                    "recomputed_from_final_products": True,
                    "original_status": STATUS12.check_status(item),
                    "original_applicable": bool(item.get("applicable", True)),
                    "recompute_note": ("执行该步时产物尚未落盘（旧读法 {0}）；"
                                       "签收时按最终产物重算").format(
                                           STATUS12.check_status(item))})
                changed.append(name)
                checks[position] = fresh
            if not changed:
                continue
            row["checks"] = checks
            row["ok"] = all_ok(checks)
            row["necessary_capabilities_recomputed"] = changed
            row["conditional_root_read"] = {"root_id": read.get("root_id"),
                                            "root_seed": read.get("root_seed"),
                                            "source": str(read.get("path"))}
            out[index] = row
            report["recomputed"].append({
                "step": 2, "checks": changed,
                "statuses": {str(item.get("name")): STATUS12.check_status(item)
                             for item in checks if str(item.get("name")) in changed},
                "root_id": read.get("root_id"),
                "source": str(read.get("path"))})
        for row in out:
            for item in (row.get("checks") or ()):
                if STATUS12.check_status(item) == STATUS12.NOT_APPLICABLE:
                    report["unresolved_not_applicable"].append(
                        {"step": row.get("step"), "name": item.get("name"),
                         "detail": str(item.get("detail"))[:160]})
        report["note"] = ("必要能力不得靠 NOT_APPLICABLE 排除：能从最终产物重算的一律重算；"
                          "重算后仍为 N/A 的行如实列出，交由签收把它读成收缩范围。")
        return out, report

    # ---------------------------------------------------------------- 全局对账
    def reconcile(self) -> Dict[str, Any]:
        """逐实例对账 + 复审 §7 通过标准（0 丢失/0 重复计费/0 未解释冲突/0 假完成）。"""

        planned = self.plan["budget"]["by_category"]
        by_name = {row["category"]: row for row in planned}
        ledger = read_ledger(self.run_root)
        spent = ledger_spent(ledger)
        instances = read_instances(self.run_root)
        # —— G1：按**冻结实例键**逐项连接 计划 ↔ 尝试 ↔ 结果 ↔ 费用（P12）——
        # 旧口径（len(所有实例行) ≥ 计划自然实例数）被裁定 §5 G1 否决：别的通道多出的
        # 记录会掩盖目标实例缺失。join 逐通道分开算，谁也补不了谁。
        join = REC12.reconcile_instances(self.run_root, self.plan)
        rows: List[Dict[str, Any]] = REC12.instance_rows(join)
        per_mix: Dict[str, Dict[str, int]] = {}
        for row in rows:
            bucket = per_mix.setdefault(str(row["opponent_mix"]), {})
            bucket[str(row["status"])] = bucket.get(str(row["status"]), 0) + 1
        aborted_rows = [
            {"iteration": row["iteration"], "mix": row["opponent_mix"],
             "root": str(row["source_root_id"])[-28:], "seat": row["seat"],
             "arm": row["arm"], "schedule": row["schedule"]}
            for row in rows
            if str(row["status"]) in (REC12.TERMINAL_FAILED, REC12.TERMINAL_BUDGET,
                                      REC12.TERMINAL_UNFINISHED)]
        aborted_reasons: Dict[str, int] = {}
        for row in aborted_rows:
            key = str(row.get("reason") or "未记原因")[:60]
            aborted_reasons[key] = aborted_reasons.get(key, 0) + 1
        conflicts = collect_instance_conflicts(self.run_root)
        double = collect_double_billing(ledger)
        fake = collect_fake_completions(self.run_root)
        family_roots = read_family_roots(self.run_root)
        registry_conflicts = list(family_roots.get("conflicts") or ())
        family_registry = (read_family_roots(self.run_root) or {}).get("channels") or {}
        registry_rows = [row for channel, block in family_registry.items()
                         for row in ((block or {}).get("roots") or ())]
        expected_natural = int(by_name["natural_full"]["n_instances"])
        # 整链判据只在最后一个迭代走到终态时适用；只跑 1,2 步的接线干跑不得被它判失败
        # （但也不能写成"通过"——报告里渲染成 N/A 并给原因）。
        chain = self.chain_complete()
        # 家族核心矩阵**逐格**验收（子场景侧 × 对手情景，每格根数取计划配置）：
        # 只数总数会把「8 根全是 branch_open」误判成齐备（2026-09-18 run3 实测）。
        # 但**登记行数仍然不够**：登记只说明"根被登记过"，不说明"某个候选在该根上有可核
        # 评价"。因此矩阵判据改用 P12 预算生成器的逐键覆盖（候选 × 核心根 × 臂）。
        required_per_cell = int(
            ((self.plan.get("frozen_inputs") or {}).get("family_config") or {})
            .get("cells_roots_per_cell") or 0)
        cells: Dict[str, int] = {}
        for row in registry_rows:
            key = "{0}|{1}".format(row.get("sub_scenario"), row.get("opponent_mix"))
            cells[key] = cells.get(key, 0) + 1
        for sub in (((self.plan.get("frozen_inputs") or {}).get("family_config") or {})
                    .get("sub_scenarios") or ()):
            for mix in ("H", "M"):
                cells.setdefault("{0}|{1}".format(sub, mix), 0)
        missing_cells = sorted(key for key, count in sorted(cells.items())
                               if count < required_per_cell)
        budget_gap = BUDGET12.comparison_gap(plan=self.plan, run_root=self.run_root)
        incomplete_rows = [row for row in rows
                           if str(row["status"]) != REC12.TERMINAL_COMPLETED]
        matrix = {"cells": dict(sorted(cells.items())),
                  "required_per_cell": required_per_cell,
                  "missing": missing_cells,
                  "registry_complete": bool(cells) and not missing_cells,
                  "per_candidate_coverage": budget_gap.get("per_candidate"),
                  "missing_core_edges": budget_gap.get("missing_core_edges") or [],
                  "complete": bool(cells) and not missing_cells
                  and not budget_gap.get("missing_core_edges")}
        chain_note = ("；本次运行只到 {0}（未跑整链），本判据不适用（不是通过）".format(
            (self.latest()[1] or {}).get("status")) if not chain else "")
        # 判定行由 P12 逐键对账生成（四项不变量 + 功能完成 + 摘要可核 + 费用 join）；
        # 家族矩阵另用**预算生成器的逐键覆盖**判据（见下），不再数登记行数。
        checks = [dict(row) for row in REC12.check_rows(join)]
        checks.extend([
            check("zero_double_billing", not double,
                  "同 (step_id, account) 不存在多条非 superseded 的 settled 行"
                  "（同一实例的多次尝试**不是**重复收费：失败重试有真实成本，"
                  "已按 superseded 单列）",
                  duplicates=double[:5]),
            check("zero_unexplained_identity_conflicts",
                  not conflicts and not registry_conflicts,
                  "实例台账身份冲突 {0} 条；家族根登记冲突 {1} 条".format(
                      len(conflicts), len(registry_conflicts)),
                  instance_conflicts=conflicts[:5],
                  registry_conflicts=registry_conflicts[:5]),
            # zero_fake_completions 由 REC12.check_rows 提供（按生产 schema 重算）；
            # 这里只补一条"文件级"读数，便于与 collect_fake_completions 对拍。
            check("fake_completions_file_level", not fake,
                  "completed 尝试的结果摘要按生产 schema 重算一致"
                  "（自然面板=嵌套臂结果块 canonical sha256；家族/条件=整文件 sha256）",
                  fakes=fake[:5], recomputed_mismatches=len(fake)),
            check("exit_no_aborted_instances",
                  not aborted_rows and not incomplete_rows,
                  "逐情景终态分布 {0}｜未完成可核实例 {1} 条：{2}".format(
                      per_mix, len(aborted_rows),
                      json.dumps(aborted_reasons, ensure_ascii=False)[:300]),
                  applicable=bool(per_mix),
                  per_mix=per_mix, aborted=aborted_rows[:20]),
            check("family_core_matrix_complete",
                  not budget_gap.get("missing_core_edges"),
                  "家族共同根矩阵**逐候选 × 逐核心根 × 逐臂**验收（不数登记行数）："
                  "缺边 {0} 条（{1} 桌）：{2}{3}".format(
                      len(budget_gap.get("missing_core_edges") or ()),
                      budget_gap.get("missing_core_tables"),
                      json.dumps(budget_gap.get("per_candidate") or [],
                                 ensure_ascii=False), chain_note),
                  applicable=chain and self.second_candidate_declared(),
                  missing_core_edges=(budget_gap.get("missing_core_edges") or [])[:20],
                  per_candidate=budget_gap.get("per_candidate"),
                  production_reported_missing=(budget_gap.get(
                      "production_reported_missing") or {})),
        ])
        redline_rows: List[Dict[str, Any]] = []
        redline_adoption_rows: List[Dict[str, Any]] = []
        redline_exceeded_rows: List[Dict[str, Any]] = []
        if self.redline_log.is_file():
            for line in self.redline_log.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    try:
                        redline_rows.append(json.loads(line))
                    except ValueError:
                        redline_rows.append({"schema": "unparsable", "line": line[:120]})
        # 红线读数判据（2026-09-18 run4 后）：允许 within_cap / within_cap_with_adoption；
        # 但"依赖采用"的行必须**带盘上证据**（overlap_rows 全部有真实 step_id + 已执行结果），
        # 否则算失败 —— 红线不得被改废。
        for row in redline_rows:
            verdict = str(row.get("verdict"))
            if verdict == "exceeds_cap":
                redline_exceeded_rows.append(row)
            elif verdict == "within_cap_with_adoption":
                evidence_ok = all(item.get("step_id") for item in
                                  (row.get("overlap_rows") or ())) and bool(
                                      row.get("overlap_rows"))
                if not evidence_ok:
                    redline_exceeded_rows.append(dict(row, missing_evidence=True))
                else:
                    redline_adoption_rows.append(row)
        redline_ok = bool(redline_rows) and not redline_exceeded_rows and all(
            str(row.get("verdict")) in ("within_cap", "within_cap_with_adoption")
            for row in redline_rows)
        checks.extend([
            check("cap_not_raised_above_plan",
                  float(self.cap) <= float(self.cap_default) + 1e-9,
                  "有效封顶 {0:.1f} ≤ 计划可执行桌数 {1:.1f}（默认值，永不允许更高）".format(
                      self.cap, self.cap_default)),
            check("budget_redline_logged", redline_ok,
                  ("预算红线读数 {0} 条，全部不超封顶（每条含 已结算/在途/本次新增计划/"
                   "扣减项与证据/封顶/来源；`within_cap_with_adoption` 表示本次判定依赖"
                   "「采用盘上结果」，必须有盘上证据才允许）".format(len(redline_rows))
                   if redline_rows else
                   "只读复算（--recheck）不产生新的红线读数；原运行的红线日志在"
                   "它自己的证据目录里，本判据在本模式下不适用（不是通过）"),
                  applicable=bool(redline_rows) or not getattr(self.args, "recheck",
                                                               False),
                  rows=redline_rows,
                  adoption_rows=redline_adoption_rows,
                  exceeded_rows=redline_exceeded_rows),
        ])
        stop = self._stop_reason_recompute()
        checks.append(check(
            "stop_reason_recomputable", stop["match"],
            "批末停止原因 {0} / 程序重算 {1}{2}".format(
                stop.get("reported"), stop.get("recomputed"), chain_note),
            applicable=chain,
            reported=stop.get("reported"), recomputed=stop.get("recomputed")))
        nxt = self._next_action_recompute()
        checks.append(check(
            "next_action_recomputable", nxt["match"],
            "批末下一动作 {0} / 程序重算 {1}{2}".format(
                nxt.get("reported"), nxt.get("recomputed"), chain_note),
            applicable=chain,
            reported=nxt.get("reported"), recomputed=nxt.get("recomputed")))
        # Q4：**分项签收** —— 四项对账不变量与六步能力覆盖分开出状态；
        # 整链状态 = 各分项中最差者（分项通过不得写成整链通过）。
        capability_source = "本次执行"
        capability_steps = list(self.steps)
        if not capability_steps:
            prior = self.prior_steps()
            if prior.get("steps"):
                capability_steps = list(prior["steps"])
                capability_source = "原运行报告（只读复算：未重新执行）{0}".format(
                    prior.get("source"))
        # 复审`最终状态统一`：**从最终产物重算必要能力**——执行期因产物尚未落盘而写成
        # N/A 的判据（第 2 步的根登记/种子/内容摘要）不得被早期 N/A 永久卡住；
        # 重算后仍缺证据的记 INSUFFICIENT（旧产物确实缺摘要），绝不当成通过。
        capability_steps, capability_recompute = self.recompute_necessary_capabilities(
            capability_steps)
        checks.append(check(
            "necessary_capabilities_recomputed",
            bool(capability_recompute.get("recomputed"))
            or not capability_recompute.get("unresolved_not_applicable"),
            ("必要能力重算（最终产物）：重算 {0} 项；重算后仍为 NOT_APPLICABLE 的判定行 "
             "{1} 条（N/A 不得用来排除必要能力）").format(
                len(capability_recompute.get("recomputed") or ()),
                len(capability_recompute.get("unresolved_not_applicable") or ())),
            applicable=True,
            insufficient=bool(capability_recompute.get("unresolved_not_applicable"))
            and not capability_recompute.get("recomputed"),
            report=capability_recompute))
        capability_rows = {int(step.get("step")): list(step.get("checks") or ())
                           for step in capability_steps}
        budget_rows = [
            {"name": "budget:" + str(row.get("name")), "ok": bool(row.get("ok")),
             "applicable": True, "insufficient": bool(row.get("insufficient")),
             "detail": row.get("detail")}
            for row in ((self.budget_preflight or {}).get("checks") or ())]
        signoff = STATUS12.sign_off(reconciliation_rows=checks,
                                    capability_rows=capability_rows,
                                    budget_rows=budget_rows)
        signoff["capability_source"] = capability_source
        signoff["capability_steps_seen"] = len(capability_steps)
        checks.append(check(
            "capability_coverage_wired",
            bool(capability_steps) and sum(
                len(list(step.get("checks") or ())) for step in capability_steps) > 0,
            "六步能力覆盖的判定行来源：{0}；读到 {1} 步 / {2} 条判定行"
            "（空 ⇒ 才可记 N/A；已执行过却渲染成 N/A 属于「用 0 错误签收未执行路径」）"
            .format(capability_source, len(capability_steps),
                    sum(len(list(step.get("checks") or ()))
                        for step in capability_steps)),
            applicable=True,
            insufficient=False,
            source=capability_source))
        if self.steps:
            # 本次执行：把重算后的判定行写回执行器，报告 §1 用最终口径渲染。
            self.steps = capability_steps
        return {"instance_rows": rows, "per_mix_status": per_mix,
                "planned_by_category": planned,
                "spent": spent,
                "instance_join": {key: value for key, value in join.items()
                                  if key != "conditional_index"},
                "budget_comparison_gap": budget_gap,
                "matrix": matrix,
                "signoff": signoff,
                "necessary_capabilities": capability_recompute,
                "checks": checks, "ok": all_ok(checks),
                "totals": {"instances": len(rows),
                           "planned_instances": int(self.plan["budget"]["total_instances"]),
                           "planned_tables": float(self.plan["budget"]["total_planned_tables"]),
                           "charged_tables_full": spent.get("tables_full", 0.0),
                           "charged_tables_partial": spent.get("tables_partial", 0.0),
                           "charged_prefix_generation": spent.get("prefix_generation", 0.0)}}

    def _completed_iteration(self) -> Tuple[Optional[Path], Dict[str, Any]]:
        """**最后一个已完成的迭代**（带 batch-report.json 的那一个）。

        step6 会新开一个"等回复"的迭代，它不是被验收的批末；停止原因与下一动作
        必须取自真正跑完的那一轮，否则会把 N/A/None 当成读数（run3 实测踩过）。
        """

        chosen: Tuple[Optional[Path], Dict[str, Any]] = (None, {})
        for iter_dir in iter_dirs(self.run_root):
            if (iter_dir / "batch-report.json").is_file():
                chosen = (iter_dir, read_state(iter_dir / "state.json"))
        return chosen

    def _stop_reason_recompute(self) -> Dict[str, Any]:
        """停止原因可由程序重算（照抄生产 _step_batch_end 的判据，不靠人眼看）。"""

        path, state = self._completed_iteration()
        if not state:
            return {"match": False, "reported": None, "recomputed": None}
        iter_dir = Path(str(state.get("iter_dir")))
        report = read_json(iter_dir / "batch-report.json") or {}
        reported = report.get("stop_reason")
        recomputed = state.get("stop_reason")
        if not recomputed:
            gaps = state.get("input_gaps") or []
            recomputed = ("input_gap:{0}".format(",".join(gaps)) if gaps
                          else "completed_proposal_budget")
        return {"match": bool(reported) and reported == recomputed,
                "reported": reported, "recomputed": recomputed}

    def _next_action_recompute(self) -> Dict[str, Any]:
        """下一动作可由程序重算：next_generation_plan(archive, history) 纯函数。"""

        prod = load_production()
        archive_mod = prod["archive"]
        search = prod["search"]
        path, state = self._completed_iteration()
        if not state:
            return {"match": False, "reported": None, "recomputed": None}
        iter_dir = Path(str(state.get("iter_dir")))
        report = read_json(iter_dir / "batch-report.json") or {}
        reported = report.get("next_task_package") or {}
        archive = read_archive(self.run_root)
        history = search._av_plan_history(self.run_root)  # noqa: SLF001 - 生产同源
        plan_next = archive_mod.next_generation_plan(archive, history)
        recomputed = {"proposal_no": plan_next.get("proposal_no"),
                      "operator": plan_next.get("operator"),
                      "parent_candidate_id": plan_next.get("parent_candidate_id"),
                      "channel": plan_next.get("channel"),
                      "family": plan_next.get("family")}
        keys = ("proposal_no", "operator", "parent_candidate_id", "channel", "family")
        return {"match": all(str(reported.get(key)) == str(recomputed.get(key))
                             for key in keys),
                "reported": {key: reported.get(key) for key in keys},
                "recomputed": recomputed}

    # ---------------------------------------------------------------- 报告
    def markdown(self, *, run_id: str, reconciliation: Mapping[str, Any],
                 evidence_kind: str) -> str:
        lines: List[str] = []
        add = lines.append
        add("# 关口二执行报告（{0}）".format(run_id))
        add("")
        add("> **范围声明**：{0}".format(evidence_kind))
        add("")
        add("> **样本身份（评审 §8）**：本报告的样本全部来自**生产本地模拟器实执行，"
            "非测试替身**（`runtime_kind=real_simulation_engine`、"
            "`engine_kind=simulation_engine_public`）；**不是**官方平台赛事验证，"
            "也不是仿真/夹具结果。")
        add("")
        add("- 生成时间：{0}".format(utc_now()))
        add("- **头部/回归数字的来源**：本报告只声明**本次实际提交的读数**"
            "（未跑的部分一律写 NOT_APPLICABLE 或 INSUFFICIENT），"
            "不统称「最新版本全量复跑」；工具回归与全量回归的数字按各自实际提交分别注明。")
        add("- **批次/运行标签**：{0}（进授权文件、运行目录、报告与全部产物；"
            "历史标签 batch7*/rep1/rep2/r6*/r7*/r8* 一律拒绝）".format(self.batch_label))
        add("- 计划：{0}".format(self.plan.get("schema")))
        add("- 运行根目录：{0}".format(self.run_root))
        add("- 授权留档：{0}；预算红线读数：{1}".format(
            self.auth_archive, self.redline_log))
        add("- 封顶：{0:.1f} 桌（来源：{1}）".format(
            self.cap, "调用方 --max-tables" if getattr(self.args, "max_tables", None)
            is not None else "计划可执行桌数（默认，且永不允许更高）"))
        add("- 树状态 HEAD：{0}（脏文件 {1} 个，tree_digest={2}）".format(
            (self.tree_state_before.get("git_head") or "?")[:12],
            len(self.tree_state_before.get("git_dirty_paths") or []),
            str(self.tree_state_before.get("tree_digest"))[:16]))
        add("")
        add("## 1. 逐步清单（复审 §7 六个步骤）")
        add("")
        add("| 步 | 验收动作 | 真实入口 | 结果 | 断言（通过/全部） |")
        add("| --- | --- | --- | --- | --- |")
        for step in self.steps:
            rows = list(step.get("checks") or ())
            applicable = [row for row in rows if row.get("applicable", True)]
            add("| {0} | {1} | {2} | {3} | {4}/{5}（N/A {6}） |".format(
                step.get("step"), step.get("name"), str(step.get("entry"))[:70],
                "PASS" if step.get("ok") else ("SKIP" if step.get("skipped") else "FAIL"),
                sum(1 for row in applicable if row.get("ok")), len(applicable),
                len(rows) - len(applicable)))
        add("")
        add("## 2. 逐实例对账表")
        add("")
        add("| 迭代 | 候选 | 情景 | 来源根 | 座位 | 臂 | 赛程 | 范围 | 尝试 | 终态 | 桌数/计划 |")
        add("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for row in (reconciliation.get("instance_rows") or ())[:400]:
            add("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} | {9} | {10}/{11} |".format(
                row["iteration"], row["candidate_id"], row["opponent_mix"],
                str(row["source_root_id"])[-28:], row["seat"], row["arm"],
                str(row["schedule"])[:26], row["scope"], row["attempts"],
                row["status"], row["tables"], row["planned_tables"]))
        if not reconciliation.get("instance_rows"):
            add("| — | — | — | — | — | — | — | — | — | — | — |")
        add("")
        add("计划分类数：{0}".format(json.dumps(
            [{row["category"]: row["n_instances"]}
             for row in reconciliation.get("planned_by_category") or ()],
            ensure_ascii=False)))
        add("")
        add("账目实际：{0}".format(json.dumps(reconciliation.get("spent") or {},
                                             ensure_ascii=False)))
        add("")
        formula = self.plan.get("natural_formula_reconciliation") or {}
        if formula:
            add("计划口径（Lead 裁定）：**生产分解 {0:.0f} 桌为准**；复审公式 {1:.0f} 桌"
                "为保守上界（差异 {2:.0f} 桌：自然面板的根按情景分桶、每根只属一个情景，"
                "复审公式重复乘了情景数）。".format(
                    float(formula.get("production_tables") or 0),
                    float(formula.get("review_formula_tables") or 0),
                    float(formula.get("delta_tables") or 0)))
            add("")
        add("## 2b. 授权派生（计划类目 → 账本账户 → 额度）")
        add("")
        deriv = self.derivation
        add("| 计划类目 | 账本账户 | 实例数 | 计划桌数 | 口径 |")
        add("| --- | --- | ---: | ---: | --- |")
        for row in deriv["mapping_table"]:
            add("| {0} | {1} | {2} | {3} | {4} |".format(
                row["category"], row["account"], row["n_instances"],
                ("{0:.1f}".format(row["planned_tables"]) if row["present_in_plan"] else "—"),
                ("在计划内" if row["present_in_plan"] else "计划内无此类目（按 0 计）")))
        add("")
        add("**逐账户派生明细**（每一项都带口径，不含拍出来的常数）")
        add("")
        for account, terms in sorted((deriv.get("account_terms") or {}).items()):
            add("- `{0}` = {1:.1f}".format(account, deriv["accounts"][account]))
            for term in terms:
                add("  - {0}：{1:.1f}（{2}）".format(
                    term.get("category") or term.get("source"),
                    float(term.get("tables", term.get("value", 0.0))),
                    term.get("basis")))
        add("- `tokens_input`/`tokens_output` = 0（零模型调用）；"
            "`confirm_reserved` = 0（确认账本不动用）")
        add("")
        add("**交叉核对**")
        add("")
        for row in deriv["cross_checks"]:
            add("- [{0}] {1}｜{2}".format("OK" if row["ok"] else "FAIL",
                                          row["name"], row["reading"]))
        add("")
        add("## 2c. 先前运行已消耗的真实桌数（失败不等于没花钱）")
        add("")
        prior = self.prior_consumption
        if prior.get("runs"):
            add("| 先前运行目录 | 状态 | tables_full | tables_partial | prefix_generation |")
            add("| --- | --- | ---: | ---: | ---: |")
            for row in prior["runs"]:
                spent = row.get("spent") or {}
                states = ",".join(
                    "{0}={1}".format(name, (value or {}).get("status"))
                    for name, value in (row.get("iterations") or {}).items())
                add("| {0} | {1} | {2} | {3} | {4} |".format(
                    row["run_root"], states or "—", spent.get("tables_full"),
                    spent.get("tables_partial"), spent.get("prefix_generation")))
            add("")
            add("先前运行合计：{0}".format(json.dumps(prior.get("totals") or {},
                                                     ensure_ascii=False)))
        else:
            add("（本次未登记先前运行）")
        add("")
        add("## 3. 通过标准（复审 §7）—— 四词状态：PASS / INSUFFICIENT / FAIL / NOT_APPLICABLE")
        add("")
        add("| 判据 | 状态 | 读数 |")
        add("| --- | --- | --- |")
        for row in (reconciliation.get("checks") or ()):
            add("| {0} | {1} | {2} |".format(
                row["name"], STATUS12.check_status(row),
                str(row.get("detail")).replace("|", "/")))
        for step in self.steps:
            for row in (step.get("checks") or ()):
                add("| 步{0}·{1} | {2} | {3} |".format(
                    step.get("step"), row["name"], STATUS12.check_status(row),
                    str(row.get("detail")).replace("|", "/")))
        add("")
        add("### 3a. 分项签收（四项对账不变量 / 六步能力覆盖**分开**，不互相补齐）")
        add("")
        signoff = reconciliation.get("signoff") or {}
        if signoff:
            add(STATUS12.render(signoff))
        add("")
        add("## 3b. 授权形态与预算预检（Q6 / G2）")
        add("")
        add("- 授权形态：**{0}**（审计字段 `authorization_form`；"
            "legacy=`authorized+batch=7+budgets`，新形态=`sitin-authorization/1`，"
            "同文档双形态=`dual`）".format(
                (getattr(self, "authorization_check", None) or {}).get(
                    "authorization_form") or "未校验"))
        add("- 统一校验结论：{0}".format(json.dumps(
            {key: value for key, value in (getattr(self, "authorization_check", None)
                                           or {}).items()
             if key in ("ok", "authorization_id", "trusted", "issued_by",
                        "issued_at_utc", "operations", "problems")},
            ensure_ascii=False)))
        gap = reconciliation.get("budget_comparison_gap") or {}
        if gap:
            add("- 完整比较缺边：{0} 条（{1} 桌）；逐候选覆盖 {2}".format(
                len(gap.get("missing_core_edges") or ()), gap.get("missing_core_tables"),
                json.dumps(gap.get("per_candidate") or (), ensure_ascii=False)))
            add("- 指定旧根重评 {0} 条（缺 {1}）与新刷新根发现 {2} 条（缺 {3}）**分列**；"
                "生产停止原因 {4}".format(
                    (gap.get("old_root_review") or {}).get("total"),
                    (gap.get("old_root_review") or {}).get("missing"),
                    (gap.get("refresh_root_discovery") or {}).get("total"),
                    (gap.get("refresh_root_discovery") or {}).get("missing"),
                    json.dumps(gap.get("production_stop") or (), ensure_ascii=False)))
            add("- 生产自报缺口（family_fill.missing）仅作对照：{0}；"
                "**预算预检以逐键覆盖为准**".format(json.dumps(
                    {key[:12]: len(value) for key, value in
                     (gap.get("production_reported_missing") or {}).items()},
                    ensure_ascii=False)))
        add("- 累计消耗口径（P9c 后，评审 §8）：**900 完整桌 / 573 部分桌 / 573 前缀 / "
            "0 模型 token**；本次运行的实际费用另列于 §2c，不被累计数掩盖。")
        add("")
        add("## 4. 分支可达性（与真实效果优劣**分别记录**）")
        add("")
        add("- 实际走到的分支：{0}".format(json.dumps(
            {key: value for key, value in self.branches.items()
             if key in ("conditional_root", "old_root_resolution",
                        "second_iteration_declarations")},
            ensure_ascii=False)[:1200]))
        add("- 同签名不可重复占探索席：{0}".format(json.dumps(
            {key: value for key, value in (self.branches.get("exploration_probe") or {})
             .items() if key in ("twin_excluded", "twin_not_seated",
                                 "different_signature_seated")}, ensure_ascii=False)))
        add("- 结论：**真实效果未必胜出；「完整比较跑完后保席」是合格结果**。"
            "晋升成功分支只允许用可判定的确定性产物另行证明可达，不得篡改真实结果。"
            "**预算不足导致的保席不属于这一类**：它是 INSUFFICIENT（停止安全），"
            "见 §3b 的缺边读数。")
        add("")
        add("## 5. 真实效果优劣（独立于可达性）")
        add("")
        add("- 中断演练效果读数：{0}".format(json.dumps(
            self.effects.get("interrupt_drill") or {}, ensure_ascii=False)))
        add("- M1 任务包读数：{0}".format(json.dumps(
            self.effects.get("m1_package") or {}, ensure_ascii=False)))
        add("- 说明：本步只记录真实读数与复用/计费事实，**不对候选强弱下结论**；"
            "比较结论属于独立自然根 + 发布合同的证据面。")
        add("")
        add("## 6. 失败与差异原因")
        add("")
        add("**剩余六项的成因（按评审 §3/§4 更正）**：不是「窗口摘要不落盘」这一件事，"
            "而是三处共同依赖缺失 + 一个真实预算缺口：")
        add("")
        add("1. **根用途误接**：目标旧根被写进 `plan.family_refresh` 与新刷新根一起请求，"
            "刷新解析器按「刷新批不得重复登记」跳过已有根，实际换了别的根；"
            "验证器再按固定目录名猜用途 ⇒ `refill={}` 与六项读数全失败。"
            "修法：计划分别表达「指定旧根重评」与「新刷新根发现」，旧根精确使用登记描述，"
            "被替换即直接拒绝该验证任务。")
        add("2. **缺真实内容见证**：普通条件入口不落盘截取窗口/内容摘要，"
            "验收器在 recorded 缺失时把「可重算」当成「已对拍一致」。"
            "修法：P12 把两个结论分开（`recomputable` / `matched`），缺见证记 "
            "INSUFFICIENT；真实见证由 P11 的 RootWitness 落地后逐根对拍。")
        add("3. **比较预算不足**：第二候选的核心根与刷新根没有按待执行实例集合算进预算，"
            "停机原因为具名预算/无进展停止。修法：预算从待执行实例集合生成，"
            "开跑前预检必须看见完整比较的所有缺边（本报告的 §3b 即该读数）。")
        add("")
        add("**两种保席必须分列**（不得混写）：")
        add("- **预算不足保席**：因额度/声明不可物化而停机 ⇒ 记为 INSUFFICIENT（停止安全），"
            "**不是**「真实结果未提升所以保席」。")
        add("- **完整比较未胜出保席**：比较确实跑完且候选未胜出 ⇒ 这是合格结果（PASS）。"
            "本次运行属于前者：缺边读数见 §3b。")
        add("")
        add("- 缺口与风险：{0}".format(json.dumps(self.gaps, ensure_ascii=False)))
        add("- worker 返回码：{0}".format(json.dumps(
            [{"tag": card.get("tag"), "rc": card.get("returncode"),
              "interrupted": card.get("interrupted")} for card in self.workers],
            ensure_ascii=False)))
        add("")
        add("## 7. 复跑命令")
        add("")
        add("    .venv/bin/python <gate2_plan.py> --out <plan.json> ...")
        add("    .venv/bin/python <gate2_run.py> --plan <plan.json> --run-root <run> \\")
        add("        --evidence <evidence/run/<run-id>> --max-tables <cap>")
        add("")
        return "\n".join(lines)


# ===========================================================================
# 编排与 CLI
# ===========================================================================


class RunArgs:
    """执行参数（含 steps_include；封顶与中断点都由这里进）。"""

    def __init__(self, *, python: str, max_tables: Optional[float],
                 interrupt_at: Optional[str], steps: Sequence[int],
                 dry_run: bool, timeout_sec: int = 10800,
                 batch_label: str = DEFAULT_BATCH_LABEL,
                 run_id: Optional[str] = None,
                 plan_path: Optional[str] = None,
                 supplied_budgets: Optional[Mapping[str, Any]] = None,
                 prior_runs: Sequence[str] = (),
                 recheck: bool = False,
                 mode: str = "signoff",
                 diagnostic_scope: Optional[str] = None) -> None:
        # 复审 P17 缺陷（2026-09-19 run7 实测）：`--mode` / `--diagnostic-scope` 是
        # 新加的**运行参数**，必须同时进 `RunArgs`——否则 run_all 只能在跑完步骤以后才
        # 抛 AttributeError（运行目录与账本已经落了真实费用，报告却写不出来）。
        self.mode = str(mode)
        self.diagnostic_scope = diagnostic_scope
        self.python = python
        self.batch_label = batch_label
        self.run_id = run_id
        self.plan_path = plan_path
        self.supplied_budgets = dict(supplied_budgets) if supplied_budgets else None
        self.prior_runs = [str(item) for item in prior_runs]
        self.recheck = bool(recheck)
        self.max_tables = max_tables
        self.interrupt_at = interrupt_at
        self.step_set = set(int(value) for value in steps)
        self.dry_run = dry_run
        self.timeout_sec = int(timeout_sec)

    def steps_include(self, number: int) -> bool:
        return int(number) in self.step_set


RUN_MODES: Tuple[str, ...] = ("signoff", "diagnostic")


def run_root_identity_mismatch(run_root: Path) -> List[Dict[str, Any]]:
    """运行根自洽性：迭代 state.json 里记的绝对路径必须落在**本运行根**之下。

    产物的指针（`iter_dir` / `registry_path` / `ledger_path` …）都是绝对路径。
    把既有运行根复制到别处再用 `--run-root <副本>` 跑，副本里的 state 仍指向原目录，
    worker 会**写回原目录**（2026-09-19 实测：29 个文件被写进真 run7 的 iter-03）。
    这里在启动 worker 之前把这种"身份漂移"逐条列出来。
    """

    root = Path(run_root).resolve()
    bad: List[Dict[str, Any]] = []
    for iter_dir in iter_dirs(root):
        state = read_json(iter_dir / "state.json") or {}
        for key in ("iter_dir", "run_root", "registry_path", "ledger_path"):
            value = state.get(key)
            if not value:
                continue
            try:
                recorded = Path(str(value)).resolve()
            except OSError:
                continue
            if recorded != root and root not in recorded.parents:
                bad.append({"iteration": iter_dir.name, "field": key,
                            "recorded": str(recorded), "run_root": str(root)})
    return bad


def run_mode_of(args: Any) -> Tuple[str, Optional[str]]:
    """运行模式读数（**必须显式来自 RunArgs**）：返回 `(mode, diagnostic_scope)`。

    2026-09-19 run7 实测缺陷：新增的 `--mode` 没进 `RunArgs`，`run_all` 直接读
    `args.mode` ⇒ 在**跑完步骤、准备出报告时**才抛 AttributeError（真实费用已发生、
    报告没落盘）。这里改成**跑任何步骤之前**的具名失败关闭：

    - 缺字段 / 取值非法 ⇒ 立即 `SystemExit`，不猜测缺省（猜成 signoff 会把诊断运行
      冒充成正式签收，猜成 diagnostic 会把签收降格成诊断）；
    - 诊断模式必须同时给非空范围（显式不同的模式与范围）。
    """

    mode = getattr(args, "mode", None)
    scope = getattr(args, "diagnostic_scope", None)
    if mode not in RUN_MODES:
        raise SystemExit(
            "运行参数缺少 mode（期望 {0}，实际 {1!r}）：新增的运行参数必须同时进 "
            "RunArgs 并由 main() 传入 —— 已在**启动任何 worker 之前**停止".format(
                "/".join(RUN_MODES), mode))
    if str(mode) == "diagnostic" and not str(scope or "").strip():
        raise SystemExit("诊断运行缺少 --diagnostic-scope（显式不同的模式与范围）")
    return str(mode), (str(scope).strip() or None)


def _prodiction() -> Optional[Dict[str, Any]]:
    """只读装载生产模块（取常量用）；缺件时返回 None，派生会标注 fallback 来源。"""

    try:
        return load_production()
    except Exception:  # noqa: BLE001
        return None


def preview(plan: Mapping[str, Any], *, run_root: Path, args: RunArgs) -> Dict[str, Any]:
    """干跑预演：只把将要发出的 worker 调用列出来（不起进程、不写运行目录）。"""

    calls: List[Dict[str, Any]] = []
    spec1 = plan["iterations"][0]
    spec2 = plan["iterations"][1] if len(plan["iterations"]) > 1 else {}
    for step, tag, action, extra in (
            (1, "step1-open", "evolve",
             {"family_channel": spec1.get("family_channel"),
              "family_refresh_count": len(spec1.get("family_refresh") or ()),
              "stop_after": None}),
            (2, "step2-conditional", "evolve", {"stop_after": "CONDITIONAL_EVALUATED"}),
            (3, "step3-iter1-complete", "evolve", {"stop_after": None}),
            (3, "step3-iter2-open", "evolve",
             {"family_refresh_count": len(spec2.get("family_refresh") or ()),
              "stop_after": None}),
            (3, "step3-iter2-conditional", "evolve",
             {"stop_after": "CONDITIONAL_EVALUATED"}),
            (5, "step5-inject", "evolve",
             {"interrupt_at": args.interrupt_at or
              plan["plan_config"].get("interrupt_at")}),
            (5, "step5-cold-resume", "resume", {}),
            (3, "step3-iter2-complete", "evolve", {"stop_after": None}),
            (4, "step4-same-signature-probe", "probe_same_signature", {}),
            (6, "step6-m1-package", "evolve", {"envelope": "不写（停等出任务包）"})):
        calls.append({"step": step, "tag": tag, "action": action, **extra})
    return {
        "schema": "sitin-gate2-dryrun-preview/1",
        "batch_label": validate_batch_label(getattr(args, "batch_label", None)
                                            or plan.get("batch_label")
                                            or DEFAULT_BATCH_LABEL),
        "run_root": str(run_root),
        "max_tables": args.max_tables,
        "max_tables_effective_cap_default": float(
            plan["budget"].get("executable_planned_tables_default_cap")
            or plan["budget"].get("executable_planned_tables") or 0.0),
        "interrupt_at": args.interrupt_at,
        "note": ("预演不是执行：不起子进程、不写运行目录、不跑任何桌赛。"
                 "真实执行请去掉 --dry-run。"),
        "worker_calls": calls,
        "account_derivation": derive_accounts(plan, prod=_prodiction()),
        "preflight": preflight(plan, supplied=args.supplied_budgets,
                               prod=_prodiction()),
        "budget": plan["budget"],
        "wall_time": plan["wall_time"],
        "gaps": plan["gaps"],
    }


def run_all(*, plan: Mapping[str, Any], run_root: Path, out_dir: Path,
            args: RunArgs) -> Dict[str, Any]:
    """按第 1→6 步执行（第 5 步的中断穿插在第二候选的自然面板里）。"""

    # 模式读数放在**最前面**：新增参数漏进 RunArgs 时必须在花钱之前具名停止，
    # 而不是跑完六步、要写报告时才炸（2026-09-19 run7 实测）。
    mode, diagnostic_scope = run_mode_of(args)
    # —— 运行根自洽性守卫（2026-09-19 实测事故）——
    # worker 是从**迭代 state.json 里的绝对路径**解析运行目录的。若把既有运行根复制到
    # 别处再用 `--run-root <副本>` 跑，副本里的 state 仍指向原目录 ⇒ worker 会写回
    # **原目录**（本次把 29 个文件写进了真 run7 的 iter-03）。这里在启动任何 worker 之前
    # 逐个迭代校验：不一致即具名停止，绝不"以为在副本里跑"。
    mismatched = run_root_identity_mismatch(Path(run_root))
    if mismatched:
        raise SystemExit(
            "运行根自洽性守卫：该运行根不是本目录自己的运行（迭代状态里的绝对路径指向"
            "别处）⇒ 在启动任何 worker 之前停止。不一致 {0} 条：{1}；"
            "如需复用既有产物，请用 --recheck 或 --steps \"\" 的只读路径；"
            "如需隔离试跑，请用**全新空运行根**（不要复制既有运行根）".format(
                len(mismatched), json.dumps(mismatched[:3], ensure_ascii=False)))
    runner = Gate2Runner(plan=plan, run_root=run_root, out_dir=out_dir, args=args)
    steps: List[Dict[str, Any]] = []
    # 失败关闭（封顶红线等）会 SystemExit：**已发生的事实必须仍写成报告**——
    # 2026-09-19 run7 的教训是"跑完六步、报告没落盘"；这里把停止原因具名记进报告，
    # 报告照写、进程仍以非零退出（fail-closed 不变），只是不再丢证据。
    fail_closed_stop: Optional[Dict[str, Any]] = None
    try:
        if args.steps_include(1):
            steps.append(runner.run_step(1))
        if args.steps_include(2):
            steps.append(runner.run_step(2))
        if args.steps_include(3):
            steps.append(runner.run_step(3))
        if args.steps_include(5):
            steps.append(runner.run_step(5))
            # 中断演练发生在第二候选迭代内部：恢复后把该迭代走完再核第 3 步后半段。
            if args.steps_include(3) and steps:
                for index, row in enumerate(steps):
                    if row.get("step") == 3 and not row.get("finalized"):
                        steps[index] = runner.finalize_second_candidate(row)
        if args.steps_include(4):
            steps.append(runner.run_step(4))
        if args.steps_include(6):
            steps.append(runner.run_step(6))
    except SystemExit as exc:
        fail_closed_stop = {
            "kind": "fail_closed_stop", "message": str(exc),
            "completed_steps": [row.get("step") for row in steps],
            "note": ("执行器按失败关闭停止（例如封顶红线）；已发生的步骤与真实费用"
                     "由本报告如实记录，不丢证据")}
        print("已按失败关闭停止；仍把已发生的事实写成报告：{0}".format(exc))
    # **六步判定行必须先接进执行器**：`reconcile()` 的分项签收与报告的 §1 逐条清单
    # 都读 `runner.steps`。2026-09-18 的缺陷：这里漏了赋值 ⇒ 报告 §1 空表、
    # 能力覆盖六步全被渲染成 NOT_APPLICABLE（正是评审 §3 禁止的"用 0 错误签收未执行路径"）。
    runner.steps = steps
    reconciliation = runner.reconcile()
    run_id = str((runner.latest()[1] or {}).get("run_id") or run_root.name)
    report = {
        "schema": RUN_SCHEMA, "created_at_utc": utc_now(), "run_id": run_id,
        "batch_label": runner.batch_label,
        "run_root": str(run_root), "plan_schema": plan.get("schema"),
        "steps_requested": sorted(args.step_set),
        "max_tables": args.max_tables,
        "max_tables_effective": runner.cap,
        "max_tables_default_source": ("plan_executable_default"
                                      if args.max_tables is None else "caller"),
        "authorization_archive": str(runner.auth_archive),
        "budget_redline_log": str(runner.redline_log),
        "preflight": runner.preflight,
        "account_derivation": runner.derivation,
        "prior_consumption": collect_prior_consumption(
            getattr(args, "prior_runs", ()) or ()),
        "interrupt_at": args.interrupt_at,
        "tree_state_before": runner.tree_state_before,
        "tree_state_after": capture_tree_state(),
        "steps": steps, "workers": runner.workers,
        "stop": fail_closed_stop,
        "reconciliation": reconciliation,
        "branches": runner.branches, "effects": runner.effects,
        "gaps": runner.gaps,
        "acceptance": {
            "reconciliation_ok": reconciliation.get("ok"),
            "steps_ok": all_ok([row for row in steps if not row.get("skipped")]),
            "failing_checks": [
                {"step": row.get("step"), "name": check_row.get("name"),
                 "detail": check_row.get("detail")}
                for row in steps for check_row in (row.get("checks") or ())
                if not check_row.get("ok") and check_row.get("applicable", True)] + [
                {"step": "reconcile", "name": check_row.get("name"),
                 "detail": check_row.get("detail")}
                for check_row in (reconciliation.get("checks") or ())
                if not check_row.get("ok") and check_row.get("applicable", True)],
            "not_applicable_checks": [
                {"step": row.get("step"), "name": check_row.get("name"),
                 "detail": check_row.get("detail")}
                for row in steps for check_row in (row.get("checks") or ())
                if not check_row.get("applicable", True)] + [
                {"step": "reconcile", "name": check_row.get("name"),
                 "detail": check_row.get("detail")}
                for check_row in (reconciliation.get("checks") or ())
                if not check_row.get("applicable", True)],
        },
    }
    # 复审「最终状态统一」：顶层 `acceptance.ok` 与 `signoff.chain` **必须是同一个出口**。
    # 旧实现里 ok = 逐步判定 AND 对账判定，而 signoff.chain = 各组最差者：两者可以不一致
    # （例如能力覆盖组 N/A、预算预检 FAIL 时 ok 仍为真）。现在只留一个出口：
    # **ok 当且仅当整链 PASS（= 没有任何一项 FAIL/INSUFFICIENT/NOT_APPLICABLE）**。
    report["mode"] = mode
    if mode == "diagnostic":
        report["diagnostic_scope"] = diagnostic_scope
    united = unified_acceptance(reconciliation=reconciliation, steps=steps,
                                mode=mode, diagnostic_scope=diagnostic_scope)
    if fail_closed_stop is not None:
        # 失败关闭运行时：绝不允许被读成通过（整链读数照出，但 ok 恒 False）。
        united["ok"] = False
        united["exit"]["rule"] += (
            "；本次执行按失败关闭停止（{0}）⇒ ok 恒为 False，停止原因见 report.stop"
            .format(str(fail_closed_stop.get("message"))[:80]))
        united["exit"]["fail_closed_stop"] = True
    report["acceptance"]["signoff_status"] = united["signoff_status"]
    report["acceptance"]["signoff_chain"] = united["signoff_chain"]
    report["acceptance"]["exit"] = united["exit"]
    report["acceptance"]["ok"] = united["ok"]
    return report, runner


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=("关口二执行器：六步真实整链（无模型、封顶）+ 逐步对账。"
                     "零模型调用；生成只经 delegate 文件通道的固定材料。"))
    parser.add_argument("--plan", required=False, help="gate2_plan.py 产出的计划 JSON")
    parser.add_argument("--batch-label", default=DEFAULT_BATCH_LABEL,
                        help=("批次/运行标签（默认 {0}）：进授权文件、运行目录、报告与"
                              "全部产物；历史标签（batch7*/rep1/rep2/r6*/r7*/r8*）"
                              "一律拒绝").format(DEFAULT_BATCH_LABEL))
    parser.add_argument("--run-root", required=False,
                        help=("运行根目录（默认 artifacts/gate2-accept/<batch-label>/"
                              "<run-id>）"))
    parser.add_argument("--run-id", default=None,
                        help="运行标识（默认 <batch-label>-<时间戳>）")
    parser.add_argument("--evidence", default=None,
                        help="报告目录（默认 evidence/v4-impl/r9-gate2/run/<run-id>）")
    parser.add_argument("--steps", default="1,2,3,4,5,6",
                        help="要执行的步骤（逗号分隔；极小规模干跑常用 1,2）")
    parser.add_argument("--max-tables", type=float, default=None,
                        help=("tables_full 封顶（缺省 = 计划可执行桌数；**不得高于**该值，"
                              "传更大值即拒绝）"))
    parser.add_argument("--interrupt-at", default=None,
                        help="受控中断注入点（默认取计划里的 interrupt_at）")
    parser.add_argument("--authorization", default=None,
                        help=("外部授权令牌 JSON（可选）：给出后预检会逐账户核对"
                              "「派生需求 ≤ 该授权的额度」，不足即拒绝开跑并点名账户与差额"))
    parser.add_argument("--prior-run", action="append", default=[],
                        help=("先前运行目录（可重复）：把**已经发生**的真实消耗如实记进"
                              "本次报告（失败不等于没花钱）"))
    parser.add_argument("--mode", choices=("signoff", "diagnostic"), default="signoff",
                        help=("运行模式。**signoff（正式签收，缺省）**：预算预检 FAIL 或预检自身"
                              "异常时，在**启动任何 worker 之前**停止（退出码 2），只把缺边与"
                              "预算读数落盘；**diagnostic**：显式不同的模式与范围"
                              "（必须同时给 --diagnostic-scope），只做有限诊断运行，"
                              "不打印「预检通过」、不自动进入完整签收链、报告不计签收"))
    parser.add_argument("--diagnostic-scope", default=None,
                        help="诊断范围（--mode diagnostic 必填）：写明有限运行覆盖什么、"
                             "不覆盖什么")
    parser.add_argument("--dry-run", action="store_true",
                        help="只预演 worker 调用，不起进程、不写运行目录")
    parser.add_argument("--python", default=sys.executable,
                        help="worker 解释器（缺省与当前解释器一致；纪律要求 .venv/bin/python）")
    parser.add_argument("--worker", default=None,
                        help="内部：worker 规格 JSON（由本文件的编排侧生成）")
    parser.add_argument("--recheck", action="store_true",
                        help=("**只读复算**：对既有运行目录重算逐步对账（0 桌、0 费用、"
                              "不写运行目录），用于修正判定口径后重新出读数"))
    args = parser.parse_args(argv)

    if args.worker:
        spec = read_json(Path(args.worker)) or {}
        return run_worker(spec)

    if not args.plan:
        parser.error("缺少 --plan（或使用 --worker）")
    plan = read_json(Path(args.plan))
    if not plan:
        raise SystemExit("计划文件不可读：{0}".format(args.plan))
    # 批次/运行标签先校验：历史标签一律拒绝（在写任何文件之前失败）。
    batch_label = validate_batch_label(args.batch_label or plan.get("batch_label")
                                       or DEFAULT_BATCH_LABEL)
    run_id = args.run_id or (
        batch_label + "-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    run_root = Path(args.run_root) if args.run_root else (
        _project_file(_PROJECT_ROOT, REPO_ROOT / "artifacts/gate2-accept" / batch_label / run_id))
    out_dir = Path(args.evidence) if args.evidence else (_project_file(_PROJECT_ROOT, GATE2_DIR / "run" / run_id))
    steps = [int(value) for value in str(args.steps).replace(" ", "").split(",") if value]
    # 封顶先校验（dry-run 也要过）：缺省 = 计划可执行桌数，且不允许更高。
    cap_default = float(plan["budget"].get("executable_planned_tables_default_cap")
                        or plan["budget"].get("executable_planned_tables") or 0.0)
    resolve_cap(requested=args.max_tables, cap_default=cap_default)
    # —— 开跑前预检（**在写任何运行目录之前**）——
    # 外部授权给了就逐账户核对「派生需求 ≤ 授权」，不足即在此拒绝开跑；
    # 没给就按派生需求自写授权（派生过程本身仍会跑交叉核对并打印对照表）。
    supplied_token = read_json(Path(args.authorization)) if args.authorization else None
    supplied = None
    supplied_check = None
    if supplied_token is not None:
        # 两种形态都支持（Q6）：legacy 的 budgets 与新形态的 allowed_accounts 都映射到
        # 统一账户口径；不合规即**拒绝开跑**（失败关闭，不允许去掉授权约束）。
        supplied_check = AUTH12.validate(
            supplied_token, expected_batch_label=batch_label,
            required_operations=("natural_panel", "conditional_prefix",
                                 "family_fill", "conditional_refill", "evaluate",
                                 "summarize"))
        if not supplied_check["ok"]:
            raise SystemExit("外部授权不合规（fail-closed，拒绝开跑）：{0}｜形态 {1}".format(
                "；".join(supplied_check["problems"]),
                supplied_check["authorization_form"]))
        supplied = dict(supplied_check["budgets"]) or None
        print("外部授权形态：{0}（authorization_id={1}）".format(
            supplied_check["authorization_form"], supplied_check["authorization_id"]))
    preflight_result = preflight(plan, supplied=supplied, prod=_prodiction())
    if supplied_check is not None:
        preflight_result["authorization_form"] = supplied_check["authorization_form"]
        preflight_result["authorization_check"] = supplied_check
    # 预算预检（P12/G2）：从**待执行实例集合**出发，先看见完整比较的所有缺边；
    # 缺边未闭合时**在启动 worker 之前具名停止**（不以扩大封顶代替漏算修复）。
    # 续跑场景：运行目录已存在时，预检必须看见**完整比较的所有缺边**（含已跑部分）。
    diagnostic_mode = (args.mode == "diagnostic")
    scope = (args.diagnostic_scope or "").strip()
    if diagnostic_mode and not scope:
        parser.error("--mode diagnostic 必须同时给 --diagnostic-scope"
                     "（显式不同的模式与范围，不能用同一个启动路径）")
    try:
        budget_preflight = BUDGET12.preflight_budget(
            plan=plan, cap=args.max_tables,
            run_root=(run_root if Path(run_root).is_dir() else None))
    except Exception as exc:  # noqa: BLE001 —— 预检自身异常必须失败关闭
        budget_preflight = {
            "ok": False, "status": STATUS12.FAIL,
            "error": "{0}: {1}".format(type(exc).__name__, exc),
            "refusal": ("预算预检自身异常 ⇒ 按失败关闭处理（预检异常不得启动正式执行）"),
            "checks": [], "execution_set_summary": {}, "missing_edges": []}
    preflight_result["budget_preflight"] = budget_preflight
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "preflight.json", preflight_result)
    print("预算预检（待执行实例集合）：{0}".format(
        json.dumps(budget_preflight.get("execution_set_summary") or {}, ensure_ascii=False)))
    for row in budget_preflight.get("checks") or ():
        print("    [budget] {0}：{1}".format("OK" if row["ok"] else "FAIL", row["detail"][:200]))
    budget_ok = bool(budget_preflight.get("ok"))
    if not budget_ok:
        print("    预算预检为 FAIL：{0}".format(
            budget_preflight.get("refusal") or budget_preflight.get("error") or "未通过"))
        # 只读诊断读数照常输出（缺边 + 预算），但**不得**据此启动正式执行。
        print("    缺边清单（只读）：{0}".format(json.dumps(
            budget_preflight.get("missing_edges") or [], ensure_ascii=False)[:400]))
        print("    预算读数（只读）：{0}".format(json.dumps(
            (preflight_result.get("derivation") or {}).get("accounts") or {},
            ensure_ascii=False)[:400]))
    if diagnostic_mode:
        print("诊断模式（**非签收**）：范围 {0}".format(scope))
        print("    本模式是显式不同的模式与范围：不打印`预检通过`、不自动进入完整签收链、"
              "报告与退出码都不会被读成关口二签收")
    elif args.recheck or args.dry_run:
        # 只读诊断（--recheck / --dry-run）**不启动任何 worker**：缺边与预算照常输出，
        # 预检不通过也不在这里当签收门（它拦的是"启动 worker"，不是"读读数"）。
        print("只读模式（{0}）：预检读数照常输出；本模式不启动任何 worker".format(
            "--recheck" if args.recheck else "--dry-run"))
        if not budget_ok:
            print("    （预检未通过：本模式的产出是**读数**，不是签收结论；"
                  "正式签收运行必须等缺边闭合后另起一次）")
    else:
        if not budget_ok:
            print("    正式签收模式：预检未通过 ⇒ 在**启动任何 worker 之前**停止"
                  "（不以抬高封顶代替漏算修复；缺边与预算读数已落盘 {0}）".format(
                      out_dir / "preflight.json"))
            return 2
        print("开跑前预检通过：{0}".format(args.plan))
    print("  类目 → 账户 → 额度（派生）：")
    derivation = preflight_result["derivation"]
    for row in derivation["mapping_table"]:
        print("    {0:<28} → {1:<18} 实例 {2:>3}  桌数 {3:>6}  {4}".format(
            row["category"], row["account"], row["n_instances"],
            ("{0:.1f}".format(row["planned_tables"]) if row["present_in_plan"] else "—"),
            ("在计划内" if row["present_in_plan"] else "计划内无此类目")))
    print("  账户额度：{0}".format(json.dumps(derivation["accounts"], ensure_ascii=False)))
    for row in derivation["cross_checks"]:
        print("    [cross] {0}：{1}｜{2}".format(
            "OK" if row["ok"] else "FAIL", row["name"], row["reading"]))
    run_args = RunArgs(python=args.python, max_tables=args.max_tables,
                       interrupt_at=args.interrupt_at, steps=steps,
                       dry_run=args.dry_run, batch_label=batch_label,
                       run_id=run_id, plan_path=str(args.plan),
                       supplied_budgets=supplied,
                       prior_runs=args.prior_run or [],
                       mode=args.mode, diagnostic_scope=args.diagnostic_scope)
    if args.recheck:
        if not args.run_root:
            parser.error("--recheck 需要 --run-root（既有运行目录）")
        run_args = RunArgs(python=args.python, max_tables=args.max_tables,
                           interrupt_at=args.interrupt_at, steps=[],
                           dry_run=True, batch_label=batch_label, run_id=run_id,
                           plan_path=str(args.plan), supplied_budgets=supplied,
                           prior_runs=args.prior_run or [], recheck=True,
                           mode=args.mode, diagnostic_scope=args.diagnostic_scope)
        runner = Gate2Runner(plan=plan, run_root=Path(args.run_root),
                             out_dir=out_dir, args=run_args)
        rec = runner.reconcile()
        payload = {
            "schema": "sitin-gate2-recheck/1", "at_utc": utc_now(),
            "batch_label": batch_label, "run_root": str(Path(args.run_root)),
            "note": ("只读复算：不跑桌、不写运行目录、不改账本；用于在判定口径修正后"
                     "对既有运行重新出读数"),
            "reconciliation": rec,
            "instance_rows": rec.get("instance_rows"),
            "matrix": dict(rec.get("matrix") or {}),
            "signoff": rec.get("signoff"),
            "mode": "recheck_readonly",
            "instance_join": rec.get("instance_join"),
            "budget_comparison_gap": rec.get("budget_comparison_gap"),
            "prior_consumption": runner.prior_consumption,
            "failing": [row for row in rec["checks"]
                        if STATUS12.check_status(row) == STATUS12.FAIL],
            "insufficient": [row for row in rec["checks"]
                             if STATUS12.check_status(row) == STATUS12.INSUFFICIENT],
            "not_applicable": [row for row in rec["checks"]
                               if STATUS12.check_status(row) == STATUS12.NOT_APPLICABLE],
        }
        out_path = write_json(out_dir / "gate2-recheck.json", payload)
        print("只读复算（0 桌）：{0}".format(args.run_root))
        for row in rec["checks"]:
            print("  {0:<14} {1:<34} {2}".format(
                STATUS12.check_status(row), row["name"], str(row["detail"])[:110]))
        signoff = rec.get("signoff") or {}
        if signoff:
            print(STATUS12.render(signoff))
        print("  家族核心矩阵逐格（登记行数仅作对照）：", json.dumps(
            payload["matrix"], ensure_ascii=False)[:400])
        print("  完整比较缺边：", json.dumps(
            (rec.get("budget_comparison_gap") or {}).get("per_candidate") or [],
            ensure_ascii=False))
        print("  复算结果已落盘：{0}".format(out_path))
        # 与正式运行**同一个出口**：只读复算的退出码同样取整链（signoff.chain）判定。
        chain_status = str(((rec.get("signoff") or {}).get("chain") or {}).get("status"))
        print("  统一出口：整链状态 {0}（0=PASS / 1=非 PASS）；本模式是只读复算，"
              "不启动 worker、不写运行目录".format(chain_status))
        return 0 if chain_status == STATUS12.PASS else 1
    if args.dry_run:
        payload = preview(plan, run_root=run_root, args=run_args)
        payload["preflight_path"] = str(out_dir / "preflight.json")
        out_path = write_json(out_dir / "gate2-dryrun-preview.json", payload)
        # 只打印人能读的摘要（不打印被截断的 JSON：截断的 JSON 不是 JSON）。
        print("预演（不执行）：批次标签 {0}；worker 调用 {1} 次；运行根 {2}".format(
            payload["batch_label"], len(payload["worker_calls"]),
            payload["run_root"]))
        print("  计划桌数 {0:.1f}（可执行 {1:.1f}）；封顶默认 = 可执行桌数，"
              "且不允许更高；墙上时间 {2}".format(
                  float(payload["budget"]["total_planned_tables"]),
                  float(payload["budget"]["executable_planned_tables"]),
                  payload["wall_time"]["status"]))
        for call in payload["worker_calls"]:
            print("  步{0} {1:<28} action={2:<20} {3}".format(
                call["step"], call["tag"], call["action"],
                json.dumps({key: value for key, value in call.items()
                            if key not in ("step", "tag", "action")},
                           ensure_ascii=False)))
        print("预演结果已落盘：{0}".format(out_path))
        return 0
    report, runner = run_all(plan=plan, run_root=run_root, out_dir=out_dir,
                             args=run_args)
    write_json(out_dir / "gate2-run.json", report)
    (out_dir / "gate2-run.md").write_text(
        runner.markdown(run_id=report["run_id"],
                        reconciliation=report["reconciliation"],
                        evidence_kind=("本报告是**真实执行**报告；"
                                       "极小规模干跑不得当作关口二验收结论")),
        encoding="utf-8")
    acceptance = dict(report.get("acceptance") or {})
    exit_info = dict(acceptance.get("exit") or {})
    print(json.dumps({"run_id": report["run_id"], "mode": report.get("mode"),
                      "ok": acceptance.get("ok"),
                      "signoff_chain": acceptance.get("signoff_status"),
                      "exit_rule": exit_info.get("rule"),
                      "scope": exit_info.get("scope"),
                      "report": str(out_dir / "gate2-run.json"),
                      "markdown": str(out_dir / "gate2-run.md"),
                      "failing": acceptance.get("failing_checks", [])[:10]},
                     ensure_ascii=False, indent=2))
    if str(report.get("mode")) == "diagnostic":
        print("诊断运行结束（**非签收**）：范围 {0}；退出码 3 —— 不得读作关口二签收"
              .format(report.get("diagnostic_scope")))
        return 3
    return 0 if acceptance.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
