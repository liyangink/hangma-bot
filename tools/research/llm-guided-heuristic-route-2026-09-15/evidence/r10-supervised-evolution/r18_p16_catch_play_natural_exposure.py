"""R18 P16：稳定 P5 全新完整桌中的抓打圈自然暴露审计。

本阶段只读取依法可见的 ``DecisionRequest`` 和规则动作事实，在运行前冻结
512 张表及三个互斥家族。选择不读取结算、积分结果或候选效果；每个来源
单元每家族最多冻结一个状态。合成题只负责规则健康，不能补足自然暴露门。
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
from collections import Counter, defaultdict
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
import r18_p9_midgame_hidden_world_teacher as p9  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.hangma.catch_play import analyze_catch_play  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.hangma.internal_types import is_wealth_code  # noqa: E402
from hangma_bot.policy.action_value_policy import build_scoring_view  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p16-catch-play-natural-exposure-01-20260922')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
AV_CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/action-value-v1.json')
PUBLIC_INTERFACE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/action-value-public-interface-v1.json')
PARENT = p9.P5
PANEL_SEED = 2026102202
MIXES = ("H", "M")
ROOTS = tuple(range(1, 33))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2
PLANNED_TABLES = len(MIXES) * len(ROOTS) * len(SEATS) * TABLES_PER_SOURCE
WORKERS = 8
LIMITS = ValueAnalysisLimits(max_expansions=20_000, max_routes_per_candidate=256)
FAMILIES = ("catch.open", "catch.renew_or_close", "catch.owner_claim")
MIN_STATES = 24
MIN_SOURCE_ROOTS = 4


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


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
            "source_root_id": f"{mix}:r{root:02d}",
            "source_id": f"{mix}:r{root:02d}:s{seat}",
        }
        for mix in MIXES for root in ROOTS for seat in SEATS
    ]


def source_path(row: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (str(row["source_id"]).replace(":", "-") + ".json"))


def _top_action(scorer: ActionValueScorer, request: Any) -> tuple[str | None, str]:
    batch_result = scorer.score(build_scoring_view(request))
    if batch_result.status != "SCORED":
        return None, "P5_" + batch_result.status + ":" + str(batch_result.reason)
    entries = sorted(batch_result.entries, key=lambda item: (-item.score, item.action_key))
    if not entries:
        return None, "P5_EMPTY_ENTRIES"
    return entries[0].action_key, "SCORED"


def _candidate_row(
    request: Any,
    source: Mapping[str, Any],
    scorer: ActionValueScorer,
) -> tuple[dict[str, Any] | None, str | None]:
    observation = request.observation
    context = analyze_catch_play(observation)
    actions = tuple(request.rules.legal_candidates)
    action_keys = tuple(item.action_key for item in actions)
    discard_keys = tuple(
        item.action_key for item in actions if item.action_key.startswith("discard:")
    )
    white_discards = tuple(
        key for key in discard_keys if is_wealth_code(key.split(":", 1)[1])
    )
    nonwhite_discards = tuple(key for key in discard_keys if key not in white_discards)
    claim_keys = tuple(
        item.action_key for item in actions
        if item.action_key.startswith(("chi:", "peng:", "gang:exposed:", "gang:added:"))
    )
    has_pass = "pass" in action_keys

    family = None
    comparison_keys: tuple[str, ...] = ()
    if (
        observation.phase == "draw"
        and not context.active
        and white_discards
        and nonwhite_discards
    ):
        family = "catch.open"
        comparison_keys = white_discards + nonwhite_discards
    elif (
        observation.phase == "draw"
        and context.active
        and context.owner_seat == observation.seat
        and context.issue is None
        and white_discards
        and nonwhite_discards
    ):
        family = "catch.renew_or_close"
        comparison_keys = white_discards + nonwhite_discards
    elif (
        observation.phase in ("response_peng", "response_chi")
        and context.active
        and context.owner_seat == observation.seat
        and context.issue is None
        and claim_keys
        and has_pass
    ):
        family = "catch.owner_claim"
        comparison_keys = claim_keys + ("pass",)
    if family is None:
        return None, None

    parent_action, parent_status = _top_action(scorer, request)
    if parent_action is None:
        return None, parent_status
    request_json = decision_request_to_json(request)
    wealth = observation.rule_state.wealth_god.code
    hand = [tile.code for tile in observation.my_hand]
    if observation.drawn_tile is not None and len(hand) != observation.hand_counts[observation.seat]:
        hand.append(observation.drawn_tile.code)
    return {
        "schema": "r18-p16-catch-natural-row/1",
        "family": family,
        "source": dict(source),
        "request_sha256": value_digest(request_json),
        "request": request_json,
        "game_id": observation.game_id,
        "round_no": observation.round_no,
        "snapshot_seq": observation.snapshot_seq,
        "phase": observation.phase,
        "seat": observation.seat,
        "dealer_seat": observation.dealer_seat,
        "remaining_tile_count": observation.remaining_tile_count,
        "wealth_count": hand.count(wealth),
        "baotou": observation.rule_state.baotou,
        "chain_count": observation.rule_state.chain_count,
        "chain_piao": observation.chain_piao,
        "catch_play_active": context.active,
        "catch_play_owner_seat": context.owner_seat,
        "catch_play_started_seq": context.started_seq,
        "catch_play_evidence_source": context.source,
        "catch_play_issue": context.issue,
        "legal_action_keys": list(action_keys),
        "comparison_action_keys": list(comparison_keys),
        "white_discard_keys": list(white_discards),
        "nonwhite_discard_keys": list(nonwhite_discards),
        "claim_action_keys": list(claim_keys),
        "has_immediate_hu": "hu" in action_keys,
        "p5_action_key": parent_action,
        "p5_status": parent_status,
    }, None


def audit_requests(
    requests: list[Any], source: Mapping[str, Any], parent_source: str,
) -> dict[str, Any]:
    scorer = ActionValueScorer("r18-p16-p5-" + str(source["source_id"]), parent_source)
    counts: Counter[str] = Counter()
    rows = []
    problems = []
    for request in requests:
        counts["focal_requests"] += 1
        observation = request.observation
        context = analyze_catch_play(observation)
        counts["catch_active_requests"] += int(context.active)
        counts["catch_owner_known_requests"] += int(
            context.active and context.owner_seat is not None and context.issue is None
        )
        counts["catch_focal_owner_requests"] += int(
            context.active and context.owner_seat == observation.seat and context.issue is None
        )
        row, problem = _candidate_row(request, source, scorer)
        if problem is not None:
            problems.append(problem)
        if row is not None:
            counts[row["family"]] += 1
            rows.append(row)
    return {"counts": dict(sorted(counts.items())), "eligible_rows": rows,
            "problems": problems}


def execute_source(source_row: Mapping[str, Any]) -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    parent_source = PARENT.read_text(encoding="utf-8")
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source_row["mix"]),
        root_index=int(source_row["root_index"]),
        focal_seat=int(source_row["focal_seat"]),
        panel_seed=PANEL_SEED,
    )
    requests: list[Any] = []
    stage = natural.run_arm_stage(
        arm="p16-p5-catch-natural",
        plans=plans,
        candidate_scorer=ActionValueScorer(
            "r18-p16-trajectory-" + str(source_row["source_id"]), parent_source,
        ),
        opponent_policies=contract["panel"]["opponent_scenarios"][
            str(source_row["mix"])
        ]["opponent_policies"],
        versions_block=natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=LIMITS,
        decision_observer=requests.append,
    )
    return {
        "source": dict(source_row),
        "status": stage.get("status"),
        "error": stage.get("error"),
        "tables": len(stage.get("tables") or []),
        "audit": audit_requests(requests, source_row, parent_source),
    }


def prepare() -> None:
    """在查看自然暴露前冻结来源、阈值和最大表数。"""

    if OUT.exists():
        raise SystemExit("P16 目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p16-catch-play-natural-exposure-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "机会优先新目标与P15停滞复盘；先验证抓打圈自然可选性",
        "scope": "全新H/M各32根、四焦点座、每来源2桌；稳定P5结果盲采集",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    frozen_sources = sources()
    write_json(_project_file(_PROJECT_ROOT, OUT / "sources.json"), {
        "schema": "r18-p16-catch-sources/1", "sources": frozen_sources,
    })
    tracked = [
        Path(__file__), CONTRACT, AV_CONTRACT, PUBLIC_INTERFACE, PARENT,
        Path(natural.__file__), _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "sources.json"),
    ]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p16-catch-natural-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "contract_sha256": digest(CONTRACT),
        "action_value_contract_sha256": digest(AV_CONTRACT),
        "public_interface_sha256": digest(PUBLIC_INTERFACE),
        "parent_sha256": digest(PARENT),
        "scoring_view_schema": "sitin-scoring-view/4",
        "panel_seed": PANEL_SEED,
        "mixes": list(MIXES),
        "root_indices": list(ROOTS),
        "focal_seats": list(SEATS),
        "sources": len(frozen_sources),
        "tables_per_source": TABLES_PER_SOURCE,
        "planned_tables": PLANNED_TABLES,
        "workers": WORKERS,
        "families": list(FAMILIES),
        "minimum_states_per_family": MIN_STATES,
        "minimum_source_roots_per_family": MIN_SOURCE_ROOTS,
        "freeze_rule": "每来源单元每家族按(round_no,snapshot_seq,request_sha256)取第一条；全局请求摘要去重",
        "trajectory_policy": "frozen P5",
        "outcome_blind": True,
        "model_calls": 0,
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "tables": PLANNED_TABLES}, ensure_ascii=False))


def verify_manifest() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["contract_sha256"] != digest(CONTRACT):
        raise ValueError("P16 桌赛合同漂移")
    if manifest["action_value_contract_sha256"] != digest(AV_CONTRACT):
        raise ValueError("P16 评分合同漂移")
    if manifest["public_interface_sha256"] != digest(PUBLIC_INTERFACE):
        raise ValueError("P16 公开接口漂移")
    if manifest["parent_sha256"] != digest(PARENT):
        raise ValueError("P16 P5 父代漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "sources.json")).read_text(encoding="utf-8"))["sources"]
    return manifest, frozen


def run() -> None:
    manifest, frozen = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for row in frozen:
        path = source_path(row)
        if path.exists():
            saved = json.loads(path.read_text(encoding="utf-8"))
            if saved.get("status") != "complete" or saved.get("tables") != TABLES_PER_SOURCE:
                raise ValueError("既有来源不完整：" + str(path))
            completed_tables += TABLES_PER_SOURCE
        else:
            pending.append(row)
    reservation = ledger.reserve(
        step_id="r18:p16-catch-natural-exposure",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="稳定P5抓打圈结果盲自然暴露",
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
                        raise RuntimeError("P5 复算失败：" + ";".join(result["audit"]["problems"][:3]))
                    write_json(source_path(row), result)
                    executed += TABLES_PER_SOURCE
                    completed_tables += TABLES_PER_SOURCE
                    if completed_tables % 64 == 0 or completed_tables == PLANNED_TABLES:
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
        "schema": "r18-p16-catch-natural-run/1",
        "source_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != len(frozen):
        raise RuntimeError("P16 抓打圈自然暴露执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def analyze() -> None:
    manifest, frozen = verify_manifest()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != PLANNED_TABLES:
        raise ValueError("P16 执行不完整")
    raw_counts: Counter[str] = Counter()
    rows_by_source_family: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    total_requests = 0
    for source in frozen:
        document = json.loads(source_path(source).read_text(encoding="utf-8"))
        raw_counts.update(document["audit"]["counts"])
        total_requests += int(document["audit"]["counts"].get("focal_requests", 0))
        for row in document["audit"]["eligible_rows"]:
            rows_by_source_family[(source["source_id"], row["family"])].append(row)

    frozen_rows = []
    seen_requests = set()
    duplicate_skips = 0
    for source in frozen:
        for family in FAMILIES:
            options = sorted(
                rows_by_source_family.get((source["source_id"], family), ()),
                key=lambda row: (
                    int(row["round_no"]), int(row["snapshot_seq"]),
                    str(row["request_sha256"]),
                ),
            )
            previously_seen = set(seen_requests)
            selected = next(
                (row for row in options if row["request_sha256"] not in previously_seen),
                None,
            )
            duplicate_skips += sum(
                row["request_sha256"] in previously_seen for row in options
            )
            if selected is not None:
                seen_requests.add(selected["request_sha256"])
                frozen_rows.append(selected)

    by_family = {}
    for family in FAMILIES:
        items = [row for row in frozen_rows if row["family"] == family]
        source_roots = sorted({row["source"]["source_root_id"] for row in items})
        by_family[family] = {
            "eligible_windows": int(raw_counts[family]),
            "frozen_independent_states": len(items),
            "source_roots": source_roots,
            "source_root_count": len(source_roots),
            "passes_natural_exposure_gate": (
                len(items) >= MIN_STATES and len(source_roots) >= MIN_SOURCE_ROOTS
            ),
            "with_immediate_hu": sum(bool(row["has_immediate_hu"]) for row in items),
            "p5_action_frequencies": dict(sorted(Counter(
                row["p5_action_key"] for row in items
            ).items())),
        }
    dataset = {
        "schema": "r18-p16-catch-natural-dataset/1",
        "outcome_blind": True,
        "rows": frozen_rows,
    }
    result = {
        "schema": "r18-p16-catch-natural-result/1",
        "status": "COMPLETE_P16_CATCH_NATURAL_EXPOSURE",
        "tables": PLANNED_TABLES,
        "source_units": len(frozen),
        "focal_requests": total_requests,
        "raw_counts": dict(sorted(raw_counts.items())),
        "frozen_states": len(frozen_rows),
        "request_hashes_unique": len(seen_requests) == len(frozen_rows),
        "duplicate_skips": duplicate_skips,
        "by_family": by_family,
        "families_open_for_p17": [
            family for family in FAMILIES
            if by_family[family]["passes_natural_exposure_gate"]
        ],
        "families_closed_for_low_exposure": [
            family for family in FAMILIES
            if not by_family[family]["passes_natural_exposure_gate"]
        ],
        "next": "仅对通过24状态/4来源根门的家族运行32个共同隐藏世界多臂教师；其余报告自然暴露不足，不用合成题补数",
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), dataset)
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
