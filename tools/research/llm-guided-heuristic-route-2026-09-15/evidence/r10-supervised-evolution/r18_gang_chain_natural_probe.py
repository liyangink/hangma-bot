"""R18 ``gang_chain`` 首尺：全新稳定 V2 完整桌中的自然杠窗口。

轨迹仍由稳定 V2 产生；冻结 P3 只在赛后复算相同请求。程序记录三类杠的
暴露率、规则价值事实完整性、一次补牌条件代理与 V2/P3 的动作分歧，供后续
选择配对反事实目标。它不把条件代理当作杠动作真值。
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
import asyncio
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
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits, ValueCoverage  # noqa: E402
from hangma_bot.kernel.serialization import window_key_to_json  # noqa: E402
from hangma_bot.offline.opportunity_oracle import (  # noqa: E402
    build_one_draw_self_win_oracle,
)
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-gang-chain-natural-probe-02-20260922')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922/generation/candidate.py')
PANEL_SEED = 2026100223
MIXES = ("H", "M")
ROOTS = tuple(range(1, 33))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2
PLANNED_TABLES = len(MIXES) * len(ROOTS) * len(SEATS) * TABLES_PER_SOURCE
LIMITS = ValueAnalysisLimits(max_expansions=20_000, max_routes_per_candidate=256)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def sources() -> list[dict[str, Any]]:
    return [
        {
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "source_id": f"{mix}:r{root:02d}:s{seat}",
        }
        for mix in MIXES for root in ROOTS for seat in SEATS
    ]


def source_path(row: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (str(row["source_id"]).replace(":", "-") + ".json"))


def source_paths() -> list[Path]:
    return [Path(__file__), CONTRACT, CANDIDATE, Path(natural.__file__)]


def prepare() -> None:
    """在看杠窗口前冻结全新 512 桌与所有计数口径。"""

    if OUT.exists():
        raise SystemExit("杠链自然探针目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-gang-chain-natural-probe-02",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "机会优先新目标转入独立gang_chain轴；先测自然分布与事实，不生成候选",
        "scope": "全新H/M各32根、四焦点座、每来源2桌；稳定V2轨迹，P3仅桌后复算",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-gang-chain-natural-probe-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "contract_sha256": digest(CONTRACT),
        "candidate_sha256": digest(CANDIDATE),
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "sources": len(sources()),
        "tables_per_source": TABLES_PER_SOURCE,
        "planned_tables": PLANNED_TABLES,
        "workers": 8,
        "trajectory_policy": "stable weighted_heuristic_v2",
        "candidate_use": "postgame request replay only",
        "gang_kinds": ["concealed", "exposed", "added"],
        "measurements": [
            "gang window and kind frequency",
            "replacement_draw_unknown and COMPLETE coverage",
            "one-replacement-draw proxy best actions",
            "V2 and frozen P3 top actions",
        ],
        "oracle_warning": "一次补牌条件代理不含抢杠、他家先胡和远期续值；只选后续反事实目标",
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "tables": PLANNED_TABLES}, ensure_ascii=False))


def verify_manifest() -> dict[str, Any]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["contract_sha256"] != digest(CONTRACT):
        raise ValueError("杠链探针合同漂移")
    if manifest["candidate_sha256"] != digest(CANDIDATE):
        raise ValueError("P3 身份漂移")
    guard.verify(manifest["runtime"])
    return manifest


def _gang_kind(key: str) -> str:
    pieces = key.split(":")
    if len(pieces) != 3 or pieces[0] != "gang" or pieces[1] not in {
        "concealed", "exposed", "added"
    }:
        raise ValueError("未知杠动作键：" + key)
    return pieces[1]


def _overlay_triggered(plan: Any) -> bool:
    for item in plan.candidates:
        detail = ((item.score_trace or {}).get("detail") or {})
        overlay = detail.get("r18_opportunity_overlay")
        if isinstance(overlay, Mapping) and overlay.get("triggered") is True:
            return True
    return False


async def audit_requests(requests: list[Any], source: str) -> dict[str, Any]:
    candidate = ActionValuePolicy(ActionValueScorer("r18-gang-probe-p3", source))
    baseline = ComparableHeuristicPolicyV2(monotonic=lambda: 800.0)
    counts: Counter[str] = Counter()
    hand_sets: dict[str, set[tuple[str, int]]] = {
        kind: set() for kind in ("any", "concealed", "exposed", "added")
    }
    windows = []
    problems = []
    for request in requests:
        counts["focal_requests"] += 1
        gang_candidates = [
            item for item in request.rules.legal_candidates
            if item.action_key.startswith("gang:")
        ]
        if not gang_candidates:
            continue
        counts["gang_windows"] += 1
        observation = request.observation
        hand_key = (observation.game_id, observation.round_no)
        hand_sets["any"].add(hand_key)
        kinds = sorted({_gang_kind(item.action_key) for item in gang_candidates})
        for kind in kinds:
            counts[kind + "_windows"] += 1
            hand_sets[kind].add(hand_key)
        for item in gang_candidates:
            value_facts = item.value_facts
            progress_facts = item.facts
            kind = _gang_kind(item.action_key)
            counts[kind + "_candidates"] += 1
            if value_facts is None or progress_facts is None:
                counts["gang_missing_value_facts"] += 1
            else:
                counts["gang_replacement_unknown"] += int(
                    progress_facts.replacement_draw_unknown
                )
                counts["gang_complete_value"] += int(
                    value_facts.coverage is ValueCoverage.COMPLETE
                )
                counts["gang_has_routes"] += int(bool(value_facts.routes))
        oracle = build_one_draw_self_win_oracle(request)
        legal = {item.action_key for item in request.rules.legal_candidates}
        complete = not oracle.issues and {item.action_key for item in oracle.values} == legal
        counts["oracle_complete_windows"] += int(complete)
        if not complete:
            counts["oracle_incomplete_windows"] += 1
            problems.extend(oracle.issues[:4])
            continue
        best_value = max(item.value for item in oracle.values)
        optimal = sorted(item.action_key for item in oracle.values if item.value == best_value)
        oracle_gang = any(key.startswith("gang:") for key in optimal)
        counts["oracle_gang_best_windows"] += int(oracle_gang)
        try:
            budget = DecisionBudget(810.0, 820.0, 830.0)
            baseline_plan = await baseline.choose(request, budget)
            candidate_plan = await candidate.choose(
                request, DecisionBudget(810.0, 820.0, 830.0)
            )
        except Exception as exc:  # noqa: BLE001 - 失败必须落证据
            counts["policy_errors"] += 1
            problems.append(type(exc).__name__ + ": " + str(exc)[:240])
            continue
        v2_action = baseline_plan.candidates[0].action_key
        p3_action = candidate_plan.candidates[0].action_key
        counts["v2_gang_choices"] += int(v2_action.startswith("gang:"))
        counts["p3_gang_choices"] += int(p3_action.startswith("gang:"))
        counts["p3_v2_disagreements"] += int(p3_action != v2_action)
        counts["p3_oracle_disagreements"] += int(p3_action not in optimal)
        windows.append({
            "game_id": observation.game_id,
            "round_no": observation.round_no,
            "seat": observation.seat,
            "dealer_seat": observation.dealer_seat,
            "snapshot_seq": observation.snapshot_seq,
            "window_key": window_key_to_json(request.window_key),
            "phase": observation.phase,
            "remaining_tile_count": observation.remaining_tile_count,
            "chain_count": observation.rule_state.chain_count,
            "chain_piao": observation.chain_piao,
            "baotou": observation.rule_state.baotou,
            "own_meld_count": len(observation.melds[observation.seat]),
            "gang_action_keys": [item.action_key for item in gang_candidates],
            "gang_kinds": kinds,
            "oracle_optimal": optimal,
            "oracle_gang_best": oracle_gang,
            "v2_action": v2_action,
            "p3_action": p3_action,
            "p3_overlay_triggered": _overlay_triggered(candidate_plan),
        })
    for kind, values in hand_sets.items():
        counts[("gang" if kind == "any" else kind) + "_hands"] = len(values)
    return {
        "counts": dict(sorted(counts.items())),
        "windows": windows,
        "problems": problems,
    }


def execute_source(source_row: Mapping[str, Any]) -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source_row["mix"]),
        root_index=int(source_row["root_index"]),
        focal_seat=int(source_row["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    source = CANDIDATE.read_text(encoding="utf-8")
    requests: list[Any] = []
    stage = natural.run_arm_stage(
        arm="baseline",
        plans=plans,
        candidate_scorer=ActionValueScorer("r18-gang-probe-unused", source),
        opponent_policies=contract["panel"]["opponent_scenarios"][
            str(source_row["mix"])
        ]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=LIMITS,
        decision_observer=requests.append,
    )
    audit = asyncio.run(audit_requests(requests, source))
    completed_hands = sum(
        int(table.get("result", {}).get("completed_hands") or 0)
        for table in stage.get("tables") or []
    )
    runtime: Counter[str] = Counter()
    for table in stage.get("tables") or []:
        runtime.update(table.get("result", {}).get("runtime_counts") or {})
    return {
        "source": dict(source_row),
        "status": stage.get("status"),
        "error": stage.get("error"),
        "tables": len(stage.get("tables") or []),
        "completed_hands": completed_hands,
        "runtime_counts": dict(sorted(runtime.items())),
        "audit": audit,
    }


def run() -> None:
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
                raise ValueError("既有来源不完整：" + str(path))
            completed_tables += TABLES_PER_SOURCE
        else:
            pending.append(row)
    reservation = ledger.reserve(
        step_id="r18:gang-chain-natural-probe",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="稳定V2自然杠链分布探针",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {pool.submit(execute_source, row): row for row in pending}
            for future in concurrent.futures.as_completed(futures):
                row = futures[future]
                result = None
                try:
                    result = future.result()
                    if result["status"] != "complete" or result["tables"] != TABLES_PER_SOURCE:
                        raise RuntimeError(result.get("error") or "来源未跑满")
                    if result["audit"]["problems"]:
                        raise RuntimeError("杠窗口审计出现问题")
                    write_json(source_path(row), result)
                    executed += TABLES_PER_SOURCE
                    completed_tables += TABLES_PER_SOURCE
                    if completed_tables % 64 == 0 or completed_tables == PLANNED_TABLES:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": PLANNED_TABLES,
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001 - 保留失败来源
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
        "schema": "r18-gang-chain-natural-probe-run/1",
        "source_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != len(sources()):
        raise RuntimeError("杠链自然探针执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def analyze() -> None:
    manifest = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary["failures"] or run_summary["actual_tables"] != PLANNED_TABLES:
        raise ValueError("杠链自然探针运行不完整")
    counts: Counter[str] = Counter()
    runtime: Counter[str] = Counter()
    windows = []
    completed_hands = 0
    for source in sources():
        document = json.loads(source_path(source).read_text(encoding="utf-8"))
        completed_hands += int(document["completed_hands"])
        counts.update(document["audit"]["counts"])
        runtime.update(document["runtime_counts"])
        for window in document["audit"]["windows"]:
            windows.append({**window, "source": dict(source)})
    gang_windows = counts["gang_windows"]
    result = {
        "schema": "r18-gang-chain-natural-probe-result/1",
        "status": "COMPLETE_GANG_CHAIN_PROBE",
        "tables": PLANNED_TABLES,
        "completed_hands": completed_hands,
        "counts": dict(sorted(counts.items())),
        "rates": {
            "gang_hands_per_completed_hand": (
                None if not completed_hands else counts["gang_hands"] / completed_hands
            ),
            "gang_windows_per_focal_request": (
                None if not counts["focal_requests"] else gang_windows / counts["focal_requests"]
            ),
            "oracle_gang_best_fraction": (
                None if not gang_windows else counts["oracle_gang_best_windows"] / gang_windows
            ),
            "v2_gang_choice_fraction": (
                None if not gang_windows else counts["v2_gang_choices"] / gang_windows
            ),
            "p3_gang_choice_fraction": (
                None if not gang_windows else counts["p3_gang_choices"] / gang_windows
            ),
        },
        "runtime_counts": dict(sorted(runtime.items())),
        "windows": windows,
        "next": "按杠种、oracle方向和V2/P3分歧冻结配对反事实目标；未校准前不发作者任务",
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


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
