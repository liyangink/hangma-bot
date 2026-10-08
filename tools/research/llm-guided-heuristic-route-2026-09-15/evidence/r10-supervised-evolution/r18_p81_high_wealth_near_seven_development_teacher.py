"""R18 P81：高财神近七对鸣牌／过牌的 R18 v2 开发集未来牌墙教师。

P80 结果盲冻结 14 个开发状态和 14 个自然复验状态。本程序只捕获开发状态；
响应窗口不能依法重采样已经发到三家的暗手，因此固定原自然隐藏手，仅为两臂
共同重排尚未摸取的未来牌墙。每状态前 16 个未来墙用于发现可能的过牌机会，
后 16 个只复查方向；自然复验状态在候选规则冻结前保持未捕获、未标注。

一次工程预检使用了不同的 sample_key，并观察到首个开发状态的单次收益标签；
正式试验不使用该 sample_key，门槛沿 P31 的根级复查框架冻结且增加完整桌
积分门，不按这一次标签改阈值。
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
from dataclasses import replace
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
import r18_p9_midgame_hidden_world_teacher as p9  # noqa: E402
import r18_p11_settlement_cascade_teacher as p11  # noqa: E402
import r18_p13_development_seven_pairs_teacher as p13  # noqa: E402
import r18_p80_high_wealth_near_seven_claim_exposure as p80  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.serialization import window_key_from_json  # noqa: E402
from hangma_bot.offline.evaluate import seat_policies_from  # noqa: E402
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p81-high-wealth-near-seven-development-teacher-01-20260925')
DATASET = p80.OUT / "dataset.json"
EXPOSURE_RESULT = p80.OUT / "result.json"
CONTRACT = p80.CONTRACT
PARENT = p80.PARENT
ROLLOUTS_PER_STATE = 32
FIT_ROLLOUTS = 16
BOOTSTRAP_REPLICATES = 20_000
MINIMUM_SELECTED_STATES = 4
MINIMUM_RECHECK_POSITIVE_FRACTION = 0.75


def write_json(path: Path, value: Any) -> None:
    """写入稳定、可复算的 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def targets() -> list[dict[str, Any]]:
    """把 P80 结果盲切分转换为精确重放目标，不打开任何收益标签。"""

    exposure = json.loads(EXPOSURE_RESULT.read_text(encoding="utf-8"))
    if exposure.get("status") != "OPEN_DEVELOPMENT_CONFIRMATION":
        raise ValueError("P80 未开放开发教师")
    document = json.loads(DATASET.read_text(encoding="utf-8"))
    if document.get("outcome_blind") is not True:
        raise ValueError("P80 数据集必须保持结果盲")
    rows = list(document.get("rows") or [])
    if len(rows) != 28 or document.get("replication_labels_opened") is not False:
        raise ValueError("P80 必须冻结 28 个结果盲自然状态")

    counters: Counter[tuple[str, str]] = Counter()
    result = []
    for row in rows:
        split = str(row["split"])
        family = str(row["family"])
        if split not in ("development", "replication") or family not in ("chi", "peng"):
            raise ValueError("P80 切分或动作家族未知")
        counters[(split, family)] += 1
        request = row["request"]
        observation = request["observation"]
        table_id = str(observation["game_id"]).removeprefix("sitin-stage:")
        result.append({
            "target_id": "r18-p81-{0}-{1}-{2:02d}".format(
                split, family, counters[(split, family)],
            ),
            "split": split,
            "family": family,
            "source": {
                "panel_seed": p80.PANEL_SEED,
                "source_id": row["source"]["source_id"],
                "source_root_id": row["source"]["source_root_id"],
                "mix": row["source"]["mix"],
                "root_index": row["source"]["root_index"],
                "focal_seat": row["source"]["focal_seat"],
                "table_no": int(table_id.rsplit("-t", 1)[1]),
                "table_id": table_id,
            },
            "window_key": request["window_key"],
            "focal_physical_seat": int(observation["seat"]),
            "request_sha256": row["request_sha256"],
            "state_projection_sha256": row["state_projection_sha256"],
            "reference_action": row["reference_action"],
            "intervention_action": row["intervention_action"],
            "features": dict(row["features"]),
        })
    result.sort(key=lambda item: (
        item["split"], item["family"], item["source"]["mix"],
        item["source"]["source_root_id"], item["request_sha256"],
    ))
    if sum(row["split"] == "development" for row in result) != 14:
        raise ValueError("P81 必须恰有 14 个开发状态")
    if sum(row["split"] == "replication" for row in result) != 14:
        raise ValueError("P81 必须恰有 14 个自然复验状态")
    roots = [row["source"]["source_root_id"] for row in result]
    if len(roots) != len(set(roots)):
        raise ValueError("P81 自然来源根必须全局独立")
    return result


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-future-{1:02d}.json".format(
        target["target_id"], index,
    ))


def source_paths() -> list[Path]:
    """列出会改变选择、重放或标签语义的实现。"""

    import hangma_bot.offline.forced_action as forced_action
    import hangma_bot.simulation.engine as simulation_engine
    import hangma_bot.simulation.shuffle as simulation_shuffle

    return [
        Path(__file__), DATASET, EXPOSURE_RESULT, CONTRACT, PARENT,
        p80.OUT / "manifest.json", Path(p9.__file__),
        Path(p11.__file__), Path(p13.__file__), Path(p80.__file__),
        Path(natural.__file__), Path(opportunities.__file__), Path(core.__file__),
        Path(forced_action.__file__), Path(simulation_engine.__file__),
        Path(simulation_shuffle.__file__),
    ]


def prepare() -> None:
    """冻结开发目标、未来墙样本、判据和最大执行预算。"""

    if OUT.exists():
        raise SystemExit("P81 目录已存在；拒绝覆盖")
    frozen = targets()
    development = [row for row in frozen if row["split"] == "development"]
    sample_keys = [
        "r18-p81-high-wealth-near-seven-future-wall-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(development) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p81-high-wealth-near-seven-development-teacher-01",
        accounts={
            "prefix_generation": len(development),
            "tables_full": planned_tables,
        },
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P80通过30根自然暴露门；只打开14个结果盲开发状态",
        "scope": "14开发状态×32共同未来牌墙×R18 v2吃碰/过牌；14自然复验状态不捕获",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p81-high-wealth-near-seven-targets/1",
        "targets": frozen,
        "replication_labels_opened": False,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p81-high-wealth-near-seven-development-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "dataset_sha256": digest(DATASET),
        "exposure_result_sha256": digest(EXPOSURE_RESULT),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "parent_sha256": digest(PARENT),
        "parent_score_source_sha256": hashlib.sha256(p80.parent_source().encode("utf-8")).hexdigest(),
        "contract_sha256": digest(CONTRACT),
        "development_states": len(development),
        "replication_states_kept_blind": len(frozen) - len(development),
        "rollouts_per_state": ROLLOUTS_PER_STATE,
        "future_wall_fit_indices": list(range(1, FIT_ROLLOUTS + 1)),
        "future_wall_recheck_indices": list(
            range(FIT_ROLLOUTS + 1, ROLLOUTS_PER_STATE + 1)
        ),
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "execution_mode": "single_process_sequential",
        "sampling_unit": "自然基础状态；32个共同未来牌墙不增加独立样本数",
        "sampling_scope": (
            "固定原自然三家暗手，只共同重排尚未摸取的未来牌墙；"
            "不宣称覆盖公开状态一致的全部隐藏手分布"
        ),
        "primary_label": "pass_minus_claim_current_round_settlement",
        "selection_rule": (
            "每状态只用前16未来墙；目标局结算与完整剩余桌积分均值都>0时选择pass，"
            "否则保持R18 v2吃碰；后16未来墙只复查该选择"
        ),
        "gate": {
            "minimum_fit_selected_states": MINIMUM_SELECTED_STATES,
            "minimum_recheck_positive_selected_fraction": MINIMUM_RECHECK_POSITIVE_FRACTION,
            "recheck_current_round_policy_mean_strictly_greater_than": 0.0,
            "recheck_full_table_policy_bootstrap_95_lower_strictly_greater_than": 0.0,
            "minimum_leave_one_source_root_out_full_table_mean_strictly_greater_than": 0.0,
        },
        "engineering_preflight_sample_key_excluded": "p80-development-future-wall-01",
        "replication_labels_opened": False,
        "model_calls": 0,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "development_states": len(development),
        "replication_states_kept_blind": len(frozen) - len(development),
        "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对 P80 输入、目标、父代、合同和运行实现均未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P80数据": (manifest["dataset_sha256"], digest(DATASET)),
        "P80结果": (manifest["exposure_result_sha256"], digest(EXPOSURE_RESULT)),
        "P81目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "R18 v2父代": (manifest["parent_sha256"], digest(PARENT)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    if manifest["parent_score_source_sha256"] != hashlib.sha256(
        p80.parent_source().encode("utf-8")
    ).hexdigest():
        raise ValueError("R18 v2 评分源码身份漂移")
    guard.verify(manifest["runtime"])
    document = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))
    if document.get("replication_labels_opened") is not False:
        raise ValueError("P81 自然复验标签必须保持封存")
    frozen = list(document["targets"])
    if frozen != targets():
        raise ValueError("P81 目标不能由 P80 结果盲重建")
    return manifest, frozen


def capture_one(target: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    """按冻结 R18 v2 自然轨迹重建精确响应窗口，只捕获开发来源。"""

    source = target["source"]
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=str(source["mix"]),
        root_index=int(source["root_index"]), focal_seat=int(source["focal_seat"]),
        panel_seed=int(source["panel_seed"]),
    )
    plan = plans[int(source["table_no"]) - 1]
    if (plan.table_id != source["table_id"]
            or plan.match_id != target["window_key"]["game_id"]):
        raise ValueError("P81 自然桌计划与冻结窗口身份漂移")
    rules = HangmaRules(core.rule_config_from_contract(contract))
    opponent_names = opportunities.opponent_policy_names(contract, str(source["mix"]))
    logical = natural.arm_logical_policies(
        arm="candidate",
        candidate_scorer=ActionValueScorer(
            "r18-p81-capture-r18-v2", p80.parent_source(),
        ),
        logical_participants=plan.logical_participants,
        opponent_policies=opponent_names, monotonic=lambda: 800.0,
    )
    policies = list(seat_policies_from(
        logical, plan.permutation, plan.logical_participants,
    ))
    physical_names = p9._physical_policy_names(plan)
    focal_physical = int(target["focal_physical_seat"])
    if physical_names[focal_physical] != "focal-arm":
        raise ValueError("P81 焦点物理座位与换座计划不符")
    verifier_names = [
        physical_names[seat] for seat in range(4) if seat != focal_physical
    ]
    runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(contract["versions"]["rounds_per_game"]),
        seed=int(plan.seed), scenario_id=str(plan.scenario_id),
    )
    tournament_config = opportunities._snapshot_tournament_config(
        {"rounds_per_game": int(contract["versions"]["rounds_per_game"])}, rules,
    )
    # 旧函数名含 P5，但真正运行的策略由 policies_by_seat 注入；修正其审计标签。
    attempt = p13.run_p5_prefix_attempt(
        runtime=runtime, rules=rules, target=target, policies_by_seat=policies,
        tournament_config=tournament_config, plan=plan,
    )
    execution = dict(attempt.prefix_execution or {})
    execution.update({
        "schema": "r18-p81-r18-v2-prefix-execution/1",
        "focal_policy": "frozen R18 v2 action-value policy",
    })
    attempt = replace(attempt, prefix_execution=execution)
    runtime_kind = opportunities.runtime_kind_of(runtime)
    snapshot = dict(opportunities.build_snapshot(
        prefix_source="v2_behavior", attempt=attempt,
        predicate_id="r18_p81_r18_v2_exact_window", focal_seat=focal_physical,
        opponent_scenario=str(source["mix"]), match_id=str(plan.match_id),
        stage_ledger={"completed_table_scores": []},
        remaining_schedule={
            "declared_endpoint": "current_table_complete",
            "remaining_tables_after_current": 0,
            "rounds_per_game": int(contract["versions"]["rounds_per_game"]),
            "tables_in_stage": 1,
        },
        panel_seed=int(source["panel_seed"]), tables_in_stage=1,
        rounds_per_game=int(contract["versions"]["rounds_per_game"]),
        runtime_evidence={
            "runtime_kind": runtime_kind,
            "engine_kind": opportunities.ENGINE_KIND_BY_RUNTIME_KIND[runtime_kind],
            "execution_kind": opportunities.execution_kind_for(
                prefix_source="v2_behavior", runtime=runtime,
            ),
            "runtime_source": str(runtime.get("runtime_entry")),
            "engine_identity": dict(runtime.get("engine_identity") or {}),
            "real_tables": True,
        },
        witness_entry="r18_p81_r18_v2_natural_exact_window",
    ))
    snapshot["seating"]["participant_ids_by_seat"] = list(plan.seats())
    snapshot["stage_plan"]["participant_ids_by_seat"] = list(plan.seats())
    snapshot["capture"] = {
        "target": dict(target), "table_seed": int(plan.seed),
        "table_scenario_id": str(plan.scenario_id),
        "physical_policy_names": physical_names,
        "opponent_names_in_physical_order": verifier_names,
        "prefix_steps": len(attempt.prefix),
        "focal_prefix_policy": "frozen R18 v2 action-value policy",
        "prefix_source_note": "v2_behavior 表示真实引擎合法前缀；实际焦点策略为冻结 R18 v2",
        "witness": dict(attempt.predicate_witness or {}),
    }
    engine, world = opportunities.rebuild_world(
        rules=rules, snapshot=snapshot, value_limits=p13.LIMITS, runtime=runtime,
    )
    if (opportunities.frame_observation_summary(engine.frame(world))
            != snapshot["observation_summary"]):
        raise ValueError("P81 快照公开重建后的观察摘要不一致")
    return snapshot


def capture() -> None:
    """只捕获 14 个开发状态的精确合法前缀。"""

    manifest, frozen = verify()
    development = [row for row in frozen if row["split"] == "development"]
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [row for row in development if not snapshot_path(row).exists()]
    reservation = ledger.reserve(
        step_id="r18:p81-high-wealth-near-seven:capture", account="prefix_generation",
        amount=len(pending), note="14个开发状态的R18 v2精确合法前缀捕获",
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    completed = 0
    failures = []
    try:
        for target in pending:
            try:
                snapshot = capture_one(target, contract)
                snapshot["capture"]["consumer"] = "R18 P81 high-wealth near-seven teacher"
                write_json(snapshot_path(target), snapshot)
                completed += 1
                print(json.dumps({
                    "captured": sum(snapshot_path(row).exists() for row in development),
                    "planned": len(development),
                }, ensure_ascii=False), flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "target_id": target["target_id"],
                    "error": type(exc).__name__ + ": " + str(exc),
                })
    finally:
        ledger.settle(reservation, actual=completed, note="按成功捕获的合法前缀计")
    write_json(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"), {
        "schema": "r18-p81-high-wealth-near-seven-capture-summary/1",
        "captured": sum(snapshot_path(row).exists() for row in development),
        "planned": manifest["development_states"],
        "failures": failures,
        "replication_snapshots": sum(
            snapshot_path(row).exists()
            for row in frozen if row["split"] == "replication"
        ),
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in development):
        raise RuntimeError("P81 开发状态捕获不完整")


def policies_for_arm(
    *, target: Mapping[str, Any], snapshot: Mapping[str, Any],
    forced_action_key: str, label: str,
) -> tuple[list[Any], ForceFirstActionPolicy]:
    """仅目标窗强制动作一次，之后焦点恢复冻结 R18 v2、对手保持合同策略。"""

    focal = int(target["focal_physical_seat"])
    policies = list(opportunities.frozen_generation_policies(
        opponent_names=snapshot["capture"]["opponent_names_in_physical_order"],
        focal_seat=focal, monotonic=lambda: 800.0,
    ))
    delegate = ActionValuePolicy(ActionValueScorer(
        "r18-p81-r18-v2-continuation-" + label, p80.parent_source(),
    ))
    forced = ForceFirstActionPolicy(
        delegate, target_window=window_key_from_json(target["window_key"]),
        forced_action_key=forced_action_key, policy_id="r18-p81-" + label,
    )
    policies[focal] = forced
    return policies, forced


def execute_rollout(
    target: Mapping[str, Any], index: int, sample_key: str,
) -> dict[str, Any]:
    """固定原隐藏手，在共同未来牌墙下执行 R18 v2 吃碰与过牌两臂。"""

    snapshot = json.loads(snapshot_path(target).read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    rules = HangmaRules(core.rule_config_from_contract(contract))
    base_runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
        seed=int(snapshot["match_spec"]["seed"]),
        scenario_id=str(snapshot["match_spec"]["scenario_id"]),
    )
    settlement = p11.SettlementCaptureEngine(base_runtime["engine"])
    runtime = dict(base_runtime)
    runtime["engine"] = settlement
    reference_policies, reference_force = policies_for_arm(
        target=target, snapshot=snapshot,
        forced_action_key=str(target["reference_action"]),
        label="p81-reference-{0}-{1:02d}".format(target["target_id"], index),
    )
    intervention_policies, intervention_force = policies_for_arm(
        target=target, snapshot=snapshot,
        forced_action_key=str(target["intervention_action"]),
        label="p81-intervention-{0}-{1:02d}".format(target["target_id"], index),
    )

    def transform(world: Any) -> Any:
        sampled = settlement.resample_future_drawable_wall(world, sample_key=sample_key)
        return replace(sampled, history_consistent=False)

    double = opportunities.run_double_arm(
        rules=rules, snapshot=snapshot,
        baseline_policies_by_seat=reference_policies,
        candidate_policies_by_seat=intervention_policies,
        config=opportunities._driver_config(), value_limits=p13.LIMITS,
        runtime=runtime, current_world_transform=transform,
    )
    if not double.get("valid"):
        errors = {
            arm: (detail.get("status"), detail.get("error"))
            for arm, detail in (double.get("arms") or {}).items()
        }
        raise RuntimeError("双臂执行无效：" + repr(errors))
    cut_round = int(target["features"]["round_no"])
    records = [record for record in settlement.records if record.round_no == cut_round]
    if len(records) != 2:
        raise RuntimeError(
            "目标局必须按参考臂、干预臂各捕获一次，实际 {0}".format(len(records))
        )
    reference_record, intervention_record = records
    focal = int(target["focal_physical_seat"])
    actions = {
        arm: (((double.get("window_actions") or {}).get("arms") or {}).get(arm) or {}).get("action_key")
        for arm in ("baseline", "candidate")
    }
    reference_score = double["arms"]["baseline"].get("focal_stage_score")
    intervention_score = double["arms"]["candidate"].get("focal_stage_score")
    mechanical = bool(
        reference_force.force_count == 1 and intervention_force.force_count == 1
        and actions["baseline"] == target["reference_action"]
        and actions["candidate"] == target["intervention_action"]
        and double.get("tables_executed") == {"baseline": 1, "candidate": 1}
        and reference_score is not None and intervention_score is not None
    )
    reference = p11.record_json(reference_record)
    intervention = p11.record_json(intervention_record)
    reference["terminal"] = p13.terminal(reference_record, focal)
    intervention["terminal"] = p13.terminal(intervention_record, focal)
    reference["focal_settlement"] = int(reference_record.score_delta[focal])
    intervention["focal_settlement"] = int(intervention_record.score_delta[focal])
    return {
        "schema": "r18-p81-high-wealth-near-seven-development-rollout/1",
        "target_id": target["target_id"], "family": target["family"],
        "rollout_index": index, "sample_key": sample_key,
        "reference_action": target["reference_action"],
        "intervention_action": target["intervention_action"],
        "actual_actions": actions,
        "force_count": {
            "reference": reference_force.force_count,
            "intervention": intervention_force.force_count,
        },
        "reference": reference, "intervention": intervention,
        "focal_current_round_settlement_delta": (
            intervention["focal_settlement"] - reference["focal_settlement"]
        ),
        "focal_remaining_table_score": {
            "reference": reference_score, "intervention": intervention_score,
            "delta": int(intervention_score) - int(reference_score),
        },
        "tables_executed": double.get("tables_executed"),
        "completion_reasons": double.get("completion_reasons"),
        "runtime_kind": double.get("runtime_kind"),
        "execution_kind": double.get("execution_kind"),
        "sampling_scope": "source hidden hands fixed; common future drawable wall only",
        "mechanical_ok": mechanical,
    }


def run() -> None:
    """顺序执行 14×32 个双臂完整桌配对，逐未来墙结算费用。"""

    manifest, frozen = verify()
    development = [row for row in frozen if row["split"] == "development"]
    capture_summary = json.loads(
        (_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8")
    )
    if (
        capture_summary["failures"]
        or capture_summary["captured"] != manifest["development_states"]
        or capture_summary["replication_snapshots"] != 0
    ):
        raise ValueError("P81 开发前缀未完整捕获或自然复验被提前打开")
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    completed_tables = 0
    for target in development:
        for index, key in enumerate(manifest["sample_keys"], 1):
            path = rollout_path(target, index)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if not row.get("mechanical_ok"):
                    raise ValueError("既有 P81 配对机械条件失败：" + str(path))
                completed_tables += 2
                continue
            reservation = ledger.reserve(
                step_id="r18:p81:development:" + target["target_id"] + f":{index:02d}",
                account="tables_full", amount=2,
                note="同一未来墙的鸣牌／过牌双臂完整桌；开发集",
            )
            try:
                row = execute_rollout(target, index, key)
                if not row["mechanical_ok"]:
                    raise RuntimeError("P81 配对机械条件失败")
                write_json(path, row)
                ledger.settle(reservation, actual=2, note="双臂完整且强制动作核对通过")
            except BaseException:
                ledger.settle(reservation, usage_unknown=True,
                              note="开发双臂异常；保守结算两桌")
                raise
            completed_tables += 2
            if completed_tables % 64 == 0 or completed_tables == manifest["planned_tables"]:
                print(json.dumps({
                    "completed_tables": completed_tables,
                    "planned_tables": manifest["planned_tables"],
                }, ensure_ascii=False), flush=True)
    files = list((_project_file(_PROJECT_ROOT, OUT / "rollouts")).glob("*.json"))
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p81-high-wealth-near-seven-run-summary/1",
        "rollout_files": len(files), "actual_tables": len(files) * 2,
        "failures": [], "spent": ledger.account_summary(),
    })
    if len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P81 开发教师执行不完整")


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    """对自然基础状态等权均值做确定性 bootstrap 95% 区间。"""

    rng = random.Random(2026092581)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return (
        means[int(0.025 * len(means))],
        means[int(0.975 * len(means)) - 1],
    )


def analyze() -> None:
    """前半未来墙按目标局和完整桌双指标选状态，后半复查同一方向。"""

    manifest, frozen = verify()
    development = [row for row in frozen if row["split"] == "development"]
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P81 开发教师执行不完整")
    states = []
    all_mechanical = True
    for target in development:
        rows = [
            json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, ROLLOUTS_PER_STATE + 1)
        ]
        mechanical = all(row["mechanical_ok"] for row in rows)
        all_mechanical = all_mechanical and mechanical
        fit_round = [
            row["focal_current_round_settlement_delta"]
            for row in rows[:FIT_ROLLOUTS]
        ]
        fit_table = [
            row["focal_remaining_table_score"]["delta"]
            for row in rows[:FIT_ROLLOUTS]
        ]
        recheck_round = [
            row["focal_current_round_settlement_delta"]
            for row in rows[FIT_ROLLOUTS:]
        ]
        recheck_table = [
            row["focal_remaining_table_score"]["delta"]
            for row in rows[FIT_ROLLOUTS:]
        ]
        fit_round_mean = statistics.fmean(fit_round)
        fit_table_mean = statistics.fmean(fit_table)
        recheck_round_mean = statistics.fmean(recheck_round)
        recheck_table_mean = statistics.fmean(recheck_table)
        selected = fit_round_mean > 0 and fit_table_mean > 0
        states.append({
            "target_id": target["target_id"], "family": target["family"],
            "source": target["source"], "features": target["features"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "mechanical_ok": mechanical,
            "fit_mean_pass_minus_claim_current_round_settlement": fit_round_mean,
            "fit_mean_remaining_table_score_delta": fit_table_mean,
            "future_wall_recheck_mean_pass_minus_claim_current_round_settlement": recheck_round_mean,
            "future_wall_recheck_mean_remaining_table_score_delta": recheck_table_mean,
            "fit_selected_pass": selected,
            "future_wall_recheck_positive_both": (
                recheck_round_mean > 0 and recheck_table_mean > 0
            ),
            "fit_round_values": fit_round,
            "fit_table_values": fit_table,
            "future_wall_recheck_round_values": recheck_round,
            "future_wall_recheck_table_values": recheck_table,
            "terminal_transitions": dict(sorted(Counter(
                row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]
                for row in rows
            ).items())),
        })

    selected = [row for row in states if row["fit_selected_pass"]]
    policy_round_values = [
        row["future_wall_recheck_mean_pass_minus_claim_current_round_settlement"]
        if row["fit_selected_pass"] else 0.0
        for row in states
    ]
    policy_table_values = [
        row["future_wall_recheck_mean_remaining_table_score_delta"]
        if row["fit_selected_pass"] else 0.0
        for row in states
    ]
    low, high = bootstrap_interval(policy_table_values)
    positive_selected = sum(row["future_wall_recheck_positive_both"] for row in selected)
    required_positive = math.ceil(
        MINIMUM_RECHECK_POSITIVE_FRACTION * len(selected)
    )
    leave_one_out = {}
    for row in states:
        root = str(row["source"]["source_root_id"])
        remaining = [
            value for item, value in zip(states, policy_table_values)
            if item["source"]["source_root_id"] != root
        ]
        leave_one_out[root] = statistics.fmean(remaining)
    minimum_loo = min(leave_one_out.values())
    gate_passed = bool(
        all_mechanical
        and len(selected) >= MINIMUM_SELECTED_STATES
        and positive_selected >= required_positive
        and statistics.fmean(policy_round_values) > 0
        and low > 0
        and minimum_loo > 0
    )
    by_family = {}
    for family in ("chi", "peng"):
        items = [row for row in states if row["family"] == family]
        family_selected = [row for row in items if row["fit_selected_pass"]]
        by_family[family] = {
            "independent_states": len(items),
            "fit_selected_pass_states": len(family_selected),
            "future_wall_recheck_positive_selected_states": sum(
                row["future_wall_recheck_positive_both"] for row in family_selected
            ),
            "future_wall_recheck_policy_current_round_mean": statistics.fmean(
                row["future_wall_recheck_mean_pass_minus_claim_current_round_settlement"]
                if row["fit_selected_pass"] else 0.0
                for row in items
            ),
            "future_wall_recheck_policy_full_table_mean": statistics.fmean(
                row["future_wall_recheck_mean_remaining_table_score_delta"]
                if row["fit_selected_pass"] else 0.0
                for row in items
            ),
        }
    result = {
        "schema": "r18-p81-high-wealth-near-seven-development-result/1",
        "status": "COMPLETE_P81_HIGH_WEALTH_NEAR_SEVEN_DEVELOPMENT_TEACHER",
        "mechanical_ok": all_mechanical,
        "development_states": len(states),
        "rollouts": len(states) * ROLLOUTS_PER_STATE,
        "tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "states": states,
        "aggregate": {
            "fit_selected_pass_states": len(selected),
            "future_wall_recheck_positive_selected_states": positive_selected,
            "required_future_wall_recheck_positive_selected_states": required_positive,
            "future_wall_recheck_policy_current_round_mean": statistics.fmean(policy_round_values),
            "future_wall_recheck_policy_full_table_mean": statistics.fmean(policy_table_values),
            "future_wall_recheck_policy_full_table_bootstrap_95": [low, high],
            "leave_one_source_root_out_full_table_mean": leave_one_out,
            "minimum_leave_one_source_root_out_full_table_mean": minimum_loo,
        },
        "by_family": by_family,
        "gate_passed": gate_passed,
        "decision": (
            "OPEN_P82_LIMITED_AUTHOR" if gate_passed
            else "CLOSE_HIGH_WEALTH_NEAR_SEVEN_CLAIM_AXIS"
        ),
        "sampling_scope": manifest["sampling_scope"],
        "replication_states_kept_blind": manifest["replication_states_kept_blind"],
        "replication_labels_opened": False,
        "next": (
            "只用开发标签与公开特征归纳小型过牌路由器；候选冻结后才打开14个自然复验状态"
            if gate_passed else
            "保持R18 v2并关闭本轴；不得查看自然复验标签后补阈值"
        ),
        "selection_eligible": True,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], "mechanical_ok": all_mechanical,
        "aggregate": result["aggregate"], "by_family": by_family,
        "gate_passed": gate_passed, "decision": result["decision"],
        "replication_labels_opened": False,
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "capture", "run", "analyze"))
    command = parser.parse_args().command
    if command == "prepare":
        prepare()
    elif command == "capture":
        capture()
    elif command == "run":
        run()
    else:
        analyze()


if __name__ == "__main__":
    main()
