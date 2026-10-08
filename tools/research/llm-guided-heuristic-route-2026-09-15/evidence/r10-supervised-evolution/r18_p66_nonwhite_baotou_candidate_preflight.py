"""R18 P66：非财神建爆头候选的开发与回归零桌预检。"""

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

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import claim_counterfactual_pilot as core  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import r18_p13_development_seven_pairs_teacher as p13  # noqa: E402
import r18_p47_integrated_parent_registration as p47  # noqa: E402
import r18_p64_nonwhite_baotou_development_teacher as p64  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.serialization import window_key_from_json  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p66-nonwhite-baotou-candidate-preflight-01-20260923')
PARENT = p64.PARENT
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p65-nonwhite-baotou-author-01-20260923/generation-supervisor01/candidate.py')
SUPERVISOR_REPAIR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p65-nonwhite-baotou-author-01-20260923/generation-supervisor01/manifest.json')
P47_RESULT = p47.OUT / "result.json"
P64_RESULT = p64.OUT / "result.json"
P64_TARGETS = p64.OUT / "targets.json"
P64_CAPTURE = p64.OUT / "capture-summary.json"
TRACE_KEY = "hu_vs_nonwealth_baotou_cf"
EXPECTED_REGRESSION_REQUESTS = 377
EXPECTED_DEVELOPMENT_STATES = 16


def digest(path: Path) -> str:
    """返回文件字节 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """稳定写入 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def source_paths() -> list[Path]:
    """列出影响预检语义的实现与冻结输入。"""

    return [
        Path(__file__), Path(p13.__file__), Path(p47.__file__), Path(p64.__file__),
        PARENT, CANDIDATE, SUPERVISOR_REPAIR,
        P47_RESULT, P64_RESULT, P64_TARGETS, P64_CAPTURE,
    ]


def prepare() -> None:
    """在运行候选前冻结输入、样本与逐点验收条件。"""

    if OUT.exists():
        raise SystemExit("P66 目录已存在；拒绝覆盖")
    p47_result = json.loads(P47_RESULT.read_text(encoding="utf-8"))
    p64_result = json.loads(P64_RESULT.read_text(encoding="utf-8"))
    repair = json.loads(SUPERVISOR_REPAIR.read_text(encoding="utf-8"))
    targets = p64.targets()
    checks = {
        "p47_active_parent": (
            p47_result.get("status") == "PASS_P47_INTEGRATED_PARENT_REGISTRATION"
            and p47_result.get("active_research_parent") is True
            and p47_result.get("candidate_sha256") == digest(PARENT)
        ),
        "p64_opened_author": (
            p64_result.get("decision") == "OPEN_P65_LIMITED_AUTHOR"
            and p64_result.get("gate_passed") is True
            and p64_result.get("replication_labels_opened") is False
        ),
        "candidate_static_repair_accepted": (
            repair.get("accepted_for_development_preflight") is True
            and repair.get("candidate_sha256") == digest(CANDIDATE)
        ),
        "development_count": sum(
            row["split"] == "development" for row in targets
        ) == EXPECTED_DEVELOPMENT_STATES,
        "replication_kept_blind": (
            sum(row["split"] == "replication" for row in targets) == 16
            and not any(
                p64.snapshot_path(row).exists()
                for row in targets if row["split"] == "replication"
            )
        ),
    }
    if not all(checks.values()):
        raise ValueError("P66 前置条件失败：" + repr(checks))
    OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), {
        "schema": "r18-p66-nonwhite-baotou-preflight-authorization/1",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "purpose": "在打开16个复验根前证明P65只实现冻结覆盖且P47回归逐点不变",
        "expected_regression_requests": EXPECTED_REGRESSION_REQUESTS,
        "expected_development_states": EXPECTED_DEVELOPMENT_STATES,
        "gate": {
            "all_regression_scores_exactly_parent": True,
            "all_regression_triggers_false": True,
            "all_development_targets_trigger": True,
            "only_target_score_changes": True,
            "target_score_equals_parent_hu_plus_one": True,
            "candidate_trace_minus_new_mapping_equals_parent_trace": True,
            "mechanical_failures": 0,
        },
        "budgets": {"tables_full": 0, "model_calls": 0, "network_calls": 0},
        "prerequisite_checks": checks,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p66-nonwhite-baotou-preflight-manifest/1",
        "runtime": guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "p64_targets_sha256": digest(P64_TARGETS),
        "replication_evaluation_started": False,
        "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", **checks}, ensure_ascii=False))


def verify() -> None:
    """核对候选、父代、目标和运行实现未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["candidate_sha256"] != digest(CANDIDATE):
        raise ValueError("P66 候选源码漂移")
    if manifest["parent_sha256"] != digest(PARENT):
        raise ValueError("P66 P47父代漂移")
    if manifest["p64_targets_sha256"] != digest(P64_TARGETS):
        raise ValueError("P66 P64目标漂移")
    guard.verify(manifest["runtime"])


def trace_without_new_mapping(trace: Mapping[str, Any]) -> dict[str, Any]:
    """移除 P65 唯一新增解释键，以核对父代解释逐点等价。"""

    return {key: value for key, value in trace.items() if key != TRACE_KEY}


def exact_request(target: Mapping[str, Any]) -> Any:
    """从 P64 已捕获开发快照重建精确公开请求，不生成新隐藏世界。"""

    snapshot = json.loads(p64.snapshot_path(target).read_text(encoding="utf-8"))
    contract = json.loads(p64.CONTRACT.read_text(encoding="utf-8"))
    rules = HangmaRules(core.rule_config_from_contract(contract))
    runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
        seed=int(snapshot["match_spec"]["seed"]),
        scenario_id=str(snapshot["match_spec"]["scenario_id"]),
    )
    engine, world = opportunities.rebuild_world(
        rules=rules, snapshot=snapshot, value_limits=p64.p13.LIMITS, runtime=runtime,
    )
    wanted = window_key_from_json(target["window_key"])
    decision = next(
        item for item in engine.frame(world).decisions if item.window_key == wanted
    )
    analysis = rules.analyze(decision.observation, value_limits=p64.p13.LIMITS)
    request = opportunities.real_window_request(
        decision=decision,
        analysis=analysis,
        match_id=str(snapshot["match_spec"]["match_id"]),
        config=opportunities._driver_config(),
        now_monotonic=lambda: 800.0,
    )
    capture = p13.ExactStateCapture(target)
    if capture(request) is None or capture.hits != 1:
        raise ValueError("P66 开发请求未精确命中冻结状态")
    return request


def score_rows(scorer: ActionValueScorer, request: Any) -> list[Any]:
    """经正式评分视图运行受限候选并返回稳定排序。"""

    batch = scorer.score(
        build_scoring_view(request, value_limits=p64.p13.LIMITS)
    )
    if batch.status != "SCORED":
        raise ValueError("候选 ABSTAIN：" + str(batch.reason))
    return sorted(batch.entries, key=lambda entry: (-entry.score, entry.action_key))


def run() -> None:
    """执行 377 请求回归与 16 个开发目标的逐点机制验收。"""

    verify()
    parent = ActionValueScorer("r18-p66-parent", PARENT.read_text(encoding="utf-8"))
    candidate = ActionValueScorer(
        "r18-p66-candidate", CANDIDATE.read_text(encoding="utf-8")
    )
    regression = []
    failures = []
    requests = p47.current_requests()
    for label, request in requests:
        try:
            before = score_rows(parent, request)
            after = score_rows(candidate, request)
            by_key = {entry.action_key: entry for entry in before}
            exact_keys = [entry.action_key for entry in after] == [
                entry.action_key for entry in before
            ]
            exact_scores = all(
                entry.action_key in by_key
                and entry.score == by_key[entry.action_key].score
                for entry in after
            )
            triggers = [
                entry.action_key for entry in after
                if isinstance(entry.trace.get(TRACE_KEY), Mapping)
                and entry.trace[TRACE_KEY].get("triggered") is True
            ]
            exact_parent_traces = all(
                entry.action_key in by_key
                and trace_without_new_mapping(entry.trace)
                == by_key[entry.action_key].trace
                for entry in after
            )
            row = {
                "label": label,
                "exact_order": exact_keys,
                "exact_scores": exact_scores,
                "exact_parent_traces": exact_parent_traces,
                "triggered_actions": triggers,
            }
            regression.append(row)
            if not (
                exact_keys and exact_scores and exact_parent_traces and not triggers
            ):
                failures.append({"scope": "regression", **row})
        except Exception as exc:  # noqa: BLE001
            failures.append({
                "scope": "regression", "label": label,
                "error": type(exc).__name__ + ": " + str(exc),
            })

    development = []
    targets = [row for row in p64.targets() if row["split"] == "development"]
    for target in targets:
        try:
            request = exact_request(target)
            before = score_rows(parent, request)
            after = score_rows(candidate, request)
            before_by_key = {entry.action_key: entry for entry in before}
            after_by_key = {entry.action_key: entry for entry in after}
            parent_top = before[0].action_key
            candidate_top = after[0].action_key
            target_key = str(target["intervention_action"])
            hu_score = before_by_key["hu"].score
            changed = sorted(
                key for key in before_by_key
                if after_by_key[key].score != before_by_key[key].score
            )
            mappings = [entry.trace.get(TRACE_KEY) for entry in after]
            mapping_complete = all(isinstance(item, Mapping) for item in mappings)
            trigger_all = mapping_complete and all(
                item.get("triggered") is True for item in mappings
            )
            target_mapping = after_by_key[target_key].trace.get(TRACE_KEY) or {}
            trace_parent_exact = all(
                trace_without_new_mapping(entry.trace)
                == before_by_key[entry.action_key].trace
                for entry in after
            )
            mechanism_exact = bool(
                parent_top == "hu"
                and candidate_top == target_key
                and changed == [target_key]
                and after_by_key[target_key].score == hu_score + 1.0
                and trigger_all
                and target_mapping.get("target_action") == target_key
                and target_mapping.get("score_capacity")
                == target["features"]["baotou_score_capacity"]
                and target_mapping.get("support_remaining")
                == target["features"]["baotou_support_remaining"]
                and target_mapping.get("min_route_fan")
                == target["features"]["baotou_min_fan"]
                and trace_parent_exact
            )
            row = {
                "target_id": target["target_id"],
                "parent_top": parent_top,
                "candidate_top": candidate_top,
                "expected_target": target_key,
                "changed_scores": changed,
                "target_score": after_by_key[target_key].score,
                "parent_hu_score": hu_score,
                "trace_parent_exact": trace_parent_exact,
                "mechanism_exact": mechanism_exact,
            }
            development.append(row)
            if not mechanism_exact:
                failures.append({"scope": "development", **row})
        except Exception as exc:  # noqa: BLE001
            failures.append({
                "scope": "development", "target_id": target["target_id"],
                "error": type(exc).__name__ + ": " + str(exc),
            })

    passed = bool(
        len(requests) == EXPECTED_REGRESSION_REQUESTS
        and len(regression) == EXPECTED_REGRESSION_REQUESTS
        and len(development) == EXPECTED_DEVELOPMENT_STATES
        and not failures
        and all(row["mechanism_exact"] for row in development)
    )
    result = {
        "schema": "r18-p66-nonwhite-baotou-candidate-preflight-result/1",
        "status": (
            "PASS_P66_NONWEALTH_BAOTOU_CANDIDATE_PREFLIGHT"
            if passed else "FAIL_P66_NONWEALTH_BAOTOU_CANDIDATE_PREFLIGHT"
        ),
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "regression_requests": len(regression),
        "regression_exact": sum(
            row["exact_order"] and row["exact_scores"]
            and row["exact_parent_traces"] and not row["triggered_actions"]
            for row in regression
        ),
        "development_states": len(development),
        "development_exact": sum(row["mechanism_exact"] for row in development),
        "failures": failures,
        "regression": regression,
        "development": development,
        "replication_evaluation_started": False,
        "model_calls": 0,
        "tables_run": 0,
        "selection_eligible": False,
        "release_eligible": False,
        "decision": (
            "OPEN_P67_REPLICATION" if passed
            else "REJECT_P65_BEFORE_REPLICATION"
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        key: result[key] for key in (
            "status", "regression_requests", "regression_exact",
            "development_states", "development_exact", "failures", "decision",
        )
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run"))
    globals()[parser.parse_args().command]()


if __name__ == "__main__":
    main()
