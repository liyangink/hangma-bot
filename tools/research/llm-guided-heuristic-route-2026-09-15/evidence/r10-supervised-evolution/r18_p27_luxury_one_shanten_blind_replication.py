"""R18 P27：锁定豪华组同为普通型 1 向听候选的盲态复验。

P26 已在未打开复验标签前冻结候选源码、作用域和逐点回退。本程序只捕获、
运行并分析 P24 预留的 12 个复验状态。每个状态在 32 个公开状态一致的隐藏
世界中比较 P5 原暗杠与候选选择的保留四张弃牌，之后两臂都恢复 P5。
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
import r18_p24_luxury_one_shanten_natural_confirmation as p24  # noqa: E402
import r18_p26_luxury_one_shanten_candidate_preflight as p26  # noqa: E402
import sitin_natural_panel as natural  # noqa: E402
import sitin_search as search  # noqa: E402
import strong_seed_batch as batch  # noqa: E402


OUT = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution/r18-p27-luxury-one-shanten-blind-replication-01-20260922')
DATASET = p24.OUT / "dataset.json"
EXPOSURE_RESULT = p24.OUT / "result.json"
CONTRACT = p24.CONTRACT
PARENT = p24.PARENT
CANDIDATE = p26.CANDIDATE
CANDIDATE_MANIFEST = p26.OUT / "manifest.json"
CANDIDATE_PREFLIGHT = p26.OUT / "preflight.json"
DEVELOPMENT_STATES = 12
REPLICATION_STATES = 12
ROLLOUTS_PER_STATE = 32
WORKERS = 8


def write_json(path: Path, value: Any) -> None:
    """写入稳定 UTF-8 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def targets() -> list[dict[str, Any]]:
    """把 P24 结果盲拆分转换为可精确重建的自然中局目标。"""

    exposure = json.loads(EXPOSURE_RESULT.read_text(encoding="utf-8"))
    if exposure.get("status") != "OPEN_DEVELOPMENT_CONFIRMATION":
        raise ValueError("P24 未开放开发确认")
    rows = json.loads(DATASET.read_text(encoding="utf-8"))["rows"]
    counters: Counter[str] = Counter()
    result = []
    for row in rows:
        split = str(row["split"])
        counters[split] += 1
        source = row["source"]
        result.append({
            "target_id": "r18-p25-{0}-{1:02d}".format(split, counters[split]),
            "split": split,
            "family": "luxury_locked.same_standard_one",
            "source": {
                "panel_seed": p24.PANEL_SEED,
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
            "features": row["features"],
        })
    if counters != Counter({
        "development": DEVELOPMENT_STATES, "replication": REPLICATION_STATES,
    }):
        raise ValueError("P27 开发/复验目标数错误：" + repr(counters))
    for split in ("development", "replication"):
        mix_counts = Counter(
            row["source"]["mix"] for row in result if row["split"] == split
        )
        if mix_counts != Counter({"H": 6, "M": 6}):
            raise ValueError("P27 " + split + " H/M 分层错误：" + repr(mix_counts))
    return sorted(result, key=lambda row: (
        row["split"], row["source"]["mix"],
        row["source"]["source_root_id"], row["request_sha256"],
    ))


def snapshot_path(target: Mapping[str, Any]) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "snapshots" / (str(target["target_id"]) + ".json"))


def rollout_path(target: Mapping[str, Any], index: int) -> Path:
    return _project_file(_PROJECT_ROOT, OUT / "rollouts" / "{0}-hidden-{1:02d}.json".format(
        target["target_id"], index,
    ))


def prepare() -> None:
    """冻结 P24 预留的 12 个复验目标、候选身份和执行预算。"""

    if OUT.exists():
        raise SystemExit("P27 目录已存在；拒绝覆盖")
    frozen = targets()
    replication = [row for row in frozen if row["split"] == "replication"]
    sample_keys = [
        "r18-p27-luxury-one-shanten-hidden-{0:02d}".format(index)
        for index in range(1, ROLLOUTS_PER_STATE + 1)
    ]
    planned_tables = len(replication) * len(sample_keys) * 2
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = batch.unified_document(
        batch_label=OUT.name,
        authorization_id="r18-p27-luxury-one-shanten-blind-replication-01",
        accounts={"prefix_generation": len(replication), "tables_full": planned_tables},
        issued_by="lead", issued_at_utc=search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "P25开发门通过且P26候选/作用域/回退预检已在复验标签打开前冻结",
        "scope": "12复验状态×32共同隐藏世界×P5原暗杠/P26保留弃牌",
        "max_model_calls": 0,
        "confirmation_roots": 0,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write_json(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "r18-p27-luxury-one-shanten-targets/1", "targets": frozen,
    })
    tracked = [
        Path(__file__), DATASET, EXPOSURE_RESULT, Path(p24.__file__),
        Path(p13.__file__), Path(natural.__file__), Path(p26.__file__), CONTRACT, PARENT,
        CANDIDATE, CANDIDATE_MANIFEST, CANDIDATE_PREFLIGHT,
        _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json"),
    ]
    write_json(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "r18-p27-luxury-one-shanten-replication-manifest/1",
        "created_at_utc": search.utc_now(),
        "runtime": guard.capture(source_paths=tracked),
        "dataset_sha256": digest(DATASET),
        "exposure_result_sha256": digest(EXPOSURE_RESULT),
        "targets_sha256": digest(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "contract_sha256": digest(CONTRACT), "parent_sha256": digest(PARENT),
        "candidate_sha256": digest(CANDIDATE),
        "candidate_manifest_sha256": digest(CANDIDATE_MANIFEST),
        "candidate_preflight_sha256": digest(CANDIDATE_PREFLIGHT),
        "replication_states": len(replication),
        "rollouts_per_state": ROLLOUTS_PER_STATE,
        "sample_keys": sample_keys, "planned_tables": planned_tables,
        "workers": WORKERS,
        "primary_label": "preserve_discard_minus_concealed_gang_current_round_settlement",
        "replication_gate": {
            "mean_strictly_positive": True,
            "bootstrap_95_lower_strictly_positive": True,
            "positive_state_means_at_least": 9,
            "all_mechanical": True,
        },
        "independence_unit": "P24自然牌山根；32隐藏分配不增加n",
        "replication_labels_opened_at_prepare": False,
        "model_calls": 0, "selection_eligible": False, "release_eligible": False,
    })
    print(json.dumps({
        "status": "PREPARED", "replication_states": len(replication),
        "planned_tables": planned_tables,
    }, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """核对 P24 输入、目标、父代、合同和执行实现未漂移。"""

    manifest = json.loads((_project_file(_PROJECT_ROOT, OUT / "manifest.json")).read_text(encoding="utf-8"))
    checks = {
        "P24数据": (manifest["dataset_sha256"], digest(DATASET)),
        "P24结果": (manifest["exposure_result_sha256"], digest(EXPOSURE_RESULT)),
        "P27目标": (manifest["targets_sha256"], digest(_project_file(_PROJECT_ROOT, OUT / "targets.json"))),
        "合同": (manifest["contract_sha256"], digest(CONTRACT)),
        "P5父代": (manifest["parent_sha256"], digest(PARENT)),
        "P26候选": (manifest["candidate_sha256"], digest(CANDIDATE)),
        "P26候选清单": (manifest["candidate_manifest_sha256"], digest(CANDIDATE_MANIFEST)),
        "P26预检": (manifest["candidate_preflight_sha256"], digest(CANDIDATE_PREFLIGHT)),
    }
    for label, (expected, actual) in checks.items():
        if expected != actual:
            raise ValueError(label + "漂移")
    guard.verify(manifest["runtime"])
    frozen = json.loads((_project_file(_PROJECT_ROOT, OUT / "targets.json")).read_text(encoding="utf-8"))["targets"]
    if frozen != targets():
        raise ValueError("P27 目标不能由 P24 结果盲重建")
    return manifest, frozen


def capture() -> None:
    """捕获 12 个复验公开状态，并先核对冻结候选确实选择目标动作。"""

    manifest, frozen = verify()
    replication = [row for row in frozen if row["split"] == "replication"]
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = [row for row in replication if not snapshot_path(row).exists()]
    reservation = ledger.reserve(
        step_id="r18:p27-luxury-one-shanten:capture", account="prefix_generation",
        amount=len(pending), note="12个复验状态的P5精确合法前缀捕获",
    )
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    completed = 0
    failures = []
    try:
        for target in pending:
            try:
                snapshot = p13.capture_one(target, contract)
                snapshot["capture"]["consumer"] = "R18 P27 luxury-one-shanten blind replication"
                write_json(snapshot_path(target), snapshot)
                completed += 1
                print(json.dumps({
                    "captured": sum(snapshot_path(row).exists() for row in replication),
                    "planned": len(replication),
                }, ensure_ascii=False), flush=True)
            except Exception as exc:  # noqa: BLE001
                failures.append({
                    "target_id": target["target_id"],
                    "error": type(exc).__name__ + ": " + str(exc),
                })
    finally:
        ledger.settle(reservation, actual=completed, note="按成功捕获的合法前缀计")
    parent = p13.ActionValueScorer("r18-p27-capture-parent", PARENT.read_text(encoding="utf-8"))
    candidate = p13.ActionValueScorer("r18-p27-capture-candidate", CANDIDATE.read_text(encoding="utf-8"))
    selection_rows = []
    if not failures and all(snapshot_path(row).exists() for row in replication):
        for target in replication:
            snapshot = json.loads(snapshot_path(target).read_text(encoding="utf-8"))
            selection_rows.append(p26.check_one(
                label=target["target_id"],
                request=p26.request_from_snapshot(target, snapshot),
                parent=parent, candidate=candidate,
            ))
    selection_ok = bool(
        len(selection_rows) == len(replication)
        and all(row["expected_trigger"] for row in selection_rows)
        and all(row["candidate_top"] == target["intervention_action"]
                for row, target in zip(selection_rows, replication))
    )
    write_json(_project_file(_PROJECT_ROOT, OUT / "candidate-selection.json"), {
        "schema": "r18-p27-candidate-selection/1",
        "candidate_sha256": digest(CANDIDATE),
        "selection_ok": selection_ok,
        "rows": selection_rows,
        "outcome_labels_opened": False,
    })
    write_json(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"), {
        "schema": "r18-p27-luxury-one-shanten-capture-summary/1",
        "captured": sum(snapshot_path(row).exists() for row in replication),
        "planned": manifest["replication_states"], "failures": failures,
        "candidate_selection_ok": selection_ok,
        "spent": ledger.account_summary(),
    })
    if failures or not all(snapshot_path(row).exists() for row in replication):
        raise RuntimeError("P27 复验状态捕获不完整")
    if not selection_ok:
        raise RuntimeError("P27 冻结候选未在全部复验状态选择预登记动作")


def execute_rollout(target: Mapping[str, Any], index: int, sample_key: str) -> dict[str, Any]:
    """复用已验证的双臂执行器，并把证据身份改为 P27。"""

    p13.OUT = OUT
    row = p13.execute_rollout(target, index, sample_key)
    row["schema"] = "r18-p27-luxury-one-shanten-replication-rollout/1"
    row["split"] = target["split"]
    row["family"] = target["family"]
    return row


def run() -> None:
    """并行执行 12×32 个复验集共同隐藏世界配对。"""

    manifest, frozen = verify()
    replication = [row for row in frozen if row["split"] == "replication"]
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "capture-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["captured"] != manifest["replication_states"]:
        raise ValueError("P27 复验状态尚未全部捕获")
    if summary["candidate_selection_ok"] is not True:
        raise ValueError("P27 候选选择预检未通过")
    authorization = json.loads((_project_file(_PROJECT_ROOT, OUT / "authorization.json")).read_text(encoding="utf-8"))
    natural.require_authorization(authorization)
    ledger = search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=search.av_ledger_budgets_from_authorization(authorization),
    )
    pending = []
    completed_tables = 0
    for target in replication:
        for index, key in enumerate(manifest["sample_keys"], 1):
            path = rollout_path(target, index)
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                if not row.get("mechanical_ok"):
                    raise ValueError("既有 P27 配对机械条件失败：" + str(path))
                completed_tables += 2
            else:
                pending.append((target, index, key))
    reservation = ledger.reserve(
        step_id="r18:p27-luxury-one-shanten:run", account="tables_full",
        amount=manifest["planned_tables"] - completed_tables,
        note="12复验状态×32共同隐藏世界×原暗杠/候选保留豪华组弃牌",
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
                        raise RuntimeError("P27 共同隐藏世界配对机械条件失败")
                    write_json(rollout_path(target, index), row)
                    executed += 2
                    completed_tables += 2
                    if completed_tables % 128 == 0 or completed_tables == manifest["planned_tables"]:
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
        "schema": "r18-p27-luxury-one-shanten-run-summary/1",
        "rollout_files": len(files), "actual_tables": len(files) * 2,
        "failures": failures, "spent": ledger.account_summary(),
    })
    if failures or len(files) * 2 != manifest["planned_tables"]:
        raise RuntimeError("P27 复验教师执行不完整")


def bootstrap_interval(values: list[float]) -> tuple[float, float]:
    """对独立自然牌山根均值做确定性百分位 bootstrap 95% 区间。"""

    rng = random.Random(2026092227)
    means = []
    for _ in range(20_000):
        means.append(statistics.fmean(rng.choice(values) for _ in values))
    means.sort()
    return means[int(0.025 * len(means))], means[int(0.975 * len(means)) - 1]


def analyze() -> None:
    """按自然牌山根等权汇总盲态复验标签；正值表示候选优于 P5 原暗杠。"""

    manifest, frozen = verify()
    replication = [row for row in frozen if row["split"] == "replication"]
    summary = json.loads((_project_file(_PROJECT_ROOT, OUT / "run-summary.json")).read_text(encoding="utf-8"))
    if summary["failures"] or summary["actual_tables"] != manifest["planned_tables"]:
        raise ValueError("P27 复验教师执行不完整")
    states = []
    for target in replication:
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
            "positive_hidden_worlds": sum(value > 0 for value in direct),
            "zero_hidden_worlds": sum(value == 0 for value in direct),
            "negative_hidden_worlds": sum(value < 0 for value in direct),
            "terminal_transitions": dict(sorted(Counter(
                row["reference"]["terminal"] + "->" + row["intervention"]["terminal"]
                for row in rows
            ).items())),
            "current_round_settlement_values": direct,
        })
    values = [row["mean_current_round_settlement_delta"] for row in states]
    low, high = bootstrap_interval(values)
    mean = statistics.fmean(values)
    positive = sum(value > 0 for value in values)
    mechanical = all(row["mechanical_ok"] for row in states)
    passes = bool(mechanical and mean > 0 and low > 0 and positive >= 9)
    result = {
        "schema": "r18-p27-luxury-one-shanten-replication-result/1",
        "status": (
            "PASS_BLIND_REPLICATION_ADMISSION" if passes
            else "CLOSE_P26_CANDIDATE"
        ),
        "mechanical_ok": mechanical,
        "replication_states": len(states),
        "rollouts": len(states) * ROLLOUTS_PER_STATE,
        "tables": len(states) * ROLLOUTS_PER_STATE * 2,
        "mean_preserve_minus_gang_current_round_settlement": mean,
        "bootstrap_95_interval": [low, high],
        "positive_state_means": positive,
        "zero_state_means": sum(value == 0 for value in values),
        "negative_state_means": sum(value < 0 for value in values),
        "passes_replication_gate": passes,
        "states": states,
        "candidate_sha256": digest(CANDIDATE),
        "replication_labels_opened": True,
        "model_calls": 0,
        "next": (
            "进入候选对自然触发率、完整桌赛非劣和正式策略接缝的分层准入"
            if passes else
            "按预登记门淘汰P26，不对复验结果追加财神数、墙深或积分阈值"
        ),
        "selection_eligible": passes,
        "release_eligible": False,
    }
    write_json(_project_file(_PROJECT_ROOT, OUT / "result.json"), result)
    print(json.dumps({
        key: result[key] for key in (
            "status", "mechanical_ok", "replication_states", "tables",
            "mean_preserve_minus_gang_current_round_settlement",
            "bootstrap_95_interval", "positive_state_means",
            "zero_state_means", "negative_state_means",
            "passes_replication_gate", "replication_labels_opened", "next",
        )
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
