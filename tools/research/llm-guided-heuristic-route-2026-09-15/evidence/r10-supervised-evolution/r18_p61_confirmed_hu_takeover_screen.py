"""R18 P61：严格胡牌机会接管相对 P47 的 256 桌开发筛选。"""

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
from collections import Counter
import concurrent.futures
import hashlib
import json
from pathlib import Path
import random
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
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402
from hangma_bot.policy.protected_public_successor_policy import (  # noqa: E402
    ProtectedPublicSuccessorSearchPolicy,
    protected_trace_state,
)
from hangma_bot.policy.public_successor_leaf_executor import (  # noqa: E402
    LeafProgramExecutor,
)
from hangma_bot.policy.public_successor_search import (  # noqa: E402
    order_discard_keys_by_confirmed_hu_takeover,
    reduce_public_successors,
)
from hangma_bot.policy.r18_integrated_positive_v1 import (  # noqa: E402
    R18_INTEGRATED_POSITIVE_V1_SHA256,
    R18_INTEGRATED_POSITIVE_V1_SOURCE,
)


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p61-confirmed-hu-takeover-screen-01-20260923')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
P47 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p47-integrated-parent-registration-01-20260922/result.json')
P58 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p58-guarded-successor-confirmation-01-20260923/result.json')
P60 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p60-confirmed-hu-takeover-preflight-01-20260923/result.json')
R17_REPRODUCTION = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-generation1-reproduction-01-20260922/result.json')
R17_SOURCE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r17-seed-author-b-sol-repair-01-20260921/candidate.py')
R17_SOURCE_SHA256 = "fb9764faa2a01ded3f8cea94eeee27d59929f014f1dcc0ffbd56380e5b1384a2"
R17_CANDIDATE_IDENTITY = (
    "73c2833da12f2844f69559d4ad6202c44fc4a1adc1b60e0b8b140c82590b4c37"
)
SPECIAL_TRACE_KEYS = (
    "r18_opportunity_overlay",
    "r18_gang_dominance_overlay",
    "r18_seven_pairs_value_overlay",
    "two_wealth_piao_keeps_baotou_cf",
)
PANEL_SEED = 2026121801
MIXES = ("H", "M")
ROOTS = tuple(range(1, 9))
SEATS = (0, 1, 2, 3)
ARMS = ("parent", "candidate")
SOURCE_UNITS = len(MIXES) * len(ROOTS) * len(SEATS)
PLANNED_TABLES = SOURCE_UNITS * len(ARMS) * 2
WORKERS = 8
BOOTSTRAP_REPLICATES = 20_000
LIMITS = ValueAnalysisLimits()


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


def sources() -> list[dict[str, Any]]:
    """冻结全新 H/M 各 8 根、四换座来源。"""

    return [
        {
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "source_id": f"{mix}:p61:r{root:02d}:s{seat}",
        }
        for mix in MIXES
        for root in ROOTS
        for seat in SEATS
    ]


def combination_identity() -> str:
    """绑定父代、叶程序、保护接缝与规则搜索实现。"""

    payload = {
        "schema": "r18-confirmed-hu-takeover-combination/1",
        "parent_source_sha256": R18_INTEGRATED_POSITIVE_V1_SHA256,
        "leaf_candidate_identity": R17_CANDIDATE_IDENTITY,
        "leaf_source_sha256": R17_SOURCE_SHA256,
        "protected_trace_keys": SPECIAL_TRACE_KEYS,
        "discard_orderer": "confirmed_hu_takeover/1",
        "modules": {
            "protected_policy": digest(
                _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/protected_public_successor_policy.py")
            ),
            "successor_search": digest(
                _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_search.py")
            ),
            "leaf_executor": digest(
                _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_leaf_executor.py")
            ),
            "value_analysis": digest(
                _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/hangma/value_analysis.py")
            ),
        },
    }
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def stage_path(arm: str, source: Mapping[str, Any]) -> Path:
    """返回一个来源单元、一个策略臂的结果路径。"""

    return _project_file(_PROJECT_ROOT, OUT / "stages" / (
        arm + "-" + str(source["source_id"]).replace(":", "-") + ".json"
    ))


def failed_stage_path(arm: str, source: Mapping[str, Any]) -> Path:
    """保留已执行但后置审计失败的阶段。"""

    return _project_file(_PROJECT_ROOT, OUT / "failed-stages" / (
        arm + "-" + str(source["source_id"]).replace(":", "-") + ".json"
    ))


def make_policy(arm: str, versions: Mapping[str, Any], monotonic):
    """按冻结版本装配 P47 父代或受保护组合候选。"""

    baseline = ActionValuePolicy(
        ActionValueScorer("r18-p61-parent", R18_INTEGRATED_POSITIVE_V1_SOURCE),
        value_limits=LIMITS,
    )
    if arm == "parent":
        return baseline
    rules = HangmaRules(
        RuleConfig(
            ruleset_version=str(versions["ruleset_version"]),
            base_score=int(versions["base_score"]),
            you_cai_bi_kao=bool(versions["you_cai_bi_kao"]),
        )
    )
    return ProtectedPublicSuccessorSearchPolicy(
        rules.analyze_public_self_draw_successors,
        LeafProgramExecutor(R17_SOURCE.read_text(encoding="utf-8"), name="r18-p61-r17-b"),
        candidate_identity=R17_CANDIDATE_IDENTITY,
        baseline=baseline,
        protected_trace_keys=SPECIAL_TRACE_KEYS,
        monotonic=monotonic,
        orderer=order_discard_keys_by_confirmed_hu_takeover,
    )


async def audit_candidate_requests(requests: list[Any]) -> dict[str, Any]:
    """复算候选请求，核对专项保护、R17 完整归约与候选集合。"""

    baseline = ActionValuePolicy(
        ActionValueScorer("r18-p61-request-parent", R18_INTEGRATED_POSITIVE_V1_SOURCE),
        value_limits=LIMITS,
    )
    leaf = LeafProgramExecutor(
        R17_SOURCE.read_text(encoding="utf-8"), name="r18-p61-request-r17-b"
    )
    rules_cache: dict[str, HangmaRules] = {}
    candidate_cache: dict[str, ProtectedPublicSuccessorSearchPolicy] = {}
    budget = DecisionBudget(10.0, 20.0, 30.0)
    counts = Counter()
    failures: list[dict[str, Any]] = []
    max_leaf_evaluations = 0
    max_candidate_operations = 0
    for request in requests:
        counts["requests"] += 1
        base_plan = await baseline.choose(request, budget)
        if any("action_value_failed" in reason for reason in base_plan.degraded_reasons):
            counts["action_value_failures"] += 1
            continue
        version = request.rules.ruleset_version
        rules = rules_cache.setdefault(
            version, HangmaRules(RuleConfig(version, 1, False))
        )
        candidate = candidate_cache.get(version)
        if candidate is None:
            candidate = ProtectedPublicSuccessorSearchPolicy(
                rules.analyze_public_self_draw_successors,
                LeafProgramExecutor(
                    R17_SOURCE.read_text(encoding="utf-8"),
                    name="r18-p61-request-plan-r17-b",
                ),
                candidate_identity=R17_CANDIDATE_IDENTITY,
                baseline=baseline,
                protected_trace_keys=SPECIAL_TRACE_KEYS,
                monotonic=lambda: 0.0,
                orderer=order_discard_keys_by_confirmed_hu_takeover,
            )
            candidate_cache[version] = candidate
        actual_plan = await candidate.choose(request, budget)
        base_all_keys = tuple(item.action_key for item in base_plan.candidates)
        actual_all_keys = tuple(item.action_key for item in actual_plan.candidates)
        if set(actual_all_keys) != set(base_all_keys):
            counts["candidate_key_set_failures"] += 1
        protected, keys = protected_trace_state(base_plan, SPECIAL_TRACE_KEYS)
        if protected:
            counts["protected_plans"] += 1
            for key in keys:
                counts["protected:" + key] += 1
            if actual_plan != base_plan:
                counts["protected_plan_mismatches"] += 1
            continue
        if request.observation.phase != "draw":
            if actual_plan == base_plan:
                counts["response_exact_plans"] += 1
            else:
                counts["response_plan_mismatches"] += 1
            continue
        baseline_keys = tuple(
            item.action_key
            for item in base_plan.candidates
            if item.action_key.startswith("discard:")
        )
        if len(baseline_keys) < 2:
            counts["draw_not_applicable"] += 1
            continue
        counts["eligible_ordinary_draws"] += 1
        successors = rules.analyze_public_self_draw_successors(request.observation)
        scorer = leaf.window_scorer()
        reduction = reduce_public_successors(request, successors, scorer)
        max_leaf_evaluations = max(
            max_leaf_evaluations,
            sum(item.leaf_evaluations for item in reduction.roots),
        )
        max_candidate_operations = max(max_candidate_operations, scorer.operation_count)
        if not reduction.complete:
            failures.append(
                {"decision_id": request.decision_id, "reason": reduction.reason}
            )
            continue
        counts["complete_ordinary_draws"] += 1
        ordered = order_discard_keys_by_confirmed_hu_takeover(
            reduction, baseline_keys
        )
        if set(ordered) != set(baseline_keys):
            counts["candidate_key_set_failures"] += 1
        actual_discard_keys = tuple(
            item.action_key
            for item in actual_plan.candidates
            if item.action_key.startswith("discard:")
        )
        if actual_discard_keys != ordered:
            counts["ordinary_order_mismatches"] += 1
        if ordered != baseline_keys:
            counts["changed_ordinary_draws"] += 1
    return {
        "schema": "r18-p61-request-audit/1",
        "counts": dict(counts),
        "workload": {
            "max_leaf_evaluations": max_leaf_evaluations,
            "max_candidate_operations": max_candidate_operations,
        },
        "failures": failures,
        "pass": (
            not failures
            and counts["action_value_failures"] == 0
            and counts["candidate_key_set_failures"] == 0
            and counts["protected_plan_mismatches"] == 0
            and counts["response_plan_mismatches"] == 0
            and counts["ordinary_order_mismatches"] == 0
            and counts["complete_ordinary_draws"]
            == counts["eligible_ordinary_draws"]
        ),
    }


def execute_stage(arm: str, source: Mapping[str, Any]) -> dict[str, Any]:
    """运行一个完整两桌来源；候选臂额外复算组合边界。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    versions = natural.stage.contract_versions_block(contract)
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source["mix"]),
        root_index=int(source["root_index"]),
        focal_seat=int(source["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    requests: list[Any] = []

    def factory(monotonic):
        return make_policy(arm, versions, monotonic)

    stage = natural.run_arm_stage(
        arm="candidate",
        plans=plans,
        candidate_scorer=None,
        opponent_policies=contract["panel"]["opponent_scenarios"][
            str(source["mix"])
        ]["opponent_policies"],
        versions_block=versions,
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=LIMITS,
        decision_observer=requests.append if arm == "candidate" else None,
        candidate_policy_factory=factory,
    )
    stage["arm"] = arm
    request_audit = None
    if arm == "candidate" and stage.get("status") == "complete":
        request_audit = asyncio.run(audit_candidate_requests(requests))
        if not request_audit["pass"]:
            stage["status"] = "error"
            stage["usable"] = False
            stage["error"] = "P61 候选请求审计失败"
    return {
        "arm": arm,
        "source": dict(source),
        "stage": stage,
        "request_audit": request_audit,
    }


def prepare() -> None:
    """结果揭示前冻结组合身份、全新来源和开发筛选门槛。"""

    if OUT.exists():
        raise SystemExit("P61 目录已存在；拒绝覆盖")
    p47 = json.loads(P47.read_text(encoding="utf-8"))
    p58 = json.loads(P58.read_text(encoding="utf-8"))
    p60 = json.loads(P60.read_text(encoding="utf-8"))
    r17 = json.loads(R17_REPRODUCTION.read_text(encoding="utf-8"))
    checks = {
        "p47_passed": p47.get("status")
        == "PASS_P47_INTEGRATED_PARENT_REGISTRATION",
        "p47_identity_exact": p47.get("candidate_sha256")
        == R18_INTEGRATED_POSITIVE_V1_SHA256,
        "r17_b_selected": r17.get("selected_candidate", {}).get(
            "candidate_identity"
        )
        == R17_CANDIDATE_IDENTITY,
        "r17_source_exact": digest(R17_SOURCE) == R17_SOURCE_SHA256,
        "p58_broad_reorder_rejected": (
            p58.get("status") == "FAIL_P58_GUARDED_SUCCESSOR_CONFIRMATION"
            and p58.get("selection_eligible") is False
        ),
        "p60_strict_takeover_preflight_passed": p60.get("status")
        == "PASS_P60_CONFIRMED_HU_TAKEOVER_PREFLIGHT",
    }
    if not all(checks.values()):
        raise ValueError("P61 前置证据不成立：" + repr(checks))
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "stages")).mkdir()
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "sources.json"),
        {"schema": "r18-p61-screen-sources/1", "sources": sources()},
    )
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p61-confirmed-hu-takeover-screen-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update(
        {
            "issuance_basis": (
                "P47是活动研究父代；P58证明全局后继排序覆盖71.1%且负向，故已拒绝；"
                "P60在377个冻结请求上证明严格四项接管仅触发17/242，专项与响应完全保持"
            ),
            "scope": (
                "严格胡牌机会接管相对P47；全新H/M各8根、四换座、父代/候选双臂、"
                "每阶段完整两桌，共256桌；只作开发筛选，不主张强度"
            ),
            "max_model_calls": 0,
            "confirmation_roots": SOURCE_UNITS,
        }
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    tracked = [
        Path(__file__),
        Path(natural.__file__),
        CONTRACT,
        P47,
        P58,
        P60,
        R17_REPRODUCTION,
        R17_SOURCE,
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/protected_public_successor_policy.py"),
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_search.py"),
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/public_successor_leaf_executor.py"),
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/policy/r18_integrated_positive_v1.py"),
        _project_file(_PROJECT_ROOT, ROOT / "src/hangma_bot/hangma/value_analysis.py"),
        _project_file(_PROJECT_ROOT, OUT / "sources.json"),
        _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
    ]
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "manifest.json"),
        {
            "schema": "r18-p61-confirmed-hu-takeover-screen-manifest/1",
            "created_at_utc": search.utc_now(),
            "runtime": guard.capture(source_paths=tracked),
            "combination_identity": combination_identity(),
            "parent_source_sha256": R18_INTEGRATED_POSITIVE_V1_SHA256,
            "r17_candidate_identity": R17_CANDIDATE_IDENTITY,
            "r17_source_sha256": R17_SOURCE_SHA256,
            "protected_trace_keys": SPECIAL_TRACE_KEYS,
            "contract": str(CONTRACT),
            "contract_sha256": digest(CONTRACT),
            "p58_sha256": digest(P58),
            "p60_sha256": digest(P60),
            "panel_seed": PANEL_SEED,
            "source_relation": (
                "panel_seed与R17两套开发来源、P46安全门、P58确认批及全部机会题库不同；"
                "P61使用预登记的新panel_seed；P58只用于否决宽接管，P60只验证静态范围；"
                "本批结果未参与来源、门槛或候选构造"
            ),
            "mixes": MIXES,
            "root_indices": ROOTS,
            "focal_seats": SEATS,
            "source_units": SOURCE_UNITS,
            "arms": ARMS,
            "tables_per_stage": 2,
            "planned_tables": PLANNED_TABLES,
            "workers": WORKERS,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "gate": {
                "overall_stage_score_delta_mean": ">=0",
                "overall_u_delta_low_mean": ">=0",
                "each_mix_u_delta_low_mean": ">=-0.0625",
                "candidate_fourth_rate": "<=parent_fourth_rate",
                "positive_u_units_distinct_roots": ">=2",
                "positive_u_units_distinct_seats": ">=2",
                "all_protected_plans_exact_by_construction_and_audit": True,
                "all_ordinary_eligible_reductions_complete": True,
                "ordinary_changed_draws": ">0 and <=20% of eligible ordinary draws",
                "candidate_key_set_failures": 0,
                "simulation_internal_failures": 0,
            },
            "diagnostics_not_gates": (
                "stage_score_bootstrap_95_interval",
                "u_delta_low_bootstrap_intervals",
                "unresolved_rate",
                "policy_elapsed_ms",
            ),
            "strength_claim": False,
            "release_eligible": False,
        },
    )
    print(
        json.dumps(
            {
                "status": "P61_PREPARED",
                "combination_identity": combination_identity(),
                "source_units": SOURCE_UNITS,
                "planned_tables": PLANNED_TABLES,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def verify() -> dict[str, Any]:
    """验证预登记后所有语义输入保持不变。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["combination_identity"] != combination_identity():
        raise ValueError("P61 组合身份漂移")
    if manifest["contract_sha256"] != digest(CONTRACT):
        raise ValueError("P61 面板合同漂移")
    if manifest["p58_sha256"] != digest(P58):
        raise ValueError("P61 P58 前置结果漂移")
    if manifest["p60_sha256"] != digest(P60):
        raise ValueError("P61 P60 前置结果漂移")
    frozen_sources = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))[
        "sources"
    ]
    if frozen_sources != sources():
        raise ValueError("P61 来源漂移")
    guard.verify(manifest["runtime"])
    return manifest


def run() -> None:
    """可恢复地并行执行父代与组合候选的全部冻结阶段。"""

    manifest = verify()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for source in sources():
        for arm in ARMS:
            path = stage_path(arm, source)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if (
                    row.get("stage", {}).get("status") != "complete"
                    or len(row["stage"].get("tables") or []) != 2
                ):
                    raise RuntimeError("既有 P61 阶段不完整：" + str(path))
                completed_tables += 2
            else:
                pending.append((arm, source))
    preexisting = completed_tables
    reservation = ledger.reserve(
        step_id="r18:p61:confirmed-hu-takeover-screen",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="严格胡牌机会接管相对P47的256桌开发筛选",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {
                pool.submit(execute_stage, arm, source): (arm, source)
                for arm, source in pending
            }
            for future in concurrent.futures.as_completed(futures):
                arm, source = futures[future]
                row = None
                try:
                    row = future.result()
                    count = len(row.get("stage", {}).get("tables") or [])
                    executed += count
                    if row["stage"]["status"] != "complete" or count != 2:
                        write_json(failed_stage_path(arm, source), row)
                        raise RuntimeError(row["stage"].get("error") or "阶段不完整")
                    write_json(stage_path(arm, source), row)
                    completed_tables += count
                    if completed_tables % 64 == 0 or completed_tables == PLANNED_TABLES:
                        print(
                            json.dumps(
                                {
                                    "completed_tables": completed_tables,
                                    "planned_tables": PLANNED_TABLES,
                                },
                                ensure_ascii=False,
                            ),
                            flush=True,
                        )
                except Exception as exc:  # noqa: BLE001 - 保留完整失败证据
                    if row is None:
                        usage_unknown = True
                    failures.append(
                        {
                            "arm": arm,
                            "source_id": source["source_id"],
                            "error": type(exc).__name__ + ": " + str(exc),
                        }
                    )
    except BaseException:
        ledger.settle(
            reservation,
            usage_unknown=True,
            note="P61进程中断，实际执行桌数未知，按预留保守结算",
        )
        raise
    if usage_unknown:
        ledger.settle(reservation, usage_unknown=True, note="子进程未返回，保守结算")
    else:
        ledger.settle(reservation, actual=executed, note="按本次返回完整桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "stages")).glob("*.json"))
    actual = sum(
        len(json.loads(path.read_text(encoding="utf-8"))["stage"].get("tables") or [])
        for path in files
    )
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "run-summary.json"),
        {
            "schema": "r18-p61-confirmed-hu-takeover-screen-run/1",
            "stage_files": len(files),
            "actual_tables": actual,
            "preexisting_complete_tables": preexisting,
            "executed_tables_this_run": executed,
            "usage_unknown": usage_unknown,
            "failures": failures,
            "spent": ledger.account_summary(),
        },
    )
    if failures or actual != PLANNED_TABLES or len(files) != SOURCE_UNITS * len(ARMS):
        raise RuntimeError("P61 开发筛选执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def focal_score(table: Mapping[str, Any]) -> int:
    participants = table["stage_situation"]["participant_ids_by_seat"]
    seat = participants.index(natural.FOCAL_PARTICIPANT)
    return int(table["scores_by_seat"][seat])


def fourth(stage: Mapping[str, Any]) -> bool:
    interval = stage.get("u_interval") or {}
    return interval.get("a") == 4 and interval.get("b") == 4


def bootstrap_interval(values: list[float], *, salt: int) -> tuple[float, float, float]:
    """按来源单元配对重采样，返回单侧95%下界和双侧95%区间上界。"""

    rng = random.Random(PANEL_SEED + salt)
    size = len(values)
    means = sorted(
        statistics.fmean(values[rng.randrange(size)] for _ in range(size))
        for _ in range(BOOTSTRAP_REPLICATES)
    )
    return (
        means[int(0.05 * (len(means) - 1))],
        means[int(0.025 * (len(means) - 1))],
        means[int(0.975 * (len(means) - 1))],
    )


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "source_units": len(rows),
        "stage_score_delta_mean": statistics.fmean(
            row["stage_score_delta"] for row in rows
        ),
        "u_delta_low_mean": statistics.fmean(row["u_delta_low"] for row in rows),
        "u_delta_high_mean": statistics.fmean(row["u_delta_high"] for row in rows),
        "candidate_fourth_rate": statistics.fmean(row["candidate_fourth"] for row in rows),
        "parent_fourth_rate": statistics.fmean(row["parent_fourth"] for row in rows),
        "candidate_unresolved_rate": statistics.fmean(
            row["candidate_unresolved"] for row in rows
        ),
        "parent_unresolved_rate": statistics.fmean(
            row["parent_unresolved"] for row in rows
        ),
    }


def analyze() -> None:
    """按预登记方向性效果门和继承可靠性裁定是否进入独立确认。"""

    manifest = verify()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary.get("failures") or run_summary.get("actual_tables") != PLANNED_TABLES:
        raise ValueError("P61 执行不完整，拒绝分析")
    paired = []
    all_tables = []
    candidate_tables = []
    audit_counts = Counter()
    audit_failures = []
    for source in sources():
        parent = json.loads(stage_path("parent", source).read_text(encoding="utf-8"))[
            "stage"
        ]
        candidate_doc = json.loads(
            stage_path("candidate", source).read_text(encoding="utf-8")
        )
        candidate = candidate_doc["stage"]
        audit = candidate_doc.get("request_audit") or {}
        audit_counts.update(audit.get("counts") or {})
        if not audit.get("pass"):
            audit_failures.append(source["source_id"])
        all_tables.extend(parent["tables"])
        all_tables.extend(candidate["tables"])
        candidate_tables.extend(candidate["tables"])
        paired.append(
            {
                **source,
                "parent_first_table_score": focal_score(parent["tables"][0]),
                "candidate_first_table_score": focal_score(candidate["tables"][0]),
                "first_table_delta": focal_score(candidate["tables"][0])
                - focal_score(parent["tables"][0]),
                "parent_stage_score": parent["focal_stage_score"],
                "candidate_stage_score": candidate["focal_stage_score"],
                "stage_score_delta": candidate["focal_stage_score"]
                - parent["focal_stage_score"],
                "u_delta_low": candidate["u_low"] - parent["u_high"],
                "u_delta_high": candidate["u_high"] - parent["u_low"],
                "candidate_unresolved": candidate["unresolved"],
                "parent_unresolved": parent["unresolved"],
                "candidate_fourth": fourth(candidate),
                "parent_fourth": fourth(parent),
            }
        )
    execution = natural.execution_audit.review_tables(all_tables)
    candidate_execution = natural.execution_audit.review_tables(candidate_tables)
    overall = summarize(paired)
    by_mix = {
        mix: summarize([row for row in paired if row["mix"] == mix]) for mix in MIXES
    }
    u_low_values = [float(row["u_delta_low"]) for row in paired]
    score_values = [float(row["stage_score_delta"]) for row in paired]
    u_one_sided, u_two_low, u_two_high = bootstrap_interval(u_low_values, salt=1)
    _score_one_sided, score_low, score_high = bootstrap_interval(score_values, salt=2)
    positive = [row for row in paired if row["u_delta_low"] > 0]
    checks = {
        "all_tables_complete": run_summary["actual_tables"] == PLANNED_TABLES,
        "zero_internal_failures": execution["zero_internal_failures_verified"] is True,
        "candidate_zero_internal_failures": candidate_execution[
            "zero_internal_failures_verified"
        ]
        is True,
        "request_audit_failures_zero": not audit_failures,
        "all_ordinary_eligible_reductions_complete": audit_counts[
            "complete_ordinary_draws"
        ]
        == audit_counts["eligible_ordinary_draws"],
        "ordinary_changed_draws_positive": audit_counts["changed_ordinary_draws"] > 0,
        "ordinary_changed_draw_rate_bounded": audit_counts["changed_ordinary_draws"]
        <= 0.20 * audit_counts["eligible_ordinary_draws"],
        "candidate_key_set_failures_zero": audit_counts["candidate_key_set_failures"] == 0,
        "action_value_failures_zero": audit_counts["action_value_failures"] == 0,
        "protected_plan_mismatches_zero": audit_counts["protected_plan_mismatches"] == 0,
        "response_plan_mismatches_zero": audit_counts["response_plan_mismatches"] == 0,
        "ordinary_order_mismatches_zero": audit_counts["ordinary_order_mismatches"] == 0,
        "overall_stage_score_delta_mean_nonnegative": overall[
            "stage_score_delta_mean"
        ]
        >= 0.0,
        "overall_u_delta_low_mean_nonnegative": overall["u_delta_low_mean"] >= 0.0,
        "each_mix_u_delta_low_mean_not_strongly_negative": all(
            by_mix[mix]["u_delta_low_mean"] >= -0.0625 for mix in MIXES
        ),
        "candidate_fourth_rate_not_higher": overall["candidate_fourth_rate"]
        <= overall["parent_fourth_rate"],
        "positive_u_units_distinct_roots": len(
            {row["root_index"] for row in positive}
        )
        >= 2,
        "positive_u_units_distinct_seats": len(
            {row["focal_seat"] for row in positive}
        )
        >= 2,
    }
    passed = all(checks.values())
    result = {
        "schema": "r18-p61-confirmed-hu-takeover-screen-result/1",
        "status": (
            "PASS_P61_CONFIRMED_HU_TAKEOVER_SCREEN"
            if passed
            else "FAIL_P61_CONFIRMED_HU_TAKEOVER_SCREEN"
        ),
        "combination_identity": manifest["combination_identity"],
        "tables": PLANNED_TABLES,
        "source_units": SOURCE_UNITS,
        "overall": {
            **overall,
            "u_delta_low_bootstrap_one_sided_95_lower": u_one_sided,
            "u_delta_low_bootstrap_two_sided_95_interval": [u_two_low, u_two_high],
            "stage_score_bootstrap_two_sided_95_interval": [score_low, score_high],
            "positive_u_units": len(positive),
            "negative_u_units": sum(row["u_delta_high"] < 0 for row in paired),
        },
        "by_mix": by_mix,
        "positive_u_distinct_roots": sorted({row["root_index"] for row in positive}),
        "positive_u_distinct_seats": sorted({row["focal_seat"] for row in positive}),
        "request_audit_counts": dict(audit_counts),
        "request_audit_failure_sources": audit_failures,
        "execution_review": execution,
        "candidate_execution_review": candidate_execution,
        "gate_checks": checks,
        "strength_claim": False,
        "selection_eligible": False,
        "confirmation_eligible": passed,
        "active_research_parent": False,
        "release_eligible": False,
        "next": (
            "冻结同一组合，在另一全新来源运行1024桌独立确认"
            if passed
            else "保留P47；关闭当前严格接管定义并按失败分面复盘"
        ),
    }
    write_json(
        _project_file(_PROJECT_ROOT, OUT / "paired-units.json"),
        {"schema": "r18-p61-confirmed-hu-takeover-paired/1", "rows": paired},
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "analyze"))
    globals()[parser.parse_args().operation]()
