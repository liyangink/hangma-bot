#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P12 · 判定状态词表与分项签收（Q4 落实）。

裁定原文（R9-ACCEPTANCE-AND-Q1-Q7-RULING §3）：
> 可判定的最终状态至少区分：`PASS`（义务已完成）、`INSUFFICIENT`（预算/见证/材料不足）、
> `FAIL`（不变量违反）、`NOT_APPLICABLE`（冻结范围本来不含此分支）。必要能力被标记
> 不适用时，只能签收缩小后的子流程，不能宣称完整关口通过。

以及 §3 的两层结构：
> **安全且可对账是必要条件；声明已跑通的功能路径也必须真正执行并有证据。**

因此本模块把签收拆成**两组**，两组各自逐项出状态，**任何一组都不能用另一组的读数补齐**：

- `reconciliation_invariants`（四项对账不变量）：计划↔尝试↔结果↔费用逐项连接、
  零丢失、零重复计费、零未解释身份冲突、零假完成；
- `capability_coverage`（六步能力覆盖）：每一步都必须是"真的跑过且有证据"。

**分项通过不等于整链通过**：只要有任何一项不是 PASS，整链就只能是
`INSUFFICIENT`（预算/见证/材料不足）或 `FAIL`（不变量违反），绝不能是 PASS。
必要能力被判 NOT_APPLICABLE 时，产物里显式给出 `scope`：
`shrunk:<被排除的子流程>`，禁止把它写成"完整关口通过"。
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

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: 词表（**唯一**的四个判定词；报告、验收器、预算预检共用，不另造同义词）。
PASS = "PASS"
INSUFFICIENT = "INSUFFICIENT"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"

STATUS_WORDS: Tuple[str, ...] = (PASS, INSUFFICIENT, FAIL, NOT_APPLICABLE)

#: 四项对账不变量的名字（与 reconcile 的判据名逐字对应；改判据名必须同步这里）。
RECONCILIATION_INVARIANTS: Tuple[Tuple[str, str], ...] = (
    ("zero_lost_instances_by_key",
     "计划↔尝试↔结果↔费用按冻结实例键逐项连接，零丢失（不靠别通道数量补齐）"),
    ("zero_fake_completions",
     "completed 尝试的 result_digest 按生产摘要 schema 重算一致（改内容不改摘要必须红）"),
    ("zero_double_billing",
     "同 (step_id, account) 不存在多条非 superseded 的 settled 行（重试≠重复收费）"),
    ("zero_unexplained_identity_conflicts",
     "实例台账与家族根登记的身份冲突必须为零且全部可解释"),
)

#: 功能完成类判据（"账目诚实但不满足功能完成"的读数落在这里）。
FUNCTIONAL_CHECKS: frozenset = frozenset((
    "all_planned_instances_completed", "accounted_missing_are_complete_cases",
    "exit_no_aborted_instances", "fake_completions_file_level"))

#: 根见证类判据（Q3：可重算 / 已对拍一致 / 见证缺失 ⇒ INSUFFICIENT）。
WITNESS_CHECKS: frozenset = frozenset((
    "result_digest_equality_available", "requirement_digest_matched",
    "refill_requirement_digest_matched", "refill_root_witness_present",
    "refill_content_digest_persisted", "window_digest_basis_available",
    "root_content_digest_persisted"))

#: 比较完整性类判据（G2：共同根矩阵的缺边）。
COMPARISON_CHECKS: frozenset = frozenset((
    "family_core_matrix_complete",))

#: 六步能力覆盖的名字（与执行器 step 号一一对应）。
CAPABILITY_STEPS: Tuple[Tuple[int, str], ...] = (
    (1, "空目录/冻结身份/首个完整家族矩阵"),
    (2, "普通根登记 → 指定旧根重评（根用途分离）"),
    (3, "首席与第二候选共同根比较"),
    (4, "行为多样性与探索席更新"),
    (5, "中断与冷恢复"),
    (6, "原生反馈 → M1 材料"),
)


def check_status(row: Mapping[str, Any]) -> str:
    """一条判定行 → 四个判定词之一。

    优先看显式 `status`；否则由 `applicable` / `insufficient` / `ok` 推出。
    **不适用不是通过**（`applicable=False`），**不足不是失败**（`insufficient=True`）。
    """

    explicit = row.get("status")
    if explicit in STATUS_WORDS:
        return str(explicit)
    if not row.get("applicable", True):
        return NOT_APPLICABLE
    if row.get("insufficient"):
        return INSUFFICIENT
    return PASS if row.get("ok") else FAIL


def rollup(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """一组判定行 → 计数 + 该组可否签收。

    - 任一项 FAIL ⇒ 组状态 FAIL；
    - 无 FAIL 但有 INSUFFICIENT ⇒ 组状态 INSUFFICIENT；
    - 无 FAIL/INSUFFICIENT 但有 NOT_APPLICABLE ⇒ 组状态 NOT_APPLICABLE
      （**只能签收缩小后的子流程**）；
    - 全 PASS ⇒ PASS。
    """

    counts = {word: 0 for word in STATUS_WORDS}
    detail: List[Dict[str, Any]] = []
    if not rows:
        # 没有任何判定行 = 这一组**本次没有评估**：既不是通过，也不是失败。
        # 记 NOT_APPLICABLE 并让上层把声称范围缩小（绝不用空集合当"全绿"）。
        return {"status": NOT_APPLICABLE, "counts": counts, "rows": detail,
                "excluded_from_scope": ["<no checks recorded>"],
                "scope": "shrunk:<no checks recorded>"}
    for row in rows:
        word = check_status(row)
        counts[word] += 1
        detail.append({"name": row.get("name"), "status": word,
                       "detail": row.get("detail")})
    if counts[FAIL]:
        status = FAIL
    elif counts[INSUFFICIENT]:
        status = INSUFFICIENT
    elif counts[NOT_APPLICABLE]:
        status = NOT_APPLICABLE
    else:
        status = PASS
    excluded = [row["name"] for row in detail if row["status"] == NOT_APPLICABLE]
    return {"status": status, "counts": counts, "rows": detail,
            "excluded_from_scope": excluded,
            "scope": ("full" if not excluded
                      else "shrunk:" + ",".join(sorted(excluded)))}


def sign_off(*, reconciliation_rows: Sequence[Mapping[str, Any]],
             capability_rows: Mapping[int, Sequence[Mapping[str, Any]]],
             budget_rows: Sequence[Mapping[str, Any]] = (),
             witness_rows: Sequence[Mapping[str, Any]] = ()) -> Dict[str, Any]:
    """分项签收：对账不变量（四项）与能力覆盖（六步）**分开**，最后才谈整链。

    整链状态只能取三者中最差的一个：
    - 任一 FAIL ⇒ FAIL；
    - 否则任一 INSUFFICIENT ⇒ INSUFFICIENT（预算/见证/材料不足：既不是 FAIL 也不是 PASS）；
    - 否则任一 NOT_APPLICABLE ⇒ NOT_APPLICABLE（只能签收缩小后的子流程）；
    - 否则 PASS。
    """

    invariant_names = dict(RECONCILIATION_INVARIANTS)
    invariants = [row for row in reconciliation_rows
                  if str(row.get("name")) in invariant_names]
    rest = [row for row in reconciliation_rows
            if str(row.get("name")) not in invariant_names]
    functional = [row for row in rest if str(row.get("name")) in FUNCTIONAL_CHECKS]
    witness = [row for row in rest if str(row.get("name")) in WITNESS_CHECKS]
    comparison = [row for row in rest if str(row.get("name")) in COMPARISON_CHECKS]
    bookkeeping = [row for row in rest
                   if str(row.get("name")) not in (FUNCTIONAL_CHECKS
                                                   | WITNESS_CHECKS
                                                   | COMPARISON_CHECKS)]
    capabilities: List[Dict[str, Any]] = []
    for number, label in CAPABILITY_STEPS:
        rows = list(capability_rows.get(number) or ())
        group = rollup(rows)
        capabilities.append({"step": number, "label": label, **group})
    groups: List[Dict[str, Any]] = [
        {"group": "reconciliation_invariants", **rollup(invariants)},
        {"group": "capability_coverage", **rollup(
            [{"name": "step{0}".format(row["step"]), "status": row["status"],
              "detail": row["label"]} for row in capabilities])},
        {"group": "functional_completion", **rollup(functional)},
        {"group": "root_witness", **rollup(list(witness_rows) + witness)},
        {"group": "comparison_completeness", **rollup(comparison)},
        {"group": "bookkeeping", **rollup(bookkeeping)},
    ]
    if budget_rows:
        groups.append({"group": "budget_preflight", **rollup(budget_rows)})
    order = {FAIL: 3, INSUFFICIENT: 2, NOT_APPLICABLE: 1, PASS: 0}
    worst_word = max((group["status"] for group in groups),
                     key=lambda word: order[word])
    excluded = sorted({name for group in groups
                       for name in (group.get("excluded_from_scope") or ())})
    return {
        "schema": "sitin-gate2-signoff/2",
        "status_words": list(STATUS_WORDS),
        "reconciliation_invariants": groups[0],
        "capability_coverage": {"status": groups[1]["status"],
                                "counts": groups[1]["counts"],
                                "steps": capabilities,
                                "excluded_from_scope": groups[1]["excluded_from_scope"],
                                "scope": groups[1]["scope"]},
        "groups": groups,
        "other_groups": groups[2:],
        # 分项签收的**唯一**合法读法：整链 = 最差的一项。
        "chain": {"status": worst_word,
                  "excluded_from_scope": excluded,
                  "scope": ("full" if not excluded
                            else "shrunk:" + ",".join(excluded)),
                  "rule": ("整链状态 = 各分项中最差者；分项通过不得写成整链通过；"
                           "INSUFFICIENT 既不是 FAIL 也不是 PASS；"
                           "必要能力被标 NOT_APPLICABLE 时只能签收缩小后的子流程")},
        "note": ("四项是对账不变量、六步是能力覆盖、另分列功能完成/根见证/比较完整性/"
                 "记账读数：各组分开签收。真实比较未胜出（保席）可以是 PASS；"
                 "预算或见证不足是 INSUFFICIENT；不变量被违反才是 FAIL。"),
    }


def render(signoff: Mapping[str, Any]) -> str:
    """人能读的签收表（报告与终端都直接用它）。"""

    lines: List[str] = []
    add = lines.append
    add("| 组 | 项 | 状态 | 说明 |")
    add("| --- | --- | --- | --- |")
    for row in (signoff.get("reconciliation_invariants") or {}).get("rows") or ():
        add("| 对账不变量 | {0} | {1} | {2} |".format(
            row["name"], row["status"], str(row.get("detail"))[:160]))
    for row in (signoff.get("capability_coverage") or {}).get("steps") or ():
        add("| 能力覆盖 | 步{0} {1} | {2} | 排除项 {3} |".format(
            row["step"], row["label"], row["status"],
            ",".join(row.get("excluded_from_scope") or ()) or "—"))
    for group in signoff.get("other_groups") or ():
        add("| {0} | — | {1} | 计数 {2} |".format(
            group["group"], group["status"], group["counts"]))
    add("")
    add("整链状态：**{0}**（{1}）".format(
        (signoff.get("chain") or {}).get("status"),
        (signoff.get("chain") or {}).get("rule")))
    if (signoff.get("capability_coverage") or {}).get("scope", "full") != "full":
        add("声称范围：**收缩** — {0}（必要能力被标 NOT_APPLICABLE，"
            "只能签收缩小后的子流程）".format(
                (signoff.get("capability_coverage") or {}).get("scope")))
    return "\n".join(lines)


def worst(*words: str) -> str:
    """多个判定词取最差（FAIL > INSUFFICIENT > NOT_APPLICABLE > PASS）。"""

    order = {FAIL: 3, INSUFFICIENT: 2, NOT_APPLICABLE: 1, PASS: 0}
    return max(words, key=lambda word: order.get(word, 3))


def status_field(row: Mapping[str, Any]) -> Optional[str]:
    """兼容旧产物的读法：旧行只有 ok/applicable 时返回 None（由 check_status 推）。"""

    value = row.get("status")
    return str(value) if value in STATUS_WORDS else None
