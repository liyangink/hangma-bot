"""R18 补杠严格支配判据：第二批全新自然来源扩样。

首个确认批在 1,536 桌中得到 4 个不同桌/来源根的严格命中，已跨 H/M 复现，
但未达到预冻结的 8 根门槛。本批不改判据和门槛，只增加两个全新
``panel_seed``，最终按三个确认种子的自然状态、桌和来源根并集裁定。
"""

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
import r18_gang_dominance_confirmation as base  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-gang-dominance-confirmation-extension-01-20260922')
PRIOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-gang-dominance-confirmation-01-20260922')
CONTRACT = base.CONTRACT
CANDIDATE = base.CANDIDATE
PANEL_SEEDS = (2026100631, 2026100643)
EXCLUDED_SEEDS = (base.DISCOVERY_SEED, base.PANEL_SEED)
MIXES = base.MIXES
ROOTS = base.ROOTS
SEATS = base.SEATS
TABLES_PER_SOURCE = base.TABLES_PER_SOURCE
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
    """列出两个新确认种子的全部自然阶段来源。"""

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
    """冻结扩样空间；沿用第一确认批已冻结的判据和累计通过门。"""

    if OUT.exists():
        raise SystemExit("补杠支配扩样目录已存在；拒绝覆盖")
    if set(PANEL_SEEDS) & set(EXCLUDED_SEEDS) or len(set(PANEL_SEEDS)) != len(PANEL_SEEDS):
        raise ValueError("扩样 panel_seed 必须全新且互不重复")
    prior = json.loads((_project_file(_PROJECT_ROOT, PRIOR / "result.json")).read_text(encoding="utf-8"))
    if prior.get("decision") != "INSUFFICIENT_FRESH_NATURAL_CONFIRMATION_EXTEND_WITH_NEW_PANEL_SEED":
        raise ValueError("第一确认批没有要求换新 panel_seed 扩样")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-gang-dominance-confirmation-extension-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "首确认批4根复现但未达预冻结8根门槛；不改判据，以两个新panel_seed扩样",
        "scope": "两个新panel_seed，H/M各96根、四焦点座、每来源两桌；与首确认批并集裁定",
        "max_model_calls": 0,
        "confirmation_roots": len(PANEL_SEEDS) * len(MIXES) * len(ROOTS),
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-gang-dominance-confirmation-extension-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=[
            Path(__file__), Path(base.__file__), CONTRACT, CANDIDATE,
            _project_file(_PROJECT_ROOT, PRIOR / "manifest.json"), _project_file(_PROJECT_ROOT, PRIOR / "result.json"),
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), Path(natural.__file__),
        ]),
        "base_predicate_source_sha256": digest(Path(base.__file__)),
        "prior_manifest_sha256": digest(_project_file(_PROJECT_ROOT, PRIOR / "manifest.json")),
        "prior_result_sha256": digest(_project_file(_PROJECT_ROOT, PRIOR / "result.json")),
        "contract_sha256": digest(CONTRACT),
        "candidate_sha256": digest(CANDIDATE),
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
        "frozen_public_predicate": json.loads(
            (_project_file(_PROJECT_ROOT, PRIOR / "manifest.json")).read_text(encoding="utf-8")
        )["frozen_public_predicate"],
        "cumulative_confirmation_gate": {
            "strict_states_min": 8,
            "strict_distinct_tables_min": 8,
            "strict_distinct_source_roots_min": 8,
            "strict_required_mixes": list(MIXES),
            "mechanical_failures": 0,
        },
        "sampling_unit": "三个确认种子的自然决策状态；另报告桌与不含焦点座位的来源根",
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED",
        "panel_seeds": list(PANEL_SEEDS),
        "new_source_roots": len(PANEL_SEEDS) * len(MIXES) * len(ROOTS),
        "tables": PLANNED_TABLES,
    }, ensure_ascii=False))


def verify_manifest() -> dict[str, Any]:
    """核对扩样代码、第一确认批、合同与候选占位身份。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "base predicate": (manifest["base_predicate_source_sha256"], digest(Path(base.__file__))),
        "prior manifest": (manifest["prior_manifest_sha256"], digest(_project_file(_PROJECT_ROOT, PRIOR / "manifest.json"))),
        "prior result": (manifest["prior_result_sha256"], digest(_project_file(_PROJECT_ROOT, PRIOR / "result.json"))),
        "contract": (manifest["contract_sha256"], digest(CONTRACT)),
        "candidate": (manifest["candidate_sha256"], digest(CANDIDATE)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + " 漂移")
    if set(manifest["panel_seeds"]) & set(manifest["excluded_panel_seeds"]):
        raise ValueError("扩样错误复用既有 panel_seed")
    guard.verify(manifest["runtime"])
    return manifest


def execute_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """跑一个来源的两桌稳定 V2 阶段并复用冻结判据分类公开请求。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source["mix"]),
        root_index=int(source["root_index"]),
        focal_seat=int(source["focal_seat"]),
        panel_seed=int(source["panel_seed"]),
    )
    requests: list[Any] = []
    scorer = ActionValueScorer(
        "r18-gang-dominance-confirmation-extension-unused",
        CANDIDATE.read_text(encoding="utf-8"),
    )
    stage_result = natural.run_arm_stage(
        arm="baseline",
        plans=plans,
        candidate_scorer=scorer,
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
        "table_ids": [str(table.get("table_id")) for table in stage_result.get("tables") or []],
        "completed_hands": completed_hands,
        "runtime_counts": dict(sorted(runtime.items())),
        "audit": base.audit_requests(requests, source),
    }


def run() -> None:
    """并行执行两个新确认种子的全部来源，支持按来源断点续跑。"""

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
                raise ValueError("既有扩样来源不完整：" + str(path))
            completed_tables += TABLES_PER_SOURCE
        else:
            pending.append(row)
    reservation = ledger.reserve(
        step_id="r18:gang-dominance-confirmation-extension",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="两个新panel_seed的稳定V2自然来源扩样",
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
                        raise RuntimeError("公开事实审计出现问题")
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
        "schema": "r18-gang-dominance-confirmation-extension-run/1",
        "source_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != len(sources()):
        raise RuntimeError("补杠支配扩样执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def analyze() -> None:
    """把第一确认批与本批按自然状态、桌、来源根并集合并裁定。"""

    manifest = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary["failures"] or run_summary["actual_tables"] != PLANNED_TABLES:
        raise ValueError("补杠支配扩样运行不完整")
    prior = json.loads((_project_file(_PROJECT_ROOT, PRIOR / "result.json")).read_text(encoding="utf-8"))
    counts: Counter[str] = Counter()
    runtime: Counter[str] = Counter()
    new_windows = []
    completed_hands = 0
    for source in sources():
        document = json.loads(source_path(source).read_text(encoding="utf-8"))
        completed_hands += int(document["completed_hands"])
        counts.update(document["audit"]["counts"])
        runtime.update(document["runtime_counts"])
        new_windows.extend(document["audit"]["windows"])
    all_windows = list(prior["windows"]) + new_windows
    strict = [row for row in all_windows if row["strict_predicate"]]
    strict_tables = {row["game_id"] for row in strict}
    strict_roots = {row["source"]["source_root_id"] for row in strict}
    strict_mixes = {row["source"]["mix"] for row in strict}
    gate = manifest["cumulative_confirmation_gate"]
    gate_checks = {
        "strict_states_min": len(strict) >= int(gate["strict_states_min"]),
        "strict_distinct_tables_min": len(strict_tables) >= int(gate["strict_distinct_tables_min"]),
        "strict_distinct_source_roots_min": len(strict_roots) >= int(gate["strict_distinct_source_roots_min"]),
        "strict_required_mixes": strict_mixes == set(gate["strict_required_mixes"]),
        "mechanical_failures_zero": not run_summary["failures"],
    }
    by_seed = {}
    for seed in (base.PANEL_SEED,) + PANEL_SEEDS:
        rows = [row for row in all_windows if int(row["source"]["panel_seed"]) == seed]
        by_seed[str(seed)] = dict(sorted(Counter(row["stratum"] for row in rows).items()))
    result = {
        "schema": "r18-gang-dominance-confirmation-extension-result/1",
        "status": "COMPLETE_GANG_DOMINANCE_CUMULATIVE_CONFIRMATION",
        "confirmation_panel_seeds": [base.PANEL_SEED, *PANEL_SEEDS],
        "discovery_panel_seed_excluded": base.DISCOVERY_SEED,
        "new_tables": PLANNED_TABLES,
        "cumulative_tables": int(prior["tables"]) + PLANNED_TABLES,
        "new_completed_hands": completed_hands,
        "new_counts": dict(sorted(counts.items())),
        "strata_by_panel_seed": by_seed,
        "strict_evidence": {
            "states": len(strict),
            "distinct_tables": len(strict_tables),
            "distinct_source_roots": len(strict_roots),
            "mixes": sorted(strict_mixes),
            "by_panel_seed": dict(sorted(Counter(
                str(row["source"]["panel_seed"]) for row in strict
            ).items())),
            "by_mix": dict(sorted(Counter(row["source"]["mix"] for row in strict).items())),
            "table_ids": sorted(strict_tables),
            "source_root_ids": sorted(strict_roots),
            "local_gains": [
                row["routes"][0]["settlement"]["focal_score"]
                - row["immediate_hu_settlement"]["focal_score"]
                for row in strict
            ],
        },
        "gate_checks": gate_checks,
        "decision": (
            "CONFIRMED_OPEN_MECHANICAL_CANDIDATE_AUTHORING"
            if all(gate_checks.values())
            else "INSUFFICIENT_FRESH_NATURAL_CONFIRMATION_EXTEND_WITH_NEW_PANEL_SEED"
        ),
        "new_runtime_counts": dict(sorted(runtime.items())),
        "new_windows": new_windows,
        "interpretation": "累计确认只开放机械候选实现；完整桌赛非劣和发布门禁仍未执行。",
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        key: result[key] for key in (
            "status", "new_tables", "cumulative_tables", "strata_by_panel_seed",
            "strict_evidence", "gate_checks", "decision",
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
