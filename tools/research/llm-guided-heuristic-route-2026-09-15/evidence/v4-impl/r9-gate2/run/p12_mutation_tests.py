#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P12 · 定向变异测试：每条修复都要有一个**能把对应判据变红**的变异。

变异（全部纯数据 / 只读既有产物；不跑桌赛、不写运行目录）：

| 变异 | 针对的修复 | 期望 |
| --- | --- | --- |
| M1 去掉挑战者的「指定旧根重评」声明（只留 discover） | P1 共同根比较接线 | `required_reevaluation_declared` **红** |
| M2 把核心根声明的 intent 写成 `discover_new_root` | P1 根用途分离 | 同一判据 **红**（并列出被写错的核心根） |
| M3 六步判定行不接进分项签收（`steps=[]`，模拟旧缺陷） | P2 能力覆盖渲染 | `capability_coverage_wired` **红**、能力覆盖组为 NOT_APPLICABLE |
| C1 原样计划（对照） | — | 同一判据 **绿** |
| C2 逐步判定行接上（对照） | — | `capability_coverage_wired` **绿**，且六步有真实状态 |
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
import copy
import json
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate2_run as G          # noqa: E402
import p12_budget as BUDGET    # noqa: E402
import p12_status as STATUS    # noqa: E402


def mutation_m1_drop_reevaluations(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """M1：挑战者只发 discover 声明（去掉全部指定旧根重评）。"""

    mutated = copy.deepcopy(plan)
    for spec in mutated.get("iterations") or ():
        if str(spec.get("iteration_label")) == "cand1":
            continue
        spec["family_refresh"] = [
            dict(row, intent="discover_new_root")
            for row in (spec.get("family_refresh") or ())]
    verdict = BUDGET.required_reevaluation_declarations(mutated)
    return {"mutation": "M1_drop_reevaluations", "expect": "red",
            "ok": not verdict["ok"],
            "missing_core_reevaluations": sum(
                len(row["missing_core_reevaluations"])
                for row in verdict["per_iteration"]),
            "problems": verdict["problems"][:4]}


def mutation_m2_intent_written_discover(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """M2：把核心根的重评写成 discover_new_root（点了已登记根却不写用途）。"""

    mutated = copy.deepcopy(plan)
    changed = 0
    for spec in mutated.get("iterations") or ():
        if str(spec.get("iteration_label")) == "cand1":
            continue
        for row in (spec.get("family_refresh") or ()):
            if str(row.get("intent")) == "reevaluate_registered_root" \
                    and row.get("root_index") is not None:
                row["intent"] = "discover_new_root"
                changed += 1
    verdict = BUDGET.required_reevaluation_declarations(mutated)
    named = sum(len(row["core_roots_declared_discover"])
                for row in verdict["per_iteration"])
    return {"mutation": "M2_intent_written_discover", "expect": "red",
            "ok": (not verdict["ok"]) and named > 0,
            "rows_flipped": changed, "core_roots_declared_discover": named,
            "problems": verdict["problems"][:4]}


def prior_report_path(run_root: Path) -> Optional[Path]:
    """原运行报告的**权威位置解析**（与执行器同口径）。

    执行器把报告写在 `--evidence` 目录
    （`evidence/v4-impl/r9-gate2/run/<run-id>/gate2-run.json`），**不是**运行根目录
    （`artifacts/gate2-accept/<label>/<run-id>/` 只有账本/迭代/授权）。
    2026-09-18 的对照用例曾直接在运行根目录找报告 ⇒ 找不到 ⇒ 被误读成"接线回归"。
    """

    base = Path(run_root)
    for path in (base / "gate2-run.json",
                 G.GATE2_DIR / "run" / base.name / "gate2-run.json"):
        if path.is_file():
            return path
    return None


def _load_prior_report(run_root: Path) -> Dict[str, Any]:
    path = prior_report_path(run_root)
    if path is None:
        return {"path": None, "report": {},
                "problem": ("找不到原运行报告：已查 <run_root>/gate2-run.json 与 "
                            "<evidence>/run/<run-id>/gate2-run.json"
                            "（运行根目录本来就不含报告）")}
    try:
        return {"path": str(path),
                "report": json.loads(path.read_text(encoding="utf-8")),
                "problem": None}
    except (OSError, ValueError) as error:
        return {"path": str(path), "report": {},
                "problem": "原运行报告不可读：{0}".format(error)}


def _runner_for_reconcile(*, plan: Mapping[str, Any], run_root: Path,
                          out_dir: Path, steps: List[Dict[str, Any]],
                          cap: float) -> Any:
    """构造一个只用于 `reconcile()` 的执行器外壳（不跑任何步骤、不写运行目录）。"""

    runner = G.Gate2Runner.__new__(G.Gate2Runner)
    runner.plan = dict(plan)
    runner.run_root = Path(run_root)
    runner.out_dir = Path(out_dir)
    runner.cap = float(cap)
    runner.cap_default = float(cap)
    runner.batch_label = "p12-mutation-test"
    runner.args = types.SimpleNamespace(recheck=True, max_tables=None)
    runner.steps = list(steps)
    runner.redline_log = Path(out_dir) / "budget-redline.jsonl"
    runner.gaps = []
    runner.branches = {}
    runner.effects = {}
    runner.prior_consumption = {}
    runner.budget_preflight = {"checks": []}
    runner.authorization_check = None
    runner.auth_path = Path(run_root) / "gate2-authorization.json"
    runner.auth_archive = Path(out_dir) / "authorization.json"
    return runner


def mutation_m3_capability_not_wired(*, plan: Mapping[str, Any], run_root: Path,
                                     cap: float) -> Dict[str, Any]:
    """M3：判定行**完全不接线**（`steps=[]` 且读不到原报告）⇒ 能力覆盖必须红。

    这正是 2026-09-18 的旧缺陷形态：`runner.steps` 没赋值 ⇒ 报告 §1 空表、
    六步被渲染成 NOT_APPLICABLE。变异同时掐掉"读原报告"的兜底
    （`prior_steps` 覆盖为空），确保判据真的在拦"没接上就写 N/A"。
    """

    with tempfile.TemporaryDirectory(prefix="p12-mutation-") as tmp:
        runner = _runner_for_reconcile(plan=plan, run_root=run_root,
                                       out_dir=Path(tmp), steps=[], cap=cap)
        runner.prior_steps = lambda: {"source": None, "steps": [],
                                      "executed_in_this_invocation": False}
        rec = runner.reconcile()
        checks = {row["name"]: row for row in rec["checks"]}
        wired = checks.get("capability_coverage_wired") or {}
        signoff = rec.get("signoff") or {}
        return {"mutation": "M3_capability_not_wired", "expect": "red",
                "ok": (not wired.get("ok", True))
                and signoff.get("capability_coverage", {}).get("status")
                == STATUS.NOT_APPLICABLE,
                "check_status": STATUS.check_status(wired) if wired else None,
                "capability_status": signoff.get("capability_coverage", {}).get("status"),
                "detail": str(wired.get("detail"))[:220]}


def mutation_m3b_fallback_reads_prior_report(*, plan: Mapping[str, Any],
                                             run_root: Path, cap: float
                                             ) -> Dict[str, Any]:
    """M3b（**对照型的正向证据**）：`steps=[]` 但原报告可读 ⇒ 兜底给出真实状态。

    这不是变异而是"接线兜底"的正向读数：只读复算时不得把已执行过的步骤写 N/A。
    """

    prior = _load_prior_report(run_root)
    report = prior["report"]
    with tempfile.TemporaryDirectory(prefix="p12-mutation-") as tmp:
        runner = _runner_for_reconcile(plan=plan, run_root=run_root,
                                       out_dir=Path(tmp), steps=[], cap=cap)
        rec = runner.reconcile()
        checks = {row["name"]: row for row in rec["checks"]}
        wired = checks.get("capability_coverage_wired") or {}
        cap_group = (rec.get("signoff") or {}).get("capability_coverage") or {}
        return {"mutation": "M3b_no_steps_but_prior_report_readable",
                "expect": "green（兜底接线；描述接线不描述样本成败）",
                "ok": bool(wired.get("ok")) and bool(report.get("steps"))
                and cap_group.get("status") != STATUS.NOT_APPLICABLE,
                "prior_report": prior["path"],
                "prior_report_problem": prior["problem"],
                "steps": len(report.get("steps") or ()),
                "capability_status": cap_group.get("status"),
                "step_statuses": [(row["step"], row["status"])
                                  for row in (cap_group.get("steps") or ())],
                "detail": str(wired.get("detail"))[:200]}


def mutation_m4_refresh_batch_missing(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """M4：去掉刷新批声明（P19 的真实缺口形态）⇒ `refresh_batch_declared` 必须红。"""

    mutated = copy.deepcopy(plan)
    for spec in mutated.get("iterations") or ():
        if str(spec.get("iteration_label")) == "cand1":
            continue
        spec["family_refresh"] = [
            row for row in (spec.get("family_refresh") or ())
            if str(row.get("intent")) != "discover_new_root"]
    verdict = BUDGET.refresh_batch_declarations(mutated)
    return {"mutation": "M4_refresh_batch_missing", "expect": "red",
            "ok": not verdict["ok"], "problems": verdict["problems"][:3],
            "normal_ok": verdict["normal"].get("ok"),
            "family": {key: row["counts"] for key, row in verdict["family"].items()}}


def mutation_m5_normal_refresh_short(plan: Mapping[str, Any]) -> Dict[str, Any]:
    """M5：第二候选自然根退回第一候选的根数 ⇒ 整体通道刷新批 0 根 ⇒ 必须红。"""

    mutated = copy.deepcopy(plan)
    iterations = list(mutated.get("iterations") or ())
    if len(iterations) >= 2:
        iterations[1]["natural_roots"] = iterations[0].get("natural_roots")
    verdict = BUDGET.refresh_batch_declarations(mutated)
    return {"mutation": "M5_normal_refresh_short", "expect": "red",
            "ok": not verdict["ok"], "normal": verdict["normal"],
            "problems": verdict["problems"][:3]}


def control_c1_plan(plan: Mapping[str, Any]) -> Dict[str, Any]:
    verdict = BUDGET.required_reevaluation_declarations(plan)
    refresh = BUDGET.refresh_batch_declarations(plan)
    return {"control": "C1_plan_unmodified", "expect": "green",
            "ok": verdict["ok"] and refresh["ok"],
            "refresh_batch_ok": refresh["ok"],
            "normal_refresh": refresh["normal"],
            "family_refresh": {key: row["counts"]
                               for key, row in refresh["family"].items()},
            "per_iteration": [{key: row[key] for key in
                               ("iteration", "n_reevaluate", "n_discover",
                                "core_roots_declared_reevaluate", "old_root_intent_ok")}
                              for row in verdict["per_iteration"]]}


def control_c2_capability_wired(*, plan: Mapping[str, Any], run_root: Path,
                                cap: float) -> Dict[str, Any]:
    """C2：把原运行报告的逐步判定行接上 ⇒ 判据绿、六步有真实状态。"""

    prior = _load_prior_report(run_root)
    report = prior["report"]
    steps = [dict(row) for row in (report.get("steps") or ())]
    with tempfile.TemporaryDirectory(prefix="p12-mutation-") as tmp:
        runner = _runner_for_reconcile(plan=plan, run_root=run_root,
                                       out_dir=Path(tmp), steps=steps, cap=cap)
        rec = runner.reconcile()
        checks = {row["name"]: row for row in rec["checks"]}
        wired = checks.get("capability_coverage_wired") or {}
        cap_group = (rec.get("signoff") or {}).get("capability_coverage") or {}
        # 判据**不放宽**：接线必须给出真实来源与计数——能力覆盖组不得是
        # NOT_APPLICABLE，且 capability_coverage_wired 必须绿。
        # 本对照描述的是**接线**、不是样本成败：步3/步4 在 run5/run6 里本来就可能是
        # FAIL（共同根比较不完整），FAIL 不构成对照失败。
        return {"control": "C2_capability_wired", "expect": "green（接线生效）",
                "ok": bool(wired.get("ok")) and bool(steps)
                and cap_group.get("status") != STATUS.NOT_APPLICABLE,
                "prior_report": prior["path"],
                "prior_report_problem": prior["problem"],
                "steps": len(steps),
                "capability_status": cap_group.get("status"),
                "step_statuses": [(row["step"], row["status"])
                                  for row in (cap_group.get("steps") or ())],
                "detail": str(wired.get("detail"))[:200]}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="P12 定向变异测试（纯数据）")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--run-root", required=True,
                        help="既有运行目录（只读；提供 cap 与逐步判定行）")
    parser.add_argument("--cap", type=float, default=216.0)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    run_root = Path(args.run_root)
    cases = [
        control_c1_plan(plan),
        mutation_m1_drop_reevaluations(plan),
        mutation_m2_intent_written_discover(plan),
        control_c2_capability_wired(plan=plan, run_root=run_root, cap=args.cap),
        mutation_m3_capability_not_wired(plan=plan, run_root=run_root, cap=args.cap),
        mutation_m3b_fallback_reads_prior_report(plan=plan, run_root=run_root,
                                                 cap=args.cap),
        mutation_m4_refresh_batch_missing(plan),
        mutation_m5_normal_refresh_short(plan),
    ]
    payload = {"schema": "sitin-gate2-p12-mutations/1",
               "plan": str(args.plan), "run_root": str(run_root),
               "cases": cases, "ok": all(case["ok"] for case in cases),
               "note": ("每条修复至少一个定向变异变红；对照必须绿。"
                        "纯数据：0 桌、0 模型调用，不写任何运行目录")}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for case in cases:
        print("  {0:<5} {1:<34} 期望 {2:<5} {3}".format(
            "PASS" if case["ok"] else "FAIL",
            case.get("mutation") or case.get("control"), case["expect"],
            json.dumps({key: value for key, value in case.items()
                        if key in ("missing_core_reevaluations",
                                   "core_roots_declared_discover",
                                   "capability_status", "step_statuses",
                                   "rows_flipped")}, ensure_ascii=False)[:150]))
    print("  总判定：{0}".format("PASS（变异全红、对照全绿）"
                                 if payload["ok"] else "FAIL"))
    print("  结果已落盘：{0}".format(out))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
