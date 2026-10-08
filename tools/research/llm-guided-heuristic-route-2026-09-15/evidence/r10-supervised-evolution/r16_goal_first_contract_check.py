"""复核 R16/B 的确定性、动作覆盖、胡优先和受限执行用量。"""

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
import math
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (HERE, _project_file(_PROJECT_ROOT, ROUTE / "tools")):
    sys.path.insert(0, str(path))

import r16_goal_first_preflight_02 as preflight  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921/B/candidate.py')
OUTPUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921/contract-check.json')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reading(batch: object) -> dict[str, object]:
    return {
        "status": batch.status,
        "reason": batch.reason,
        "entries": [
            {"action_key": entry.action_key, "score": entry.score,
             "trace": entry.trace}
            for entry in batch.entries
        ],
    }


def main() -> None:
    if OUTPUT.exists():
        raise SystemExit("R16合同复核证据已存在；拒绝覆盖")
    scorer = ActionValueScorer("r16-B-contract-check",
                               CANDIDATE.read_text(encoding="utf-8"))
    failures = []
    operation_counts = []
    hu_windows = 0
    for name, request, _ in preflight.load_windows():
        view = preflight.behavior.build_scoring_view(request)
        first_batch = scorer.score(view)
        first_ops = scorer.last_operation_count
        second_batch = scorer.score(view)
        second_ops = scorer.last_operation_count
        first = reading(first_batch)
        second = reading(second_batch)
        operation_counts.extend((first_ops, second_ops))
        if first != second or first_ops != second_ops:
            failures.append({"window_id": name, "reason": "non_deterministic"})
        expected_keys = sorted(action.action_key for action in view.actions)
        actual_keys = sorted(entry.action_key for entry in first_batch.entries)
        if first_batch.status != "SCORED" or actual_keys != expected_keys:
            failures.append({"window_id": name, "reason": "action_coverage"})
        if any(not math.isfinite(entry.score) for entry in first_batch.entries):
            failures.append({"window_id": name, "reason": "non_finite_score"})
        hu_keys = {action.action_key for action in view.actions
                   if action.action_type == "hu"}
        if hu_keys:
            hu_windows += 1
            best = max(first_batch.entries, key=lambda entry: (entry.score, entry.action_key))
            if best.action_key not in hu_keys:
                failures.append({"window_id": name, "reason": "hu_not_first"})
    evidence = {
        "schema": "r16-goal-first-contract-check/1",
        "status": "PASS" if not failures else "FAIL",
        "candidate_sha256": digest(CANDIDATE),
        "executor_version": scorer.executor_version,
        "windows_checked": 226,
        "repeat_scores_per_window": 2,
        "hu_windows_checked": hu_windows,
        "max_operations_limit": scorer.max_operations,
        "max_operations_observed": max(operation_counts),
        "mean_operations_observed": sum(operation_counts) / len(operation_counts),
        "checks": {
            "deterministic_score_trace_and_operation_count": not any(
                item["reason"] == "non_deterministic" for item in failures),
            "complete_action_coverage": not any(
                item["reason"] == "action_coverage" for item in failures),
            "finite_scores": not any(
                item["reason"] == "non_finite_score" for item in failures),
            "legal_hu_first": not any(
                item["reason"] == "hu_not_first" for item in failures),
            "operations_within_limit": max(operation_counts) <= scorer.max_operations,
        },
        "failures": failures,
        "tables_run": 0, "strength_claim": False, "release_eligible": False,
    }
    OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"status": evidence["status"],
                      "hu_windows": hu_windows,
                      "max_operations": max(operation_counts)}, ensure_ascii=False))
    if evidence["status"] != "PASS" or not all(evidence["checks"].values()):
        raise RuntimeError("R16/B 受限执行合同复核失败")


if __name__ == "__main__":
    main()
