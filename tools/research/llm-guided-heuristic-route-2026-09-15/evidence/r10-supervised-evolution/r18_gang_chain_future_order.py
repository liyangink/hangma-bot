"""R18 杠链：自然决策状态的共同未来牌墙配对复核。

本批把自然探针冻结的七个杠/不杠直接分歧重建到精确决策边界；每个状态
重排 32 个尚未摸取的可摸区，并在同一重排下分别强制 V2 动作与一次补牌
代理动作。策略只接收 ``PlayerObservation``；完整世界只由模拟器在离线教师
侧重建和重排。本批用于校准方向、发现正负控，不直接准入或生成候选。
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
import math
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

import claim_counterfactual_pilot as core  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.serialization import (  # noqa: E402
    window_key_from_json,
    window_key_to_json,
)
from hangma_bot.offline.evaluate import seat_policies_from  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-gang-chain-future-order-01-20260922')
TARGETS_FILE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-gang-chain-counterfactual-01-20260922/targets.json')
PROBE_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-gang-chain-natural-probe-02-20260922/result.json')
CONTRACT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/contracts/group-dev-v1.json')
LIMITS = ValueAnalysisLimits(max_expansions=20_000, max_routes_per_candidate=256)
ROLLOUTS_PER_STATE = 32
BOOTSTRAP_REPLICATES = 20_000


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    """写入排序、缩进且以换行结束的 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def targets() -> list[dict[str, Any]]:
    """读取冻结的七个自然直接分歧，不按既有续打结果筛选。"""

    return list(json.loads(TARGETS_FILE.read_text(encoding="utf-8"))["targets"])


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-wall-{1:02d}.json".format(
        target["target_id"], index
    ))


def source_paths() -> list[Path]:
    """列出会改变捕获、重建或续打语义的代码与冻结输入。"""

    import hangma_bot.offline.forced_action as forced_action
    import hangma_bot.simulation.engine as simulation_engine
    import hangma_bot.simulation.shuffle as simulation_shuffle

    return [
        Path(__file__), TARGETS_FILE, PROBE_RESULT, CONTRACT,
        Path(core.__file__), Path(natural.__file__), Path(opportunities.__file__),
        Path(forced_action.__file__), Path(simulation_engine.__file__),
        Path(simulation_shuffle.__file__),
    ]


def prepare() -> None:
    """冻结七个状态、32 个未来牌墙键、判据和预算。"""

    if OUT.exists():
        raise SystemExit("杠链跨未来牌墙目录已存在；拒绝覆盖")
    frozen = targets()
    if len(frozen) != 7:
        raise ValueError("冻结自然直接分歧应为 7 个")
    strata = Counter(str(row["stratum"]) for row in frozen)
    if strata != Counter({"proxy_promotes_gang": 4, "proxy_rejects_gang": 3}):
        raise ValueError("冻结分层漂移：" + repr(strata))
    sample_keys = [
        "r18-gang-future-order-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(frozen) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-gang-chain-future-order-01",
        accounts={"prefix_generation": len(frozen), "tables_full": planned_tables},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "自然杠链首尺只有单一后续牌墙；先隔离未来顺序方差",
        "scope": "冻结7个自然决策状态；每状态32个可摸区重排；V2动作与代理动作共同牌墙配对",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-gang-chain-future-order-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")]),
        "targets_sha256": digest(TARGETS_FILE),
        "probe_result_sha256": digest(PROBE_RESULT),
        "contract_sha256": digest(CONTRACT),
        "targets": len(frozen),
        "strata": dict(sorted(strata.items())),
        "rollouts_per_state": len(sample_keys),
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "workers": 8,
        "sampling_unit": "自然决策状态；未来牌墙变体只估计该状态条件均值，不冒充独立状态",
        "resampling_scope": "只重排当前局尚未摸取的可摸区；保留公开前缀、四家暗手、多重集和固定保留区",
        "teacher_scope": "给定真实隐藏分配的未来可摸顺序条件效果；不是隐藏手牌后验或精确Q值",
        "decision_rule": {
            "added_gang_vs_hu_support": "4个proxy_promotes_gang状态至少3个条件均值>0，且四状态均值的等权平均>0",
            "author_gate": "本批无论结果均不发作者任务；独立自然基础状态达到24个并冻结训练/确认切分后重审",
        },
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "targets": len(frozen),
        "rollouts_per_state": len(sample_keys), "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify_manifest() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对代码、合同和上游冻结输入没有漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["targets_sha256"] != digest(TARGETS_FILE):
        raise ValueError("杠链目标清单漂移")
    if manifest["probe_result_sha256"] != digest(PROBE_RESULT):
        raise ValueError("自然杠链探针结果漂移")
    if manifest["contract_sha256"] != digest(CONTRACT):
        raise ValueError("合同漂移")
    guard.verify(manifest["runtime"])
    return manifest, targets()


def _physical_policy_names(plan: Any) -> list[str]:
    """把计划中的逻辑策略名按换座映射为物理座位顺序。"""

    names = [""] * 4
    for logical, physical in enumerate(plan.permutation):
        names[int(physical)] = str(plan.policy_names[logical])
    return names


class ExactWindowCapture:
    """只在冻结 ``WindowKey`` 截取，并验证两动作仍由规则判为合法。"""

    def __init__(self, target: Mapping[str, Any]) -> None:
        self.target = dict(target)
        self.window_key = window_key_from_json(target["window_key"])
        self.hits = 0

    def __call__(self, request: Any) -> dict[str, Any] | None:
        if request.window_key != self.window_key:
            return None
        legal = sorted(item.action_key for item in request.rules.legal_candidates)
        expected = {
            str(self.target["reference_action"]),
            str(self.target["intervention_action"]),
        }
        missing = sorted(expected - set(legal))
        if missing:
            raise ValueError("冻结杠链动作已不合法：" + repr(missing))
        self.hits += 1
        return {
            "target_id": self.target["target_id"],
            "reference_action": self.target["reference_action"],
            "intervention_action": self.target["intervention_action"],
            "legal_action_keys": legal,
            "remaining_tile_count": request.observation.remaining_tile_count,
            "dealer_seat": request.observation.dealer_seat,
            "own_meld_count": len(request.observation.melds[request.observation.seat]),
        }


def capture_one(target: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    """用原自然桌计划与稳定 V2 合法前缀重建一个精确中局快照。"""

    source = target["source"]
    plans = natural.build_seat_stage_plans(
        contract=contract,
        opponent=str(source["mix"]),
        root_index=int(source["root_index"]),
        focal_seat=int(source["focal_seat"]),
        panel_seed=int(source["panel_seed"]),
    )
    plan = plans[int(source["table_no"]) - 1]
    if plan.table_id != source["table_id"]:
        raise ValueError("自然桌计划身份漂移")
    if plan.match_id != target["window_key"]["game_id"]:
        raise ValueError("自然桌 match_id 与冻结 WindowKey 不符")
    rules = HangmaRules(core.rule_config_from_contract(contract))
    opponent_names = opportunities.opponent_policy_names(contract, str(source["mix"]))
    logical = natural.arm_logical_policies(
        arm="baseline",
        candidate_scorer=None,
        logical_participants=plan.logical_participants,
        opponent_policies=opponent_names,
        monotonic=lambda: 800.0,
    )
    policies = seat_policies_from(logical, plan.permutation, plan.logical_participants)
    physical_names = _physical_policy_names(plan)
    focal_physical = int(target["focal_physical_seat"])
    if physical_names[focal_physical] != "focal-arm":
        raise ValueError("焦点物理座位与计划换座不符")
    verifier_names = [
        physical_names[seat] for seat in range(4) if seat != focal_physical
    ]
    runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(contract["versions"]["rounds_per_game"]),
        seed=int(plan.seed),
        scenario_id=str(plan.scenario_id),
    )
    capture = ExactWindowCapture(target)
    attempt = opportunities.run_real_prefix_attempt(
        runtime=runtime,
        rules=rules,
        predicate_id="r18_gang_exact_window",
        focal_seat=focal_physical,
        attempt_index=int(target["target_id"].split("-")[-1]),
        source_root_id=str(plan.scenario_id),
        match_id=str(plan.match_id),
        tournament_config=opportunities._snapshot_tournament_config(
            {"rounds_per_game": int(contract["versions"]["rounds_per_game"])}, rules
        ),
        seed=int(plan.seed),
        value_limits=LIMITS,
        behavior_policies_by_seat=policies,
        opponent_names=verifier_names,
        opponent_scenario=str(source["mix"]),
        capture_condition=capture,
    )
    if attempt.status != "hit" or capture.hits != 1:
        raise ValueError("未在原自然桌合法前缀命中冻结窗口")
    runtime_kind = opportunities.runtime_kind_of(runtime)
    snapshot = dict(opportunities.build_snapshot(
        prefix_source="v2_behavior",
        attempt=attempt,
        predicate_id="r18_gang_exact_window",
        focal_seat=focal_physical,
        opponent_scenario=str(source["mix"]),
        match_id=str(plan.match_id),
        stage_ledger={"completed_table_scores": []},
        remaining_schedule={
            "declared_endpoint": "current_table_complete",
            "remaining_tables_after_current": 0,
            "rounds_per_game": int(contract["versions"]["rounds_per_game"]),
            "tables_in_stage": 1,
        },
        panel_seed=int(source["panel_seed"]),
        tables_in_stage=1,
        rounds_per_game=int(contract["versions"]["rounds_per_game"]),
        runtime_evidence={
            "runtime_kind": runtime_kind,
            "engine_kind": opportunities.ENGINE_KIND_BY_RUNTIME_KIND[runtime_kind],
            "execution_kind": opportunities.execution_kind_for(
                prefix_source="v2_behavior", runtime=runtime
            ),
            "runtime_source": str(runtime.get("runtime_entry")),
            "engine_identity": dict(runtime.get("engine_identity") or {}),
            "real_tables": True,
        },
        witness_entry="r18_gang_natural_exact_window",
    ))
    # 本实验只续打当前自然桌；把真实换座后的物理参赛者顺序写回快照账。
    snapshot["seating"]["participant_ids_by_seat"] = list(plan.seats())
    snapshot["stage_plan"]["participant_ids_by_seat"] = list(plan.seats())
    snapshot["capture"] = {
        "target": dict(target),
        "table_seed": int(plan.seed),
        "table_scenario_id": str(plan.scenario_id),
        "physical_policy_names": physical_names,
        "opponent_names_in_physical_order": verifier_names,
        "prefix_steps": len(attempt.prefix),
        "witness": dict(attempt.predicate_witness or {}),
    }
    # 立即走公开重建入口核对，确保持久化快照可独立恢复到相同帧。
    engine, world = opportunities.rebuild_world(
        rules=rules, snapshot=snapshot, value_limits=LIMITS, runtime=runtime
    )
    rebuilt = engine.frame(world)
    if opportunities.frame_observation_summary(rebuilt) != snapshot["observation_summary"]:
        raise ValueError("快照公开重建后的观察摘要不一致")
    return snapshot


def capture() -> None:
    """顺序捕获七个状态；一个状态失败即整批保持未完成。"""

    manifest, frozen = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [row for row in frozen if not snapshot_path(row).exists()]
    reservation = ledger.reserve(
        step_id="r18:gang-chain-future-order:capture",
        account="prefix_generation",
        amount=len(pending),
        note="七个自然杠链精确窗口合法前缀捕获",
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    completed = 0
    failures = []
    try:
        for target in pending:
            try:
                write_json(snapshot_path(target), capture_one(target, contract))
                completed += 1
                print(json.dumps({
                    "captured": sum(snapshot_path(row).exists() for row in frozen),
                    "planned": len(frozen),
                }, ensure_ascii=False), flush=True)
            except Exception as exc:  # noqa: BLE001 - 逐目标落失败证据
                failures.append({
                    "target_id": target["target_id"],
                    "error": type(exc).__name__ + ": " + str(exc),
                })
    finally:
        ledger.settle(reservation, actual=completed, note="按成功捕获的合法前缀计")
    write_json(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"), {
        "schema": "r18-gang-chain-future-order-capture/1",
        "captured": sum(snapshot_path(row).exists() for row in frozen),
        "planned": manifest["targets"],
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in frozen):
        raise RuntimeError("杠链状态捕获不完整")
    print(json.dumps({"status": "CAPTURE_COMPLETE", "targets": len(frozen)}, ensure_ascii=False))


def _policies_for_arm(
    *, target: Mapping[str, Any], snapshot: Mapping[str, Any], action_key: str,
    label: str,
) -> tuple[list[Any], Any]:
    """按捕获时的物理对手顺序装配 V2，并只在目标窗口强制一次动作。"""

    capture_meta = snapshot["capture"]
    return core.policies_for_arm(
        opponent_names=capture_meta["opponent_names_in_physical_order"],
        focal_seat=int(target["focal_physical_seat"]),
        forced_action_key=action_key,
        target_window=window_key_from_json(target["window_key"]),
        arm_name=label,
    )


def execute_rollout(target: Mapping[str, Any], index: int, sample_key: str) -> dict[str, Any]:
    """在一个共同未来可摸顺序下完成参考/干预两臂当前桌。"""

    snapshot = json.loads(snapshot_path(target).read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    rules = HangmaRules(core.rule_config_from_contract(contract))
    runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
        seed=int(snapshot["match_spec"]["seed"]),
        scenario_id=str(snapshot["match_spec"]["scenario_id"]),
    )
    reference_policies, reference_force = _policies_for_arm(
        target=target,
        snapshot=snapshot,
        action_key=str(target["reference_action"]),
        label="reference-{0}-{1:02d}".format(target["target_id"], index),
    )
    intervention_policies, intervention_force = _policies_for_arm(
        target=target,
        snapshot=snapshot,
        action_key=str(target["intervention_action"]),
        label="intervention-{0}-{1:02d}".format(target["target_id"], index),
    )
    double = opportunities.run_double_arm(
        rules=rules,
        snapshot=snapshot,
        baseline_policies_by_seat=reference_policies,
        candidate_policies_by_seat=intervention_policies,
        config=opportunities._driver_config(),
        value_limits=LIMITS,
        runtime=runtime,
        current_world_transform=lambda world: runtime["engine"].resample_future_drawable_wall(
            world, sample_key=sample_key
        ),
    )
    actions = {
        arm: (((double.get("window_actions") or {}).get("arms") or {}).get(arm) or {}).get("action_key")
        for arm in ("baseline", "candidate")
    }
    reference = double["arms"]["baseline"]
    intervention = double["arms"]["candidate"]
    mechanical_ok = bool(
        double.get("valid")
        and reference_force.force_count == 1
        and intervention_force.force_count == 1
        and actions["baseline"] == target["reference_action"]
        and actions["candidate"] == target["intervention_action"]
        and double.get("tables_executed") == {"baseline": 1, "candidate": 1}
    )
    reference_score = reference.get("focal_stage_score")
    intervention_score = intervention.get("focal_stage_score")
    delta = (
        None
        if reference_score is None or intervention_score is None
        else int(intervention_score) - int(reference_score)
    )
    return {
        "schema": "r18-gang-chain-future-order-rollout/1",
        "target_id": target["target_id"],
        "stratum": target["stratum"],
        "rollout_index": index,
        "sample_key": sample_key,
        "reference_action": target["reference_action"],
        "intervention_action": target["intervention_action"],
        "actual_actions": actions,
        "force_count": {
            "reference": reference_force.force_count,
            "intervention": intervention_force.force_count,
        },
        "focal_current_table_score": {
            "reference": reference_score,
            "intervention": intervention_score,
        },
        "intervention_minus_reference": delta,
        "tables_executed": double.get("tables_executed"),
        "completion_reasons": double.get("completion_reasons"),
        "runtime_kind": double.get("runtime_kind"),
        "execution_kind": double.get("execution_kind"),
        "mechanical_ok": mechanical_ok,
    }


def run() -> None:
    """并行执行 7×32 个共同未来牌墙配对，支持断点续跑。"""

    manifest, frozen = verify_manifest()
    capture_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    if capture_summary["failures"] or capture_summary["captured"] != manifest["targets"]:
        raise ValueError("七个精确状态尚未全部捕获")
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for target in frozen:
        for index, key in enumerate(manifest["sample_keys"], 1):
            path = rollout_path(target, index)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if not row.get("mechanical_ok"):
                    raise ValueError("既有杠链牌墙配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:gang-chain-future-order:run",
        account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="七状态×32共同未来牌墙×两臂当前桌续打",
    )
    failures = []
    executed = 0
    usage_unknown = False
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {
                pool.submit(execute_rollout, target, index, key): (target, index)
                for target, index, key in pending
            }
            for future in concurrent.futures.as_completed(futures):
                target, index = futures[future]
                result = None
                try:
                    result = future.result()
                    if not result["mechanical_ok"] or result["intervention_minus_reference"] is None:
                        raise RuntimeError("共同未来牌墙配对机械条件失败")
                    write_json(rollout_path(target, index), result)
                    executed += 2
                    completed_tables += 2
                    if completed_tables % 32 == 0:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": manifest["planned_tables"],
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001 - 失败必须落证据
                    if result is None:
                        usage_unknown = True
                    failures.append({
                        "target_id": target["target_id"],
                        "rollout_index": index,
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按成功完成的两臂桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "rollouts")).glob("*.json"))
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-gang-chain-future-order-run/1",
        "rollout_files": len(files),
        "actual_tables": len(files) * 2,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("杠链跨未来牌墙执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": len(files) * 2}, ensure_ascii=False))


def bootstrap_interval(values: list[float], salt: int) -> tuple[float, float]:
    """确定性普通 bootstrap；只解释为同一状态的未来顺序条件均值区间。"""

    rng = random.Random(202609221800 + salt)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(sum(values[rng.randrange(len(values))] for _ in values) / len(values))
    means.sort()
    return (
        means[math.floor(0.025 * (len(means) - 1))],
        means[math.ceil(0.975 * (len(means) - 1))],
    )


def analyze() -> None:
    """先按状态汇总 32 个墙变体，再对状态均值等权汇总。"""

    manifest, frozen = verify_manifest()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("杠链跨未来牌墙执行不完整")
    state_rows = []
    all_mechanical = True
    for salt, target in enumerate(frozen, 1):
        rows = [
            json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, ROLLOUTS_PER_STATE + 1)
        ]
        values = [float(row["intervention_minus_reference"]) for row in rows]
        lo, hi = bootstrap_interval(values, salt)
        all_mechanical = all_mechanical and all(row["mechanical_ok"] for row in rows)
        state_rows.append({
            "target_id": target["target_id"],
            "stratum": target["stratum"],
            "gang_kinds": target["gang_kinds"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "future_wall_rollouts": len(values),
            "mean_delta": statistics.fmean(values),
            "median_delta": statistics.median(values),
            "bootstrap_95_mean": [lo, hi],
            "positive": sum(value > 0 for value in values),
            "zero": sum(value == 0 for value in values),
            "negative": sum(value < 0 for value in values),
            "min": min(values),
            "max": max(values),
            "values": values,
        })
    strata = {}
    for name in ("proxy_promotes_gang", "proxy_rejects_gang"):
        selected = [row for row in state_rows if row["stratum"] == name]
        means = [float(row["mean_delta"]) for row in selected]
        strata[name] = {
            "base_states": len(selected),
            "future_wall_rollouts": sum(row["future_wall_rollouts"] for row in selected),
            "unweighted_mean_of_state_means": statistics.fmean(means),
            "positive_state_means": sum(value > 0 for value in means),
            "zero_state_means": sum(value == 0 for value in means),
            "negative_state_means": sum(value < 0 for value in means),
            "state_ids": [row["target_id"] for row in selected],
        }
    promotes = strata["proxy_promotes_gang"]
    direction_supported = bool(
        promotes["positive_state_means"] >= 3
        and promotes["unweighted_mean_of_state_means"] > 0
    )
    decision = (
        "EXPAND_ADDED_GANG_BASE_STATE_BANK"
        if direction_supported
        else "PAUSE_ADDED_GANG_DIRECTION"
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "r18-gang-chain-future-order-result/1",
        "status": "COMPLETE_GANG_CHAIN_FUTURE_ORDER",
        "mechanical_ok": all_mechanical,
        "base_states": len(state_rows),
        "rollouts": len(state_rows) * ROLLOUTS_PER_STATE,
        "tables": len(state_rows) * ROLLOUTS_PER_STATE * 2,
        "states": state_rows,
        "strata": strata,
        "checks": {
            "all_pairs_mechanical_ok": all_mechanical,
            "promotes_positive_state_means_at_least_3_of_4": promotes["positive_state_means"] >= 3,
            "promotes_unweighted_state_mean_positive": promotes["unweighted_mean_of_state_means"] > 0,
        },
        "decision": decision,
        "author_task_open": False,
        "next_gate": "至少24个独立自然基础状态；按基础状态冻结训练/确认切分后才允许作者任务",
        "interpretation": "未来墙变体只估计给定当前隐藏分配的条件效果；状态数仍是7，不能把224个rollout当224个独立样本",
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps(json.loads((_project_file(_PROJECT_ROOT, OUT / "result.json")).read_text(encoding="utf-8")), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "capture", "run", "analyze"))
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "capture":
        capture()
    elif args.command == "run":
        run()
    else:
        analyze()


if __name__ == "__main__":
    main()
