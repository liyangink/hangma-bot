"""R17 代际 1：在全新 H/M 来源评价通过零桌门的单叶程序。"""

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
import concurrent.futures
import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (
    _project_file(_PROJECT_ROOT, ROOT / "src"),
    _project_file(_PROJECT_ROOT, ROUTE / "tools"),
    _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"),
    HERE,
):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.config import RuleConfig  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402
from hangma_bot.policy.public_successor_leaf_executor import (  # noqa: E402
    LeafProgramExecutor,
)
from hangma_bot.policy.public_successor_policy import (  # noqa: E402
    PublicSuccessorSearchPolicy,
)
from hangma_bot.policy.public_successor_search import (  # noqa: E402
    order_discard_keys_by_fronts,
    reduce_public_successors,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-generation1-effect-03-20260921')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R17-RULE-OWNED-PUBLIC-SEARCH-EVOLUTION-PLAN-2026-09-21.md')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
LEAF_CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/r17-public-successor-leaf-v1.json')
PANEL_SEED = 2026092917
MIXES = ("H", "M")
ROOTS = tuple(range(1, 9))
SEATS = (0, 1, 2, 3)
SOURCE_UNITS = len(MIXES) * len(ROOTS) * len(SEATS)
CANDIDATE_INPUTS = {
    "A": {
        "author_dir": _project_file(_PROJECT_ROOT, HERE / "r17-seed-author-a-astra-01-20260921"),
        "gate_dir": _project_file(_PROJECT_ROOT, HERE / "r17-seed-gate-a-astra-03-20260921"),
    },
    "B": {
        "author_dir": _project_file(_PROJECT_ROOT, HERE / "r17-seed-author-b-sol-repair-01-20260921"),
        "gate_dir": _project_file(_PROJECT_ROOT, HERE / "r17-seed-gate-b-sol-repair-03-20260921"),
    },
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sources() -> list[dict[str, Any]]:
    return [
        {
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "source_id": f"{mix}:r{root:02d}:s{seat}",
        }
        for mix in MIXES
        for root in ROOTS
        for seat in SEATS
    ]


def passing_candidates() -> dict[str, dict[str, str]]:
    """只接收身份与全窗行为均已冻结通过的两个预登记种子。"""

    passed = {}
    for candidate_id, inputs in CANDIDATE_INPUTS.items():
        candidate_path = inputs["author_dir"] / "candidate.py"
        gate_path = inputs["gate_dir"] / "result.json"
        result = json.loads(gate_path.read_text(encoding="utf-8"))
        if (
            result.get("status") != "PASS_R17_SEED_ZERO_TABLE"
            or not result.get("coverage_pass")
            or not result.get("behavior_pass")
            or result.get("failures")
        ):
            raise RuntimeError("R17 种子未通过冻结零桌门: " + candidate_id)
        if result.get("candidate_source_sha256") != digest(candidate_path):
            raise RuntimeError("R17 种子源码与零桌身份漂移: " + candidate_id)
        passed[candidate_id] = {
            "path": str(candidate_path),
            "sha256": digest(candidate_path),
            "identity": str(result["candidate_identity"]),
            "gate_result": str(gate_path),
            "gate_result_sha256": digest(gate_path),
        }
    return passed


def source_paths(candidates: Mapping[str, Mapping[str, str]]) -> list[Path]:
    paths = [
        Path(__file__),
        PLAN,
        CONTRACT,
        LEAF_CONTRACT,
        Path(natural.__file__),
    ]
    for item in candidates.values():
        paths.extend((Path(item["path"]), Path(item["gate_result"])))
    return paths


def prepare() -> None:
    """冻结两个种子、全新来源以及共享基线的 384 桌完整预算。"""

    if OUT.exists():
        raise SystemExit("R17 代际1输出已存在；拒绝覆盖")
    candidates = passing_candidates()
    for candidate_id, item in candidates.items():
        LeafProgramExecutor(
            Path(item["path"]).read_text(encoding="utf-8"),
            name="r17-generation1-precheck-" + candidate_id,
        )
    arms = ["baseline", *["candidate:" + item for item in sorted(candidates)]]
    planned_tables = SOURCE_UNITS * len(arms) * 2
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r17-generation1-effect-02",
        accounts={"tables_full": planned_tables},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update(
        {
            "issuance_basis": "R17 两个预登记种子通过源码绑定、226窗完整归约、确定性、删边拒绝和非同分行为门",
            "scope": "稳定V2和R17种子A/B；全新H/M各8根、4座位、完整两桌；基线在两候选间共享；开发选择，不确认不发布",
            "max_model_calls": 0,
            "confirmation_roots": 0,
        }
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    manifest = {
        "schema": "r17-generation1-effect/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(
            source_paths=source_paths(candidates) + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]
        ),
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "leaf_contract": str(LEAF_CONTRACT),
        "leaf_contract_sha256": digest(LEAF_CONTRACT),
        "candidates": candidates,
        "rules_hash": natural.compute_rules_hash(natural.REPO),
        "panel_seed": PANEL_SEED,
        "source_relation": "全新 panel_seed；零桌窗口与先前 R16 开发来源均不参与本轮选根",
        "mixes": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "source_units": SOURCE_UNITS,
        "tables_per_stage": 2,
        "arms": arms,
        "planned_tables": planned_tables,
        "shared_baseline_tables": SOURCE_UNITS * 2,
        "per_candidate_comparison_tables": SOURCE_UNITS * 2 * 2,
        "workers": 4,
        "gate": {
            "overall_u_delta_low_mean": ">0",
            "each_mix_u_delta_low_mean": ">=0",
            "at_least_one_mix_u_delta_low_mean": ">0",
            "positive_u_units_distinct_roots_min": 2,
            "positive_u_units_distinct_seats_min": 2,
            "simulation_execution_failures": 0,
            "eligible_draw_reduction_failures": 0,
            "response_non_fallbacks": 0,
        },
        "diagnostics_not_gates": [
            "first_table_delta_mean",
            "stage_score_delta_mean",
            "stage_score_delta_quantiles",
            "fourth_place_rate",
            "unresolved_rate",
            "policy_elapsed_ms",
        ],
        "first_table_policy": "记录但不淘汰；全部来源执行完整两桌",
        "strength_claim": False,
        "confirmation_reserved": 0,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(
        json.dumps(
            {
                "status": "PREPARED",
                "candidates": sorted(candidates),
                "sources": SOURCE_UNITS,
                "planned_tables": planned_tables,
            },
            ensure_ascii=False,
        )
    )


def verify_manifest() -> dict[str, Any]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    for key, sha_key in (
        ("plan", "plan_sha256"),
        ("contract", "contract_sha256"),
        ("leaf_contract", "leaf_contract_sha256"),
    ):
        if digest(Path(manifest[key])) != manifest[sha_key]:
            raise RuntimeError("冻结输入摘要漂移: " + key)
    for candidate_id, item in manifest["candidates"].items():
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("冻结候选摘要漂移: " + candidate_id)
        if digest(Path(item["gate_result"])) != item["gate_result_sha256"]:
            raise RuntimeError("冻结零桌门摘要漂移: " + candidate_id)
    guard.verify(manifest["runtime"])
    return manifest


async def _audit_requests(
    requests: list[Any], source: str, candidate_identity: str
) -> dict[str, Any]:
    """在臂结束后复算每个焦点请求，覆盖策略内部精确回退无法携带的诊断。"""

    rules_cache = {}
    executor = LeafProgramExecutor(source, name="r17-stage-request-audit")
    baseline = ComparableHeuristicPolicyV2(monotonic=lambda: 0.0)
    budget = DecisionBudget(10.0, 20.0, 30.0)
    counts = {
        "requests": 0,
        "response_exact_fallbacks": 0,
        "draw_not_applicable": 0,
        "eligible_draws": 0,
        "complete_eligible_draws": 0,
        "changed_eligible_draws": 0,
    }
    failures = []
    max_leaf_evaluations = 0
    max_candidate_operations = 0
    for request in requests:
        counts["requests"] += 1
        baseline_plan = await baseline.choose(request, budget)
        baseline_keys = tuple(
            item.action_key
            for item in baseline_plan.candidates
            if item.action_key.startswith("discard:")
        )
        if request.observation.phase != "draw":
            counts["response_exact_fallbacks"] += 1
            continue
        if len(baseline_keys) < 2:
            counts["draw_not_applicable"] += 1
            continue
        counts["eligible_draws"] += 1
        version = request.rules.ruleset_version
        rules = rules_cache.setdefault(
            version, HangmaRules(RuleConfig(version, 1, False))
        )
        analysis = rules.analyze_public_self_draw_successors(request.observation)
        scorer = executor.window_scorer()
        reduction = reduce_public_successors(request, analysis, scorer)
        max_leaf_evaluations = max(
            max_leaf_evaluations,
            sum(item.leaf_evaluations for item in reduction.roots),
        )
        max_candidate_operations = max(
            max_candidate_operations, scorer.operation_count
        )
        ordered = order_discard_keys_by_fronts(reduction, baseline_keys)
        if not reduction.complete:
            failures.append(
                {
                    "decision_id": request.decision_id,
                    "reason": reduction.reason,
                }
            )
            continue
        counts["complete_eligible_draws"] += 1
        if ordered != baseline_keys:
            counts["changed_eligible_draws"] += 1
    return {
        "schema": "r17-stage-request-audit/1",
        "candidate_identity": candidate_identity,
        "counts": counts,
        "workload": {
            "max_leaf_evaluations": max_leaf_evaluations,
            "max_candidate_operations": max_candidate_operations,
        },
        "failures": failures,
        "pass": (
            counts["complete_eligible_draws"] == counts["eligible_draws"]
            and not failures
        ),
    }


def execute_stage(
    arm: str,
    source_row: Mapping[str, Any],
    candidates: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    """每个进程独立装载候选，运行一个真实两桌阶段并复算公开后继状态。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source_row["mix"]),
        root_index=int(source_row["root_index"]),
        focal_seat=int(source_row["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    requests: list[Any] = []
    factory = None
    candidate_identity = None
    source = None
    if arm.startswith("candidate:"):
        candidate_id = arm.split(":", 1)[1]
        item = candidates[candidate_id]
        source = Path(item["path"]).read_text(encoding="utf-8")
        candidate_identity = str(item["identity"])
        versions = natural.stage.contract_versions_block(contract)

        def factory(monotonic):
            rules = HangmaRules(
                RuleConfig(
                    ruleset_version=str(versions["ruleset_version"]),
                    base_score=int(versions["base_score"]),
                    you_cai_bi_kao=bool(versions["you_cai_bi_kao"]),
                )
            )
            return PublicSuccessorSearchPolicy(
                rules.analyze_public_self_draw_successors,
                LeafProgramExecutor(source, name="r17-stage-" + candidate_id),
                candidate_identity=candidate_identity,
                monotonic=monotonic,
            )

    result = natural.run_arm_stage(
        arm="candidate" if arm.startswith("candidate:") else "baseline",
        plans=plans,
        candidate_scorer=None,
        opponent_policies=contract["panel"]["opponent_scenarios"][
            str(source_row["mix"])
        ]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=ValueAnalysisLimits(),
        decision_observer=(requests.append if factory is not None else None),
        candidate_policy_factory=factory,
    )
    result["arm"] = arm
    if factory is not None:
        result["r17_request_audit"] = asyncio.run(
            _audit_requests(requests, source, candidate_identity)
        )
        if not result["r17_request_audit"]["pass"]:
            result["status"] = "error"
            result["usable"] = False
            result["error"] = "R17 焦点请求复算存在不完整归约"
    return {"arm": arm, "source": dict(source_row), "stage": result}


def _stage_path(arm: str, source_row: Mapping[str, Any]) -> Path:
    safe_arm = arm.replace(":", "-")
    safe_source = str(source_row["source_id"]).replace(":", "-")
    return _project_file(_PROJECT_ROOT, OUT / "stages" / f"{safe_arm}-{safe_source}.json")


def _failed_stage_path(arm: str, source_row: Mapping[str, Any]) -> Path:
    """保留已经执行但未通过后置审计的阶段，供实际桌数记账。"""

    safe_arm = arm.replace(":", "-")
    safe_source = str(source_row["source_id"]).replace(":", "-")
    return _project_file(_PROJECT_ROOT, OUT / "failed-stages" / f"{safe_arm}-{safe_source}.json")


def run() -> None:
    """并行执行冻结阶段；中断后只跳过身份仍匹配的完整文件。"""

    manifest = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for source_row in sources():
        for arm in manifest["arms"]:
            path = _stage_path(arm, source_row)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if (
                    row.get("stage", {}).get("status") != "complete"
                    or len(row["stage"].get("tables") or []) != 2
                ):
                    raise RuntimeError("既有阶段文件不完整: " + str(path))
                completed_tables += 2
            else:
                pending.append((arm, source_row))
    preexisting_complete_tables = completed_tables
    reservation = ledger.reserve(
        step_id="r17-generation1:full-stages",
        account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="R17代际1全新来源完整两桌；异常按未完成预留保守结算",
    )
    failures = []
    executed_tables_this_run = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=manifest["workers"]
        ) as pool:
            futures = {
                pool.submit(
                    execute_stage, arm, source_row, manifest["candidates"]
                ): (arm, source_row)
                for arm, source_row in pending
            }
            for future in concurrent.futures.as_completed(futures):
                arm, source_row = futures[future]
                row = None
                try:
                    row = future.result()
                    returned_tables = len(row.get("stage", {}).get("tables") or [])
                    executed_tables_this_run += returned_tables
                    if (
                        row["stage"]["status"] != "complete"
                        or returned_tables != 2
                    ):
                        write_json(_failed_stage_path(arm, source_row), row)
                        raise RuntimeError(row["stage"].get("error") or "阶段未完整")
                    write_json(_stage_path(arm, source_row), row)
                    completed_tables += 2
                    if completed_tables % 32 == 0 or completed_tables == manifest["planned_tables"]:
                        print(
                            json.dumps(
                                {
                                    "completed_tables": completed_tables,
                                    "planned_tables": manifest["planned_tables"],
                                },
                                ensure_ascii=False,
                            ),
                            flush=True,
                        )
                except Exception as exc:  # noqa: BLE001
                    if row is None:
                        usage_unknown = True
                    failures.append(
                        {
                            "arm": arm,
                            "source": source_row,
                            "error": type(exc).__name__ + ": " + str(exc),
                            "known_executed_tables": (
                                None
                                if row is None
                                else len(row.get("stage", {}).get("tables") or [])
                            ),
                        }
                    )
    except BaseException:
        ledger.settle(
            reservation,
            usage_unknown=True,
            note="进程中断，实际执行桌数未知，按预留额度保守结算",
        )
        raise
    all_files = (
        list((_project_file(_PROJECT_ROOT, OUT / "stages")).glob("*.json"))
        if (_project_file(_PROJECT_ROOT, OUT / "stages")).exists()
        else []
    )
    actual_tables = sum(
        len(json.loads(path.read_text(encoding="utf-8"))["stage"].get("tables") or [])
        for path in all_files
    )
    if usage_unknown:
        ledger.settle(
            reservation,
            usage_unknown=True,
            note="至少一个子进程未返回阶段对象，按预留额度保守结算",
        )
    else:
        ledger.settle(
            reservation,
            actual=executed_tables_this_run,
            note="按本次成功及后置审计失败阶段实际返回的桌数结算",
        )
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "run-summary.json"),
        {
            "schema": "r17-generation1-run/1",
            "stage_files": len(all_files),
            "actual_tables": actual_tables,
            "preexisting_complete_tables": preexisting_complete_tables,
            "executed_tables_this_run": executed_tables_this_run,
            "usage_unknown": usage_unknown,
            "failures": failures,
            "spent": ledger.account_summary(),
        },
    )
    expected_files = SOURCE_UNITS * len(manifest["arms"])
    if (
        failures
        or len(all_files) != expected_files
        or actual_tables != manifest["planned_tables"]
    ):
        raise RuntimeError("R17代际1执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual_tables}, ensure_ascii=False))


def mean(rows: list[dict[str, Any]], key: str) -> float:
    return statistics.fmean(float(row[key]) for row in rows)


def quantiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)

    def pick(fraction: float) -> float:
        return ordered[round((len(ordered) - 1) * fraction)]

    return {
        "min": ordered[0],
        "p10": pick(0.10),
        "median": pick(0.50),
        "p90": pick(0.90),
        "max": ordered[-1],
    }


def focal_score(table: Mapping[str, Any]) -> int:
    participants = table["stage_situation"]["participant_ids_by_seat"]
    seat = participants.index(natural.FOCAL_PARTICIPANT)
    return int(table["scores_by_seat"][seat])


def fourth(stage_row: Mapping[str, Any]) -> bool:
    interval = stage_row.get("u_interval") or {}
    return interval.get("a") == 4 and interval.get("b") == 4


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sources": len(rows),
        "first_table_delta_mean": mean(rows, "first_table_delta"),
        "stage_score_delta_mean": mean(rows, "stage_score_delta"),
        "stage_score_delta_quantiles": quantiles(
            [float(row["stage_score_delta"]) for row in rows]
        ),
        "u_delta_low_mean": mean(rows, "u_delta_low"),
        "u_delta_high_mean": mean(rows, "u_delta_high"),
        "candidate_fourth_rate": mean(rows, "candidate_fourth"),
        "baseline_fourth_rate": mean(rows, "baseline_fourth"),
        "candidate_unresolved_rate": mean(rows, "candidate_unresolved"),
        "baseline_unresolved_rate": mean(rows, "baseline_unresolved"),
    }


def analyze() -> None:
    """逐候选按预登记 U 同向门裁定，积分和第四率只作诊断。"""

    manifest = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if (
        run_summary.get("failures")
        or run_summary.get("actual_tables") != manifest["planned_tables"]
    ):
        raise RuntimeError("执行未完整，拒绝分析")
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    all_tables = []
    for source_row in sources():
        for arm in manifest["arms"]:
            stage_row = json.loads(
                _stage_path(arm, source_row).read_text(encoding="utf-8")
            )["stage"]
            by_key[(arm, str(source_row["source_id"]))] = stage_row
            all_tables.extend(stage_row["tables"])
    simulation_audit = natural.execution_audit.review_tables(all_tables)
    candidate_results = []
    all_paired = {}
    for candidate_id in manifest["candidates"]:
        arm = "candidate:" + candidate_id
        paired = []
        request_audit_failures = []
        request_counts = {
            "requests": 0,
            "response_exact_fallbacks": 0,
            "draw_not_applicable": 0,
            "eligible_draws": 0,
            "complete_eligible_draws": 0,
            "changed_eligible_draws": 0,
        }
        for source_row in sources():
            source_id = str(source_row["source_id"])
            baseline = by_key[("baseline", source_id)]
            candidate = by_key[(arm, source_id)]
            audit = candidate.get("r17_request_audit") or {}
            if not audit.get("pass"):
                request_audit_failures.append(source_id)
            for key in request_counts:
                request_counts[key] += int((audit.get("counts") or {}).get(key, 0))
            paired.append(
                {
                    **dict(source_row),
                    "candidate_id": candidate_id,
                    "baseline_first_table_score": focal_score(baseline["tables"][0]),
                    "candidate_first_table_score": focal_score(candidate["tables"][0]),
                    "first_table_delta": (
                        focal_score(candidate["tables"][0])
                        - focal_score(baseline["tables"][0])
                    ),
                    "baseline_stage_score": baseline["focal_stage_score"],
                    "candidate_stage_score": candidate["focal_stage_score"],
                    "stage_score_delta": (
                        candidate["focal_stage_score"] - baseline["focal_stage_score"]
                    ),
                    "u_delta_low": candidate["u_low"] - baseline["u_high"],
                    "u_delta_high": candidate["u_high"] - baseline["u_low"],
                    "candidate_unresolved": candidate["unresolved"],
                    "baseline_unresolved": baseline["unresolved"],
                    "candidate_fourth": fourth(candidate),
                    "baseline_fourth": fourth(baseline),
                }
            )
        overall = summarize(paired)
        by_mix = {
            mix: summarize([row for row in paired if row["mix"] == mix])
            for mix in MIXES
        }
        positive = [row for row in paired if row["u_delta_low"] > 0]
        gate_checks = {
            "simulation_execution_failures": bool(
                simulation_audit["zero_internal_failures_verified"]
            ),
            "r17_request_audit_failures": not request_audit_failures,
            "all_eligible_draws_complete": (
                request_counts["complete_eligible_draws"]
                == request_counts["eligible_draws"]
            ),
            "overall_u_delta_low_mean": overall["u_delta_low_mean"] > 0,
            "each_mix_u_delta_low_mean": all(
                by_mix[mix]["u_delta_low_mean"] >= 0 for mix in MIXES
            ),
            "at_least_one_mix_u_delta_low_mean": any(
                by_mix[mix]["u_delta_low_mean"] > 0 for mix in MIXES
            ),
            "positive_u_units_distinct_roots": len(
                {row["root_index"] for row in positive}
            )
            >= 2,
            "positive_u_units_distinct_seats": len(
                {row["focal_seat"] for row in positive}
            )
            >= 2,
        }
        passed = all(gate_checks.values())
        candidate_results.append(
            {
                "candidate_id": candidate_id,
                "candidate_identity": manifest["candidates"][candidate_id]["identity"],
                "candidate_sha256": manifest["candidates"][candidate_id]["sha256"],
                "status": (
                    "PASS_R17_GENERATION1_DEVELOPMENT_GATE"
                    if passed
                    else "FAIL_R17_GENERATION1_DEVELOPMENT_GATE"
                ),
                "overall": overall,
                "by_mix": by_mix,
                "positive_u_units": len(positive),
                "positive_u_distinct_roots": sorted(
                    {row["root_index"] for row in positive}
                ),
                "positive_u_distinct_seats": sorted(
                    {row["focal_seat"] for row in positive}
                ),
                "request_audit_counts": request_counts,
                "request_audit_failure_sources": request_audit_failures,
                "gate_checks": gate_checks,
            }
        )
        all_paired[candidate_id] = paired
    passed_ids = [
        row["candidate_id"]
        for row in candidate_results
        if row["status"] == "PASS_R17_GENERATION1_DEVELOPMENT_GATE"
    ]
    result = {
        "schema": "r17-generation1-effect-result/1",
        "status": (
            "PASS_SOME_R17_GENERATION1_DEVELOPMENT_GATE"
            if passed_ids
            else "FAIL_ALL_R17_GENERATION1_DEVELOPMENT_GATE"
        ),
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "candidates": candidate_results,
        "passed_candidate_ids": passed_ids,
        "simulation_execution_audit": simulation_audit,
        "strength_claim": False,
        "confirmation_eligible": False,
        "next": (
            "按冻结选择键保留至多一个，以同一源码进入第二套全新开发来源"
            if passed_ids
            else "两个首代结构种子均失败；停止追加效果样本并执行文献与杭麻规则复盘"
        ),
    }
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "paired-units.json"),
        {"schema": "r17-generation1-paired/1", "by_candidate": all_paired},
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "analyze"))
    args = parser.parse_args()
    globals()[args.operation]()
