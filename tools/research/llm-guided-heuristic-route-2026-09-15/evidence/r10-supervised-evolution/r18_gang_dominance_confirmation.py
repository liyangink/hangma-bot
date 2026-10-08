"""R18 补杠严格支配判据：全新自然来源盲确认。

本批在执行前冻结公开信息判据，再用全新的 ``panel_seed`` 跑稳定 V2 自然
桌。发现批 ``2026100223`` 不参与确认。统计单位同时报告自然决策状态、桌和
来源根；同一状态的未来牌墙变体不进入本批，也不冒充独立样本。

这不是候选强度评测。它回答的是：已在发现批证明的“立即胡 vs 补杠后任意
补牌仍可胡且杠开结算更高”机制，能否在新牌山和新自然轨迹中重复出现，并且
能否由只读规则事实精确识别。
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
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.interface import ValueCoverage  # noqa: E402
from hangma_bot.kernel.actions import CANONICAL_TILE_CODES  # noqa: E402
from hangma_bot.kernel.serialization import window_key_to_json  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-gang-dominance-confirmation-01-20260922')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922/generation/candidate.py')
DISCOVERY_SEED = 2026100223
PANEL_SEED = 2026100627
MIXES = ("H", "M")
ROOTS = tuple(range(1, 97))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2
PLANNED_TABLES = len(MIXES) * len(ROOTS) * len(SEATS) * TABLES_PER_SOURCE
LIMITS = ValueAnalysisLimits(max_expansions=20_000, max_routes_per_candidate=256)
ALL_CODES = frozenset(CANONICAL_TILE_CODES)


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """写入稳定排序、缩进且以换行结束的 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def sources() -> list[dict[str, Any]]:
    """列出全部自然阶段来源；每项含两桌，但统计另报告不含座位的来源根。"""

    return [
        {
            "panel_seed": PANEL_SEED,
            "mix": mix,
            "root_index": root,
            "focal_seat": seat,
            "source_id": f"s{PANEL_SEED}:{mix}:r{root:02d}:s{seat}",
            "source_root_id": natural.natural_root_id(mix, PANEL_SEED, root),
        }
        for mix in MIXES for root in ROOTS for seat in SEATS
    ]


def source_path(row: Mapping[str, Any]) -> Path:
    """一个来源的断点文件。"""

    return _project_file(_PROJECT_ROOT, OUT / "sources" / (str(row["source_id"]).replace(":", "-") + ".json"))


def source_paths() -> list[Path]:
    """列出改变执行或判据语义的冻结输入。"""

    return [Path(__file__), CONTRACT, CANDIDATE, Path(natural.__file__)]


def prepare() -> None:
    """在查看新自然桌前冻结判据、样本空间、通过门槛和预算。"""

    if OUT.exists():
        raise SystemExit("补杠支配确认目录已存在；拒绝覆盖")
    if PANEL_SEED == DISCOVERY_SEED:
        raise ValueError("确认批不得复用发现批 panel_seed")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-gang-dominance-confirmation-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "补杠严格支配机制已在发现批完成规则与未来牌墙证明；转入新来源盲确认",
        "scope": "全新panel_seed，H/M各96根、四焦点座、每来源两桌；稳定V2自然轨迹",
        "max_model_calls": 0,
        "confirmation_roots": len(MIXES) * len(ROOTS),
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-gang-dominance-confirmation-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "contract_sha256": digest(CONTRACT),
        "candidate_sha256": digest(CANDIDATE),
        "discovery_panel_seed_excluded": DISCOVERY_SEED,
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "sources": len(sources()),
        "tables_per_source": TABLES_PER_SOURCE,
        "planned_tables": PLANNED_TABLES,
        "workers": 8,
        "trajectory_policy": "stable weighted_heuristic_v2",
        "frozen_public_predicate": {
            "legal_same_window": ["hu", "gang:added:*"],
            "value_coverage": "complete",
            "value_issues": [],
            "replacement_draw_unknown": True,
            "standard_shanten_after": 0,
            "standard_useful_tile_codes": "exactly all 34 canonical codes",
            "value_routes": "exactly one route; draw_kind=replacement; shanten=0; no followup discard",
            "route_useful_tile_codes": "exactly the standard useful codes whose public remaining estimate is positive",
            "settlement": "gang route focal score strictly greater than immediate hu focal score",
            "unknown_or_missing": "fail closed",
        },
        "control_strata": [
            "hu_plus_added_gang_but_predicate_false",
            "added_gang_without_immediate_hu",
            "concealed_gang",
            "exposed_gang",
        ],
        "confirmation_gate": {
            "strict_states_min": 8,
            "strict_distinct_tables_min": 8,
            "strict_distinct_source_roots_min": 8,
            "strict_required_mixes": list(MIXES),
            "mechanical_failures": 0,
        },
        "sampling_unit": "自然决策状态；另报告桌与不含焦点座位的来源根，绝不把牌墙变体当独立状态",
        "candidate_use": "仅为run_arm_stage接口提供未使用的baseline占位评分器",
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED",
        "panel_seed": PANEL_SEED,
        "source_roots": len(MIXES) * len(ROOTS),
        "tables": PLANNED_TABLES,
    }, ensure_ascii=False))


def verify_manifest() -> dict[str, Any]:
    """拒绝合同、占位候选、执行代码或冻结判据漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["contract_sha256"] != digest(CONTRACT):
        raise ValueError("合同漂移")
    if manifest["candidate_sha256"] != digest(CANDIDATE):
        raise ValueError("P3 占位候选身份漂移")
    if manifest["panel_seed"] == manifest["discovery_panel_seed_excluded"]:
        raise ValueError("确认批错误复用发现批 panel_seed")
    guard.verify(manifest["runtime"])
    return manifest


def _gang_kind(action_key: str) -> str:
    """从规范动作键读取杠种。"""

    pieces = action_key.split(":")
    if len(pieces) != 3 or pieces[0] != "gang" or pieces[1] not in {
        "concealed", "exposed", "added",
    }:
        raise ValueError("未知杠动作键：" + action_key)
    return pieces[1]


def _settlement(value: Any, focal_seat: int) -> dict[str, Any] | None:
    """把结算转成可审计 JSON；座位向量顺序固定为 0—3。"""

    if value is None:
        return None
    return {
        "fan": int(value.fan),
        "details": list(value.details),
        "score_delta_by_seat_0_to_3": list(value.score_delta),
        "focal_score": int(value.score_delta[focal_seat]),
    }


def _strict_predicate(hu: Any | None, gang: Any, focal_seat: int) -> tuple[bool, dict[str, bool]]:
    """执行预先冻结的公开信息严格支配判据；任一未知或缺失均不触发。"""

    facts = gang.facts
    value_facts = gang.value_facts
    immediate = None if hu is None or hu.value_facts is None else hu.value_facts.immediate_settlement
    routes = () if value_facts is None else tuple(value_facts.routes)
    route = routes[0] if len(routes) == 1 else None
    standard_codes = set() if facts is None or facts.standard_useful_tiles is None else {
        item.code for item in facts.standard_useful_tiles
    }
    publicly_possible_codes = set() if facts is None or facts.standard_useful_tiles is None else {
        item.code for item in facts.standard_useful_tiles if item.remaining_estimate > 0
    }
    route_codes = set() if route is None else {item.code for item in route.useful_tiles}
    route_score = None if route is None else int(route.conditional_settlement.score_delta[focal_seat])
    immediate_score = None if immediate is None else int(immediate.score_delta[focal_seat])
    checks = {
        "hu_legal_with_immediate_settlement": hu is not None and immediate is not None,
        "added_gang": gang.action_key.startswith("gang:added:"),
        "coverage_complete": value_facts is not None and value_facts.coverage is ValueCoverage.COMPLETE,
        "no_value_issues": value_facts is not None and not value_facts.issues,
        "replacement_unknown": facts is not None and facts.replacement_draw_unknown is True,
        "pre_replacement_standard_shanten_zero": facts is not None and facts.standard_shanten_after == 0,
        "standard_codes_all_34": standard_codes == ALL_CODES,
        "unique_route": route is not None,
        "replacement_route": route is not None and route.conditions.draw_kind == "replacement",
        "route_shanten_zero": route is not None and route.shanten == 0,
        "route_has_no_followup_discard": route is not None and route.followup_discard is None,
        "route_covers_all_publicly_possible_tiles": (
            route is not None
            and bool(publicly_possible_codes)
            and route_codes == publicly_possible_codes
        ),
        "route_score_strictly_higher": (
            route_score is not None and immediate_score is not None and route_score > immediate_score
        ),
    }
    return all(checks.values()), checks


def audit_requests(requests: list[Any], source: Mapping[str, Any]) -> dict[str, Any]:
    """分类全部自然杠窗口，并保留严格命中与对照所需公开事实。"""

    counts: Counter[str] = Counter()
    windows = []
    for request in requests:
        counts["focal_requests"] += 1
        candidates = {item.action_key: item for item in request.rules.legal_candidates}
        gang_candidates = [
            item for item in request.rules.legal_candidates
            if item.action_key.startswith("gang:")
        ]
        if not gang_candidates:
            continue
        counts["gang_windows"] += 1
        hu = candidates.get("hu")
        for gang in gang_candidates:
            kind = _gang_kind(gang.action_key)
            counts[kind + "_candidates"] += 1
            strict, checks = _strict_predicate(hu, gang, request.observation.seat)
            if strict:
                stratum = "strict_dominance"
            elif kind == "added" and hu is not None:
                stratum = "hu_plus_added_gang_but_predicate_false"
            elif kind == "added":
                stratum = "added_gang_without_immediate_hu"
            else:
                stratum = kind + "_gang"
            counts[stratum] += 1
            facts = gang.facts
            value_facts = gang.value_facts
            immediate = None if hu is None or hu.value_facts is None else hu.value_facts.immediate_settlement
            routes = () if value_facts is None else tuple(value_facts.routes)
            windows.append({
                "stratum": stratum,
                "strict_predicate": strict,
                "checks": checks,
                "source": dict(source),
                "game_id": request.observation.game_id,
                "round_no": request.observation.round_no,
                "snapshot_seq": request.observation.snapshot_seq,
                "focal_physical_seat": request.observation.seat,
                "window_key": window_key_to_json(request.window_key),
                "remaining_tile_count": request.observation.remaining_tile_count,
                "gang_action": gang.action_key,
                "hu_action": None if hu is None else hu.action_key,
                "coverage": None if value_facts is None else value_facts.coverage.value,
                "issue_codes": [] if value_facts is None else [
                    str(getattr(issue, "code", type(issue).__name__)) for issue in value_facts.issues
                ],
                "replacement_draw_unknown": None if facts is None else facts.replacement_draw_unknown,
                "standard_shanten_after": None if facts is None else facts.standard_shanten_after,
                "standard_useful_codes": [] if facts is None or facts.standard_useful_tiles is None else [
                    item.code for item in facts.standard_useful_tiles
                ],
                "immediate_hu_settlement": _settlement(immediate, request.observation.seat),
                "routes": [{
                    "draw_kind": route.conditions.draw_kind,
                    "shanten": route.shanten,
                    "followup_discard": route.followup_discard,
                    "useful_codes": [item.code for item in route.useful_tiles],
                    "settlement": _settlement(route.conditional_settlement, request.observation.seat),
                } for route in routes],
            })
    return {
        "counts": dict(sorted(counts.items())),
        "windows": windows,
        "problems": [],
    }


def execute_source(source: Mapping[str, Any]) -> dict[str, Any]:
    """跑一个来源的两桌稳定 V2 阶段，并只观察焦点座位公开请求。"""

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source["mix"]),
        root_index=int(source["root_index"]),
        focal_seat=int(source["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    requests: list[Any] = []
    scorer = ActionValueScorer(
        "r18-gang-dominance-confirmation-unused",
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
        "audit": audit_requests(requests, source),
    }


def run() -> None:
    """并行执行全部新来源，按来源断点续跑，失败时保守记账。"""

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
        step_id="r18:gang-dominance-confirmation",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="新panel_seed稳定V2自然来源盲确认",
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
                    if completed_tables % 128 == 0 or completed_tables == PLANNED_TABLES:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": PLANNED_TABLES,
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001 - 失败必须进入证据
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
        "schema": "r18-gang-dominance-confirmation-run/1",
        "source_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != len(sources()):
        raise RuntimeError("补杠支配确认执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def analyze() -> None:
    """按状态、桌、来源根和对手混合汇总，严格套用预冻结通过门。"""

    manifest = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary["failures"] or run_summary["actual_tables"] != PLANNED_TABLES:
        raise ValueError("补杠支配确认运行不完整")
    counts: Counter[str] = Counter()
    runtime: Counter[str] = Counter()
    windows = []
    completed_hands = 0
    for source in sources():
        document = json.loads(source_path(source).read_text(encoding="utf-8"))
        completed_hands += int(document["completed_hands"])
        counts.update(document["audit"]["counts"])
        runtime.update(document["runtime_counts"])
        windows.extend(document["audit"]["windows"])
    strict = [row for row in windows if row["strict_predicate"]]
    strict_tables = {row["game_id"] for row in strict}
    strict_roots = {row["source"]["source_root_id"] for row in strict}
    strict_mixes = {row["source"]["mix"] for row in strict}
    gate = manifest["confirmation_gate"]
    gate_checks = {
        "strict_states_min": len(strict) >= int(gate["strict_states_min"]),
        "strict_distinct_tables_min": len(strict_tables) >= int(gate["strict_distinct_tables_min"]),
        "strict_distinct_source_roots_min": len(strict_roots) >= int(gate["strict_distinct_source_roots_min"]),
        "strict_required_mixes": strict_mixes == set(gate["strict_required_mixes"]),
        "mechanical_failures_zero": not run_summary["failures"],
    }
    by_mix = {
        mix: dict(sorted(Counter(
            row["stratum"] for row in windows if row["source"]["mix"] == mix
        ).items()))
        for mix in MIXES
    }
    result = {
        "schema": "r18-gang-dominance-confirmation-result/1",
        "status": "COMPLETE_GANG_DOMINANCE_CONFIRMATION",
        "panel_seed": PANEL_SEED,
        "discovery_panel_seed_excluded": DISCOVERY_SEED,
        "tables": PLANNED_TABLES,
        "completed_hands": completed_hands,
        "counts": dict(sorted(counts.items())),
        "strata_by_mix": by_mix,
        "strict_evidence": {
            "states": len(strict),
            "distinct_tables": len(strict_tables),
            "distinct_source_roots": len(strict_roots),
            "mixes": sorted(strict_mixes),
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
        "runtime_counts": dict(sorted(runtime.items())),
        "windows": windows,
        "interpretation": "仅确认公开严格支配机制在新自然来源复现；尚未证明候选完整桌赛非劣或可发布。",
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        key: result[key] for key in (
            "status", "tables", "completed_hands", "strata_by_mix",
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
