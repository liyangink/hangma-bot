"""R18 P14：用未标注开发窗口确认七对/普通型双路线向听 Pareto 边界。"""

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
from collections import Counter
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


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p14-pareto-gate-confirmation-01-20260922')
DATASET = p12.OUT / "dataset.json"
FRONTIER = p12.OUT / "frozen-frontier.json"
CONTRACT = p12.CONTRACT
PARENT = p12.PARENT
LIMITS = p12.LIMITS
ROLLOUTS_PER_STATE = 32
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


def rank(row: Mapping[str, Any]) -> str:
    """结果盲固定每个来源内状态的选择顺序。"""

    return hashlib.sha256(
        ("r18-p14-pareto-confirm|" + str(row["source_id"]) + "|"
         + str(row["request_sha256"])).encode("utf-8")
    ).hexdigest()


def gate(row: Mapping[str, Any]) -> bool:
    """七对严格改善已由 P12 保证；这里只要求普通型向听数不增加。"""

    return bool(
        row["split"] == "development"
        and int(row["seven_pairs_frontier"]["standard_shanten_after"])
        <= int(row["parent"]["standard_shanten_after"])
    )


def targets() -> list[dict[str, Any]]:
    """排除 P13 状态后，每个满足边界的开发来源最多冻结一个状态。"""

    frozen = json.loads(FRONTIER.read_text(encoding="utf-8"))
    if frozen.get("hidden_labels_opened") is not False:
        raise ValueError("P12 hidden 必须仍未打开")
    used = {row["request_sha256"] for row in frozen["development"]}
    rows = json.loads(DATASET.read_text(encoding="utf-8"))["rows"]
    eligible = [row for row in rows if gate(row) and row["request_sha256"] not in used]
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in eligible:
        by_source.setdefault(str(row["source_id"]), []).append(row)
    selected = [sorted(items, key=rank)[0] for _, items in sorted(by_source.items())]
    if len(selected) < 10:
        raise ValueError("P14 独立状态不足预登记的 10 个")
    result = []
    for index, row in enumerate(selected, 1):
        request = row["request"]
        observation = request["observation"]
        game_id = str(observation["game_id"])
        table_id = game_id.removeprefix("sitin-stage:")
        result.append({
            "target_id": "r18-p14-confirm-{0:02d}".format(index),
            "source": {
                "panel_seed": p12.PANEL_SEED,
                "source_id": row["source_id"], "mix": row["mix"],
                "root_index": row["root_index"], "focal_seat": row["focal_seat"],
                "table_no": int(table_id.rsplit("-t", 1)[1]), "table_id": table_id,
            },
            "window_key": request["window_key"],
            "focal_physical_seat": int(observation["seat"]),
            "request_sha256": row["request_sha256"],
            "state_projection_sha256": p13.value_digest(p13.state_projection(request)),
            "reference_action": row["parent"]["action_key"],
            "intervention_action": row["seven_pairs_frontier"]["action_key"],
            "features": {
                "round_no": row["round_no"], "dealer": row["dealer"],
                "remaining_tile_count": row["remaining_tile_count"],
                "wealth_count": row["wealth_count"], "pair_kinds": row["pair_kinds"],
                "triplet_kinds": row["triplet_kinds"],
                "standard_effect": row["standard_effect"],
                "parent": row["parent"],
                "seven_pairs_frontier": row["seven_pairs_frontier"],
            },
        })
    return result


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-hidden-{1:02d}.json".format(
        target["target_id"], index,
    ))


def prepare() -> None:
    """在任何新结果产生前冻结确认状态、判据和预算。"""

    if OUT.exists():
        raise SystemExit("P14 目录已存在；拒绝覆盖")
    frozen = targets()
    sample_keys = [
        "r18-p14-confirm-hidden-world-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(frozen) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name, authorization_id="r18-p14-pareto-gate-confirmation-01",
        accounts={"prefix_generation": len(frozen), "tables_full": planned_tables},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P13 发现双路线向听 Pareto 非劣边界；用未标注开发窗口跨来源确认",
        "scope": "每个未使用开发来源最多一个状态；32共同隐藏世界；P12 hidden不运行",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p14-pareto-confirm-targets/1", "targets": frozen,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p14-pareto-confirm-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=[
            Path(__file__), Path(p12.__file__), Path(p13.__file__),
            DATASET, FRONTIER, CONTRACT, PARENT,
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "dataset_sha256": digest(DATASET), "frontier_sha256": digest(FRONTIER),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "parent_sha256": digest(PARENT), "contract_sha256": digest(CONTRACT),
        "base_states": len(frozen), "rollouts_per_state": len(sample_keys),
        "sample_keys": sample_keys, "planned_tables": planned_tables,
        "workers": WORKERS,
        "frozen_gate": "seven_pairs route strictly improves by P12; intervention.standard_shanten_after <= parent.standard_shanten_after",
        "selection": "排除P13已冻结请求；每来源按固定哈希最多一状态",
        "pass_rule": {
            "minimum_states": 10,
            "minimum_positive_fraction": "2/3",
            "bootstrap_95_state_mean_lower": 0.0,
            "minimum_leave_one_root_out_mean": 0.0,
        },
        "hidden_labels_opened": False, "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "targets": len(frozen),
        "roots": sorted({row["source"]["root_index"] for row in frozen}),
        "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P12数据集": (manifest["dataset_sha256"], digest(DATASET)),
        "P12冻结前沿": (manifest["frontier_sha256"], digest(FRONTIER)),
        "P14目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "P5父代": (manifest["parent_sha256"], digest(PARENT)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["targets"]
    if frozen != targets():
        raise ValueError("P14目标不可由冻结开发数据重建")
    return manifest, frozen


def capture() -> None:
    manifest, frozen = verify()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [row for row in frozen if not snapshot_path(row).exists()]
    reservation = ledger.reserve(
        step_id="r18:p14-pareto-confirm:capture", account="prefix_generation",
        amount=len(pending), note="未标注开发窗口的P5精确合法前缀捕获",
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    completed = 0
    failures = []
    try:
        for target in pending:
            try:
                write_json(snapshot_path(target), p13.capture_one(target, contract))
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
        ledger.settle(reservation, actual=completed, note="按成功捕获计")
    write_json(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"), {
        "schema": "r18-p14-capture-summary/1",
        "captured": sum(snapshot_path(row).exists() for row in frozen),
        "planned": manifest["base_states"], "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in frozen):
        raise RuntimeError("P14 状态捕获不完整")


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
        label="p14-reference-{0}-{1:02d}".format(target["target_id"], index),
    )
    intervention_policies, intervention_force = p13.policies_for_arm(
        target=target, snapshot=snapshot,
        forced_action_key=str(target["intervention_action"]),
        label="p14-intervention-{0}-{1:02d}".format(target["target_id"], index),
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
    cut_round = int(target["features"]["round_no"])
    records = [record for record in settlement.records if record.round_no == cut_round]
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
        "schema": "r18-p14-pareto-confirm-rollout/1",
        "target_id": target["target_id"], "rollout_index": index,
        "sample_key": sample_key, "reference_action": target["reference_action"],
        "intervention_action": target["intervention_action"],
        "actual_actions": actions,
        "force_count": {"reference": reference_force.force_count,
                        "intervention": intervention_force.force_count},
        "reference": reference, "intervention": intervention,
        "focal_current_round_settlement_delta": (
            intervention["focal_settlement"] - reference["focal_settlement"]
        ),
        "focal_remaining_table_score": {
            "reference": reference_score, "intervention": intervention_score,
            "delta": int(intervention_score) - int(reference_score),
        },
        "tables_executed": double.get("tables_executed"),
        "mechanical_ok": mechanical,
    }


def run() -> None:
    manifest, frozen = verify()
    capture_summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    if capture_summary["failures"] or capture_summary["captured"] != manifest["base_states"]:
        raise ValueError("P14 精确状态尚未全部捕获")
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
                    raise ValueError("既有P14配对机械条件失败")
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p14-pareto-confirm:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="跨来源开发确认状态×32共同隐藏世界×两臂",
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
                        raise RuntimeError("P14配对机械条件失败")
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
        "schema": "r18-p14-run-summary/1", "rollout_files": len(files),
        "actual_tables": len(files) * 2, "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P14 确认执行不完整")


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    rng = random.Random(202609222314)
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
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P14 确认执行不完整")
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
        reference = p13._arm_summary(rows, "reference")
        intervention = p13._arm_summary(rows, "intervention")
        direct = [row["focal_current_round_settlement_delta"] for row in rows]
        full = [row["focal_remaining_table_score"]["delta"] for row in rows]
        states.append({
            "target_id": target["target_id"], "source": target["source"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "features": target["features"], "hidden_world_rollouts": len(rows),
            "reference": reference, "intervention": intervention,
            "delta": {
                "focal_hu_rate": intervention["focal_hu_rate"] - reference["focal_hu_rate"],
                "opponent_hu_rate": intervention["opponent_hu_rate"] - reference["opponent_hu_rate"],
                "mean_current_round_settlement": statistics.fmean(direct),
                "mean_remaining_table_score": statistics.fmean(full),
            },
            "current_round_settlement_values": direct,
            "remaining_table_score_values": full,
        })
    values = [row["delta"]["mean_current_round_settlement"] for row in states]
    full_values = [row["delta"]["mean_remaining_table_score"] for row in states]
    lo, hi = bootstrap_interval(values)
    roots = sorted({int(row["source"]["root_index"]) for row in states})
    leave_one_root_out = {
        str(root): statistics.fmean(
            row["delta"]["mean_current_round_settlement"]
            for row in states if int(row["source"]["root_index"]) != root
        )
        for root in roots
    }
    required_positive = math.ceil(2 * len(states) / 3)
    passed = bool(
        all_mechanical and len(states) >= 10
        and sum(value > 0 for value in values) >= required_positive
        and lo >= 0.0 and min(leave_one_root_out.values()) >= 0.0
    )
    result = {
        "schema": "r18-p14-pareto-confirm-result/1",
        "status": "COMPLETE_P14_PARETO_GATE_CONFIRMATION",
        "mechanical_ok": all_mechanical, "base_states": len(states),
        "rollouts": len(states) * ROLLOUTS_PER_STATE,
        "tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "states": states,
        "aggregate": {
            "mean_current_round_settlement_delta": statistics.fmean(values),
            "bootstrap_95_state_mean": [lo, hi],
            "mean_remaining_table_score_delta": statistics.fmean(full_values),
            "positive_state_means": sum(value > 0 for value in values),
            "zero_state_means": sum(value == 0 for value in values),
            "negative_state_means": sum(value < 0 for value in values),
            "required_positive_state_means": required_positive,
            "leave_one_root_out_mean": leave_one_root_out,
            "minimum_leave_one_root_out_mean": min(leave_one_root_out.values()),
            "terminal_transitions": dict(sorted(transitions.items())),
        },
        "gate_passed": passed,
        "decision": "FREEZE_PARETO_GATE_CANDIDATE" if passed else "CLOSE_GATE_KEEP_P5",
        "checks": {
            "all_pairs_mechanical_ok": all_mechanical,
            "all_states_have_32_common_hidden_worlds": all(
                row["hidden_world_rollouts"] == 32 for row in states
            ),
            "hidden_labels_opened": False,
        },
        "next_gate": (
            "在P5上实现精确双路线向听Pareto覆盖并冻结源码；随后才打开P12 hidden"
            if passed else
            "关闭该边界，保留P5并回到新的机制表示；不得打开P12 hidden"
        ),
        "hidden_labels_opened": False, "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], "base_states": len(states),
        "aggregate": result["aggregate"], "gate_passed": passed,
        "decision": result["decision"],
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
