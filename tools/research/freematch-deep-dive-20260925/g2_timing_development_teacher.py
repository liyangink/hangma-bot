#!/usr/bin/env python3
"""G2：仅打开 G1 双听牌鸣/过的开发根，复用 P84 精确配对教师。"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/freematch-deep-dive-20260925'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys
from typing import Any

ROOT = _PROJECT_ROOT
ROUTE = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15')
R10 = _project_file(_PROJECT_ROOT, 'review/llm-guided-heuristic-route-2026-09-15/evidence/r10-supervised-evolution')
for path in (_project_file(_PROJECT_ROOT, ROOT / "src"), _project_file(_PROJECT_ROOT, ROUTE / "tools"), R10):
    sys.path.insert(0, str(path))

import r18_p84_high_wealth_near_seven_current_table_teacher as p84  # noqa: E402

HERE = Path(__file__).resolve().parent
G1 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g1-timing-natural-01')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g2-timing-development-01')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G2-SELF-DRAW-TIMING-DEVELOPMENT-PREREG-2026-09-26.md')
DATASET = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g1-timing-natural-01/dataset.json')
RESULT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g1-timing-natural-01/result.json')
IDENTITY = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g1-timing-natural-01/policy-identity-review.json')
ROLLS = 32
PANEL_SEED = 2026102701
SAMPLE_KEYS = [f"g2-self-draw-timing-20260926-future-wall-{i:02d}" for i in range(1, ROLLS + 1)]

# P84 的物理重建和续打函数是本实验的唯一执行实现；仅换输出目录与冻结目标。
p84.OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g2-timing-development-01')


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    p84.write_json(path, value)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def targets() -> list[dict[str, Any]]:
    """将 G1 冻结的结果盲行转成 P84 精确前缀目标。"""
    identity = read(IDENTITY)
    result = read(RESULT)
    data = read(DATASET)
    if (identity.get("review_passed") is not True
            or identity.get("actual_tables") != 512
            or identity.get("selected_window_policy_top_checked") != 48
            or result.get("status") != "OPEN_DEVELOPMENT_TEACHER"
            or data.get("outcome_blind") is not True
            or data.get("replication_labels_opened") is not False):
        raise ValueError("G1 结果盲、策略身份或开发门不成立")
    rows = list(data["rows"])
    if len(rows) != 48:
        raise ValueError("G1 必须冻结 48 个独立根")
    made = []
    for i, row in enumerate(rows, 1):
        source = dict(row["source"])
        source.update(panel_seed=PANEL_SEED, table_no=row["table_no"],
                      table_id=row["table_id"])
        made.append({
            "target_id": f"g2-timing-{i:04d}",
            "split": row["split"], "category": row["category"],
            "family": row["family"], "source": source,
            "window_key": row["window_key"],
            "competition": row["request"]["competition"],
            "focal_physical_seat": row["focal_physical_seat"],
            "request_sha256": row["request_sha256"],
            "state_projection_sha256": row["state_projection_sha256"],
            "reference_action": row["reference_action"],
            "intervention_action": row["intervention_action"],
            "features": row["features"],
        })
    cells = Counter((t["source"]["mix"], t["category"], t["split"]) for t in made)
    if len(cells) != 8 or set(cells.values()) != {6}:
        raise ValueError("G1 H/M×鸣/过×开发/复验必须各 6 根")
    roots = [t["source"]["source_root_id"] for t in made]
    if len(roots) != len(set(roots)):
        raise ValueError("G1 自然根不独立")
    return made


def source_paths() -> list[Path]:
    """记录实际执行闭包；G1 的结果盲原件与 P84 物理函数均受摘要保护。"""
    return [Path(__file__), PREREG, DATASET, RESULT, IDENTITY,
            p84.CONTRACT, p84.PARENT, Path(p84.__file__),
            *[path for path in p84.source_paths()
              if path not in (Path(p84.__file__), p84.DATASET,
                              p84.EXPOSURE_RESULT, p84.OUT / "manifest.json",
                              p84.OUT / "policy-identity-review.json")]]


def prepare() -> None:
    """在任何收益标签生成前冻结来源、样本键和费用。"""
    if OUT.exists():
        raise SystemExit("G2 已有输出目录，拒绝覆盖")
    frozen = targets()
    dev = [t for t in frozen if t["split"] == "development"]
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    authorization = p84.batch.unified_document(
        batch_label=OUT.name, authorization_id="g2-self-draw-timing-development-01",
        accounts={"prefix_generation": len(dev), "tables_full": len(dev) * ROLLS * 2},
        issued_by="lead", issued_at_utc=p84.search.utc_now(), legacy_alias=False,
    )
    authorization.update({
        "issuance_basis": "G1 48 个结果盲独立根通过身份门，仅开发 24 根",
        "scope": "24 根×32 共同未来墙×双臂当前完整桌；24 自然复验根封存",
        "max_model_calls": 0, "confirmation_roots": 0,
    })
    write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), authorization)
    write(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "g2-timing-targets/1", "targets": frozen,
        "replication_labels_opened": False,
    })
    write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "g2-timing-development-manifest/1",
        "created_at_utc": p84.search.utc_now(),
        "runtime": p84.guard.capture(source_paths=source_paths() + [
            _project_file(_PROJECT_ROOT, OUT / "authorization.json"), _project_file(_PROJECT_ROOT, OUT / "targets.json")]),
        "dataset_sha256": sha(DATASET), "result_sha256": sha(RESULT),
        "identity_sha256": sha(IDENTITY), "parent_sha256": sha(p84.PARENT),
        "contract_sha256": sha(p84.CONTRACT),
        "targets_sha256": sha(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "parent_score_source_sha256": hashlib.sha256(
            p84.p83.parent_source().encode("utf-8")).hexdigest(),
        "development_roots": 24, "replication_roots_sealed": 24,
        "rollouts_per_root": ROLLS, "planned_pairs": 24 * ROLLS,
        "planned_tables": 24 * ROLLS * 2, "sample_keys": SAMPLE_KEYS,
        "preflight_sample_key": "g2-timing-engineering-preflight-excluded-00",
        "teacher_endpoint": "target_round_and_current_full_table_only",
        "sampling_unit": "独立自然根；同根 32 未来墙仅降低根内误差",
        "replication_labels_opened": False, "model_calls": 0,
        "release_eligible": False,
    })
    print(json.dumps({"status": "PREPARED", "development_roots": 24,
                      "replication_roots_sealed": 24,
                      "planned_tables": 1536}, ensure_ascii=False))


def verify() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """重算所有结果盲输入与运行实现摘要，禁止漂移后续跑。"""
    manifest = read(_project_file(_PROJECT_ROOT, OUT / "manifest.json"))
    checks = [("G1 dataset", DATASET, "dataset_sha256"),
              ("G1 result", RESULT, "result_sha256"),
              ("G1 identity", IDENTITY, "identity_sha256"),
              ("parent", p84.PARENT, "parent_sha256"),
              ("contract", p84.CONTRACT, "contract_sha256"),
              ("targets", _project_file(_PROJECT_ROOT, OUT / "targets.json"), "targets_sha256")]
    for label, path, key in checks:
        if sha(path) != manifest[key]:
            raise ValueError(label + " 摘要漂移")
    if hashlib.sha256(p84.p83.parent_source().encode("utf-8")).hexdigest() != manifest[
        "parent_score_source_sha256"]:
        raise ValueError("R18 v2 评分源码漂移")
    p84.guard.verify(manifest["runtime"])
    doc = read(_project_file(_PROJECT_ROOT, OUT / "targets.json"))
    if doc.get("replication_labels_opened") is not False or doc["targets"] != targets():
        raise ValueError("G2 冻结目标漂移或复验已打开")
    return manifest, doc["targets"]


def development(frozen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [target for target in frozen if target["split"] == "development"]


def ensure_sealed(frozen: list[dict[str, Any]]) -> None:
    if any(p84.snapshot_path(t).exists() for t in frozen if t["split"] == "replication"):
        raise ValueError("自然复验根快照被提前打开")
    if any(p84.rollout_path(t, i).exists() for t in frozen if t["split"] == "replication"
           for i in range(1, ROLLS + 1)):
        raise ValueError("自然复验根续打被提前打开")


def ledger() -> Any:
    auth = read(_project_file(_PROJECT_ROOT, OUT / "authorization.json"))
    p84.natural.require_authorization(auth)
    return p84.search.ActionValueLedger.load(
        _project_file(_PROJECT_ROOT, OUT / "ledger.json"),
        authorized_budgets=p84.search.av_ledger_budgets_from_authorization(auth),
    )


def capture() -> None:
    """只捕获开发根；每成功一根记一个精确前缀。"""
    manifest, frozen = verify()
    ensure_sealed(frozen)
    dev = development(frozen)
    book = ledger()
    contract = read(p84.CONTRACT)
    for target in dev:
        path = p84.snapshot_path(target)
        if path.exists():
            continue
        reservation = book.reserve(
            step_id="g2:capture:" + target["target_id"],
            account="prefix_generation", amount=1,
            note="G1 开发根精确合法前缀",
        )
        try:
            snapshot = p84.capture_one(target, contract)
            snapshot["capture"]["consumer"] = "G2 self-draw timing development"
            write(path, snapshot)
            book.settle(reservation, actual=1, note="精确前缀身份一致")
        except BaseException:
            book.settle(reservation, usage_unknown=True, note="捕获异常，保守计费")
            raise
        print(json.dumps({"captured": sum(p84.snapshot_path(t).exists() for t in dev),
                          "planned": len(dev)}, ensure_ascii=False), flush=True)
    count = sum(p84.snapshot_path(t).exists() for t in dev)
    ensure_sealed(frozen)
    write(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"), {
        "schema": "g2-timing-capture-summary/1", "captured": count,
        "planned": manifest["development_roots"], "replication_snapshots": 0,
        "spent": book.account_summary(),
    })
    if count != manifest["development_roots"]:
        raise ValueError("开发根前缀不完整")


def run() -> None:
    """32 墙逐根续打；仅目标窗动作不同，结算当前完整桌。"""
    manifest, frozen = verify()
    ensure_sealed(frozen)
    if read(_project_file(_PROJECT_ROOT, OUT / "capture-summary.json"))["captured"] != 24:
        raise ValueError("尚未完成 24 根开发前缀")
    book = ledger()
    dev = development(frozen)
    complete = 0
    for target in dev:
        for index, key in enumerate(SAMPLE_KEYS, 1):
            path = p84.rollout_path(target, index)
            if path.exists():
                if read(path).get("mechanical_ok") is not True:
                    raise ValueError("旧配对机械门失败：" + str(path))
                complete += 2
                continue
            reservation = book.reserve(
                step_id=f"g2:run:{target['target_id']}:{index:02d}",
                account="tables_full", amount=2,
                note="同暗手同未来墙首动作双臂当前完整桌",
            )
            try:
                row = p84.execute_rollout(target, index, key)
                if row["mechanical_ok"] is not True:
                    raise ValueError("双臂动作机械门失败")
                row["schema"] = "g2-timing-development-rollout/1"
                row["category"] = target["category"]
                row["source_root_id"] = target["source"]["source_root_id"]
                row["mix"] = target["source"]["mix"]
                write(path, row)
                book.settle(reservation, actual=2, note="双臂完整且机械门通过")
            except BaseException:
                book.settle(reservation, usage_unknown=True, note="续打异常，保守按两桌计")
                raise
            complete += 2
            if complete % 64 == 0 or complete == manifest["planned_tables"]:
                print(json.dumps({"completed_tables": complete,
                                  "planned_tables": manifest["planned_tables"]},
                                 ensure_ascii=False), flush=True)
    ensure_sealed(frozen)
    files = list((_project_file(_PROJECT_ROOT, OUT / "rollouts")).glob("*.json"))
    write(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"), {
        "schema": "g2-timing-run-summary/1", "rollout_files": len(files),
        "actual_tables": len(files) * 2, "mechanical_failures": 0,
        "replication_rollouts": 0, "spent": book.account_summary(),
    })
    if len(files) * 2 != manifest["planned_tables"]:
        raise ValueError("G2 开发配对未完整")


def interval(values: list[float], salt: int) -> list[float]:
    """对自然根等权重抽样；未来墙不算独立根。"""
    rng = random.Random(2026092600 + salt)
    draws = sorted(statistics.fmean(rng.choice(values) for _ in values)
                   for _ in range(20000))
    return [draws[500], draws[19499]]


def analyze() -> None:
    """四格根级诊断；只形成机制判读，不在本批宣称发布增益。"""
    manifest, frozen = verify()
    ensure_sealed(frozen)
    summary = read(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"))
    if (summary["actual_tables"] != manifest["planned_tables"]
            or summary["mechanical_failures"] or summary["replication_rollouts"]):
        raise ValueError("G2 机械完成门未过")
    roots = []
    for target in development(frozen):
        rows = [read(p84.rollout_path(target, i)) for i in range(1, ROLLS + 1)]
        if not all(row["mechanical_ok"] and row["source_root_id"] ==
                   target["source"]["source_root_id"] for row in rows):
            raise ValueError("G2 根机械身份失败")
        table = [float(r["focal_current_table_score"]["delta"]) for r in rows]
        local = [float(r["focal_current_round_settlement_delta"]) for r in rows]
        transitions = Counter(r["reference"]["terminal"] + "→" +
                              r["intervention"]["terminal"] for r in rows)
        details = Counter()
        for r in rows:
            for arm in ("reference", "intervention"):
                for detail in r[arm]["details"]:
                    details[arm + ":" + detail] += 1
        roots.append({
            "target_id": target["target_id"], "source_root_id": target["source"]["source_root_id"],
            "mix": target["source"]["mix"], "category": target["category"],
            "family": target["family"], "features": target["features"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "table_delta_mean": statistics.fmean(table),
            "round_delta_mean": statistics.fmean(local),
            "table_delta_first16": statistics.fmean(table[:16]),
            "table_delta_last16": statistics.fmean(table[16:]),
            "round_delta_first16": statistics.fmean(local[:16]),
            "round_delta_last16": statistics.fmean(local[16:]),
            "terminal_transitions": dict(sorted(transitions.items())),
            "settlement_details": dict(sorted(details.items())),
        })
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for root in roots:
        groups[(root["mix"], root["category"])].append(root)
    cells = {}
    for number, ((mix, category), members) in enumerate(sorted(groups.items()), 1):
        if len(members) != 6:
            raise ValueError("四格中独立根数不是 6")
        values = [r["table_delta_mean"] for r in members]
        round_values = [r["round_delta_mean"] for r in members]
        cells[mix + ":" + category] = {
            "independent_roots": len(members),
            "table_delta_root_mean": statistics.fmean(values),
            "table_delta_root_bootstrap_95": interval(values, number),
            "round_delta_root_mean": statistics.fmean(round_values),
            "first16_root_mean": statistics.fmean(r["table_delta_first16"] for r in members),
            "last16_root_mean": statistics.fmean(r["table_delta_last16"] for r in members),
            "positive_roots": sum(x > 0 for x in values),
            "positive_first16_roots": sum(r["table_delta_first16"] > 0 for r in members),
            "positive_last16_roots": sum(r["table_delta_last16"] > 0 for r in members),
            "leave_one_root_out_means": [statistics.fmean(v for j, v in enumerate(values)
                                                         if j != i)
                                         for i in range(len(values))],
        }
    report = {
        "schema": "g2-timing-development-result/1",
        "status": "DEVELOPMENT_LABELS_OPENED_REPLICATION_SEALED",
        "independent_roots": len(roots), "paired_future_walls": len(roots) * ROLLS,
        "complete_tables": summary["actual_tables"], "cells": cells,
        "roots": roots, "replication_labels_opened": False,
        "release_eligible": False,
    }
    write(_project_file(_PROJECT_ROOT, OUT / "result.json"), report)
    print(json.dumps({"status": report["status"], "cells": cells}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify", "capture", "run", "analyze"))
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "verify":
        manifest, frozen = verify()
        ensure_sealed(frozen)
        print(json.dumps({"status": "VERIFIED", "planned_tables": manifest["planned_tables"]},
                         ensure_ascii=False))
    else:
        globals()[args.command]()


if __name__ == "__main__":
    main()
