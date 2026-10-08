"""R16 代际 1：复核目标排序候选的动作相关性与双重反事实消融。"""

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
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import sitin_real_behavior as behavior  # noqa: E402
from hangma_bot.policy.action_value import batch_to_ranked_candidates  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921/behavior-preflight-02')
SOURCES = {
    "stable_v2": _project_file(_PROJECT_ROOT, HERE / "v2-parent-revalidation-20260920/parent/generation/candidate.py"),
    "A": _project_file(_PROJECT_ROOT, AUTHOR / "A/candidate.py"),
    "B": _project_file(_PROJECT_ROOT, AUTHOR / "B/candidate.py"),
}
PANELS = (
    _project_file(_PROJECT_ROOT, HERE / "batch03-known-root-diagnostic/panel.json"),
    _project_file(_PROJECT_ROOT, HERE / "comparable-shape-second-diagnostic-20260920/panel.json"),
    _project_file(_PROJECT_ROOT, HERE / "discard-shape-mix-diagnostic-20260920/panel.json"),
    _project_file(_PROJECT_ROOT, HERE / "followup-balance-diagnostic-20260920/panel.json"),
    _project_file(_PROJECT_ROOT, HERE / "followup-quality-diagnostic-20260920/panel.json"),
    _project_file(_PROJECT_ROOT, HERE / "pattern-generalization-diagnostic-v2-20260920/panel.json"),
    _project_file(_PROJECT_ROOT, HERE / "piao-opportunity-probe-20260920/panel.json"),
    _project_file(_PROJECT_ROOT, HERE / "real-behavior-panel-v1/panel.json"),
    _project_file(_PROJECT_ROOT, HERE / "route-decision-diagnostic-20260920/panel.json"),
    _project_file(_PROJECT_ROOT, HERE / "selfdraw-tempo-diagnostic-20260920/panel.json"),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_windows() -> list[tuple[str, Any, list[str]]]:
    """合并已消费真实面板，同一可见视图只保留一次。"""

    by_name: dict[str, tuple[Any, list[str]]] = {}
    for panel in PANELS:
        _, windows = behavior.load_panel(panel)
        for name, request in windows:
            if name not in by_name:
                by_name[name] = (request, [])
            by_name[name][1].append(str(panel))
    return [(name, request, origins) for name, (request, origins) in sorted(by_name.items())]


def batch_reading(scorer: Any, view: Any) -> dict[str, Any]:
    """在指定视图上保留分数、排序和目标 trace。"""

    scored = scorer.score(view)
    ranked = batch_to_ranked_candidates(scored, view.actions) if scored.status == "SCORED" else ()
    return {
        "status": scored.status,
        "scores": {entry.action_key: entry.score for entry in scored.entries},
        "traces": {entry.action_key: dict(entry.trace) for entry in scored.entries},
        "action_key": ranked[0].action_key if ranked else None,
        "ordered_actions": [item.action_key for item in ranked],
    }


def without_target_routes(view: Any) -> Any:
    """只抹去候选目标层消费的条件路线，保留同一公开观察与其他动作事实。"""

    return replace(
        view,
        actions=tuple(replace(action, routes=()) for action in view.actions),
    )


def production_reading(scorer: Any, request: Any) -> dict[str, Any]:
    view = behavior.build_scoring_view(request)
    row = batch_reading(scorer, view)
    plan = behavior.evaluate_request(scorer, behavior.digest(view.candidate_view()), request)
    row["action_key"] = plan["action_key"]
    row["ordered_actions"] = plan["ordered_actions"]
    row["degraded_reasons"] = plan["degraded_reasons"]
    return row


def goal_trace(reading: dict[str, Any], action_key: str | None) -> dict[str, Any] | None:
    if action_key is None:
        return None
    value = reading["traces"].get(action_key, {}).get("goal_target")
    return value if isinstance(value, dict) else None


def comparable_target(before: dict[str, Any] | None, after: dict[str, Any] | None) -> bool:
    """改选前后必须有动作相关、非共同常数的目标事实。"""

    if before is None or after is None:
        return False
    required = (
        "mechanism_active", "stage_account_ready", "conditional_score_delta",
        "conditional_rank_low", "conditional_rank_high", "boundary_margin_before",
        "boundary_margin_after", "target_priority", "fallback_exact_v2", "reason",
    )
    if any(key not in before or key not in after for key in required):
        return False
    if after.get("mechanism_active") is not True or after.get("stage_account_ready") is not True:
        return False
    signatures = (
        "conditional_score_delta", "conditional_rank_low", "conditional_rank_high",
        "boundary_margin_after", "target_priority", "selected_followup_key",
        "selected_route_followup_discard",
    )
    return any(before.get(key) != after.get(key) for key in signatures)


def main() -> None:
    """零桌裁定两个候选；阶段账消融必须逐分回退 V2。"""

    if OUT.exists():
        raise SystemExit("R16行为预检目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    windows = load_windows()
    scorers = {name: ActionValueScorer("r16-preflight-" + name,
                                       path.read_text(encoding="utf-8"))
               for name, path in SOURCES.items()}
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r16-goal-first-behavior-preflight/2",
        "sources": {name: {"path": str(path), "sha256": digest(path)}
                    for name, path in SOURCES.items()},
        "panels": [{"path": str(path), "sha256": digest(path)} for path in PANELS],
        "deduplicated_windows": len(windows),
        "gate": {
            "active_and_changed": True,
            "non_tie_changed_origins_min": 2,
            "non_tie_changed_seats_min": 2,
            "action_related_target_change": True,
            "masked_stage_account_exact_v2": True,
            "masked_target_routes_exact_v2": True,
            "target_route_ablation_removes_change": True,
            "mean_evaluate_ms_max": 25.0,
        },
        "effect_tables": 0, "model_calls": 0,
        "strength_claim": False, "confirmation_eligible": False,
    })
    baseline = {}
    masked_baseline = {}
    route_masked_baseline = {}
    for name, request, _ in windows:
        view = behavior.build_scoring_view(request)
        baseline[name] = production_reading(scorers["stable_v2"], request)
        masked_baseline[name] = batch_reading(scorers["stable_v2"],
                                              replace(view, competition=None))
        route_masked_baseline[name] = batch_reading(
            scorers["stable_v2"], without_target_routes(view))
    summaries = []
    for candidate_id in ("A", "B"):
        counts: Counter[str] = Counter()
        states: Counter[str] = Counter()
        problems = []
        rows = []
        changed_origins = set()
        changed_seats = set()
        started = time.perf_counter()
        for name, request, origins in windows:
            view = behavior.build_scoring_view(request)
            stable = baseline[name]
            got = production_reading(scorers[candidate_id], request)
            masked = batch_reading(scorers[candidate_id], replace(view, competition=None))
            stable_masked = masked_baseline[name]
            masked_exact = (masked["status"] == stable_masked["status"]
                            and masked["scores"] == stable_masked["scores"]
                            and masked["ordered_actions"] == stable_masked["ordered_actions"])
            route_masked = batch_reading(
                scorers[candidate_id], without_target_routes(view))
            stable_route_masked = route_masked_baseline[name]
            route_masked_exact = (
                route_masked["status"] == stable_route_masked["status"]
                and route_masked["scores"] == stable_route_masked["scores"]
                and route_masked["ordered_actions"] == stable_route_masked["ordered_actions"])
            changed = got["action_key"] != stable["action_key"]
            v2_before = stable["scores"].get(stable["action_key"])
            v2_after = stable["scores"].get(got["action_key"])
            non_tie = changed and v2_before is not None and v2_after is not None \
                and v2_before != v2_after
            before_trace = goal_trace(got, stable["action_key"])
            after_trace = goal_trace(got, got["action_key"])
            related = changed and comparable_target(before_trace, after_trace)
            traces = [trace.get("goal_target") for trace in got["traces"].values()]
            traces_present = bool(traces) and all(isinstance(trace, dict) for trace in traces)
            window_active = traces_present and any(
                trace.get("mechanism_active") is True for trace in traces)
            for trace in traces:
                if isinstance(trace, dict):
                    states[str(trace.get("reason"))] += 1
            counts["windows"] += 1
            counts["active_windows"] += int(window_active)
            counts["changed_choices"] += int(changed)
            counts["non_tie_changed_choices"] += int(non_tie)
            counts["action_related_changes"] += int(related)
            counts["masked_fallback_mismatches"] += int(not masked_exact)
            counts["route_masked_fallback_mismatches"] += int(not route_masked_exact)
            counts["changed_choices_removed_by_route_mask"] += int(
                changed and route_masked_exact
                and route_masked["action_key"] == stable_route_masked["action_key"])
            counts["missing_goal_trace_windows"] += int(not traces_present)
            if got["status"] != "SCORED" or got["action_key"] is None:
                problems.append(name + ":candidate_not_scored")
            if set(got["scores"]) != set(stable["scores"]):
                problems.append(name + ":action_coverage")
            if not traces_present:
                problems.append(name + ":goal_trace_missing")
            if not masked_exact:
                problems.append(name + ":masked_stage_not_exact_v2")
            if not route_masked_exact:
                problems.append(name + ":masked_routes_not_exact_v2")
            unexpected = [reason for reason in got.get("degraded_reasons", [])
                          if "评分完成" not in reason]
            if unexpected:
                problems.append(name + ":unexpected_plan_reason")
            if changed:
                visible = view.visible_state
                if non_tie:
                    changed_origins.update(origins)
                    changed_seats.add(visible.seat)
                rows.append({
                    "window_id": name, "origins": origins,
                    "seat": visible.seat, "phase": visible.phase,
                    "baseline_action": stable["action_key"],
                    "candidate_action": got["action_key"],
                    "non_tie_change": non_tie,
                    "action_related_target_change": related,
                    "v2_before_score": v2_before, "v2_after_score": v2_after,
                    "baseline_action_goal_trace": before_trace,
                    "candidate_action_goal_trace": after_trace,
                })
        elapsed = time.perf_counter() - started
        mean_ms = 1000.0 * elapsed / len(windows)
        gate_checks = {
            "active_windows": counts["active_windows"] > 0,
            "changed_choices": counts["changed_choices"] > 0,
            "non_tie_changed_origins": len(changed_origins) >= 2,
            "non_tie_changed_seats": len(changed_seats) >= 2,
            "action_related_target_change": counts["action_related_changes"] > 0,
            "masked_stage_account_exact_v2": counts["masked_fallback_mismatches"] == 0,
            "masked_target_routes_exact_v2": counts["route_masked_fallback_mismatches"] == 0,
            "target_route_ablation_removes_change": (
                counts["changed_choices_removed_by_route_mask"] > 0),
            "goal_trace_complete": counts["missing_goal_trace_windows"] == 0,
            "mean_evaluate_ms": mean_ms <= 25.0,
            "no_contract_problems": not problems,
        }
        passed = all(gate_checks.values())
        summaries.append({
            "candidate_id": candidate_id,
            "status": "PASS_R16_ZERO_TABLE_GATE" if passed else "FAIL_R16_ZERO_TABLE_GATE",
            "counts": dict(sorted(counts.items())),
            "goal_reasons": dict(sorted(states.items())),
            "non_tie_changed_origins": sorted(changed_origins),
            "non_tie_changed_seats": sorted(changed_seats),
            "elapsed_seconds": elapsed, "mean_evaluate_ms": mean_ms,
            "gate_checks": gate_checks, "problems": problems,
        })
        write_json(_project_file(_PROJECT_ROOT, OUT / f"{candidate_id}-changed-windows.json"),
                   {"schema": "r16-goal-first-changes/2", "rows": rows})
    result = {
        "schema": "r16-goal-first-behavior-preflight-result/2",
        "status": ("PASS_SOME_R16_ZERO_TABLE_GATE"
                   if any(row["status"] == "PASS_R16_ZERO_TABLE_GATE" for row in summaries)
                   else "FAIL_ALL_R16_ZERO_TABLE_GATE"),
        "deduplicated_windows": len(windows),
        "candidates": summaries,
        "effect_tables": 0, "model_calls": 0,
        "strength_claim": False, "confirmation_eligible": False,
        "next": "只让通过候选进入同一全新完整阶段开发面板",
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
