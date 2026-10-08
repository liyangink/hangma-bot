"""R11-DV1-2：按预登记分级采样采集规模化弃牌动作价值教师。"""

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
import concurrent.futures
import hashlib
import json
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


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/discard-value-scaled-teacher-01-20260921')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R11-DISCARD-ACTION-VALUE-EVOLUTION-PLAN-2026-09-21.md')
PANEL_SEEDS = (2026092340, 2026092341, 2026092342, 2026092343)
MIXES = ("H", "M")
SHARDS = tuple((seed, mix) for seed in PANEL_SEEDS for mix in MIXES)
TARGET_SNAPSHOTS_PER_SHARD = 16
MAX_ROOTS_PER_SHARD = 32
STAGE1_ROLLOUTS = 4
STAGE2_ROLLOUTS = 8
STAGE3_ROLLOUTS = 16
STAGE2_TARGET_ALTERNATIVES = 4
STAGE2_MAX_ALTERNATIVES = 6
STAGE3_TARGET_ALTERNATIVES = 2
STAGE3_MAX_ALTERNATIVES = 4
MAX_ACTIONS_PER_SNAPSHOT = 14
TABLES_PER_ARM = core.TABLES_PER_ARM
MAX_SNAPSHOTS = len(SHARDS) * TARGET_SNAPSHOTS_PER_SHARD
MAX_ARMS_PER_SNAPSHOT = (
    STAGE1_ROLLOUTS * MAX_ACTIONS_PER_SNAPSHOT
    + (STAGE2_ROLLOUTS - STAGE1_ROLLOUTS)
    * (1 + STAGE2_MAX_ALTERNATIVES)
    + (STAGE3_ROLLOUTS - STAGE2_ROLLOUTS)
    * (1 + STAGE3_MAX_ALTERNATIVES)
)
MAX_TABLES = MAX_SNAPSHOTS * MAX_ARMS_PER_SNAPSHOT * TABLES_PER_ARM
LABEL = "r11_dv1_scaled_discard_teacher"


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


class DiscardWindowCapture:
    """截取稳定 V2 首选为弃牌且至少有两个合法弃牌的自然摸牌窗口。"""

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
        if len(action_keys) > MAX_ACTIONS_PER_SNAPSHOT:
            raise ValueError("合法弃牌种类超过手牌上界")
        return {
            "baseline_action_key": baseline_key,
            "action_keys": action_keys,
            "observable_features_by_action": {
                key: encode_discard_value_features(request, key)
                for key in action_keys
            },
            "candidate_id": str(
                getattr(self.policy, "policy_id", type(self.policy).__name__)
            ),
        }


def source_paths() -> list[Path]:
    """列出试点身份冻结的代码、计划和合同。"""

    import hangma_bot.offline.discard_value_features as features
    import hangma_bot.offline.forced_action as forced_action
    import hangma_bot.simulation.engine as simulation_engine
    import hangma_bot.simulation.shuffle as simulation_shuffle

    return [
        Path(__file__), Path(core.__file__), Path(opportunities.__file__),
        Path(features.__file__), Path(forced_action.__file__),
        Path(simulation_engine.__file__), Path(simulation_shuffle.__file__),
        PLAN, core.CONTRACT, core.ROUTE_SOURCE,
    ]


def prepare() -> None:
    """冻结新来源、十六个未来顺序和三阶段动作预算分配。"""

    if OUT.exists():
        raise SystemExit("DV1-2 目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "roots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "raw")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / ".gitignore")).write_text("/roots/\n/raw/\n", encoding="utf-8")
    authorization = batch.unified_document(
        batch_label="r11-dv1-scaled-discard-teacher-v1",
        authorization_id="r11-dv1-scaled-discard-teacher-v1-20260921",
        accounts={
            "tables_full": MAX_TABLES,
            "prefix_generation": len(SHARDS) * MAX_ROOTS_PER_SHARD,
        },
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "DV1-1机械与机会门通过；试点最佳替代动作配对增益中位数+8.625、标准差中位数23.524；计划已冻结分级采样",
        "scope": "四个全新panel_seed；每个seed×H/M前16个自然摸牌窗口；全部合法弃牌先4轨迹，预登记分级追加到8/16轨迹；首动作后恢复V2",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r11-dv1-scaled-discard-teacher/1",
        "execution_revision": 1,
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "contract": str(core.CONTRACT),
        "contract_sha256": digest(core.CONTRACT),
        "feature_schema": FEATURE_SCHEMA,
        "panel_seeds": list(PANEL_SEEDS),
        "mixes": list(MIXES),
        "target_snapshots_per_shard": TARGET_SNAPSHOTS_PER_SHARD,
        "max_roots_per_shard": MAX_ROOTS_PER_SHARD,
        "rollout_stages": [
            {
                "total_rollouts": STAGE1_ROLLOUTS,
                "alternatives": "all",
            },
            {
                "total_rollouts": STAGE2_ROLLOUTS,
                "target_alternatives": STAGE2_TARGET_ALTERNATIVES,
                "max_alternatives": STAGE2_MAX_ALTERNATIVES,
            },
            {
                "total_rollouts": STAGE3_ROLLOUTS,
                "target_alternatives": STAGE3_TARGET_ALTERNATIVES,
                "max_alternatives": STAGE3_MAX_ALTERNATIVES,
            },
        ],
        "sample_keys": [
            f"future-order-{index:02d}"
            for index in range(1, STAGE3_ROLLOUTS + 1)
        ],
        "selection": "每个seed×mix按root_index升序取前16个V2首选为discard且同窗至少两个合法discard的自然draw窗口；全部合法弃牌进入首阶段；不读取未执行未来顺序",
        "teacher": "每个未来顺序下基准V2弃牌只执行一次；替代弃牌共享该基准和同一世界重排；随后均恢复稳定V2",
        "allocation": "第1阶段全动作4轨迹；按配对辅助均值降序保留前4替代动作并纳入第4名并列、最多6个，追加到8轨迹；再按8轨迹配对均值保留前2并纳入第2名并列、最多4个，追加到16轨迹；并列上限按action_key稳定截断；基准始终16轨迹",
        "continue_gate": "128快照机械全绿且完整；冻结数据集后按快照分组训练与留出；当前批不作学生强度结论",
        "student_information": "仅PlayerObservation、CompetitionContext、HangmaRules候选事实和具体弃牌；无WorldState、未来、来源、面板种子或对手身份",
        "max_snapshots": MAX_SNAPSHOTS,
        "max_actions_per_snapshot": MAX_ACTIONS_PER_SNAPSHOT,
        "max_arms_per_snapshot": MAX_ARMS_PER_SNAPSHOT,
        "max_tables": MAX_TABLES,
        "llm_calls": 0,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({
        "status": "PREPARED_DV1_2_SCALED_TEACHER",
        "snapshots": MAX_SNAPSHOTS,
        "max_tables": MAX_TABLES,
    }, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """核对代码、计划、合同和父代未漂移。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (
        ("plan", "plan_sha256"),
        ("contract", "contract_sha256"),
    ):
        if digest(Path(manifest[path_key])) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")


def _root_path(panel_seed: int, mix: str, root_index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "roots" / f"s{panel_seed}-{mix}-root{root_index:03d}.json")


def _arm_path(
    panel_seed: int, mix: str, root_index: int, rollout_index: int, action_index: int
) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "raw" / (
        f"s{panel_seed}-{mix}-root{root_index:03d}"
        f"-r{rollout_index:02d}-a{action_index:02d}.json"
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


def _capture_source(
    *, panel_seed: int, mix: str, root_index: int, contract: dict,
    rules: HangmaRules, value_limits: ValueAnalysisLimits,
) -> tuple[dict, dict[str, Any] | None]:
    """生成自然摸牌窗口快照，不执行任何效果臂。"""

    focal_seat = (root_index - 1) % 4
    descriptor = core.stage.root_descriptor(
        generator=opportunities.GENERATOR_V2_BEHAVIOR,
        sub_scenario=LABEL,
        opponent_mix=mix,
        panel_seed=panel_seed,
        root_index=root_index,
    )
    source_root_id = str(descriptor["root_id"])
    match_id = f"dv1-{panel_seed}-{mix}-r{root_index:03d}-s{focal_seat}"
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
    common = {
        "schema": "r11-dv1-scaled-discard-source/1",
        "panel_seed": panel_seed,
        "mix": mix,
        "root_index": root_index,
        "focal_seat": focal_seat,
        "source_root_id": source_root_id,
    }
    if attempt.status != "hit":
        return {**common, "status": "MISS"}, None
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
        witness_entry="dv1_scaled_teacher_first_draw_window",
    )
    witness = dict(attempt.predicate_witness or {})
    if not all(
        item.get("schema") == FEATURE_SCHEMA
        for item in witness["observable_features_by_action"].values()
    ):
        raise ValueError("弃牌窗口缺少冻结玩家可见动作编码")
    return {
        **common,
        "status": "SOURCE_HIT",
        "root_descriptor": descriptor,
        "snapshot": snapshot,
        "witness": witness,
    }, runtime


def _runtime_for_source(source: dict, contract: dict, rules: HangmaRules) -> dict[str, Any]:
    descriptor = source["root_descriptor"]
    return opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(contract["versions"]["rounds_per_game"]),
        seed=int(descriptor["root_seed"]),
        scenario_id=str(source["source_root_id"]),
    )


def _run_arm(
    *, source: dict, rollout_index: int, action_index: int, action_key: str,
    sample_key: str, contract: dict, rules: HangmaRules,
    value_limits: ValueAnalysisLimits, runtime: dict[str, Any],
) -> dict:
    """完成一个确定性未来顺序下的一个首弃牌臂。"""

    path = _arm_path(
        int(source["panel_seed"]), str(source["mix"]), int(source["root_index"]),
        rollout_index, action_index,
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
        arm_name=f"dv1-scaled-r{rollout_index:02d}-a{action_index:02d}",
    )
    arm = opportunities.run_conditional_stage_arm(
        arm_name=f"action-{action_index:02d}",
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
        "schema": "r11-dv1-scaled-discard-rollout/1",
        "panel_seed": source["panel_seed"],
        "mix": source["mix"],
        "root_index": source["root_index"],
        "source_root_id": source["source_root_id"],
        "sample_key": sample_key,
        "action_index": action_index,
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


def _select_alternatives(
    *, source: dict, through_rollout: int, eligible_alternatives: list[str],
    target: int, cap: int,
) -> tuple[list[str], dict[str, float]]:
    """按已冻结共同未来顺序上的配对均值选追加预算动作。"""

    action_keys = list(source["witness"]["action_keys"])
    action_indexes = {key: index for index, key in enumerate(action_keys)}
    baseline_key = str(source["witness"]["baseline_action_key"])
    baseline_index = action_indexes[baseline_key]
    means: dict[str, float] = {}
    for action_key in eligible_alternatives:
        action_index = action_indexes[action_key]
        deltas = []
        for rollout_index in range(1, through_rollout + 1):
            action = batch.read(_arm_path(
                int(source["panel_seed"]), str(source["mix"]),
                int(source["root_index"]), rollout_index, action_index,
            ))
            baseline = batch.read(_arm_path(
                int(source["panel_seed"]), str(source["mix"]),
                int(source["root_index"]), rollout_index, baseline_index,
            ))
            deltas.append(
                float(action["outcome"]["focal_stage_score"])
                - float(baseline["outcome"]["focal_stage_score"])
            )
        means[action_key] = statistics.fmean(deltas)
    ordered = sorted(eligible_alternatives, key=lambda key: (-means[key], key))
    if len(ordered) <= target:
        return ordered, means
    threshold = means[ordered[target - 1]]
    selected = [key for key in ordered if means[key] >= threshold]
    return selected[:cap], means


def _worker(panel_seed: int, mix: str, manifest: dict, contract: dict) -> dict:
    """顺序处理一个来源分片；八个分片按固定并发上限执行。"""

    rules = HangmaRules(core.rule_config_from_contract(contract))
    value_limits = ValueAnalysisLimits()
    valid_snapshots = 0
    attempts = 0
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
                panel_seed=panel_seed, mix=mix, root_index=root_index,
                contract=contract, rules=rules, value_limits=value_limits,
            )
            batch.write(path, source)
        if source["status"] == "MISS":
            continue
        if runtime is None:
            runtime = _runtime_for_source(source, contract, rules)
        action_keys = list(source["witness"]["action_keys"])
        baseline_key = str(source["witness"]["baseline_action_key"])
        alternatives = [key for key in action_keys if key != baseline_key]
        action_indexes = {key: index for index, key in enumerate(action_keys)}
        rows = []
        for rollout_index in range(1, STAGE1_ROLLOUTS + 1):
            sample_key = manifest["sample_keys"][rollout_index - 1]
            for action_index, action_key in enumerate(action_keys):
                rows.append(_run_arm(
                    source=source,
                    rollout_index=rollout_index,
                    action_index=action_index,
                    action_key=action_key,
                    sample_key=sample_key,
                    contract=contract,
                    rules=rules,
                    value_limits=value_limits,
                    runtime=runtime,
                ))
        stage2_alternatives, _ = _select_alternatives(
            source=source,
            through_rollout=STAGE1_ROLLOUTS,
            eligible_alternatives=alternatives,
            target=STAGE2_TARGET_ALTERNATIVES,
            cap=STAGE2_MAX_ALTERNATIVES,
        )
        stage2_actions = [baseline_key, *stage2_alternatives]
        for rollout_index in range(STAGE1_ROLLOUTS + 1, STAGE2_ROLLOUTS + 1):
            sample_key = manifest["sample_keys"][rollout_index - 1]
            for action_key in stage2_actions:
                rows.append(_run_arm(
                    source=source,
                    rollout_index=rollout_index,
                    action_index=action_indexes[action_key],
                    action_key=action_key,
                    sample_key=sample_key,
                    contract=contract,
                    rules=rules,
                    value_limits=value_limits,
                    runtime=runtime,
                ))
        stage3_alternatives, _ = _select_alternatives(
            source=source,
            through_rollout=STAGE2_ROLLOUTS,
            eligible_alternatives=stage2_alternatives,
            target=STAGE3_TARGET_ALTERNATIVES,
            cap=STAGE3_MAX_ALTERNATIVES,
        )
        stage3_actions = [baseline_key, *stage3_alternatives]
        for rollout_index in range(STAGE2_ROLLOUTS + 1, STAGE3_ROLLOUTS + 1):
            sample_key = manifest["sample_keys"][rollout_index - 1]
            for action_key in stage3_actions:
                rows.append(_run_arm(
                    source=source,
                    rollout_index=rollout_index,
                    action_index=action_indexes[action_key],
                    action_key=action_key,
                    sample_key=sample_key,
                    contract=contract,
                    rules=rules,
                    value_limits=value_limits,
                    runtime=runtime,
                ))
        failures = [
            {"sample_key": row["sample_key"], "action_key": row["action_key"]}
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
        "complete": valid_snapshots >= TARGET_SNAPSHOTS_PER_SHARD,
        "mechanical_failure": mechanical_failure,
    }


def _compact_source(source: dict, manifest: dict) -> dict:
    """压缩分级轨迹，并保留每个动作实际获得的配对样本数。"""

    action_keys = list(source["witness"]["action_keys"])
    baseline_key = str(source["witness"]["baseline_action_key"])
    action_indexes = {key: index for index, key in enumerate(action_keys)}
    alternatives = [key for key in action_keys if key != baseline_key]
    stage2_alternatives, stage1_means = _select_alternatives(
        source=source,
        through_rollout=STAGE1_ROLLOUTS,
        eligible_alternatives=alternatives,
        target=STAGE2_TARGET_ALTERNATIVES,
        cap=STAGE2_MAX_ALTERNATIVES,
    )
    stage3_alternatives, stage2_means = _select_alternatives(
        source=source,
        through_rollout=STAGE2_ROLLOUTS,
        eligible_alternatives=stage2_alternatives,
        target=STAGE3_TARGET_ALTERNATIVES,
        cap=STAGE3_MAX_ALTERNATIVES,
    )
    rows_by_key: dict[str, list[dict]] = {}
    for action_key in action_keys:
        rows = []
        action_index = action_indexes[action_key]
        for rollout_index in range(1, STAGE3_ROLLOUTS + 1):
            path = _arm_path(
                int(source["panel_seed"]), str(source["mix"]),
                int(source["root_index"]), rollout_index, action_index,
            )
            if not path.exists():
                break
            rows.append(batch.read(path))
        rows_by_key[action_key] = rows
    if len(rows_by_key[baseline_key]) != STAGE3_ROLLOUTS:
        raise ValueError("基准弃牌未完成全部十六个预登记未来顺序")

    winners_by_rollout: list[list[str]] = []
    eligible_by_rollout = (
        [action_keys] * STAGE1_ROLLOUTS
        + [[baseline_key, *stage2_alternatives]]
        * (STAGE2_ROLLOUTS - STAGE1_ROLLOUTS)
        + [[baseline_key, *stage3_alternatives]]
        * (STAGE3_ROLLOUTS - STAGE2_ROLLOUTS)
    )
    for rollout_index, eligible in enumerate(eligible_by_rollout, start=1):
        round_rows = [rows_by_key[key][rollout_index - 1] for key in eligible]
        best_score = max(float(row["outcome"]["focal_stage_score"]) for row in round_rows)
        winners_by_rollout.append(sorted(
            row["action_key"] for row in round_rows
            if float(row["outcome"]["focal_stage_score"]) == best_score
        ))
    baseline_rows = rows_by_key[baseline_key]
    actions = []
    for action_key in action_keys:
        action_rows = rows_by_key[action_key]
        paired_baseline_rows = baseline_rows[:len(action_rows)]
        auxiliary = [
            float(action["outcome"]["focal_stage_score"])
            - float(base["outcome"]["focal_stage_score"])
            for action, base in zip(action_rows, paired_baseline_rows)
        ]
        primary_low = [
            float(action["outcome"]["u_low"])
            - float(base["outcome"]["u_low"])
            for action, base in zip(action_rows, paired_baseline_rows)
        ]
        primary_high = [
            float(action["outcome"]["u_high"])
            - float(base["outcome"]["u_high"])
            for action, base in zip(action_rows, paired_baseline_rows)
        ]
        auxiliary_stdev = statistics.stdev(auxiliary)
        actions.append({
            "action_key": action_key,
            "is_v2_baseline": action_key == baseline_key,
            "features": source["witness"]["observable_features_by_action"][action_key],
            "labels": {
                "auxiliary_values": auxiliary,
                "auxiliary_mean": statistics.fmean(auxiliary),
                "auxiliary_stdev": auxiliary_stdev,
                "auxiliary_standard_error": auxiliary_stdev / len(auxiliary) ** 0.5,
                "rollout_count": len(auxiliary),
                "u_low_values": primary_low,
                "u_low_mean": statistics.fmean(primary_low),
                "u_high_mean": statistics.fmean(primary_high),
            },
        })
    stage1_winner_support = Counter(
        key for winners in winners_by_rollout[:STAGE1_ROLLOUTS] for key in winners
    )
    stage1_stable_winners = sorted(
        key for key, count in stage1_winner_support.items() if count >= 3
    )
    positive_alternatives = [
        item["action_key"] for item in actions
        if not item["is_v2_baseline"]
        and item["labels"]["auxiliary_mean"] > 0
        and item["labels"]["u_low_mean"] >= 0
    ]
    return {
        "row_id": f"s{source['panel_seed']}:{source['mix']}:{source['source_root_id']}",
        "group": {
            "panel_seed": source["panel_seed"],
            "mix": source["mix"],
            "source_root_id": source["source_root_id"],
            "root_index": source["root_index"],
        },
        "baseline_action_key": baseline_key,
        "actions": actions,
        "winners_by_rollout": winners_by_rollout,
        "allocation": {
            "stage1_rollouts": STAGE1_ROLLOUTS,
            "stage1_paired_means": dict(sorted(stage1_means.items())),
            "stage2_alternatives": stage2_alternatives,
            "stage2_rollouts": STAGE2_ROLLOUTS,
            "stage2_paired_means": dict(sorted(stage2_means.items())),
            "stage3_alternatives": stage3_alternatives,
            "stage3_rollouts": STAGE3_ROLLOUTS,
        },
        "stage1_winner_support": dict(sorted(stage1_winner_support.items())),
        "stage1_stable_winners": stage1_stable_winners,
        "stage1_ranking_stable": bool(stage1_stable_winners),
        "positive_alternatives": positive_alternatives,
    }


def run() -> None:
    """执行八分片规模化教师采集并冻结分组数据集。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("DV1-2 教师已形成结果；拒绝覆盖")
    contract = batch.read(core.CONTRACT)
    summaries: list[dict] = []
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=min(8, len(SHARDS))) as executor:
            futures = [
                executor.submit(_worker, seed, mix, manifest, contract)
                for seed, mix in SHARDS
            ]
            for future in concurrent.futures.as_completed(futures):
                summaries.append(future.result())
    except Exception as exc:
        batch.write(_project_file(_PROJECT_ROOT, OUT / "failure.json"), {
            "schema": "r11-dv1-scaled-discard-teacher-failure/1",
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
    positive = sum(bool(item["positive_alternatives"]) for item in compact)
    unstable = sum(not item["stage1_ranking_stable"] for item in compact)
    action_counts = [len(item["actions"]) for item in compact]
    rollout_counts = [
        int(action["labels"]["rollout_count"])
        for item in compact for action in item["actions"]
    ]
    total_arms = sum(rollout_counts)
    if not all_mechanical:
        status = "STOP_DV1_2_MECHANICAL_FAILURE"
        next_step = "修复强制弃牌或多臂执行接缝；当前效果读数不得使用"
    elif not complete:
        status = "CLOSE_DV1_2_INSUFFICIENT_WINDOWS"
        next_step = "复盘自然摸牌窗口定义和来源预算；不得按结果补样"
    else:
        status = "PASS_DV1_2_SCALED_TEACHER_FOR_GROUPED_MODELING"
        next_step = "冻结快照分组，训练低容量成对排序器、受限树与广义加性模型；完整面板留出不得拆窗"

    batch.write(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), {
        "schema": "r11-dv1-scaled-discard-teacher-rows/1",
        "feature_schema": FEATURE_SCHEMA,
        "rows": compact,
    })
    result = {
        "schema": "r11-dv1-scaled-discard-teacher-result/1",
        "status": status,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "dataset_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "dataset.json")),
        "shards": summaries,
        "summary": {
            "snapshots": len(compact),
            "action_counts": {
                "min": min(action_counts) if action_counts else None,
                "max": max(action_counts) if action_counts else None,
                "mean": statistics.fmean(action_counts) if action_counts else None,
            },
            "paired_action_rollouts": total_arms,
            "full_or_partial_tables": total_arms * TABLES_PER_ARM,
            "rollout_counts": {
                "four": sum(value == STAGE1_ROLLOUTS for value in rollout_counts),
                "eight": sum(value == STAGE2_ROLLOUTS for value in rollout_counts),
                "sixteen": sum(value == STAGE3_ROLLOUTS for value in rollout_counts),
            },
            "positive_alternative_snapshots": positive,
            "stage1_ranking_stable_snapshots": len(compact) - unstable,
            "stage1_ranking_unstable_snapshots": unstable,
            "all_mechanical": all_mechanical,
            "complete": complete,
            "strength_claim": False,
        },
        "next": next_step,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    verify_inputs(manifest)
    print(json.dumps({
        "status": status,
        **result["summary"],
        "next": next_step,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    args = parser.parse_args()
    globals()[args.operation]()
