#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P12 · 封顶红线记账口径的**回归反例**（2026-09-18 run4）。

背景（Lead 在 run4 复现的现象）：`step5-cold-resume` 处读数
`settled 136 + inflight 32 + planned 64 = 232 > 216` 被停。判定结论见报告：
这是**记账重复计数**（在途那 32 被计两次），不是额度不足。

本脚本在**纯数据**上做四件事（0 桌、0 模型调用，不写任何运行目录）：

1. `run4_replay_fixed`：按 run4 真实红线日志的**时间序列**重放（每一步取该时刻之前的
   账本状态 + 该调用声明的范围/计划量），用**修后的口径**算 —— 必须全部不超封顶；
2. `run4_old_formula`：同一份数据用**旧口径**（对所有行求和当"已结算"再 +在途）算 ——
   必须复现 `232 > 216` 的假红线（这就是缺陷本身）；
3. `true_overflow_new_candidate`：换成"一个还没有任何已完成工作的新候选"，
   计划 96 桌 —— **必须仍然 exceeds_cap**（红线不得被改废）；
4. `no_evidence_no_deduction`：在途且有重叠，但**盘上没有结果证据** —— 
   不允许扣减，必须 exceeds_cap；同一数据**有证据**时必须 within_cap（对照组）。
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
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import gate2_run as G                 # noqa: E402  （纯函数 + 只读方法）
import p12_reconcile as REC           # noqa: E402

#: run4 每次调用声明的范围（与 gate2_run 的 call site 逐字对应）。
RUN4_CALLS: Dict[str, Dict[str, Any]] = {
    "step2-conditional": {"channels": ["conditional"], "iteration": "cand1"},
    "step3-iter1-complete": {"channels": ["natural", "family"], "iteration": "cand1"},
    "step3-iter2-conditional": {"channels": ["conditional"], "iteration": "cand2"},
    "step5-inject": {"channels": ["natural"], "iteration": "cand2"},
    "step5-cold-resume": {"channels": ["natural", "family"], "iteration": "cand2"},
    # 假想的下一次调用（run4 被假红线停住，没能走到）：第二候选收尾
    "step3-iter2-complete": {"channels": ["natural", "family"], "iteration": "cand2"},
}

#: 调用顺序（收尾那次用日志之外的计划量，见 RUN4_NEXT_PLANNED）
RUN4_ORDER: List[str] = ["step2-conditional", "step3-iter1-complete",
                         "step3-iter2-conditional", "step5-inject",
                         "step5-cold-resume"]
RUN4_NEXT_PLANNED = 96.0     # natural_full(cand2) 64 + family_fill(cand2) 32


def _ledger_upto(ledger: Mapping[str, Any], at_utc: str) -> Dict[str, Any]:
    """该时刻之前的账本状态（账行按 at_utc 排序，ISO 串可直接比较）。"""

    rows = [dict(row) for row in (ledger.get("reservations") or ())
            if str(row.get("at_utc") or "") <= str(at_utc)]
    return {"reservations": rows}


def _candidate12(run_root: Path, plan: Mapping[str, Any], iteration: str) -> str:
    runner = G.Gate2Runner.__new__(G.Gate2Runner)
    runner.run_root = Path(run_root)
    runner.plan = dict(plan)
    return runner.iteration_candidate12(iteration)


def _adoptable(run_root: Path, ledger: Mapping[str, Any]) -> Dict[str, bool]:
    runner = G.Gate2Runner.__new__(G.Gate2Runner)
    runner.run_root = Path(run_root)
    return {str(row.get("step_id")): runner._step_result_on_disk(str(row.get("step_id")))
            for row in (ledger.get("reservations") or ())
            if str(row.get("status")) == "reserved"
            and str(row.get("account")) == "tables_full"}


def replay_run4(*, run_root: Path, plan: Mapping[str, Any],
                evidence_dir: Path) -> Dict[str, Any]:
    """按真实红线日志重放 run4 的五次调用（+ 假想的第六次）。"""

    ledger = json.loads((Path(run_root) / "av-ledger.json").read_text(encoding="utf-8"))
    redline = []
    log_path = Path(evidence_dir) / "budget-redline.jsonl"
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            redline.append(json.loads(line))
    cap = float(redline[0]["cap"]) if redline else 216.0
    steps: List[Dict[str, Any]] = []
    for row in sorted(redline, key=lambda item: str(item.get("at_utc"))):
        where = str(row.get("where"))
        spec = RUN4_CALLS.get(where) or {}
        state = _ledger_upto(ledger, str(row.get("at_utc")))
        candidate12 = _candidate12(run_root, plan, str(spec.get("iteration")))
        adoptable = _adoptable(run_root, state)
        fixed = G.redline_accounting(
            ledger=state, planned=float(row.get("planned_this_call") or 0.0), cap=cap,
            scope_channels=spec.get("channels") or (), scope_candidate12=candidate12,
            adoptable_steps=adoptable)
        # 旧口径（缺陷复现）：对所有行求和当"已结算"，再加上在途
        old_settled = round(sum(float(item.get("charged") or 0.0)
                                for item in state["reservations"]
                                if str(item.get("account")) == "tables_full"), 6)
        old_inflight = round(sum(float(item.get("amount") or 0.0)
                                 for item in state["reservations"]
                                 if str(item.get("account")) == "tables_full"
                                 and str(item.get("status")) == "reserved"), 6)
        old_sum = round(old_settled + old_inflight
                        + float(row.get("planned_this_call") or 0.0), 6)
        steps.append({
            "where": where, "at_utc": row.get("at_utc"),
            "scope_channels": list(spec.get("channels") or ()),
            "scope_candidate12": candidate12,
            "planned_this_call": row.get("planned_this_call"),
            "old_formula": {"settled_all_rows": old_settled, "inflight": old_inflight,
                            "sum": old_sum,
                            "verdict": "within_cap" if old_sum <= cap else "exceeds_cap"},
            "fixed": {key: fixed[key] for key in (
                "settled", "inflight", "planned_new", "overlap_deducted", "sum",
                "worst_case_sum", "verdict")},
            "overlap_rows": fixed["overlap_rows"],
        })
    # —— 假想的第六次调用：第二候选收尾（run4 被假红线停住，没能走到） ——
    last_at = max((str(row.get("at_utc")) for row in redline), default="")
    state = _ledger_upto(ledger, "9999")
    candidate12 = _candidate12(run_root, plan, "cand2")
    adoptable = _adoptable(run_root, state)
    fixed_next = G.redline_accounting(
        ledger=state, planned=RUN4_NEXT_PLANNED, cap=cap,
        scope_channels=("natural", "family"), scope_candidate12=candidate12,
        adoptable_steps=adoptable)
    steps.append({
        "where": "step3-iter2-complete（假想，被假红线停住后本应发生的下一步）",
        "at_utc": last_at, "scope_channels": ["natural", "family"],
        "scope_candidate12": candidate12, "planned_this_call": RUN4_NEXT_PLANNED,
        "old_formula": {"verdict": ("within_cap"
                                    if (G.ledger_readings(ledger)["committed"]
                                        + RUN4_NEXT_PLANNED) <= cap
                                    else "exceeds_cap"),
                        "settled_all_rows": G.ledger_readings(ledger)["committed"],
                        "inflight": G.ledger_readings(ledger)["inflight"],
                        "sum": round(G.ledger_readings(ledger)["committed"]
                                     + RUN4_NEXT_PLANNED, 6)},
        "fixed": {key: fixed_next[key] for key in (
            "settled", "inflight", "planned_new", "overlap_deducted", "sum",
            "worst_case_sum", "verdict")},
        "overlap_rows": fixed_next["overlap_rows"],
    })
    return {"cap": cap, "steps": steps,
            "ok": all(step["fixed"]["verdict"] in ("within_cap",
                                                   "within_cap_with_adoption")
                      for step in steps),
            "old_formula_ok": all(step["old_formula"]["verdict"] == "within_cap"
                                  for step in steps),
            "note": ("修复后：run4 全部调用不超封顶（且被停住的那次本应继续）；"
                     "旧口径：至少一次 exceeds_cap（假红线 = 在途被计两次）")}


def true_overflow_case() -> Dict[str, Any]:
    """真实超额：一个还没有任何已完成工作的新候选，计划 96 桌 ⇒ 必须 exceeds_cap。"""

    ledger = {"reservations": [
        {"step_id": "natural:d7a10efcbfd9:H:2", "account": "tables_full",
         "status": "settled", "charged": 32.0, "at_utc": "2026-09-18T07:06:00Z"},
        {"step_id": "natural:d7a10efcbfd9:M:2", "account": "tables_full",
         "status": "settled", "charged": 32.0, "at_utc": "2026-09-18T07:07:00Z"},
        {"step_id": "natural:544f7d353965:H:2", "account": "tables_full",
         "status": "settled", "charged": 32.0, "at_utc": "2026-09-18T07:10:00Z"},
        {"step_id": "natural:544f7d353965:M:2", "account": "tables_full",
         "status": "settled", "charged": 32.0, "at_utc": "2026-09-18T07:11:00Z"},
        {"step_id": "natural:544f7d353965:H:2", "account": "tables_full",
         "status": "settled", "charged": 32.0, "superseded": True,
         "at_utc": "2026-09-18T07:11:30Z"},
    ]}
    accounting = G.redline_accounting(
        ledger=ledger, planned=96.0, cap=216.0,
        scope_channels=("natural", "family"), scope_candidate12="ffffffffffff",
        adoptable_steps={})
    return {"case": "true_overflow_new_candidate", "accounting": {
        key: accounting[key] for key in ("settled", "inflight", "overlap_deducted",
                                        "planned_new", "sum", "verdict")},
        "ok": accounting["verdict"] == "exceeds_cap",
        "detail": ("已结算 160（含 32 失败重试保留费）+ 新候选 96 桌全新工作 = 256 > 216 "
                   "⇒ 必须停（红线没被改废）")}


def no_evidence_case() -> Dict[str, Any]:
    """在途有重叠但盘上无证据 ⇒ 不得扣减（必须 exceeds_cap）；有证据 ⇒ within_cap。"""

    ledger = {"reservations": [
        {"step_id": "natural:d7a10efcbfd9:H:2", "account": "tables_full",
         "status": "settled", "charged": 140.0, "at_utc": "2026-09-18T07:06:00Z"},
        {"step_id": "natural:544f7d353965:H:2", "account": "tables_full",
         "status": "reserved", "amount": 32.0, "charged": 32.0,
         "at_utc": "2026-09-18T07:09:50Z"},
    ]}
    without = G.redline_accounting(
        ledger=ledger, planned=64.0, cap=216.0, scope_channels=("natural",),
        scope_candidate12="544f7d353965", adoptable_steps={})
    with_evidence = G.redline_accounting(
        ledger=ledger, planned=64.0, cap=216.0, scope_channels=("natural",),
        scope_candidate12="544f7d353965",
        adoptable_steps={"natural:544f7d353965:H:2": True})
    return {"case": "no_evidence_no_deduction",
            "without_evidence": {key: without[key] for key in
                                 ("settled", "inflight", "overlap_deducted",
                                  "planned_new", "sum", "verdict")},
            "with_evidence": {key: with_evidence[key] for key in
                              ("settled", "inflight", "overlap_deducted",
                               "planned_new", "sum", "verdict")},
            "ok": (without["verdict"] == "exceeds_cap"
                   and with_evidence["verdict"] in ("within_cap",
                                                    "within_cap_with_adoption")),
            "detail": ("无盘上证据 ⇒ 不扣减 ⇒ 140+32+64=236 > 216（停）；"
                       "有证据 ⇒ 扣掉在途 32 ⇒ 140+32+32=204 ≤ 216（继续）")}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="P12 封顶红线记账回归（纯数据）")
    parser.add_argument("--run-root", required=True, help="run4 运行目录（只读）")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--evidence-dir", required=True,
                        help="run4 的证据目录（含 budget-redline.jsonl）")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    replay = replay_run4(run_root=Path(args.run_root), plan=plan,
                         evidence_dir=Path(args.evidence_dir))
    overflow = true_overflow_case()
    no_evidence = no_evidence_case()
    payload = {"schema": "sitin-gate2-redline-regression/1",
               "run_root": str(args.run_root),
               "evidence_dir": str(args.evidence_dir),
               "replay": replay, "true_overflow": overflow,
               "no_evidence": no_evidence,
               "ok": bool(replay["ok"] and not replay["old_formula_ok"]
                          and overflow["ok"] and no_evidence["ok"]),
               "note": ("纯数据回归：0 桌、0 模型调用；期望 = 修后全部不超、"
                        "旧口径复现假红线、真实超额仍红、无证据不扣减")}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("封顶红线记账回归（run4 真实日志重放）")
    print("  cap = {0}".format(replay["cap"]))
    for step in replay["steps"]:
        old = step["old_formula"]
        new = step["fixed"]
        print("  {0:<62} 旧: settled {1:>6} + inflight {2:>5} + planned {3:>5} = {4:>6} {5:<12} |"
              " 新: settled {6:>6} + inflight {7:>5} + 新增 {8:>5} = {9:>6} {10}".format(
                  str(step["where"])[:62], old.get("settled_all_rows"),
                  old.get("inflight"), step["planned_this_call"], old.get("sum"),
                  old.get("verdict"), new["settled"], new["inflight"],
                  new["planned_new"], new["sum"], new["verdict"]))
    print("  重放判定：修后全部不超 = {0}；旧口径复现假红线 = {1}".format(
        replay["ok"], not replay["old_formula_ok"]))
    print("  真实超额用例：{0}（{1}）".format(
        overflow["accounting"]["verdict"], overflow["detail"]))
    print("  无证据不扣减：无证据={0} / 有证据={1}".format(
        no_evidence["without_evidence"]["verdict"],
        no_evidence["with_evidence"]["verdict"]))
    print("  总判定：{0}".format("PASS" if payload["ok"] else "FAIL"))
    print("  结果已落盘：{0}".format(out))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
