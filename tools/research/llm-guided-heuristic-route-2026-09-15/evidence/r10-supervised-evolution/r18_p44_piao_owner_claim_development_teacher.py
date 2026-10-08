"""R18 P44：首飘后圈主吃碰的开发集共同未来牌墙教师。

P43 结果盲冻结了 16 个开发状态和 16 个隐藏状态。本批只运行开发状态，
固定来源世界的四家暗手与已经发生的历史，在截取响应窗口共同重排尚未摸取
的未来牌墙。每个合法吃碰分别与 ``pass`` 配对；同一状态即使有多个吃法也
仍只算一个统计根。

开发集只有 3 个吃响应、13 个碰响应，因此预先冻结：碰是唯一准入统计层，
吃只作探索性诊断。隐藏状态在候选源码与公开谓词冻结前不生成收益标签。
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
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
ROOT = _PROJECT_ROOT
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), HERE):
    sys.path.insert(0, str(path))

import confirmation_execution_identity as guard  # noqa: E402
import r18_p43_piao_owner_claim_exposure as p43  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.kernel.actions import action_key  # noqa: E402
from hangma_bot.kernel.serialization import window_key_from_json  # noqa: E402
from hangma_bot.offline.evaluate import frame_observation_summary, resume_match  # noqa: E402
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.simulation import SimulationChoice, SimulationEngine  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p44-piao-owner-claim-development-teacher-01-20260922')
P43_TARGETS = p43.OUT / "targets.json"
P43_RESULT = p43.OUT / "result.json"
PARENT = p43.PARENT
CONTRACT = p43.CONTRACT
PRIMARY_FAMILY = "peng"
ROLLOUTS_PER_STATE = 32
FIT_ROLLOUTS = 16
WORKERS = 8
BOOTSTRAP_REPLICATES = 20_000
BOOTSTRAP_SEED = 2026092244
MINIMUM_SELECTED_STATES = 4
MINIMUM_RECHECK_POSITIVE_FRACTION = 0.75


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def targets() -> list[dict[str, Any]]:
    """从 P43 的结果盲切分重建开发与隐藏目标，不读取结算。"""

    result = json.loads(P43_RESULT.read_text(encoding="utf-8"))
    if result.get("status") != "OPEN_P44_DEVELOPMENT_TEACHER":
        raise ValueError("P43 未开放 P44 开发教师")
    document = json.loads(P43_TARGETS.read_text(encoding="utf-8"))
    if document.get("hidden_labels_opened") is not False:
        raise ValueError("P43 隐藏标签必须保持封存")
    rows = [("development", row) for row in document["development"]]
    rows.extend(("hidden", row) for row in document["hidden"])
    counters: Counter[tuple[str, str]] = Counter()
    frozen = []
    for split, row in rows:
        family = "chi" if row["phase"] == "response_chi" else "peng"
        if row["phase"] not in ("response_chi", "response_peng"):
            raise ValueError("P44 只接受吃碰响应")
        counters[(split, family)] += 1
        request = row["request"]
        frozen.append({
            "target_id": "r18-p44-{0}-{1}-{2:02d}".format(
                split, family, counters[(split, family)],
            ),
            "split": split,
            "family": family,
            "source": dict(row["source"]),
            "window_key": request["window_key"],
            "focal_physical_seat": int(request["observation"]["seat"]),
            "request_sha256": row["request_sha256"],
            "reference_action": "pass",
            "claim_actions": list(row["claim_action_keys"]),
            "features": {
                "phase": row["phase"],
                "role": row["source"]["role"],
                "focal_seat": int(row["source"]["focal_seat"]),
                "round_no": int(row["round_no"]),
                "remaining_tile_count": row["remaining_tile_count"],
                "chain_piao": row["chain_piao"],
                "chain_count": row["chain_count"],
                "claim_count": len(row["claim_action_keys"]),
            },
        })
    if Counter(item["split"] for item in frozen) != {"development": 16, "hidden": 16}:
        raise ValueError("P44 开发/隐藏状态数漂移")
    development_counts = Counter(
        item["family"] for item in frozen if item["split"] == "development"
    )
    if development_counts != {"peng": 13, "chi": 3}:
        raise ValueError("P44 开发动作家族分布漂移")
    source_ids = [item["source"]["source_id"] for item in frozen]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("P44 开发/隐藏来源必须全局独立")
    return frozen


def source_row(target: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(p43.source_path(str(target["source"]["source_id"])).read_text(encoding="utf-8"))


def exposure_row(target: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(p43.exposure_path(str(target["source"]["source_id"])).read_text(encoding="utf-8"))


def rollout_path(target: Mapping[str, Any], claim_index: int, rollout_index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-claim-{1:02d}-future-{2:02d}.json".format(
        target["target_id"], claim_index, rollout_index,
    ))


def source_paths() -> list[Path]:
    frozen = targets()
    development = [item for item in frozen if item["split"] == "development"]
    return [
        Path(__file__), Path(p43.__file__), P43_TARGETS, P43_RESULT, PARENT, CONTRACT,
        *[p43.source_path(str(item["source"]["source_id"])) for item in development],
        *[p43.exposure_path(str(item["source"]["source_id"])) for item in development],
    ]


def prepare() -> None:
    """在生成收益标签前冻结目标、共同未来墙、主统计层和通过门。"""

    if OUT.exists():
        raise SystemExit("P44目录已存在；拒绝覆盖")
    frozen = targets()
    development = [item for item in frozen if item["split"] == "development"]
    hidden = [item for item in frozen if item["split"] == "hidden"]
    sample_keys = [
        "r18-p44-piao-owner-claim-future-wall-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    claim_arms = sum(len(item["claim_actions"]) for item in development)
    planned_tables = claim_arms * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p44-piao-owner-claim-development-teacher-01",
        accounts={"tables_full": planned_tables},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P43通过圈主响应暴露门；只打开16个结果盲开发状态",
        "scope": (
            "16开发状态×每个合法吃碰×32共同未来牌墙×pass/claim；"
            "碰为主统计层，吃仅诊断，16隐藏状态不生成标签"
        ),
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p44-piao-owner-claim-targets/1",
        "targets": frozen,
        "hidden_labels_opened": False,
    })
    tracked = source_paths() + [_project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json")]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p44-piao-owner-claim-development-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "p43_targets_sha256": digest(P43_TARGETS),
        "p43_result_sha256": digest(P43_RESULT),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "parent_sha256": digest(PARENT),
        "contract_sha256": digest(CONTRACT),
        "development_states": len(development),
        "development_family_counts": dict(sorted(Counter(
            item["family"] for item in development
        ).items())),
        "hidden_states_kept_blind": len(hidden),
        "primary_family": PRIMARY_FAMILY,
        "diagnostic_families": ["chi"],
        "claim_arms": claim_arms,
        "rollouts_per_claim": len(sample_keys),
        "fit_indices": list(range(1, FIT_ROLLOUTS + 1)),
        "recheck_indices": list(range(FIT_ROLLOUTS + 1, ROLLOUTS_PER_STATE + 1)),
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "workers": WORKERS,
        "sampling_unit": "P43独立来源状态；共同未来墙与同状态多吃法不增加独立样本数",
        "sampling_scope": (
            "固定来源完整世界的四家暗手和已发生历史，只共同重排截取点之后的"
            "可摸牌墙；是定向可达条件教师，不是自然后验"
        ),
        "state_selection_rule": (
            "每状态只用前16未来墙，选claim_minus_pass均值最大的合法claim；"
            "最大值>0才选择claim，否则保持pass；后16只复查"
        ),
        "primary_label": "selected_claim_minus_pass_current_round_settlement",
        "gate": {
            "minimum_fit_selected_peng_states": MINIMUM_SELECTED_STATES,
            "minimum_recheck_positive_selected_fraction": MINIMUM_RECHECK_POSITIVE_FRACTION,
            "recheck_policy_bootstrap_95_lower_strictly_greater_than": 0.0,
            "minimum_leave_one_source_out_mean_strictly_greater_than": 0.0,
            "mechanical_success_required": True,
        },
        "hidden_labels_opened": False,
        "model_calls": 0,
        "selection_eligible": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "development_states": len(development),
        "hidden_states_kept_blind": len(hidden), "claim_arms": claim_arms,
        "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P43目标": (manifest["p43_targets_sha256"], digest(P43_TARGETS)),
        "P43结果": (manifest["p43_result_sha256"], digest(P43_RESULT)),
        "P44目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "P37父代": (manifest["parent_sha256"], digest(PARENT)),
        "评分合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    document = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))
    if document.get("hidden_labels_opened") is not False:
        raise ValueError("P44隐藏标签必须保持封存")
    frozen = list(document["targets"])
    if frozen != targets():
        raise ValueError("P44目标不能由P43结果盲切分重建")
    return manifest, frozen


def _rebuild_target_world(target: Mapping[str, Any]) -> tuple[SimulationEngine, Any]:
    """按 P43 冻结动作逐帧重放到目标响应边界。"""

    source = source_row(target)
    exposure = exposure_row(target)
    if exposure.get("status") != "hit" or exposure.get("target") is None:
        raise ValueError("P44来源不是P43命中状态")
    if exposure["target"]["request_sha256"] != target["request_sha256"]:
        raise ValueError("P44目标请求与P43暴露漂移")
    world_row = source["full_world"]
    engine = SimulationEngine(p43.p3.pilot.RULES, rules_hash=str(world_row["rules_hash"]))
    world = engine.from_replay(world_row)
    prefix_by_window = {
        window_key_from_json(item["window_key"]): str(item["action_key"])
        for item in exposure["target"]["prefix"]
    }
    target_window = window_key_from_json(target["window_key"])
    used = set()
    for _ in range(100_000):
        frame = engine.frame(world)
        if frame.final_scores is not None or frame.blocked_reason is not None:
            raise RuntimeError("P44重放在目标前终止")
        target_decision = next(
            (decision for decision in frame.decisions if decision.window_key == target_window),
            None,
        )
        if target_decision is not None:
            analysis = p43.p3.pilot.RULES.analyze(
                target_decision.observation, value_limits=p43.LIMITS,
            )
            request = opportunities.real_window_request(
                decision=target_decision, analysis=analysis,
                match_id=str(world_row["initial"]["world_payload"]["match_id"]),
                config=p43.p3.pilot.driver_config(), now_monotonic=lambda: 800.0,
            )
            if value_digest(decision_request_to_json(request)) != target["request_sha256"]:
                raise RuntimeError("P44重建目标请求摘要不一致")
            if used != set(prefix_by_window):
                raise RuntimeError("P44到达目标时没有消费全部冻结前缀")
            return engine, world
        choices = []
        for decision in frame.decisions:
            if decision.window_key not in prefix_by_window:
                raise RuntimeError("P44重放遇到冻结前缀外窗口：" + repr(decision.window_key))
            analysis = p43.p3.pilot.RULES.analyze(
                decision.observation, value_limits=p43.LIMITS,
            )
            planned_key = prefix_by_window[decision.window_key]
            candidate = next(
                (item for item in analysis.legal_candidates if item.action_key == planned_key),
                None,
            )
            if candidate is None:
                raise RuntimeError("P44冻结前缀动作不再合法：" + planned_key)
            choices.append(SimulationChoice(decision.window_key, candidate.action))
            used.add(decision.window_key)
        world = engine.advance(world, frame.revision, tuple(choices))
    raise RuntimeError("P44重放超过步数上限")


async def _run_arm(
    target: Mapping[str, Any], world: Any, forced_action: str, label: str,
) -> dict[str, Any]:
    engine = SimulationEngine(p43.p3.pilot.RULES, rules_hash=world.rules_hash)
    policies: list[Any] = [
        ComparableHeuristicPolicyV2(monotonic=lambda: 800.0) for _ in range(4)
    ]
    focal = int(target["focal_physical_seat"])
    parent = ActionValuePolicy(ActionValueScorer(
        "r18-p44-parent-" + label, PARENT.read_text(encoding="utf-8"),
    ))
    force = ForceFirstActionPolicy(
        parent, target_window=window_key_from_json(target["window_key"]),
        forced_action_key=forced_action, policy_id="r18-p44-force-" + label,
    )
    policies[focal] = force
    frame = engine.frame(world)
    outcome = await resume_match(
        engine=engine, world=world, policies_by_seat=tuple(policies),
        rules=p43.p3.pilot.RULES, choice_factory=SimulationChoice,
        config=p43.p3.pilot.driver_config(), now_monotonic=lambda: 800.0,
        wall_clock=None, remaining_schedule={"declared_endpoint": "hand_complete"},
        stage_snapshot={
            "observation_summary": frame_observation_summary(frame),
            "match_spec": {"match_id": world.match_id},
        },
        value_limits=p43.LIMITS,
    )
    scores = None if outcome.final_scores is None else list(outcome.final_scores)
    return {
        "status": outcome.status,
        "error_reason": outcome.error_reason,
        "blocked_reason": outcome.blocked_reason,
        "force_count": force.force_count,
        "final_scores": scores,
        "focal_score": None if scores is None else scores[focal],
        "completed_hands": outcome.completed_hands,
        "steps": outcome.steps,
        "decisions": len(outcome.decisions),
        "runtime_counts": asdict(outcome.runtime_counts),
    }


def execute_rollout(
    target: Mapping[str, Any], claim_index: int, rollout_index: int, sample_key: str,
) -> dict[str, Any]:
    """在同一重排未来墙下执行 pass 与一个合法 claim。"""

    claim_action = str(target["claim_actions"][claim_index - 1])
    engine, world = _rebuild_target_world(target)
    sampled = engine.resample_future_drawable_wall(world, sample_key=sample_key)
    sampled = replace(sampled, history_consistent=False)
    pass_arm = asyncio.run(_run_arm(
        target, sampled, "pass",
        "{0}-pass-{1:02d}-{2:02d}".format(target["target_id"], claim_index, rollout_index),
    ))
    claim_arm = asyncio.run(_run_arm(
        target, sampled, claim_action,
        "{0}-claim-{1:02d}-{2:02d}".format(target["target_id"], claim_index, rollout_index),
    ))
    mechanical = bool(
        pass_arm["status"] == "complete" and claim_arm["status"] == "complete"
        and pass_arm["focal_score"] is not None and claim_arm["focal_score"] is not None
        and pass_arm["force_count"] == 1 and claim_arm["force_count"] == 1
    )
    return {
        "schema": "r18-p44-piao-owner-claim-development-rollout/1",
        "target_id": target["target_id"],
        "source_id": target["source"]["source_id"],
        "family": target["family"],
        "claim_index": claim_index,
        "claim_action": claim_action,
        "rollout_index": rollout_index,
        "sample_key": sample_key,
        "pass": pass_arm,
        "claim": claim_arm,
        "claim_minus_pass_current_round_settlement": (
            None if not mechanical else
            int(claim_arm["focal_score"]) - int(pass_arm["focal_score"])
        ),
        "sampling_scope": "source hidden hands fixed; common future drawable wall only",
        "mechanical_ok": mechanical,
    }


def run() -> None:
    """并行执行开发状态的所有 claim/pass 共同未来牌墙配对。"""

    manifest, frozen = verify()
    development = [item for item in frozen if item["split"] == "development"]
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for target in development:
        for claim_index, _claim in enumerate(target["claim_actions"], 1):
            for rollout_index, sample_key in enumerate(manifest["sample_keys"], 1):
                path = rollout_path(target, claim_index, rollout_index)
                if path.exists():
                    row = json.loads(path.read_text(encoding="utf-8"))
                    if not row.get("mechanical_ok"):
                        raise ValueError("既有P44配对机械失败：" + str(path))
                    completed_tables += 2
                else:
                    pending.append((target, claim_index, rollout_index, sample_key))
    reservation = ledger.reserve(
        step_id="r18:p44-piao-owner-claim:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="16开发状态的每个吃碰×32共同未来墙×pass/claim",
    )
    executed_tables = 0
    failures = []
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=manifest["workers"]) as pool:
            futures = {
                pool.submit(execute_rollout, *item): item[:3] for item in pending
            }
            for future in concurrent.futures.as_completed(futures):
                target, claim_index, rollout_index = futures[future]
                try:
                    row = future.result()
                    if not row["mechanical_ok"]:
                        raise RuntimeError("P44双臂机械条件失败")
                    write_json(rollout_path(target, claim_index, rollout_index), row)
                    executed_tables += 2
                except Exception as exc:  # noqa: BLE001
                    failures.append({
                        "target_id": target["target_id"],
                        "claim_index": claim_index,
                        "rollout_index": rollout_index,
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        ledger.settle(reservation, actual=executed_tables, note="按完成的双臂桌数计")
    complete = completed_tables + executed_tables
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p44-run-summary/1",
        "planned_tables": manifest["planned_tables"],
        "completed_tables": complete,
        "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or complete != manifest["planned_tables"]:
        raise RuntimeError("P44开发教师执行不完整")
    print(json.dumps({
        "status": "RUN_COMPLETE", "tables": complete, "failures": len(failures),
    }, ensure_ascii=False))


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    rng = random.Random(BOOTSTRAP_SEED)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(statistics.fmean(values[rng.randrange(len(values))] for _ in values))
    means.sort()
    return (
        means[math.floor(0.025 * (len(means) - 1))],
        means[math.ceil(0.975 * (len(means) - 1))],
    )


def analyze() -> None:
    manifest, frozen = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["completed_tables"] != manifest["planned_tables"]:
        raise ValueError("P44执行不完整")
    development = [item for item in frozen if item["split"] == "development"]
    states = []
    all_mechanical = True
    for target in development:
        arms = []
        for claim_index, claim_action in enumerate(target["claim_actions"], 1):
            rows = [
                json.loads(rollout_path(target, claim_index, index).read_text(encoding="utf-8"))
                for index in range(1, ROLLOUTS_PER_STATE + 1)
            ]
            mechanical = all(row["mechanical_ok"] for row in rows)
            all_mechanical = all_mechanical and mechanical
            values = [float(row["claim_minus_pass_current_round_settlement"]) for row in rows]
            arms.append({
                "claim_action": claim_action,
                "mechanical_ok": mechanical,
                "fit_values": values[:FIT_ROLLOUTS],
                "recheck_values": values[FIT_ROLLOUTS:],
                "fit_mean_claim_minus_pass": statistics.fmean(values[:FIT_ROLLOUTS]),
                "recheck_mean_claim_minus_pass": statistics.fmean(values[FIT_ROLLOUTS:]),
            })
        selected_arm = min(
            arms,
            key=lambda arm: (-arm["fit_mean_claim_minus_pass"], arm["claim_action"]),
        )
        selected = selected_arm["fit_mean_claim_minus_pass"] > 0
        states.append({
            "target_id": target["target_id"],
            "family": target["family"],
            "source": target["source"],
            "features": target["features"],
            "reference_action": "pass",
            "arms": arms,
            "selected_action": selected_arm["claim_action"] if selected else "pass",
            "fit_selected_claim": selected,
            "selected_fit_mean_claim_minus_pass": (
                selected_arm["fit_mean_claim_minus_pass"] if selected else 0.0
            ),
            "selected_recheck_mean_claim_minus_pass": (
                selected_arm["recheck_mean_claim_minus_pass"] if selected else 0.0
            ),
            "recheck_positive": bool(
                selected and selected_arm["recheck_mean_claim_minus_pass"] > 0
            ),
            "mechanical_ok": all(arm["mechanical_ok"] for arm in arms),
        })
    primary = [state for state in states if state["family"] == PRIMARY_FAMILY]
    selected = [state for state in primary if state["fit_selected_claim"]]
    policy_values = [state["selected_recheck_mean_claim_minus_pass"] for state in primary]
    low, high = bootstrap_interval(policy_values)
    positive_selected = sum(state["recheck_positive"] for state in selected)
    required_positive = math.ceil(MINIMUM_RECHECK_POSITIVE_FRACTION * len(selected))
    leave_one_out = {}
    for state in primary:
        source_id = str(state["source"]["source_id"])
        remaining = [
            value for other, value in zip(primary, policy_values)
            if other["source"]["source_id"] != source_id
        ]
        leave_one_out[source_id] = statistics.fmean(remaining)
    minimum_loo = min(leave_one_out.values())
    gate = bool(
        all_mechanical
        and len(selected) >= MINIMUM_SELECTED_STATES
        and positive_selected >= required_positive
        and low > 0
        and minimum_loo > 0
    )
    by_family = {}
    for family in ("chi", "peng"):
        rows = [state for state in states if state["family"] == family]
        chosen = [state for state in rows if state["fit_selected_claim"]]
        by_family[family] = {
            "role": "primary" if family == PRIMARY_FAMILY else "diagnostic_only",
            "independent_states": len(rows),
            "fit_selected_claim_states": len(chosen),
            "recheck_positive_selected_states": sum(state["recheck_positive"] for state in chosen),
            "recheck_policy_mean": statistics.fmean(
                state["selected_recheck_mean_claim_minus_pass"] for state in rows
            ),
        }
    result = {
        "schema": "r18-p44-piao-owner-claim-development-result/1",
        "status": "COMPLETE_P44_PIAO_OWNER_CLAIM_DEVELOPMENT_TEACHER",
        "mechanical_ok": all_mechanical,
        "development_states": len(states),
        "claim_arms": manifest["claim_arms"],
        "rollouts": manifest["claim_arms"] * ROLLOUTS_PER_STATE,
        "tables": manifest["planned_tables"],
        "states": states,
        "primary_family": PRIMARY_FAMILY,
        "aggregate": {
            "independent_primary_states": len(primary),
            "fit_selected_claim_states": len(selected),
            "recheck_positive_selected_states": positive_selected,
            "required_recheck_positive_selected_states": required_positive,
            "recheck_policy_mean": statistics.fmean(policy_values),
            "recheck_policy_bootstrap_95": [low, high],
            "leave_one_source_out_mean": leave_one_out,
            "minimum_leave_one_source_out_mean": minimum_loo,
        },
        "by_family": by_family,
        "gate_passed": gate,
        "decision": "OPEN_P45_LIMITED_AUTHOR" if gate else "CLOSE_PIAO_OWNER_CLAIM_AXIS",
        "sampling_scope": manifest["sampling_scope"],
        "hidden_states_kept_blind": manifest["hidden_states_kept_blind"],
        "hidden_labels_opened": False,
        "next": (
            "只用碰开发标签与公开事实调用一次受限作者；候选冻结后才打开隐藏标签"
            if gate else
            "保持P37并关闭本轴；不得打开隐藏标签后补阈值"
        ),
        "selection_eligible": True,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], "mechanical_ok": all_mechanical,
        "aggregate": result["aggregate"], "by_family": by_family,
        "gate_passed": gate, "decision": result["decision"],
        "hidden_labels_opened": False,
    }, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "run", "analyze"))
    command = parser.parse_args().command
    if command == "prepare":
        prepare()
    elif command == "run":
        run()
    else:
        analyze()


if __name__ == "__main__":
    main()
