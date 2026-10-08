"""真实开发观察面板：复用公开审计 codec、生产投影与受限评分，不重算历史规则。"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/tools'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from hangma_bot.application.audit_codec import decision_request_from_json, decision_request_to_json
from hangma_bot.policy.action_value import batch_to_ranked_candidates
from hangma_bot.policy.action_value_executor import WorkloadExceeded
from hangma_bot.policy.action_value_policy import ActionValuePolicy, build_scoring_view
from hangma_bot.policy.action_value_seeds import ActionValueScorer
from hangma_bot.policy.interface import DecisionBudget
import sitin_execution_profile as execution_profiles


def digest(value: Any) -> str:
    """规范 JSON 摘要；非有限数拒绝，数组保持顺序。"""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def capture_request(request: Any) -> dict[str, Any]:
    """编码合法可见请求并核验公开往返；运行关联键留在面板层，不进入候选输入。"""
    payload = decision_request_to_json(request)
    view = build_scoring_view(request)
    restored = build_scoring_view(decision_request_from_json(payload))
    view_hash = digest(view.candidate_view())
    if digest(restored.candidate_view()) != view_hash:
        raise ValueError("决策请求往返改变了候选可见输入")
    return {"schema": "sitin-real-behavior-window/1", "request": payload,
            "request_sha256": digest(payload), "candidate_view_sha256": view_hash,
            "projection": "build_scoring_view/default-value-limits"}


def load_panel(path: Path) -> tuple[str, list[tuple[str, Any]]]:
    """按冻结清单读取开发窗口；拒绝篡改、重复、越界路径及输入投影漂移。"""
    manifest = json.loads(path.read_text())
    if (manifest.get("schema") != "sitin-real-behavior-panel/1"
            or manifest.get("purpose") != "development_behavior"
            or manifest.get("selection_eligible") is not False):
        raise ValueError("需要明确的开发行为面板，不能用作效果或确认样本")
    entries = manifest.get("windows")
    if not isinstance(entries, list) or not entries:
        raise ValueError("面板缺少窗口")
    windows = []
    seen = set()
    for entry in entries:
        name = entry["candidate_view_sha256"]
        if name in seen:
            raise ValueError("重复观察")
        seen.add(name)
        target = (path.parent / entry["file"]).resolve()
        if not target.is_relative_to(path.parent.resolve()):
            raise ValueError("窗口路径越过面板目录")
        data = json.loads(target.read_text())
        if digest(data) != entry["record_sha256"]:
            raise ValueError("窗口记录摘要不符")
        if (data.get("schema") != "sitin-real-behavior-window/1"
                or data.get("projection") != "build_scoring_view/default-value-limits"):
            raise ValueError("未知窗口或投影版本")
        if digest(data["request"]) != data["request_sha256"]:
            raise ValueError("决策请求摘要不符")
        request = decision_request_from_json(data["request"])
        view = build_scoring_view(request)
        if digest(view.candidate_view()) != name or data["candidate_view_sha256"] != name:
            raise ValueError("候选可见输入发生漂移")
        windows.append((name, request))
    return digest(manifest), windows


def decision_signature(row: dict[str, Any]) -> dict[str, Any]:
    """比较生产计划的动作语义；分数尺度和解释文字不冒充实际行为差异。"""
    return {key: row[key] for key in ("ordered_actions", "emergency_actions", "revision")}


class RecordingScorer:
    """记录生产 choose 实际消费的评分批；每次窗口只执行候选一次。"""

    def __init__(self, scorer: Any) -> None:
        self.scorer = scorer
        self.name = scorer.name
        self.batch = None

    def score(self, view: Any) -> Any:
        """原样返回受限执行结果；失败由生产策略降级，本工具另记不可判定。"""
        self.batch = self.scorer.score(view)
        return self.batch


def evaluate_request(scorer: Any, name: str, request: Any) -> dict[str, Any]:
    """重放正式计划：过滤拒绝、保留紧急候选；预算仅占位，不是时限测试。"""
    recorder = RecordingScorer(scorer)
    plan = asyncio.run(ActionValuePolicy(recorder).choose(request, DecisionBudget(1.0, 2.0, 3.0)))
    batch = recorder.batch
    view = build_scoring_view(request)
    raw_ranked = batch_to_ranked_candidates(batch, view.actions) if batch is not None else ()
    return {"window_id": name, "status": batch.status if batch is not None else "FAILED",
            "action_key": plan.candidates[0].action_key if plan.candidates else None,
            "raw_action_key": raw_ranked[0].action_key if raw_ranked else None,
            "ordered_actions": [item.action_key for item in plan.candidates],
            "emergency_actions": [item.action_key for item in plan.candidates if item.is_emergency],
            "revision": plan.revision, "degraded_reasons": list(plan.degraded_reasons),
            "scores": {item.action_key: item.score for item in batch.entries} if batch else {}}


def evaluate(source: str, panel_path: Path, *, execution_profile: Any = None) -> dict[str, Any]:
    """按生产 choose 重放真实窗口；评分/装载失败保留未知，不能成为等行为证明。"""
    import sitin_gates
    import sitin_deps

    profile = execution_profiles.resolve(execution_profile)
    panel_digest, views = load_panel(panel_path)
    graph = sitin_deps.entry_call_graph(reader=lambda path: path.read_bytes(),
                                       entries=[Path(__file__).name])
    if graph["missing"]:
        raise ValueError("行为面板执行依赖清单不完整")
    execution = {"deps_digest": sitin_gates.av_deps_digest(),
                 "candidate_execution_profile": profile,
                 "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 "entry_dependencies": {name: node["sha256"] for name, node in sorted(graph["nodes"].items())}}
    scorer = None
    load_error = None
    try:
        scorer = ActionValueScorer("real-development-panel", source,
                                  max_operations=profile["max_operations"])
    except (Exception, WorkloadExceeded) as error:
        load_error = type(error).__name__ + ": " + str(error)
    rows = []
    for name, request in views:
        try:
            if load_error is not None:
                raise ValueError(load_error)
            rows.append(evaluate_request(scorer, name, request))
        except (Exception, WorkloadExceeded) as error:
            rows.append({"window_id": name, "status": "FAILED", "action_key": None,
                         "error": type(error).__name__ + ": " + str(error)})
    comparable = all(row["status"] == "SCORED" and row["action_key"] for row in rows)
    return {"schema": "sitin-real-behavior-result/2", "panel_digest": panel_digest,
            "execution_identity": execution,
            "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "comparable": bool(comparable), "windows": rows,
            "behavior_digest": digest({"panel": panel_digest, "execution": execution,
                                        "choices": [(row["window_id"], decision_signature(row))
                                                    for row in rows]}) if comparable else None,
            "scope": "仅限该开发观察清单；不证明全域等价或效果增强"}


def compare(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """只比较同一冻结面板的完整评分；弃权或失败报告不可判定。"""
    if left["panel_digest"] != right["panel_digest"]:
        raise ValueError("不同面板的签名不能比较")
    if not left.get("execution_identity") or left["execution_identity"] != right.get("execution_identity"):
        raise ValueError("执行身份缺失或不同，必须在同一实现下重评")
    left_ids = [row["window_id"] for row in left["windows"]]
    right_ids = [row["window_id"] for row in right["windows"]]
    if not left_ids or left_ids != right_ids or len(left_ids) != len(set(left_ids)):
        raise ValueError("窗口清单为空、重复或未对齐，不能按位置比较")
    if not left["comparable"] or not right["comparable"]:
        return {"verdict": "INDETERMINATE", "changed_windows": None}
    changed = [a["window_id"] for a, b in zip(left["windows"], right["windows"], strict=True)
               if decision_signature(a) != decision_signature(b)]
    return {"verdict": "DIFFERENT" if changed else "SAME_ON_PANEL",
            "changed_windows": changed, "panel_digest": left["panel_digest"],
            "changed_first_choices": [a["window_id"] for a, b in zip(left["windows"], right["windows"], strict=True)
                                      if a["action_key"] != b["action_key"]]}


def main() -> None:
    """只写新结果文件；输入是开发面板和两份候选源码，不执行模拟或调用模型。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    parent = evaluate(args.parent.read_text(), args.panel)
    candidate = evaluate(args.candidate.read_text(), args.panel)
    result = {"parent": parent, "candidate": candidate, "comparison": compare(parent, candidate)}
    with args.out.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(result["comparison"], ensure_ascii=False))


if __name__ == "__main__":
    main()
