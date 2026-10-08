"""R18 P13：P12 开发集七对竞争前沿的共同隐藏世界教师。

只打开 P12 冻结的 28 个 development 状态；hidden 状态继续保持无标签。
每个状态在 32 个公开状态一致隐藏世界中，比较 P5 原动作与结果盲冻结的
七对前沿动作。两臂只在目标窗口分叉，之后焦点均恢复 P5，对手保持合同策略。

主标签是目标局内的焦点和牌到达、条件番数、对手和牌、流局和局结算；完整
剩余桌得分仅作安全诊断，防止把后续庄位、分数与未来局级联写回动作教师。
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
from collections import Counter
import hashlib
import json
from pathlib import Path
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
import r18_p12_natural_seven_pairs_frontier as p12  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.actions import action_key  # noqa: E402
from hangma_bot.kernel.serialization import window_key_from_json, window_key_to_json  # noqa: E402
from hangma_bot.offline.evaluate import seat_policies_from  # noqa: E402
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p13-development-seven-pairs-teacher-01-20260922')
FRONTIER = p12.OUT / "frozen-frontier.json"
CONTRACT = p12.CONTRACT
PARENT = p12.PARENT
LIMITS = p12.LIMITS
ROLLOUTS_PER_STATE = 32
WORKERS = 8


def write_json(path: Path, value: Any) -> None:
    """写入排序、缩进且以换行结束的 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    """返回规范 JSON 值摘要。"""

    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def state_projection(request_json: Mapping[str, Any]) -> dict[str, Any]:
    """去掉策略身份与赛事排名，只保留能够证明同一决策状态的请求字段。"""

    return {
        "observation": request_json["observation"],
        "rules": request_json["rules"],
        "trigger_seq": request_json["trigger_seq"],
        "window_key": request_json["window_key"],
    }


def targets() -> list[dict[str, Any]]:
    """把结果盲冻结的 development 行转换为紧凑教师目标。"""

    document = json.loads(FRONTIER.read_text(encoding="utf-8"))
    if document.get("hidden_labels_opened") is not False:
        raise ValueError("P12 hidden 必须仍为未开标签状态")
    development = document.get("development") or []
    if len(development) != 28:
        raise ValueError("P12 development 必须恰有 28 个状态")
    result = []
    for index, row in enumerate(development, 1):
        request = row["request"]
        observation = request["observation"]
        game_id = str(observation["game_id"])
        table_id = game_id.removeprefix("sitin-stage:")
        result.append({
            "target_id": "r18-p13-dev-{0:02d}".format(index),
            "source": {
                "panel_seed": p12.PANEL_SEED,
                "source_id": row["source_id"],
                "mix": row["mix"],
                "root_index": row["root_index"],
                "focal_seat": row["focal_seat"],
                "table_no": int(table_id.rsplit("-t", 1)[1]),
                "table_id": table_id,
            },
            "window_key": request["window_key"],
            "focal_physical_seat": int(observation["seat"]),
            "request_sha256": row["request_sha256"],
            "state_projection_sha256": value_digest(state_projection(request)),
            "reference_action": row["parent"]["action_key"],
            "intervention_action": row["seven_pairs_frontier"]["action_key"],
            "features": {
                "round_no": row["round_no"],
                "dealer": row["dealer"],
                "remaining_tile_count": row["remaining_tile_count"],
                "wealth_count": row["wealth_count"],
                "pair_kinds": row["pair_kinds"],
                "triplet_kinds": row["triplet_kinds"],
                "standard_effect": row["standard_effect"],
                "parent": row["parent"],
                "seven_pairs_frontier": row["seven_pairs_frontier"],
            },
        })
    if len({row["source"]["source_id"] for row in result}) != len(result):
        raise ValueError("P13 development 来源重复")
    return result


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-hidden-{1:02d}.json".format(
        target["target_id"], index,
    ))


def source_paths() -> list[Path]:
    """列出会改变重放、隐藏重采样或标签语义的输入。"""

    import hangma_bot.offline.forced_action as forced_action
    import hangma_bot.simulation.engine as simulation_engine
    import hangma_bot.simulation.shuffle as simulation_shuffle

    return [
        Path(__file__), FRONTIER, CONTRACT, PARENT,
        Path(core.__file__), Path(p9.__file__), Path(p11.__file__), Path(p12.__file__),
        Path(natural.__file__), Path(opportunities.__file__), Path(forced_action.__file__),
        Path(simulation_engine.__file__), Path(simulation_shuffle.__file__),
    ]


def prepare() -> None:
    """冻结 28 个开发状态、32 个共同隐藏世界和执行预算。"""

    if OUT.exists():
        raise SystemExit("P13 目录已存在；拒绝覆盖")
    frozen = targets()
    sample_keys = [
        "r18-p13-dev-hidden-world-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(frozen) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p13-development-seven-pairs-teacher-01",
        accounts={"prefix_generation": len(frozen), "tables_full": planned_tables},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P12 已结果盲冻结 development/hidden；本批只打开 development 标签",
        "scope": "28个开发状态×32个共同隐藏世界×P5原动作/七对前沿动作；hidden不运行",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p13-development-targets/1", "targets": frozen,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p13-development-teacher-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "frontier_sha256": digest(FRONTIER),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "parent_sha256": digest(PARENT),
        "contract_sha256": digest(CONTRACT),
        "base_states": len(frozen),
        "rollouts_per_state": len(sample_keys),
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "workers": WORKERS,
        "sampling_unit": "自然基础状态；32个隐藏分配只估计该状态的等权稳健性",
        "primary_labels": [
            "focal_hu", "focal_hu_fan", "opponent_hu", "wall_draw_or_non_hu_end",
            "focal_current_round_settlement",
        ],
        "safety_diagnostic": "focal_remaining_table_score；不得直接写回七对动作教师",
        "hidden_labels_opened": False,
        "development_labels_selection_eligible": True,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "targets": len(frozen),
        "rollouts_per_state": len(sample_keys), "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对冻结输入与执行实现没有漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P12冻结前沿": (manifest["frontier_sha256"], digest(FRONTIER)),
        "P13目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "P5父代": (manifest["parent_sha256"], digest(PARENT)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["targets"]
    if frozen != targets():
        raise ValueError("P13目标不可由P12重建")
    return manifest, frozen


class ExactStateCapture:
    """只截取冻结窗口，并核对可复算状态摘要与两动作合法性。"""

    def __init__(self, target: Mapping[str, Any]) -> None:
        self.target = dict(target)
        self.window_key = window_key_from_json(target["window_key"])
        self.hits = 0

    def __call__(self, request: Any) -> dict[str, Any] | None:
        if request.window_key != self.window_key:
            return None
        request_json = decision_request_to_json(request)
        actual = value_digest(state_projection(request_json))
        if actual != self.target["state_projection_sha256"]:
            raise ValueError("命中WindowKey但观察/规则状态摘要漂移")
        legal = sorted(item.action_key for item in request.rules.legal_candidates)
        expected = {
            str(self.target["reference_action"]),
            str(self.target["intervention_action"]),
        }
        missing = sorted(expected - set(legal))
        if missing:
            raise ValueError("冻结七对竞争动作已不合法：" + repr(missing))
        self.hits += 1
        return {
            "target_id": self.target["target_id"],
            "state_projection_sha256": actual,
            "reference_action": self.target["reference_action"],
            "intervention_action": self.target["intervention_action"],
            "legal_action_keys": legal,
        }


def run_p5_prefix_attempt(
    *, runtime: Mapping[str, Any], rules: HangmaRules,
    target: Mapping[str, Any], policies_by_seat: list[Any],
    tournament_config: Any, plan: Any,
) -> Any:
    """按 P12 的 P5 与合同对手重放合法前缀，截取精确状态。"""

    engine = runtime["engine"]
    chooser = runtime["choice_factory"]
    spec = runtime["spec_factory"](
        match_id=str(plan.match_id), scenario_id=str(plan.scenario_id),
        config=tournament_config, seed=int(plan.seed),
        initial_dealer=int(plan.initial_dealer), initial_scores=[0, 0, 0, 0],
    )
    world = engine.start(spec)
    prefix = []
    capture = ExactStateCapture(target)
    execution = {
        seat: {
            "seat": seat, "policy_id": str(getattr(policy, "policy_id", "") or ""),
            "policy_class": type(policy).__name__, "windows": 0,
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
                decision=decision, analysis=analysis, match_id=str(plan.match_id),
                config=opportunities._driver_config(), now_monotonic=lambda: 800.0,
            )
            witness = capture(request)
            if witness is not None:
                return opportunities.AttemptOutcome(
                    status="hit",
                    attempt_index=int(str(target["target_id"]).split("-")[-1]),
                    source_root_id=str(plan.scenario_id), spec_seed=int(plan.seed),
                    prefix=tuple(prefix), cut_frame=frame, cut_decision=decision,
                    predicate_values={}, predicate_witness=witness,
                    projected_facts=None,
                    prefix_execution={
                        "schema": "r18-p13-p5-prefix-execution/1",
                        "focal_policy": "frozen P5 action-value policy",
                        "opponents": "group-dev-v1 whitelist policies",
                        "by_seat": list(execution.values()),
                    },
                )
        choices = []
        for decision in frame.decisions:
            analysis = rules.analyze(decision.observation, value_limits=LIMITS)
            request = opportunities.real_window_request(
                decision=decision, analysis=analysis, match_id=str(plan.match_id),
                config=opportunities._driver_config(), now_monotonic=lambda: 800.0,
            )
            seat = int(decision.window_key.seat)
            execution[seat]["windows"] += 1
            decision_plan = asyncio.run(policies_by_seat[seat].choose(
                request,
                opportunities._driver_config().budget_policy.build(
                    800.0, decision.timeout_seconds,
                ),
            ))
            if not decision_plan.candidates:
                raise ValueError("P5前缀策略未返回动作")
            action = decision_plan.candidates[0].action
            key = action_key(action)
            if not any(item.action_key == key for item in analysis.legal_candidates):
                raise ValueError("P5前缀策略返回非法动作：" + key)
            choices.append(chooser(decision.window_key, action))
        world = engine.advance(world, frame.revision, tuple(choices))
        prefix.extend({
            "window_key": window_key_to_json(choice.window_key),
            "action_key": action_key(choice.action),
        } for choice in choices)
    raise ValueError("P5合法前缀未命中冻结窗口")


def capture_one(target: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    """用原自然桌计划与 P5 合法前缀重建精确中局快照。"""

    source = target["source"]
    plans = natural.build_seat_stage_plans(
        contract=contract, opponent=str(source["mix"]),
        root_index=int(source["root_index"]), focal_seat=int(source["focal_seat"]),
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
            "r18-p13-capture-p5", PARENT.read_text(encoding="utf-8"),
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
        raise ValueError("焦点物理座位与计划换座不符")
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
    attempt = run_p5_prefix_attempt(
        runtime=runtime, rules=rules, target=target, policies_by_seat=policies,
        tournament_config=tournament_config, plan=plan,
    )
    runtime_kind = opportunities.runtime_kind_of(runtime)
    snapshot = dict(opportunities.build_snapshot(
        prefix_source="v2_behavior", attempt=attempt,
        predicate_id="r18_p13_p5_exact_window", focal_seat=focal_physical,
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
        witness_entry="r18_p13_p5_natural_exact_window",
    ))
    snapshot["seating"]["participant_ids_by_seat"] = list(plan.seats())
    snapshot["stage_plan"]["participant_ids_by_seat"] = list(plan.seats())
    snapshot["capture"] = {
        "target": dict(target), "table_seed": int(plan.seed),
        "table_scenario_id": str(plan.scenario_id),
        "physical_policy_names": physical_names,
        "opponent_names_in_physical_order": verifier_names,
        "prefix_steps": len(attempt.prefix),
        "focal_prefix_policy": "frozen P5 action-value policy",
        "prefix_source_note": "snapshot枚举沿用v2_behavior表示真实引擎合法前缀；实际焦点策略由本字段绑定为P5",
        "witness": dict(attempt.predicate_witness or {}),
    }
    engine, world = opportunities.rebuild_world(
        rules=rules, snapshot=snapshot, value_limits=LIMITS, runtime=runtime,
    )
    if opportunities.frame_observation_summary(engine.frame(world)) != snapshot["observation_summary"]:
        raise ValueError("快照公开重建后的观察摘要不一致")
    return snapshot


def capture() -> None:
    """顺序捕获 28 个开发状态，支持断点续跑。"""

    manifest, frozen = verify()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [row for row in frozen if not snapshot_path(row).exists()]
    reservation = ledger.reserve(
        step_id="r18:p13-development-seven-pairs:capture",
        account="prefix_generation", amount=len(pending),
        note="28个P12开发状态的P5精确合法前缀捕获",
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
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "target_id": target["target_id"],
                    "error": type(exc).__name__ + ": " + str(exc),
                })
    finally:
        ledger.settle(reservation, actual=completed, note="按成功捕获的合法前缀计")
    write_json(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"), {
        "schema": "r18-p13-capture-summary/1",
        "captured": sum(snapshot_path(row).exists() for row in frozen),
        "planned": manifest["base_states"], "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in frozen):
        raise RuntimeError("P13 development 状态捕获不完整")


def policies_for_arm(
    *, target: Mapping[str, Any], snapshot: Mapping[str, Any],
    forced_action_key: str, label: str,
) -> tuple[list[Any], ForceFirstActionPolicy]:
    """焦点强制目标动作一次后恢复 P5，对手沿用捕获合同。"""

    focal = int(target["focal_physical_seat"])
    policies = list(opportunities.frozen_generation_policies(
        opponent_names=snapshot["capture"]["opponent_names_in_physical_order"],
        focal_seat=focal, monotonic=lambda: 800.0,
    ))
    delegate = ActionValuePolicy(ActionValueScorer(
        "r18-p13-p5-continuation-" + label, PARENT.read_text(encoding="utf-8"),
    ))
    forced = ForceFirstActionPolicy(
        delegate, target_window=window_key_from_json(target["window_key"]),
        forced_action_key=forced_action_key, policy_id="r18-p13-" + label,
    )
    policies[focal] = forced
    return policies, forced


def terminal(record: Any, focal: int) -> str:
    """把目标局结算归为焦点和、对手和或流局/非和终止。"""

    if record.is_draw or record.winner_seat is None:
        return "wall_draw_or_non_hu_end"
    return "focal_hu" if int(record.winner_seat) == focal else "opponent_hu"


def execute_rollout(target: Mapping[str, Any], index: int, sample_key: str) -> dict[str, Any]:
    """在一个共同隐藏世界下执行两臂并截取目标局结算。"""

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
        label="reference-{0}-{1:02d}".format(target["target_id"], index),
    )
    intervention_policies, intervention_force = policies_for_arm(
        target=target, snapshot=snapshot,
        forced_action_key=str(target["intervention_action"]),
        label="intervention-{0}-{1:02d}".format(target["target_id"], index),
    )
    double = opportunities.run_double_arm(
        rules=rules, snapshot=snapshot,
        baseline_policies_by_seat=reference_policies,
        candidate_policies_by_seat=intervention_policies,
        config=opportunities._driver_config(), value_limits=LIMITS, runtime=runtime,
        current_world_transform=lambda world: settlement.resample_public_consistent_hidden_world(
            world, focal_seat=int(target["focal_physical_seat"]),
            sample_key=sample_key,
        ),
    )
    cut_round = int(target["features"]["round_no"])
    records = [record for record in settlement.records if record.round_no == cut_round]
    if len(records) != 2:
        raise RuntimeError("目标局必须按参考臂、干预臂各捕获一次，实际 {0}".format(len(records)))
    reference_record, intervention_record = records
    focal = int(target["focal_physical_seat"])
    actions = {
        arm: (((double.get("window_actions") or {}).get("arms") or {}).get(arm) or {}).get("action_key")
        for arm in ("baseline", "candidate")
    }
    reference_score = double["arms"]["baseline"].get("focal_stage_score")
    intervention_score = double["arms"]["candidate"].get("focal_stage_score")
    mechanical = bool(
        double.get("valid") and reference_force.force_count == 1
        and intervention_force.force_count == 1
        and actions["baseline"] == target["reference_action"]
        and actions["candidate"] == target["intervention_action"]
        and double.get("tables_executed") == {"baseline": 1, "candidate": 1}
        and reference_score is not None and intervention_score is not None
    )
    reference = p11.record_json(reference_record)
    intervention = p11.record_json(intervention_record)
    reference["terminal"] = terminal(reference_record, focal)
    intervention["terminal"] = terminal(intervention_record, focal)
    reference["focal_settlement"] = int(reference_record.score_delta[focal])
    intervention["focal_settlement"] = int(intervention_record.score_delta[focal])
    return {
        "schema": "r18-p13-development-seven-pairs-rollout/1",
        "target_id": target["target_id"], "rollout_index": index,
        "sample_key": sample_key,
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
        "sampling_scope": "public-consistent opponent hands plus unconsumed wall; not history posterior",
        "mechanical_ok": mechanical,
    }


def run() -> None:
    """并行执行 28×32 个共同隐藏世界配对，支持断点续跑。"""

    manifest, frozen = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["captured"] != manifest["base_states"]:
        raise ValueError("P13 精确状态尚未全部捕获")
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
                    raise ValueError("既有P13配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p13-development-seven-pairs:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="28开发状态×32共同隐藏世界×P5原动作/七对前沿动作",
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
                row = None
                try:
                    row = future.result()
                    if not row["mechanical_ok"]:
                        raise RuntimeError("P13共同隐藏世界配对机械条件失败")
                    write_json(rollout_path(target, index), row)
                    executed += 2
                    completed_tables += 2
                    if completed_tables % 64 == 0:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": manifest["planned_tables"],
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    if row is None:
                        usage_unknown = True
                    failures.append({
                        "target_id": target["target_id"], "rollout_index": index,
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按成功两臂桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "rollouts")).glob("*.json"))
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p13-run-summary/1", "rollout_files": len(files),
        "actual_tables": len(files) * 2, "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P13 development 教师执行不完整")


def _arm_summary(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    """汇总一条动作臂的局内结果；番数仅在焦点和牌条件下取均值。"""

    terminal_counts = Counter(row[arm]["terminal"] for row in rows)
    focal_wins = [row[arm] for row in rows if row[arm]["terminal"] == "focal_hu"]
    return {
        "focal_hu": terminal_counts["focal_hu"],
        "opponent_hu": terminal_counts["opponent_hu"],
        "wall_draw_or_non_hu_end": terminal_counts["wall_draw_or_non_hu_end"],
        "focal_hu_rate": terminal_counts["focal_hu"] / len(rows),
        "opponent_hu_rate": terminal_counts["opponent_hu"] / len(rows),
        "wall_draw_or_non_hu_end_rate": terminal_counts["wall_draw_or_non_hu_end"] / len(rows),
        "mean_focal_settlement": statistics.fmean(
            row[arm]["focal_settlement"] for row in rows
        ),
        "conditional_focal_hu_mean_fan": (
            statistics.fmean(row["fan"] for row in focal_wins)
            if focal_wins else None
        ),
        "conditional_focal_hu_mean_settlement": (
            statistics.fmean(row["focal_settlement"] for row in focal_wins)
            if focal_wins else None
        ),
    }


def analyze() -> None:
    """按基础状态等权生成可用于拟合的机制标签与安全诊断。"""

    manifest, frozen = verify()
    run_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if run_summary["failures"] or run_summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P13 development 教师执行不完整")
    states = []
    transitions: Counter[str] = Counter()
    all_mechanical = True
    for target in frozen:
        rows = [
            json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, ROLLOUTS_PER_STATE + 1)
        ]
        all_mechanical = all_mechanical and all(row["mechanical_ok"] for row in rows)
        for row in rows:
            transitions[row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]] += 1
        reference = _arm_summary(rows, "reference")
        intervention = _arm_summary(rows, "intervention")
        direct_values = [row["focal_current_round_settlement_delta"] for row in rows]
        full_values = [row["focal_remaining_table_score"]["delta"] for row in rows]
        states.append({
            "target_id": target["target_id"], "source": target["source"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "features": target["features"], "hidden_world_rollouts": len(rows),
            "reference": reference, "intervention": intervention,
            "delta": {
                "focal_hu_rate": intervention["focal_hu_rate"] - reference["focal_hu_rate"],
                "opponent_hu_rate": intervention["opponent_hu_rate"] - reference["opponent_hu_rate"],
                "wall_draw_or_non_hu_end_rate": (
                    intervention["wall_draw_or_non_hu_end_rate"]
                    - reference["wall_draw_or_non_hu_end_rate"]
                ),
                "mean_current_round_settlement": statistics.fmean(direct_values),
                "mean_remaining_table_score": statistics.fmean(full_values),
            },
            "current_round_settlement_values": direct_values,
            "remaining_table_score_values": full_values,
        })
    reference_hu = sum(row["reference"]["focal_hu"] for row in states)
    intervention_hu = sum(row["intervention"]["focal_hu"] for row in states)
    direct_state_means = [row["delta"]["mean_current_round_settlement"] for row in states]
    full_state_means = [row["delta"]["mean_remaining_table_score"] for row in states]
    result = {
        "schema": "r18-p13-development-seven-pairs-result/1",
        "status": "COMPLETE_P13_DEVELOPMENT_SEVEN_PAIRS_TEACHER",
        "mechanical_ok": all_mechanical,
        "base_states": len(states),
        "rollouts": len(states) * ROLLOUTS_PER_STATE,
        "tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "states": states,
        "aggregate": {
            "reference_focal_hu": reference_hu,
            "intervention_focal_hu": intervention_hu,
            "focal_hu_delta": intervention_hu - reference_hu,
            "terminal_transitions": dict(sorted(transitions.items())),
            "unweighted_mean_state_current_round_settlement_delta": statistics.fmean(direct_state_means),
            "unweighted_mean_state_remaining_table_score_delta": statistics.fmean(full_state_means),
            "positive_current_round_state_means": sum(value > 0 for value in direct_state_means),
            "zero_current_round_state_means": sum(value == 0 for value in direct_state_means),
            "negative_current_round_state_means": sum(value < 0 for value in direct_state_means),
        },
        "checks": {
            "all_pairs_mechanical_ok": all_mechanical,
            "all_28_development_states_present": len(states) == 28,
            "all_states_have_32_common_hidden_worlds": all(
                row["hidden_world_rollouts"] == 32 for row in states
            ),
            "hidden_labels_opened": False,
        },
        "next_gate": "用开发标签拟合可解释七对动作价值并按source分组交叉验证；候选冻结前不得生成P12 hidden标签",
        "interpretation": "独立统计单位是28个自然基础状态；32个等权隐藏分配不是历史动作条件后验，也不增加独立状态数",
        "development_labels_selection_eligible": True,
        "hidden_labels_opened": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], "mechanical_ok": all_mechanical,
        "base_states": len(states), "rollouts": result["rollouts"],
        "aggregate": result["aggregate"],
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
