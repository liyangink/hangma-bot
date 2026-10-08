"""R16 代际 2：统一验证集合稳健候选的真实作用域与精确回退。"""

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

from dataclasses import replace
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (HERE, _project_file(_PROJECT_ROOT, ROUTE / "tools")):
    sys.path.insert(0, str(path))

import r16_goal_first_preflight_02 as previous  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-02-20260921')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-02-20260921/behavior-preflight-01')
SOURCES = {
    "stable_v2": _project_file(_PROJECT_ROOT, HERE / "v2-parent-revalidation-20260920/parent/generation/candidate.py"),
    "C": _project_file(_PROJECT_ROOT, AUTHOR / "C/candidate.py"),
    "D": _project_file(_PROJECT_ROOT, AUTHOR / "D/candidate.py"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def without_routes(view: Any) -> Any:
    return replace(view, actions=tuple(replace(action, routes=()) for action in view.actions))


def with_partial_coverage(view: Any) -> Any:
    return replace(
        view,
        actions=tuple(replace(action, value_coverage="partial")
                      if action.routes else action for action in view.actions),
    )


def reversed_routes(view: Any) -> Any:
    return replace(
        view,
        actions=tuple(replace(action, routes=tuple(reversed(action.routes)))
                      for action in view.actions),
    )


def same(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (left["status"] == right["status"]
            and left["scores"] == right["scores"]
            and left["ordered_actions"] == right["ordered_actions"])


def main() -> None:
    if OUT.exists():
        raise SystemExit("R16代际2零桌证据已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    windows = previous.load_windows()
    scorers = {name: ActionValueScorer("r16-g2-" + name, path.read_text(encoding="utf-8"))
               for name, path in SOURCES.items()}
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r16-generation2-preflight/1",
        "sources": {name: {"path": str(path), "sha256": digest(path)}
                    for name, path in SOURCES.items()},
        "deduplicated_windows": len(windows), "tables_run": 0,
        "gate": {
            "active_windows_min": 1, "changed_choices_min": 1,
            "non_tie_changed_origins_min": 2, "non_tie_changed_seats_min": 2,
            "stage_ablation_exact_v2": True, "route_ablation_exact_v2": True,
            "partial_coverage_exact_v2": True, "route_order_invariant": True,
            "deterministic": True, "mean_evaluate_ms_max": 25.0,
        },
        "strength_claim": False, "confirmation_eligible": False,
    })
    baseline = {}
    for name, request, _ in windows:
        baseline[name] = previous.batch_reading(
            scorers["stable_v2"], previous.behavior.build_scoring_view(request))
    summaries = []
    for candidate_id in ("C", "D"):
        counts: Counter[str] = Counter()
        reasons: Counter[str] = Counter()
        changed_origins = set()
        changed_seats = set()
        failures = []
        changed_rows = []
        operations = []
        started = time.perf_counter()
        candidate_seconds = 0.0
        for name, request, origins in windows:
            view = previous.behavior.build_scoring_view(request)
            score_started = time.perf_counter()
            first_batch = scorers[candidate_id].score(view)
            candidate_seconds += time.perf_counter() - score_started
            first_ops = scorers[candidate_id].last_operation_count
            second_batch = scorers[candidate_id].score(view)
            second_ops = scorers[candidate_id].last_operation_count
            first = previous.batch_reading(scorers[candidate_id], view)
            operations.extend((first_ops, second_ops, scorers[candidate_id].last_operation_count))
            second = {
                "status": second_batch.status,
                "scores": {entry.action_key: entry.score for entry in second_batch.entries},
                "traces": {entry.action_key: dict(entry.trace) for entry in second_batch.entries},
                "ordered_actions": [entry.action_key for entry in sorted(
                    second_batch.entries, key=lambda entry: (-entry.score, entry.action_key))],
            }
            base = baseline[name]
            changed = first["action_key"] != base["action_key"]
            non_tie = (changed and base["scores"].get(first["action_key"])
                       != base["scores"].get(base["action_key"]))
            goal_rows = [trace.get("goal_set") for trace in first["traces"].values()]
            trace_complete = bool(goal_rows) and all(isinstance(item, dict) for item in goal_rows)
            active = trace_complete and any(item.get("mechanism_active") is True
                                            for item in goal_rows)
            for item in goal_rows:
                if isinstance(item, dict):
                    reasons[str(item.get("reason"))] += 1
            stage_masked = previous.batch_reading(
                scorers[candidate_id], replace(view, competition=None))
            stage_base = previous.batch_reading(
                scorers["stable_v2"], replace(view, competition=None))
            routes_masked = previous.batch_reading(
                scorers[candidate_id], without_routes(view))
            routes_base = previous.batch_reading(
                scorers["stable_v2"], without_routes(view))
            partial = previous.batch_reading(
                scorers[candidate_id], with_partial_coverage(view))
            partial_base = previous.batch_reading(
                scorers["stable_v2"], with_partial_coverage(view))
            reversed_reading = previous.batch_reading(
                scorers[candidate_id], reversed_routes(view))
            counts["windows"] += 1
            counts["active_windows"] += int(active)
            counts["changed_choices"] += int(changed)
            counts["non_tie_changed_choices"] += int(non_tie)
            counts["stage_ablation_mismatches"] += int(not same(stage_masked, stage_base))
            counts["route_ablation_mismatches"] += int(not same(routes_masked, routes_base))
            counts["partial_coverage_mismatches"] += int(not same(partial, partial_base))
            counts["route_order_mismatches"] += int(not same(reversed_reading, first))
            deterministic = (first["status"] == second["status"]
                             and first["scores"] == second["scores"]
                             and first["traces"] == second["traces"]
                             and first["ordered_actions"] == second["ordered_actions"]
                             and first_ops == second_ops)
            counts["determinism_mismatches"] += int(not deterministic)
            counts["missing_goal_trace_windows"] += int(not trace_complete)
            if non_tie:
                changed_origins.update(origins)
                changed_seats.add(view.visible_state.seat)
            if changed:
                changed_rows.append({"window_id": name, "origins": origins,
                                     "seat": view.visible_state.seat,
                                     "baseline_action": base["action_key"],
                                     "candidate_action": first["action_key"],
                                     "non_tie": non_tie})
            if first["status"] != "SCORED" or set(first["scores"]) != set(base["scores"]):
                failures.append(name + ":score_or_coverage")
        elapsed = time.perf_counter() - started
        mean_ms = candidate_seconds * 1000.0 / len(windows)
        gate_checks = {
            "active_windows": counts["active_windows"] > 0,
            "changed_choices": counts["changed_choices"] > 0,
            "non_tie_changed_origins": len(changed_origins) >= 2,
            "non_tie_changed_seats": len(changed_seats) >= 2,
            "stage_ablation_exact_v2": counts["stage_ablation_mismatches"] == 0,
            "route_ablation_exact_v2": counts["route_ablation_mismatches"] == 0,
            "partial_coverage_exact_v2": counts["partial_coverage_mismatches"] == 0,
            "route_order_invariant": counts["route_order_mismatches"] == 0,
            "deterministic": counts["determinism_mismatches"] == 0,
            "goal_trace_complete": counts["missing_goal_trace_windows"] == 0,
            "mean_evaluate_ms": mean_ms <= 25.0,
            "operations_within_limit": max(operations) <= scorers[candidate_id].max_operations,
            "no_contract_failures": not failures,
        }
        passed = all(gate_checks.values())
        summaries.append({
            "candidate_id": candidate_id,
            "status": "PASS_R16_G2_ZERO_TABLE_GATE" if passed else "FAIL_R16_G2_ZERO_TABLE_GATE",
            "counts": dict(sorted(counts.items())), "goal_reasons": dict(sorted(reasons.items())),
            "non_tie_changed_origins": sorted(changed_origins),
            "non_tie_changed_seats": sorted(changed_seats),
            "total_preflight_seconds": elapsed,
            "mean_evaluate_ms": mean_ms, "max_operations_observed": max(operations),
            "gate_checks": gate_checks, "failures": failures,
        })
        write_json(_project_file(_PROJECT_ROOT, OUT / f"{candidate_id}-changed-windows.json"), {
            "schema": "r16-generation2-changes/1", "rows": changed_rows})
    result = {
        "schema": "r16-generation2-preflight-result/1",
        "status": ("PASS_SOME_R16_G2_ZERO_TABLE_GATE"
                   if any(item["status"].startswith("PASS") for item in summaries)
                   else "FAIL_ALL_R16_G2_ZERO_TABLE_GATE"),
        "deduplicated_windows": len(windows), "candidates": summaries,
        "tables_run": 0, "strength_claim": False, "confirmation_eligible": False,
        "next": "全部失败则按冻结停止条件关闭R16并复盘公开投影充分性",
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
