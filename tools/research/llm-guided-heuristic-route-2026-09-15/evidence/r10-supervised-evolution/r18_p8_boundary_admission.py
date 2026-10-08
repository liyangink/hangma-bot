"""R18 P8 七对起手域边界的题库继承与自然反例验收。"""

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
import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_seven_pairs_bank as bank  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_from_json  # noqa: E402
from hangma_bot.offline.opportunity_capability import (  # noqa: E402
    OpportunityCapabilityCase,
    OracleActionValue,
    evaluate_pair,
    summarize_family,
)
from hangma_bot.policy.action_value_policy import (  # noqa: E402
    ActionValuePolicy,
    build_scoring_view,
)
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


AUTHOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p8-seven-pairs-initial-01-20260922')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p8-seven-pairs-initial-01-20260922/generation/candidate.py')
PARENT = bank.PARENT
DEVELOPMENT_OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p8-seven-pairs-initial-01-20260922/development-preflight-01')
HIDDEN_OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p8-historical-hidden-regression-01-20260922')
BORDER_DATASET = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p7-table-safety-topup-01-20260922/natural-trigger-outcome-dataset.json')
BOUNDARY_OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p8-seven-pairs-initial-01-20260922/natural-boundary-regression-01/result.json')
BANK_MANIFEST = bank.OUT / "manifest.json"
DEVELOPMENT_BANK = bank.OUT / "development.json"
HIDDEN_BANK = bank.OUT / "hidden.json"


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


def load_split(name: str) -> tuple[list[OpportunityCapabilityCase], list[dict[str, Any]]]:
    """读取并核对指定冻结分割。"""

    if name not in ("development", "hidden"):
        raise ValueError("未知题库分割")
    payload = json.loads((bank.OUT / (name + ".json")).read_text(encoding="utf-8"))
    cases = []
    metadata = []
    for row in payload["cases"]:
        if bank.digest_value(row["request"]) != row["request_sha256"]:
            raise ValueError(row["case_id"] + " 请求摘要漂移")
        if bank.digest_value(row["reachability_witness"]) != row["reachability_witness_sha256"]:
            raise ValueError(row["case_id"] + " 可达见证摘要漂移")
        cases.append(OpportunityCapabilityCase(
            case_id=row["case_id"],
            base_scenario_id=row["base_scenario_id"],
            family=row["family"],
            split=row["split"],
            generator_seed=row["generator_seed"],
            rules_hash=row["rules_hash"],
            generator_sha256=row["generator_sha256"],
            oracle_version=row["oracle_version"],
            oracle_level=row["oracle_level"],
            request_sha256=row["request_sha256"],
            reachability_witness_sha256=row["reachability_witness_sha256"],
            request=decision_request_from_json(row["request"]),
            action_values=tuple(OracleActionValue(**item) for item in row["action_values"]),
        ))
        metadata.append({
            "decision_type": row["decision_type"],
            "reachability_witness_sha256": row["reachability_witness_sha256"],
        })
    return cases, metadata


def top_key(batch: Any) -> str:
    """按合同排序规则读取首选动作。"""

    return sorted(batch.entries, key=lambda item: (-item.score, item.action_key))[0].action_key


def score_map(batch: Any) -> dict[str, float]:
    """返回完整动作评分。"""

    return {item.action_key: item.score for item in batch.entries}


async def evaluate_split(name: str) -> dict[str, Any]:
    """经正式 BotPolicy 与直接评分双路径评价一个分割。"""

    cases, metadata = load_split(name)
    candidate_source = CANDIDATE.read_text(encoding="utf-8")
    parent_source = PARENT.read_text(encoding="utf-8")
    candidate_policy = ActionValuePolicy(ActionValueScorer("r18-p8-" + name, candidate_source))
    parent_policy = ActionValuePolicy(ActionValueScorer("r18-p8-parent-" + name, parent_source))
    candidate_scorer = ActionValueScorer("r18-p8-direct-" + name, candidate_source)
    parent_scorer = ActionValueScorer("r18-p8-parent-direct-" + name, parent_source)
    outcomes = []
    rows = []
    problems = []
    max_operations = 0
    for case, meta in zip(cases, metadata):
        outcome = await evaluate_pair(candidate_policy, parent_policy, case, bank.bank.budget)
        outcomes.append(outcome)
        view = build_scoring_view(case.request)
        parent_batch = parent_scorer.score(view)
        candidate_batch = candidate_scorer.score(view)
        max_operations = max(max_operations, candidate_scorer.last_operation_count)
        parent_top = top_key(parent_batch)
        candidate_top = top_key(candidate_batch)
        traces = [
            item.action_key for item in candidate_batch.entries
            if isinstance(item.trace.get("r18_seven_pairs_value_overlay"), dict)
            and item.trace["r18_seven_pairs_value_overlay"].get("triggered") is True
        ]
        optimal = set(outcome.candidate.optimal_action_keys)
        dtype = meta["decision_type"]
        if outcome.candidate.status != "SCORED" or outcome.baseline.status != "SCORED":
            problems.append(case.case_id + ":formal_policy_status")
        if candidate_top != outcome.candidate.chosen_action_key:
            problems.append(case.case_id + ":direct_formal_candidate_mismatch")
        if parent_top != outcome.baseline.chosen_action_key:
            problems.append(case.case_id + ":direct_formal_parent_mismatch")
        if dtype == "seven_pairs_tradeoff":
            if candidate_top not in optimal:
                problems.append(case.case_id + ":candidate_miss")
            if parent_top in optimal:
                problems.append(case.case_id + ":parent_has_no_headroom")
            if traces != [candidate_top]:
                problems.append(case.case_id + ":trigger_mismatch")
            if outcome.capability_gain is None or outcome.capability_gain <= 0.0:
                problems.append(case.case_id + ":gain_not_positive")
        elif dtype == "standard_switch":
            if candidate_top not in optimal or parent_top not in optimal:
                problems.append(case.case_id + ":standard_control_miss")
            if traces:
                problems.append(case.case_id + ":standard_control_triggered")
            if score_map(candidate_batch) != score_map(parent_batch):
                problems.append(case.case_id + ":standard_control_scores_changed")
        else:
            problems.append(case.case_id + ":unknown_type")
        rows.append({
            "case_id": case.case_id,
            "decision_type": dtype,
            "optimal_action_keys": sorted(optimal),
            "parent_action": parent_top,
            "candidate_action": candidate_top,
            "trigger_keys": traces,
            "capability_gain": outcome.capability_gain,
            "candidate_operations": candidate_scorer.last_operation_count,
            "reachability_witness_sha256": meta["reachability_witness_sha256"],
        })
    by_type = {}
    for dtype in bank.QUOTAS:
        selected = [row for row in rows if row["decision_type"] == dtype]
        by_type[dtype] = {
            "cases": len(selected),
            "candidate_optimal_hits": sum(row["candidate_action"] in row["optimal_action_keys"] for row in selected),
            "parent_optimal_hits": sum(row["parent_action"] in row["optimal_action_keys"] for row in selected),
            "triggered": sum(bool(row["trigger_keys"]) for row in selected),
            "mean_capability_gain": sum(float(row["capability_gain"] or 0.0) for row in selected) / len(selected),
        }
    expected = {
        "development": {"seven_pairs_tradeoff": 48, "standard_switch": 24},
        "hidden": {"seven_pairs_tradeoff": 16, "standard_switch": 8},
    }[name]
    checks = {
        "expected_counts": all(by_type[key]["cases"] == value for key, value in expected.items()),
        "seven_pairs_all_hit_and_trigger": (
            by_type["seven_pairs_tradeoff"]["candidate_optimal_hits"]
            == by_type["seven_pairs_tradeoff"]["cases"]
            == by_type["seven_pairs_tradeoff"]["triggered"]
        ),
        "seven_pairs_parent_headroom_all": by_type["seven_pairs_tradeoff"]["parent_optimal_hits"] == 0,
        "standard_controls_both_hit": (
            by_type["standard_switch"]["candidate_optimal_hits"]
            == by_type["standard_switch"]["cases"]
            == by_type["standard_switch"]["parent_optimal_hits"]
        ),
        "standard_controls_never_trigger": by_type["standard_switch"]["triggered"] == 0,
        "problems_zero": not problems,
        "operations_within_default_limit": max_operations <= 100_000,
    }
    return {
        "schema": "r18-p8-boundary-admission/1",
        "status": (
            "PASS_P8_DEVELOPMENT" if name == "development" else
            "PASS_P8_HISTORICAL_HIDDEN_REGRESSION"
        ) if all(checks.values()) else (
            "FAIL_P8_DEVELOPMENT" if name == "development" else
            "FAIL_P8_HISTORICAL_HIDDEN_REGRESSION"
        ),
        "split": name,
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "bank_manifest_sha256": digest(BANK_MANIFEST),
        "bank_split_sha256": digest(bank.OUT / (name + ".json")),
        "summary": asdict(summarize_family(
            outcomes, family="seven_pairs_closed", split=name
        )),
        "by_type": by_type,
        "max_candidate_operations": max_operations,
        "checks": checks,
        "problems": problems,
        "rows": rows,
        "selection_eligible": False,
        "release_eligible": False,
    }


def development() -> None:
    """只读开发题完成候选冻结前预检。"""

    if DEVELOPMENT_OUT.exists():
        raise SystemExit("P8 开发预检目录已存在；拒绝覆盖")
    result = asyncio.run(evaluate_split("development"))
    write_json(_project_file(_PROJECT_ROOT, DEVELOPMENT_OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"],
        "by_type": result["by_type"],
        "max_candidate_operations": result["max_candidate_operations"],
        "checks": result["checks"],
        "problems": result["problems"],
    }, ensure_ascii=False, indent=2))
    if result["status"] != "PASS_P8_DEVELOPMENT":
        raise RuntimeError("P8 开发预检未通过")


def prepare_hidden() -> None:
    """冻结候选身份后才开放一次性隐藏评分。"""

    if HIDDEN_OUT.exists():
        raise SystemExit("P8 历史隐藏回归目录已存在；拒绝覆盖")
    development_result = _project_file(_PROJECT_ROOT, DEVELOPMENT_OUT / "result.json")
    result = json.loads(development_result.read_text(encoding="utf-8"))
    if result.get("status") != "PASS_P8_DEVELOPMENT" or result.get("candidate_sha256") != digest(CANDIDATE):
        raise ValueError("P8 当前身份未通过开发预检")
    HIDDEN_OUT.mkdir(parents=True)
    write_json(_project_file(_PROJECT_ROOT, HIDDEN_OUT / "manifest.json"), {
        "schema": "r18-p8-historical-hidden-regression-manifest/1",
        "created_by": str(Path(__file__).relative_to(ROOT)),
        "runtime": guard.capture(source_paths=[
            Path(__file__), Path(bank.__file__), CANDIDATE, PARENT,
            BANK_MANIFEST, HIDDEN_BANK, development_result,
        ]),
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "bank_manifest_sha256": digest(BANK_MANIFEST),
        "hidden_bank_sha256": digest(HIDDEN_BANK),
        "development_result_sha256": digest(development_result),
        "hidden_cases": 24,
        "hidden_tradeoff_cases": 16,
        "hidden_standard_controls": 8,
        "max_model_calls": 0,
        "historical_hidden_only": True,
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED",
        "candidate_sha256": digest(CANDIDATE),
        "hidden_cases": 24,
    }, ensure_ascii=False))


def hidden() -> None:
    """一次性读取隐藏题并执行冻结门。"""

    result_path = _project_file(_PROJECT_ROOT, HIDDEN_OUT / "result.json")
    if result_path.exists():
        raise SystemExit("P8 历史隐藏回归结果已存在；拒绝覆盖")
    manifest = json.loads((_project_file(_PROJECT_ROOT, HIDDEN_OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "candidate": (manifest["candidate_sha256"], digest(CANDIDATE)),
        "parent": (manifest["parent_sha256"], digest(PARENT)),
        "bank_manifest": (manifest["bank_manifest_sha256"], digest(BANK_MANIFEST)),
        "hidden_bank": (manifest["hidden_bank_sha256"], digest(HIDDEN_BANK)),
        "development": (
            manifest["development_result_sha256"],
            digest(_project_file(_PROJECT_ROOT, DEVELOPMENT_OUT / "result.json")),
        ),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + " 漂移")
    guard.verify(manifest["runtime"])
    result = asyncio.run(evaluate_split("hidden"))
    write_json(result_path, result)
    print(json.dumps({
        "status": result["status"],
        "by_type": result["by_type"],
        "max_candidate_operations": result["max_candidate_operations"],
        "checks": result["checks"],
        "problems": result["problems"],
    }, ensure_ascii=False, indent=2))
    if result["status"] != "PASS_P8_HISTORICAL_HIDDEN_REGRESSION":
        raise RuntimeError("P8 历史隐藏回归未通过")


async def evaluate_boundary() -> dict[str, Any]:
    """确认 29 个越域自然窗口逐点评分严格回退 P5。"""

    document = json.loads(BORDER_DATASET.read_text(encoding="utf-8"))
    if document.get("status") != "COMPLETE" or len(document.get("rows") or []) != 29:
        raise ValueError("P7 自然触发反例数据集不完整")
    candidate_source = CANDIDATE.read_text(encoding="utf-8")
    parent_source = PARENT.read_text(encoding="utf-8")
    candidate_policy = ActionValuePolicy(ActionValueScorer("r18-p8-boundary", candidate_source))
    parent_policy = ActionValuePolicy(ActionValueScorer("r18-p8-boundary-parent", parent_source))
    candidate_scorer = ActionValueScorer("r18-p8-boundary-direct", candidate_source)
    parent_scorer = ActionValueScorer("r18-p8-boundary-parent-direct", parent_source)
    rows = []
    problems = []
    max_operations = 0
    for item in document["rows"]:
        request = decision_request_from_json(item["request"])
        candidate_plan = await candidate_policy.choose(request, bank.bank.budget)
        parent_plan = await parent_policy.choose(request, bank.bank.budget)
        view = build_scoring_view(request)
        candidate_batch = candidate_scorer.score(view)
        parent_batch = parent_scorer.score(view)
        max_operations = max(max_operations, candidate_scorer.last_operation_count)
        traces = [
            entry.action_key for entry in candidate_batch.entries
            if isinstance(entry.trace.get("r18_seven_pairs_value_overlay"), dict)
            and entry.trace["r18_seven_pairs_value_overlay"].get("triggered") is True
        ]
        same_scores = score_map(candidate_batch) == score_map(parent_batch)
        same_direct_top = top_key(candidate_batch) == top_key(parent_batch)
        same_formal_top = (
            candidate_plan.candidates[0].action_key
            == parent_plan.candidates[0].action_key
        )
        if traces:
            problems.append(item["request_sha256"] + ":p8_triggered_outside_domain")
        if not same_scores:
            problems.append(item["request_sha256"] + ":scores_not_exact_p5")
        if not same_direct_top or not same_formal_top:
            problems.append(item["request_sha256"] + ":top_not_exact_p5")
        rows.append({
            "request_sha256": item["request_sha256"],
            "source_id": item["source_id"],
            "remaining_tile_count": request.observation.remaining_tile_count,
            "river_lengths": [len(river) for river in request.observation.discards],
            "trigger_keys": traces,
            "same_scores": same_scores,
            "same_direct_top": same_direct_top,
            "same_formal_top": same_formal_top,
            "candidate_operations": candidate_scorer.last_operation_count,
        })
    checks = {
        "all_29_replayed": len(rows) == 29,
        "all_outside_validated_initial_domain": all(
            row["remaining_tile_count"] != 83 or any(row["river_lengths"])
            for row in rows
        ),
        "all_exact_p5_fallback": all(
            row["same_scores"] and row["same_direct_top"] and row["same_formal_top"]
            and not row["trigger_keys"] for row in rows
        ),
        "operations_within_default_limit": max_operations <= 100_000,
        "problems_zero": not problems,
    }
    return {
        "schema": "r18-p8-natural-boundary-regression/1",
        "status": "PASS_P8_NATURAL_BOUNDARY" if all(checks.values()) else "FAIL_P8_NATURAL_BOUNDARY",
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "dataset_sha256": digest(BORDER_DATASET),
        "cases": len(rows),
        "max_candidate_operations": max_operations,
        "checks": checks,
        "problems": problems,
        "rows": rows,
        "selection_eligible": False,
        "release_eligible": False,
    }


def boundary() -> None:
    """执行自然越域反例的精确回退门。"""

    if BOUNDARY_OUT.exists():
        raise SystemExit("P8 自然边界回归结果已存在；拒绝覆盖")
    result = asyncio.run(evaluate_boundary())
    write_json(BOUNDARY_OUT, result)
    print(json.dumps({
        "status": result["status"], "cases": result["cases"],
        "max_candidate_operations": result["max_candidate_operations"],
        "checks": result["checks"], "problems": result["problems"],
    }, ensure_ascii=False, indent=2))
    if result["status"] != "PASS_P8_NATURAL_BOUNDARY":
        raise RuntimeError("P8 自然边界回归未通过")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("development", "prepare-hidden", "hidden", "boundary"))
    args = parser.parse_args()
    if args.operation == "development":
        development()
    elif args.operation == "prepare-hidden":
        prepare_hidden()
    elif args.operation == "hidden":
        hidden()
    else:
        boundary()


if __name__ == "__main__":
    main()
