"""R18 P24：立即收 1 番平价胡 / 盲弃胡续打的 R18 v2 开发集未来牌墙教师。

状态池来自 p24_exposure 的结果盲自然暴露：draw 窗口、hu 合法、冻结 R18 v2 首选就是 hu、
立刻胡番数 == 1、且不存在任何合法非财神弃牌使 baotou_after 为真（无爆头靶）。
臂 A（reference）= 立即 hu；臂 B（candidate）= 强制 R18 v2 自评最优的非财神弃牌。

响应窗不能依法重采样已发到三家的暗手，因此固定原自然隐藏手，只让两臂共享同一重排后的
尚未摸取的未来牌墙。每状态 32 面未来墙：前 16 面用于开发选择，后 16 面只做同一根的顺序
敏感性复查。判定严格按 P24-PREREG-DEFERRAL-COMPLEMENT.md §三 的四道门（Δ = B − A）。
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p24-deferral-complement-01-20260925'

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
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import random
import statistics
import sys
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
EV = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution')
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), EV):
    sys.path.insert(0, str(path))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import claim_counterfactual_pilot as core  # noqa: E402
import confirmation_execution_identity as guard  # noqa: E402
import p24_exposure as p24  # noqa: E402
import r18_p9_midgame_hidden_world_teacher as p9  # noqa: E402
import r18_p11_settlement_cascade_teacher as p11  # noqa: E402
import r18_p13_development_seven_pairs_teacher as p13  # noqa: E402
import r18_p86_hu_deferral_development_teacher_v2 as p86  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.actions import action_key  # noqa: E402
from hangma_bot.kernel.serialization import window_key_from_json, window_key_to_json  # noqa: E402
from hangma_bot.offline.evaluate import (  # noqa: E402
    StageSituationProjection, resume_match, seat_policies_from,
)
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p24-deferral-complement-01-20260925/teacher')
DATASET = p24.OUT / "dataset.json"
EXPOSURE_RESULT = p24.OUT / "result.json"
CONTRACT = p24.CONTRACT
PARENT = p24.PARENT
ROLLOUTS_PER_STATE = 32
FIT_ROLLOUTS = 16
BOOTSTRAP_REPLICATES = 20_000
BOOTSTRAP_SEED = 2026092607
MINIMUM_SELECTED_ROOTS = 4
MINIMUM_RECHECK_POSITIVE_FRACTION = 0.75
WORKERS = 4


def write_json(path: Path, value: Any) -> None:
    """写入稳定、可复算的 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + chr(10),
                    encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def targets() -> list[dict[str, Any]]:
    """把结果盲暴露数据集转换为精确重放目标，不打开任何收益标签。"""

    exposure = json.loads(EXPOSURE_RESULT.read_text(encoding="utf-8"))
    if exposure.get("status") != "OPEN_DEVELOPMENT_TEACHER":
        raise ValueError("P24 暴露未开放开发教师")
    if exposure.get("selected_states") != 16:
        raise ValueError("P24 必须冻结 16 个开发状态")
    document = json.loads(DATASET.read_text(encoding="utf-8"))
    if document.get("outcome_blind") is not True:
        raise ValueError("P24 暴露数据集不再结果盲")
    rows = list(document["rows"])
    result = []
    for index, row in enumerate(rows, 1):
        request = row["request"]
        observation = request["observation"]
        table_id = str(observation["game_id"]).removeprefix("sitin-stage:")
        if row["reference_action"] != "hu":
            raise ValueError("P24 参考臂动作身份漂移")
        if not str(row["intervention_action"]).startswith("discard:"):
            raise ValueError("P24 干预臂动作身份漂移")
        hu_candidates = [candidate for candidate in request["rules"]["legal_candidates"]
                         if candidate["action_key"] == "hu"]
        if len(hu_candidates) != 1:
            raise ValueError("P24 立即胡合法候选不唯一")
        immediate = hu_candidates[0]["value_facts"]["immediate_settlement"]
        if not isinstance(immediate, dict) or len(immediate["score_delta"]) != 4:
            raise ValueError("P24 立即胡结算缺失")
        if int(immediate["fan"]) != 1:
            raise ValueError("P24 目标不是 1 番平价胡")
        result.append({
            "target_id": "r18-p24-development-{0:02d}".format(index),
            "split": "development",
            "source": {
                "panel_seed": p24.PANEL_SEED,
                "source_id": row["source"]["source_id"],
                "source_root_id": row["source"]["source_root_id"],
                "mix": row["source"]["mix"],
                "root_index": row["source"]["root_index"],
                "focal_seat": row["source"]["focal_seat"],
                "table_no": int(table_id.rsplit("-t", 1)[1]),
                "table_id": table_id,
            },
            "window_key": request["window_key"],
            "competition": request["competition"],
            "focal_physical_seat": int(observation["seat"]),
            "request_sha256": row["request_sha256"],
            "state_projection_sha256": row["state_projection_sha256"],
            "reference_action": row["reference_action"],
            "intervention_action": row["intervention_action"],
            "expected_hu_settlement": immediate,
            "features": dict(row["features"]),
        })
    if len(result) != 16:
        raise ValueError("P24 必须恰有 16 个开发状态")
    roots = [row["source"]["source_root_id"] for row in result]
    if len(roots) != len(set(roots)):
        raise ValueError("P24 开发来源根必须独立")
    mixes = Counter(row["source"]["mix"] for row in result)
    if mixes != Counter({"H": 8, "M": 8}):
        raise ValueError("P24 开发根必须 H/M 各 8：" + str(dict(mixes)))
    return result


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-future-{1:02d}.json".format(target["target_id"], index))


def source_paths() -> list[Path]:
    """列出会改变选择、重放或标签语义的实现。"""

    import hangma_bot.offline.forced_action as forced_action
    import hangma_bot.offline.evaluate as evaluate
    import hangma_bot.simulation.engine as simulation_engine
    import hangma_bot.simulation.shuffle as simulation_shuffle

    return [
        Path(__file__), Path(p24.__file__), DATASET, EXPOSURE_RESULT, CONTRACT, PARENT,
        Path(p9.__file__), Path(p11.__file__), Path(p13.__file__),
        Path(p86.__file__), Path(natural.__file__), Path(opportunities.__file__),
        Path(core.__file__), Path(evaluate.__file__), Path(forced_action.__file__),
        Path(simulation_engine.__file__), Path(simulation_shuffle.__file__),
        p24.OUT / "manifest.json", p24.OUT / "run-summary.json",
    ]


def prepare() -> None:
    """冻结开发目标、未来墙样本、判据和最大执行预算。"""

    if OUT.exists():
        raise SystemExit("P24 教师目录已存在；拒绝覆盖")
    frozen = targets()
    sample_keys = [
        "r18-p24-deferral-complement-future-wall-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(frozen) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.parent.name,
        authorization_id="r18-p24-deferral-complement-development-teacher-01",
        accounts={"prefix_generation": len(frozen), "tables_full": planned_tables},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P24 暴露在 192 张新自然桌上冻结 16 个结果盲开发状态",
        "scope": "16 状态 × 32 共同未来墙 ×（立即 1 番胡 / 盲弃胡）双臂；仅续打当前完整桌",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p24-deferral-complement-targets/1",
        "targets": frozen,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p24-deferral-complement-teacher-manifest/1",
        "created_at_utc": search.utc_now(),
        "worktree_absolute_path_binding": str(ROOT.resolve()),
        "runtime": guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "dataset_sha256": digest(DATASET),
        "exposure_result_sha256": digest(EXPOSURE_RESULT),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "parent_sha256": digest(PARENT),
        "parent_score_source_sha256": hashlib.sha256(
            p24.parent_source().encode("utf-8")).hexdigest(),
        "contract_sha256": digest(CONTRACT),
        "development_states": len(frozen),
        "rollouts_per_state": ROLLOUTS_PER_STATE,
        "future_wall_fit_indices": list(range(1, FIT_ROLLOUTS + 1)),
        "future_wall_recheck_indices": list(range(FIT_ROLLOUTS + 1, ROLLOUTS_PER_STATE + 1)),
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "execution_mode": "process_pool_workers_{0}".format(WORKERS),
        "sampling_unit": "自然基础状态；32 面共同未来牌墙不增加独立样本数",
        "sampling_scope": (
            "固定原自然三家暗手，只共同重排尚未摸取的未来牌墙；"
            "不宣称覆盖公开状态一致的全部隐藏手分布"
        ),
        "primary_label": "blind_deferral_minus_immediate_fan1_hu_current_table_score",
        "selection_rule": (
            "每状态只用前 16 面未来墙；Δround 与 Δtable（B−A）均值同时严格 > 0 才标记该根"
            "「盲弃胡有利」，否则保持 R18 v2 立即胡；后 16 面只复查同一根的方向"
        ),
        "gate": {
            "mechanical_precise_prefix_and_first_divergence_is_target": True,
            "minimum_fit_selected_roots": MINIMUM_SELECTED_ROOTS,
            "selected_roots_must_cover_mixes": ["H", "M"],
            "minimum_fit_negative_counterexample_roots": 1,
            "minimum_recheck_positive_selected_fraction": MINIMUM_RECHECK_POSITIVE_FRACTION,
            "recheck_all_root_current_table_mean_strictly_greater_than": 0.0,
            "recheck_oracle_policy_current_table_bootstrap_95_lower_strictly_greater_than": 0.0,
            "minimum_leave_one_source_root_out_current_table_mean_strictly_greater_than": 0.0,
            "recheck_current_table_mean_per_mix_strictly_greater_than": 0.0,
        },
        "teacher_endpoint": "target_round_and_current_full_table_only",
        "model_calls": 0, "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "development_states": len(frozen),
                      "planned_tables": planned_tables}, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对暴露输入、目标、父代、合同和运行实现均未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest.get("worktree_absolute_path_binding") != str(ROOT.resolve()):
        raise ValueError("P24 冻结批次绑定原 worktree；跨路径运行须另起批次")
    checks = {
        "P24暴露数据": (manifest["dataset_sha256"], digest(DATASET)),
        "P24暴露结果": (manifest["exposure_result_sha256"], digest(EXPOSURE_RESULT)),
        "P24目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "R18 v2父代": (manifest["parent_sha256"], digest(PARENT)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    if manifest["parent_score_source_sha256"] != hashlib.sha256(
            p24.parent_source().encode("utf-8")).hexdigest():
        raise ValueError("R18 v2 评分源码身份漂移")
    guard.verify(manifest["runtime"])
    frozen = list(json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["targets"])
    if frozen != targets():
        raise ValueError("P24 目标不能由暴露数据集结果盲重建")
    return manifest, frozen


def run_exact_prefix(
    *, runtime: Mapping[str, Any], rules: HangmaRules, target: Mapping[str, Any],
    policies_by_seat: list[Any], tournament_config: Any, plan: Any,
    situation: StageSituationProjection,
) -> Any:
    """以原自然阶段上下文重放 R18 v2，精确截取目标动作之前的世界。"""

    engine = runtime["engine"]
    chooser = runtime["choice_factory"]
    spec = runtime["spec_factory"](
        match_id=str(plan.match_id), scenario_id=str(plan.scenario_id),
        config=tournament_config, seed=int(plan.seed),
        initial_dealer=int(plan.initial_dealer), initial_scores=[0, 0, 0, 0],
    )
    world = engine.start(spec)
    prefix = []
    config = replace(opportunities._driver_config(),
                     competition_tournament_id=str(plan.scenario_id))
    execution = {seat: {
        "seat": seat, "policy_id": str(getattr(policy, "policy_id", "") or ""),
        "policy_class": type(policy).__name__, "windows": 0,
    } for seat, policy in enumerate(policies_by_seat)}
    target_key = window_key_from_json(target["window_key"])
    for _ in range(100_000):
        frame = engine.frame(world)
        if frame.final_scores is not None or frame.blocked_reason is not None:
            break
        for decision in frame.decisions:
            if decision.window_key != target_key:
                continue
            analysis = rules.analyze(decision.observation, value_limits=p24.LIMITS)
            request = opportunities.real_window_request(
                decision=decision, analysis=analysis, match_id=str(plan.match_id),
                config=config, now_monotonic=lambda: 800.0,
                stage_situation=situation,
            )
            request_json = decision_request_to_json(request)
            if value_digest(p13.state_projection(request_json)) != target["state_projection_sha256"]:
                raise ValueError("P24 截取窗口玩家观察/规则状态与暴露冻结请求不同")
            if request_json["competition"] != target["competition"]:
                raise ValueError("P24 截取窗口阶段上下文与暴露冻结请求不同")
            focal = int(target["focal_physical_seat"])
            plan_at_cut = asyncio.run(policies_by_seat[focal].choose(
                request, config.budget_policy.build(800.0, decision.timeout_seconds),
            ))
            actual_top = (None if not plan_at_cut.candidates else
                          action_key(plan_at_cut.candidates[0].action))
            if actual_top != target["reference_action"]:
                raise ValueError("P24 截取窗口 R18 v2 首选动作与暴露不同")
            legal = {item.action_key: item for item in analysis.legal_candidates}
            if {target["reference_action"], target["intervention_action"]} - set(legal):
                raise ValueError("P24 冻结双臂动作不再合法")
            immediate = next(item.value_facts.immediate_settlement
                             for item in analysis.legal_candidates
                             if item.action_key == "hu")
            actual_hu = {
                "fan": immediate.fan,
                "score_delta": list(immediate.score_delta),
                "details": list(immediate.details),
            }
            if actual_hu != target["expected_hu_settlement"]:
                raise ValueError("P24 规则即时胡结算与暴露冻结请求不同")
            intervention_item = legal[target["intervention_action"]]
            intervention_facts = intervention_item.facts
            if intervention_facts is None or intervention_facts.baotou_after is True:
                raise ValueError("P24 干预动作在规则上仍是爆头靶，拒绝按「盲弃胡」使用")
            return opportunities.AttemptOutcome(
                status="hit", attempt_index=int(str(target["target_id"]).split("-")[-1]),
                source_root_id=str(plan.scenario_id), spec_seed=int(plan.seed),
                prefix=tuple(prefix), cut_frame=frame, cut_decision=decision,
                predicate_values={}, predicate_witness={
                    "target_id": target["target_id"],
                    "state_projection_sha256": target["state_projection_sha256"],
                    "reference_action": target["reference_action"],
                    "intervention_action": target["intervention_action"],
                    "hu_settlement": actual_hu,
                    "r18_v2_actual_top_action": actual_top,
                    "intervention_baotou_after": intervention_facts.baotou_after,
                    "intervention_shanten_after": intervention_facts.shanten_after,
                }, projected_facts=None,
                prefix_execution={
                    "schema": "r18-p24-r18-v2-stage-aware-prefix-execution/1",
                    "focal_policy": "frozen R18 v2 action-value policy",
                    "by_seat": list(execution.values()),
                },
            )
        choices = []
        for decision in frame.decisions:
            analysis = rules.analyze(decision.observation, value_limits=p24.LIMITS)
            request = opportunities.real_window_request(
                decision=decision, analysis=analysis, match_id=str(plan.match_id),
                config=config, now_monotonic=lambda: 800.0,
                stage_situation=situation,
            )
            seat = int(decision.window_key.seat)
            execution[seat]["windows"] += 1
            decision_plan = asyncio.run(policies_by_seat[seat].choose(
                request, config.budget_policy.build(800.0, decision.timeout_seconds),
            ))
            if not decision_plan.candidates:
                raise ValueError("P24 前缀策略未返回动作")
            action = decision_plan.candidates[0].action
            key = action_key(action)
            if key not in {item.action_key for item in analysis.legal_candidates}:
                raise ValueError("P24 前缀策略返回非法动作：" + key)
            choices.append(chooser(decision.window_key, action))
        world = engine.advance(world, frame.revision, tuple(choices))
        prefix.extend({
            "window_key": window_key_to_json(choice.window_key),
            "action_key": action_key(choice.action),
        } for choice in choices)
    raise ValueError("P24 R18 v2 合法前缀未命中冻结窗口")


def capture_one(target: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    """捕获一个开发窗口，保存已审计的赛事阶段上下文与合法前缀。"""

    source = target["source"]
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=str(source["mix"]),
        root_index=int(source["root_index"]), focal_seat=int(source["focal_seat"]),
        panel_seed=int(source["panel_seed"]),
    )
    plan = plans[int(source["table_no"]) - 1]
    if (plan.table_id != source["table_id"]
            or plan.match_id != target["window_key"]["game_id"]):
        raise ValueError("P24 自然桌计划与冻结窗口身份漂移")
    rules = HangmaRules(core.rule_config_from_contract(contract))
    rounds_per_game = int(contract["versions"]["rounds_per_game"])
    situation = p86.stage_projection(target, plan, rounds_per_game)
    opponent_names = opportunities.opponent_policy_names(contract, str(source["mix"]))
    logical = natural.arm_logical_policies(
        arm="candidate",
        candidate_scorer=ActionValueScorer(
            "r18-p24-capture-r18-v2", p24.parent_source(),
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
        raise ValueError("P24 焦点物理座位与换座计划不符")
    verifier_names = [
        physical_names[seat] for seat in range(4) if seat != focal_physical
    ]
    runtime = opportunities.build_real_runtime(
        rules_config=rules.config, rounds_per_game=rounds_per_game,
        seed=int(plan.seed), scenario_id=str(plan.scenario_id),
    )
    tournament_config = opportunities._snapshot_tournament_config(
        {"rounds_per_game": rounds_per_game}, rules,
    )
    attempt = run_exact_prefix(
        runtime=runtime, rules=rules, target=target, policies_by_seat=policies,
        tournament_config=tournament_config, plan=plan, situation=situation,
    )
    prior_scores = p86.completed_table_scores_for_snapshot(target, plan)
    runtime_kind = opportunities.runtime_kind_of(runtime)
    snapshot = dict(opportunities.build_snapshot(
        prefix_source="v2_behavior", attempt=attempt,
        predicate_id="r18_p24_r18_v2_flat_fan1_hu_window", focal_seat=focal_physical,
        opponent_scenario=str(source["mix"]), match_id=str(plan.match_id),
        stage_ledger={"completed_table_scores": prior_scores},
        remaining_schedule={
            "declared_endpoint": "current_table_complete",
            "remaining_tables_after_current": int(plan.tables_in_stage) - int(source["table_no"]),
            "rounds_per_game": rounds_per_game,
            "tables_in_stage": int(plan.tables_in_stage),
        },
        panel_seed=int(source["panel_seed"]), tables_in_stage=int(plan.tables_in_stage),
        rounds_per_game=rounds_per_game,
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
        witness_entry="r18_p24_r18_v2_natural_exact_window",
    ))
    snapshot["seating"]["participant_ids_by_seat"] = list(plan.seats())
    snapshot["stage_plan"]["participant_ids_by_seat"] = list(plan.seats())
    snapshot["stage_plan"]["table_index"] = int(source["table_no"])
    snapshot["stage_plan"]["permutation"] = list(plan.permutation)
    snapshot["current_stage_situation"] = situation.to_json()
    if (snapshot["stage_ledger"]["completed_table_scores"] != prior_scores
            or snapshot["stage_plan"]["participant_ids_by_seat"] != list(plan.seats())):
        raise ValueError("P24 已完成桌积分座位映射漂移")
    snapshot["capture"] = {
        "target": dict(target), "table_seed": int(plan.seed),
        "table_scenario_id": str(plan.scenario_id),
        "physical_policy_names": physical_names,
        "opponent_names_in_physical_order": verifier_names,
        "prefix_steps": len(attempt.prefix),
        "focal_prefix_policy": "frozen R18 v2 action-value policy",
        "witness": dict(attempt.predicate_witness or {}),
    }
    engine, world = opportunities.rebuild_world(
        rules=rules, snapshot=snapshot, value_limits=p24.LIMITS, runtime=runtime,
    )
    if (opportunities.frame_observation_summary(engine.frame(world))
            != snapshot["observation_summary"]):
        raise ValueError("P24 快照公开重建后的观察摘要不一致")
    return snapshot


def capture() -> None:
    """只捕获 16 个开发状态的精确合法前缀。"""

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
        step_id="r18:p24-deferral-complement:capture", account="prefix_generation",
        amount=len(pending), note="16 个开发状态的 R18 v2 精确合法前缀捕获",
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    completed = 0
    failures = []
    try:
        for target in pending:
            try:
                snapshot = capture_one(target, contract)
                snapshot["capture"]["consumer"] = "R18 P24 fan1 flat hu deferral teacher"
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
        "schema": "r18-p24-deferral-complement-capture-summary/1",
        "captured": sum(snapshot_path(row).exists() for row in development),
        "planned": manifest["development_states"],
        "failures": failures,
        "unexpected_snapshot_files": sorted(
            path.name for path in (_project_file(_PROJECT_ROOT, OUT / "snapshots")).glob("*.json")
            if path.name not in {snapshot_path(row).name for row in development}
        ),
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in development):
        raise RuntimeError("P24 开发状态捕获不完整")


class FocalRecorderPolicy:
    """只记录焦点座位每个窗口的规则事实；返回计划原样透传，不改变行为。"""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.records: list[dict[str, Any]] = []
        self.policy_id = getattr(inner, "policy_id", type(inner).__name__)
        self.max_operations = getattr(inner, "max_operations", None)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def choose(self, request: Any, budget: Any) -> Any:
        plan = await self._inner.choose(request, budget)
        try:
            observation = request.observation
            chosen = None if not plan.candidates else plan.candidates[0].action_key
            item = next((candidate for candidate in request.rules.legal_candidates
                         if candidate.action_key == chosen), None)
            facts = None if item is None else item.facts
            useful = () if facts is None else (facts.useful_tiles or ())
            self.records.append({
                "trigger_seq": int(request.window_key.trigger_seq),
                "round_no": int(observation.round_no),
                "phase": str(observation.phase),
                "chosen": chosen,
                "chosen_shanten_after": (None if facts is None else facts.shanten_after),
                "chosen_useful_kinds": len(useful),
                "chosen_baotou_after": (None if facts is None else facts.baotou_after),
                "concealed": sorted(tile.code for tile in observation.my_hand),
                "meld_count": len(observation.melds[observation.seat]),
            })
        except Exception:  # noqa: BLE001 记录失败不得影响执行
            pass
        return plan


def policies_for_arm(
    *, target: Mapping[str, Any], snapshot: Mapping[str, Any],
    forced_action_key: str, label: str,
) -> tuple[list[Any], ForceFirstActionPolicy, FocalRecorderPolicy]:
    """仅目标窗强制动作一次，之后焦点恢复冻结 R18 v2、对手保持合同策略。"""

    focal = int(target["focal_physical_seat"])
    policies = list(opportunities.frozen_generation_policies(
        opponent_names=snapshot["capture"]["opponent_names_in_physical_order"],
        focal_seat=focal, monotonic=lambda: 800.0,
    ))
    delegate = ActionValuePolicy(ActionValueScorer(
        "r18-p24-r18-v2-continuation-" + label, p24.parent_source(),
    ))
    forced = ForceFirstActionPolicy(
        delegate, target_window=window_key_from_json(target["window_key"]),
        forced_action_key=forced_action_key, policy_id="r18-p24-" + label,
    )
    recorder = FocalRecorderPolicy(forced)
    policies[focal] = recorder
    return policies, forced, recorder


def decision_sequence(outcome: Any) -> list[tuple[Any, Any, Any, Any]]:
    return [(window_key_from_json(record.window_key), record.action_key,
             record.legal, record.fallback_reason) for record in outcome.decisions]


def divergence_report(
    *, sequence_reference: list[Any], sequence_intervention: list[Any],
    target_key: Any, reference_action: str, intervention_action: str,
) -> dict[str, Any]:
    """逐例核对：两臂首个分叉点索引必须恰好是目标窗口。"""

    target_index = next((index for index, item in enumerate(sequence_reference)
                         if item[0] == target_key), None)
    target_index_intervention = next(
        (index for index, item in enumerate(sequence_intervention) if item[0] == target_key), None)
    first = None
    for index in range(min(len(sequence_reference), len(sequence_intervention))):
        if sequence_reference[index] != sequence_intervention[index]:
            first = index
            break
    if first is None and len(sequence_reference) != len(sequence_intervention):
        first = min(len(sequence_reference), len(sequence_intervention))
    prefix_payload = [list(map(str, item)) for item in sequence_reference[:target_index or 0]]
    diverge_pair = None
    if first is not None and first < len(sequence_reference) and first < len(sequence_intervention):
        diverge_pair = [str(sequence_reference[first][1]), str(sequence_intervention[first][1])]
    return {
        "target_index_reference": target_index,
        "target_index_intervention": target_index_intervention,
        "first_divergence_index": first,
        "first_divergence_actions": diverge_pair,
        "decisions_reference": len(sequence_reference),
        "decisions_intervention": len(sequence_intervention),
        "prefix_decision_digest": value_digest(prefix_payload),
        "prefix_decisions": len(prefix_payload),
        "divergence_is_target_window": bool(
            first is not None and first == target_index
            and first == target_index_intervention
            and diverge_pair == [reference_action, intervention_action]
        ),
        "prefix_identical": bool(
            target_index is not None and all(
                sequence_reference[index] == sequence_intervention[index]
                for index in range(target_index)
            )
        ),
    }


def focal_widths(records: list[dict[str, Any]], target: Mapping[str, Any],
                 limit: int = 3) -> list[dict[str, Any]]:
    """目标窗之后、同一局内的焦点摸牌窗听口宽度（分层描述，不参与判定）。"""

    key = target["window_key"]
    out = []
    for item in records:
        if item["round_no"] != int(key["round_no"]):
            continue
        if item["trigger_seq"] <= int(key["trigger_seq"]):
            continue
        if item["phase"] != "draw":
            continue
        out.append({
            "trigger_seq": item["trigger_seq"],
            "chosen": item["chosen"],
            "chosen_shanten_after": item["chosen_shanten_after"],
            "chosen_useful_kinds": item["chosen_useful_kinds"],
            "chosen_baotou_after": item["chosen_baotou_after"],
            "meld_count": item["meld_count"],
        })
        if len(out) >= limit:
            break
    return out


def execute_rollout(
    target: Mapping[str, Any], index: int, sample_key: str,
) -> dict[str, Any]:
    """固定原隐藏手与阶段上下文，只比较目标局及当前完整桌。"""

    snapshot = json.loads(snapshot_path(target).read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    rules = HangmaRules(core.rule_config_from_contract(contract))
    source = target["source"]
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=str(source["mix"]),
        root_index=int(source["root_index"]), focal_seat=int(source["focal_seat"]),
        panel_seed=int(source["panel_seed"]),
    )
    plan = plans[int(source["table_no"]) - 1]
    situation = p86.stage_projection(target, plan, int(snapshot["match_spec"]["rounds_per_game"]))
    if snapshot["current_stage_situation"] != situation.to_json():
        raise ValueError("P24 当前桌阶段上下文快照漂移")
    base_runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
        seed=int(snapshot["match_spec"]["seed"]),
        scenario_id=str(snapshot["match_spec"]["scenario_id"]),
    )
    settlement = p11.SettlementCaptureEngine(base_runtime["engine"])
    runtime = dict(base_runtime)
    runtime["engine"] = settlement
    reference_policies, reference_force, reference_recorder = policies_for_arm(
        target=target, snapshot=snapshot,
        forced_action_key=str(target["reference_action"]),
        label="reference-{0}-{1:02d}".format(target["target_id"], index),
    )
    intervention_policies, intervention_force, intervention_recorder = policies_for_arm(
        target=target, snapshot=snapshot,
        forced_action_key=str(target["intervention_action"]),
        label="intervention-{0}-{1:02d}".format(target["target_id"], index),
    )
    config = replace(opportunities._driver_config(),
                     competition_tournament_id=str(plan.scenario_id))
    cut_round = int(target["features"]["round_no"])
    focal = int(target["focal_physical_seat"])
    arms = {}
    sequences = {}
    for arm_name, policies, force, recorder in (
        ("baseline", reference_policies, reference_force, reference_recorder),
        ("candidate", intervention_policies, intervention_force, intervention_recorder),
    ):
        engine, world = opportunities.rebuild_world(
            rules=rules, snapshot=snapshot, value_limits=p24.LIMITS, runtime=runtime,
        )
        transformed = replace(
            settlement.resample_future_drawable_wall(world, sample_key=sample_key),
            history_consistent=False,
        )
        before = len(settlement.records)
        outcome = asyncio.run(resume_match(
            engine=engine, world=transformed, policies_by_seat=tuple(policies),
            rules=rules, choice_factory=runtime["choice_factory"], config=config,
            now_monotonic=lambda: 800.0, wall_clock=None,
            remaining_schedule=snapshot["remaining_schedule"],
            stage_snapshot={
                "observation_summary": snapshot["observation_summary"],
                "match_spec": snapshot["match_spec"],
            },
            value_limits=p24.LIMITS, stage_situation=situation,
        ))
        if (outcome.status != "complete" or outcome.final_scores is None
                or outcome.completed_hands != int(snapshot["match_spec"]["rounds_per_game"])):
            raise RuntimeError("P24 当前桌续打未完整：" + str(outcome.status))
        all_records = settlement.records[before:]
        records = [record for record in all_records if record.round_no == cut_round]
        if len(records) != 1:
            raise RuntimeError("P24 目标局结算记录不是唯一")
        cut_records = [record for record in outcome.decisions
                       if window_key_from_json(record.window_key)
                       == window_key_from_json(target["window_key"])]
        if len(cut_records) != 1:
            raise RuntimeError("P24 截取窗口执行记录不是唯一")
        cut = cut_records[0]
        arms[arm_name] = {
            "round_record": records[0],
            "score": int(outcome.final_scores[focal]),
            "action": cut.action_key,
            "cut_legal": cut.legal,
            "cut_fallback": cut.fallback_reason,
            "force_count": force.force_count,
            "decisions": len(outcome.decisions),
            "next_round_dealer": next(
                (int(record.dealer_seat) for record in all_records
                 if int(record.round_no) == cut_round + 1), None,
            ),
            "focal_widths": focal_widths(recorder.records, target),
        }
        sequences[arm_name] = decision_sequence(outcome)

    reference_record = arms["baseline"]["round_record"]
    intervention_record = arms["candidate"]["round_record"]
    reference_score = arms["baseline"]["score"]
    intervention_score = arms["candidate"]["score"]
    actions = {name: arms[name]["action"] for name in ("baseline", "candidate")}
    divergence = divergence_report(
        sequence_reference=sequences["baseline"],
        sequence_intervention=sequences["candidate"],
        target_key=window_key_from_json(target["window_key"]),
        reference_action=str(target["reference_action"]),
        intervention_action=str(target["intervention_action"]),
    )
    mechanical = bool(
        reference_force.force_count == 1 and intervention_force.force_count == 1
        and actions["baseline"] == target["reference_action"]
        and actions["candidate"] == target["intervention_action"]
        and all(arms[name]["cut_legal"] is True and arms[name]["cut_fallback"] is None
                for name in ("baseline", "candidate"))
        and reference_record.winner_seat is not None
        and int(reference_record.winner_seat) == focal
        and not reference_record.is_draw
        and list(reference_record.score_delta)
            == list(target["expected_hu_settlement"]["score_delta"])
        and int(reference_record.fan) == int(target["expected_hu_settlement"]["fan"])
        and divergence["divergence_is_target_window"] is True
        and divergence["prefix_identical"] is True
    )
    reference = p11.record_json(reference_record)
    intervention = p11.record_json(intervention_record)
    reference["terminal"] = p13.terminal(reference_record, focal)
    intervention["terminal"] = p13.terminal(intervention_record, focal)
    reference["focal_settlement"] = int(reference_record.score_delta[focal])
    intervention["focal_settlement"] = int(intervention_record.score_delta[focal])
    reference["next_round_dealer"] = arms["baseline"]["next_round_dealer"]
    intervention["next_round_dealer"] = arms["candidate"]["next_round_dealer"]
    return {
        "schema": "r18-p24-deferral-complement-rollout/1",
        "target_id": target["target_id"],
        "rollout_index": index, "sample_key": sample_key,
        "reference_action": target["reference_action"],
        "intervention_action": target["intervention_action"],
        "actual_actions": actions,
        "force_count": {
            "reference": reference_force.force_count,
            "intervention": intervention_force.force_count,
        },
        "divergence": divergence,
        "reference": reference, "intervention": intervention,
        "focal_current_round_settlement_delta": (
            intervention["focal_settlement"] - reference["focal_settlement"]
        ),
        "focal_current_table_score": {
            "reference": reference_score, "intervention": intervention_score,
            "delta": int(intervention_score) - int(reference_score),
        },
        "focal_widths": {name: arms[name]["focal_widths"] for name in ("baseline", "candidate")},
        "tables_executed": {"baseline": 1, "candidate": 1},
        "decisions_after_cut": {name: arms[name]["decisions"] for name in ("baseline", "candidate")},
        "runtime_kind": opportunities.runtime_kind_of(runtime),
        "execution_kind": opportunities.execution_kind_for(
            prefix_source="v2_behavior", runtime=runtime,
        ),
        "sampling_scope": "source hidden hands fixed; common future drawable wall only",
        "mechanical_ok": mechanical,
    }


def validate_rollout_row(
    row: Mapping[str, Any], target: Mapping[str, Any], index: int, sample_key: str,
) -> None:
    """断点恢复和分析都逐字段核对冻结配对身份及内部算术。"""

    expected = {
        "schema": "r18-p24-deferral-complement-rollout/1",
        "target_id": target["target_id"],
        "rollout_index": index,
        "sample_key": sample_key,
        "reference_action": target["reference_action"],
        "intervention_action": target["intervention_action"],
        "actual_actions": {
            "baseline": target["reference_action"],
            "candidate": target["intervention_action"],
        },
        "force_count": {"reference": 1, "intervention": 1},
        "tables_executed": {"baseline": 1, "candidate": 1},
        "mechanical_ok": True,
    }
    for name, value in expected.items():
        if row.get(name) != value:
            raise ValueError("P24 配对身份或机械字段漂移：" + name)
    divergence = row.get("divergence") or {}
    if divergence.get("divergence_is_target_window") is not True:
        raise ValueError("P24 首个分叉点不等于目标窗口")
    if divergence.get("prefix_identical") is not True:
        raise ValueError("P24 目标窗口之前两臂决策序列不一致")
    if divergence.get("first_divergence_actions") != [target["reference_action"],
                                                     target["intervention_action"]]:
        raise ValueError("P24 分叉动作对不等于冻结双臂动作")
    reference = row.get("reference") or {}
    intervention = row.get("intervention") or {}
    if (reference.get("round_no") != target["features"]["round_no"]
            or intervention.get("round_no") != target["features"]["round_no"]):
        raise ValueError("P24 配对目标局号漂移")
    expected_hu = target["expected_hu_settlement"]
    if (reference.get("winner_seat") != target["focal_physical_seat"]
            or reference.get("terminal") != "focal_hu"
            or reference.get("fan") != expected_hu["fan"]
            or reference.get("score_delta") != expected_hu["score_delta"]):
        raise ValueError("P24 立即胡臂未执行冻结规则结算")
    focal = int(target["focal_physical_seat"])
    if (reference.get("focal_settlement") != reference["score_delta"][focal]
            or intervention.get("focal_settlement") != intervention["score_delta"][focal]
            or row.get("focal_current_round_settlement_delta")
            != intervention["focal_settlement"] - reference["focal_settlement"]):
        raise ValueError("P24 目标局本人积分差不自洽")
    table = row.get("focal_current_table_score") or {}
    if table.get("delta") != table["intervention"] - table["reference"]:
        raise ValueError("P24 当前完整桌积分差不自洽")


def run() -> None:
    """顺序提交 16×32 个双臂当前完整桌配对，四进程并行，逐未来墙结算费用。"""

    import concurrent.futures

    manifest, frozen = verify()
    development = [row for row in frozen if row["split"] == "development"]
    capture_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    if (capture_summary["failures"]
            or capture_summary["captured"] != manifest["development_states"]
            or capture_summary["unexpected_snapshot_files"]):
        raise ValueError("P24 开发前缀未完整捕获")
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    completed_tables = 0
    pending = []
    for target in development:
        for index, key in enumerate(manifest["sample_keys"], 1):
            path = rollout_path(target, index)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                validate_rollout_row(row, target, index, key)
                completed_tables += 2
                continue
            pending.append((target, index, key))
    print(json.dumps({"resumed_tables": completed_tables,
                      "pending_rollouts": len(pending)}, ensure_ascii=False), flush=True)
    failures = []
    rows_written = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = {}
        for target, index, key in pending:
            reservation = ledger.reserve(
                step_id="r18:p24:development:" + target["target_id"] + ":{0:02d}".format(index),
                account="tables_full", amount=2,
                note="同一未来墙的立即 1 番胡／盲弃胡双臂完整桌；开发集",
            )
            future = pool.submit(execute_rollout, target, index, key)
            futures[future] = (target, index, key, reservation)
        for future in concurrent.futures.as_completed(futures):
            target, index, key, reservation = futures[future]
            try:
                row = future.result()
                validate_rollout_row(row, target, index, key)
                write_json(rollout_path(target, index), row)
                ledger.settle(reservation, actual=2, note="双臂完整且机械核对通过")
                completed_tables += 2
                rows_written += 1
            except BaseException as exc:  # noqa: BLE001
                ledger.settle(reservation, usage_unknown=True,
                              note="双臂异常；保守结算两桌")
                failures.append({"target_id": target["target_id"], "rollout_index": index,
                                 "error": type(exc).__name__ + ": " + str(exc)})
            if rows_written % 32 == 0:
                print(json.dumps({"completed_tables": completed_tables,
                                  "planned_tables": manifest["planned_tables"],
                                  "failures": len(failures)},
                                 ensure_ascii=False), flush=True)
    files = list((_project_file(_PROJECT_ROOT, OUT / "rollouts")).glob("*.json"))
    expected_files = {rollout_path(target, index).name for target in development
                      for index in range(1, ROLLOUTS_PER_STATE + 1)}
    if {path.name for path in files} - expected_files:
        raise ValueError("P24 配对目录出现非开发或非预注册未来墙文件")
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p24-deferral-complement-run-summary/1",
        "rollout_files": len(files), "actual_tables": len(files) * 2,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures:
        raise RuntimeError("P24 存在失败配对：" + json.dumps(failures[:3], ensure_ascii=False))
    if len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P24 开发教师执行不完整")


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    """对自然基础状态等权均值做确定性 bootstrap 95% 区间。"""

    rng = random.Random(BOOTSTRAP_SEED)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return (means[int(0.025 * len(means))], means[int(0.975 * len(means)) - 1])


def _rate(values: list[bool]) -> float | None:
    return None if not values else sum(1 for value in values if value) / len(values)


def _mean(values: list[float]) -> float | None:
    return None if not values else statistics.fmean(values)


def arm_metrics(rows: list[dict[str, Any]], focal: int, arm: str) -> dict[str, Any]:
    """单臂的本人先胡率与胡牌平均番值（分层描述，不改门）。"""

    won = []
    fans = []
    for row in rows:
        record = row[arm]
        is_win = (record.get("winner_seat") is not None
                  and int(record["winner_seat"]) == focal
                  and not record.get("is_draw"))
        won.append(bool(is_win))
        if is_win and record.get("fan") is not None:
            fans.append(float(record["fan"]))
    return {"rounds": len(rows), "focal_hu_rate": _rate(won),
            "mean_fan_when_focal_hu": _mean(fans), "focal_hu_count": sum(won)}


def analyze() -> None:
    """以 16 个独立开发根评估「立即收 1 番」相对「盲弃胡」的机会与损失。"""

    manifest, frozen = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P24 开发教师执行不完整")
    development = [row for row in frozen if row["split"] == "development"]
    states = []
    all_mechanical = True
    divergence_ok = True
    for target in development:
        rows = [json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
                for index in range(1, ROLLOUTS_PER_STATE + 1)]
        for index, row in enumerate(rows, 1):
            validate_rollout_row(row, target, index, manifest["sample_keys"][index - 1])
        mechanical = all(row["mechanical_ok"] for row in rows)
        all_mechanical = all_mechanical and mechanical
        divergence_ok = divergence_ok and all(
            row["divergence"]["divergence_is_target_window"] is True for row in rows)
        focal = int(target["focal_physical_seat"])
        fit = rows[:FIT_ROLLOUTS]
        recheck = rows[FIT_ROLLOUTS:]
        fit_round = [row["focal_current_round_settlement_delta"] for row in fit]
        fit_table = [row["focal_current_table_score"]["delta"] for row in fit]
        recheck_round = [row["focal_current_round_settlement_delta"] for row in recheck]
        recheck_table = [row["focal_current_table_score"]["delta"] for row in recheck]
        fit_round_mean = statistics.fmean(fit_round)
        fit_table_mean = statistics.fmean(fit_table)
        recheck_round_mean = statistics.fmean(recheck_round)
        recheck_table_mean = statistics.fmean(recheck_table)
        selected = fit_round_mean > 0 and fit_table_mean > 0
        widths = {
            "reference": [item for row in fit for item in row["focal_widths"]["baseline"]][:0],
        }
        next_widths = {
            arm: [row["focal_widths"][arm][0]["chosen_useful_kinds"]
                  for row in recheck if row["focal_widths"][arm]]
            for arm in ("baseline", "candidate")
        }
        states.append({
            "target_id": target["target_id"],
            "source": target["source"], "features": target["features"],
            "immediate_hu_settlement": target["expected_hu_settlement"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "mechanical_ok": mechanical,
            "fit_mean_blind_deferral_minus_immediate_hu_current_round": fit_round_mean,
            "fit_mean_blind_deferral_minus_immediate_hu_current_table": fit_table_mean,
            "recheck_mean_blind_deferral_minus_immediate_hu_current_round": recheck_round_mean,
            "recheck_mean_blind_deferral_minus_immediate_hu_current_table": recheck_table_mean,
            "fit_selected_blind_deferral": selected,
            "fit_negative_counterexample": fit_round_mean < 0 or fit_table_mean < 0,
            "recheck_positive_both": recheck_round_mean > 0 and recheck_table_mean > 0,
            "fit_round_values": fit_round, "fit_table_values": fit_table,
            "recheck_round_values": recheck_round, "recheck_table_values": recheck_table,
            "fit_arm_metrics": {arm: arm_metrics(fit, focal, arm)
                                for arm in ("reference", "intervention")},
            "recheck_arm_metrics": {arm: arm_metrics(recheck, focal, arm)
                                    for arm in ("reference", "intervention")},
            "all_arm_metrics": {arm: arm_metrics(rows, focal, arm)
                                for arm in ("reference", "intervention")},
            "intervention_next_draw_useful_kinds_mean": _mean(next_widths["candidate"]),
            "reference_next_draw_useful_kinds_mean": _mean(next_widths["baseline"]),
            "recheck_terminal_counts_reference": dict(sorted(Counter(
                row["reference"]["terminal"] for row in recheck).items())),
            "recheck_terminal_counts_intervention": dict(sorted(Counter(
                row["intervention"]["terminal"] for row in recheck).items())),
            "terminal_transitions": dict(sorted(Counter(
                row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]
                for row in rows).items())),
            "divergence_prefix_digests": sorted({
                row["divergence"]["prefix_decision_digest"] for row in rows}),
        })

    selected = [row for row in states if row["fit_selected_blind_deferral"]]
    policy_round_values = [
        row["recheck_mean_blind_deferral_minus_immediate_hu_current_round"]
        if row["fit_selected_blind_deferral"] else 0.0 for row in states]
    policy_table_values = [
        row["recheck_mean_blind_deferral_minus_immediate_hu_current_table"]
        if row["fit_selected_blind_deferral"] else 0.0 for row in states]
    low, high = bootstrap_interval(policy_table_values)
    positive_selected = sum(row["recheck_positive_both"] for row in selected)
    required_positive = math.ceil(MINIMUM_RECHECK_POSITIVE_FRACTION * len(selected))
    negative_counterexamples = sum(row["fit_negative_counterexample"] for row in states)
    by_mix = {}
    for mix in ("H", "M"):
        items = [row for row in states if row["source"]["mix"] == mix]
        mix_selected = [row for row in items if row["fit_selected_blind_deferral"]]
        by_mix[mix] = {
            "independent_roots": len(items),
            "fit_selected_blind_deferral_roots": len(mix_selected),
            "fit_negative_counterexample_roots": sum(
                row["fit_negative_counterexample"] for row in items),
            "recheck_positive_selected_roots": sum(
                row["recheck_positive_both"] for row in mix_selected),
            "recheck_oracle_policy_table_mean": statistics.fmean(
                row["recheck_mean_blind_deferral_minus_immediate_hu_current_table"]
                if row["fit_selected_blind_deferral"] else 0.0 for row in items),
            "recheck_always_deferral_table_mean": statistics.fmean(
                row["recheck_mean_blind_deferral_minus_immediate_hu_current_table"]
                for row in items),
        }
    leave_one_out = {}
    for row in states:
        root = str(row["source"]["source_root_id"])
        remaining = [value for item, value in zip(states, policy_table_values)
                     if item["source"]["source_root_id"] != root]
        leave_one_out[root] = statistics.fmean(remaining)
    minimum_loo = min(leave_one_out.values())
    gate_development = bool(
        len(selected) >= MINIMUM_SELECTED_ROOTS
        and {row["source"]["mix"] for row in selected} == {"H", "M"}
        and negative_counterexamples >= 1
    )
    gate_order = bool(
        positive_selected >= required_positive
        and statistics.fmean(policy_table_values) > 0
    )
    gate_interval = bool(
        low > 0 and minimum_loo > 0
        and all(by_mix[mix]["recheck_oracle_policy_table_mean"] > 0 for mix in ("H", "M"))
    )
    gate_passed = bool(divergence_ok and all_mechanical
                       and gate_development and gate_order and gate_interval)
    result = {
        "schema": "r18-p24-deferral-complement-development-result/1",
        "status": "COMPLETE_P24_DEFERRAL_COMPLEMENT_DEVELOPMENT_TEACHER",
        "mechanical_ok": all_mechanical,
        "divergence_is_target_window_all": divergence_ok,
        "development_independent_roots": len(states),
        "paired_future_walls": len(states) * ROLLOUTS_PER_STATE,
        "current_full_tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "states": states,
        "aggregate": {
            "fit_selected_blind_deferral_roots": len(selected),
            "fit_negative_counterexample_roots": negative_counterexamples,
            "recheck_positive_selected_roots": positive_selected,
            "required_recheck_positive_selected_roots": required_positive,
            "recheck_oracle_policy_current_round_mean": statistics.fmean(policy_round_values),
            "recheck_oracle_policy_current_table_mean": statistics.fmean(policy_table_values),
            "recheck_oracle_policy_current_table_root_bootstrap_95": [low, high],
            "minimum_leave_one_source_root_out_current_table_mean": minimum_loo,
            "recheck_always_deferral_current_round_mean": statistics.fmean(
                row["recheck_mean_blind_deferral_minus_immediate_hu_current_round"]
                for row in states),
            "recheck_always_deferral_current_table_mean": statistics.fmean(
                row["recheck_mean_blind_deferral_minus_immediate_hu_current_table"]
                for row in states),
            "all_walls_always_deferral_current_round_mean": statistics.fmean(
                statistics.fmean(row["fit_round_values"] + row["recheck_round_values"])
                for row in states),
            "all_walls_always_deferral_current_table_mean": statistics.fmean(
                statistics.fmean(row["fit_table_values"] + row["recheck_table_values"])
                for row in states),
            "recheck_immediate_hu_focal_hu_rate": statistics.fmean(
                row["recheck_arm_metrics"]["reference"]["focal_hu_rate"] for row in states),
            "recheck_blind_deferral_focal_hu_rate": statistics.fmean(
                row["recheck_arm_metrics"]["intervention"]["focal_hu_rate"] for row in states),
            "recheck_immediate_hu_mean_fan": _mean([
                row["recheck_arm_metrics"]["reference"]["mean_fan_when_focal_hu"]
                for row in states if row["recheck_arm_metrics"]["reference"][
                    "mean_fan_when_focal_hu"] is not None]),
            "recheck_blind_deferral_mean_fan": _mean([
                row["recheck_arm_metrics"]["intervention"]["mean_fan_when_focal_hu"]
                for row in states if row["recheck_arm_metrics"]["intervention"][
                    "mean_fan_when_focal_hu"] is not None]),
        },
        "by_mix": by_mix,
        "leave_one_source_root_out_current_table": leave_one_out,
        "gate": {
            "mechanical": all_mechanical and divergence_ok,
            "development": gate_development,
            "order_sensitivity": gate_order,
            "interval": gate_interval,
        },
        "gate_passed": gate_passed,
        "decision": ("OPEN_PUBLIC_CRITERION_DESIGN" if gate_passed
                     else "CLOSE_WIDEN_HU_DEFERRAL_COVERAGE_AXIS_KEEP_R18_V2"),
        "inference_limit": (
            "fit-selected oracle is not a deployable policy; a public single-degree rule and "
            "independent unseen natural roots are still required"
        ),
        "sampling_scope": manifest["sampling_scope"],
        "model_calls": 0, "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({"status": result["status"], "mechanical_ok": all_mechanical,
                      "aggregate": result["aggregate"], "by_mix": by_mix,
                      "gate": result["gate"], "gate_passed": gate_passed,
                      "decision": result["decision"]}, ensure_ascii=False, indent=2))


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

