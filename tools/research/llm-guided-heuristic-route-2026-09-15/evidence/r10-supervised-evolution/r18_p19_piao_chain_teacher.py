"""R18 P19：圈主首次再摸时“立即胡 vs 续飘白”的共同隐藏世界教师。

P18 已从首次飘白被独立证明为正的 P3 可达中局中冻结 20 个开发状态和
9 个隐藏状态。本阶段只打开开发状态，每状态使用 32 个公开状态一致隐藏
世界；前 16 个用于选择，后 16 个只用于复现。两臂在目标窗口分别强制
P5 的 ``hu`` 与 ``discard:白``，随后都恢复 P5。
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
from dataclasses import asdict
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
import r18_p3_reachable_midgame as p3  # noqa: E402
import r18_p16_catch_play_natural_exposure as p16  # noqa: E402
import r18_p18_piao_chain_exposure as p18  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.application.audit_codec import decision_request_to_json  # noqa: E402
from hangma_bot.kernel.serialization import (  # noqa: E402
    window_key_from_json,
    window_key_to_json,
)
from hangma_bot.offline.evaluate import frame_observation_summary, resume_match  # noqa: E402
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402
from hangma_bot.policy.heuristic_v2 import ComparableHeuristicPolicyV2  # noqa: E402
from hangma_bot.simulation import SimulationChoice, SimulationEngine  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p19-piao-chain-teacher-01-20260922')
P18_TARGETS = p18.OUT / "targets.json"
P18_RESULT = p18.OUT / "result.json"
PARENT = p16.PARENT
CONTRACT = p16.CONTRACT
LIMITS = p16.LIMITS
ROLLOUTS_PER_STATE = 32
FIT_ROLLOUTS = 16
WORKERS = 8
BOOTSTRAP_REPLICATES = 20_000


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


def source_case(case_id: str) -> dict[str, Any]:
    rows = json.loads((p3.OUT / "bank.json").read_text(encoding="utf-8"))["cases"]
    return next(row for row in rows if row["case_id"] == case_id)


def frozen_targets() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    result = json.loads(P18_RESULT.read_text(encoding="utf-8"))
    if result.get("passes_exposure_gate") is not True:
        raise ValueError("P18续飘链必须先通过自然可达门")
    document = json.loads(P18_TARGETS.read_text(encoding="utf-8"))
    if document.get("hidden_labels_opened") is not False:
        raise ValueError("P18 hidden 标签必须仍封存")
    development = list(document.get("development") or [])
    hidden = list(document.get("hidden") or [])
    if len(development) != 20 or len(hidden) != 9:
        raise ValueError("P19要求P18冻结20开发/9隐藏状态")
    if any(row["reference_action"] != "hu" for row in development):
        raise ValueError("P19开发集参考动作必须全部为hu")
    if any(row["renew_action"] != "discard:白" for row in development):
        raise ValueError("P19干预动作必须全部为discard:白")
    return development, hidden


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-hidden-{1:02d}.json".format(
        target["source"]["case_id"], index,
    ))


def prepare() -> None:
    """冻结开发/隐藏身份、共同隐藏世界和通过门。"""

    if OUT.exists():
        raise SystemExit("P19目录已存在；拒绝覆盖")
    development, hidden = frozen_targets()
    sample_keys = [
        "r18-p19-piao-chain-hidden-world-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(development) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p19-piao-chain-teacher-01",
        accounts={"tables_full": planned_tables},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P18冻结29个独立续飘链状态并通过24状态门",
        "scope": "20开发状态×32共同隐藏世界×立即胡/续飘白；9 hidden不运行",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p19-piao-chain-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=[
            Path(__file__), P18_TARGETS, P18_RESULT, PARENT, CONTRACT,
            p3.OUT / "bank.json", Path(p3.__file__), Path(p18.__file__),
            Path(opportunities.__file__), _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
        ]),
        "p18_targets_sha256": digest(P18_TARGETS),
        "p18_result_sha256": digest(P18_RESULT),
        "parent_sha256": digest(PARENT),
        "contract_sha256": digest(CONTRACT),
        "development_states": len(development),
        "hidden_states": len(hidden),
        "rollouts_per_state": len(sample_keys),
        "fit_indices": list(range(1, FIT_ROLLOUTS + 1)),
        "replication_indices": list(range(FIT_ROLLOUTS + 1, len(sample_keys) + 1)),
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "workers": WORKERS,
        "selection_rule": "每状态仅用fit半区；续飘均值>0才选择，否则回退P5立即胡",
        "primary_label": "focal_hand_score_delta",
        "gate": {
            "minimum_fit_selected_renew_states": 5,
            "minimum_replication_positive_fraction": "2/3",
            "replication_all_state_bootstrap_95_lower": 0.0,
            "minimum_leave_one_source_case_out_mean": 0.0,
        },
        "sampling_scope": "公开状态一致对手暗牌与未消费牌墙；不是历史动作条件后验",
        "hidden_labels_opened": False,
        "development_labels_selection_eligible": True,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "development": len(development),
        "hidden": len(hidden), "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P18目标": (manifest["p18_targets_sha256"], digest(P18_TARGETS)),
        "P18结果": (manifest["p18_result_sha256"], digest(P18_RESULT)),
        "P5父代": (manifest["parent_sha256"], digest(PARENT)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    development, _ = frozen_targets()
    return manifest, development


def rebuild_cut(target: Mapping[str, Any]) -> tuple[SimulationEngine, Any, Any]:
    """从 P3 完整世界按 P18 冻结合法动作前缀重建目标窗口。"""

    case = source_case(str(target["source"]["case_id"]))
    world_row = case["full_world"]
    engine = SimulationEngine(p3.pilot.RULES, rules_hash=str(world_row["rules_hash"]))
    world = engine.from_replay(world_row)
    prefix = list(target["prefix"])
    offset = 0
    target_window = window_key_from_json(target["request"]["window_key"])
    for _ in range(100_000):
        frame = engine.frame(world)
        if offset == len(prefix):
            decision = next(
                (item for item in frame.decisions if item.window_key == target_window), None,
            )
            if decision is None:
                raise ValueError("P18目标窗口未在前缀末端重建")
            analysis = p3.pilot.RULES.analyze(decision.observation, value_limits=LIMITS)
            request = opportunities.real_window_request(
                decision=decision, analysis=analysis,
                match_id=str(world_row["initial"]["world_payload"]["match_id"]),
                config=p3.pilot.driver_config(), now_monotonic=lambda: 800.0,
            )
            request_json = decision_request_to_json(request)
            if value_digest(request_json) != target["request_sha256"]:
                raise ValueError("P18目标请求摘要漂移")
            return engine, world, frame
        if frame.final_scores is not None or frame.blocked_reason is not None:
            raise ValueError("前缀重建在目标窗口前结束")
        amount = len(frame.decisions)
        group = prefix[offset:offset + amount]
        if len(group) != amount:
            raise ValueError("P18冻结前缀在帧中间截断")
        by_window = {
            json.dumps(step["window_key"], sort_keys=True, ensure_ascii=False): step
            for step in group
        }
        choices = []
        for decision in frame.decisions:
            key = json.dumps(
                window_key_to_json(decision.window_key), sort_keys=True, ensure_ascii=False,
            )
            step = by_window.get(key)
            if step is None:
                raise ValueError("P18冻结前缀与重建帧窗口不一致")
            analysis = p3.pilot.RULES.analyze(decision.observation, value_limits=LIMITS)
            candidate = next(
                (item for item in analysis.legal_candidates
                 if item.action_key == step["action_key"]), None,
            )
            if candidate is None:
                raise ValueError("P18冻结前缀动作已不合法：" + str(step["action_key"]))
            choices.append(SimulationChoice(decision.window_key, candidate.action))
        world = engine.advance(world, frame.revision, tuple(choices))
        offset += amount
    raise RuntimeError("P19前缀重建超过步数上限")


async def run_arm(
    target: Mapping[str, Any], *, action: str, sample_key: str, label: str,
) -> dict[str, Any]:
    engine, world, _ = rebuild_cut(target)
    focal = int(target["request"]["observation"]["seat"])
    world = engine.resample_public_consistent_hidden_world(
        world, focal_seat=focal, sample_key=sample_key,
    )
    frame = engine.frame(world)
    policies: list[Any] = [
        ComparableHeuristicPolicyV2(monotonic=lambda: 800.0) for _ in range(4)
    ]
    delegate = ActionValuePolicy(ActionValueScorer(
        "r18-p19-p5-" + label, PARENT.read_text(encoding="utf-8"),
    ))
    forced = ForceFirstActionPolicy(
        delegate, target_window=window_key_from_json(target["request"]["window_key"]),
        forced_action_key=action, policy_id="r18-p19-" + label,
    )
    policies[focal] = forced
    outcome = await resume_match(
        engine=engine, world=world, policies_by_seat=tuple(policies),
        rules=p3.pilot.RULES, choice_factory=SimulationChoice,
        config=p3.pilot.driver_config(), now_monotonic=lambda: 800.0,
        wall_clock=None, remaining_schedule={"declared_endpoint": "hand_complete"},
        stage_snapshot={
            "observation_summary": frame_observation_summary(frame),
            "match_spec": {
                "match_id": source_case(str(target["source"]["case_id"]))[
                    "full_world"
                ]["initial"]["world_payload"]["match_id"],
            },
        },
        value_limits=LIMITS,
    )
    final_scores = None if outcome.final_scores is None else list(outcome.final_scores)
    return {
        "status": outcome.status,
        "completed_hands": outcome.completed_hands,
        "final_scores": final_scores,
        "focal_score": None if final_scores is None else final_scores[focal],
        "force_count": forced.force_count,
        "runtime_counts": asdict(outcome.runtime_counts),
        "error_reason": outcome.error_reason,
    }


def execute_rollout(target: Mapping[str, Any], index: int, sample_key: str) -> dict[str, Any]:
    reference = asyncio.run(run_arm(
        target, action=str(target["reference_action"]), sample_key=sample_key,
        label="reference-{0}-{1:02d}".format(target["source"]["case_id"], index),
    ))
    renew = asyncio.run(run_arm(
        target, action=str(target["renew_action"]), sample_key=sample_key,
        label="renew-{0}-{1:02d}".format(target["source"]["case_id"], index),
    ))
    mechanical = bool(
        reference["status"] == "complete" and renew["status"] == "complete"
        and reference["completed_hands"] == 1 and renew["completed_hands"] == 1
        and reference["force_count"] == 1 and renew["force_count"] == 1
        and reference["focal_score"] is not None and renew["focal_score"] is not None
        and all(value == 0 for value in reference["runtime_counts"].values())
        and all(value == 0 for value in renew["runtime_counts"].values())
    )
    return {
        "schema": "r18-p19-piao-chain-rollout/1",
        "case_id": target["source"]["case_id"],
        "rollout_index": index,
        "sample_split": "fit" if index <= FIT_ROLLOUTS else "replication",
        "sample_key": sample_key,
        "reference_action": target["reference_action"],
        "renew_action": target["renew_action"],
        "reference": reference,
        "renew": renew,
        "focal_hand_score_delta": int(renew["focal_score"] or 0) - int(reference["focal_score"] or 0),
        "mechanical_ok": mechanical,
    }


def run() -> None:
    manifest, development = verify()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for target in development:
        for index, key in enumerate(manifest["sample_keys"], 1):
            path = rollout_path(target, index)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if not row.get("mechanical_ok"):
                    raise ValueError("既有P19配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p19-piao-chain:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="20开发状态×32共同隐藏世界×立即胡/续飘白",
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
                        raise RuntimeError("P19共同隐藏世界配对机械条件失败")
                    write_json(rollout_path(target, index), row)
                    executed += 2
                    completed_tables += 2
                    if completed_tables % 128 == 0:
                        print(json.dumps({
                            "completed_tables": completed_tables,
                            "planned_tables": manifest["planned_tables"],
                        }, ensure_ascii=False), flush=True)
                except Exception as exc:  # noqa: BLE001
                    if row is None:
                        usage_unknown = True
                    failures.append({
                        "case_id": target["source"]["case_id"],
                        "rollout_index": index,
                        "error": type(exc).__name__ + ": " + str(exc),
                    })
    finally:
        if usage_unknown:
            ledger.settle(reservation, usage_unknown=True, note="子进程未返回；保守结算")
        else:
            ledger.settle(reservation, actual=executed, note="按成功两臂桌数结算")
    files = list((_project_file(_PROJECT_ROOT, OUT / "rollouts")).glob("*.json"))
    write_json(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "r18-p19-run-summary/1", "rollout_files": len(files),
        "actual_tables": len(files) * 2, "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P19续飘链教师执行不完整")


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    rng = random.Random(202609222319)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(statistics.fmean(values[rng.randrange(len(values))] for _ in values))
    means.sort()
    return (
        means[math.floor(0.025 * (len(means) - 1))],
        means[math.ceil(0.975 * (len(means) - 1))],
    )


def analyze() -> None:
    """拟合半区选续飘状态，复现半区按预登记门裁定作者资格。"""

    manifest, development = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P19执行不完整")
    states = []
    all_mechanical = True
    for target in development:
        rows = [
            json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, ROLLOUTS_PER_STATE + 1)
        ]
        all_mechanical = all_mechanical and all(row["mechanical_ok"] for row in rows)
        fit_values = [row["focal_hand_score_delta"] for row in rows[:FIT_ROLLOUTS]]
        replication_values = [row["focal_hand_score_delta"] for row in rows[FIT_ROLLOUTS:]]
        fit_mean = statistics.fmean(fit_values)
        replication_mean = statistics.fmean(replication_values)
        selected = fit_mean > 0.0
        states.append({
            "case_id": target["source"]["case_id"],
            "source": target["source"],
            "features": {
                "role": target["source"]["role"],
                "focal_seat": target["source"]["focal_seat"],
                "remaining_tile_count": target["remaining_tile_count"],
                "wealth_count": target["wealth_count"],
                "baotou": target["baotou"],
                "chain_count": target["chain_count"],
                "chain_piao": target["chain_piao"],
                "legal_action_keys": target["legal_action_keys"],
            },
            "reference_action": target["reference_action"],
            "renew_action": target["renew_action"],
            "selected_renew_from_fit": selected,
            "fit": {"mean": fit_mean, "values": fit_values},
            "replication": {
                "mean": replication_mean, "values": replication_values,
                "positive": selected and replication_mean > 0.0,
            },
            "policy_replication_value": replication_mean if selected else 0.0,
        })
    selected = [row for row in states if row["selected_renew_from_fit"]]
    policy_values = [row["policy_replication_value"] for row in states]
    lo, hi = bootstrap_interval(policy_values)
    required_positive = math.ceil(2 * len(selected) / 3) if selected else 0
    positive = sum(row["replication"]["positive"] for row in selected)
    leave_one_out = {
        row["case_id"]: statistics.fmean(
            other["policy_replication_value"]
            for other in states if other["case_id"] != row["case_id"]
        )
        for row in states
    }
    gate_passed = bool(
        all_mechanical and len(selected) >= 5 and positive >= required_positive
        and lo >= 0.0 and min(leave_one_out.values()) >= 0.0
    )
    result = {
        "schema": "r18-p19-piao-chain-result/1",
        "status": "COMPLETE_P19_PIAO_CHAIN_TEACHER",
        "mechanical_ok": all_mechanical,
        "development_states": len(states),
        "hidden_states_frozen_unopened": manifest["hidden_states"],
        "rollouts": len(states) * ROLLOUTS_PER_STATE,
        "tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "states": states,
        "aggregate": {
            "fit_selected_renew_states": len(selected),
            "replication_positive_selected_states": positive,
            "required_replication_positive_selected_states": required_positive,
            "replication_all_state_policy_mean": statistics.fmean(policy_values),
            "replication_all_state_policy_bootstrap_95": [lo, hi],
            "replication_selected_renew_mean": (
                statistics.fmean(row["replication"]["mean"] for row in selected)
                if selected else 0.0
            ),
            "leave_one_source_case_out_mean": leave_one_out,
            "minimum_leave_one_source_case_out_mean": min(leave_one_out.values()),
        },
        "gate_passed": gate_passed,
        "decision": "OPEN_P20_LIMITED_AUTHOR" if gate_passed else "CLOSE_SECOND_PIAO",
        "next_gate": (
            "只用开发fit标签和公开动作事实归纳续飘边界；候选冻结后才打开P18 hidden"
            if gate_passed else
            "保留P5立即胡；不得查看P18 hidden后补续飘阈值"
        ),
        "hidden_labels_opened": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], "mechanical_ok": all_mechanical,
        "aggregate": result["aggregate"], "gate_passed": gate_passed,
        "decision": result["decision"],
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
