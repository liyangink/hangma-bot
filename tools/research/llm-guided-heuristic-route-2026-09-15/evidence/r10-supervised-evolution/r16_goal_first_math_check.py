"""独立复算 R16/B 真实改选的条件名次、边界差与单路线相容性。"""

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
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (HERE, _project_file(_PROJECT_ROOT, ROUTE / "tools")):
    sys.path.insert(0, str(path))

import r16_goal_first_preflight_02 as preflight  # noqa: E402


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921')
CHANGES = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921/behavior-preflight-02/B-changed-windows.json')
PREFLIGHT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921/behavior-preflight-02/result.json')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921/B/candidate.py')
OUTPUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r16-goal-first-author-01-20260921/math-check.json')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rank_interval(values: tuple[int, int, int, int], seat: int) -> tuple[int, int]:
    """独立枚举：严格高于者决定最好名次，同分者决定最差名次。"""

    own = values[seat]
    higher = sum(1 for index, value in enumerate(values)
                 if index != seat and value > own)
    tied = sum(1 for index, value in enumerate(values)
               if index != seat and value == own)
    return 1 + higher, 1 + higher + tied


def boundary_margin(values: tuple[int, int, int, int], seat: int) -> int:
    """本人积分减去条件排序第二位积分；正/零/负对应前二内/边界/外。"""

    return values[seat] - sorted(values, reverse=True)[1]


def relation(interval: tuple[int, int]) -> str:
    if interval[1] <= 2:
        return "inside"
    if interval[0] <= 2:
        return "boundary"
    return "outside"


def expected_priority(before: str, after: str,
                      before_margin: int, after_margin: int) -> str:
    """按冻结机制规格独立列举目标类别，不调用候选函数。"""

    if after == "inside":
        if before == "outside":
            return "cross_top_two"
        if before == "boundary":
            return "resolve_top_two"
        return "preserve_top_two"
    if after == "boundary":
        if before == "outside":
            return "approach_top_two"
        if before == "inside":
            return "weaken_to_boundary"
        return "hold_boundary"
    if before == "inside":
        return "retreat_from_top_two"
    if before == "boundary":
        return "leave_boundary"
    if after_margin > before_margin:
        return "improve_outside_margin"
    return "outside_no_cross"


def compatible_route(action: Any, trace: dict[str, Any]) -> bool:
    """见证必须是一条完整规则路线；禁止从多路线拼字段。"""

    delta = tuple(trace["conditional_score_delta"])
    followup = trace["selected_route_followup_discard"]
    matches = [route for route in action.routes
               if tuple(route.conditional_settlement.score_delta) == delta
               and route.followup_discard == followup]
    if not matches:
        return False
    branch_key = trace["selected_followup_key"]
    if action.action_type in ("chi", "peng"):
        return branch_key is not None and any(
            branch.followup_key == branch_key
            and branch.followup_discard == followup
            for branch in (action.followup_branches or ()))
    return branch_key is None and followup is None


def main() -> None:
    if OUTPUT.exists():
        raise SystemExit("R16数学复核证据已存在；拒绝覆盖")
    result = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    b_result = next(item for item in result["candidates"] if item["candidate_id"] == "B")
    if b_result["status"] != "PASS_R16_ZERO_TABLE_GATE":
        raise RuntimeError("候选B未通过冻结零桌门")
    windows = {name: preflight.behavior.build_scoring_view(request)
               for name, request, _ in preflight.load_windows()}
    changes = json.loads(CHANGES.read_text(encoding="utf-8"))["rows"]
    rows = []
    for change in changes:
        view = windows[change["window_id"]]
        seat = int(view.visible_state.seat)
        current = tuple(int(value) for value in view.competition.current_stage_scores)
        completed = tuple(int(value) for value in view.competition.stage_scores)
        live = tuple(int(value) for value in view.competition.table_scores)
        trace = change["candidate_action_goal_trace"]
        delta = tuple(int(value) for value in trace["conditional_score_delta"])
        after = tuple(current[index] + delta[index] for index in range(4))
        before_rank = rank_interval(current, seat)
        after_rank = rank_interval(after, seat)
        before_margin = boundary_margin(current, seat)
        after_margin = boundary_margin(after, seat)
        action = next(item for item in view.actions
                      if item.action_key == change["candidate_action"])
        checks = {
            "current_stage_composition": current == tuple(
                completed[index] + live[index] for index in range(4)),
            "zero_sum_settlement": sum(delta) == 0,
            "rank_low": trace["conditional_rank_low"] == after_rank[0],
            "rank_high": trace["conditional_rank_high"] == after_rank[1],
            "boundary_margin_before": trace["boundary_margin_before"] == before_margin,
            "boundary_margin_after": trace["boundary_margin_after"] == after_margin,
            "target_priority": trace["target_priority"] == expected_priority(
                relation(before_rank), relation(after_rank), before_margin, after_margin),
            "single_compatible_route": compatible_route(action, trace),
        }
        rows.append({
            "window_id": change["window_id"], "seat": seat,
            "action_key": change["candidate_action"],
            "current_stage_scores": current, "conditional_score_delta": delta,
            "conditional_scores": after, "before_rank_interval": before_rank,
            "after_rank_interval": after_rank,
            "before_margin": before_margin, "after_margin": after_margin,
            "checks": checks, "passed": all(checks.values()),
        })
    evidence = {
        "schema": "r16-goal-first-independent-math-check/1",
        "status": "PASS" if rows and all(row["passed"] for row in rows) else "FAIL",
        "candidate_sha256": digest(CANDIDATE),
        "preflight_sha256": digest(PREFLIGHT),
        "changes_sha256": digest(CHANGES),
        "changed_windows_checked": len(rows),
        "action_related_changes": sum(
            bool(row["action_related_target_change"]) for row in changes),
        "rows": rows,
        "scope": "独立复算真实公开窗口的条件账、名次区间、前二边界和单路线相容性；不复用候选数学，不是强度样本",
        "tables_run": 0, "strength_claim": False, "release_eligible": False,
    }
    OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"status": evidence["status"],
                      "changed_windows_checked": len(rows)}, ensure_ascii=False))
    if evidence["status"] != "PASS":
        raise RuntimeError("R16/B 条件目标数学复核失败")


if __name__ == "__main__":
    main()
