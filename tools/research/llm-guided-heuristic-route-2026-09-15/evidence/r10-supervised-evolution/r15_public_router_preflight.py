"""R15：在既有真实公开观察上验证父代路由的可达、等价和行为覆盖。"""

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
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r15-public-state-router-author-01-20260921')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r15-public-state-router-author-01-20260921/behavior-preflight-01')
SOURCES = {
    "stable_v2": _project_file(_PROJECT_ROOT, HERE / "v2-parent-revalidation-20260920/parent/generation/candidate.py"),
    "specialist": _project_file(_PROJECT_ROOT, HERE / (
        "strong-seeds-20260920/hard-sol-max/run/iterations/iter-02/generation/candidate.py")),
    "router": _project_file(_PROJECT_ROOT, AUTHOR / "candidate.py"),
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
    """合并已消费面板并按候选可见视图去重，不产生效果样本。"""

    by_name: dict[str, tuple[Any, list[str]]] = {}
    for panel in PANELS:
        _, windows = behavior.load_panel(panel)
        for name, request in windows:
            if name not in by_name:
                by_name[name] = (request, [])
            by_name[name][1].append(str(panel))
    return [(name, request, origins) for name, (request, origins) in sorted(by_name.items())]


def reading(scorer: Any, request: Any) -> dict[str, Any]:
    """保留原始分数、审计 trace 与生产排序。"""

    view = behavior.build_scoring_view(request)
    scored = scorer.score(view)
    plan = behavior.evaluate_request(scorer, behavior.digest(view.candidate_view()), request)
    return {
        "status": scored.status,
        "scores": {entry.action_key: entry.score for entry in scored.entries},
        "traces": {entry.action_key: dict(entry.trace) for entry in scored.entries},
        "action_key": plan["action_key"],
        "ordered_actions": plan["ordered_actions"],
        "degraded_reasons": plan["degraded_reasons"],
    }


def router_record(got: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    """要求同一窗口所有动作携带完全相同的父代路由记录。"""

    values = [trace.get("parent_router") for trace in got["traces"].values()]
    if not values or any(not isinstance(value, dict) for value in values):
        return None, False
    first = values[0]
    return first, all(value == first for value in values)


def main() -> None:
    """执行零桌、零模型行为门；任一父代混分或不可达即失败。"""

    if OUT.exists():
        raise SystemExit("R15行为预检目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    windows = load_windows()
    scorers = {name: ActionValueScorer("r15-preflight-" + name,
                                       path.read_text(encoding="utf-8"))
               for name, path in SOURCES.items()}
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r15-public-state-parent-router-preflight/1",
        "sources": {name: {"path": str(path), "sha256": digest(path)}
                    for name, path in SOURCES.items()},
        "panels": [{"path": str(path), "sha256": digest(path)} for path in PANELS],
        "deduplicated_windows": len(windows),
        "gate": {
            "both_unique_parent_branches_hit": True,
            "candidate_exactly_equals_selected_parent": True,
            "unknown_fallback_exact_v2": True,
            "non_tie_changed_choice": True,
            "changed_origins_min": 2,
            "changed_seats_min": 2,
            "changed_transition_families_min": 2,
            "mean_evaluate_ms_max": 25.0,
        },
        "effect_tables": 0, "model_calls": 0,
        "selection_eligible": False, "confirmation_eligible": False,
    })
    parents: dict[str, dict[str, dict[str, Any]]] = {name: {} for name in ("stable_v2", "specialist")}
    for name, request, _ in windows:
        for parent in parents:
            parents[parent][name] = reading(scorers[parent], request)
    counts: Counter[str] = Counter()
    problems = []
    rows = []
    changed_origins = set()
    changed_seats = set()
    changed_transitions = set()
    states = Counter()
    started = time.perf_counter()
    for name, request, origins in windows:
        stable = parents["stable_v2"][name]
        specialist = parents["specialist"][name]
        got = reading(scorers["router"], request)
        record, record_consistent = router_record(got)
        selected = record.get("selected_parent") if record else None
        rule_state = record.get("rule_state") if record else None
        unknown_fallback = record.get("unknown_fallback") if record else None
        exact_stable = (got["scores"] == stable["scores"]
                        and got["ordered_actions"] == stable["ordered_actions"])
        exact_specialist = (got["scores"] == specialist["scores"]
                            and got["ordered_actions"] == specialist["ordered_actions"])
        exact_selected = ((selected == "stable_v2" and exact_stable)
                          or (selected == "specialist" and exact_specialist))
        changed = got["action_key"] != stable["action_key"]
        v2_before = stable["scores"].get(stable["action_key"])
        v2_after = stable["scores"].get(got["action_key"])
        non_tie_change = changed and v2_before is not None and v2_after is not None \
            and v2_before != v2_after
        counts["windows"] += 1
        counts["selected:" + str(selected)] += 1
        counts["record_inconsistent"] += int(not record_consistent)
        counts["selected_parent_mismatch"] += int(not exact_selected)
        counts["changed_choices"] += int(changed)
        counts["non_tie_changed_choices"] += int(non_tie_change)
        counts["unknown_fallback_windows"] += int(unknown_fallback is True)
        states[str(rule_state)] += 1
        if got["status"] != "SCORED" or got["action_key"] is None:
            problems.append(name + ":router_not_scored")
        if set(got["scores"]) != set(stable["scores"]):
            problems.append(name + ":action_coverage")
        if not record_consistent:
            problems.append(name + ":router_trace_inconsistent")
        if selected not in ("stable_v2", "specialist"):
            problems.append(name + ":selected_parent_unknown")
        if not exact_selected:
            problems.append(name + ":selected_parent_not_exact")
        if unknown_fallback is True and not exact_stable:
            problems.append(name + ":unknown_fallback_not_v2")
        unexpected = [reason for reason in got["degraded_reasons"] if "评分完成" not in reason]
        if unexpected:
            problems.append(name + ":unexpected_plan_reason")
        if changed:
            visible = behavior.build_scoring_view(request).visible_state
            before = str(stable["action_key"]).split(":", 1)[0]
            after = str(got["action_key"]).split(":", 1)[0]
            transition = before + "->" + after
            changed_origins.update(origins)
            changed_seats.add(visible.seat)
            changed_transitions.add(transition)
            rows.append({
                "window_id": name, "origins": origins,
                "seat": visible.seat, "phase": visible.phase,
                "rule_state": rule_state, "selected_parent": selected,
                "unknown_fallback": unknown_fallback,
                "baseline_action": stable["action_key"],
                "candidate_action": got["action_key"],
                "transition": transition, "non_tie_change": non_tie_change,
                "v2_before_score": v2_before, "v2_after_score": v2_after,
                "exact_selected_parent": exact_selected,
                "router_record": record,
            })
    elapsed = time.perf_counter() - started
    mean_ms = 1000.0 * elapsed / len(windows)
    gate_checks = {
        "stable_branch_hit": counts["selected:stable_v2"] > 0,
        "specialist_branch_hit": counts["selected:specialist"] > 0,
        "selected_parent_exact": counts["selected_parent_mismatch"] == 0,
        "trace_consistent": counts["record_inconsistent"] == 0,
        "unknown_fallback_exact_v2": not any("unknown_fallback_not_v2" in item for item in problems),
        "non_tie_behavior_change": counts["non_tie_changed_choices"] > 0,
        "changed_origins": len(changed_origins) >= 2,
        "changed_seats": len(changed_seats) >= 2,
        "changed_transition_families": len(changed_transitions) >= 2,
        "mean_evaluate_ms": mean_ms <= 25.0,
        "no_contract_problems": not problems,
    }
    passed = all(gate_checks.values())
    result = {
        "schema": "r15-public-state-parent-router-preflight-result/1",
        "status": "PASS_R15_ZERO_TABLE_GATE" if passed else "FAIL_R15_ZERO_TABLE_GATE",
        "deduplicated_windows": len(windows),
        "counts": dict(sorted(counts.items())),
        "rule_states": dict(sorted(states.items())),
        "changed_origins": sorted(changed_origins),
        "changed_seats": sorted(changed_seats),
        "changed_transition_families": sorted(changed_transitions),
        "elapsed_seconds": elapsed, "mean_evaluate_ms": mean_ms,
        "gate_checks": gate_checks, "problems": problems,
        "effect_tables": 0, "model_calls": 0,
        "strength_claim": False, "confirmation_eligible": False,
        "next": ("冻结候选并进入全新H/M完整阶段开发门" if passed
                 else "关闭当前父代与规则态路由实例；不消耗桌赛"),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "changed-windows.json"), {"schema": "r15-router-changes/1", "rows": rows})
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
