"""AV2-1：以八个未来可摸顺序平均的吃碰动作价值训练池。"""

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
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
REPO = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROUTE / "tools"), _project_file(_PROJECT_ROOT, ROUTE / "evidence/v4-impl/r9-gate2/run"), HERE):
    sys.path.insert(0, str(path))

import claim_counterfactual_pilot as core  # noqa: E402
import claim_value_dataset as av1_dataset  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.actions import WindowKey, WindowPhase  # noqa: E402
from hangma_bot.offline.claim_value_features import SCHEMA as FEATURE_SCHEMA  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/claim-value-averaged-02-20260921')
PLAN = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/R10-AVERAGED-TEACHER-EVOLUTION-PLAN-2026-09-21.md')
PANEL_SEEDS = (2026092320, 2026092321)
MIXES = ("H", "M")
TARGET_SNAPSHOTS_PER_SHARD = 16
MAX_ROOTS_PER_SHARD = 96
ROLLOUTS_PER_SNAPSHOT = 8
TABLES_PER_ARM = core.TABLES_PER_ARM
SHARDS = tuple((seed, mix) for seed in PANEL_SEEDS for mix in MIXES)
MAX_SNAPSHOTS = len(SHARDS) * TARGET_SNAPSHOTS_PER_SHARD
MAX_TABLES = MAX_SNAPSHOTS * ROLLOUTS_PER_SNAPSHOT * 2 * TABLES_PER_ARM
MAX_PREFIX_ROOTS = len(SHARDS) * MAX_ROOTS_PER_SHARD
LABEL = "r10_av2_averaged_teacher"


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_paths() -> list[Path]:
    """列出执行身份需要冻结的实现、计划与合同。"""

    import hangma_bot.offline.claim_value_features as features
    import hangma_bot.offline.forced_action as forced_action
    import hangma_bot.simulation.engine as simulation_engine
    import hangma_bot.simulation.shuffle as simulation_shuffle

    return [
        Path(__file__),
        Path(core.__file__),
        Path(av1_dataset.__file__),
        Path(opportunities.__file__),
        Path(features.__file__),
        Path(forced_action.__file__),
        Path(simulation_engine.__file__),
        Path(simulation_shuffle.__file__),
        PLAN,
        core.CONTRACT,
        core.ROUTE_SOURCE,
    ]


def prepare() -> None:
    """冻结全新来源、八轨迹教师、预算、选择顺序和机械门禁。"""

    if OUT.exists():
        raise SystemExit("AV2-1 目录已存在；拒绝覆盖")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "roots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "raw")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / ".gitignore")).write_text("/roots/\n/raw/\n", encoding="utf-8")
    authorization = batch.unified_document(
        batch_label="r10-av2-averaged-action-value-dataset-v2",
        authorization_id="r10-av2-averaged-action-value-dataset-v2-20260921",
        accounts={"tables_full": MAX_TABLES, "prefix_generation": MAX_PREFIX_ROOTS},
        issued_by="lead",
        issued_at_utc=batch.search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "AV1-TV1证明单轨迹标签受未来摸牌顺序显著污染；按Suphx奖励预测和rollout期望条件转入八顺序平均教师",
        "scope": "两个全新panel_seed；每个seed×H/M按root_index升序取前16个自然机会；每快照8个未来可摸区重排；过牌/具体吃碰使用同一重排配对",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    runtime = guard.capture(source_paths=source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json")])
    manifest = {
        "schema": "r10-av2-averaged-action-value-dataset/1",
        "execution_revision": 2,
        "created_at_utc": batch.search.utc_now(),
        "runtime": runtime,
        "plan": str(PLAN),
        "plan_sha256": digest(PLAN),
        "contract": str(core.CONTRACT),
        "contract_sha256": digest(core.CONTRACT),
        "route_source": str(core.ROUTE_SOURCE),
        "route_source_sha256": digest(core.ROUTE_SOURCE),
        "feature_schema": FEATURE_SCHEMA,
        "panel_seeds": list(PANEL_SEEDS),
        "mixes": list(MIXES),
        "target_snapshots_per_shard": TARGET_SNAPSHOTS_PER_SHARD,
        "max_roots_per_shard": MAX_ROOTS_PER_SHARD,
        "rollouts_per_snapshot": ROLLOUTS_PER_SNAPSHOT,
        "sample_keys": [
            f"future-order-{index:02d}"
            for index in range(1, ROLLOUTS_PER_SNAPSHOT + 1)
        ],
        "selection": "每个seed×mix按root_index升序取前16个V2首选pass且冻结路线父代首选合法chi/peng的机会；不读取任何续打标签；首个机械失效即停止分片",
        "resampling_scope": "只重排当前局wall[wall_front:wall_back]；保持已消费前缀、当前暗手分配、公开状态、牌张多重集、保留区与后续桌种子不变",
        "student_information": "仅DecisionRequest中的PlayerObservation、CompetitionContext、HangmaRules候选事实和具体动作；无来源、对手实现、隐藏牌、未来信息或终局派生特征",
        "teacher_label": "八个预登记未来可摸顺序下，具体鸣牌臂减过牌臂的完整剩余阶段指标均值；同时保留标准差和符号计数",
        "seat_schedule": "seat=(root_index-1)%4",
        "max_snapshots": MAX_SNAPSHOTS,
        "max_tables": MAX_TABLES,
        "max_prefix_roots": MAX_PREFIX_ROOTS,
        "parallel_shards": len(SHARDS),
        "training": False,
        "selection_effect_claim": False,
        "strength_claim": False,
        "confirmation_eligible": False,
        "release_eligible": False,
    }
    batch.write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), manifest)
    print(json.dumps({
        "status": "PREPARED_AV2_1",
        "target_snapshots": MAX_SNAPSHOTS,
        "max_tables": MAX_TABLES,
        "max_prefix_roots": MAX_PREFIX_ROOTS,
    }, ensure_ascii=False))


def verify_inputs(manifest: dict) -> None:
    """核对计划、合同、父代和实现均未漂移。"""

    guard.verify(manifest["runtime"])
    for path_key, sha_key in (
        ("plan", "plan_sha256"),
        ("contract", "contract_sha256"),
        ("route_source", "route_source_sha256"),
    ):
        if digest(Path(manifest[path_key])) != manifest[sha_key]:
            raise ValueError(path_key + " 摘要漂移")


def _root_path(panel_seed: int, mix: str, root_index: int) -> Path:
    """返回来源根检查点路径。"""

    return _project_file(_PROJECT_ROOT, OUT / "roots" / f"s{panel_seed}-{mix}-root{root_index:03d}.json")


def _rollout_path(panel_seed: int, mix: str, root_index: int, rollout: int) -> Path:
    """返回单个未来顺序配对检查点路径。"""

    return _project_file(_PROJECT_ROOT, OUT / "raw" / (
        f"s{panel_seed}-{mix}-root{root_index:03d}-r{rollout:02d}.json"
    ))


def _window(snapshot: dict) -> WindowKey:
    """从冻结快照恢复精确动作窗口键。"""

    cut = snapshot["cut_window"]
    return WindowKey(
        game_id=str(snapshot["match_spec"]["match_id"]),
        round_no=int(cut["round_no"]),
        trigger_seq=int(cut["trigger_seq"]),
        phase=WindowPhase(str(cut["phase"])),
        seat=int(cut["seat"]),
    )


def _capture_source(
    *,
    panel_seed: int,
    mix: str,
    root_index: int,
    contract: dict,
    rules: HangmaRules,
    value_limits: ValueAnalysisLimits,
) -> tuple[dict, dict[str, Any] | None]:
    """只生成首个自然行为分歧快照，不执行单轨迹教师。"""

    focal_seat = (root_index - 1) % 4
    descriptor = core.stage.root_descriptor(
        generator=opportunities.GENERATOR_V2_BEHAVIOR,
        sub_scenario=LABEL,
        opponent_mix=mix,
        panel_seed=panel_seed,
        root_index=root_index,
    )
    source_root_id = str(descriptor["root_id"])
    match_id = f"av2-{panel_seed}-{mix}-r{root_index:03d}-s{focal_seat}"
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
    capture = av1_dataset.AV1RouteChangeCapture(rules.config, value_limits)
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
        capture_condition=capture,
    )
    common = {
        "schema": "r10-av2-averaged-source/1",
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
        witness_entry="av2_averaged_teacher_first_hit",
    )
    witness = dict(attempt.predicate_witness or {})
    if (witness.get("observable_features") or {}).get("schema") != FEATURE_SCHEMA:
        raise ValueError("来源机会缺少冻结 AV1 玩家可见编码")
    return {
        **common,
        "status": "SOURCE_HIT",
        "root_descriptor": descriptor,
        "snapshot": snapshot,
        "witness": witness,
    }, runtime


def _run_rollout(
    *,
    source: dict,
    rollout_index: int,
    sample_key: str,
    contract: dict,
    rules: HangmaRules,
    value_limits: ValueAnalysisLimits,
    runtime: dict[str, Any],
) -> dict:
    """在同一未来可摸顺序下完成过牌与具体鸣牌两臂。"""

    path = _rollout_path(
        int(source["panel_seed"]), str(source["mix"]),
        int(source["root_index"]), rollout_index,
    )
    if path.exists():
        return batch.read(path)
    snapshot = source["snapshot"]
    witness = source["witness"]
    focal_seat = int(source["focal_seat"])
    opponent_names = opportunities.opponent_policy_names(contract, str(source["mix"]))
    baseline_policies, pass_policy = core.policies_for_arm(
        opponent_names=opponent_names,
        focal_seat=focal_seat,
        forced_action_key=str(witness["baseline_action_key"]),
        target_window=_window(snapshot),
        arm_name=f"av2-pass-r{rollout_index:02d}",
    )
    candidate_policies, claim_policy = core.policies_for_arm(
        opponent_names=opponent_names,
        focal_seat=focal_seat,
        forced_action_key=str(witness["claim_action_key"]),
        target_window=_window(snapshot),
        arm_name=f"av2-claim-r{rollout_index:02d}",
    )
    double_arm = opportunities.run_double_arm(
        rules=rules,
        snapshot=snapshot,
        baseline_policies_by_seat=baseline_policies,
        candidate_policies_by_seat=candidate_policies,
        config=opportunities._driver_config(),
        value_limits=value_limits,
        runtime=runtime,
        current_world_transform=lambda world: runtime["engine"].resample_future_drawable_wall(
            world, sample_key=sample_key
        ),
    )
    actual = {
        arm: (((double_arm.get("window_actions") or {}).get("arms") or {}).get(arm) or {}).get("action_key")
        for arm in ("baseline", "candidate")
    }
    reviews = {
        arm: double_arm["arms"][arm].get("execution_review") or {}
        for arm in ("baseline", "candidate")
    }
    mechanical_ok = bool(
        double_arm.get("valid")
        and pass_policy.force_count == 1
        and claim_policy.force_count == 1
        and actual["baseline"] == witness["baseline_action_key"]
        and actual["candidate"] == witness["claim_action_key"]
        and all(
            reviews[arm].get("status") == "complete"
            and reviews[arm].get("zero_internal_failures_verified") is True
            for arm in ("baseline", "candidate")
        )
    )
    baseline = double_arm["arms"]["baseline"]
    candidate = double_arm["arms"]["candidate"]
    row = {
        "schema": "r10-av2-averaged-rollout/1",
        "panel_seed": source["panel_seed"],
        "mix": source["mix"],
        "root_index": source["root_index"],
        "source_root_id": source["source_root_id"],
        "sample_key": sample_key,
        "actual_cut_actions": actual,
        "force_count": {
            "baseline": pass_policy.force_count,
            "candidate": claim_policy.force_count,
        },
        "label": {
            "u_low_delta": float(candidate["u_low"]) - float(baseline["u_low"]),
            "u_high_delta": float(candidate["u_high"]) - float(baseline["u_high"]),
            "focal_stage_score_delta": (
                int(candidate["focal_stage_score"])
                - int(baseline["focal_stage_score"])
            ),
        },
        "mechanical_ok": mechanical_ok,
        "tables_executed": double_arm["tables_executed"],
    }
    batch.write(path, row)
    return row


def _runtime_for_source(source: dict, contract: dict, rules: HangmaRules) -> dict[str, Any]:
    """从冻结来源描述重建无状态模拟运行时。"""

    descriptor = source["root_descriptor"]
    return opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(contract["versions"]["rounds_per_game"]),
        seed=int(descriptor["root_seed"]),
        scenario_id=str(source["source_root_id"]),
    )


def _worker(panel_seed: int, mix: str, manifest: dict, contract: dict) -> dict:
    """顺序处理一个 seed×mix 分片，分片之间并行。"""

    rules = HangmaRules(core.rule_config_from_contract(contract))
    value_limits = ValueAnalysisLimits()
    valid_snapshots = 0
    attempts = 0
    mechanical_failure: dict | None = None
    for root_index in range(1, MAX_ROOTS_PER_SHARD + 1):
        if valid_snapshots >= TARGET_SNAPSHOTS_PER_SHARD or mechanical_failure:
            break
        attempts = root_index
        root_path = _root_path(panel_seed, mix, root_index)
        if root_path.exists():
            source = batch.read(root_path)
            runtime = None
        else:
            source, runtime = _capture_source(
                panel_seed=panel_seed,
                mix=mix,
                root_index=root_index,
                contract=contract,
                rules=rules,
                value_limits=value_limits,
            )
            batch.write(root_path, source)
        if source["status"] == "MISS":
            continue
        if source["status"] != "SOURCE_HIT":
            raise ValueError("未知来源状态：" + str(source["status"]))
        if runtime is None:
            runtime = _runtime_for_source(source, contract, rules)
        rows = [
            _run_rollout(
                source=source,
                rollout_index=index,
                sample_key=sample_key,
                contract=contract,
                rules=rules,
                value_limits=value_limits,
                runtime=runtime,
            )
            for index, sample_key in enumerate(manifest["sample_keys"], start=1)
        ]
        if not all(row["mechanical_ok"] for row in rows):
            mechanical_failure = {
                "panel_seed": panel_seed,
                "mix": mix,
                "root_index": root_index,
                "failed_sample_keys": [
                    row["sample_key"] for row in rows if not row["mechanical_ok"]
                ],
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


def _signs(values: list[float]) -> dict[str, int]:
    """汇总正、零、负数目。"""

    return {
        "positive": sum(value > 0 for value in values),
        "zero": sum(value == 0 for value in values),
        "negative": sum(value < 0 for value in values),
    }


def _compact_row(source: dict, rollouts: list[dict]) -> dict:
    """把八条教师轨迹压缩为一个玩家可见训练样本。"""

    auxiliary = [float(row["label"]["focal_stage_score_delta"]) for row in rollouts]
    primary_low = [float(row["label"]["u_low_delta"]) for row in rollouts]
    primary_high = [float(row["label"]["u_high_delta"]) for row in rollouts]
    witness = source["witness"]
    return {
        "row_id": f"s{source['panel_seed']}:{source['mix']}:{source['source_root_id']}",
        "group": {
            "panel_seed": source["panel_seed"],
            "mix": source["mix"],
            "source_root_id": source["source_root_id"],
            "root_index": source["root_index"],
        },
        "claim_action_key": witness["claim_action_key"],
        "features": witness["observable_features"],
        "labels": {
            "rollouts": len(rollouts),
            "focal_stage_score_delta_mean": statistics.fmean(auxiliary),
            "focal_stage_score_delta_stdev": statistics.stdev(auxiliary),
            "focal_stage_score_delta_signs": _signs(auxiliary),
            "u_low_delta_mean": statistics.fmean(primary_low),
            "u_high_delta_mean": statistics.fmean(primary_high),
            "u_low_delta_signs": _signs(primary_low),
        },
    }


def run() -> None:
    """执行四个训练分片并生成平均教师数据集。"""

    manifest = batch.read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    verify_inputs(manifest)
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("AV2-1 已形成结果；拒绝覆盖")
    contract = batch.read(core.CONTRACT)
    summaries: list[dict] = []
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=len(SHARDS)) as executor:
            futures = [
                executor.submit(_worker, seed, mix, manifest, contract)
                for seed, mix in SHARDS
            ]
            for future in concurrent.futures.as_completed(futures):
                summaries.append(future.result())
    except Exception as exc:
        batch.write(_project_file(_PROJECT_ROOT, OUT / "failure.json"), {
            "schema": "r10-av2-averaged-dataset-failure/1",
            "status": "INTERRUPTED_RESUMABLE",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "completed_shards": sorted(
                summaries, key=lambda item: (item["panel_seed"], item["mix"])
            ),
        })
        raise

    summaries.sort(key=lambda item: (item["panel_seed"], item["mix"]))
    compact_rows: list[dict] = []
    raw_index: list[dict] = []
    for seed, mix in SHARDS:
        shard_hits = 0
        for root_index in range(1, MAX_ROOTS_PER_SHARD + 1):
            path = _root_path(seed, mix, root_index)
            if not path.exists():
                break
            source = batch.read(path)
            raw_index.append({
                "panel_seed": seed,
                "mix": mix,
                "root_index": root_index,
                "source_root_id": source["source_root_id"],
                "status": source["status"],
                "sha256": digest(path),
            })
            if source["status"] != "SOURCE_HIT":
                continue
            rollout_paths = [
                _rollout_path(seed, mix, root_index, index)
                for index in range(1, ROLLOUTS_PER_SNAPSHOT + 1)
            ]
            if not all(item.exists() for item in rollout_paths):
                raise ValueError(f"命中来源缺少八个轨迹：{seed}/{mix}/{root_index}")
            rollouts = [batch.read(item) for item in rollout_paths]
            if not all(row["mechanical_ok"] for row in rollouts):
                continue
            compact_rows.append(_compact_row(source, rollouts))
            shard_hits += 1
            if shard_hits >= TARGET_SNAPSHOTS_PER_SHARD:
                break

    action_types = Counter(
        str(row["claim_action_key"]).split(":", 1)[0] for row in compact_rows
    )
    auxiliary_means = [
        float(row["labels"]["focal_stage_score_delta_mean"])
        for row in compact_rows
    ]
    primary_low_means = [
        float(row["labels"]["u_low_delta_mean"]) for row in compact_rows
    ]
    by_mix = {}
    for mix in MIXES:
        selected = [row for row in compact_rows if row["group"]["mix"] == mix]
        by_mix[mix] = {
            "snapshots": len(selected),
            "auxiliary_mean": statistics.fmean(
                float(row["labels"]["focal_stage_score_delta_mean"])
                for row in selected
            ) if selected else None,
            "primary_low_mean": statistics.fmean(
                float(row["labels"]["u_low_delta_mean"]) for row in selected
            ) if selected else None,
        }
    all_mechanical = all(
        item["mechanical_failure"] is None for item in summaries
    )
    complete = all(item["complete"] for item in summaries)
    coverage = action_types.get("chi", 0) > 0 and action_types.get("peng", 0) > 0
    if not all_mechanical:
        status = "STOP_AV2_1_MECHANICAL_FAILURE"
        next_step = "修复执行接缝并从同一冻结检查点复算；当前标签不得用于建模"
    elif not complete:
        status = "CLOSE_AV2_1_INSUFFICIENT_NATURAL_OPPORTUNITIES"
        next_step = "按文献复盘自然机会定义和成本；不得按标签扩样"
    elif not coverage:
        status = "CLOSE_AV2_1_ACTION_FAMILY_COVERAGE"
        next_step = "关闭本批；重新定义预登记来源以覆盖吃和碰，不按效果补样"
    else:
        status = "PASS_AV2_1_FOR_GROUPED_MODELING"
        next_step = "按完整panel_seed留出训练低容量模型；H/M只作分层读数，不进入学生输入"

    batch.write(_project_file(_PROJECT_ROOT, OUT / "raw-index.json"), {
        "schema": "r10-av2-averaged-raw-index/1",
        "records": raw_index,
    })
    batch.write(_project_file(_PROJECT_ROOT, OUT / "dataset.json"), {
        "schema": "r10-av2-averaged-action-value-rows/1",
        "feature_schema": FEATURE_SCHEMA,
        "rows": compact_rows,
    })
    result = {
        "schema": "r10-av2-averaged-action-value-result/1",
        "status": status,
        "manifest_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "manifest.json")),
        "dataset_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "dataset.json")),
        "shards": summaries,
        "summary": {
            "snapshots": len(compact_rows),
            "paired_rollouts": len(compact_rows) * ROLLOUTS_PER_SNAPSHOT,
            "full_or_partial_tables": len(compact_rows) * ROLLOUTS_PER_SNAPSHOT * 2 * TABLES_PER_ARM,
            "action_types": dict(sorted(action_types.items())),
            "auxiliary_mean_of_snapshot_means": (
                statistics.fmean(auxiliary_means) if auxiliary_means else None
            ),
            "auxiliary_snapshot_mean_signs": _signs(auxiliary_means),
            "primary_low_mean_of_snapshot_means": (
                statistics.fmean(primary_low_means) if primary_low_means else None
            ),
            "primary_low_snapshot_mean_signs": _signs(primary_low_means),
            "median_within_snapshot_auxiliary_stdev": (
                statistics.median(
                    float(row["labels"]["focal_stage_score_delta_stdev"])
                    for row in compact_rows
                ) if compact_rows else None
            ),
            "by_mix": by_mix,
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
