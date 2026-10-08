"""R18 P69：非财神建爆头候选相对 P47 的 1024 桌独立确认。"""

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
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_p66b_nonwhite_baotou_candidate_preflight as p66b  # noqa: E402
import r18_p67_nonwhite_baotou_blind_replication as p67  # noqa: E402
import r18_p68_nonwhite_baotou_table_safety_screen as p68  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p69-nonwhite-baotou-table-confirmation-01-20260923')
CONTRACT = p68.CONTRACT
CANDIDATE = p66b.CANDIDATE
PREFLIGHT = p66b.OUT / "result.json"
REPLICATION = p67.OUT / "result.json"
SCREEN = p68.OUT / "result.json"
PARENT = p66b.PARENT
TRACE_KEY = p66b.TRACE_KEY
PANEL_SEED = 2026102305
MIXES = ("H", "M")
ROOTS = tuple(range(1, 33))
SEATS = (0, 1, 2, 3)
ARMS = ("parent", "candidate")
SOURCE_UNITS = len(MIXES) * len(ROOTS) * len(SEATS)
INDEPENDENT_ROOTS = len(MIXES) * len(ROOTS)
PLANNED_TABLES = SOURCE_UNITS * len(ARMS) * 2
LIMITS = ValueAnalysisLimits()
WORKERS = 8
BOOTSTRAP_REPLICATES = 20_000
MIN_TRIGGERED_SOURCE_UNITS = 64
MIN_TRIGGERED_SOURCE_UNITS_PER_MIX = 24


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
    """冻结 H/M 各 32 根、四个焦点座位的确认来源单元。"""

    return [
        {
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "source_id": f"{mix}:p69:r{root:02d}:s{seat}",
        }
        for mix in MIXES for root in ROOTS for seat in SEATS
    ]


def stage_path(arm: str, source: Mapping[str, Any]) -> Path:
    """返回一个来源单元、一个策略臂的冻结结果路径。"""

    return _project_file(_PROJECT_ROOT, OUT / "stages" / (
        arm + "-" + str(source["source_id"]).replace(":", "-") + ".json"
    ))


def bootstrap_mean_interval(values: list[float]) -> tuple[float, float]:
    """按对手组合×牌山根的聚类均值重采样，返回冻结 95% 区间。"""

    if not values:
        raise ValueError("bootstrap 需要非空配对差值")
    rng = random.Random(PANEL_SEED + 999_999)
    means = []
    size = len(values)
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(sum(values[rng.randrange(size)] for _ in range(size)) / size)
    means.sort()
    return (
        means[int(0.025 * (len(means) - 1))],
        means[int(0.975 * (len(means) - 1))],
    )


def prepare() -> None:
    """在执行前冻结候选身份、全新来源和完整桌非劣判据。"""

    if OUT.exists():
        raise SystemExit("P69 目录已存在；拒绝覆盖")
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    replication = json.loads(REPLICATION.read_text(encoding="utf-8"))
    screen = json.loads(SCREEN.read_text(encoding="utf-8"))
    if (
        preflight.get("status") != "PASS_P66B_NONWEALTH_BAOTOU_CANDIDATE_PREFLIGHT"
        or preflight.get("candidate_sha256") != digest(CANDIDATE)
    ):
        raise ValueError("P65 候选未以当前身份通过 P66B 预检")
    if not (
        replication.get("status") == "PASS_P67_NONWEALTH_BAOTOU_BLIND_REPLICATION"
        and replication.get("passes_replication_gate") is True
        and replication.get("candidate_sha256") == digest(CANDIDATE)
        and replication.get("decision") == "OPEN_P68_TABLE_SAFETY"
    ):
        raise ValueError("P67 隐藏复验未通过")
    if not (
        screen.get("status") == "PASS_P68_NONWEALTH_BAOTOU_TABLE_SAFETY_SCREEN"
        and screen.get("selection_eligible") is True
        and screen.get("candidate_sha256") == digest(CANDIDATE)
        and screen.get("parent_sha256") == digest(PARENT)
    ):
        raise ValueError("P68 256桌安全屏未通过")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "stages")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p69-nonwhite-baotou-table-confirmation-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": (
            "P67已通过盲态因果复验；P68已通过256桌安全屏并观察到60次自然触发"
        ),
        "scope": (
            "P65相对P47；全新H/M各32根、四座位、候选/父代两臂、"
            "每阶段两桌；默认ValueAnalysisLimits同墙换座，共1024桌"
        ),
        "max_model_calls": 0,
        "confirmation_roots": INDEPENDENT_ROOTS,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {
        "schema": "r18-p69-nonwhite-baotou-table-confirmation-sources/1",
        "sources": sources(),
    })
    tracked = [
        Path(__file__), Path(natural.__file__), CONTRACT, CANDIDATE, PREFLIGHT,
        REPLICATION, SCREEN, Path(p66b.__file__), Path(p67.__file__), Path(p68.__file__),
        p66b.OUT / "manifest.json", p67.OUT / "manifest.json", p68.OUT / "manifest.json",
        PARENT, _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "sources.json"),
    ]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p69-nonwhite-baotou-table-confirmation-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "candidate_path": str(CANDIDATE),
        "candidate_sha256": digest(CANDIDATE),
        "parent_path": str(PARENT),
        "parent_sha256": digest(PARENT),
        "preflight_path": str(PREFLIGHT),
        "preflight_sha256": digest(PREFLIGHT),
        "replication_path": str(REPLICATION),
        "replication_sha256": digest(REPLICATION),
        "screen_path": str(SCREEN),
        "screen_sha256": digest(SCREEN),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "source_units": SOURCE_UNITS,
        "independent_root_clusters": INDEPENDENT_ROOTS,
        "arms": list(ARMS),
        "tables_per_stage": 2,
        "planned_tables": PLANNED_TABLES,
        "workers": WORKERS,
        "value_analysis_limits": {
            "max_expansions": LIMITS.max_expansions,
            "max_routes_per_candidate": LIMITS.max_routes_per_candidate,
        },
        "source_relation": (
            "全新panel_seed；不复用P63/P64/P64B/P67机会世界或P68安全屏牌山"
        ),
        "gate": {
            "all_tables_complete": True,
            "zero_internal_failures": True,
            "all_candidate_requests_action_value_scored": True,
            "candidate_request_errors": 0,
            "new_trigger_consistency": "新覆盖触发请求数等于顶层动作变更请求数",
            "exposure_sufficiency": "触发来源单元>=64，且H/M各>=24",
            "paired_effect": (
                "配对阶段积分均值>0；按H/M×牌山根聚类的bootstrap 95%下界>0；H/M各自均值>0"
            ),
        },
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "statistical_unit": "opponent_mix×root_index；四个焦点座位先在根内取均值",
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "P69_PREPARED",
        "source_units": SOURCE_UNITS,
        "planned_tables": PLANNED_TABLES,
    }, ensure_ascii=False, indent=2))


def verify() -> dict[str, Any]:
    """核对候选、父代、预检、合同、运行实现和来源均未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "candidate": (manifest["candidate_sha256"], digest(CANDIDATE)),
        "parent": (manifest["parent_sha256"], digest(PARENT)),
        "preflight": (manifest["preflight_sha256"], digest(PREFLIGHT)),
        "replication": (manifest["replication_sha256"], digest(REPLICATION)),
        "screen": (manifest["screen_sha256"], digest(SCREEN)),
        "contract": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError("P69 " + label + " 漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    if frozen != sources():
        raise ValueError("P69 来源清单漂移")
    return manifest


async def audit_requests(
    requests: list[Any], candidate_source: str, parent_source: str
) -> dict[str, Any]:
    """经正式策略接缝复算每个候选请求，并审计新覆盖的自然触发。"""

    candidate = ActionValuePolicy(ActionValueScorer("r18-P69-audit", candidate_source))
    parent = ActionValuePolicy(ActionValueScorer("r18-P69-parent-audit", parent_source))
    counts = Counter()
    problems = []
    for request in requests:
        counts["requests"] += 1
        budget = DecisionBudget(810.0, 820.0, 830.0)
        try:
            candidate_plan = await candidate.choose(request, budget)
            parent_plan = await parent.choose(request, budget)
        except Exception as exc:  # noqa: BLE001 - 保留策略异常证据
            counts["policy_errors"] += 1
            problems.append(type(exc).__name__ + ": " + str(exc)[:240])
            continue
        if candidate_plan.candidates[0].action_key != parent_plan.candidates[0].action_key:
            counts["changed_top_actions"] += 1
        overlays = []
        for item in candidate_plan.candidates:
            detail = ((item.score_trace or {}).get("detail") or {})
            overlay = detail.get(TRACE_KEY)
            if isinstance(overlay, Mapping):
                overlays.append(overlay)
        if overlays:
            counts["new_overlay_present"] += 1
        if any(row.get("triggered") is True for row in overlays):
            counts["new_overlay_triggered"] += 1
    return {"counts": dict(counts), "problems": problems}


def execute_stage(arm: str, source: Mapping[str, Any]) -> dict[str, Any]:
    """运行一个来源单元的候选臂或父代臂。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source["mix"]),
        root_index=int(source["root_index"]),
        focal_seat=int(source["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    candidate_source = CANDIDATE.read_text(encoding="utf-8")
    parent_source = PARENT.read_text(encoding="utf-8")
    scorer = ActionValueScorer(
        "r18-P69-table-" + arm,
        candidate_source if arm == "candidate" else parent_source,
    )
    requests: list[Any] = []
    stage = natural.run_arm_stage(
        arm="candidate",
        plans=plans,
        candidate_scorer=scorer,
        opponent_policies=contract["panel"]["opponent_scenarios"][
            str(source["mix"])
        ]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=LIMITS,
        decision_observer=requests.append if arm == "candidate" else None,
    )
    request_audit = None
    if arm == "candidate" and stage.get("status") == "complete":
        request_audit = asyncio.run(
            audit_requests(requests, candidate_source, parent_source)
        )
        if request_audit["counts"].get("policy_errors", 0):
            stage["status"] = "error"
            stage["usable"] = False
            stage["error"] = "P65/P47 请求复算存在策略异常"
    return {
        "arm": arm,
        "source": dict(source),
        "stage": stage,
        "request_audit": request_audit,
    }


def run() -> None:
    """并行执行全部同墙换座来源单元。"""

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
                if row.get("stage", {}).get("status") != "complete":
                    raise ValueError("既有 P69 阶段不完整：" + str(path))
                completed_tables += len(row["stage"].get("tables") or [])
            else:
                pending.append((arm, source))
    reservation = ledger.reserve(
        step_id="r18:p69:nonwealth-baotou-table-confirmation",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="P65非财神建爆头候选相对P47的全新默认配置1024桌独立确认",
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
                        raise RuntimeError(row["stage"].get("error") or "阶段不完整")
                    write_json(stage_path(arm, source), row)
                    completed_tables += count
                    if completed_tables % 128 == 0 or completed_tables == PLANNED_TABLES:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": PLANNED_TABLES,
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001 - 批次保留完整失败证据
                    if row is None:
                        usage_unknown = True
                    failures.append({
                        "arm": arm,
                        "source_id": source["source_id"],
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按本次返回完整桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "stages")).glob("*.json"))
    actual = sum(
        len(json.loads(path.read_text(encoding="utf-8"))["stage"].get("tables") or [])
        for path in files
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p69-nonwhite-baotou-table-confirmation-run/1",
        "stage_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != SOURCE_UNITS * len(ARMS):
        raise RuntimeError("P69 完整桌安全门执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def analyze() -> None:
    """分析配对积分、自然触发与正式接缝可靠性。"""

    manifest = verify()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary.get("failures") or run_summary.get("actual_tables") != PLANNED_TABLES:
        raise ValueError("P69 执行不完整，拒绝分析")
    all_tables = []
    candidate_tables = []
    paired = []
    audit_counts = Counter()
    audit_problems = []
    for source in sources():
        parent = json.loads(stage_path("parent", source).read_text(encoding="utf-8"))["stage"]
        candidate_doc = json.loads(
            stage_path("candidate", source).read_text(encoding="utf-8")
        )
        candidate = candidate_doc["stage"]
        all_tables.extend(parent["tables"])
        all_tables.extend(candidate["tables"])
        candidate_tables.extend(candidate["tables"])
        audit = candidate_doc.get("request_audit") or {}
        source_audit_counts = Counter(audit.get("counts") or {})
        audit_counts.update(source_audit_counts)
        audit_problems.extend(audit.get("problems") or [])
        paired.append({
            **source,
            "parent_stage_score": parent["focal_stage_score"],
            "candidate_stage_score": candidate["focal_stage_score"],
            "stage_score_delta": candidate["focal_stage_score"] - parent["focal_stage_score"],
            "u_delta_low": candidate["u_low"] - parent["u_high"],
            "u_delta_high": candidate["u_high"] - parent["u_low"],
            "score_trajectory_equal": [
                table["scores_by_seat"] for table in candidate["tables"]
            ] == [table["scores_by_seat"] for table in parent["tables"]],
            "candidate_requests": int(source_audit_counts["requests"]),
            "new_overlay_triggered_requests": int(
                source_audit_counts["new_overlay_triggered"]
            ),
            "changed_top_action_requests": int(
                source_audit_counts["changed_top_actions"]
            ),
        })
    execution = natural.execution_audit.review_tables(all_tables)
    candidate_execution = natural.execution_audit.review_tables(candidate_tables)
    recorded = execution["recorded_counts"]
    candidate_recorded = candidate_execution["recorded_counts"]
    failure_windows = sum(int(recorded[key]) for key in (
        "action_value_failed", "ambiguous_diagnostics", "unclassified_action_value",
    ))
    deltas = [int(row["stage_score_delta"]) for row in paired]
    root_clusters = []
    for mix in MIXES:
        for root in ROOTS:
            members = [
                row for row in paired
                if row["mix"] == mix and row["root_index"] == root
            ]
            if len(members) != len(SEATS):
                raise ValueError("P69 根内四个焦点座位不完整")
            root_clusters.append({
                "mix": mix,
                "root_index": root,
                "source_units": len(members),
                "stage_score_delta_mean": statistics.fmean(
                    row["stage_score_delta"] for row in members
                ),
                "triggered_source_units": sum(
                    row["new_overlay_triggered_requests"] > 0 for row in members
                ),
                "triggered_requests": sum(
                    row["new_overlay_triggered_requests"] for row in members
                ),
            })
    cluster_values = [row["stage_score_delta_mean"] for row in root_clusters]
    mean_delta = statistics.fmean(cluster_values)
    interval = bootstrap_mean_interval(cluster_values)
    new_triggers = int(audit_counts["new_overlay_triggered"])
    changed_top_actions = int(audit_counts["changed_top_actions"])
    exact_units = sum(row["score_trajectory_equal"] for row in paired)
    by_mix = {
        mix: {
            "units": sum(row["mix"] == mix for row in paired),
            "stage_score_delta_mean": statistics.fmean(
                row["stage_score_delta"] for row in paired if row["mix"] == mix
            ),
            "negative_units": sum(
                row["stage_score_delta"] < 0 for row in paired if row["mix"] == mix
            ),
            "triggered_requests": sum(
                row["new_overlay_triggered_requests"]
                for row in paired if row["mix"] == mix
            ),
            "triggered_source_units": sum(
                row["new_overlay_triggered_requests"] > 0
                for row in paired if row["mix"] == mix
            ),
        }
        for mix in MIXES
    }
    mechanics = {
        "all_tables_complete": run_summary["actual_tables"] == PLANNED_TABLES,
        "zero_internal_failures": execution["zero_internal_failures_verified"] is True,
        "candidate_request_errors": audit_counts["policy_errors"] == 0,
        "all_candidate_requests_action_value_scored": (
            candidate_recorded["action_value_scored"] == audit_counts["requests"]
        ),
        "zero_action_value_failure_windows": failure_windows == 0,
        "new_overlay_trace_present_on_all_requests": (
            audit_counts["new_overlay_present"] == audit_counts["requests"]
        ),
        "new_trigger_matches_changed_top_action": new_triggers == changed_top_actions,
    }
    triggered_source_units = sum(
        row["new_overlay_triggered_requests"] > 0 for row in paired
    )
    exposure_sufficient = bool(
        triggered_source_units >= MIN_TRIGGERED_SOURCE_UNITS
        and min(row["triggered_source_units"] for row in by_mix.values())
        >= MIN_TRIGGERED_SOURCE_UNITS_PER_MIX
    )
    paired_effect_confirmed = bool(
        mean_delta > 0.0
        and interval[0] > 0.0
        and min(row["stage_score_delta_mean"] for row in by_mix.values()) > 0.0
    )
    checks = {
        **mechanics,
        "natural_exposure_sufficient": exposure_sufficient,
        "cluster_paired_effect_confirmed": paired_effect_confirmed,
    }
    mechanics_passed = all(mechanics.values())
    passed = mechanics_passed and exposure_sufficient and paired_effect_confirmed
    if not mechanics_passed:
        status = "FAIL_P69_NONWEALTH_BAOTOU_TABLE_CONFIRMATION_MECHANICS"
        decision = "REJECT_P65_TABLE_CONFIRMATION_MECHANICS"
    elif not exposure_sufficient:
        status = "INCONCLUSIVE_P69_NONWEALTH_BAOTOU_TABLE_EXPOSURE"
        decision = "HOLD_P65_FOR_EXPOSURE_TOPUP"
    elif paired_effect_confirmed:
        status = "PASS_P69_NONWEALTH_BAOTOU_TABLE_CONFIRMATION"
        decision = "OPEN_P70_INTEGRATED_PARENT_PREFLIGHT"
    else:
        status = "FAIL_P69_NONWEALTH_BAOTOU_TABLE_CONFIRMATION_EFFECT"
        decision = "REJECT_P65_AFTER_TABLE_CONFIRMATION"
    result = {
        "schema": "r18-p69-nonwhite-baotou-table-confirmation-result/1",
        "status": status,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "candidate_sha256": manifest["candidate_sha256"],
        "parent_sha256": manifest["parent_sha256"],
        "tables": PLANNED_TABLES,
        "source_units": SOURCE_UNITS,
        "independent_root_clusters": len(root_clusters),
        "overall": {
            "stage_score_delta_mean": mean_delta,
            "root_cluster_bootstrap_mean_95_interval": list(interval),
            "statistical_unit": "opponent_mix×root_index",
            "negative_units": sum(value < 0 for value in deltas),
            "positive_units": sum(value > 0 for value in deltas),
            "zero_units": sum(value == 0 for value in deltas),
            "score_trajectory_equal_units": exact_units,
            "u_delta_low_mean": statistics.fmean(row["u_delta_low"] for row in paired),
            "u_delta_high_mean": statistics.fmean(row["u_delta_high"] for row in paired),
        },
        "by_mix": by_mix,
        "request_audit_counts": dict(audit_counts),
        "request_audit_problems": audit_problems,
        "execution_review": execution,
        "candidate_execution_review": candidate_execution,
        "action_value_failure_windows": failure_windows,
        "gate_checks": checks,
        "natural_exposure": {
            "new_overlay_triggered_requests": new_triggers,
            "changed_top_action_requests": changed_top_actions,
            "triggered_source_units": triggered_source_units,
            "minimum_triggered_source_units": MIN_TRIGGERED_SOURCE_UNITS,
            "minimum_triggered_source_units_per_mix": MIN_TRIGGERED_SOURCE_UNITS_PER_MIX,
        },
        "root_clusters": root_clusters,
        "decision": decision,
        "selection_eligible": passed,
        "active_research_parent": False,
        "release_eligible": False,
        "next": (
            "执行P70累计能力全链预检与活动研究父代注册；在P70通过前继续保持P47"
            if passed else
            ("增加全新暴露根，不改阈值或候选源码"
             if status.startswith("INCONCLUSIVE") else
             "停止P65晋级；定位全桌负面传导或正式接缝回归")
        ),
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "paired-units.json"), {
        "schema": "r18-p69-nonwhite-baotou-table-confirmation-paired/1", "rows": paired,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not passed:
        raise RuntimeError("P69 非财神建爆头候选完整桌确认未通过：" + status)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "analyze"))
    globals()[parser.parse_args().operation]()
