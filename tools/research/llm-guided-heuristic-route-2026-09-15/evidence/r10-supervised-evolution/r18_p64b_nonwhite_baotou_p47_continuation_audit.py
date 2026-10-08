"""R18 P64B：显式绑定 P47 续打的非财神建爆头开发复核。

P64 已证明该杭麻机会在旧 P5 续打下有强正向因果信号，但复核发现复用 P13
执行器时未显式切换其模块级父代。P64B 使用同一批结果盲开发根、全新共同隐藏
世界，并在捕获和双臂续打前显式绑定当前 P47；16 个复验根继续不捕获、不生成
收益标签。
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

import confirmation_execution_identity as guard  # noqa: E402
import r18_p13_development_seven_pairs_teacher as p13  # noqa: E402
import r18_p63_nonwhite_baotou_natural_exposure as p63  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p64b-nonwhite-baotou-p47-continuation-audit-01-20260923')
CONTRACT = p63.CONTRACT
PARENT = p63.PARENT
ROLLOUTS_PER_STATE = 32
FIT_ROLLOUTS = 16
WORKERS = 8
BOOTSTRAP_REPLICATES = 20_000
MIN_RECHECK_POSITIVE_STATES = 12
P63_RESULT = p63.OUT / "result.json"
P63_DATASET = p63.OUT / "dataset.json"
P64_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p64-nonwhite-baotou-development-teacher-01-20260923/result.json')
P66B_RESULT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p66b-nonwhite-baotou-candidate-preflight-01-20260923/result.json')


def write_json(path: Path, value: Any) -> None:
    """写入稳定、可复算的 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def natural_rows() -> list[dict[str, Any]]:
    """读取 P63 在收益揭示前冻结的 16 开发根与 16 复验根。"""

    result = json.loads(P63_RESULT.read_text(encoding="utf-8"))
    document = json.loads(P63_DATASET.read_text(encoding="utf-8"))
    rows = list(document["rows"])
    if not (
        result.get("status") == "OPEN_DEVELOPMENT_CONFIRMATION"
        and result.get("passes_natural_exposure_gate") is True
        and result.get("replication_labels_opened") is False
        and document.get("outcome_blind") is True
        and document.get("replication_labels_opened") is False
    ):
        raise ValueError("P64B 只能消费仍保持复验盲态的 P63 自然数据集")
    if Counter(row["split"] for row in rows) != {
        "development": 16, "replication": 16,
    }:
        raise ValueError("P64B 必须绑定 P63 冻结的 16 开发根与 16 复验根")
    if Counter(row["source"]["mix"] for row in rows) != {"H": 16, "M": 16}:
        raise ValueError("P64B H/M 自然根计数漂移")
    roots = [str(row["source"]["source_root_id"]) for row in rows]
    if len(roots) != len(set(roots)):
        raise ValueError("P64B 来源根必须独立")
    if sorted({int(row["focal_physical_seat"]) for row in rows}) != [0, 1, 2, 3]:
        raise ValueError("P64B 焦点座位覆盖漂移")
    return rows


def targets() -> list[dict[str, Any]]:
    """把 P63 的结果盲切分投影为可捕获目标，不重新选择样本。"""

    rows = natural_rows()
    counters: Counter[str] = Counter()
    result = []
    for row in rows:
        split = str(row["split"])
        counters[split] += 1
        source = row["source"]
        result.append({
            "target_id": "r18-p64b-{0}-{1:02d}".format(
                split, counters[split],
            ),
            "split": split,
            "family": "hu_vs_nonwealth_baotou",
            "source": {
                "panel_seed": p63.PANEL_SEED,
                "source_id": source["source_id"],
                "source_root_id": source["source_root_id"],
                "mix": source["mix"],
                "root_index": source["root_index"],
                "focal_seat": source["focal_seat"],
                "table_no": row["table_no"],
                "table_id": row["table_id"],
            },
            "window_key": row["window_key"],
            "focal_physical_seat": row["focal_physical_seat"],
            "request_sha256": row["request_sha256"],
            "state_projection_sha256": row["state_projection_sha256"],
            "reference_action": row["reference_action"],
            "intervention_action": row["intervention_action"],
            "features": dict(row["features"]),
        })
    result.sort(key=lambda row: (
        row["split"], row["source"]["mix"],
        row["source"]["source_root_id"], row["request_sha256"],
    ))
    if Counter(row["split"] for row in result) != {
        "development": 16, "replication": 16,
    }:
        raise ValueError("P64B 开发/复验切分计数错误")
    roots = [row["source"]["source_root_id"] for row in result]
    if len(roots) != len(set(roots)):
        raise ValueError("P64B 来源根不独立")
    return result


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-hidden-{1:02d}.json".format(
        target["target_id"], index,
    ))


def source_paths() -> list[Path]:
    """列出会改变目标、重放或标签语义的实现与冻结输入。"""

    return [
        Path(__file__), Path(p13.__file__), Path(p63.__file__), CONTRACT, PARENT,
        p63.OUT / "manifest.json", P63_RESULT, P63_DATASET,
        P64_RESULT, P66B_RESULT,
    ]


def prepare() -> None:
    """在生成任何收益标签前冻结切分、隐藏世界和通过门。"""

    if OUT.exists():
        raise SystemExit("P64B 目录已存在；拒绝覆盖")
    p64_result = json.loads(P64_RESULT.read_text(encoding="utf-8"))
    p66b_result = json.loads(P66B_RESULT.read_text(encoding="utf-8"))
    if not (
        p64_result.get("status") == "COMPLETE_P64_NONWEALTH_BAOTOU_DEVELOPMENT_TEACHER"
        and p64_result.get("gate_passed") is True
        and p64_result.get("replication_labels_opened") is False
    ):
        raise ValueError("P64 开发信号或复验盲态不符合 P64B 入口条件")
    if not (
        p66b_result.get("status") == "PASS_P66B_NONWEALTH_BAOTOU_CANDIDATE_PREFLIGHT"
        and p66b_result.get("decision") == "OPEN_P67_REPLICATION"
    ):
        raise ValueError("P66B 候选预检未通过")
    frozen = targets()
    development = [row for row in frozen if row["split"] == "development"]
    sample_keys = [
        "r18-p64b-nonwhite-baotou-p47-public-hidden-world-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(development) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p64b-nonwhite-baotou-development-teacher-01",
        accounts={
            "prefix_generation": len(development),
            "tables_full": planned_tables,
        },
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P64暴露旧P5续打绑定缺口；P66B预检通过；使用同一批结果盲开发根、全新隐藏世界复核P47续打",
        "scope": "16开发根×32全新共同隐藏世界×立即胡/非财神建爆头；捕获与双臂续打显式绑定P47；16复验根不捕获",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p64b-nonwhite-baotou-targets/1",
        "p63_dataset_sha256": digest(P63_DATASET),
        "targets": frozen,
        "replication_labels_opened": False,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p64b-nonwhite-baotou-development-teacher-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "parent_sha256": digest(PARENT),
        "contract_sha256": digest(CONTRACT),
        "natural_roots": len(frozen),
        "development_states": len(development),
        "replication_states_kept_blind": len(frozen) - len(development),
        "rollouts_per_state": ROLLOUTS_PER_STATE,
        "fit_indices": list(range(1, FIT_ROLLOUTS + 1)),
        "recheck_indices": list(range(FIT_ROLLOUTS + 1, ROLLOUTS_PER_STATE + 1)),
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "workers": WORKERS,
        "sampling_unit": "自然来源根；共同隐藏世界不增加独立样本数",
        "sampling_scope": "依法可见公开状态一致的对手暗手与未消耗牌墙；不是历史后验",
        "continuation_parent": "P47；捕获前与每个工作子进程内都显式设置p13.PARENT",
        "method_correction": "P64仅支持旧P5续打；P64B在不打开复验标签的前提下校正为当前P47续打",
        "primary_label": "nonwealth_baotou_minus_immediate_hu_current_round_settlement",
        "gate": {
            "fit_state_mean_bootstrap_95_lower_strictly_greater_than": 0.0,
            "recheck_state_mean_bootstrap_95_lower_strictly_greater_than": 0.0,
            "minimum_recheck_positive_states": MIN_RECHECK_POSITIVE_STATES,
            "minimum_recheck_leave_one_root_out_mean_strictly_greater_than": 0.0,
            "each_mix_recheck_mean_strictly_greater_than": 0.0,
            "mechanical_success_required": True,
        },
        "replication_labels_opened": False,
        "model_calls": 0,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "natural_roots": len(frozen),
        "development_states": len(development),
        "replication_states_kept_blind": len(frozen) - len(development),
        "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对冻结切分、父代、合同和运行实现未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P64目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "P47父代": (manifest["parent_sha256"], digest(PARENT)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    document = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))
    if document.get("replication_labels_opened") is not False:
        raise ValueError("P64B 复验标签必须保持封存")
    frozen = list(document["targets"])
    if frozen != targets():
        raise ValueError("P64B 目标不能从 P63 结果盲数据集重建")
    return manifest, frozen


def capture() -> None:
    """只捕获 16 个开发根；16 个复验根保持零快照。"""

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
        step_id="r18:p64b-nonwealth-baotou-p47:capture", account="prefix_generation",
        amount=len(pending), note="16个非财神建爆头开发根的P47精确合法前缀捕获",
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    p13.PARENT = PARENT
    completed = 0
    failures = []
    try:
        for target in pending:
            try:
                snapshot = p13.capture_one(target, contract)
                snapshot["capture"]["consumer"] = "R18 P64B nonwealth baotou teacher"
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
        "schema": "r18-p64b-nonwhite-baotou-capture-summary/1",
        "captured": sum(snapshot_path(row).exists() for row in development),
        "planned": manifest["development_states"], "failures": failures,
        "replication_snapshots": sum(
            snapshot_path(row).exists() for row in frozen
            if row["split"] == "replication"
        ),
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in development):
        raise RuntimeError("P64B 开发状态捕获不完整")


def execute_rollout(
    target: Mapping[str, Any], index: int, sample_key: str,
) -> dict[str, Any]:
    """复用已验证的 P13 公开状态一致双臂执行。"""

    p13.OUT = OUT
    p13.PARENT = PARENT
    row = p13.execute_rollout(target, index, sample_key)
    row["schema"] = "r18-p64b-nonwhite-baotou-rollout/1"
    row["family"] = target["family"]
    row["split"] = target["split"]
    return row


def run() -> None:
    """并行执行 16×32 个公开状态一致共同隐藏世界配对。"""

    manifest, frozen = verify()
    development = [row for row in frozen if row["split"] == "development"]
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    if (
        summary["failures"]
        or summary["captured"] != manifest["development_states"]
        or summary["replication_snapshots"] != 0
    ):
        raise ValueError("P64B 开发前缀未完整捕获或复验状态被提前打开")
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
                    raise ValueError("既有 P64B 配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p64b-nonwealth-baotou-p47:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="16开发根×32共同隐藏世界×立即胡/非财神建爆头",
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
                        raise RuntimeError("P64B 配对机械条件失败")
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
        "schema": "r18-p64b-nonwhite-baotou-run-summary/1",
        "rollout_files": len(files), "actual_tables": len(files) * 2,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P64B 非财神建爆头教师执行不完整")


def bootstrap_interval(values: list[float], salt: int) -> tuple[float, float]:
    """对自然基础状态均值做确定性 bootstrap 95% 区间。"""

    rng = random.Random(2026092365 + salt)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return (
        means[int(0.025 * len(means))],
        means[int(0.975 * len(means)) - 1],
    )


def analyze() -> None:
    """按 16 个自然开发根等权裁定；正值表示非财神建爆头优于立即胡。"""

    manifest, frozen = verify()
    development = [row for row in frozen if row["split"] == "development"]
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P64B 开发教师执行不完整")
    states = []
    all_mechanical = True
    for target in development:
        rows = [
            json.loads(rollout_path(target, index).read_text(encoding="utf-8"))
            for index in range(1, ROLLOUTS_PER_STATE + 1)
        ]
        mechanical = all(row["mechanical_ok"] for row in rows)
        all_mechanical = all_mechanical and mechanical
        fit = [
            row["focal_current_round_settlement_delta"]
            for row in rows[:FIT_ROLLOUTS]
        ]
        recheck = [
            row["focal_current_round_settlement_delta"]
            for row in rows[FIT_ROLLOUTS:]
        ]
        full_recheck = [
            row["focal_remaining_table_score"]["delta"]
            for row in rows[FIT_ROLLOUTS:]
        ]
        states.append({
            "target_id": target["target_id"], "source": target["source"],
            "features": target["features"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "mechanical_ok": mechanical,
            "fit_mean_baotou_minus_hu_current_round_settlement": statistics.fmean(fit),
            "recheck_mean_baotou_minus_hu_current_round_settlement": statistics.fmean(recheck),
            "recheck_mean_remaining_table_score_delta": statistics.fmean(full_recheck),
            "fit_values": fit, "recheck_values": recheck,
            "terminal_transitions": dict(sorted(Counter(
                row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]
                for row in rows
            ).items())),
        })
    fit_values = [
        row["fit_mean_baotou_minus_hu_current_round_settlement"] for row in states
    ]
    recheck_values = [
        row["recheck_mean_baotou_minus_hu_current_round_settlement"] for row in states
    ]
    fit_low, fit_high = bootstrap_interval(fit_values, 1)
    recheck_low, recheck_high = bootstrap_interval(recheck_values, 2)
    leave_one_out = {}
    for row in states:
        root = str(row["source"]["source_root_id"])
        remaining = [
            value for item, value in zip(states, recheck_values)
            if str(item["source"]["source_root_id"]) != root
        ]
        leave_one_out[root] = statistics.fmean(remaining)
    positive_recheck = sum(value > 0 for value in recheck_values)
    mix_recheck_means = {
        mix: statistics.fmean(
            value for row, value in zip(states, recheck_values)
            if row["source"]["mix"] == mix
        )
        for mix in ("H", "M")
    }
    gate_passed = bool(
        all_mechanical
        and statistics.fmean(fit_values) > 0 and fit_low > 0
        and statistics.fmean(recheck_values) > 0 and recheck_low > 0
        and positive_recheck >= MIN_RECHECK_POSITIVE_STATES
        and min(leave_one_out.values()) > 0
        and min(mix_recheck_means.values()) > 0
    )
    aggregate = {
        "fit_mean_baotou_minus_hu_current_round_settlement": statistics.fmean(fit_values),
        "fit_bootstrap_95": [fit_low, fit_high],
        "recheck_mean_baotou_minus_hu_current_round_settlement": statistics.fmean(recheck_values),
        "recheck_bootstrap_95": [recheck_low, recheck_high],
        "recheck_positive_states": positive_recheck,
        "recheck_zero_states": sum(value == 0 for value in recheck_values),
        "recheck_negative_states": sum(value < 0 for value in recheck_values),
        "minimum_required_recheck_positive_states": MIN_RECHECK_POSITIVE_STATES,
        "recheck_leave_one_source_root_out_mean": leave_one_out,
        "minimum_recheck_leave_one_source_root_out_mean": min(leave_one_out.values()),
        "recheck_mean_by_mix": mix_recheck_means,
    }
    result = {
        "schema": "r18-p64b-nonwhite-baotou-development-teacher-result/1",
        "status": "COMPLETE_P64B_NONWEALTH_BAOTOU_P47_CONTINUATION_AUDIT",
        "mechanical_ok": all_mechanical,
        "natural_roots": manifest["natural_roots"],
        "development_states": len(states),
        "replication_states_kept_blind": manifest["replication_states_kept_blind"],
        "rollouts": len(states) * ROLLOUTS_PER_STATE,
        "tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "states": states, "aggregate": aggregate,
        "gate_passed": gate_passed,
        "decision": (
            "CONFIRM_P64_UNDER_P47_AND_OPEN_P67_REPLICATION" if gate_passed
            else "REJECT_P65_BEFORE_REPLICATION"
        ),
        "replication_labels_opened": False,
        "next": (
            "P64因果信号已在当前P47续打下复现；允许按预注册门打开16个复验根"
            if gate_passed else
            "保持P47并拒绝P65；不得打开复验标签后补阈值"
        ),
        "selection_eligible": False,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], "mechanical_ok": all_mechanical,
        "aggregate": aggregate, "gate_passed": gate_passed,
        "decision": result["decision"], "replication_labels_opened": False,
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
