#!/usr/bin/env python3
"""G13 独立结算版自然面板入口；保留冻结 G11 驱动源码和旧阶段文件。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

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
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Sequence


ROOT = _PROJECT_ROOT
for entry in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROOT / "review/llm-guided-heuristic-route-2026-09-15/tools"),
              _project_file(_PROJECT_ROOT, ROOT / "review/r18-four-arm-evaluation-2026-09-23")):
    sys.path.insert(0, str(entry))

import sitin_natural_panel as natural  # noqa: E402
import paired_study  # noqa: E402
from g13_hand_accounting import HandAccountingEngine, summarize_hands  # noqa: E402
from hangma_bot.offline.evaluate import drive_match  # noqa: E402


HERE = Path(__file__).resolve().parent
CONTRACT = paired_study.CONTRACT
PILOT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g13-hand-accounting-pilot-20260927')
OLD_RUN = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g11-shape-risk-development-20260927/stages')


def digest(path: Path) -> str:
    """将研究运行器、父代及冻结对照文件与内容摘要绑定。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute_accounted_natural_table(*, plan: Any, policies_by_seat: Sequence[Any],
                                    versions_block: Mapping[str, Any], step_limit: int,
                                    value_limits: Any,
                                    stage_situation: Any = None) -> dict[str, Any]:
    """用原自然面板的组合根/驱动运行一桌，另采集公开导出的赛后单局结算。"""

    from hangma_bot import bootstrap
    from hangma_bot.application.deadline import BudgetPolicy, ManualClock
    from hangma_bot.hangma.engine import HangmaRules

    rules_config = natural.RuleConfig(
        ruleset_version=str(versions_block["ruleset_version"]),
        base_score=int(versions_block["base_score"]),
        you_cai_bi_kao=bool(versions_block["you_cai_bi_kao"]))
    tournament_config = natural.TournamentConfig(
        max_games=1, rounds_per_game=int(versions_block["rounds_per_game"]),
        rules=rules_config, timing=natural.TimingConfig(**dict(natural.stage.DEFAULT_TIMING)))
    runtime = getattr(bootstrap, natural.BOOTSTRAP_RUNTIME_HOOK)(
        "matches", natural.MatchExperiment(
            kind="matches", clock_mode=str(versions_block["clock_mode"]),
            baseline=natural.PolicyDeclaration(policy_id="natural-slot-a", name="panel", weights=()),
            challenger=natural.PolicyDeclaration(policy_id="natural-slot-b", name="panel", weights=()),
            opponents=tuple(natural.PolicyDeclaration(
                policy_id=f"natural-slot-{index}", name="panel", weights=())
                for index in (3, 4, 5)),
            tournament_config=tournament_config,
            seeds=(natural.MatchSeedSpec(seed=plan.seed, scenario_id=plan.scenario_id),),
            seat_permutations=(natural.stage.IDENTITY_PERMUTATION,), initial_dealer=0,
            initial_scores=(0, 0, 0, 0)))
    if not isinstance(runtime, Mapping):
        raise RuntimeError("组合根未装配 matches 运行时")
    clock = ManualClock(start_monotonic=800.0, wait_scale=1.0)
    now_monotonic = (clock.now if str(versions_block["clock_mode"]) == "logical"
                     else time.monotonic)
    rules = HangmaRules(rules_config)
    spec = runtime["spec_factory"](
        match_id=plan.match_id, scenario_id=plan.scenario_id,
        config=tournament_config, seed=plan.seed,
        initial_dealer=plan.initial_dealer, initial_scores=[0, 0, 0, 0])
    engine = HandAccountingEngine(runtime["engine"])
    version_pairs = [
        ("clock_mode", str(versions_block["clock_mode"])),
        ("driver", "g13_accounted_panel.py (offline.evaluate drive_match)"),
        ("hand_accounting_schema", "g13-hand-accounting/1"),
        ("hand_accounting_source_sha256", digest(_project_file(_PROJECT_ROOT, HERE / "g13_hand_accounting.py"))),
        ("panel_policy_names", sorted(set(str(name) for name in plan.policy_names))),
        ("rules_hash", natural.compute_rules_hash(ROOT)),
        ("ruleset_version", rules_config.ruleset_version),
        ("value_limits", json.dumps({
            "max_expansions": value_limits.max_expansions,
            "max_routes_per_candidate": value_limits.max_routes_per_candidate,
        }, sort_keys=True)),
    ]
    for seat, policy in enumerate(policies_by_seat):
        version_pairs.append((f"natural_seat_policy:{seat}",
                              str(getattr(policy, "policy_id", type(policy).__name__))))
        if getattr(policy, "max_operations", None) is not None:
            version_pairs.append((f"natural_seat_max_operations:{seat}",
                                  str(policy.max_operations)))
    started = time.monotonic()
    outcome = asyncio.run(drive_match(
        engine=engine, spec=spec, policies_by_seat=tuple(policies_by_seat), rules=rules,
        choice_factory=runtime["choice_factory"],
        config=natural.MatchDriverConfig(
            clock_mode=str(versions_block["clock_mode"]), step_limit=int(step_limit),
            budget_policy=BudgetPolicy(), competition_tournament_id=plan.scenario_id),
        now_monotonic=now_monotonic, wall_clock=None, value_limits=value_limits,
        stage_situation=stage_situation))
    wall_ms = (time.monotonic() - started) * 1000.0
    policy_execution = natural.execution_audit.summarize(
        outcome.decisions,
        policy_ids_by_seat=[str(getattr(policy, "policy_id", type(policy).__name__))
                            for policy in policies_by_seat])
    version_pairs.extend((
        ("policy_execution_schema", natural.execution_audit.SCHEMA),
        ("policy_execution_sha256", natural.execution_audit.digest(policy_execution)),
    ))
    result = natural.build_match_result(
        match_id=plan.match_id, scenario_id=plan.scenario_id, pair_id=plan.pair_id,
        config=tournament_config, policy_ids_by_seat=plan.seats(),
        seat_permutation=plan.permutation, initial_scores_physical=(0, 0, 0, 0),
        outcome=outcome, versions=tuple(sorted(version_pairs)),
        source_refs=({"note": "natural panel table with postgame hand accounting",
                      "producer": "g13_accounted_panel.py"},),
        result_id="r-" + plan.match_id, source_kind="simulation")
    row = {"table_id": plan.table_id, "seed": int(plan.seed),
           "match_status": outcome.status, "wall_ms": round(wall_ms, 3),
           "scores_by_seat": (None if outcome.final_scores is None
                              else [int(value) for value in outcome.final_scores]),
           "result": result.to_json(), "policy_execution": policy_execution}
    if outcome.status == "complete" and outcome.final_scores is not None:
        focal_seat = plan.seats().index(natural.FOCAL_PARTICIPANT)
        row["hand_account"] = summarize_hands(
            engine.hands, focal_seat=focal_seat,
            initial_scores=(0, 0, 0, 0), final_scores=outcome.final_scores,
            expected_hands=tournament_config.rounds_per_game)
        # 仅在逐局积分与桌末分全部对账后保存最小赛后结算字段，供候选收入归因。
        row["hand_records"] = list(engine.hands)
    return row


def run_accounted_stage(*, plans: Sequence[Any], candidate_policy_factory: Callable,
                        opponent_policies: Sequence[str], versions_block: Mapping[str, Any],
                        step_limit: int, value_limits: Any) -> dict[str, Any]:
    """在单进程内临时注入研究桌执行器；原模块源码/全局函数在返回前恢复。"""

    accounts: dict[str, dict[str, Any]] = {}
    records: dict[str, list[dict[str, Any]]] = {}
    original = natural.execute_natural_table

    def execute(**kwargs: Any) -> dict[str, Any]:
        row = execute_accounted_natural_table(**kwargs)
        if "hand_account" in row:
            accounts[row["table_id"]] = row["hand_account"]
            records[row["table_id"]] = row["hand_records"]
        return row

    # 本入口每进程串行执行一个阶段；禁止在同一 Python 进程并发调用此函数。
    natural.execute_natural_table = execute
    try:
        stage = natural.run_arm_stage(
            arm="candidate", plans=plans, candidate_scorer=None,
            candidate_policy_factory=candidate_policy_factory,
            opponent_policies=opponent_policies, versions_block=versions_block,
            step_limit=step_limit, value_limits=value_limits)
    finally:
        natural.execute_natural_table = original
    for table in stage["tables"]:
        account = accounts.get(table["table_id"])
        if account is not None:
            table["hand_account"] = account
            table["hand_records"] = records[table["table_id"]]
        elif table["match_status"] == "complete":
            stage.update(status="error", usable=False,
                         error="已完成桌缺逐单局收益拆账")
    return stage


def write_json(path: Path, data: Any) -> None:
    """原子写入研究证据，不覆盖已有文件。"""

    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                    indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def pilot(*, mix: str, root_index: int, seat: int, panel_seed: int) -> dict[str, Any]:
    """用 G11 只读旧阶段作机械对照；旧根不用于 G13 候选收益推断。"""

    if mix not in ("H", "M") or not 0 <= seat < 4 or root_index < 1:
        raise ValueError("需要 H/M、0..3 座、正整数根")
    old_manifest = json.loads((_project_file(_PROJECT_ROOT, OLD_RUN.parent / "manifest.json")).read_text(encoding="utf-8"))
    frozen_runner = 'tools/offline/sitin/sitin_natural_panel.py'
    old_runner_hash = digest(_project_file(_PROJECT_ROOT, ROOT / frozen_runner))
    if (old_manifest["panel_seed"] != panel_seed
            or old_manifest["input_identity"][frozen_runner] != old_runner_hash):
        raise ValueError("旧阶段清单的面板种子或自然运行器源码摘要漂移")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root_index,
        focal_seat=seat, panel_seed=panel_seed)
    versions = natural.stage.contract_versions_block(contract)
    stage = run_accounted_stage(
        plans=plans, candidate_policy_factory=paired_study.policy_factory("r18_v2"),
        opponent_policies=contract["panel"]["opponent_scenarios"][mix]["opponent_policies"],
        versions_block=versions, step_limit=int(contract["stop"]["step_limit"]),
        value_limits=paired_study.LIMITS)
    old_path = _project_file(_PROJECT_ROOT, OLD_RUN / f"{mix}-r{root_index:04d}-s{seat}-r18_v2.json")
    old = json.loads(old_path.read_text(encoding="utf-8"))["stage"]
    if stage["status"] != "complete" or len(stage["tables"]) != len(old["tables"]):
        raise ValueError("新旧阶段未完成或桌数不一致")
    checks = []
    for now, before in zip(stage["tables"], old["tables"]):
        checks.append({"table_id": now["table_id"],
                       "same_scores": now["scores_by_seat"] == before["scores_by_seat"],
                       "same_runtime_counts": (now["result"]["runtime_counts"] ==
                                               before["result"]["runtime_counts"]),
                       "same_policy_execution": (now["policy_execution"] ==
                                                 before["policy_execution"]),
                       "same_identity": (now["seed"] == before["seed"] and
                                         now["table_id"] == before["table_id"] and
                                         now["result"]["game_key"] ==
                                         before["result"]["game_key"]),
                       "accounted_hands": now["hand_account"]["complete_hands"]})
    if not all(all(value is True for key, value in row.items() if key.startswith("same_"))
               and row["accounted_hands"] == 8 for row in checks):
        raise ValueError("新旧运行的积分、运行计数、策略调用或身份发生偏移")
    if stage["focal_stage_score"] != old["focal_stage_score"]:
        raise ValueError("新旧阶段本人积分发生偏移")
    if (stage["execution_review"] != old["execution_review"]
            or stage["stage_totals_by_participant"] != old["stage_totals_by_participant"]
            or stage["u_interval"] != old["u_interval"]):
        raise ValueError("新旧阶段执行审计、参赛者积分或晋级指标发生偏移")
    return {"schema": "g13-accounted-panel-pilot/1", "mix": mix,
            "root_index": root_index, "seat": seat, "panel_seed": panel_seed,
            "old_stage_sha256": digest(old_path),
            "old_runner_sha256": old_runner_hash,
            "new_runner_sha256": digest(_project_file(_PROJECT_ROOT, HERE / "g13_accounted_panel.py")),
            "accounting_source_sha256": digest(_project_file(_PROJECT_ROOT, HERE / "g13_hand_accounting.py")),
            "checks": checks, "stage": stage,
            "boundary": "旧 G11 根只供无行为偏移的机械对账，不用于新候选收益。"}


def main() -> None:
    """按指定旧 H/M 阶段运行一次结算版机械对照。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mix", choices=("H", "M"), required=True)
    parser.add_argument("--root-index", type=int, default=1)
    parser.add_argument("--seat", type=int, default=0)
    parser.add_argument("--panel-seed", type=int, default=2026110601)
    parser.add_argument("--out", type=Path, default=PILOT)
    args = parser.parse_args()
    result = pilot(mix=args.mix, root_index=args.root_index,
                   seat=args.seat, panel_seed=args.panel_seed)
    target = args.out / f"{args.mix}-r{args.root_index:04d}-s{args.seat}.json"
    write_json(target, result)
    print(json.dumps({"target": str(target), "checks": result["checks"]},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
