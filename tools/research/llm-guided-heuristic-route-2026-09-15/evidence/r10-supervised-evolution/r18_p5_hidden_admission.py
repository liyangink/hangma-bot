"""R18 P5 补杠严格支配候选的一次性新来源机会准入。"""

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
from collections import Counter
import concurrent.futures
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_gang_dominance_confirmation as predicate  # noqa: E402
import r18_p5_development_preflight as development  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p5-hidden-admission-01-20260922')
CANDIDATE = development.CANDIDATE
PARENT = development.PARENT
PREFLIGHT = development.OUT / "result.json"
CONTRACT = predicate.CONTRACT
PANEL_SEEDS = (2026100719, 2026100733)
EXCLUDED_SEEDS = (
    predicate.DISCOVERY_SEED,
    predicate.PANEL_SEED,
    2026100631,
    2026100643,
    2026100659,
    2026100671,
)
MIXES = predicate.MIXES
ROOTS = predicate.ROOTS
SEATS = predicate.SEATS
TABLES_PER_SOURCE = predicate.TABLES_PER_SOURCE
PLANNED_TABLES = (
    len(PANEL_SEEDS) * len(MIXES) * len(ROOTS) * len(SEATS) * TABLES_PER_SOURCE
)
LIMITS = ValueAnalysisLimits(max_expansions=20_000, max_routes_per_candidate=256)


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


def sources() -> list[dict[str, Any]]:
    """列出候选冻结后两个新种子的全部自然来源。"""

    return [
        {
            "panel_seed": seed,
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "source_id": f"s{seed}:{mix}:r{root:02d}:s{seat}",
            "source_root_id": natural.natural_root_id(mix, seed, root),
        }
        for seed in PANEL_SEEDS
        for mix in MIXES
        for root in ROOTS
        for seat in SEATS
    ]


def source_path(row: Mapping[str, Any]) -> Path:
    """一个来源的断点文件。"""

    return _project_file(_PROJECT_ROOT, OUT / "sources" / (str(row["source_id"]).replace(":", "-") + ".json"))


def prepare() -> None:
    """在生成新自然轨迹前冻结 P5 源码、父代、判据、样本空间和门槛。"""

    if OUT.exists():
        raise SystemExit("R18 P5 隐藏准入目录已存在；拒绝覆盖")
    if set(PANEL_SEEDS) & set(EXCLUDED_SEEDS) or len(set(PANEL_SEEDS)) != len(PANEL_SEEDS):
        raise ValueError("隐藏准入 panel_seed 必须全新且互不重复")
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if preflight.get("status") != "PASS_P5_DEVELOPMENT":
        raise ValueError("P5 开发预检未通过")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p5-hidden-admission-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P5机械候选开发预检通过；源码冻结后用全新自然来源一次性验收",
        "scope": "两个全新panel_seed，H/M各96根、四焦点座、每来源两桌；严格命中改良与非命中P3逐点保持",
        "max_model_calls": 0,
        "confirmation_roots": len(PANEL_SEEDS) * len(MIXES) * len(ROOTS),
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p5-hidden-admission-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=[
            Path(__file__), Path(predicate.__file__), Path(development.__file__),
            CANDIDATE, PARENT, PREFLIGHT, CONTRACT, _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
            Path(natural.__file__),
        ]),
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "preflight_sha256": digest(PREFLIGHT),
        "predicate_source_sha256": digest(Path(predicate.__file__)),
        "contract_sha256": digest(CONTRACT),
        "excluded_panel_seeds": list(EXCLUDED_SEEDS),
        "panel_seeds": list(PANEL_SEEDS),
        "mixes": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "sources": len(sources()),
        "tables_per_source": TABLES_PER_SOURCE,
        "planned_tables": PLANNED_TABLES,
        "workers": 12,
        "trajectory_policy": "stable weighted_heuristic_v2",
        "admission_gate": {
            "strict_states_min": 4,
            "strict_distinct_tables_min": 4,
            "strict_distinct_source_roots_min": 4,
            "strict_required_mixes": list(MIXES),
            "strict_selection_failures": 0,
            "nonstrict_score_or_choice_mismatches": 0,
            "mechanical_failures": 0,
        },
        "hidden_semantics": "候选源码与门槛先冻结；新牌山窗口只在执行后生成；未命中窗口必须逐点评分保持P3",
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED",
        "candidate_sha256": digest(CANDIDATE),
        "panel_seeds": list(PANEL_SEEDS),
        "tables": PLANNED_TABLES,
    }, ensure_ascii=False))


def verify_manifest() -> dict[str, Any]:
    """拒绝候选、父代、判据、预检、合同或执行代码漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "candidate": (manifest["candidate_sha256"], digest(CANDIDATE)),
        "parent": (manifest["parent_sha256"], digest(PARENT)),
        "preflight": (manifest["preflight_sha256"], digest(PREFLIGHT)),
        "predicate": (manifest["predicate_source_sha256"], digest(Path(predicate.__file__))),
        "contract": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + " 漂移")
    if set(manifest["panel_seeds"]) & set(manifest["excluded_panel_seeds"]):
        raise ValueError("隐藏准入错误复用既有 panel_seed")
    guard.verify(manifest["runtime"])
    return manifest


def _top_key(batch_result: Any) -> str:
    """按合同排序规则读取首选动作。"""

    return sorted(
        batch_result.entries, key=lambda item: (-item.score, item.action_key)
    )[0].action_key


def _score_map(batch_result: Any) -> dict[str, float]:
    """返回完整动作评分映射。"""

    return {item.action_key: item.score for item in batch_result.entries}


def audit_requests(requests: list[Any], source: Mapping[str, Any]) -> dict[str, Any]:
    """以独立规则判据标注杠窗口，再比较冻结 P5 与 P3 的完整评分。"""

    parent = ActionValueScorer(
        "r18-p5-hidden-parent", PARENT.read_text(encoding="utf-8")
    )
    candidate = ActionValueScorer(
        "r18-p5-hidden-candidate", CANDIDATE.read_text(encoding="utf-8")
    )
    counts: Counter[str] = Counter()
    windows = []
    problems = []
    max_operations = 0
    for request in requests:
        gang_candidates = [
            item for item in request.rules.legal_candidates
            if item.action_key.startswith("gang:")
        ]
        if not gang_candidates:
            continue
        independent = predicate.audit_requests([request], source)["windows"]
        view = build_scoring_view(request)
        try:
            parent_batch = parent.score(view)
            candidate_batch = candidate.score(view)
        except Exception as exc:  # noqa: BLE001 - 候选失败必须进入准入证据
            problems.append(type(exc).__name__ + ": " + str(exc)[:300])
            counts["scoring_failures"] += 1
            continue
        max_operations = max(max_operations, candidate.last_operation_count)
        parent_scores = _score_map(parent_batch)
        candidate_scores = _score_map(candidate_batch)
        parent_top = _top_key(parent_batch)
        candidate_top = _top_key(candidate_batch)
        trigger_records = {}
        for entry in candidate_batch.entries:
            record = entry.trace.get("r18_gang_dominance_overlay")
            if isinstance(record, dict) and record.get("triggered") is True:
                trigger_records[entry.action_key] = dict(record)
        strict_rows = [row for row in independent if row["strict_predicate"]]
        strict_keys = sorted(row["gang_action"] for row in strict_rows)
        expected_key = None
        if strict_rows:
            expected = sorted(
                strict_rows,
                key=lambda row: (
                    -row["routes"][0]["settlement"]["focal_score"],
                    row["gang_action"],
                ),
            )[0]
            expected_key = expected["gang_action"]
            counts["strict_windows"] += 1
            counts["strict_actions"] += len(strict_rows)
            if candidate_top != expected_key:
                counts["strict_selection_failures"] += 1
            if sorted(trigger_records) != strict_keys:
                counts["strict_trace_failures"] += 1
            for row in strict_rows:
                record = trigger_records.get(row["gang_action"])
                expected_gain = (
                    row["routes"][0]["settlement"]["focal_score"]
                    - row["immediate_hu_settlement"]["focal_score"]
                )
                if record is None or record.get("local_gain") != expected_gain:
                    counts["strict_trace_gain_failures"] += 1
        else:
            counts["nonstrict_windows"] += 1
            if candidate_scores != parent_scores:
                counts["nonstrict_score_mismatches"] += 1
            if candidate_top != parent_top:
                counts["nonstrict_choice_mismatches"] += 1
            if trigger_records:
                counts["nonstrict_trace_failures"] += 1
        windows.append({
            "source": dict(source),
            "game_id": request.observation.game_id,
            "round_no": request.observation.round_no,
            "snapshot_seq": request.observation.snapshot_seq,
            "window_key": independent[0]["window_key"],
            "strict_keys": strict_keys,
            "expected_key": expected_key,
            "parent_top": parent_top,
            "candidate_top": candidate_top,
            "trigger_keys": sorted(trigger_records),
            "same_scores_as_parent": candidate_scores == parent_scores,
            "candidate_operations": candidate.last_operation_count,
            "independent_rows": independent,
        })
    return {
        "counts": dict(sorted(counts.items())),
        "windows": windows,
        "problems": problems,
        "max_candidate_operations": max_operations,
    }


def execute_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """跑一个新来源的两桌稳定 V2 阶段，并在桌后盲评 P5/P3。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source["mix"]),
        root_index=int(source["root_index"]),
        focal_seat=int(source["focal_seat"]),
        panel_seed=int(source["panel_seed"]),
    )
    requests: list[Any] = []
    placeholder = ActionValueScorer(
        "r18-p5-hidden-unused", PARENT.read_text(encoding="utf-8")
    )
    stage_result = natural.run_arm_stage(
        arm="baseline",
        plans=plans,
        candidate_scorer=placeholder,
        opponent_policies=contract["panel"]["opponent_scenarios"][str(source["mix"])]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=LIMITS,
        decision_observer=requests.append,
    )
    completed_hands = sum(
        int(table.get("result", {}).get("completed_hands") or 0)
        for table in stage_result.get("tables") or []
    )
    runtime: Counter[str] = Counter()
    for table in stage_result.get("tables") or []:
        runtime.update(table.get("result", {}).get("runtime_counts") or {})
    return {
        "source": dict(source),
        "status": stage_result.get("status"),
        "error": stage_result.get("error"),
        "tables": len(stage_result.get("tables") or []),
        "completed_hands": completed_hands,
        "runtime_counts": dict(sorted(runtime.items())),
        "audit": audit_requests(requests, source),
    }


def run() -> None:
    """并行执行一次性隐藏来源，按来源断点续跑。"""

    manifest = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for row in sources():
        path = source_path(row)
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("status") != "complete" or saved.get("tables") != TABLES_PER_SOURCE:
                raise ValueError("既有隐藏来源不完整：" + str(path))
            completed_tables += TABLES_PER_SOURCE
        else:
            pending.append(row)
    reservation = ledger.reserve(
        step_id="r18:p5:hidden-admission",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="P5冻结后两个新panel_seed自然机会准入",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=int(manifest["workers"])) as pool:
            futures = {pool.submit(execute_source, row): row for row in pending}
            for future in concurrent.futures.as_completed(futures):
                row = futures[future]
                result = None
                try:
                    result = future.result()
                    if result["status"] != "complete" or result["tables"] != TABLES_PER_SOURCE:
                        raise RuntimeError(result.get("error") or "来源未跑满")
                    if result["audit"]["problems"]:
                        raise RuntimeError("P5/P3 评分出现异常")
                    write_json(source_path(row), result)
                    executed += TABLES_PER_SOURCE
                    completed_tables += TABLES_PER_SOURCE
                    if completed_tables % 256 == 0 or completed_tables == PLANNED_TABLES:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": PLANNED_TABLES,
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    if result is None:
                        usage_unknown = True
                    failures.append({
                        "source_id": row["source_id"],
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按完整返回桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "sources")).glob("*.json")) if (_project_file(_PROJECT_ROOT, OUT / "sources")).exists() else []
    actual = sum(json.loads(path.read_text(encoding="utf-8"))["tables"] for path in files)
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p5-hidden-admission-run/1",
        "source_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != len(sources()):
        raise RuntimeError("P5 隐藏准入执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def analyze() -> None:
    """按状态、桌、来源根与混合汇总一次性隐藏准入。"""

    manifest = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary["failures"] or run_summary["actual_tables"] != PLANNED_TABLES:
        raise ValueError("P5 隐藏准入运行不完整")
    counts: Counter[str] = Counter()
    runtime: Counter[str] = Counter()
    windows = []
    completed_hands = 0
    max_operations = 0
    for source in sources():
        document = json.loads(source_path(source).read_text(encoding="utf-8"))
        completed_hands += int(document["completed_hands"])
        counts.update(document["audit"]["counts"])
        runtime.update(document["runtime_counts"])
        max_operations = max(max_operations, int(document["audit"]["max_candidate_operations"]))
        windows.extend(document["audit"]["windows"])
    strict = [row for row in windows if row["strict_keys"]]
    strict_tables = {row["game_id"] for row in strict}
    strict_roots = {row["source"]["source_root_id"] for row in strict}
    strict_mixes = {row["source"]["mix"] for row in strict}
    gate = manifest["admission_gate"]
    mismatch_count = (
        counts["nonstrict_score_mismatches"]
        + counts["nonstrict_choice_mismatches"]
        + counts["nonstrict_trace_failures"]
    )
    strict_failure_count = (
        counts["strict_selection_failures"]
        + counts["strict_trace_failures"]
        + counts["strict_trace_gain_failures"]
    )
    local_gains = []
    for window in strict:
        for row in window["independent_rows"]:
            if row["strict_predicate"]:
                local_gains.append(
                    row["routes"][0]["settlement"]["focal_score"]
                    - row["immediate_hu_settlement"]["focal_score"]
                )
    gate_checks = {
        "strict_states_min": len(strict) >= int(gate["strict_states_min"]),
        "strict_distinct_tables_min": len(strict_tables) >= int(gate["strict_distinct_tables_min"]),
        "strict_distinct_source_roots_min": len(strict_roots) >= int(gate["strict_distinct_source_roots_min"]),
        "strict_required_mixes": strict_mixes == set(gate["strict_required_mixes"]),
        "strict_selection_failures_zero": strict_failure_count == 0,
        "nonstrict_mismatches_zero": mismatch_count == 0,
        "mechanical_failures_zero": not run_summary["failures"] and counts["scoring_failures"] == 0,
    }
    passed = all(gate_checks.values())
    result = {
        "schema": "r18-p5-hidden-admission-result/1",
        "status": "PASS_P5_HIDDEN" if passed else "FAIL_P5_HIDDEN",
        "candidate_sha256": digest(CANDIDATE),
        "parent_sha256": digest(PARENT),
        "tables": PLANNED_TABLES,
        "completed_hands": completed_hands,
        "counts": dict(sorted(counts.items())),
        "strict_evidence": {
            "states": len(strict),
            "distinct_tables": len(strict_tables),
            "distinct_source_roots": len(strict_roots),
            "mixes": sorted(strict_mixes),
            "by_panel_seed": dict(sorted(Counter(
                str(row["source"]["panel_seed"]) for row in strict
            ).items())),
            "by_mix": dict(sorted(Counter(row["source"]["mix"] for row in strict).items())),
            "local_gains": local_gains,
        },
        "gate_checks": gate_checks,
        "max_candidate_operations": max_operations,
        "candidate_max_operations": ActionValueScorer(
            "r18-p5-hidden-limit", CANDIDATE.read_text(encoding="utf-8")
        ).max_operations,
        "runtime_counts": dict(sorted(runtime.items())),
        "next": (
            "P5获得补杠严格支配机会资格；进入冻结完整桌安全门"
            if passed else "隐藏集已消耗；停止P5晋级并以全新来源重构或扩样"
        ),
        "selection_eligible": passed,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    write_json(_project_file(_PROJECT_ROOT, OUT / "windows.json"), {"windows": windows})
    print(json.dumps({
        key: result[key] for key in (
            "status", "tables", "completed_hands", "counts", "strict_evidence",
            "gate_checks", "max_candidate_operations", "next",
        )
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "analyze"))
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "run":
        run()
    else:
        analyze()


if __name__ == "__main__":
    main()
