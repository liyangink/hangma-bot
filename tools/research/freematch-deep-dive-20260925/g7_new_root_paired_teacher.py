#!/usr/bin/env python3
"""G7 新根正差/零差首动作配对教师；规则、前缀和双臂运行复用已冻结实现。"""

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
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import g7_new_root_negative_control_exposure as exposure  # noqa: E402
import g7_first_action_teacher_preflight as teacher  # noqa: E402

OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-new-root-paired-teacher-20260927')
PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G7-NEW-ROOT-PAIRED-TEACHER-PREREG-2026-09-27.md')
SAMPLES = tuple(f"g7-control-future-{index:02d}" for index in range(1, 9))

# 原始教师模块的选择/分析不同于本批，只有精确目标重建和机械执行复用。
teacher.OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-new-root-paired-teacher-20260927')
teacher.PREREG = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/G7-NEW-ROOT-PAIRED-TEACHER-PREREG-2026-09-27.md')
teacher.PILOT_RESULT = exposure.OUT / "result.json"
teacher.PILOT_MANIFEST = exposure.OUT / "manifest.json"
teacher.SAMPLES = SAMPLES
teacher.p84.OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g7-new-root-paired-teacher-20260927')


def selected_rows():
    """按独立根、代理类别和窗口哈希冻结最早目标。"""

    doc = teacher._read(teacher.PILOT_RESULT)
    manifest = teacher._read(teacher.PILOT_MANIFEST)
    if (doc.get("outcome_labels_opened") is not False
            or doc.get("planned_tables") != 192
            or manifest.get("panel_seed") != exposure.PANEL_SEED
            or doc.get("parent_source_sha256")
            != teacher.g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256):
        raise ValueError("新根暴露身份、结果盲状态或父代不符")
    by_root_class = {}
    for row in doc["rows"]:
        if row["delta_2"] != 0 or row["delta_3"] < 0:
            continue
        category = "positive" if row["delta_3"] > 0 else "zero"
        key = (row["source"]["source_root_id"], category)
        if key not in by_root_class or row["hash"] < by_root_class[key]["hash"]:
            by_root_class[key] = row
    coverage = defaultdict(lambda: defaultdict(set))
    for (root, category), row in by_root_class.items():
        coverage[row["group"]][category].add(root)
    if any(len(coverage[mix][category]) < 6
           for mix in ("H", "M") for category in ("positive", "zero")):
        raise ValueError("H/M 正差与零差负控独立根未达到预登记的各 6 根")
    rows = sorted(by_root_class.values(), key=lambda row: (
        row["group"], row["source"]["source_root_id"],
        row["delta_3"] == 0, row["hash"],
    ))
    return rows, {mix: {category: len(coverage[mix][category])
                        for category in ("positive", "zero")}
                  for mix in ("H", "M")}


def prepare() -> None:
    """在结局盲状态重建、核对并冻结最多 48 个首动作双臂目标。"""

    if OUT.exists():
        raise SystemExit("G7 新根教师目录已存在，拒绝覆盖")
    rows, coverage = selected_rows()
    targets = []
    for index, row in enumerate(rows, 1):
        target = teacher._rebuild_target(row, index)
        target["features"]["proxy_class"] = (
            "positive" if row["delta_3"] > 0 else "zero"
        )
        targets.append(target)
    if len(targets) > 48:
        raise ValueError("超过 24 根每根两类的上限")
    OUT.mkdir(parents=True)
    (_project_file(_PROJECT_ROOT, OUT / "snapshots")).mkdir()
    (_project_file(_PROJECT_ROOT, OUT / "rollouts")).mkdir()
    auth = teacher.g1.p83.batch.unified_document(
        batch_label=OUT.name, authorization_id="g7-new-root-paired-teacher-20260927",
        accounts={"prefix_generation": len(targets),
                  "tables_full": len(targets) * len(SAMPLES) * 2},
        issued_by="lead", issued_at_utc=teacher.g1.p83.search.utc_now(),
        legacy_alias=False,
    )
    auth.update({"scope": "24 根最多双类正差/零差，八未来墙当前整桌双臂",
                 "max_model_calls": 0, "confirmation_roots": 0})
    teacher._write(_project_file(_PROJECT_ROOT, OUT / "authorization.json"), auth)
    teacher._write(_project_file(_PROJECT_ROOT, OUT / "targets.json"), {
        "schema": "g7-new-root-teacher-targets/1",
        "targets": targets, "outcome_labels_opened": False,
    })
    closure = [Path(__file__), PREREG, Path(exposure.__file__),
               teacher.PILOT_RESULT, teacher.PILOT_MANIFEST,
               Path(teacher.__file__), Path(teacher.pilot.__file__),
               Path(teacher.g1.__file__), Path(teacher.overlap.__file__),
               Path(teacher.g7.__file__), _project_file(_PROJECT_ROOT, OUT / "authorization.json"),
               _project_file(_PROJECT_ROOT, OUT / "targets.json"), *teacher.p84.source_paths()]
    teacher._write(_project_file(_PROJECT_ROOT, OUT / "manifest.json"), {
        "schema": "g7-new-root-paired-teacher-manifest/1",
        "created_at_utc": teacher.g1.p83.search.utc_now(),
        "runtime": teacher.g1.p83.guard.capture(source_paths=closure),
        "pilot_result_sha256": teacher._sha(teacher.PILOT_RESULT),
        "pilot_manifest_sha256": teacher._sha(teacher.PILOT_MANIFEST),
        "parent_sha256": teacher.g1.p83.R18_INTEGRATED_POSITIVE_V2_SHA256,
        "targets_sha256": teacher._sha(_project_file(_PROJECT_ROOT, OUT / "targets.json")),
        "roots": len(targets),
        "independent_source_roots": len({target["source"]["source_root_id"]
                                         for target in targets}),
        "coverage": coverage,
        "future_walls": len(SAMPLES), "sample_keys": SAMPLES,
        "planned_tables": len(targets) * len(SAMPLES) * 2,
        "outcome_labels_opened": False, "release_eligible": False,
    })
    print(json.dumps({"targets": len(targets), "coverage": coverage,
                      "planned_tables": len(targets) * len(SAMPLES) * 2},
                     ensure_ascii=False))


def analyze() -> None:
    """按独立根与代理类别汇总，并保留全部目标局终止与番分事实。"""

    manifest, targets = teacher._verify()
    if (_project_file(_PROJECT_ROOT, OUT / "result.json")).exists():
        raise SystemExit("教师结果已存在，拒绝覆盖")
    if teacher._read(_project_file(_PROJECT_ROOT, OUT / "run-summary.json"))["completed_tables"] != manifest["planned_tables"]:
        raise ValueError("双臂完整桌未跑满")
    rows = []
    for target in targets:
        deltas = []
        rounds = []
        terminal = Counter()
        focal_wins = {"reference": Counter(), "intervention": Counter()}
        for index in range(1, len(SAMPLES)+1):
            result = teacher._read(teacher.p84.rollout_path(target, index))
            if result.get("mechanical_ok") is not True:
                raise ValueError("双臂机械门失败")
            deltas.append(result["focal_current_table_score"]["delta"])
            rounds.append(result["focal_current_round_settlement_delta"])
            terminal[result["reference"]["terminal"] + "->" +
                     result["intervention"]["terminal"]] += 1
            for arm in ("reference", "intervention"):
                record = result[arm]
                if record["terminal"] == "focal_hu":
                    focal_wins[arm][json.dumps({"fan": record["fan"],
                                                "details": record["details"]},
                                               ensure_ascii=False, sort_keys=True)] += 1
        rows.append({
            "target_id": target["target_id"],
            "source_root_id": target["source"]["source_root_id"],
            "mix": target["source"]["mix"],
            "proxy_class": target["features"]["proxy_class"],
            "delta_3": target["features"]["delta_3"],
            "whites": target["features"]["whites"],
            "reference_action": target["reference_action"],
            "intervention_action": target["intervention_action"],
            "table_delta_mean": statistics.mean(deltas),
            "target_round_delta_mean": statistics.mean(rounds),
            "table_deltas": deltas,
            "terminal_transitions": dict(sorted(terminal.items())),
            "focal_win_details": {arm: dict(sorted(counts.items()))
                                  for arm, counts in focal_wins.items()},
        })
    summary = {}
    for mix in ("H", "M"):
        summary[mix] = {}
        for category in ("positive", "zero"):
            subset = [row for row in rows if row["mix"] == mix
                      and row["proxy_class"] == category]
            table_values = [row["table_delta_mean"] for row in subset]
            round_values = [row["target_round_delta_mean"] for row in subset]
            if not table_values:
                raise ValueError("预登记类别缺少目标")
            leave_one_out = [statistics.mean(table_values[:i]+table_values[i+1:])
                             for i in range(len(table_values))] if len(table_values) > 1 else []
            summary[mix][category] = {
                "independent_roots": len(subset),
                "table_root_mean": statistics.mean(table_values),
                "target_round_root_mean": statistics.mean(round_values),
                "table_root_positive": sum(value > 0 for value in table_values),
                "table_root_zero": sum(value == 0 for value in table_values),
                "table_root_negative": sum(value < 0 for value in table_values),
                "table_leave_one_root_out_min": min(leave_one_out) if leave_one_out else None,
                "max_abs_single_future_wall_delta": max(
                    abs(value) for row in subset for value in row["table_deltas"]),
            }
    output = {
        "schema": "g7-new-root-paired-teacher-result/1",
        "rows": rows, "by_mix_and_proxy_class": summary,
        "completed_tables": manifest["planned_tables"],
        "independence_unit": "source_root_id", "release_eligible": False,
        "note": "正差/零差不同状态；负控仅检验代理辨识，不是严格因果差",
    }
    teacher._write(_project_file(_PROJECT_ROOT, OUT / "result.json"), output)
    print(json.dumps(summary, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "capture", "run", "analyze"))
    args = parser.parse_args()
    {"prepare": prepare, "capture": teacher.capture,
     "run": teacher.run, "analyze": analyze}[args.command]()


if __name__ == "__main__":
    main()
