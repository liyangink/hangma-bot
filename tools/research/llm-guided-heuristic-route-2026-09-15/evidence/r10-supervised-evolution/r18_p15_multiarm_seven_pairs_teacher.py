"""R18 P15：七对开发状态的结果盲非支配多臂教师。"""

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
from collections import Counter, defaultdict
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
import r18_p11_settlement_cascade_teacher as p11  # noqa: E402
import r18_p12_natural_seven_pairs_frontier as p12  # noqa: E402
import r18_p13_development_seven_pairs_teacher as p13  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p15-multiarm-seven-pairs-teacher-01-20260922')
FRONTIER = p12.OUT / "frozen-frontier.json"
CONTRACT = p12.CONTRACT
PARENT = p12.PARENT
LIMITS = p12.LIMITS
ROLLOUTS_PER_ACTION = 32
FIT_ROLLOUTS = 16
BOOTSTRAP_REPLICATES = 20_000
WORKERS = 8


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _vector(action: Mapping[str, Any]) -> tuple[int, int, int, int]:
    """全部转为越小越优的普通型/七对路线向量。"""

    return (
        int(action["standard_shanten_after"]),
        -int(action["standard_support_remaining"]),
        int(action["seven_pairs_shanten_after"]),
        -int(action["seven_pairs_support_remaining"]),
    )


def dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    a = _vector(left)
    b = _vector(right)
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def nondominated(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """结果盲保留四维非支配七对替代动作。"""

    unique = {str(action["action_key"]): action for action in actions}
    rows = list(unique.values())
    result = [
        action for action in rows
        if not any(dominates(other, action) for other in rows if other is not action)
    ]
    return sorted(result, key=lambda action: (_vector(action), str(action["action_key"])))


def targets() -> list[dict[str, Any]]:
    document = json.loads(FRONTIER.read_text(encoding="utf-8"))
    if document.get("hidden_labels_opened") is not False:
        raise ValueError("P12 hidden 必须仍未打开")
    rows = document.get("development") or []
    p13_by_hash = {row["request_sha256"]: row for row in p13.targets()}
    result = []
    for state_index, row in enumerate(rows, 1):
        request = row["request"]
        observation = request["observation"]
        base = p13_by_hash.get(row["request_sha256"])
        if base is None:
            raise ValueError("P15 状态缺 P13 精确快照身份")
        alternatives = nondominated(list(row["eligible_alternatives"]))
        for arm_index, alternative in enumerate(alternatives, 1):
            if alternative["action_key"] == row["parent"]["action_key"]:
                raise ValueError("替代动作不得等于 P5 原动作")
            result.append({
                "target_id": "r18-p15-state-{0:02d}-arm-{1:02d}".format(
                    state_index, arm_index,
                ),
                "state_id": "r18-p15-state-{0:02d}".format(state_index),
                "p13_target_id": base["target_id"],
                "source": dict(base["source"]),
                "window_key": request["window_key"],
                "focal_physical_seat": int(observation["seat"]),
                "request_sha256": row["request_sha256"],
                "state_projection_sha256": p13.value_digest(p13.state_projection(request)),
                "reference_action": row["parent"]["action_key"],
                "intervention_action": alternative["action_key"],
                "features": {
                    "round_no": row["round_no"], "dealer": row["dealer"],
                    "remaining_tile_count": row["remaining_tile_count"],
                    "wealth_count": row["wealth_count"], "pair_kinds": row["pair_kinds"],
                    "triplet_kinds": row["triplet_kinds"],
                    "parent": row["parent"], "intervention": alternative,
                    "nondominated_alternatives": len(alternatives),
                },
            })
    if len(result) != 50:
        raise ValueError("P15 预期 50 个非支配替代动作，实际 {0}".format(len(result)))
    return result


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return p13.OUT / "snapshots" / (str(target["p13_target_id"]) + ".json")


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-hidden-{1:02d}.json".format(
        target["target_id"], index,
    ))


def prepare() -> None:
    """在运行前冻结动作前沿、拟合/复现样本键和生存门。"""

    if OUT.exists():
        raise SystemExit("P15 目录已存在；拒绝覆盖")
    frozen = targets()
    sample_keys = [
        "r18-p15-multiarm-hidden-world-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_ACTION + 1)
    ]
    planned_tables = len(frozen) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name, authorization_id="r18-p15-multiarm-seven-pairs-teacher-01",
        accounts={"tables_full": planned_tables}, issued_by="lead",
        issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P14关闭单一阈值；需验证结果盲多动作空间是否存在可学习正价值",
        "scope": "28个P12开发状态、50个非支配替代动作、每动作32共同隐藏世界；hidden不运行",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p15-multiarm-targets/1", "targets": frozen,
    })
    snapshot_paths = sorted({snapshot_path(row) for row in frozen})
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p15-multiarm-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=[
            Path(__file__), Path(p12.__file__), Path(p13.__file__), FRONTIER,
            CONTRACT, PARENT, p13.OUT / "manifest.json", p13.OUT / "targets.json",
            p13.OUT / "capture-summary.json", *snapshot_paths,
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "frontier_sha256": digest(FRONTIER),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "p13_manifest_sha256": digest(p13.OUT / "manifest.json"),
        "base_states": len({row["state_id"] for row in frozen}),
        "action_pairs": len(frozen),
        "rollouts_per_action": len(sample_keys),
        "fit_indices": list(range(1, FIT_ROLLOUTS + 1)),
        "replication_indices": list(range(FIT_ROLLOUTS + 1, len(sample_keys) + 1)),
        "sample_keys": sample_keys, "planned_tables": planned_tables,
        "workers": WORKERS,
        "action_freeze": "P12 eligible_alternatives 按普通型向听/支持和七对向听/支持四维去支配；不看P13/P14结果",
        "selection_rule": "每状态仅用fit半区选均值最高且>0的替代动作，否则选P5；replication半区只验证",
        "viability_rule": {
            "minimum_non_reference_states": 8,
            "minimum_positive_selected_fraction": "2/3",
            "replication_bootstrap_95_all_state_mean_lower": 0.0,
        },
        "hidden_labels_opened": False, "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "base_states": 28, "action_pairs": len(frozen),
        "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    if manifest["frontier_sha256"] != digest(FRONTIER):
        raise ValueError("P12冻结前沿漂移")
    if manifest["targets_sha256"] != digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")):
        raise ValueError("P15目标漂移")
    if manifest["p13_manifest_sha256"] != digest(p13.OUT / "manifest.json"):
        raise ValueError("P13快照合同漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["targets"]
    if frozen != targets():
        raise ValueError("P15目标不可重建")
    for target in frozen:
        snapshot = json.loads(snapshot_path(target).read_text(encoding="utf-8"))
        legal = set(snapshot["capture"]["witness"]["legal_action_keys"])
        if target["intervention_action"] not in legal:
            raise ValueError("P15替代动作不在捕获快照合法动作中")
    return manifest, frozen


def execute_rollout(target: Mapping[str, Any], index: int, sample_key: str) -> dict[str, Any]:
    snapshot = json.loads(snapshot_path(target).read_text(encoding="utf-8"))
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    rules = HangmaRules(p13.core.rule_config_from_contract(contract))
    base_runtime = opportunities.build_real_runtime(
        rules_config=rules.config,
        rounds_per_game=int(snapshot["match_spec"]["rounds_per_game"]),
        seed=int(snapshot["match_spec"]["seed"]),
        scenario_id=str(snapshot["match_spec"]["scenario_id"]),
    )
    settlement = p11.SettlementCaptureEngine(base_runtime["engine"])
    runtime = dict(base_runtime)
    runtime["engine"] = settlement
    reference_policies, reference_force = p13.policies_for_arm(
        target=target, snapshot=snapshot,
        forced_action_key=str(target["reference_action"]),
        label="p15-reference-{0}-{1:02d}".format(target["target_id"], index),
    )
    intervention_policies, intervention_force = p13.policies_for_arm(
        target=target, snapshot=snapshot,
        forced_action_key=str(target["intervention_action"]),
        label="p15-intervention-{0}-{1:02d}".format(target["target_id"], index),
    )
    double = opportunities.run_double_arm(
        rules=rules, snapshot=snapshot,
        baseline_policies_by_seat=reference_policies,
        candidate_policies_by_seat=intervention_policies,
        config=opportunities._driver_config(), value_limits=LIMITS, runtime=runtime,
        current_world_transform=lambda world: settlement.resample_public_consistent_hidden_world(
            world, focal_seat=int(target["focal_physical_seat"]), sample_key=sample_key,
        ),
    )
    records = [
        record for record in settlement.records
        if record.round_no == int(target["features"]["round_no"])
    ]
    if len(records) != 2:
        raise RuntimeError("目标局结算记录必须为两条")
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
    reference["terminal"] = p13.terminal(reference_record, focal)
    intervention["terminal"] = p13.terminal(intervention_record, focal)
    reference["focal_settlement"] = int(reference_record.score_delta[focal])
    intervention["focal_settlement"] = int(intervention_record.score_delta[focal])
    return {
        "schema": "r18-p15-multiarm-rollout/1",
        "target_id": target["target_id"], "state_id": target["state_id"],
        "rollout_index": index,
        "sample_split": "fit" if index <= FIT_ROLLOUTS else "replication",
        "sample_key": sample_key, "reference_action": target["reference_action"],
        "intervention_action": target["intervention_action"],
        "actual_actions": actions,
        "reference": reference, "intervention": intervention,
        "focal_current_round_settlement_delta": (
            intervention["focal_settlement"] - reference["focal_settlement"]
        ),
        "focal_remaining_table_score_delta": int(intervention_score) - int(reference_score),
        "reference_remaining_table_score": reference_score,
        "intervention_remaining_table_score": intervention_score,
        "mechanical_ok": mechanical,
    }


def run() -> None:
    manifest, frozen = verify()
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
                    raise ValueError("既有P15配对机械条件失败")
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p15-multiarm:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="50非支配替代动作×32共同隐藏世界×两臂",
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
                        raise RuntimeError("P15配对机械条件失败")
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
        "schema": "r18-p15-run-summary/1", "rollout_files": len(files),
        "actual_tables": len(files) * 2, "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P15多臂教师执行不完整")


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    rng = random.Random(202609222315)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(statistics.fmean(values[rng.randrange(len(values))] for _ in values))
    means.sort()
    return (
        means[math.floor(0.025 * (len(means) - 1))],
        means[math.ceil(0.975 * (len(means) - 1))],
    )


def analyze() -> None:
    """拟合半区选动作，复现半区只验证，不反向修改选择。"""

    manifest, frozen = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P15多臂教师执行不完整")
    action_rows = []
    reference_witnesses: dict[tuple[str, int], set[str]] = defaultdict(set)
    for target in frozen:
        rows = [
            json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, ROLLOUTS_PER_ACTION + 1)
        ]
        for row in rows:
            witness = json.dumps({
                "record": row["reference"],
                "score": row["reference_remaining_table_score"],
            }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            reference_witnesses[(target["state_id"], row["rollout_index"])].add(witness)
        fit = rows[:FIT_ROLLOUTS]
        replication = rows[FIT_ROLLOUTS:]
        fit_direct = [row["focal_current_round_settlement_delta"] for row in fit]
        replication_direct = [row["focal_current_round_settlement_delta"] for row in replication]
        action_rows.append({
            "target_id": target["target_id"], "state_id": target["state_id"],
            "source": target["source"], "features": target["features"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "fit": {
                "mean_current_round_settlement_delta": statistics.fmean(fit_direct),
                "mean_remaining_table_score_delta": statistics.fmean(
                    row["focal_remaining_table_score_delta"] for row in fit
                ),
                "focal_hu_delta": sum(row["intervention"]["terminal"] == "focal_hu" for row in fit)
                - sum(row["reference"]["terminal"] == "focal_hu" for row in fit),
            },
            "replication": {
                "mean_current_round_settlement_delta": statistics.fmean(replication_direct),
                "mean_remaining_table_score_delta": statistics.fmean(
                    row["focal_remaining_table_score_delta"] for row in replication
                ),
                "focal_hu_delta": sum(row["intervention"]["terminal"] == "focal_hu" for row in replication)
                - sum(row["reference"]["terminal"] == "focal_hu" for row in replication),
            },
            "direction_stable_positive": (
                statistics.fmean(fit_direct) > 0.0
                and statistics.fmean(replication_direct) > 0.0
            ),
        })
    inconsistent_reference = [
        {"state_id": state_id, "rollout_index": index, "variants": len(values)}
        for (state_id, index), values in sorted(reference_witnesses.items())
        if len(values) != 1
    ]
    by_state: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in action_rows:
        by_state[row["state_id"]].append(row)
    selections = []
    for state_id, rows in sorted(by_state.items()):
        ranked = sorted(rows, key=lambda row: (
            -float(row["fit"]["mean_current_round_settlement_delta"]),
            str(row["intervention_action"]),
        ))
        best = ranked[0]
        selected = best if best["fit"]["mean_current_round_settlement_delta"] > 0.0 else None
        selections.append({
            "state_id": state_id,
            "selected_action": None if selected is None else selected["intervention_action"],
            "fit_mean": 0.0 if selected is None else selected["fit"]["mean_current_round_settlement_delta"],
            "replication_mean": 0.0 if selected is None else selected["replication"]["mean_current_round_settlement_delta"],
            "replication_full_table_mean": 0.0 if selected is None else selected["replication"]["mean_remaining_table_score_delta"],
            "selected_non_reference": selected is not None,
            "replication_positive": selected is not None and selected["replication"]["mean_current_round_settlement_delta"] > 0.0,
            "stable_positive_actions": sum(row["direction_stable_positive"] for row in rows),
            "available_actions": len(rows),
        })
    selected = [row for row in selections if row["selected_non_reference"]]
    replication_all = [row["replication_mean"] for row in selections]
    lo, hi = bootstrap_interval(replication_all)
    required_positive = math.ceil(2 * len(selected) / 3) if selected else 0
    viable = bool(
        not inconsistent_reference
        and len(selected) >= 8
        and sum(row["replication_positive"] for row in selected) >= required_positive
        and lo >= 0.0
    )
    result = {
        "schema": "r18-p15-multiarm-result/1",
        "status": "COMPLETE_P15_MULTIARM_SEVEN_PAIRS_TEACHER",
        "mechanical_ok": not inconsistent_reference,
        "base_states": len(by_state), "action_pairs": len(action_rows),
        "rollouts": len(action_rows) * ROLLOUTS_PER_ACTION,
        "tables": len(action_rows) * ROLLOUTS_PER_ACTION * 2,
        "actions": action_rows, "fit_selected_replication": selections,
        "aggregate": {
            "reference_consistency_failures": inconsistent_reference,
            "direction_stable_positive_action_pairs": sum(
                row["direction_stable_positive"] for row in action_rows
            ),
            "states_with_stable_positive_action": sum(
                row["stable_positive_actions"] > 0 for row in selections
            ),
            "fit_selected_non_reference_states": len(selected),
            "replication_positive_selected_states": sum(
                row["replication_positive"] for row in selected
            ),
            "required_replication_positive_selected_states": required_positive,
            "replication_all_state_mean": statistics.fmean(replication_all),
            "replication_all_state_bootstrap_95": [lo, hi],
            "replication_selected_full_table_mean": (
                statistics.fmean(row["replication_full_table_mean"] for row in selected)
                if selected else 0.0
            ),
        },
        "action_space_viable": viable,
        "decision": (
            "FIT_OBSERVABLE_MULTIARM_SCORER" if viable
            else "CLOSE_CURRENT_SEVEN_PAIRS_ACTION_SPACE"
        ),
        "next_gate": (
            "只用fit标签和公开特征拟合评分器；replication标签继续作为内部验证，候选冻结后才打开P12 hidden"
            if viable else
            "保留P5并转向新的七对动作表示或其他机会家族；不得打开P12 hidden"
        ),
        "hidden_labels_opened": False, "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], "mechanical_ok": result["mechanical_ok"],
        "aggregate": result["aggregate"],
        "action_space_viable": viable, "decision": result["decision"],
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
