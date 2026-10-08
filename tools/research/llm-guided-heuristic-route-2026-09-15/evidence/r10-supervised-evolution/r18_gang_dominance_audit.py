"""R18 补杠支配条件审计：验证“任意补牌仍可胡”不是重采样失效。

输入是已冻结的四个“立即胡 vs 补杠”自然状态及 32 个未来牌墙键。本脚本
只经模拟器公开重建/推进/单局导出入口读取教师事实；候选仍只能消费规则模块
投影的 ``CandidateFacts`` 与 ``CandidateValueFacts``。
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
import r18_gang_chain_future_order as prior  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.actions import CANONICAL_TILE_CODES  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-gang-dominance-audit-01-20260922')
PRIOR = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-gang-chain-future-order-01-20260922')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def positive_targets() -> list[dict[str, Any]]:
    """冻结全部四个代理推荐补杠、V2 立即胡的状态。"""

    return [
        row for row in prior.targets()
        if row["stratum"] == "proxy_promotes_gang"
    ]


def row_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rows" / "{0}-wall-{1:02d}.json".format(target["target_id"], index))


def prepare() -> None:
    """冻结四状态、32 个共同未来牌墙键和支配判据。"""

    if OUT.exists():
        raise SystemExit("补杠支配审计目录已存在；拒绝覆盖")
    previous = json.loads((_project_file(_PROJECT_ROOT, PRIOR / "result.json")).read_text(encoding="utf-8"))
    if previous.get("status") != "COMPLETE_GANG_CHAIN_FUTURE_ORDER":
        raise ValueError("跨未来牌墙结果尚未完成")
    selected = positive_targets()
    if len(selected) != 4:
        raise ValueError("补杠正向状态应为 4 个")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "rows")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-gang-dominance-audit-01",
        accounts={"tables_full": len(selected) * prior.ROLLOUTS_PER_STATE},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "四个补杠状态的32墙收益恒定；排除重采样无效并核对局部规则路径",
        "scope": "4状态×32未来牌墙；强制补杠后读取公开补牌窗口并立即胡，导出本单局结算",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-gang-dominance-audit-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=[
            Path(__file__), Path(prior.__file__), prior.CONTRACT,
            _project_file(_PROJECT_ROOT, PRIOR / "manifest.json"), _project_file(_PROJECT_ROOT, PRIOR / "result.json"),
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
        ]),
        "prior_manifest_sha256": digest(_project_file(_PROJECT_ROOT, PRIOR / "manifest.json")),
        "prior_result_sha256": digest(_project_file(_PROJECT_ROOT, PRIOR / "result.json")),
        "targets": [row["target_id"] for row in selected],
        "sample_keys": [
            "r18-gang-future-order-{0:02d}".format(index)
            for index in range(1, prior.ROLLOUTS_PER_STATE + 1)
        ],
        "planned_partial_hands": len(selected) * prior.ROLLOUTS_PER_STATE,
        "workers": 8,
        "dominance_requirements": [
            "原窗口hu与added gang同时合法，规则价值覆盖complete且无issue",
            "added gang补牌前standard_shanten_after=0，标准有效牌码覆盖全部34种规范牌",
            "杠路线是replacement且条件结算本座得分严格高于立即胡",
            "32个确定性重排至少观察到2种实际补牌，且每种补牌后hu合法",
            "补杠后立即胡的公开单局结算逐项等于规则条件结算",
        ],
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "partial_hands": len(selected) * 32}, ensure_ascii=False))


def verify_manifest() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["prior_manifest_sha256"] != digest(_project_file(_PROJECT_ROOT, PRIOR / "manifest.json")):
        raise ValueError("跨未来牌墙清单漂移")
    if manifest["prior_result_sha256"] != digest(_project_file(_PROJECT_ROOT, PRIOR / "result.json")):
        raise ValueError("跨未来牌墙结果漂移")
    guard.verify(manifest["runtime"])
    return manifest, positive_targets()


def _public_fact_audit(target: Mapping[str, Any]) -> dict[str, Any]:
    """只读截取窗口公开观察与规则事实，形成可部署的支配条件读数。"""

    snapshot = json.loads(prior.snapshot_path(target).read_text(encoding="utf-8"))
    contract = json.loads(prior.CONTRACT.read_text(encoding="utf-8"))
    rules = HangmaRules(prior.core.rule_config_from_contract(contract))
    runtime = prior.opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
        seed=int(snapshot["match_spec"]["seed"]),
        scenario_id=str(snapshot["match_spec"]["scenario_id"]),
    )
    engine, world = prior.opportunities.rebuild_world(
        rules=rules, snapshot=snapshot, value_limits=prior.LIMITS, runtime=runtime
    )
    decision = next(
        item for item in engine.frame(world).decisions
        if item.window_key == prior.window_key_from_json(target["window_key"])
    )
    analysis = rules.analyze(decision.observation, value_limits=prior.LIMITS)
    by_key = {item.action_key: item for item in analysis.legal_candidates}
    hu = by_key[str(target["reference_action"])]
    gang = by_key[str(target["intervention_action"])]
    immediate = hu.value_facts.immediate_settlement if hu.value_facts else None
    routes = tuple(gang.value_facts.routes) if gang.value_facts else ()
    route = routes[0] if len(routes) == 1 else None
    standard_codes = {
        item.code for item in (gang.facts.standard_useful_tiles or ())
    } if gang.facts is not None else set()
    focal = int(target["focal_physical_seat"])
    return {
        "target_id": target["target_id"],
        "hu_action": hu.action_key,
        "gang_action": gang.action_key,
        "gang_kind": getattr(gang.action.kind, "value", str(gang.action.kind)),
        "coverage": None if gang.value_facts is None else gang.value_facts.coverage.value,
        "issues": [] if gang.value_facts is None else list(gang.value_facts.issues),
        "replacement_draw_unknown": None if gang.facts is None else gang.facts.replacement_draw_unknown,
        "standard_shanten_after": None if gang.facts is None else gang.facts.standard_shanten_after,
        "standard_useful_code_count": len(standard_codes),
        "standard_useful_codes_are_all_canonical": standard_codes == set(CANONICAL_TILE_CODES),
        "immediate_hu": None if immediate is None else {
            "fan": immediate.fan,
            "details": list(immediate.details),
            "score_delta": list(immediate.score_delta),
            "focal_score": immediate.score_delta[focal],
        },
        "gang_route": None if route is None else {
            "draw_kind": route.conditions.draw_kind,
            "shanten": route.shanten,
            "fan": route.conditional_settlement.fan,
            "details": list(route.conditional_settlement.details),
            "score_delta": list(route.conditional_settlement.score_delta),
            "focal_score": route.conditional_settlement.score_delta[focal],
        },
    }


def execute_one(target: Mapping[str, Any], index: int, sample_key: str) -> dict[str, Any]:
    """补杠一次，核对实际补牌、V2 决策和本单局结算。"""

    snapshot = json.loads(prior.snapshot_path(target).read_text(encoding="utf-8"))
    contract = json.loads(prior.CONTRACT.read_text(encoding="utf-8"))
    rules = HangmaRules(prior.core.rule_config_from_contract(contract))
    runtime = prior.opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
        seed=int(snapshot["match_spec"]["seed"]),
        scenario_id=str(snapshot["match_spec"]["scenario_id"]),
    )
    engine, world = prior.opportunities.rebuild_world(
        rules=rules, snapshot=snapshot, value_limits=prior.LIMITS, runtime=runtime
    )
    world = engine.resample_future_drawable_wall(world, sample_key=sample_key)
    frame = engine.frame(world)
    target_window = prior.window_key_from_json(target["window_key"])
    decision = next(item for item in frame.decisions if item.window_key == target_window)
    analysis = rules.analyze(decision.observation, value_limits=prior.LIMITS)
    gang = next(
        item for item in analysis.legal_candidates
        if item.action_key == target["intervention_action"]
    )
    world = engine.advance(
        world, frame.revision,
        (runtime["choice_factory"](decision.window_key, gang.action),),
    )
    replacement_frame = engine.frame(world)
    replacement = next(
        item for item in replacement_frame.decisions
        if item.window_key.seat == int(target["focal_physical_seat"])
    )
    replacement_analysis = rules.analyze(
        replacement.observation, value_limits=prior.LIMITS
    )
    hu = next(
        (item for item in replacement_analysis.legal_candidates if item.action_key == "hu"),
        None,
    )
    v2 = ComparableHeuristicPolicyV2(monotonic=lambda: 800.0)
    request = prior.opportunities.real_window_request(
        decision=replacement,
        analysis=replacement_analysis,
        match_id=str(snapshot["match_spec"]["match_id"]),
        config=prior.opportunities._driver_config(),
        now_monotonic=lambda: 800.0,
    )
    plan = asyncio.run(v2.choose(
        request,
        prior.opportunities._driver_config().budget_policy.build(
            800.0, replacement.timeout_seconds
        ),
    ))
    if hu is None:
        return {
            "target_id": target["target_id"], "rollout_index": index,
            "sample_key": sample_key,
            "replacement_tile": replacement.observation.drawn_tile.code,
            "hu_legal": False, "v2_action": None if not plan.candidates else plan.candidates[0].action_key,
            "mechanical_ok": False,
        }
    world = engine.advance(
        world, replacement_frame.revision,
        (runtime["choice_factory"](replacement.window_key, hu.action),),
    )
    hand = engine.export_hand(
        world, int(target["round_no"]),
        match_id=str(snapshot["match_spec"]["match_id"]),
    )
    return {
        "schema": "r18-gang-dominance-audit-row/1",
        "target_id": target["target_id"],
        "rollout_index": index,
        "sample_key": sample_key,
        "replacement_tile": replacement.observation.drawn_tile.code,
        "hu_legal": True,
        "v2_action": None if not plan.candidates else plan.candidates[0].action_key,
        "chain_count": replacement.observation.rule_state.chain_count,
        "chain_piao": replacement.observation.chain_piao,
        "fan": hand["fan"],
        "details": hand["details"],
        "score_delta": hand["score_delta"],
        "winner_seat": hand["winner_seat"],
        "mechanical_ok": hand["winner_seat"] == int(target["focal_physical_seat"]),
    }


def run() -> None:
    """并行核对 128 个补牌分支，支持断点续跑。"""

    manifest, selected = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    facts = [_public_fact_audit(target) for target in selected]
    write_json(_project_file(_PROJECT_ROOT, OUT / "public-facts.json"), {
        "schema": "r18-gang-dominance-public-facts/1", "states": facts,
    })
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed = 0
    for target in selected:
        for index, key in enumerate(manifest["sample_keys"], 1):
            path = row_path(target, index)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if not row.get("mechanical_ok"):
                    raise ValueError("既有支配审计行机械失败：" + str(path))
                completed += 1
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:gang-dominance-audit",
        account="tables_full",
        amount=len(pending),
        note="按完整桌等价预算保守计费的补杠后单局局部核对",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {
                pool.submit(execute_one, target, index, key): (target, index)
                for target, index, key in pending
            }
            for future in concurrent.futures.as_completed(futures):
                target, index = futures[future]
                result = None
                try:
                    result = future.result()
                    if not result["mechanical_ok"]:
                        raise RuntimeError("补杠局部路径机械条件失败")
                    write_json(row_path(target, index), result)
                    executed += 1
                    completed += 1
                    if completed % 32 == 0:
                        print(json.dumps({
                            "completed": completed,
                            "planned": manifest["planned_partial_hands"],
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    if result is None:
                        usage_unknown = True
                    failures.append({
                        "target_id": target["target_id"], "rollout_index": index,
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按成功局部核对数结算")
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-gang-dominance-audit-run/1",
        "completed": completed,
        "planned": manifest["planned_partial_hands"],
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or completed != manifest["planned_partial_hands"]:
        raise RuntimeError("补杠支配审计执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "partial_hands": completed}, ensure_ascii=False))


def analyze() -> None:
    """将公开事实证明与实际多补牌路径逐状态对账。"""

    manifest, selected = verify_manifest()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary["failures"] or run_summary["completed"] != manifest["planned_partial_hands"]:
        raise ValueError("补杠支配审计执行不完整")
    fact_rows = {
        row["target_id"]: row
        for row in json.loads((_project_file(_PROJECT_ROOT, OUT / "public-facts.json")).read_text(encoding="utf-8"))["states"]
    }
    states = []
    for target in selected:
        fact = fact_rows[target["target_id"]]
        rows = [
            json.loads(row_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, prior.ROLLOUTS_PER_STATE + 1)
        ]
        route = fact["gang_route"]
        immediate = fact["immediate_hu"]
        checks = {
            "added_gang": fact["gang_kind"] == "added",
            "coverage_complete_no_issues": fact["coverage"] == "complete" and not fact["issues"],
            "replacement_unknown": fact["replacement_draw_unknown"] is True,
            "pre_replacement_shanten_zero": fact["standard_shanten_after"] == 0,
            "all_34_tile_codes_useful": fact["standard_useful_codes_are_all_canonical"],
            "replacement_route": route is not None and route["draw_kind"] == "replacement",
            "route_focal_score_strictly_higher": route is not None and immediate is not None and route["focal_score"] > immediate["focal_score"],
            "replacement_tiles_varied": len({row["replacement_tile"] for row in rows}) >= 2,
            "all_replacements_hu_legal": all(row["hu_legal"] for row in rows),
            "v2_hu_after_every_replacement": all(row["v2_action"] == "hu" for row in rows),
            "settlement_matches_projected_route": all(
                row["fan"] == route["fan"]
                and row["details"] == route["details"]
                and row["score_delta"] == route["score_delta"]
                for row in rows
            ),
        }
        states.append({
            "target_id": target["target_id"],
            "distinct_replacement_tiles": len({row["replacement_tile"] for row in rows}),
            "replacement_tiles": sorted({row["replacement_tile"] for row in rows}),
            "immediate_hu_focal_score": immediate["focal_score"],
            "gang_hu_focal_score": route["focal_score"],
            "local_gain": route["focal_score"] - immediate["focal_score"],
            "checks": checks,
            "passed": all(checks.values()),
        })
    all_passed = all(row["passed"] for row in states)
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "r18-gang-dominance-audit-result/1",
        "status": "COMPLETE_GANG_DOMINANCE_AUDIT",
        "states": states,
        "all_four_states_passed": all_passed,
        "decision": (
            "FREEZE_PUBLIC_DOMINANCE_PREDICATE_AND_COLLECT_INDEPENDENT_CONFIRMATION"
            if all_passed else "REJECT_PUBLIC_DOMINANCE_PREDICATE"
        ),
        "author_task_open": False,
        "interpretation": "恒定收益来自规则已证明的任意牌补杠后仍胡及杠开倍数；实际补牌值发生变化，排除重采样无效。仍须在全新自然状态冻结确认后才写候选。",
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, OUT / "result.json")).read_text(encoding="utf-8")), ensure_ascii=False, indent=2))


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
