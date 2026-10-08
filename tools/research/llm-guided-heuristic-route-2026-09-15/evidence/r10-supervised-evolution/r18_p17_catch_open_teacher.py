"""R18 P17：主动弃白开圈的开发集共同隐藏世界教师。

P16 已结果盲冻结 256 个自然开圈位点。本阶段排除当前可立即胡的状态，
按来源根固定哈希各取一条：H/M 的 1—16 根作为开发集，17—32 根只冻结
请求身份作为隐藏集。开发状态比较 P5 非白弃牌与 ``discard:白``；两臂只在
目标窗口分叉，随后都恢复 P5，并共享公开状态一致的隐藏世界。

前 16 个隐藏世界只用于拟合选择，后 16 个只用于复现。主标签是目标局内
焦点结算差；完整剩余桌得分只作安全诊断。隐藏集标签在候选冻结前不得打开。
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
import r18_p13_development_seven_pairs_teacher as p13  # noqa: E402
import r18_p16_catch_play_natural_exposure as p16  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_opportunities as opportunities  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402
from hangma_bot.hangma.engine import HangmaRules  # noqa: E402
from hangma_bot.kernel.serialization import window_key_from_json  # noqa: E402
from hangma_bot.offline.forced_action import ForceFirstActionPolicy  # noqa: E402
from hangma_bot.policy.action_value_policy import ActionValuePolicy  # noqa: E402
from hangma_bot.policy.action_value_seeds import ActionValueScorer  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p17-catch-open-teacher-01-20260922')
P16_DATASET = p16.OUT / "dataset.json"
P16_RESULT = p16.OUT / "result.json"
CONTRACT = p16.CONTRACT
PARENT = p16.PARENT
LIMITS = p16.LIMITS
ROLLOUTS_PER_STATE = 32
FIT_ROLLOUTS = 16
WORKERS = 8
BOOTSTRAP_REPLICATES = 20_000
SELECTION_SALT = "r18-p17-catch-open-source-root-v1"


def write_json(path: Path, value: Any) -> None:
    """写入可复算且以换行结束的 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    """返回文件 SHA-256。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_digest(value: Any) -> str:
    """返回规范 JSON 值的 SHA-256。"""

    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _selection_key(row: Mapping[str, Any]) -> tuple[str, str]:
    key = SELECTION_SALT + "|" + str(row["request_sha256"])
    return hashlib.sha256(key.encode("utf-8")).hexdigest(), str(row["request_sha256"])


def _target(row: Mapping[str, Any], *, split: str, index: int) -> dict[str, Any]:
    request = row["request"]
    observation = request["observation"]
    game_id = str(observation["game_id"])
    table_id = game_id.removeprefix("sitin-stage:")
    white = list(row["white_discard_keys"])
    if len(white) != 1:
        raise ValueError("标准开圈状态必须只有一个白牌弃牌动作")
    target_id = "r18-p17-{0}-{1:02d}".format(split, index)
    return {
        "target_id": target_id,
        "split": split,
        "source": {
            "panel_seed": p16.PANEL_SEED,
            "source_id": row["source"]["source_id"],
            "source_root_id": row["source"]["source_root_id"],
            "mix": row["source"]["mix"],
            "root_index": row["source"]["root_index"],
            "focal_seat": row["source"]["focal_seat"],
            "table_no": int(table_id.rsplit("-t", 1)[1]),
            "table_id": table_id,
        },
        "window_key": request["window_key"],
        "focal_physical_seat": int(observation["seat"]),
        "request_sha256": row["request_sha256"],
        "state_projection_sha256": value_digest(p13.state_projection(request)),
        "reference_action": row["p5_action_key"],
        "intervention_action": white[0],
        "features": {
            "family": row["family"],
            "round_no": row["round_no"],
            "dealer_seat": row["dealer_seat"],
            "remaining_tile_count": row["remaining_tile_count"],
            "wealth_count": row["wealth_count"],
            "baotou": row["baotou"],
            "chain_count": row["chain_count"],
            "chain_piao": row["chain_piao"],
            "catch_play_active": row["catch_play_active"],
            "has_immediate_hu": row["has_immediate_hu"],
            "legal_action_keys": row["legal_action_keys"],
            "nonwhite_discard_keys": row["nonwhite_discard_keys"],
        },
    }


def rebuild_targets() -> dict[str, list[dict[str, Any]]]:
    """按结果盲来源根分割和固定哈希重建开发/隐藏目标。"""

    result = json.loads(P16_RESULT.read_text(encoding="utf-8"))
    if result.get("families_open_for_p17") != ["catch.open"]:
        raise ValueError("P16 只应开放 catch.open")
    dataset = json.loads(P16_DATASET.read_text(encoding="utf-8"))
    if dataset.get("outcome_blind") is not True:
        raise ValueError("P16 数据集必须结果盲")
    eligible = []
    for row in dataset.get("rows") or []:
        if row.get("family") != "catch.open" or row.get("has_immediate_hu"):
            continue
        if row.get("p5_action_key") not in (row.get("nonwhite_discard_keys") or []):
            continue
        if len(row.get("white_discard_keys") or []) != 1:
            continue
        eligible.append(row)

    by_root: dict[str, list[dict[str, Any]]] = {}
    for row in eligible:
        root = str(row["source"]["source_root_id"])
        by_root.setdefault(root, []).append(row)
    selected = [min(rows, key=_selection_key) for _, rows in sorted(by_root.items())]
    development_rows = sorted(
        (row for row in selected if int(row["source"]["root_index"]) <= 16),
        key=lambda row: str(row["source"]["source_root_id"]),
    )
    hidden_rows = sorted(
        (row for row in selected if int(row["source"]["root_index"]) > 16),
        key=lambda row: str(row["source"]["source_root_id"]),
    )
    if len(development_rows) != 32 or len(hidden_rows) != 32:
        raise ValueError("P17 开发/隐藏必须各有32个独立来源根")
    development = [
        _target(row, split="development", index=index)
        for index, row in enumerate(development_rows, 1)
    ]
    hidden = [
        _target(row, split="hidden", index=index)
        for index, row in enumerate(hidden_rows, 1)
    ]
    roots = [row["source"]["source_root_id"] for row in development + hidden]
    hashes = [row["request_sha256"] for row in development + hidden]
    if len(set(roots)) != 64 or len(set(hashes)) != 64:
        raise ValueError("P17 来源根或请求摘要不唯一")
    return {"development": development, "hidden": hidden}


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-hidden-{1:02d}.json".format(
        target["target_id"], index,
    ))


def source_paths() -> list[Path]:
    """列出会改变目标、重放或标签语义的实现。"""

    import hangma_bot.offline.forced_action as forced_action
    import hangma_bot.simulation.engine as simulation_engine
    import hangma_bot.simulation.shuffle as simulation_shuffle

    return [
        Path(__file__), P16_DATASET, P16_RESULT, CONTRACT, PARENT,
        Path(p11.__file__), Path(p13.__file__), Path(p16.__file__),
        Path(natural.__file__), Path(opportunities.__file__),
        Path(forced_action.__file__), Path(simulation_engine.__file__),
        Path(simulation_shuffle.__file__),
    ]


def prepare() -> None:
    """冻结 32 个开发状态、32 个隐藏状态和 P17 执行预算。"""

    if OUT.exists():
        raise SystemExit("P17 目录已存在；拒绝覆盖")
    frozen = rebuild_targets()
    development = frozen["development"]
    sample_keys = [
        "r18-p17-catch-open-hidden-world-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(development) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p17-catch-open-teacher-01",
        accounts={"prefix_generation": len(development), "tables_full": planned_tables},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P16 catch.open 通过24状态/4来源根自然暴露门",
        "scope": "32个开发状态×32共同隐藏世界×P5非白弃牌/主动弃白；隐藏32状态不运行",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p17-catch-open-targets/1",
        "selection_salt": SELECTION_SALT,
        "development": development,
        "hidden": frozen["hidden"],
        "hidden_labels_opened": False,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p17-catch-open-teacher-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "p16_dataset_sha256": digest(P16_DATASET),
        "p16_result_sha256": digest(P16_RESULT),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "parent_sha256": digest(PARENT),
        "contract_sha256": digest(CONTRACT),
        "development_states": len(development),
        "hidden_states": len(frozen["hidden"]),
        "rollouts_per_state": len(sample_keys),
        "fit_indices": list(range(1, FIT_ROLLOUTS + 1)),
        "replication_indices": list(range(FIT_ROLLOUTS + 1, len(sample_keys) + 1)),
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "workers": WORKERS,
        "sampling_unit": "自然基础状态；共同隐藏分配只估计该状态条件效应",
        "selection_rule": "每状态只用fit半区；均值>0选择主动开圈，否则回退P5",
        "primary_label": "focal_current_round_settlement_delta",
        "safety_diagnostic": "focal_remaining_table_score_delta",
        "gate": {
            "minimum_fit_selected_non_reference_states": 8,
            "minimum_replication_positive_fraction": "2/3",
            "replication_all_state_bootstrap_95_lower": 0.0,
            "minimum_leave_one_source_root_out_mean": 0.0,
        },
        "hidden_labels_opened": False,
        "development_labels_selection_eligible": True,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "development": len(development),
        "hidden": len(frozen["hidden"]), "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对冻结目标、父代、合同与执行实现没有漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P16数据集": (manifest["p16_dataset_sha256"], digest(P16_DATASET)),
        "P16结果": (manifest["p16_result_sha256"], digest(P16_RESULT)),
        "P17目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "P5父代": (manifest["parent_sha256"], digest(PARENT)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    document = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))
    if document.get("hidden_labels_opened") is not False:
        raise ValueError("P17 hidden 标签必须保持封存")
    rebuilt = rebuild_targets()
    if document["development"] != rebuilt["development"] or document["hidden"] != rebuilt["hidden"]:
        raise ValueError("P17目标不可由P16结果盲重建")
    return manifest, list(document["development"])


def capture() -> None:
    """顺序捕获 32 个开发状态；隐藏状态只冻结身份。"""

    manifest, development = verify()
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [row for row in development if not snapshot_path(row).exists()]
    reservation = ledger.reserve(
        step_id="r18:p17-catch-open:capture",
        account="prefix_generation", amount=len(pending),
        note="32个开发状态的P5精确合法前缀捕获；隐藏不捕获",
    )
    completed = 0
    failures = []
    try:
        for target in pending:
            try:
                write_json(snapshot_path(target), p13.capture_one(
                    target, json.loads(CONTRACT.read_text(encoding="utf-8")),
                ))
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
        "schema": "r18-p17-capture-summary/1",
        "captured": sum(snapshot_path(row).exists() for row in development),
        "planned": manifest["development_states"], "failures": failures,
        "spent": ledger.account_summary(), "hidden_captured": 0,
    })
    if failures or not all(snapshot_path(row).exists() for row in development):
        raise RuntimeError("P17 development 状态捕获不完整")


def policies_for_arm(
    *, target: Mapping[str, Any], snapshot: Mapping[str, Any],
    forced_action_key: str, label: str,
) -> tuple[list[Any], ForceFirstActionPolicy]:
    """焦点强制一次目标动作后恢复 P5；对手沿用冻结合同策略。"""

    focal = int(target["focal_physical_seat"])
    policies = list(opportunities.frozen_generation_policies(
        opponent_names=snapshot["capture"]["opponent_names_in_physical_order"],
        focal_seat=focal, monotonic=lambda: 800.0,
    ))
    delegate = ActionValuePolicy(ActionValueScorer(
        "r18-p17-p5-continuation-" + label, PARENT.read_text(encoding="utf-8"),
    ))
    forced = ForceFirstActionPolicy(
        delegate, target_window=window_key_from_json(target["window_key"]),
        forced_action_key=forced_action_key, policy_id="r18-p17-" + label,
    )
    policies[focal] = forced
    return policies, forced


def terminal(record: Any, focal: int) -> str:
    """把目标局结算归为焦点和、对手和或流局/非和终止。"""

    if record.is_draw or record.winner_seat is None:
        return "wall_draw_or_non_hu_end"
    return "focal_hu" if int(record.winner_seat) == focal else "opponent_hu"


def execute_rollout(target: Mapping[str, Any], index: int, sample_key: str) -> dict[str, Any]:
    """在一个共同隐藏世界中执行 P5 与主动开圈两臂。"""

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
            world, focal_seat=int(target["focal_physical_seat"]), sample_key=sample_key,
        ),
    )
    cut_round = int(target["features"]["round_no"])
    records = [record for record in settlement.records if record.round_no == cut_round]
    if len(records) != 2:
        raise RuntimeError("目标局必须按参考臂、开圈臂各捕获一次，实际 {0}".format(len(records)))
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
        and target["intervention_action"] == "discard:白"
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
        "schema": "r18-p17-catch-open-rollout/1",
        "target_id": target["target_id"], "rollout_index": index,
        "sample_split": "fit" if index <= FIT_ROLLOUTS else "replication",
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
        "focal_remaining_table_score_delta": int(intervention_score) - int(reference_score),
        "tables_executed": double.get("tables_executed"),
        "completion_reasons": double.get("completion_reasons"),
        "runtime_kind": double.get("runtime_kind"),
        "execution_kind": double.get("execution_kind"),
        "sampling_scope": "public-consistent opponent hands plus unconsumed wall; not history posterior",
        "mechanical_ok": mechanical,
    }


def run() -> None:
    """并行执行 32×32 个共同隐藏世界配对，支持断点续跑。"""

    manifest, development = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["captured"] != manifest["development_states"]:
        raise ValueError("P17 精确状态尚未全部捕获")
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
                    raise ValueError("既有P17配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p17-catch-open:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="32开发状态×32共同隐藏世界×P5非白弃牌/主动弃白",
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
                        raise RuntimeError("P17共同隐藏世界配对机械条件失败")
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
        "schema": "r18-p17-run-summary/1", "rollout_files": len(files),
        "actual_tables": len(files) * 2, "failures": failures,
        "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P17主动开圈教师执行不完整")


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    """按独立自然状态等权计算固定种子的双侧 95% bootstrap 区间。"""

    rng = random.Random(202609222317)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(statistics.fmean(values[rng.randrange(len(values))] for _ in values))
    means.sort()
    return (
        means[math.floor(0.025 * (len(means) - 1))],
        means[math.ceil(0.975 * (len(means) - 1))],
    )


def _arm_summary(rows: list[dict[str, Any]], arm: str) -> dict[str, Any]:
    terminal_counts = Counter(row[arm]["terminal"] for row in rows)
    return {
        "focal_hu": terminal_counts["focal_hu"],
        "opponent_hu": terminal_counts["opponent_hu"],
        "wall_draw_or_non_hu_end": terminal_counts["wall_draw_or_non_hu_end"],
        "mean_focal_settlement": statistics.fmean(
            row[arm]["focal_settlement"] for row in rows
        ),
    }


def analyze() -> None:
    """用拟合半区选开圈状态，并只用复现半区裁定是否进入作者阶段。"""

    manifest, development = verify()
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P17主动开圈教师执行不完整")
    states = []
    all_mechanical = True
    for target in development:
        rows = [
            json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, ROLLOUTS_PER_STATE + 1)
        ]
        all_mechanical = all_mechanical and all(row["mechanical_ok"] for row in rows)
        fit = rows[:FIT_ROLLOUTS]
        replication = rows[FIT_ROLLOUTS:]
        fit_values = [row["focal_current_round_settlement_delta"] for row in fit]
        replication_values = [
            row["focal_current_round_settlement_delta"] for row in replication
        ]
        fit_mean = statistics.fmean(fit_values)
        replication_mean = statistics.fmean(replication_values)
        selected = fit_mean > 0.0
        states.append({
            "target_id": target["target_id"], "source": target["source"],
            "features": target["features"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "selected_open_from_fit": selected,
            "fit": {
                "reference": _arm_summary(fit, "reference"),
                "intervention": _arm_summary(fit, "intervention"),
                "mean_current_round_settlement_delta": fit_mean,
                "mean_remaining_table_score_delta": statistics.fmean(
                    row["focal_remaining_table_score_delta"] for row in fit
                ),
                "values": fit_values,
            },
            "replication": {
                "reference": _arm_summary(replication, "reference"),
                "intervention": _arm_summary(replication, "intervention"),
                "mean_current_round_settlement_delta": replication_mean,
                "mean_remaining_table_score_delta": statistics.fmean(
                    row["focal_remaining_table_score_delta"] for row in replication
                ),
                "values": replication_values,
                "positive": selected and replication_mean > 0.0,
            },
            "policy_replication_value": replication_mean if selected else 0.0,
        })

    selected = [row for row in states if row["selected_open_from_fit"]]
    policy_values = [row["policy_replication_value"] for row in states]
    lo, hi = bootstrap_interval(policy_values)
    required_positive = math.ceil(2 * len(selected) / 3) if selected else 0
    leave_one_root_out = {
        row["source"]["source_root_id"]: statistics.fmean(
            other["policy_replication_value"]
            for other in states if other["target_id"] != row["target_id"]
        )
        for row in states
    }
    replication_positive = sum(row["replication"]["positive"] for row in selected)
    gate_passed = bool(
        all_mechanical
        and len(selected) >= 8
        and replication_positive >= required_positive
        and lo >= 0.0
        and min(leave_one_root_out.values()) >= 0.0
    )
    result = {
        "schema": "r18-p17-catch-open-result/1",
        "status": "COMPLETE_P17_CATCH_OPEN_TEACHER",
        "mechanical_ok": all_mechanical,
        "development_states": len(states),
        "hidden_states_frozen_unopened": manifest["hidden_states"],
        "rollouts": len(states) * ROLLOUTS_PER_STATE,
        "tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "states": states,
        "aggregate": {
            "fit_selected_open_states": len(selected),
            "replication_positive_selected_states": replication_positive,
            "required_replication_positive_selected_states": required_positive,
            "replication_all_state_policy_mean": statistics.fmean(policy_values),
            "replication_all_state_policy_bootstrap_95": [lo, hi],
            "replication_selected_open_mean": (
                statistics.fmean(
                    row["replication"]["mean_current_round_settlement_delta"]
                    for row in selected
                ) if selected else 0.0
            ),
            "replication_selected_open_remaining_table_mean": (
                statistics.fmean(
                    row["replication"]["mean_remaining_table_score_delta"]
                    for row in selected
                ) if selected else 0.0
            ),
            "leave_one_source_root_out_mean": leave_one_root_out,
            "minimum_leave_one_source_root_out_mean": min(leave_one_root_out.values()),
        },
        "gate_passed": gate_passed,
        "decision": "OPEN_P18_LIMITED_AUTHOR" if gate_passed else "CLOSE_STANDARD_CATCH_OPEN",
        "next_gate": (
            "只用开发fit标签与公开特征归纳小型开圈路由器；候选冻结后才打开hidden标签"
            if gate_passed else
            "保留P5并关闭标准主动开圈；不得查看hidden标签后补阈值"
        ),
        "interpretation": "独立统计单位是32个自然基础状态；32个隐藏分配不增加独立状态数",
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
