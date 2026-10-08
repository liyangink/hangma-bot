"""R18 P6 七对门清机械候选的开发预检与精确回退审计。"""

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
from dataclasses import replace
from pathlib import Path
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_seven_pairs_natural_probe as probe  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
from hangma_bot.kernel.serialization import window_key_to_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p6-seven-pairs-01-20260922')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p6-seven-pairs-01-20260922/generation/candidate.py')
PARENT = probe.PARENT
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p6-seven-pairs-01-20260922/development-preflight-02')
PROBE_RESULT = probe.OUT / "result.json"


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """写入稳定 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def key_of(value: Mapping[str, Any]) -> str:
    """把 WindowKey JSON 折成稳定键。"""

    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def selected_sources(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """固定选择 H/M 各四个不同来源根，覆盖首批自然正例。"""

    chosen = []
    roots = {"H": set(), "M": set()}
    source_ids = set()
    for row in result["windows"]:
        source = dict(row["source"])
        mix = str(source["mix"])
        root = str(source["source_root_id"])
        if len(roots[mix]) >= 4 or root in roots[mix]:
            continue
        roots[mix].add(root)
        if source["source_id"] not in source_ids:
            chosen.append(source)
            source_ids.add(source["source_id"])
    if {mix: len(values) for mix, values in roots.items()} != {"H": 4, "M": 4}:
        raise ValueError("开发预检无法取得 H/M 各四个不同来源根")
    return chosen


def requests_for(source: Mapping[str, Any]) -> list[Any]:
    """按冻结自然计划重建一个来源的全部焦点公开请求。"""

    contract = json.loads(probe.CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source["mix"]),
        root_index=int(source["root_index"]),
        focal_seat=int(source["focal_seat"]),
        panel_seed=int(source["panel_seed"]),
    )
    requests: list[Any] = []
    stage = natural.run_arm_stage(
        arm="baseline",
        plans=plans,
        candidate_scorer=ActionValueScorer("r18-p6-preflight-unused", PARENT.read_text(encoding="utf-8")),
        opponent_policies=contract["panel"]["opponent_scenarios"][str(source["mix"])]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=probe.LIMITS,
        decision_observer=requests.append,
    )
    if stage.get("status") != "complete" or len(stage.get("tables") or []) != probe.TABLES_PER_SOURCE:
        raise RuntimeError(stage.get("error") or "开发来源未跑满")
    return requests


def top_key(batch: Any) -> str:
    """按合同排序规则读取首选动作。"""

    return sorted(batch.entries, key=lambda item: (-item.score, item.action_key))[0].action_key


def scores(batch: Any) -> dict[str, float]:
    """返回完整动作评分。"""

    return {item.action_key: item.score for item in batch.entries}


def trigger_keys(batch: Any) -> list[str]:
    """返回 P6 七对覆盖实际触发的动作键。"""

    return [
        item.action_key for item in batch.entries
        if isinstance(item.trace.get("r18_seven_pairs_overlay"), dict)
        and item.trace["r18_seven_pairs_overlay"].get("triggered") is True
    ]


def replace_action(view: Any, target_key: str, **changes: Any) -> Any:
    """只为负控替换一个动作事实。"""

    return replace(view, actions=tuple(
        replace(action, **changes) if action.action_key == target_key else action
        for action in view.actions
    ))


def main() -> None:
    """执行真实正例、全窗回退和逐字段 fail-closed 预检。"""

    if OUT.exists():
        raise SystemExit("P6 开发预检目录已存在；拒绝覆盖")
    result = json.loads(PROBE_RESULT.read_text(encoding="utf-8"))
    if result.get("decision") != "OPEN_MECHANICAL_SEVEN_PAIRS_CANDIDATE":
        raise ValueError("自然证据门未开放 P6 实现")
    expected_by_key = {key_of(row["window_key"]): row for row in result["windows"]}
    parent = ActionValueScorer("r18-p6-preflight-parent", PARENT.read_text(encoding="utf-8"))
    candidate = ActionValueScorer("r18-p6-preflight-candidate", CANDIDATE.read_text(encoding="utf-8"))
    rows = []
    problems = []
    max_operations = 0
    target_request = None
    selected = selected_sources(result)
    for source in selected:
        for request in requests_for(source):
            view = build_scoring_view(request)
            parent_batch = parent.score(view)
            candidate_batch = candidate.score(view)
            max_operations = max(max_operations, candidate.last_operation_count)
            parent_top = top_key(parent_batch)
            candidate_top = top_key(candidate_batch)
            triggers = trigger_keys(candidate_batch)
            expected = expected_by_key.get(key_of(window_key_to_json(request.window_key)))
            if expected is None:
                if triggers:
                    problems.append("unexpected_trigger:" + key_of(window_key_to_json(request.window_key)))
                if scores(candidate_batch) != scores(parent_batch):
                    problems.append("nontrigger_scores_changed:" + key_of(window_key_to_json(request.window_key)))
                if candidate_top != parent_top:
                    problems.append("nontrigger_top_changed:" + key_of(window_key_to_json(request.window_key)))
                continue
            if target_request is None:
                target_request = request
            expected_key = str(expected["dominant_action"])
            if parent_top != expected["parent_action"]:
                problems.append("parent_top_mismatch:" + key_of(expected["window_key"]))
            if candidate_top != expected_key:
                problems.append("candidate_top_mismatch:" + key_of(expected["window_key"]))
            if triggers != [expected_key]:
                problems.append("trigger_mismatch:" + key_of(expected["window_key"]))
            trace = next(
                (item.trace.get("r18_seven_pairs_overlay") for item in candidate_batch.entries if item.action_key == expected_key),
                None,
            )
            if not isinstance(trace, dict) or trace.get("parent_action") != expected["parent_action"]:
                problems.append("trace_parent_mismatch:" + key_of(expected["window_key"]))
            rows.append({
                "window_key": expected["window_key"],
                "mix": source["mix"],
                "source_root_id": source["source_root_id"],
                "parent_action": parent_top,
                "candidate_action": candidate_top,
                "trigger_keys": triggers,
                "candidate_operations": candidate.last_operation_count,
            })
    if target_request is None:
        raise ValueError("开发预检没有重建到正例")
    target_expected = expected_by_key[key_of(window_key_to_json(target_request.window_key))]
    target_key = str(target_expected["dominant_action"])
    target_view = build_scoring_view(target_request)
    target_action = next(item for item in target_view.actions if item.action_key == target_key)
    mutations = {
        "seven_useful_unknown": replace_action(target_view, target_key, seven_pairs_useful_tiles=None),
        "standard_useful_unknown": replace_action(target_view, target_key, standard_useful_tiles=None),
        "pattern_note_present": replace_action(target_view, target_key, pattern_progress_note="forced unknown"),
        "standard_shanten_unknown": replace_action(
            target_view, target_key, standard_shanten_after=None,
        ),
    }
    mutation_rows = []
    for name, view in mutations.items():
        parent_batch = parent.score(view)
        candidate_batch = candidate.score(view)
        max_operations = max(max_operations, candidate.last_operation_count)
        same_scores = scores(candidate_batch) == scores(parent_batch)
        same_top = top_key(candidate_batch) == top_key(parent_batch)
        triggers = trigger_keys(candidate_batch)
        if triggers:
            problems.append(name + ":unexpected_trigger")
        if not same_scores:
            problems.append(name + ":fallback_scores_changed")
        if not same_top:
            problems.append(name + ":fallback_top_changed")
        mutation_rows.append({
            "mutation": name,
            "trigger_keys": triggers,
            "same_scores_as_p5": same_scores,
            "same_top_as_p5": same_top,
            "candidate_operations": candidate.last_operation_count,
        })
    checks = {
        "natural_positives_at_least_8": len(rows) >= 8,
        "natural_roots_at_least_8": len({row["source_root_id"] for row in rows}) >= 8,
        "both_mixes_present": {row["mix"] for row in rows} == {"H", "M"},
        "all_positive_choices_match": all(
            row["candidate_action"] == row["trigger_keys"][0]
            for row in rows if row["trigger_keys"]
        ) and all(len(row["trigger_keys"]) == 1 for row in rows),
        "fail_closed_mutations_exact_p5": all(
            row["same_scores_as_p5"] and row["same_top_as_p5"] and not row["trigger_keys"]
            for row in mutation_rows
        ),
        "problems_zero": not problems,
        "operations_within_default_limit": max_operations <= 100_000,
    }
    document = {
        "schema": "r18-p6-development-preflight/1",
        "status": "PASS_P6_DEVELOPMENT" if all(checks.values()) else "FAIL_P6_DEVELOPMENT",
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "probe_result_sha256": digest(PROBE_RESULT),
        "selected_sources": selected,
        "positive_rows": rows,
        "mutation_rows": mutation_rows,
        "max_candidate_operations": max_operations,
        "checks": checks,
        "problems": problems,
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), document)
    print(json.dumps({
        "status": document["status"],
        "positive_windows": len(rows),
        "distinct_roots": len({row["source_root_id"] for row in rows}),
        "max_candidate_operations": max_operations,
        "checks": checks,
        "problems": problems,
    }, ensure_ascii=False, indent=2))
    if not all(checks.values()):
        raise RuntimeError("P6 开发预检未通过")


if __name__ == "__main__":
    main()
