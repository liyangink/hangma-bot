"""R18 P5 补杠严格支配候选的开发与精确回退预检。"""

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
from pathlib import Path
import sys
import time
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import r18_gang_chain_future_order as prior  # noqa: E402
import r18_gang_dominance_audit as dominance  # noqa: E402
import r18_gang_dominance_confirmation_extension2 as confirmation  # noqa: E402
import r18_opportunity_behavior_preflight as real_behavior  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.observation import CompetitionContext  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.interface import DecisionRequest  # noqa: E402


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-gang-dominance-01-20260922')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-gang-dominance-01-20260922/generation/candidate.py')
PARENT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922/generation/candidate.py')
OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-gang-dominance-01-20260922/development-preflight-02')
CONFIRMATION = confirmation.OUT / "result.json"


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


def scorer(path: Path, name: str) -> ActionValueScorer:
    """以线上默认工作量上限装载候选。"""

    return ActionValueScorer(name, path.read_text(encoding="utf-8"))


def exact_request(target: dict[str, Any]) -> DecisionRequest:
    """从已冻结发现快照重建精确自然决策请求；不读取隐藏墙给候选。"""

    snapshot = json.loads(prior.snapshot_path(target).read_text(encoding="utf-8"))
    contract = json.loads(prior.CONTRACT.read_text(encoding="utf-8"))
    rules = HangmaRules(prior.core.rule_config_from_contract(contract))
    runtime = prior.opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
        seed=int(snapshot["match_spec"]["seed"]),
        scenario_id=str(snapshot["match_spec"]["scenario_id"]),
    )
    engine, world = prior.opportunities.rebuild_world(
        rules=rules, snapshot=snapshot, value_limits=prior.LIMITS, runtime=runtime
    )
    decision = next(
        item for item in engine.frame(world).decisions
        if item.window_key == prior.window_key_from_json(target["window_key"])
    )
    return DecisionRequest(
        observation=decision.observation,
        competition=CompetitionContext(
            tournament_id="r18-p5-development",
            stage_no=None,
            stage_role=None,
            stage_total=None,
            participant_rank=None,
            ranking=(),
            observed_at_unix_ms=0,
        ),
        rules=rules.analyze(decision.observation, value_limits=prior.LIMITS),
        decision_id=str(target["target_id"]),
        trigger_seq=decision.window_key.trigger_seq,
        window_key=decision.window_key,
        rejected_attempts=(),
    )


def top_key(batch: Any) -> str:
    """按合同的分数降序、动作键升序规则取首选。"""

    return sorted(batch.entries, key=lambda item: (-item.score, item.action_key))[0].action_key


def score_map(batch: Any) -> dict[str, float]:
    """把完整动作评分折为动作键映射。"""

    return {item.action_key: item.score for item in batch.entries}


def trigger_keys(batch: Any) -> list[str]:
    """返回带有 P5 严格支配触发记录的动作键。"""

    return [
        item.action_key for item in batch.entries
        if isinstance(item.trace.get("r18_gang_dominance_overlay"), dict)
        and item.trace["r18_gang_dominance_overlay"].get("triggered") is True
    ]


def replace_action(view: Any, target_key: str, **changes: Any) -> Any:
    """只为开发负控替换一个动作事实；动作集合与合法身份保持不变。"""

    actions = tuple(
        replace(item, **changes) if item.action_key == target_key else item
        for item in view.actions
    )
    return replace(view, actions=actions)


def evaluate_discovery() -> tuple[list[dict[str, Any]], list[str], int]:
    """四个发现正例必须触发；三个非目标杠状态必须逐点评分保持 P3。"""

    parent = scorer(PARENT, "r18-p5-development-parent")
    candidate = scorer(CANDIDATE, "r18-p5-development-candidate")
    expected_gain = {
        row["target_id"]: row["local_gain"]
        for row in json.loads(
            (dominance.OUT / "result.json").read_text(encoding="utf-8")
        )["states"]
    }
    rows = []
    problems = []
    max_operations = 0
    for target in prior.targets():
        request = exact_request(target)
        parent_reading = real_behavior.reading(parent, request)
        candidate_reading = real_behavior.reading(candidate, request)
        max_operations = max(max_operations, candidate.last_operation_count)
        triggers = [
            key for key, trace in candidate_reading["traces"].items()
            if isinstance(trace.get("r18_gang_dominance_overlay"), dict)
            and trace["r18_gang_dominance_overlay"].get("triggered") is True
        ]
        positive = target["stratum"] == "proxy_promotes_gang"
        if positive:
            if parent_reading["action_key"] != "hu":
                problems.append(target["target_id"] + ":parent_not_hu")
            if candidate_reading["action_key"] != target["intervention_action"]:
                problems.append(target["target_id"] + ":candidate_not_added_gang")
            if triggers != [target["intervention_action"]]:
                problems.append(target["target_id"] + ":trigger_not_exactly_once")
            if triggers:
                trace = candidate_reading["traces"][triggers[0]]["r18_gang_dominance_overlay"]
                if trace.get("local_gain") != expected_gain[target["target_id"]]:
                    problems.append(target["target_id"] + ":local_gain_mismatch")
                checks = trace.get("checks") or {}
                if not checks or any(value is not True for value in checks.values()):
                    problems.append(target["target_id"] + ":predicate_check_false")
        else:
            if candidate_reading["scores"] != parent_reading["scores"]:
                problems.append(target["target_id"] + ":nontrigger_scores_changed")
            if candidate_reading["action_key"] != parent_reading["action_key"]:
                problems.append(target["target_id"] + ":nontrigger_choice_changed")
            if triggers:
                problems.append(target["target_id"] + ":unexpected_trigger")
        if set(candidate_reading["scores"]) != set(parent_reading["scores"]):
            problems.append(target["target_id"] + ":action_coverage")
        rows.append({
            "target_id": target["target_id"],
            "positive": positive,
            "parent_action": parent_reading["action_key"],
            "candidate_action": candidate_reading["action_key"],
            "trigger_keys": triggers,
            "candidate_operations": candidate.last_operation_count,
        })
    return rows, problems, max_operations


def evaluate_fail_closed_mutations() -> tuple[list[dict[str, Any]], list[str], int]:
    """逐项破坏正例公开事实；P5 必须停止触发并与 P3 逐点评分相同。"""

    target = dominance.positive_targets()[0]
    request = exact_request(target)
    view = build_scoring_view(request)
    action_key = str(target["intervention_action"])
    gang = next(item for item in view.actions if item.action_key == action_key)
    mutations = {
        "coverage_unavailable": replace_action(
            view, action_key,
            value_coverage="unavailable",
            value_issues=({"area": "development", "reason": "forced unknown"},),
        ),
        "value_issue_present": replace_action(
            view, action_key,
            value_issues=({"area": "development", "reason": "forced issue"},),
        ),
        "replacement_known_false": replace_action(
            view, action_key, replacement_draw_unknown=False,
        ),
        "standard_shanten_one": replace_action(
            view, action_key, standard_shanten_after=1,
        ),
        "missing_standard_code": replace_action(
            view, action_key,
            standard_useful_tiles=gang.standard_useful_tiles[:-1],
        ),
        "route_missing": replace_action(view, action_key, routes=()),
    }
    parent = scorer(PARENT, "r18-p5-mutation-parent")
    candidate = scorer(CANDIDATE, "r18-p5-mutation-candidate")
    rows = []
    problems = []
    max_operations = 0
    for name, mutated in mutations.items():
        parent_batch = parent.score(mutated)
        candidate_batch = candidate.score(mutated)
        max_operations = max(max_operations, candidate.last_operation_count)
        triggers = trigger_keys(candidate_batch)
        same_scores = score_map(candidate_batch) == score_map(parent_batch)
        same_top = top_key(candidate_batch) == top_key(parent_batch)
        if triggers:
            problems.append(name + ":unexpected_trigger")
        if not same_scores:
            problems.append(name + ":fallback_scores_changed")
        if not same_top:
            problems.append(name + ":fallback_top_changed")
        rows.append({
            "mutation": name,
            "triggers": triggers,
            "same_scores_as_p3": same_scores,
            "same_top_as_p3": same_top,
            "candidate_operations": candidate.last_operation_count,
        })
    return rows, problems, max_operations


def evaluate_real_windows() -> tuple[dict[str, Any], list[str], int]:
    """既有真实公开窗口上，未命中严格判据时必须逐点评分保持 P3。"""

    parent = scorer(PARENT, "r18-p5-real-parent")
    candidate = scorer(CANDIDATE, "r18-p5-real-candidate")
    windows = real_behavior.load_windows()
    problems = []
    changed = []
    triggered = []
    max_operations = 0
    started = time.perf_counter()
    for name, request, origins in windows:
        parent_reading = real_behavior.reading(parent, request)
        candidate_reading = real_behavior.reading(candidate, request)
        max_operations = max(max_operations, candidate.last_operation_count)
        trigger = [
            key for key, trace in candidate_reading["traces"].items()
            if isinstance(trace.get("r18_gang_dominance_overlay"), dict)
        ]
        if trigger:
            triggered.append({"window": name, "actions": trigger, "origins": origins})
        else:
            if candidate_reading["scores"] != parent_reading["scores"]:
                problems.append(name + ":nontrigger_scores_changed")
            if candidate_reading["action_key"] != parent_reading["action_key"]:
                problems.append(name + ":nontrigger_choice_changed")
        if candidate_reading["scores"] != parent_reading["scores"]:
            changed.append(name)
    elapsed = time.perf_counter() - started
    return {
        "windows": len(windows),
        "triggered_windows": len(triggered),
        "changed_windows": len(changed),
        "mean_candidate_evaluate_ms": 1000.0 * elapsed / max(1, len(windows)),
        "triggered": triggered,
    }, problems, max_operations


def main() -> None:
    if OUT.exists():
        raise SystemExit("R18 P5 开发预检目录已存在；拒绝覆盖")
    confirmation_result = json.loads(CONFIRMATION.read_text(encoding="utf-8"))
    if confirmation_result.get("decision") != "CONFIRMED_OPEN_MECHANICAL_CANDIDATE_AUTHORING":
        raise ValueError("独立自然确认门没有开放机械候选实现")
    discovery_rows, discovery_problems, discovery_ops = evaluate_discovery()
    mutation_rows, mutation_problems, mutation_ops = evaluate_fail_closed_mutations()
    real_summary, real_problems, real_ops = evaluate_real_windows()
    problems = discovery_problems + mutation_problems + real_problems
    positive = [row for row in discovery_rows if row["positive"]]
    negative = [row for row in discovery_rows if not row["positive"]]
    checks = {
        "four_discovery_positives_trigger": len(positive) == 4 and all(
            row["candidate_action"].startswith("gang:added:") and len(row["trigger_keys"]) == 1
            for row in positive
        ),
        "three_nontarget_states_exact_p3": len(negative) == 3 and all(
            row["candidate_action"] == row["parent_action"] and not row["trigger_keys"]
            for row in negative
        ),
        "six_fail_closed_mutations_exact_p3": len(mutation_rows) == 6 and all(
            row["same_scores_as_p3"] and row["same_top_as_p3"] and not row["triggers"]
            for row in mutation_rows
        ),
        "existing_real_windows_exact_p3_when_untriggered": not real_problems,
        "no_problems": not problems,
    }
    passed = all(checks.values())
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p5-development-preflight-manifest/1",
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "confirmation_sha256": digest(CONFIRMATION),
        "sources": {
            str(path): digest(path) for path in (
                Path(__file__), CANDIDATE, PARENT, CONFIRMATION,
                dominance.OUT / "result.json",
                prior.OUT / "manifest.json",
            )
        },
        "candidate_frozen_before_any_new_hidden_bank": True,
        "hidden_bank_read": False,
        "selection_eligible": False,
        "release_eligible": False,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "r18-p5-development-preflight-result/1",
        "status": "PASS_P5_DEVELOPMENT" if passed else "FAIL_P5_DEVELOPMENT",
        "checks": checks,
        "problems": problems,
        "discovery_rows": discovery_rows,
        "fail_closed_mutations": mutation_rows,
        "real_windows": real_summary,
        "max_candidate_operations": max(discovery_ops, mutation_ops, real_ops),
        "candidate_max_operations": scorer(CANDIDATE, "r18-p5-limit-read").max_operations,
        "next": (
            "冻结P5源码；建立新来源隐藏机会验收与完整桌安全门"
            if passed else "停止P5晋级并修复机械判据或精确回退"
        ),
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PASS_P5_DEVELOPMENT" if passed else "FAIL_P5_DEVELOPMENT",
        "checks": checks,
        "problems": problems,
        "max_candidate_operations": max(discovery_ops, mutation_ops, real_ops),
        "real_windows": real_summary,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
