"""R18 P21b：明杠响应窗口的共同未来牌墙修复教师。

P21 证明公开一致隐藏手重采样只支持本人摸牌窗口，明杠响应窗口因而整层
fail-closed。本批不改原证据：复用 P21 已冻结的 16 个明杠开发状态和精确
快照，固定原自然隐藏手，只在每一臂共同重排尚未摸取的未来牌墙。该标签的
适用范围比摸牌窗口教师窄，结论必须按 16 个自然基础状态统计并单列限制。
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
from collections import Counter
import concurrent.futures
from dataclasses import replace
import hashlib
import json
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
import r18_p11_settlement_cascade_teacher as p11  # noqa: E402
import r18_p13_development_seven_pairs_teacher as p13  # noqa: E402
import r18_p21_gang_pair_development_teacher as p21  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p21b-exposed-gang-future-wall-teacher-01-20260922')
TARGETS = p21.OUT / "targets.json"
P21_MANIFEST = p21.OUT / "manifest.json"
P21_CAPTURE = p21.OUT / "capture-summary.json"
CONTRACT = p21.CONTRACT
PARENT = p21.PARENT
FAMILY = "exposed.gang_to_nongang"
ROLLOUTS_PER_STATE = 32
WORKERS = 8


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def targets() -> list[dict[str, Any]]:
    rows = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"]
    selected = [
        row for row in rows
        if row["split"] == "development" and row["family"] == FAMILY
    ]
    if len(selected) != 16:
        raise ValueError("P21b 必须恰有 16 个明杠开发状态")
    if len({row["source"]["source_root_id"] for row in selected}) != len(selected):
        raise ValueError("P21b 明杠开发状态的来源根不独立")
    return selected


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-future-{1:02d}.json".format(
        target["target_id"], index,
    ))


def source_paths() -> list[Path]:
    return [
        Path(__file__), Path(p11.__file__), Path(p13.__file__), Path(p21.__file__),
        TARGETS, P21_MANIFEST, P21_CAPTURE, CONTRACT, PARENT,
        *[p21.snapshot_path(target) for target in targets()],
    ]


def prepare() -> None:
    """冻结 P21 明杠开发状态、未来牌墙样本和独立修复预算。"""

    if OUT.exists():
        raise SystemExit("P21b 目录已存在；拒绝覆盖")
    p21_manifest, _ = p21.verify()
    capture = json.loads(P21_CAPTURE.read_text(encoding="utf-8"))
    if capture["failures"] or capture["captured"] != p21_manifest["development_states"]:
        raise ValueError("P21 开发快照未完整冻结")
    frozen = targets()
    sample_keys = [
        "r18-p21b-exposed-future-wall-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(frozen) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p21b-exposed-gang-future-wall-teacher-01",
        accounts={"tables_full": planned_tables},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P21明杠层因响应窗口不支持隐藏手重采样而整层失败；改用合法的共同未来牌墙",
        "scope": "复用16个冻结明杠开发状态；原自然隐藏手固定；32个共同未来牌墙；复验标签仍不打开",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p21b-exposed-targets/1", "targets": frozen,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p21b-exposed-future-wall-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "p21_targets_sha256": digest(TARGETS),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "parent_sha256": digest(PARENT),
        "contract_sha256": digest(CONTRACT),
        "family": FAMILY,
        "base_states": len(frozen),
        "rollouts_per_state": len(sample_keys),
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "workers": WORKERS,
        "sampling_unit": "自然基础状态；32个共同未来牌墙不增加独立样本数",
        "sampling_scope": "固定原自然三家暗手，只重排尚未摸取的未来牌墙；不是公开状态一致隐藏手分布",
        "repair_of": "P21明杠响应窗口512个失败配对；原失败不删除、不改写、不补零",
        "replication_labels_opened": False,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "base_states": len(frozen),
        "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P21目标": (manifest["p21_targets_sha256"], digest(TARGETS)),
        "P21b目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "P5父代": (manifest["parent_sha256"], digest(PARENT)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["targets"]
    if frozen != targets():
        raise ValueError("P21b 目标不能由 P21 冻结目标重建")
    return manifest, frozen


def execute_rollout(target: Mapping[str, Any], index: int, sample_key: str) -> dict[str, Any]:
    """固定原隐藏手，在共同未来牌墙下执行明杠与非杠两臂。"""

    snapshot = json.loads(p21.snapshot_path(target).read_text(encoding="utf-8"))
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
    reference_policies, reference_force = p13.policies_for_arm(
        target=target, snapshot=snapshot,
        forced_action_key=str(target["reference_action"]),
        label="p21b-reference-{0}-{1:02d}".format(target["target_id"], index),
    )
    intervention_policies, intervention_force = p13.policies_for_arm(
        target=target, snapshot=snapshot,
        forced_action_key=str(target["intervention_action"]),
        label="p21b-intervention-{0}-{1:02d}".format(target["target_id"], index),
    )

    def transform(world: Any) -> Any:
        sampled = settlement.resample_future_drawable_wall(world, sample_key=sample_key)
        return replace(sampled, history_consistent=False)

    double = opportunities.run_double_arm(
        rules=rules, snapshot=snapshot,
        baseline_policies_by_seat=reference_policies,
        candidate_policies_by_seat=intervention_policies,
        config=opportunities._driver_config(), value_limits=p13.LIMITS,
        runtime=runtime, current_world_transform=transform,
    )
    if not double.get("valid"):
        errors = {
            arm: (detail.get("status"), detail.get("error"))
            for arm, detail in (double.get("arms") or {}).items()
        }
        raise RuntimeError("双臂执行无效：" + repr(errors))
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
        reference_force.force_count == 1 and intervention_force.force_count == 1
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
        "schema": "r18-p21b-exposed-future-wall-rollout/1",
        "target_id": target["target_id"], "family": target["family"],
        "rollout_index": index, "sample_key": sample_key,
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
        "sampling_scope": "source hidden hands fixed; common future drawable wall only",
        "mechanical_ok": mechanical,
    }


def run() -> None:
    """并行执行 16×32 个明杠响应窗口共同未来牌墙配对。"""

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
                    raise ValueError("既有 P21b 配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p21b-exposed-future-wall:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="16明杠开发状态×32共同未来牌墙×杠/非杠",
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
                        raise RuntimeError("P21b 配对机械条件失败")
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
        "schema": "r18-p21b-exposed-run-summary/1",
        "rollout_files": len(files), "actual_tables": len(files) * 2,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P21b 明杠未来牌墙教师执行不完整")


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    rng = random.Random(2026092221)
    means = []
    for _ in range(20_000):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return means[int(0.025 * len(means))], means[int(0.975 * len(means)) - 1]


def analyze() -> None:
    """按 16 个自然基础状态等权汇总，正值表示非杠优于原明杠。"""

    manifest, frozen = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P21b 执行不完整")
    states = []
    for target in frozen:
        rows = [
            json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, ROLLOUTS_PER_STATE + 1)
        ]
        direct = [row["focal_current_round_settlement_delta"] for row in rows]
        full = [row["focal_remaining_table_score"]["delta"] for row in rows]
        states.append({
            "target_id": target["target_id"], "source": target["source"],
            "features": target["features"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "hidden_world_rollouts": len(rows),
            "mechanical_ok": all(row["mechanical_ok"] for row in rows),
            "mean_current_round_settlement_delta": statistics.fmean(direct),
            "mean_remaining_table_score_delta": statistics.fmean(full),
            "positive_future_walls": sum(value > 0 for value in direct),
            "zero_future_walls": sum(value == 0 for value in direct),
            "negative_future_walls": sum(value < 0 for value in direct),
            "current_round_settlement_values": direct,
            "terminal_transitions": dict(sorted(Counter(
                row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]
                for row in rows
            ).items())),
        })
    values = [row["mean_current_round_settlement_delta"] for row in states]
    low, high = bootstrap_interval(values)
    mean = statistics.fmean(values)
    mechanical = all(row["mechanical_ok"] for row in states)
    positive = sum(value > 0 for value in values)
    aggregate = {
        "independent_states": len(states),
        "mean_non_gang_minus_gang_current_round_settlement": mean,
        "bootstrap_95_interval": [low, high],
        "positive_state_means": positive,
        "zero_state_means": sum(value == 0 for value in values),
        "negative_state_means": sum(value < 0 for value in values),
        "open_for_rule_authoring": bool(
            mechanical and len(states) == 16 and mean > 0 and low > 0 and positive >= 10
        ),
    }
    result = {
        "schema": "r18-p21b-exposed-future-wall-result/1",
        "status": "COMPLETE_P21B_EXPOSED_GANG_FUTURE_WALL_TEACHER",
        "mechanical_ok": mechanical,
        "base_states": len(states), "rollouts": len(states) * ROLLOUTS_PER_STATE,
        "tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "states": states, "aggregate": aggregate,
        "sampling_scope": manifest["sampling_scope"],
        "replication_labels_opened": False,
        "next": "与P21暗杠/补杠开发结果并列审查；只有过门家族才拟合窄规则，随后冻结候选并打开各自复验状态",
        "selection_eligible": True,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], "mechanical_ok": mechanical,
        "aggregate": aggregate, "replication_labels_opened": False,
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
