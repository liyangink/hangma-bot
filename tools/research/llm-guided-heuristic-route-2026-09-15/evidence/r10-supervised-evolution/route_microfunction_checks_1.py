"""R10 条件路线微函数第一批：变形金例与真实视图差异诊断。"""
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

import copy
import dataclasses
import hashlib
import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE, _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run")):
    sys.path.insert(0, str(path))

import structural_behavior_preflight as preflight  # noqa: E402
from hangma_bot.policy.action_value import batch_to_ranked_candidates  # noqa: E402
from hangma_bot.policy.action_value_executor import ActionValueExecutor  # noqa: E402


BATCH = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-01-20260921')
BEHAVIOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/route-microfunction-01-20260921/behavior-preflight-v2')
V2 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/v2-parent-revalidation-20260920/parent/generation/candidate.py')


def digest(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def reading(executor: ActionValueExecutor, view) -> dict:
    batch = executor.score(view)
    ranked = batch_to_ranked_candidates(batch, view.actions)
    return {
        "status": batch.status,
        "preferred": ranked[0].action_key if ranked else None,
        "scores": {entry.action_key: entry.score for entry in batch.entries},
        "trace": {entry.action_key: entry.trace for entry in batch.entries},
    }


def partition_check(source_path: Path, views: list) -> dict:
    """在当前依赖下重建12个等价拆分/重排输入，避免复用旧核心面板身份。"""
    selected = []
    for view_index, view in enumerate(views):
        plain = view.candidate_view()
        choices = []
        for action in plain["actions"]:
            for route_index, route in enumerate(action.get("routes") or ()):
                size = len(route.get("useful_tiles") or ())
                if size >= 2:
                    choices.append((-size, action["action_key"], route_index))
        if choices:
            _, key, route_index = min(choices)
            selected.append((view_index, view, key, route_index))
        if len(selected) == 12:
            break
    if len(selected) != 12:
        raise ValueError("当前真实视图不足12个可拆分条件路线")
    executor = ActionValueExecutor(source_path.read_text(encoding="utf-8"),
                                   name="partition-" + source_path.parent.name)
    passed = 0
    rows = []
    for view_index, view, key, route_index in selected:
        plain = view.candidate_view()
        projected = {action["action_key"]: action for action in plain["actions"]}
        cases = {"original": view}
        for mode in ("split_identical_condition", "reverse_route_order"):
            actions = []
            for action in view.actions:
                routes = copy.deepcopy(list(projected[action.action_key].get("routes") or ()))
                if mode == "reverse_route_order":
                    routes.reverse()
                elif action.action_key == key:
                    route = routes[route_index]
                    first = copy.deepcopy(route)
                    rest = copy.deepcopy(route)
                    first["useful_tiles"] = route["useful_tiles"][:1]
                    rest["useful_tiles"] = route["useful_tiles"][1:]
                    routes[route_index:route_index + 1] = [first, rest]
                actions.append(dataclasses.replace(action, routes=tuple(routes)))
            cases[mode] = dataclasses.replace(view, actions=tuple(actions))
        results = {}
        for mode, case in cases.items():
            row = reading(executor, case)
            results[mode] = {"status": row["status"], "scores": row["scores"]}
        invariant = all(
            row["status"] == results["original"]["status"]
            and row["scores"] == results["original"]["scores"]
            for row in results.values()
        )
        passed += int(invariant)
        rows.append({"view_index": view_index, "action_key": key, "invariant": invariant})
    return {"cases": len(rows), "invariant": passed, "rows": rows}


def main() -> None:
    output = _project_file(_PROJECT_ROOT, BATCH / "microfunction-checks.json")
    if output.exists():
        raise SystemExit("微函数检查结果已存在；拒绝覆盖")
    summary = json.loads((_project_file(_PROJECT_ROOT, BEHAVIOR / "summary.json")).read_text(encoding="utf-8"))
    if set(summary.get("passed_tasks") or []) != {"M1", "M2"}:
        raise ValueError("行为预检未同时通过M1/M2")
    views, corpus = preflight.load_real_views()
    base = ActionValueExecutor(V2.read_text(encoding="utf-8"), name="stable-v2")
    base_rows = [reading(base, view) for view in views]
    configs = []
    changed_windows = []
    for task in summary["tasks"]:
        for row in task["configurations"]:
            source_path = _project_file(_PROJECT_ROOT, BEHAVIOR / "configurations" / row["config_id"] / "candidate.py")
            invariance = partition_check(source_path, views)
            if invariance["cases"] != 12 or invariance["invariant"] != 12:
                raise ValueError(row["config_id"] + " 路线拆分/重排变形检查失败")
            executor = ActionValueExecutor(source_path.read_text(encoding="utf-8"),
                                           name=row["config_id"])
            current = [reading(executor, view) for view in views]
            local_changes = []
            for index, (candidate, reference) in enumerate(zip(current, base_rows)):
                if (candidate["status"] != reference["status"]
                        or candidate["preferred"] != reference["preferred"]):
                    key = candidate["preferred"]
                    base_key = reference["preferred"]
                    local_changes.append({
                        "view_index": index,
                        "candidate_view_sha256": digest(views[index].candidate_view()),
                        "phase": views[index].visible_state.phase,
                        "base_preferred": base_key,
                        "candidate_preferred": key,
                        "base_preferred_score": reference["scores"].get(base_key),
                        "candidate_preferred_score": candidate["scores"].get(key),
                        "candidate_route_delta": (
                            (candidate["trace"].get(key) or {}).get("route_delta")
                        ),
                        "base_score_for_candidate_choice": reference["scores"].get(key),
                    })
            changed_windows.extend({"config_id": row["config_id"], **item}
                                   for item in local_changes)
            configs.append({
                "task": task["task"],
                "config_id": row["config_id"],
                "values": row["values"],
                "source_sha256": row["source_sha256"],
                "is_zero_effect": row["is_zero_effect"],
                "changed_preferred_vs_v2": len(local_changes),
                "preference_signature": row["preference_signature"],
                "score_signature": row["score_signature"],
                "partition_and_order_cases": invariance["cases"],
                "partition_and_order_passed": invariance["invariant"],
            })
    result = {
        "schema": "r10-route-microfunction-checks/1",
        "corpus": corpus,
        "configurations": configs,
        "changed_windows": changed_windows,
        "all_partition_and_order_checks_passed": all(
            row["partition_and_order_passed"] == row["partition_and_order_cases"]
            for row in configs
        ),
        "zero_effect_configs": [row["config_id"] for row in configs if row["is_zero_effect"]],
        "effect_tables": 0,
        "selection_eligible": False,
        "limits": (
            "变形检查只证明等价拆分/重排不改变评分；冻结真实视图只证明接线与行为差异，"
            "都不提供动作正确标签或桌赛效果。"
        ),
    }
    write_json(output, result)
    print(json.dumps({
        "status": "COMPLETE",
        "configs": len(configs),
        "partition_cases": sum(row["partition_and_order_cases"] for row in configs),
        "partition_passed": sum(row["partition_and_order_passed"] for row in configs),
        "changed_window_rows": len(changed_windows),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
