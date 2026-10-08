"""R14 第一代：在既有真实公开观察面板上验证两个子代的触发、退化和改选范围。"""

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


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r14-robust-offspring-author-01-20260921')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r14-robust-offspring-author-01-20260921/behavior-preflight-02')
SOURCES = {
    "stable-v2": _project_file(_PROJECT_ROOT, HERE / "v2-parent-revalidation-20260920/parent/generation/candidate.py"),
    "R1": _project_file(_PROJECT_ROOT, AUTHOR / "generations/R1/candidate.py"),
    "R2": _project_file(_PROJECT_ROOT, AUTHOR / "generations/R2/normalized-v3/candidate.py"),
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
    """合并十份已消费诊断面板；同一候选视图只保留一次并记录全部来源。"""

    by_name: dict[str, tuple[Any, list[str]]] = {}
    for panel in PANELS:
        _, windows = behavior.load_panel(panel)
        for name, request in windows:
            if name not in by_name:
                by_name[name] = (request, [])
            by_name[name][1].append(str(panel))
    return [(name, request, origins) for name, (request, origins) in sorted(by_name.items())]


def reading(scorer: Any, request: Any) -> dict[str, Any]:
    """同时保留受限评分批和生产排序结果。"""

    view = behavior.build_scoring_view(request)
    batch = scorer.score(view)
    plan = behavior.evaluate_request(scorer, behavior.digest(view.candidate_view()), request)
    return {
        "status": batch.status,
        "scores": {entry.action_key: entry.score for entry in batch.entries},
        "traces": {entry.action_key: dict(entry.trace) for entry in batch.entries},
        "action_key": plan["action_key"],
        "ordered_actions": plan["ordered_actions"],
        "degraded_reasons": plan["degraded_reasons"],
    }


def triggered(candidate_id: str, traces: dict[str, dict[str, Any]]) -> tuple[bool, list[str]]:
    """按候选自带审计 trace 识别机制实际触发动作。"""

    actions = []
    for key, trace in traces.items():
        if candidate_id == "R1":
            record = trace.get("claim_rebase") or {}
        else:
            record = trace.get("discard_tiebreak") or {}
        if record.get("triggered") is True:
            actions.append(key)
    return bool(actions), actions


def main() -> None:
    """执行零桌、零模型的真实观察行为预检。"""

    if OUT.exists():
        raise SystemExit("行为预检目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    windows = load_windows()
    texts = {name: path.read_text(encoding="utf-8") for name, path in SOURCES.items()}
    scorers = {name: ActionValueScorer("r14-preflight-" + name, text)
               for name, text in texts.items()}
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r14-robust-offspring-behavior-preflight/1",
        "sources": {name: {"path": str(path), "sha256": digest(path)}
                    for name, path in SOURCES.items()},
        "panels": [{"path": str(path), "sha256": digest(path)} for path in PANELS],
        "deduplicated_windows": len(windows),
        "effect_tables": 0, "model_calls": 0,
        "selection_eligible": False, "confirmation_eligible": False,
    })
    baseline_rows = {}
    baseline_started = time.perf_counter()
    for name, request, _ in windows:
        baseline_rows[name] = reading(scorers["stable-v2"], request)
    baseline_elapsed = time.perf_counter() - baseline_started
    summaries = []
    all_rows = {}
    for candidate_id in ("R1", "R2"):
        counts: Counter[str] = Counter()
        problems = []
        rows = []
        started = time.perf_counter()
        for name, request, origins in windows:
            base = baseline_rows[name]
            got = reading(scorers[candidate_id], request)
            active, active_actions = triggered(candidate_id, got["traces"])
            same_scores = got["scores"] == base["scores"]
            same_choice = got["action_key"] == base["action_key"]
            counts["windows"] += 1
            counts["triggered_windows"] += int(active)
            counts["changed_choices"] += int(not same_choice)
            counts["fallback_score_mismatches"] += int(not active and not same_scores)
            counts["trigger_without_score_change"] += int(active and same_scores)
            counts["triggered_actions"] += len(active_actions)
            if not same_choice:
                before = str(base["action_key"]).split(":", 1)[0]
                after = str(got["action_key"]).split(":", 1)[0]
                counts["transition:" + before + "->" + after] += 1
            expected_keys = set(base["scores"])
            if got["status"] != "SCORED" or got["action_key"] is None:
                problems.append(name + ":candidate_not_scored")
            if set(got["scores"]) != expected_keys:
                problems.append(name + ":action_coverage")
            if not active and not same_scores:
                problems.append(name + ":fallback_not_exact_v2")
            unexpected_reasons = [reason for reason in got["degraded_reasons"]
                                  if "评分完成" not in reason]
            if unexpected_reasons:
                problems.append(name + ":unexpected_plan_reason")
            if active or not same_choice or not same_scores:
                rows.append({
                    "window_id": name, "origins": origins,
                    "triggered": active, "triggered_actions": active_actions,
                    "same_scores_as_v2": same_scores,
                    "baseline_action": base["action_key"],
                    "candidate_action": got["action_key"],
                    "candidate_trigger_traces": {
                        key: got["traces"][key] for key in active_actions},
                })
        elapsed = time.perf_counter() - started
        if counts["triggered_windows"] == 0:
            problems.append("no_real_trigger")
        if counts["changed_choices"] == 0:
            problems.append("no_real_behavior_change")
        status = "PASS" if not problems else "FAIL"
        summary = {
            "candidate_id": candidate_id, "status": status,
            "counts": dict(sorted(counts.items())), "problems": problems,
            "elapsed_seconds": elapsed,
            "mean_evaluate_ms": 1000.0 * elapsed / len(windows),
            "scope": "既有已消费真实公开观察；验证触发/退化/行为，不是效果或线上时限证据",
        }
        summaries.append(summary)
        all_rows[candidate_id] = rows
        write_json(_project_file(_PROJECT_ROOT, OUT / f"{candidate_id}-rows.json"), {"rows": rows})
    result = {
        "schema": "r14-robust-offspring-behavior-preflight-result/1",
        "status": "PASS" if all(row["status"] == "PASS" for row in summaries) else "FAIL",
        "deduplicated_windows": len(windows),
        "baseline_elapsed_seconds": baseline_elapsed,
        "candidates": summaries,
        "effect_tables": 0, "model_calls": 0,
        "strength_claim": False, "confirmation_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
