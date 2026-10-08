"""R14：重放 MF1 已消费的最差 M 来源，定位 hard-sol-max 与稳定 V2 的动作差异。"""

from __future__ import annotations

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

import asyncio
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import multifidelity_prospective_audit as mf1  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_real_behavior as behavior  # noqa: E402
import sitin_search as search  # noqa: E402
from hangma_bot.policy.action_value import batch_to_ranked_candidates  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from p12_authorization import unified_document  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/hard-sol-max-m-failure-diagnosis-01-retry01-20260921')
CANDIDATE = mf1.STRUCTURAL_SOURCES["hard-sol-max"]
MF1_OUT = mf1.OUT
SOURCE = {"mix": "M", "root_index": 3, "focal_seat": 2,
          "source_id": "M:r03:s2"}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def original_table(candidate_id: str, table_no: int) -> Mapping[str, Any]:
    """读取 MF1 冻结桌结果，供确定性复现核对。"""

    name = f"{candidate_id}-M-r03-s2-t{table_no}.json"
    return json.loads((MF1_OUT / f"table{table_no}" / name).read_text(encoding="utf-8"))["table"]


def candidate_reading(scorer: Any, request: Any) -> dict[str, Any]:
    """在同一公开请求上运行候选生产计划并保留所选动作 trace。"""

    recorder = behavior.RecordingScorer(scorer)
    plan = asyncio.run(behavior.ActionValuePolicy(recorder).choose(
        request, behavior.DecisionBudget(1.0, 2.0, 3.0)))
    batch = recorder.batch
    view = behavior.build_scoring_view(request)
    ranked = batch_to_ranked_candidates(batch, view.actions) if batch is not None else ()
    traces = {entry.action_key: dict(entry.trace) for entry in batch.entries} if batch else {}
    action_key = plan.candidates[0].action_key if plan.candidates else None
    return {
        "status": batch.status if batch is not None else "FAILED",
        "action_key": action_key,
        "raw_action_key": ranked[0].action_key if ranked else None,
        "trace": traces.get(action_key),
        "ordered_actions": [item.action_key for item in plan.candidates],
    }


def baseline_reading(request: Any) -> dict[str, Any]:
    """在同一公开请求上运行稳定 V2 生产策略。"""

    policy = natural.stage.build_panel_policy(natural.BASELINE_FOCAL_POLICY, lambda: 0.0)
    plan = asyncio.run(policy.choose(request, behavior.DecisionBudget(1.0, 2.0, 3.0)))
    return {"action_key": plan.candidates[0].action_key if plan.candidates else None,
            "ordered_actions": [item.action_key for item in plan.candidates]}


def main() -> None:
    """执行 4 桌已消费来源重放，产出可见请求上的比较反馈。"""

    if OUT.exists():
        raise SystemExit("诊断目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    auth = unified_document(
        batch_label=OUT.name, authorization_id="r14-hard-sol-max-m-diagnosis-01",
        accounts={"tables_full": 4}, issued_by="lead",
        issued_at_utc=search.utc_now(), legacy_alias=False)
    auth.update({
        "issuance_basis": "R14 先定位 MF1 已消费最差 M 来源；4桌、0模型、0确认",
        "scope": "只重放 M/root03/焦点座位2 的稳定V2与hard-sol-max；不得作为新增效果样本",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), auth)
    natural.require_authorization(auth)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(auth))
    source_text = CANDIDATE.read_text(encoding="utf-8")
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r14-hard-sol-max-m-failure-diagnosis/1",
        "purpose": "consumed_development_failure_diagnosis",
        "selection_eligible": False, "confirmation_eligible": False,
        "source": SOURCE, "panel_seed": mf1.PANEL_SEED,
        "candidate": {"path": str(CANDIDATE),
                      "sha256": hashlib.sha256(source_text.encode()).hexdigest()},
        "mf1_manifest_sha256": hashlib.sha256((MF1_OUT / "manifest.json").read_bytes()).hexdigest(),
        "planned_tables": 4,
        "information_boundary": "比较只读取焦点策略收到的PlayerObservation及规则投影；不读取WorldState",
    })
    contract = json.loads(mf1.CONTRACT.read_text(encoding="utf-8"))
    plans = mf1._plans(SOURCE)
    scorer = ActionValueScorer("hard-sol-max-diagnosis", source_text)
    all_requests: list[tuple[str, Any]] = []
    stages = []
    for arm, candidate_id in (("baseline", mf1.BASELINE_ID), ("candidate", "hard-sol-max")):
        requests: list[Any] = []
        reservation = ledger.reserve(
            step_id="diagnosis:" + arm, account="tables_full", amount=2,
            note="MF1 已消费来源重放，不增加选留或确认样本")
        try:
            result = natural.run_arm_stage(
                arm=arm, plans=plans, candidate_scorer=scorer,
                opponent_policies=contract["panel"]["opponent_scenarios"]["M"]["opponent_policies"],
                versions_block=natural.stage.contract_versions_block(contract),
                step_limit=int(contract["stop"]["step_limit"]),
                value_limits=natural.ValueAnalysisLimits(),
                decision_observer=requests.append)
        finally:
            ledger.settle(reservation, usage_unknown=True,
                          note="异常保守结算；成功后用实际桌数复核")
        if result["status"] != "complete":
            raise RuntimeError(f"{arm} 诊断阶段未完成")
        ledger.settle(reservation, actual=len(result["tables"]))
        reproduced = []
        for table_no, row in enumerate(result["tables"], start=1):
            original = original_table(candidate_id, table_no)
            same = (row["scores_by_seat"] == original["scores_by_seat"]
                    and row["match_status"] == original["match_status"])
            reproduced.append(same)
        if not all(reproduced):
            raise RuntimeError(f"{arm} 结果未复现 MF1，停止诊断")
        stages.append({"arm": arm, "requests": len(requests),
                       "tables_reproduced": reproduced,
                       "focal_stage_score": result["focal_stage_score"],
                       "u_low": result["u_low"], "u_high": result["u_high"]})
        all_requests.extend((arm, request) for request in requests)

    counts: Counter[str] = Counter()
    basis_counts: Counter[str] = Counter()
    changed_rows = []
    seen = set()
    for trajectory_arm, request in all_requests:
        view = behavior.build_scoring_view(request)
        view_id = behavior.digest(view.candidate_view())
        dedupe_key = (trajectory_arm, view_id)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        baseline = baseline_reading(request)
        candidate = candidate_reading(scorer, request)
        if not baseline["action_key"] or candidate["status"] != "SCORED" or not candidate["action_key"]:
            raise RuntimeError("诊断请求不可比较")
        before = baseline["action_key"]
        after = candidate["action_key"]
        changed = before != after
        counts["views"] += 1
        counts[f"trajectory:{trajectory_arm}"] += 1
        counts["preferred_changed"] += int(changed)
        if changed:
            transition = before.split(":", 1)[0] + "->" + after.split(":", 1)[0]
            counts["transition:" + transition] += 1
            trace = candidate.get("trace") or {}
            basis = str(trace.get("basis"))
            basis_counts[basis] += 1
            row = {
                "trajectory_arm": trajectory_arm,
                "window_id": view_id,
                "phase": view.visible_state.phase,
                "baseline_action": before,
                "candidate_action": after,
                "candidate_trace": trace,
                "baseline_top5": baseline["ordered_actions"][:5],
                "candidate_top5": candidate["ordered_actions"][:5],
            }
            changed_rows.append(row)
    changed_rows.sort(key=lambda row: (row["trajectory_arm"], row["phase"], row["window_id"]))
    with (_project_file(_PROJECT_ROOT, OUT / "changed-decisions.jsonl")).open("x", encoding="utf-8") as handle:
        for row in changed_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "schema": "r14-hard-sol-max-m-failure-diagnosis-summary/1",
        "stages": stages,
        "counts": dict(sorted(counts.items())),
        "changed_candidate_basis": dict(sorted(basis_counts.items())),
        "changed_decisions": len(changed_rows),
        "spent": ledger.account_summary(),
        "selection_eligible": False, "confirmation_eligible": False,
        "interpretation": "同一公开请求上的行为差异用于作者反馈；单根结果不标注动作对错",
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "summary.json"), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
