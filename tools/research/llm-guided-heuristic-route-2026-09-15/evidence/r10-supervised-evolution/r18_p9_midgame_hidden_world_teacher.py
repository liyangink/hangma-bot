"""R18 P9：中后盘七对的公开状态一致隐藏世界教师。

本批重建 P7 在完整桌中自然触发的 29 个门清弃牌窗口。每个基础状态生成
32 个共同隐藏世界：固定焦点玩家可见状态、公开历史、各家手牌张数与牌张
守恒，同时重分配三家暗手和未消费牌墙。两臂只在目标窗口分别强制 P5 与
P7 动作，之后焦点恢复 P5，对手保持冻结合同策略并完成当前桌。

重采样未使用历史动作似然，因此它是稳健性教师，不是历史条件后验。29 个
状态全部来自既有开发反例，本批不能冒充新隐藏准入；用途是判断哪些公开
子域值得冻结后再采零重叠隐藏状态。
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
import r18_p7_table_safety_topup as topup  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.hangma.interface import ValueAnalysisLimits  # noqa: E402
from hangma_bot.kernel.actions import action_key  # noqa: E402
from hangma_bot.kernel.serialization import (  # noqa: E402
    window_key_from_json,
    window_key_to_json,
)
from hangma_bot.offline.evaluate import seat_policies_from  # noqa: E402
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p9-midgame-hidden-world-teacher-01-20260922')
DATASET = topup.OUT / "natural-trigger-outcome-dataset.json"
P7 = topup.CANDIDATE
P5 = topup.PARENT
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
    """从既有 29 个自然触发生成固定目标；不按续打结果筛选。"""

    document = json.loads(DATASET.read_text(encoding="utf-8"))
    rows = document.get("rows") or []
    if document.get("status") != "COMPLETE" or len(rows) != 29:
        raise ValueError("P7 自然触发数据集必须完整包含 29 个窗口")
    result = []
    for index, row in enumerate(rows, 1):
        mix, root_text, focal_text = str(row["source_id"]).split(":")
        game_id = str(row["request"]["observation"]["game_id"])
        table_id = game_id.removeprefix("sitin-stage:")
        features = dict(row["observable_features"])
        result.append({
            "target_id": "p9-midgame-{0:02d}".format(index),
            "source": {
                "panel_seed": topup.PANEL_SEED,
                "mix": mix,
                "root_index": int(root_text[1:]),
                "focal_seat": int(focal_text[1:]),
                "table_no": int(table_id.rsplit("-t", 1)[1]),
                "table_id": table_id,
            },
            "window_key": row["request"]["window_key"],
            "focal_physical_seat": int(row["request"]["observation"]["seat"]),
            "reference_action": features["parent"]["action_key"],
            "intervention_action": features["candidate"]["action_key"],
            "features": features,
            "request_sha256": row["request_sha256"],
        })
    if len({row["request_sha256"] for row in result}) != len(result):
        raise ValueError("P9 基础窗口不唯一")
    return result


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-hidden-{1:02d}.json".format(
        target["target_id"], index
    ))


def source_paths() -> list[Path]:
    """列出会改变捕获、重建或续打语义的代码与冻结输入。"""

    import hangma_bot.offline.forced_action as forced_action
    import hangma_bot.simulation.engine as simulation_engine
    import hangma_bot.simulation.shuffle as simulation_shuffle

    return [
        Path(__file__), DATASET, P7, P5, CONTRACT,
        Path(core.__file__), Path(natural.__file__), Path(opportunities.__file__),
        Path(forced_action.__file__), Path(simulation_engine.__file__),
        Path(simulation_shuffle.__file__),
    ]


def prepare() -> None:
    """冻结 29 个开发状态、32 个隐藏世界键、分层判据和预算。"""

    if OUT.exists():
        raise SystemExit("P9 中后盘隐藏世界教师目录已存在；拒绝覆盖")
    frozen = targets()
    sample_keys = [
        "r18-p9-hidden-world-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(frozen) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p9-midgame-hidden-world-teacher-01",
        accounts={"prefix_generation": len(frozen), "tables_full": planned_tables},
        issued_by="lead",
        issued_at_utc=search.utc_now(),
        legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P7 的29个自然中后段触发只有单一已发生世界，不能据此训练或扩大P8作用域",
        "scope": "冻结29个既有开发窗口；每状态32个公开状态一致隐藏世界；P5/P7动作共同世界配对并恢复P5续打",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p9-midgame-hidden-world-targets/1",
        "targets": frozen,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p9-midgame-hidden-world-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "dataset_sha256": digest(DATASET),
        "p7_sha256": digest(P7),
        "p5_sha256": digest(P5),
        "contract_sha256": digest(CONTRACT),
        "targets": len(frozen),
        "rollouts_per_state": len(sample_keys),
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "workers": 8,
        "sampling_unit": "自然基础状态；32个隐藏分配只估计该状态的等权稳健性，不冒充32个独立状态",
        "resampling_scope": "固定焦点PlayerObservation、公开历史、手牌张数和牌张多重集；共同重分配三家暗手与未消费牌墙（含保留区）",
        "teacher_scope": "公开状态一致的等权隐藏分配稳健性；未使用历史动作似然，不是历史后验或无偏真实Q",
        "predeclared_strata": {
            "all": "全部29状态",
            "standard_tenpai": "candidate.standard_shanten_after == 0",
            "standard_not_tenpai": "candidate.standard_shanten_after >= 1",
            "early_wall": "remaining_tile_count >= 60",
            "late_wall": "remaining_tile_count < 60",
            "high_value_ratio": "expected_value_ratio >= 1.30",
            "lower_value_ratio": "expected_value_ratio < 1.30",
            "wealth_ge_2": "wealth_count >= 2",
            "wealth_lt_2": "wealth_count < 2",
            "dealer": "dealer == true",
            "nondealer": "dealer == false",
        },
        "decision_rule": {
            "eligible_development_subdomain": "预声明分层至少6个基础状态；不少于2/3状态均值为正；状态均值等权bootstrap下界>=0；逐一留一均值最小值>=0",
            "next_if_eligible": "按固定可观测谓词生成零重叠自然隐藏基础状态；隐藏通过前不扩大P8",
            "next_if_none": "保留P8起手边界；关闭P7中后盘代理，改造七对多步价值表示",
        },
        "development_only": True,
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
    checks = {
        "目标清单": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "自然数据集": (manifest["dataset_sha256"], digest(DATASET)),
        "P7": (manifest["p7_sha256"], digest(P7)),
        "P5": (manifest["p5_sha256"], digest(P5)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["targets"]
    if frozen != targets():
        raise ValueError("冻结目标与上游可重建目标不一致")
    return manifest, frozen


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
            raise ValueError("冻结七对动作已不合法：" + repr(missing))
        self.hits += 1
        return {
            "target_id": self.target["target_id"],
            "reference_action": self.target["reference_action"],
            "intervention_action": self.target["intervention_action"],
            "legal_action_keys": legal,
            "remaining_tile_count": request.observation.remaining_tile_count,
            "dealer_seat": request.observation.dealer_seat,
            "own_meld_count": len(request.observation.melds[request.observation.seat]),
            "features": self.target["features"],
        }


def run_p7_prefix_attempt(
    *,
    runtime: Mapping[str, Any],
    rules: HangmaRules,
    target: Mapping[str, Any],
    policies_by_seat: list[Any],
    tournament_config: Any,
    plan: Any,
) -> Any:
    """用 P7 焦点和合同对手重放合法前缀，截取精确窗口。

    通用机会捕获器把焦点策略固定为 V2，不能诚实重放 P7 已经改变过的
    自然轨迹。本入口保留同一组合根、规则分析、正式策略请求与合法动作复核，
    只把焦点行为身份显式改成冻结 P7；三家对手仍由合同白名单装配。
    """

    engine = runtime["engine"]
    chooser = runtime["choice_factory"]
    spec = runtime["spec_factory"](
        match_id=str(plan.match_id),
        scenario_id=str(plan.scenario_id),
        config=tournament_config,
        seed=int(plan.seed),
        initial_dealer=int(plan.initial_dealer),
        initial_scores=[0, 0, 0, 0],
    )
    world = engine.start(spec)
    prefix = []
    capture = ExactWindowCapture(target)
    execution = {
        seat: {
            "seat": seat,
            "policy_id": str(getattr(policy, "policy_id", "") or ""),
            "policy_class": type(policy).__name__,
            "windows": 0,
        }
        for seat, policy in enumerate(policies_by_seat)
    }
    for _ in range(100_000):
        frame = engine.frame(world)
        if frame.final_scores is not None or frame.blocked_reason is not None:
            break
        for decision in frame.decisions:
            if decision.window_key.seat != int(target["focal_physical_seat"]):
                continue
            analysis = rules.analyze(decision.observation, value_limits=LIMITS)
            request = opportunities.real_window_request(
                decision=decision,
                analysis=analysis,
                match_id=str(plan.match_id),
                config=opportunities._driver_config(),
                now_monotonic=lambda: 800.0,
            )
            witness = capture(request)
            if witness is not None:
                return opportunities.AttemptOutcome(
                    status="hit",
                    attempt_index=int(str(target["target_id"]).split("-")[-1]),
                    source_root_id=str(plan.scenario_id),
                    spec_seed=int(plan.seed),
                    prefix=tuple(prefix),
                    cut_frame=frame,
                    cut_decision=decision,
                    predicate_values={},
                    predicate_witness=witness,
                    projected_facts=None,
                    prefix_execution={
                        "schema": "r18-p9-p7-prefix-execution/1",
                        "focal_policy": "frozen P7 action-value policy",
                        "opponents": "group-dev-v1 whitelist policies",
                        "by_seat": list(execution.values()),
                    },
                )
        choices = []
        for decision in frame.decisions:
            analysis = rules.analyze(decision.observation, value_limits=LIMITS)
            request = opportunities.real_window_request(
                decision=decision,
                analysis=analysis,
                match_id=str(plan.match_id),
                config=opportunities._driver_config(),
                now_monotonic=lambda: 800.0,
            )
            seat = int(decision.window_key.seat)
            execution[seat]["windows"] += 1
            policy = policies_by_seat[seat]
            decision_plan = asyncio.run(policy.choose(
                request,
                opportunities._driver_config().budget_policy.build(
                    800.0, decision.timeout_seconds
                ),
            ))
            if not decision_plan.candidates:
                raise ValueError("P7 前缀策略未返回动作")
            action = decision_plan.candidates[0].action
            key = action_key(action)
            if not any(item.action_key == key for item in analysis.legal_candidates):
                raise ValueError("P7 前缀策略返回非法动作：" + key)
            choices.append(chooser(decision.window_key, action))
        world = engine.advance(world, frame.revision, tuple(choices))
        prefix.extend({
            "window_key": window_key_to_json(choice.window_key),
            "action_key": action_key(choice.action),
        } for choice in choices)
    raise ValueError("P7 合法前缀未命中冻结窗口")


def capture_one(target: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    """用原自然桌计划与冻结 P7 合法前缀重建一个精确中局快照。"""

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
        arm="candidate",
        candidate_scorer=ActionValueScorer(
            "r18-p9-capture-p7", P7.read_text(encoding="utf-8")
        ),
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
    tournament_config = opportunities._snapshot_tournament_config(
        {"rounds_per_game": int(contract["versions"]["rounds_per_game"])}, rules
    )
    attempt = run_p7_prefix_attempt(
        runtime=runtime,
        rules=rules,
        target=target,
        policies_by_seat=list(policies),
        tournament_config=tournament_config,
        plan=plan,
    )
    if attempt.status != "hit":
        raise ValueError("未在原自然桌合法前缀命中冻结窗口")
    runtime_kind = opportunities.runtime_kind_of(runtime)
    snapshot = dict(opportunities.build_snapshot(
        prefix_source="v2_behavior",
        attempt=attempt,
        predicate_id="r18_p9_seven_pairs_exact_window",
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
        witness_entry="r18_p9_seven_pairs_natural_exact_window",
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
        "focal_prefix_policy": "frozen P7 action-value policy",
        "prefix_source_note": "snapshot枚举沿用v2_behavior表示真实引擎合法前缀；实际焦点策略由prefix_behavior和本字段绑定为P7",
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
    """顺序捕获 29 个状态；一个状态失败即整批保持未完成。"""

    manifest, frozen = verify_manifest()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [row for row in frozen if not snapshot_path(row).exists()]
    reservation = ledger.reserve(
        step_id="r18:p9-midgame-hidden-world:capture",
        account="prefix_generation",
        amount=len(pending),
        note="29个自然七对精确窗口的P7合法前缀捕获",
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
        "schema": "r18-p9-midgame-hidden-world-capture/1",
        "captured": sum(snapshot_path(row).exists() for row in frozen),
        "planned": manifest["targets"],
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in frozen):
        raise RuntimeError("P9 七对状态捕获不完整")
    print(json.dumps({"status": "CAPTURE_COMPLETE", "targets": len(frozen)}, ensure_ascii=False))


def _policies_for_arm(
    *, target: Mapping[str, Any], snapshot: Mapping[str, Any], action_key: str,
    label: str,
) -> tuple[list[Any], Any]:
    """按捕获时的物理对手顺序装配对手；焦点强制一次后恢复 P5。"""

    capture_meta = snapshot["capture"]
    focal_seat = int(target["focal_physical_seat"])
    policies = list(opportunities.frozen_generation_policies(
        opponent_names=capture_meta["opponent_names_in_physical_order"],
        focal_seat=focal_seat,
        monotonic=lambda: 800.0,
    ))
    delegate = ActionValuePolicy(ActionValueScorer(
        "r18-p9-p5-continuation-" + label,
        P5.read_text(encoding="utf-8"),
    ))
    forced = ForceFirstActionPolicy(
        delegate,
        target_window=window_key_from_json(target["window_key"]),
        forced_action_key=action_key,
        policy_id="r18-p9-" + label,
    )
    policies[focal_seat] = forced
    return policies, forced


def execute_rollout(target: Mapping[str, Any], index: int, sample_key: str) -> dict[str, Any]:
    """在一个共同公开状态一致隐藏世界下完成两臂当前桌。"""

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
        current_world_transform=lambda world: runtime["engine"].resample_public_consistent_hidden_world(
            world,
            focal_seat=int(target["focal_physical_seat"]),
            sample_key=sample_key,
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
        "schema": "r18-p9-midgame-hidden-world-rollout/1",
        "target_id": target["target_id"],
        "rollout_index": index,
        "sample_key": sample_key,
        "reference_action": target["reference_action"],
        "intervention_action": target["intervention_action"],
        "actual_actions": actions,
        "force_count": {
            "reference": reference_force.force_count,
            "intervention": intervention_force.force_count,
        },
        "focal_remaining_table_score": {
            "reference": reference_score,
            "intervention": intervention_score,
        },
        "intervention_minus_reference": delta,
        "tables_executed": double.get("tables_executed"),
        "completion_reasons": double.get("completion_reasons"),
        "runtime_kind": double.get("runtime_kind"),
        "execution_kind": double.get("execution_kind"),
        "sampling_scope": "public-consistent opponent hands plus unconsumed wall; not history posterior",
        "mechanical_ok": mechanical_ok,
    }


def run() -> None:
    """并行执行 29×32 个共同隐藏世界配对，支持断点续跑。"""

    manifest, frozen = verify_manifest()
    capture_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    if capture_summary["failures"] or capture_summary["captured"] != manifest["targets"]:
        raise ValueError("29 个精确状态尚未全部捕获")
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
                    raise ValueError("既有七对隐藏世界配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p9-midgame-hidden-world:run",
        account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="29状态×32共同隐藏世界×P5/P7首动作两臂当前桌续打",
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
                        raise RuntimeError("共同隐藏世界配对机械条件失败")
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
        "schema": "r18-p9-midgame-hidden-world-run/1",
        "rollout_files": len(files),
        "actual_tables": len(files) * 2,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P9 跨隐藏世界执行不完整")
    print(json.dumps({"status": "RUN_COMPLETE", "tables": len(files) * 2}, ensure_ascii=False))


def bootstrap_interval(values: list[float], salt: int) -> tuple[float, float]:
    """确定性普通 bootstrap；解释单位由调用处明确。"""

    rng = random.Random(202609221800 + salt)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(sum(values[rng.randrange(len(values))] for _ in values) / len(values))
    means.sort()
    return (
        means[math.floor(0.025 * (len(means) - 1))],
        means[math.ceil(0.975 * (len(means) - 1))],
    )


def target_strata(target: Mapping[str, Any]) -> tuple[str, ...]:
    """按预登记的单维公开谓词给基础状态分层。"""

    features = target["features"]
    standard = int(features["candidate"]["standard_shanten_after"])
    remaining = int(features["remaining_tile_count"])
    ratio = float(features["expected_value_ratio"])
    wealth = int(features["wealth_count"])
    return (
        "all",
        "standard_tenpai" if standard == 0 else "standard_not_tenpai",
        "early_wall" if remaining >= 60 else "late_wall",
        "high_value_ratio" if ratio >= 1.30 else "lower_value_ratio",
        "wealth_ge_2" if wealth >= 2 else "wealth_lt_2",
        "dealer" if features["dealer"] else "nondealer",
    )


def analyze() -> None:
    """先按状态汇总 32 个隐藏世界，再按基础状态等权判读预声明分层。"""

    manifest, frozen = verify_manifest()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P9 跨隐藏世界执行不完整")
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
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "strata": list(target_strata(target)),
            "features": target["features"],
            "hidden_world_rollouts": len(values),
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
    for index, name in enumerate(manifest["predeclared_strata"]):
        selected = [row for row in state_rows if name in row["strata"]]
        means = [float(row["mean_delta"]) for row in selected]
        lo, hi = bootstrap_interval(means, 10_000 + index)
        required_positive = math.ceil(2 * len(means) / 3)
        leave_one_out = [
            statistics.fmean(means[:cut] + means[cut + 1:])
            for cut in range(len(means))
        ] if len(means) > 1 else means
        eligible = bool(
            len(means) >= 6
            and sum(value > 0 for value in means) >= required_positive
            and lo >= 0.0
            and min(leave_one_out) >= 0.0
        )
        strata[name] = {
            "base_states": len(selected),
            "hidden_world_rollouts": sum(row["hidden_world_rollouts"] for row in selected),
            "unweighted_mean_of_state_means": statistics.fmean(means),
            "bootstrap_95_state_mean": [lo, hi],
            "positive_state_means": sum(value > 0 for value in means),
            "zero_state_means": sum(value == 0 for value in means),
            "negative_state_means": sum(value < 0 for value in means),
            "required_positive_state_means": required_positive,
            "minimum_leave_one_state_out_mean": min(leave_one_out),
            "eligible_development_subdomain": eligible,
            "state_ids": [row["target_id"] for row in selected],
        }
    eligible = [name for name, row in strata.items()
                if row["eligible_development_subdomain"]]
    eligible.sort(key=lambda name: (
        -int(strata[name]["base_states"]),
        -float(strata[name]["bootstrap_95_state_mean"][0]),
        name,
    ))
    selected = eligible[0] if eligible else None
    decision = (
        "FREEZE_SUBDOMAIN_AND_BUILD_ZERO_OVERLAP_HIDDEN"
        if selected is not None else
        "CLOSE_P7_MIDGAME_PROXY_KEEP_P8_INITIAL_ONLY"
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), {
        "schema": "r18-p9-midgame-hidden-world-result/1",
        "status": "COMPLETE_P9_MIDGAME_HIDDEN_WORLD_TEACHER",
        "mechanical_ok": all_mechanical,
        "base_states": len(state_rows),
        "rollouts": len(state_rows) * ROLLOUTS_PER_STATE,
        "tables": len(state_rows) * ROLLOUTS_PER_STATE * 2,
        "states": state_rows,
        "strata": strata,
        "checks": {
            "all_pairs_mechanical_ok": all_mechanical,
            "all_29_base_states_present": len(state_rows) == 29,
            "all_states_have_32_common_hidden_worlds": all(
                row["hidden_world_rollouts"] == 32 for row in state_rows
            ),
        },
        "decision": decision,
        "eligible_development_subdomains": eligible,
        "selected_development_subdomain": selected,
        "author_task_open": False,
        "next_gate": (
            "把选中单维谓词冻结为P9候选域，采集零重叠自然基础状态并重复32世界配对；隐藏通过前不改P8"
            if selected is not None else
            "停止P7一次自摸代理向中后盘外推；建立含他家先胡与多步生存的七对价值表示"
        ),
        "interpretation": "32个隐藏世界只估计每个既有开发状态的等权稳健性；独立统计单位仍是29个基础状态，且采样不是历史动作条件后验",
        "development_only": True,
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
