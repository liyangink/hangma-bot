"""R11-DV1-2R：在全新来源独立确认冻结弃牌研究候选。"""

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
import concurrent.futures
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import claim_counterfactual_pilot as core  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import discard_value_grouped_model as grouped  # noqa: E402
import discard_value_research_candidate as candidate  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.actions import Discard, WindowKey, WindowPhase  # noqa: E402
from hangma_bot.offline.discard_value_features import (  # noqa: E402
    SCHEMA as FEATURE_SCHEMA,
    encode_discard_value_features,
)
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/discard-value-research-confirmation-01-20260921')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R11-DISCARD-ACTION-VALUE-EVOLUTION-PLAN-2026-09-21.md')
CANDIDATE = candidate.OUT / "candidate.json"
CANDIDATE_RESULT = candidate.OUT / "result.json"
PANEL_SEEDS = (2026092350, 2026092351, 2026092352, 2026092353)
MIXES = ("H", "M")
SHARDS = tuple((seed, mix) for seed in PANEL_SEEDS for mix in MIXES)
TARGET_SNAPSHOTS_PER_SHARD = 16
MAX_ROOTS_PER_SHARD = 32
ROLLOUTS_PER_CHANGED_SNAPSHOT = 16
TABLES_PER_ARM = core.TABLES_PER_ARM
MAX_SNAPSHOTS = len(SHARDS) * TARGET_SNAPSHOTS_PER_SHARD
MAX_TABLES = MAX_SNAPSHOTS * ROLLOUTS_PER_CHANGED_SNAPSHOT * 2 * TABLES_PER_ARM
LABEL = "r11_dv1_research_confirmation"


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


class DiscardWindowCapture:
    """截取自然摸牌窗口并冻结全部合法弃牌公开特征。"""

    def __init__(self) -> None:
        self.policy = ComparableHeuristicPolicyV2(monotonic=lambda: 800.0)
        self.config = opportunities._driver_config()

    def __call__(self, request: Any) -> dict | None:
        if request.observation.phase != "draw":
            return None
        discard_candidates = [
            item for item in request.rules.legal_candidates
            if isinstance(item.action, Discard)
        ]
        if len(discard_candidates) < 2:
            return None
        import asyncio

        plan = asyncio.run(self.policy.choose(
            request, self.config.budget_policy.build(800.0, 3.0)
        ))
        if not plan.candidates:
            return None
        baseline_key = str(plan.candidates[0].action_key)
        by_key = {item.action_key: item for item in discard_candidates}
        if baseline_key not in by_key:
            return None
        action_keys = sorted(by_key)
        return {
            "baseline_action_key": baseline_key,
            "action_keys": action_keys,
            "observable_features_by_action": {
                key: encode_discard_value_features(request, key)
                for key in action_keys
            },
            "candidate_id": type(self.policy).__name__,
        }


def source_paths() -> list[Path]:
    """列出独立确认冻结的实现、候选、计划和合同。"""

    import hangma_bot.offline.forced_action as forced_action
    import hangma_bot.simulation.engine as simulation_engine
    import hangma_bot.simulation.shuffle as simulation_shuffle

    return [
        Path(__file__), Path(grouped.__file__), Path(candidate.__file__),
        Path(core.__file__), Path(opportunities.__file__),
        Path(forced_action.__file__), Path(simulation_engine.__file__),
        Path(simulation_shuffle.__file__), PLAN, CANDIDATE, CANDIDATE_RESULT,
        core.CONTRACT,
    ]


def prepare() -> None:
    """冻结全新来源、唯一候选、16 个共同未来顺序和确认门。"""

    if OUT.exists():
        raise SystemExit("DV1-2R 确认目录已存在；拒绝覆盖")
    frozen = batch.read(CANDIDATE_RESULT)
    if frozen.get("status") != "FROZEN_RESEARCH_CANDIDATE_FOR_INDEPENDENT_ACTION_VALIDATION":
        raise SystemExit("研究候选未冻结")
    if frozen.get("original_gate_passed") is not False:
        raise SystemExit("确认批必须保留原门未通过身份")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "roots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "raw")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / ".gitignore")).write_text("/roots/\n/raw/\n", encoding="utf-8")
    authorization = batch.unified_document(
        batch_label="r11-dv1-research-confirmation-v1",
        authorization_id="r11-dv1-research-confirmation-v1-20260921",
        accounts={
            "tables_full": MAX_TABLES,
            "prefix_generation": len(SHARDS) * MAX_ROOTS_PER_SHARD,
        },
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "从11规格事后留存的GAM-16只允许一次全新来源独立动作确认；原四折失败不追认",
        "scope": "四个全新panel_seed×H/M×16快照；同动作记零；改动作时V2与冻结候选使用16共同未来顺序成对续打",
        "max_model_calls": 0,
        "confirmation_roots": MAX_SNAPSHOTS,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r11-dv1-research-confirmation/1",
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "candidate": str(CANDIDATE),
        "candidate_sha256": digest(CANDIDATE),
        "candidate_result": str(CANDIDATE_RESULT),
        "candidate_result_sha256": digest(CANDIDATE_RESULT),
        "panel_seeds": list(PANEL_SEEDS),
        "mixes": list(MIXES),
        "target_snapshots_per_shard": TARGET_SNAPSHOTS_PER_SHARD,
        "max_roots_per_shard": MAX_ROOTS_PER_SHARD,
        "rollouts_per_changed_snapshot": ROLLOUTS_PER_CHANGED_SNAPSHOT,
        "sample_keys": [
            f"confirmation-future-order-{index:02d}"
            for index in range(1, ROLLOUTS_PER_CHANGED_SNAPSHOT + 1)
        ],
        "selection": "每个seed×mix按root_index升序取前16个自然draw弃牌窗口；模型只读冻结公开特征；不按决定或结果删窗",
        "teacher": "模型与V2同动作记零；改动作时两臂共享未来顺序且首动作后均恢复稳定V2",
        "continue_gate": "机械全绿；改动率5%–50%；单一改动作<80%；快照级辅助均值双侧95%区间下界>0；H/M辅助均值>=0；总体u_low均值>=0",
        "multiple_models_screened_before_confirmation": 11,
        "original_grouped_gate_passed": False,
        "max_snapshots": MAX_SNAPSHOTS,
        "max_tables": MAX_TABLES,
        "llm_calls": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({
        "status": "PREPARED_DV1_2R_CONFIRMATION",
        "snapshots": MAX_SNAPSHOTS,
        "max_tables": MAX_TABLES,
    }, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """核对实现、计划、候选与原失败身份未漂移。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (
        ("plan", "plan_sha256"),
        ("candidate", "candidate_sha256"),
        ("candidate_result", "candidate_result_sha256"),
    ):
        if digest(Path(manifest[path_key])) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")


def _root_path(panel_seed: int, mix: str, root_index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "roots" / f"s{panel_seed}-{mix}-root{root_index:03d}.json")


def _arm_path(
    panel_seed: int, mix: str, root_index: int, rollout_index: int, arm: str,
) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "raw" / (
        f"s{panel_seed}-{mix}-root{root_index:03d}-r{rollout_index:02d}-{arm}.json"
    ))


def _window(snapshot: dict) -> WindowKey:
    cut = snapshot["cut_window"]
    return WindowKey(
        game_id=str(snapshot["match_spec"]["match_id"]),
        round_no=int(cut["round_no"]),
        trigger_seq=int(cut["trigger_seq"]),
        phase=WindowPhase(str(cut["phase"])),
        seat=int(cut["seat"]),
    )


def _decision(witness: dict, frozen: dict) -> dict:
    """用冻结模型和阈值选择一个合法弃牌。"""

    model, threshold = grouped.decision_from_artifact(frozen)
    actions = [
        {
            "action_key": key,
            "is_v2_baseline": key == witness["baseline_action_key"],
            "features": witness["observable_features_by_action"][key],
        }
        for key in witness["action_keys"]
    ]
    row = {
        "baseline_action_key": witness["baseline_action_key"],
        "actions": actions,
    }
    selected, scores = grouped.choose(model, row, threshold)
    if selected not in witness["action_keys"]:
        raise ValueError("冻结模型选出非法弃牌")
    return {
        "selected_action_key": selected,
        "baseline_action_key": witness["baseline_action_key"],
        "changed": selected != witness["baseline_action_key"],
        "decision_threshold": threshold,
        "scores": dict(sorted(scores.items())),
    }


def _capture_source(
    *, panel_seed: int, mix: str, root_index: int, contract: dict,
    rules: HangmaRules, value_limits: ValueAnalysisLimits, frozen: dict,
) -> tuple[dict, dict[str, Any] | None]:
    """生成一个自然摸牌窗口，并在任何效果续局前冻结模型决定。"""

    focal_seat = (root_index - 1) % 4
    descriptor = core.stage.root_descriptor(
        generator=opportunities.GENERATOR_V2_BEHAVIOR,
        sub_scenario=LABEL,
        opponent_mix=mix,
        panel_seed=panel_seed,
        root_index=root_index,
    )
    source_root_id = str(descriptor["root_id"])
    match_id = f"dv1r-{panel_seed}-{mix}-r{root_index:03d}-s{focal_seat}"
    opponent_names = opportunities.opponent_policy_names(contract, mix)
    behavior = opportunities.frozen_generation_policies(
        opponent_names=opponent_names,
        focal_seat=focal_seat,
        monotonic=lambda: 800.0,
    )
    runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(contract["versions"]["rounds_per_game"]),
        seed=int(descriptor["root_seed"]),
        scenario_id=source_root_id,
    )
    attempt = opportunities.run_real_prefix_attempt(
        runtime=runtime,
        rules=rules,
        predicate_id=LABEL,
        focal_seat=focal_seat,
        attempt_index=root_index,
        source_root_id=source_root_id,
        match_id=match_id,
        tournament_config=opportunities._snapshot_tournament_config(
            {"rounds_per_game": int(contract["versions"]["rounds_per_game"])}, rules
        ),
        seed=int(descriptor["root_seed"]),
        value_limits=value_limits,
        behavior_policies_by_seat=behavior,
        opponent_names=opponent_names,
        opponent_scenario=mix,
        capture_condition=DiscardWindowCapture(),
    )
    common_row = {
        "schema": "r11-dv1-research-confirmation-source/1",
        "panel_seed": panel_seed,
        "mix": mix,
        "root_index": root_index,
        "focal_seat": focal_seat,
        "source_root_id": source_root_id,
    }
    if attempt.status != "hit":
        return {**common_row, "status": "MISS"}, None
    runtime_kind = opportunities.runtime_kind_of(runtime)
    runtime_evidence = {
        "runtime_kind": runtime_kind,
        "engine_kind": opportunities.ENGINE_KIND_BY_RUNTIME_KIND[runtime_kind],
        "execution_kind": opportunities.execution_kind_for(
            prefix_source="v2_behavior", runtime=runtime
        ),
        "runtime_source": str(runtime.get("runtime_entry")),
        "engine_identity": dict(runtime.get("engine_identity") or {}),
        "real_tables": True,
    }
    snapshot = opportunities.build_snapshot(
        prefix_source="v2_behavior",
        attempt=attempt,
        predicate_id=LABEL,
        focal_seat=focal_seat,
        opponent_scenario=mix,
        match_id=match_id,
        stage_ledger={"completed_table_scores": []},
        remaining_schedule={
            "declared_endpoint": "stage_complete",
            "remaining_tables_after_current": TABLES_PER_ARM - 1,
            "rounds_per_game": int(contract["versions"]["rounds_per_game"]),
            "tables_in_stage": TABLES_PER_ARM,
        },
        panel_seed=panel_seed,
        tables_in_stage=TABLES_PER_ARM,
        rounds_per_game=int(contract["versions"]["rounds_per_game"]),
        runtime_evidence=runtime_evidence,
        descriptor=descriptor,
        witness_entry="dv1_research_confirmation_first_draw_window",
    )
    witness = dict(attempt.predicate_witness or {})
    if not all(
        item.get("schema") == FEATURE_SCHEMA
        for item in witness["observable_features_by_action"].values()
    ):
        raise ValueError("确认窗口缺少冻结玩家可见动作编码")
    return {
        **common_row,
        "status": "SOURCE_HIT",
        "root_descriptor": descriptor,
        "snapshot": snapshot,
        "witness": witness,
        "decision": _decision(witness, frozen),
    }, runtime


def _runtime_for_source(source: dict, contract: dict, rules: HangmaRules) -> dict[str, Any]:
    """为可恢复来源重建同一模拟运行时。"""

    descriptor = source["root_descriptor"]
    return opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(contract["versions"]["rounds_per_game"]),
        seed=int(descriptor["root_seed"]),
        scenario_id=str(source["source_root_id"]),
    )


def _run_arm(
    *, source: dict, rollout_index: int, arm_name: str, action_key: str,
    sample_key: str, contract: dict, rules: HangmaRules,
    value_limits: ValueAnalysisLimits, runtime: dict[str, Any],
) -> dict:
    """完成一个共同未来顺序下的 V2 或冻结候选首弃牌臂。"""

    path = _arm_path(
        int(source["panel_seed"]), str(source["mix"]), int(source["root_index"]),
        rollout_index, arm_name,
    )
    if path.exists():
        return batch.read(path)
    focal_seat = int(source["focal_seat"])
    opponent_names = opportunities.opponent_policy_names(contract, str(source["mix"]))
    policies, forced = core.policies_for_arm(
        opponent_names=opponent_names,
        focal_seat=focal_seat,
        forced_action_key=action_key,
        target_window=_window(source["snapshot"]),
        arm_name=f"dv1r-{rollout_index:02d}-{arm_name}",
    )
    arm = opportunities.run_conditional_stage_arm(
        arm_name=arm_name,
        rules=rules,
        snapshot=source["snapshot"],
        policies_by_seat=policies,
        config=opportunities._driver_config(),
        value_limits=value_limits,
        runtime=runtime,
        current_world_transform=lambda world: runtime["engine"].resample_future_drawable_wall(
            world, sample_key=sample_key
        ),
    )
    review = arm.get("execution_review") or {}
    reading = arm.get("focal_action_at_cut") or {}
    mechanical_ok = bool(
        arm.get("usable")
        and forced.force_count == 1
        and reading.get("action_key") == action_key
        and arm.get("focal_action_at_cut_status") == "collected"
        and review.get("status") == "complete"
        and review.get("zero_internal_failures_verified") is True
    )
    row = {
        "schema": "r11-dv1-research-confirmation-rollout/1",
        "panel_seed": source["panel_seed"],
        "mix": source["mix"],
        "root_index": source["root_index"],
        "source_root_id": source["source_root_id"],
        "sample_key": sample_key,
        "arm_name": arm_name,
        "action_key": action_key,
        "actual_cut_action": reading.get("action_key"),
        "force_count": forced.force_count,
        "outcome": {
            "u_low": arm.get("u_low"),
            "u_high": arm.get("u_high"),
            "focal_stage_score": arm.get("focal_stage_score"),
        },
        "mechanical_ok": mechanical_ok,
        "tables_executed": arm.get("tables_executed"),
        "elapsed_ms": arm.get("elapsed_ms"),
        "error": arm.get("error"),
    }
    batch.write(path, row)
    return row


def _worker(panel_seed: int, mix: str, manifest: dict, contract: dict, frozen: dict) -> dict:
    """顺序处理一个确认分片；分片之间并行。"""

    rules = HangmaRules(core.rule_config_from_contract(contract))
    value_limits = ValueAnalysisLimits()
    valid_snapshots = 0
    attempts = 0
    changed_snapshots = 0
    mechanical_failure = None
    for root_index in range(1, MAX_ROOTS_PER_SHARD + 1):
        if valid_snapshots >= TARGET_SNAPSHOTS_PER_SHARD or mechanical_failure:
            break
        attempts = root_index
        path = _root_path(panel_seed, mix, root_index)
        if path.exists():
            source = batch.read(path)
            runtime = None
        else:
            source, runtime = _capture_source(
                panel_seed=panel_seed,
                mix=mix,
                root_index=root_index,
                contract=contract,
                rules=rules,
                value_limits=value_limits,
                frozen=frozen,
            )
            batch.write(path, source)
        if source["status"] == "MISS":
            continue
        if source["decision"]["changed"]:
            changed_snapshots += 1
            if runtime is None:
                runtime = _runtime_for_source(source, contract, rules)
            rows = []
            for rollout_index, sample_key in enumerate(manifest["sample_keys"], start=1):
                rows.append(_run_arm(
                    source=source,
                    rollout_index=rollout_index,
                    arm_name="baseline",
                    action_key=source["decision"]["baseline_action_key"],
                    sample_key=sample_key,
                    contract=contract,
                    rules=rules,
                    value_limits=value_limits,
                    runtime=runtime,
                ))
                rows.append(_run_arm(
                    source=source,
                    rollout_index=rollout_index,
                    arm_name="candidate",
                    action_key=source["decision"]["selected_action_key"],
                    sample_key=sample_key,
                    contract=contract,
                    rules=rules,
                    value_limits=value_limits,
                    runtime=runtime,
                ))
            failures = [
                {"sample_key": row["sample_key"], "arm_name": row["arm_name"]}
                for row in rows if not row["mechanical_ok"]
            ]
            if failures:
                mechanical_failure = {
                    "panel_seed": panel_seed,
                    "mix": mix,
                    "root_index": root_index,
                    "failures": failures,
                }
                break
        valid_snapshots += 1
    return {
        "panel_seed": panel_seed,
        "mix": mix,
        "attempts": attempts,
        "valid_snapshots": valid_snapshots,
        "changed_snapshots": changed_snapshots,
        "complete": valid_snapshots >= TARGET_SNAPSHOTS_PER_SHARD,
        "mechanical_failure": mechanical_failure,
    }


def _compact_source(source: dict, manifest: dict) -> dict:
    """把同窗决定和 16 个配对结果压成一个独立快照读数。"""

    decision = source["decision"]
    if not decision["changed"]:
        auxiliary = [0.0] * ROLLOUTS_PER_CHANGED_SNAPSHOT
        primary_low = [0.0] * ROLLOUTS_PER_CHANGED_SNAPSHOT
        primary_high = [0.0] * ROLLOUTS_PER_CHANGED_SNAPSHOT
    else:
        auxiliary = []
        primary_low = []
        primary_high = []
        for rollout_index, _ in enumerate(manifest["sample_keys"], start=1):
            baseline = batch.read(_arm_path(
                int(source["panel_seed"]), str(source["mix"]),
                int(source["root_index"]), rollout_index, "baseline",
            ))
            selected = batch.read(_arm_path(
                int(source["panel_seed"]), str(source["mix"]),
                int(source["root_index"]), rollout_index, "candidate",
            ))
            auxiliary.append(
                float(selected["outcome"]["focal_stage_score"])
                - float(baseline["outcome"]["focal_stage_score"])
            )
            primary_low.append(
                float(selected["outcome"]["u_low"])
                - float(baseline["outcome"]["u_low"])
            )
            primary_high.append(
                float(selected["outcome"]["u_high"])
                - float(baseline["outcome"]["u_high"])
            )
    return {
        "row_id": f"s{source['panel_seed']}:{source['mix']}:{source['source_root_id']}",
        "group": {
            "panel_seed": source["panel_seed"],
            "mix": source["mix"],
            "source_root_id": source["source_root_id"],
            "root_index": source["root_index"],
        },
        "baseline_action_key": decision["baseline_action_key"],
        "selected_action_key": decision["selected_action_key"],
        "changed": decision["changed"],
        "selected_score": decision["scores"][decision["selected_action_key"]],
        "decision_threshold": decision["decision_threshold"],
        "labels": {
            "auxiliary_values": auxiliary,
            "auxiliary_mean": statistics.fmean(auxiliary),
            "u_low_values": primary_low,
            "u_low_mean": statistics.fmean(primary_low),
            "u_high_mean": statistics.fmean(primary_high),
        },
    }


def _metrics(rows: list[dict]) -> dict:
    """按独立快照为统计单位汇总确认读数。"""

    auxiliary = [float(row["labels"]["auxiliary_mean"]) for row in rows]
    primary = [float(row["labels"]["u_low_mean"]) for row in rows]
    mean = statistics.fmean(auxiliary)
    standard_error = statistics.stdev(auxiliary) / math.sqrt(len(auxiliary))
    return {
        "snapshots": len(rows),
        "auxiliary_mean": mean,
        "auxiliary_standard_error": standard_error,
        "auxiliary_ci95": [mean - 1.96 * standard_error, mean + 1.96 * standard_error],
        "u_low_mean": statistics.fmean(primary),
        "changed_rate": statistics.fmean(float(row["changed"]) for row in rows),
    }


def run() -> None:
    """执行独立确认并按预登记统计门裁定。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("DV1-2R 确认结果已存在；拒绝覆盖")
    contract = batch.read(core.CONTRACT)
    frozen = batch.read(CANDIDATE)
    summaries: list[dict] = []
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=min(8, len(SHARDS))) as executor:
            futures = [
                executor.submit(_worker, seed, mix, manifest, contract, frozen)
                for seed, mix in SHARDS
            ]
            for future in concurrent.futures.as_completed(futures):
                summaries.append(future.result())
    except Exception as exc:
        batch.write(_project_file(_PROJECT_ROOT, OUT / "failure.json"), {
            "schema": "r11-dv1-research-confirmation-failure/1",
            "status": "INTERRUPTED_RESUMABLE",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "completed_shards": sorted(
                summaries, key=lambda item: (item["panel_seed"], item["mix"])
            ),
        })
        raise

    summaries.sort(key=lambda item: (item["panel_seed"], item["mix"]))
    compact = []
    for seed, mix in SHARDS:
        hits = 0
        for root_index in range(1, MAX_ROOTS_PER_SHARD + 1):
            path = _root_path(seed, mix, root_index)
            if not path.exists():
                break
            source = batch.read(path)
            if source["status"] != "SOURCE_HIT":
                continue
            compact.append(_compact_source(source, manifest))
            hits += 1
            if hits >= TARGET_SNAPSHOTS_PER_SHARD:
                break

    all_mechanical = all(item["mechanical_failure"] is None for item in summaries)
    complete = all(item["complete"] for item in summaries)
    overall = _metrics(compact)
    by_seed = {
        str(seed): _metrics([row for row in compact if row["group"]["panel_seed"] == seed])
        for seed in PANEL_SEEDS
    }
    by_mix = {
        mix: _metrics([row for row in compact if row["group"]["mix"] == mix])
        for mix in MIXES
    }
    changed = [row for row in compact if row["changed"]]
    changed_counts = Counter(row["selected_action_key"] for row in changed)
    max_changed_fraction = max(changed_counts.values()) / len(changed) if changed else 1.0
    behavior_ok = bool(
        0.05 <= overall["changed_rate"] <= 0.50
        and max_changed_fraction < 0.80
    )
    effect_ok = bool(
        overall["auxiliary_ci95"][0] > 0
        and overall["u_low_mean"] >= 0
        and all(item["auxiliary_mean"] >= 0 for item in by_mix.values())
    )
    if not all_mechanical:
        status = "STOP_DV1_2R_MECHANICAL_FAILURE"
        next_step = "修复独立确认执行接缝；效果读数不得使用"
    elif not complete:
        status = "CLOSE_DV1_2R_INCOMPLETE_CONFIRMATION"
        next_step = "来源预算内未形成128个快照；不得按结果补样"
    elif behavior_ok and effect_ok:
        status = "PASS_DV1_2R_FOR_FULL_STAGE_CANDIDATE_COMPILATION"
        next_step = "把冻结模型提炼为确定性启发式候选，执行完整阶段24→8→3级联和新来源复核"
    else:
        status = "CLOSE_DV1_2R_INDEPENDENT_CONFIRMATION_FAILED"
        next_step = "关闭当前价值蒸馏候选；复盘阶段价值连接或隐藏状态平均，不再调本同族参数"
    batch.write(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), {
        "schema": "r11-dv1-research-confirmation-rows/1",
        "candidate_sha256": digest(CANDIDATE),
        "rows": compact,
    })
    result = {
        "schema": "r11-dv1-research-confirmation-result/1",
        "status": status,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "dataset_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "dataset.json")),
        "candidate_sha256": digest(CANDIDATE),
        "shards": summaries,
        "summary": {
            "overall": overall,
            "by_panel_seed": by_seed,
            "by_mix": by_mix,
            "changed_action_counts": dict(sorted(changed_counts.items())),
            "max_changed_action_fraction": max_changed_fraction,
            "paired_action_rollouts": len(changed) * ROLLOUTS_PER_CHANGED_SNAPSHOT * 2,
            "full_or_partial_tables": len(changed) * ROLLOUTS_PER_CHANGED_SNAPSHOT * 2 * TABLES_PER_ARM,
            "all_mechanical": all_mechanical,
            "complete": complete,
            "behavior_ok": behavior_ok,
            "effect_ok": effect_ok,
            "original_grouped_gate_passed": False,
            "multiple_models_screened_before_confirmation": 11,
            "strength_claim": False,
        },
        "next": next_step,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    verify_inputs(manifest)
    print(json.dumps({"status": status, **result["summary"], "next": next_step}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
