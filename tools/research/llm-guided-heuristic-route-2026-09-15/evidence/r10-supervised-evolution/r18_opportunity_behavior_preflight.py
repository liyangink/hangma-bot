"""R18 机会专长在既有真实公开窗口上的 V2 精确退化预检。"""

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


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-opportunity-author-01-20260922/behavior-preflight-01')
SOURCES = {
    "stable-v2": _project_file(_PROJECT_ROOT, HERE / "v2-parent-revalidation-20260920/parent/generation/candidate.py"),
    "K3": _project_file(_PROJECT_ROOT, AUTHOR / "generations/K3/normalized-v2/candidate.py"),
    "P4": _project_file(_PROJECT_ROOT, AUTHOR / "generations/P4/normalized-v2/candidate.py"),
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
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def load_windows() -> list[tuple[str, Any, list[str]]]:
    by_name: dict[str, tuple[Any, list[str]]] = {}
    for panel in PANELS:
        _, windows = behavior.load_panel(panel)
        for name, request in windows:
            if name not in by_name:
                by_name[name] = (request, [])
            by_name[name][1].append(str(panel))
    return [
        (name, request, origins)
        for name, (request, origins) in sorted(by_name.items())
    ]


def reading(scorer: Any, request: Any) -> dict[str, Any]:
    view = behavior.build_scoring_view(request)
    batch = scorer.score(view)
    plan = behavior.evaluate_request(
        scorer, behavior.digest(view.candidate_view()), request
    )
    return {
        "status": batch.status,
        "scores": {entry.action_key: entry.score for entry in batch.entries},
        "traces": {entry.action_key: dict(entry.trace) for entry in batch.entries},
        "action_key": plan["action_key"],
        "ordered_actions": plan["ordered_actions"],
        "degraded_reasons": plan["degraded_reasons"],
    }


def triggered(traces: dict[str, dict[str, Any]]) -> tuple[bool, list[str]]:
    actions = []
    for key, trace in traces.items():
        record = trace.get("r18_opportunity_overlay") or {}
        if record.get("triggered") is True:
            actions.append(key)
    return bool(actions), actions


def main() -> None:
    if OUT.exists():
        raise SystemExit("R18 行为预检目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    windows = load_windows()
    texts = {name: path.read_text(encoding="utf-8") for name, path in SOURCES.items()}
    scorers = {
        name: ActionValueScorer("r18-real-preflight-" + name, text)
        for name, text in texts.items()
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-opportunity-behavior-preflight/1",
        "sources": {
            name: {"path": str(path), "sha256": digest(path)}
            for name, path in SOURCES.items()
        },
        "panels": [
            {"path": str(path), "sha256": digest(path)} for path in PANELS
        ],
        "deduplicated_windows": len(windows),
        "effect_tables": 0,
        "model_calls": 0,
        "purpose": "只检验正式公开观察上的执行完整性和非触发精确退化",
    })
    baseline_rows = {}
    started = time.perf_counter()
    for name, request, _ in windows:
        baseline_rows[name] = reading(scorers["stable-v2"], request)
    baseline_elapsed = time.perf_counter() - started
    summaries = []
    for candidate_id in ("K3", "P4"):
        counts: Counter[str] = Counter()
        problems = []
        rows = []
        started = time.perf_counter()
        for name, request, origins in windows:
            base = baseline_rows[name]
            got = reading(scorers[candidate_id], request)
            active, active_actions = triggered(got["traces"])
            same_scores = got["scores"] == base["scores"]
            same_choice = got["action_key"] == base["action_key"]
            counts["windows"] += 1
            counts["triggered_windows"] += int(active)
            counts["changed_choices"] += int(not same_choice)
            counts["fallback_score_mismatches"] += int(not active and not same_scores)
            counts["trigger_without_score_change"] += int(active and same_scores)
            counts["triggered_actions"] += len(active_actions)
            expected_keys = set(base["scores"])
            if got["status"] != "SCORED" or got["action_key"] is None:
                problems.append(name + ":candidate_not_scored")
            if set(got["scores"]) != expected_keys:
                problems.append(name + ":action_coverage")
            if not active and not same_scores:
                problems.append(name + ":fallback_not_exact_v2")
            if active and len(active_actions) != 1:
                problems.append(name + ":trigger_not_single_action")
            unexpected = [
                reason for reason in got["degraded_reasons"]
                if "评分完成" not in reason
            ]
            if unexpected:
                problems.append(name + ":unexpected_plan_reason")
            if active or not same_choice or not same_scores:
                rows.append({
                    "window_id": name,
                    "origins": origins,
                    "triggered": active,
                    "triggered_actions": active_actions,
                    "same_scores_as_v2": same_scores,
                    "baseline_action": base["action_key"],
                    "candidate_action": got["action_key"],
                    "trigger_traces": {
                        key: got["traces"][key] for key in active_actions
                    },
                })
        elapsed = time.perf_counter() - started
        summary = {
            "candidate_id": candidate_id,
            "status": "PASS" if not problems else "FAIL",
            "counts": dict(sorted(counts.items())),
            "problems": problems,
            "elapsed_seconds": elapsed,
            "mean_evaluate_ms": 1000.0 * elapsed / len(windows),
            "no_trigger_is_coverage_fact_not_failure": True,
            "scope": (
                "已消费真实公开观察；验证执行与V2退化，不是机会效果、"
                "完整桌赛强度或线上时限证据"
            ),
        }
        summaries.append(summary)
        write_json(_project_file(_PROJECT_ROOT, OUT / f"{candidate_id}-rows.json"), {"rows": rows})
    result = {
        "schema": "r18-opportunity-behavior-preflight-result/1",
        "status": (
            "PASS" if all(row["status"] == "PASS" for row in summaries) else "FAIL"
        ),
        "deduplicated_windows": len(windows),
        "baseline_elapsed_seconds": baseline_elapsed,
        "candidates": summaries,
        "effect_tables": 0,
        "model_calls": 0,
        "strength_claim": False,
        "hidden_evaluation_started": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
