"""R18 P3 三财神飘候选的开发、P4 保持与真实窗口预检。"""

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
from collections import Counter
from dataclasses import asdict
import difflib
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_multi_wealth_bank as bank  # noqa: E402
import r18_opportunity_behavior_preflight as real_behavior  # noqa: E402
import r18_p4_shape_bank as p4_bank  # noqa: E402
import r18_wealth_gap_bank as gap_bank  # noqa: E402
from hangma_bot.offline.opportunity_capability import evaluate_pair  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922/generation/candidate.py')
PARENT = gap_bank.PARENT
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922/development-preflight-01')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def policy(path: Path, identity: str) -> ActionValuePolicy:
    return ActionValuePolicy(ActionValueScorer(
        identity, path.read_text(encoding="utf-8")
    ))


async def evaluate_gap() -> tuple[list[Any], list[dict[str, Any]]]:
    cases, metadata = gap_bank.load_development()
    candidate = policy(CANDIDATE, "r18-p3-gap")
    parent = policy(PARENT, "r18-p4-gap-parent")
    rows = [
        await evaluate_pair(candidate, parent, case, bank.budget) for case in cases
    ]
    return rows, metadata


async def evaluate_p4_preservation() -> tuple[list[Any], list[dict[str, Any]]]:
    cases, metadata = p4_bank.load_development()
    candidate = policy(CANDIDATE, "r18-p3-p4-preserve")
    parent = policy(PARENT, "r18-p4-preserve-parent")
    rows = [
        await evaluate_pair(candidate, parent, case, bank.budget) for case in cases
    ]
    return rows, metadata


def summarize_strata(
    rows: list[Any], metadata: list[dict[str, Any]], key: str,
) -> dict[str, dict[str, Any]]:
    result = {}
    values = sorted({meta[key] for meta in metadata})
    for value in values:
        selected = [
            row for row, meta in zip(rows, metadata) if meta[key] == value
        ]
        result[value] = {
            "cases": len(selected),
            "scored": sum(row.capability_gain is not None for row in selected),
            "changed_from_parent": sum(
                row.candidate.chosen_action_key != row.baseline.chosen_action_key
                for row in selected
            ),
            "improved_over_parent": sum(
                row.capability_gain is not None and row.capability_gain > 0
                for row in selected
            ),
            "regressed_from_parent": sum(
                row.capability_gain is not None and row.capability_gain < 0
                for row in selected
            ),
            "candidate_optimal": sum(
                row.candidate.chosen_action_key in row.candidate.optimal_action_keys
                for row in selected
            ),
            "parent_optimal": sum(
                row.baseline.chosen_action_key in row.baseline.optimal_action_keys
                for row in selected
            ),
            "mean_gain_over_parent": (
                sum(float(row.capability_gain) for row in selected if row.capability_gain is not None)
                / max(1, sum(row.capability_gain is not None for row in selected))
            ),
        }
    return result


def overlay_records(reading: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        trace["r18_opportunity_overlay"]
        for trace in reading["traces"].values()
        if isinstance(trace.get("r18_opportunity_overlay"), dict)
    ]


def evaluate_real_windows() -> dict[str, Any]:
    windows = real_behavior.load_windows()
    parent_scorer = ActionValueScorer(
        "r18-p3-real-parent", PARENT.read_text(encoding="utf-8")
    )
    candidate_scorer = ActionValueScorer(
        "r18-p3-real-candidate", CANDIDATE.read_text(encoding="utf-8")
    )
    counts: Counter[str] = Counter()
    problems = []
    changed_rows = []
    started = time.perf_counter()
    for name, request, origins in windows:
        parent = real_behavior.reading(parent_scorer, request)
        candidate = real_behavior.reading(candidate_scorer, request)
        records = overlay_records(candidate)
        p3_triggered = any(
            row.get("structure") == "three_wealth_piao_cf_supported/v1"
            and row.get("triggered") is True
            for row in records
        )
        same_scores = candidate["scores"] == parent["scores"]
        same_choice = candidate["action_key"] == parent["action_key"]
        counts["windows"] += 1
        counts["p3_triggered_windows"] += int(p3_triggered)
        counts["changed_choices"] += int(not same_choice)
        counts["nontrigger_score_mismatches"] += int(not p3_triggered and not same_scores)
        if candidate["status"] != "SCORED" or candidate["action_key"] is None:
            problems.append(name + ":candidate_not_scored")
        if set(candidate["scores"]) != set(parent["scores"]):
            problems.append(name + ":action_coverage")
        if not p3_triggered and not same_scores:
            problems.append(name + ":fallback_not_exact_parent")
        if p3_triggered and sum(
            row.get("structure") == "three_wealth_piao_cf_supported/v1"
            and row.get("triggered") is True
            for row in records
        ) != 1:
            problems.append(name + ":p3_trigger_not_single_action")
        unexpected = [
            reason for reason in candidate["degraded_reasons"] if "评分完成" not in reason
        ]
        if unexpected:
            problems.append(name + ":unexpected_plan_reason")
        if p3_triggered or not same_scores or not same_choice:
            changed_rows.append({
                "window_id": name,
                "origins": origins,
                "p3_triggered": p3_triggered,
                "same_scores_as_parent": same_scores,
                "parent_action": parent["action_key"],
                "candidate_action": candidate["action_key"],
                "overlay_records": records,
            })
    elapsed = time.perf_counter() - started
    return {
        "status": "PASS" if not problems else "FAIL",
        "counts": dict(sorted(counts.items())),
        "problems": problems,
        "elapsed_seconds": elapsed,
        "mean_evaluate_ms": 1000.0 * elapsed / len(windows),
        "changed_rows": changed_rows,
        "scope": "真实公开观察执行与父代回退；不提供机会效果或完整桌强度结论",
    }


def main() -> None:
    if OUT.exists():
        raise SystemExit("R18 P3 开发预检目录已存在；拒绝覆盖")
    if not CANDIDATE.exists():
        raise ValueError("P3 作者源码不存在")
    gap_rows, gap_meta = asyncio.run(evaluate_gap())
    p4_rows, p4_meta = asyncio.run(evaluate_p4_preservation())
    gap = summarize_strata(gap_rows, gap_meta, "opportunity_stratum")
    p4 = summarize_strata(p4_rows, p4_meta, "decision_type")
    real = evaluate_real_windows()
    parent_lines = PARENT.read_text(encoding="utf-8").splitlines()
    candidate_lines = CANDIDATE.read_text(encoding="utf-8").splitlines()
    diff = list(difflib.unified_diff(parent_lines, candidate_lines, lineterm=""))
    checks = {
        "gap_all_scored": all(row["scored"] == row["cases"] for row in gap.values()),
        "three_piao_all_improved": (
            gap["three_wealth_piao"]["improved_over_parent"]
            == gap["three_wealth_piao"]["cases"]
            and gap["three_wealth_piao"]["candidate_optimal"]
            == gap["three_wealth_piao"]["cases"]
        ),
        "keep_strata_unchanged": all(
            gap[name]["changed_from_parent"] == 0
            and gap[name]["regressed_from_parent"] == 0
            for name in ("three_wealth_keep", "four_wealth_keep")
        ),
        "p4_bank_exactly_preserved": all(
            row["changed_from_parent"] == 0
            and row["regressed_from_parent"] == 0
            for row in p4.values()
        ),
        "real_windows_pass": real["status"] == "PASS",
    }
    passed = all(checks.values())
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p3-development-preflight-manifest/1",
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "sources": {
            str(path): digest(path) for path in (
                Path(__file__), CANDIDATE, PARENT,
                gap_bank.OUT / "manifest.json", gap_bank.OUT / "development.json",
                p4_bank.OUT / "manifest.json", p4_bank.OUT / "development.json",
            )
        },
        "hidden_bank_read": False,
        "candidate_frozen_before_hidden": True,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "r18-p3-development-preflight-result/1",
        "status": "PASS_P3_DEVELOPMENT" if passed else "FAIL_P3_DEVELOPMENT",
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "checks": checks,
        "wealth_gap_strata": gap,
        "p4_preservation_strata": p4,
        "real_windows": {key: value for key, value in real.items() if key != "changed_rows"},
        "source_diff_line_count": len(diff),
        "hidden_evaluation_started": False,
        "release_eligible": False,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "real-window-changes.json"), {"rows": real["changed_rows"]})
    (_project_file(_PROJECT_ROOT, OUT / "parent-to-candidate.diff")).write_text("\n".join(diff) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS_P3_DEVELOPMENT" if passed else "FAIL_P3_DEVELOPMENT",
        "checks": checks,
        "wealth_gap_strata": gap,
        "p4_preservation_strata": p4,
        "real_window_counts": real["counts"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
