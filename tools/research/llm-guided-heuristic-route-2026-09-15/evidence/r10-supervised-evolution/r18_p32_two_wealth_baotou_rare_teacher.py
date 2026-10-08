"""R18 P32：双财神飘后保持爆头的稀有机会开发教师。

P29 在标准自然通道的 24 根门处关闭，但 3,072 桌已经证明 19 个独立自然根
真实可达。P32 按新的稀有机会协议结果盲拆为 10 个开发根和 9 个隐藏根；只
运行开发根，在 32 个公开状态一致共同隐藏世界中比较立即胡与飘白。隐藏根在
候选源码和覆盖谓词冻结前不得捕获或生成收益标签。
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
import r18_p29_multiwhite_baotou_natural_exposure as p29  # noqa: E402
import r18_p29b_multiwhite_baotou_natural_topup as p29b  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p32-two-wealth-baotou-rare-teacher-01-20260922')
CONTRACT = p29.CONTRACT
PARENT = p29.PARENT
ROLLOUTS_PER_STATE = 32
FIT_ROLLOUTS = 16
WORKERS = 8
BOOTSTRAP_REPLICATES = 20_000
SELECTION_SALT = "r18-p32-two-wealth-root-selection/v1"
SPLIT_SALT = "r18-p32-two-wealth-rare-split/v1"
MIN_RECHECK_POSITIVE_STATES = 7
BATCHES = (
    ("P29", p29.OUT, p29.PANEL_SEED),
    ("P29b", p29b.OUT, p29b.PANEL_SEED),
)


def write_json(path: Path, value: Any) -> None:
    """写入稳定、可复算的 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash_order(row: Mapping[str, Any], salt: str) -> str:
    payload = "|".join((
        salt, str(row["batch"]), str(row["source"]["source_root_id"]),
        str(row["request_sha256"]),
    ))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def natural_rows() -> list[dict[str, Any]]:
    """从 P29/P29b 冻结产物重建 19 个结果盲自然根。"""

    by_root: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for batch_name, directory, panel_seed in BATCHES:
        for path in sorted((directory / "sources").glob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            for source_row in document["audit"]["eligible_rows"]:
                row = dict(source_row)
                row["batch"] = batch_name
                row["panel_seed"] = panel_seed
                key = (batch_name, str(row["source"]["source_root_id"]))
                by_root.setdefault(key, []).append(row)
    selected = [
        min(options, key=lambda row: _hash_order(row, SELECTION_SALT))
        for _, options in sorted(by_root.items())
    ]
    if len(selected) != 19:
        raise ValueError("P32 必须从 P29/P29b 重建 19 个独立自然根")
    if Counter(row["source"]["mix"] for row in selected) != {"H": 10, "M": 9}:
        raise ValueError("P32 H/M 自然根计数漂移")
    if sorted({int(row["focal_physical_seat"]) for row in selected}) != [0, 1, 2, 3]:
        raise ValueError("P32 焦点座位覆盖漂移")
    return selected


def targets() -> list[dict[str, Any]]:
    """按 H/M 冻结哈希拆出 10 个开发根和 9 个隐藏根。"""

    rows = natural_rows()
    pools = {
        mix: sorted(
            (row for row in rows if row["source"]["mix"] == mix),
            key=lambda row: _hash_order(row, SPLIT_SALT),
        )
        for mix in ("H", "M")
    }
    development_quota = {"H": 5, "M": 5}
    counters: Counter[str] = Counter()
    result = []
    for mix in ("H", "M"):
        for index, row in enumerate(pools[mix]):
            split = "development" if index < development_quota[mix] else "hidden"
            counters[split] += 1
            source = row["source"]
            result.append({
                "target_id": "r18-p32-{0}-{1:02d}".format(
                    split, counters[split],
                ),
                "split": split,
                "family": "two_wealth.piao_keeps_baotou",
                "source": {
                    "batch": row["batch"],
                    "panel_seed": row["panel_seed"],
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
    if Counter(row["split"] for row in result) != {"development": 10, "hidden": 9}:
        raise ValueError("P32 开发/隐藏切分计数错误")
    roots = [(row["source"]["batch"], row["source"]["source_root_id"]) for row in result]
    if len(roots) != len(set(roots)):
        raise ValueError("P32 来源根不独立")
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
        Path(__file__), Path(p13.__file__), Path(p29.__file__), Path(p29b.__file__),
        CONTRACT, PARENT,
        p29.OUT / "manifest.json", p29.OUT / "result.json",
        p29b.OUT / "manifest.json", p29b.OUT / "result.json",
    ]


def prepare() -> None:
    """在生成任何收益标签前冻结切分、隐藏世界和通过门。"""

    if OUT.exists():
        raise SystemExit("P32 目录已存在；拒绝覆盖")
    frozen = targets()
    development = [row for row in frozen if row["split"] == "development"]
    sample_keys = [
        "r18-p32-two-wealth-public-hidden-world-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(development) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p32-two-wealth-baotou-rare-teacher-01",
        accounts={
            "prefix_generation": len(development),
            "tables_full": planned_tables,
        },
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P32稀有机会协议；P29的19个自然根已证明可达性",
        "scope": "10开发根×32共同隐藏世界×立即胡/飘白；9隐藏根不捕获",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p32-two-wealth-baotou-targets/1",
        "selection_salt": SELECTION_SALT,
        "split_salt": SPLIT_SALT,
        "targets": frozen,
        "hidden_labels_opened": False,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p32-two-wealth-baotou-rare-teacher-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
        ]),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "parent_sha256": digest(PARENT),
        "contract_sha256": digest(CONTRACT),
        "natural_roots": len(frozen),
        "development_states": len(development),
        "hidden_states_kept_blind": len(frozen) - len(development),
        "rollouts_per_state": ROLLOUTS_PER_STATE,
        "fit_indices": list(range(1, FIT_ROLLOUTS + 1)),
        "recheck_indices": list(range(FIT_ROLLOUTS + 1, ROLLOUTS_PER_STATE + 1)),
        "sample_keys": sample_keys,
        "planned_tables": planned_tables,
        "workers": WORKERS,
        "sampling_unit": "自然来源根；共同隐藏世界不增加独立样本数",
        "sampling_scope": "依法可见公开状态一致的对手暗手与未消耗牌墙；不是历史后验",
        "primary_label": "piao_minus_immediate_hu_current_round_settlement",
        "gate": {
            "fit_state_mean_bootstrap_95_lower_strictly_greater_than": 0.0,
            "recheck_state_mean_bootstrap_95_lower_strictly_greater_than": 0.0,
            "minimum_recheck_positive_states": MIN_RECHECK_POSITIVE_STATES,
            "minimum_recheck_leave_one_root_out_mean_strictly_greater_than": 0.0,
            "mechanical_success_required": True,
        },
        "hidden_labels_opened": False,
        "model_calls": 0,
        "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "natural_roots": len(frozen),
        "development_states": len(development),
        "hidden_states_kept_blind": len(frozen) - len(development),
        "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对冻结切分、父代、合同和运行实现未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P32目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "P5父代": (manifest["parent_sha256"], digest(PARENT)),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    document = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))
    if document.get("hidden_labels_opened") is not False:
        raise ValueError("P32 隐藏标签必须保持封存")
    frozen = list(document["targets"])
    if frozen != targets():
        raise ValueError("P32 目标不能从 P29/P29b 结果盲重建")
    return manifest, frozen


def capture() -> None:
    """只捕获 10 个开发根；9 个隐藏根保持零快照。"""

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
        step_id="r18:p32-two-wealth:capture", account="prefix_generation",
        amount=len(pending), note="10个双财神开发根的P5精确合法前缀捕获",
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    completed = 0
    failures = []
    try:
        for target in pending:
            try:
                snapshot = p13.capture_one(target, contract)
                snapshot["capture"]["consumer"] = "R18 P32 two-wealth rare teacher"
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
        "schema": "r18-p32-two-wealth-capture-summary/1",
        "captured": sum(snapshot_path(row).exists() for row in development),
        "planned": manifest["development_states"], "failures": failures,
        "hidden_snapshots": sum(
            snapshot_path(row).exists() for row in frozen if row["split"] == "hidden"
        ),
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in development):
        raise RuntimeError("P32 开发状态捕获不完整")


def execute_rollout(
    target: Mapping[str, Any], index: int, sample_key: str,
) -> dict[str, Any]:
    """复用已验证的 P13 公开状态一致双臂执行。"""

    p13.OUT = OUT
    row = p13.execute_rollout(target, index, sample_key)
    row["schema"] = "r18-p32-two-wealth-baotou-rollout/1"
    row["family"] = target["family"]
    row["split"] = target["split"]
    return row


def run() -> None:
    """并行执行 10×32 个公开状态一致共同隐藏世界配对。"""

    manifest, frozen = verify()
    development = [row for row in frozen if row["split"] == "development"]
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    if (
        summary["failures"]
        or summary["captured"] != manifest["development_states"]
        or summary["hidden_snapshots"] != 0
    ):
        raise ValueError("P32 开发前缀未完整捕获或隐藏状态被提前打开")
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
                    raise ValueError("既有 P32 配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p32-two-wealth:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="10开发根×32共同隐藏世界×立即胡/飘白",
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
                        raise RuntimeError("P32 配对机械条件失败")
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
        "schema": "r18-p32-two-wealth-run-summary/1",
        "rollout_files": len(files), "actual_tables": len(files) * 2,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P32 稀有机会教师执行不完整")


def bootstrap_interval(values: list[float], salt: int) -> tuple[float, float]:
    """对自然基础状态均值做确定性 bootstrap 95% 区间。"""

    rng = random.Random(2026092232 + salt)
    means = []
    for _ in range(BOOTSTRAP_REPLICATES):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return (
        means[int(0.025 * len(means))],
        means[int(0.975 * len(means)) - 1],
    )


def analyze() -> None:
    """按 10 个自然开发根等权裁定；正值表示飘白优于立即胡。"""

    manifest, frozen = verify()
    development = [row for row in frozen if row["split"] == "development"]
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P32 开发教师执行不完整")
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
            "fit_mean_piao_minus_hu_current_round_settlement": statistics.fmean(fit),
            "recheck_mean_piao_minus_hu_current_round_settlement": statistics.fmean(recheck),
            "recheck_mean_remaining_table_score_delta": statistics.fmean(full_recheck),
            "fit_values": fit, "recheck_values": recheck,
            "terminal_transitions": dict(sorted(Counter(
                row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]
                for row in rows
            ).items())),
        })
    fit_values = [
        row["fit_mean_piao_minus_hu_current_round_settlement"] for row in states
    ]
    recheck_values = [
        row["recheck_mean_piao_minus_hu_current_round_settlement"] for row in states
    ]
    fit_low, fit_high = bootstrap_interval(fit_values, 1)
    recheck_low, recheck_high = bootstrap_interval(recheck_values, 2)
    leave_one_out = {}
    for row in states:
        root = (row["source"]["batch"], row["source"]["source_root_id"])
        remaining = [
            value for item, value in zip(states, recheck_values)
            if (item["source"]["batch"], item["source"]["source_root_id"]) != root
        ]
        leave_one_out["|".join(root)] = statistics.fmean(remaining)
    positive_recheck = sum(value > 0 for value in recheck_values)
    gate_passed = bool(
        all_mechanical
        and statistics.fmean(fit_values) > 0 and fit_low > 0
        and statistics.fmean(recheck_values) > 0 and recheck_low > 0
        and positive_recheck >= MIN_RECHECK_POSITIVE_STATES
        and min(leave_one_out.values()) > 0
    )
    aggregate = {
        "fit_mean_piao_minus_hu_current_round_settlement": statistics.fmean(fit_values),
        "fit_bootstrap_95": [fit_low, fit_high],
        "recheck_mean_piao_minus_hu_current_round_settlement": statistics.fmean(recheck_values),
        "recheck_bootstrap_95": [recheck_low, recheck_high],
        "recheck_positive_states": positive_recheck,
        "recheck_zero_states": sum(value == 0 for value in recheck_values),
        "recheck_negative_states": sum(value < 0 for value in recheck_values),
        "minimum_required_recheck_positive_states": MIN_RECHECK_POSITIVE_STATES,
        "recheck_leave_one_source_root_out_mean": leave_one_out,
        "minimum_recheck_leave_one_source_root_out_mean": min(leave_one_out.values()),
    }
    result = {
        "schema": "r18-p32-two-wealth-baotou-rare-teacher-result/1",
        "status": "COMPLETE_P32_TWO_WEALTH_BAOTOU_RARE_TEACHER",
        "mechanical_ok": all_mechanical,
        "natural_roots": manifest["natural_roots"],
        "development_states": len(states),
        "hidden_states_kept_blind": manifest["hidden_states_kept_blind"],
        "rollouts": len(states) * ROLLOUTS_PER_STATE,
        "tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "states": states, "aggregate": aggregate,
        "gate_passed": gate_passed,
        "decision": (
            "OPEN_P33_LIMITED_AUTHOR" if gate_passed
            else "CLOSE_TWO_WEALTH_PIAO_KEEPS_BAOTOU"
        ),
        "hidden_labels_opened": False,
        "next": (
            "只用开发标签与公开事实生成一个精确回退P5的双财神候选；冻结后才打开9个隐藏根"
            if gate_passed else
            "保持P5并关闭该双财神假设；不得打开隐藏标签后补阈值"
        ),
        "selection_eligible": True,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        "status": result["status"], "mechanical_ok": all_mechanical,
        "aggregate": aggregate, "gate_passed": gate_passed,
        "decision": result["decision"], "hidden_labels_opened": False,
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
