"""R18 P3 三/四财神飘的自然完整桌暴露率测量。

固定全新面板后只运行稳定 V2 轨迹；P3 仅在赛后对焦点玩家已经收到的
``DecisionRequest`` 做离线复算，不改变动作或牌局路径。结果用于估计机会
样本预算，不能作为 P3 相对 V2 的赛事效果比较。
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
import math
from pathlib import Path
import statistics
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
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.serialization import window_key_to_json  # noqa: E402
from hangma_bot.offline.opportunity_oracle import (  # noqa: E402
    build_one_draw_self_win_oracle,
)
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.interface import DecisionBudget  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-natural-exposure-01-20260922')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
CANDIDATE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p3-author-01-20260922/generation/candidate.py')
PANEL_SEED = 2026100221
MIXES = ("H", "M")
ROOTS = tuple(range(1, 33))
SEATS = (0, 1, 2, 3)
TABLES_PER_SOURCE = 2
PLANNED_TABLES = len(MIXES) * len(ROOTS) * len(SEATS) * TABLES_PER_SOURCE
LIMITS = ValueAnalysisLimits(max_expansions=20_000, max_routes_per_candidate=256)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_value(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
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
            "source_id": f"{mix}:r{root:02d}:s{seat}",
        }
        for mix in MIXES for root in ROOTS for seat in SEATS
    ]


def source_path(row: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "sources" / (str(row["source_id"]).replace(":", "-") + ".json"))


def source_paths() -> list[Path]:
    return [Path(__file__), CONTRACT, CANDIDATE, Path(natural.__file__)]


def prepare() -> None:
    """在看到任何新面板请求前冻结 512 桌样本和统计口径。"""

    if OUT.exists():
        raise SystemExit("自然暴露率目录已存在；拒绝覆盖")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if int(contract["group"]["tables_per_group"]) != TABLES_PER_SOURCE:
        raise ValueError("合同 tables_per_group 与冻结计划不一致")
    OUT.mkdir(parents=True)
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p3-natural-exposure-01",
        accounts={"tables_full": PLANNED_TABLES},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "新目标下量化稀有杭麻机会的自然基准率；稳定V2单臂，不作效果选择",
        "scope": "H/M各32根、4焦点逻辑座、每来源2张完整桌；P3仅赛后复算请求",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p3-natural-exposure-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "contract": str(CONTRACT),
        "contract_sha256": digest(CONTRACT),
        "candidate": str(CANDIDATE),
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
        "candidate_use": "postgame request replay only; cannot change trajectory",
        "value_analysis_limits": {
            "max_expansions": LIMITS.max_expansions,
            "max_routes_per_candidate": LIMITS.max_routes_per_candidate,
        },
        "frozen_denominators": [
            "complete_table", "completed_hand", "focal_request", "focal_draw_window"
        ],
        "frozen_events": [
            "wealth_count_3_or_4_draw",
            "wealth_count_3_or_4_baotou_draw",
            "hu_and_discard_white_legal",
            "oracle_piao",
            "p3_overlay_trigger",
        ],
        "interval": "Wilson 95% binomial interval; clustering limitation reported separately",
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED",
        "sources": len(sources()),
        "tables": PLANNED_TABLES,
    }, ensure_ascii=False))


def verify_manifest() -> dict[str, Any]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["contract_sha256"] != digest(CONTRACT):
        raise ValueError("自然暴露率合同漂移")
    if manifest["candidate_sha256"] != digest(CANDIDATE):
        raise ValueError("P3 候选身份漂移")
    guard.verify(manifest["runtime"])
    return manifest


def _wealth_count(observation: Any) -> int:
    wealth = observation.rule_state.wealth_god.code
    amount = sum(tile.code == wealth for tile in observation.my_hand)
    own_melds = len(observation.melds[observation.seat])
    if (
        observation.drawn_tile is not None
        and len(observation.my_hand) != 14 - 3 * own_melds
        and observation.drawn_tile.code == wealth
    ):
        amount += 1
    return amount


def _overlay_records(plan: Any) -> list[Mapping[str, Any]]:
    rows = []
    for item in plan.candidates:
        detail = ((item.score_trace or {}).get("detail") or {})
        overlay = detail.get("r18_opportunity_overlay")
        if isinstance(overlay, Mapping):
            rows.append(overlay)
    return rows


async def audit_requests(requests: list[Any], source: str) -> dict[str, Any]:
    """按冻结事件聚合焦点可见请求；只对小候选集运行 P3。"""

    candidate = ActionValuePolicy(ActionValueScorer("r18-p3-exposure", source))
    counts: Counter[str] = Counter()
    hand_sets: dict[str, set[tuple[str, int]]] = {
        "observed": set(),
        "wealth_3_or_4_draw": set(),
        "hu_white_baotou": set(),
        "oracle_piao": set(),
        "p3_trigger": set(),
    }
    opportunities = []
    problems = []
    for request in requests:
        observation = request.observation
        hand_key = (observation.game_id, observation.round_no)
        hand_sets["observed"].add(hand_key)
        counts["focal_requests"] += 1
        if observation.phase != "draw":
            counts["response_windows"] += 1
            continue
        counts["focal_draw_windows"] += 1
        rivers = sum(len(river) for river in observation.discards)
        counts["initial_draw_windows" if rivers == 0 else "midgame_draw_windows"] += 1
        wealth_count = _wealth_count(observation)
        counts["draw_wealth_" + str(wealth_count)] += 1
        if wealth_count not in (3, 4):
            continue
        counts["wealth_3_or_4_draw_windows"] += 1
        counts["wealth_{0}_draw_windows".format(wealth_count)] += 1
        hand_sets["wealth_3_or_4_draw"].add(hand_key)
        baotou = observation.rule_state.baotou is True
        counts["wealth_3_or_4_baotou_draw_windows"] += int(baotou)
        legal = {item.action_key for item in request.rules.legal_candidates}
        hu_white = {"hu", "discard:白"} <= legal
        counts["hu_white_windows"] += int(hu_white)
        counts["hu_white_baotou_windows"] += int(hu_white and baotou)
        if not (hu_white and baotou):
            continue
        hand_sets["hu_white_baotou"].add(hand_key)
        oracle = build_one_draw_self_win_oracle(request)
        complete = not oracle.issues and {item.action_key for item in oracle.values} == legal
        counts["oracle_complete"] += int(complete)
        if not complete:
            counts["oracle_incomplete"] += 1
            problems.extend(oracle.issues[:4])
            continue
        best = max(item.value for item in oracle.values)
        optimal = sorted(item.action_key for item in oracle.values if item.value == best)
        oracle_piao = "discard:白" in optimal
        counts["oracle_piao_windows"] += int(oracle_piao)
        counts["oracle_hu_windows"] += int("hu" in optimal)
        if oracle_piao:
            hand_sets["oracle_piao"].add(hand_key)
        try:
            plan = await candidate.choose(
                request, DecisionBudget(810.0, 820.0, 830.0)
            )
        except Exception as exc:  # noqa: BLE001 - 测量失败必须落证据
            counts["candidate_errors"] += 1
            problems.append(type(exc).__name__ + ": " + str(exc)[:240])
            continue
        overlays = _overlay_records(plan)
        triggered = any(item.get("triggered") is True for item in overlays)
        counts["p3_overlay_trigger_windows"] += int(triggered)
        counts["p3_piao_choices"] += int(
            plan.candidates[0].action_key == "discard:白"
        )
        if triggered:
            hand_sets["p3_trigger"].add(hand_key)
        opportunities.append({
            "window_identity_sha256": digest_value({
                "decision_id": request.decision_id,
                "game_id": observation.game_id,
                "round_no": observation.round_no,
                "trigger_seq": request.trigger_seq,
                "seat": observation.seat,
            }),
            "window_key": window_key_to_json(request.window_key),
            "game_id": observation.game_id,
            "round_no": observation.round_no,
            "seat": observation.seat,
            "dealer_seat": observation.dealer_seat,
            "snapshot_seq": observation.snapshot_seq,
            "remaining_tile_count": observation.remaining_tile_count,
            "river_lengths": [len(river) for river in observation.discards],
            "meld_counts": [len(melds) for melds in observation.melds],
            "wealth_count": wealth_count,
            "oracle_optimal": optimal,
            "candidate_action": plan.candidates[0].action_key,
            "overlay_triggered": triggered,
        })
    for name, values in hand_sets.items():
        counts[name + "_hands"] = len(values)
    return {
        "counts": dict(sorted(counts.items())),
        "opportunities": opportunities,
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
        candidate_scorer=ActionValueScorer("r18-p3-exposure-unused", source),
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
    runtime_counts: Counter[str] = Counter()
    for table in stage.get("tables") or []:
        runtime_counts.update(table.get("result", {}).get("runtime_counts") or {})
    return {
        "source": dict(source_row),
        "status": stage.get("status"),
        "error": stage.get("error"),
        "tables": len(stage.get("tables") or []),
        "completed_hands": completed_hands,
        "runtime_counts": dict(sorted(runtime_counts.items())),
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
        step_id="r18-p3:natural-exposure",
        account="tables_full",
        amount=PLANNED_TABLES - completed_tables,
        note="稳定V2单臂自然机会暴露率",
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
                        raise RuntimeError("请求复算出现问题")
                    write_json(source_path(row), result)
                    executed += TABLES_PER_SOURCE
                    completed_tables += TABLES_PER_SOURCE
                    if completed_tables % 64 == 0 or completed_tables == PLANNED_TABLES:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": PLANNED_TABLES,
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001 - 保留来源失败
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
        "schema": "r18-p3-natural-exposure-run/1",
        "source_files": len(files),
        "actual_tables": actual,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or actual != PLANNED_TABLES or len(files) != len(sources()):
        raise RuntimeError("自然暴露率执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": actual}, ensure_ascii=False))


def wilson(k: int, n: int) -> list[float] | None:
    if n <= 0:
        return None
    z = 1.959963984540054
    p = k / n
    denominator = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denominator
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def rate(k: int, n: int) -> dict[str, Any]:
    return {
        "events": k,
        "denominator": n,
        "rate": None if n == 0 else k / n,
        "wilson_95": wilson(k, n),
    }


def analyze() -> None:
    verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary["failures"] or run_summary["actual_tables"] != PLANNED_TABLES:
        raise ValueError("自然暴露率运行不完整")
    counts: Counter[str] = Counter()
    runtime: Counter[str] = Counter()
    opportunities = []
    completed_hands = 0
    source_rows = []
    for row in sources():
        document = json.loads(source_path(row).read_text(encoding="utf-8"))
        completed_hands += int(document["completed_hands"])
        counts.update(document["audit"]["counts"])
        runtime.update(document["runtime_counts"])
        opportunities.extend(document["audit"]["opportunities"])
        source_rows.append({
            **row,
            "tables": document["tables"],
            "completed_hands": document["completed_hands"],
            "counts": document["audit"]["counts"],
        })
    tables = int(run_summary["actual_tables"])
    draw_windows = counts["focal_draw_windows"]
    result = {
        "schema": "r18-p3-natural-exposure-result/1",
        "status": "COMPLETE_EXPOSURE_ESTIMATE",
        "tables": tables,
        "completed_hands": completed_hands,
        "focal_requests": counts["focal_requests"],
        "focal_draw_windows": draw_windows,
        "runtime_counts": dict(sorted(runtime.items())),
        "events": dict(sorted(counts.items())),
        "rates": {
            "wealth_3_or_4_draw_per_draw_window": rate(
                counts["wealth_3_or_4_draw_windows"], draw_windows
            ),
            "hu_white_baotou_per_draw_window": rate(
                counts["hu_white_baotou_windows"], draw_windows
            ),
            "oracle_piao_per_draw_window": rate(
                counts["oracle_piao_windows"], draw_windows
            ),
            "p3_trigger_per_draw_window": rate(
                counts["p3_overlay_trigger_windows"], draw_windows
            ),
            "wealth_3_or_4_hand_per_completed_hand": rate(
                counts["wealth_3_or_4_draw_hands"], completed_hands
            ),
            "oracle_piao_hand_per_completed_hand": rate(
                counts["oracle_piao_hands"], completed_hands
            ),
            "p3_trigger_hand_per_completed_hand": rate(
                counts["p3_trigger_hands"], completed_hands
            ),
            "p3_trigger_hand_per_table": rate(counts["p3_trigger_hands"], tables),
        },
        "opportunity_records": opportunities,
        "interpretation": {
            "trajectory": "全部牌局由稳定V2焦点策略运行；P3只赛后读取正式请求",
            "use": "估计稀有机会预算与桌赛漏检风险；不比较P3/V2赛事效果",
            "interval_limit": "Wilson区间把窗口视作二项试验，未校正同桌/同手牌聚类；手牌级率同时报告",
        },
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "source-counts.json"), {"rows": source_rows})
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
