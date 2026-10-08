#!/usr/bin/env python3
"""G134：G133 逐局旁路与 G131 原三臂完整桌逐桌对拍和收入归因。"""

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

import hashlib
import json
from pathlib import Path

import g14_accounted_paired_panel as g14
import g132_g131_pilot_summary as g132
from g13_hand_accounting import summarize_hands


HERE = Path(__file__).resolve().parent
OLD = g132.RUN
NEW = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g133-g131-hand-accounting-20260928')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g133-g131-hand-accounting-20260928/verification.json')
COMPONENTS = g14.COMPONENTS
ARMS = g132.ARMS


def sha(path: Path) -> str:
    """绑定原桌、新拆账与核验程序原文。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    """核三臂完整身份与零和拆账后才报告 H/M 收入差。"""
    if OUT.exists():
        raise FileExistsError("G134 拆账核验已存在，拒绝覆盖")
    old_manifest = json.loads((OLD / "manifest.json").read_text(encoding="utf-8"))
    new_manifest = json.loads((_project_file(_PROJECT_ROOT, NEW / "manifest.json")).read_text(encoding="utf-8"))
    old_result = json.loads((OLD / "result.json").read_text(encoding="utf-8"))
    new_result = json.loads((_project_file(_PROJECT_ROOT, NEW / "result.json")).read_text(encoding="utf-8"))
    if (not (old_manifest["panel_seed"] == new_manifest["panel_seed"] == 2026123101)
            or not (old_manifest["root_start"] == new_manifest["root_start"] == 1)
            or not (old_manifest["roots_per_mix"] == new_manifest["roots_per_mix"] == 8)
            or not (old_manifest["arms"] == new_manifest["arms"] == list(ARMS))
            or old_manifest["candidate_sources"] != new_manifest["candidate_sources"]
            or not (old_result["complete_tables"] == new_result["complete_tables"] == 384)):
        raise ValueError("G134 原桌/逐局实验清单不相同")
    stage_count = 0
    table_count = 0
    hand_count = 0
    components: dict[tuple[str, int, str, str], list[int]] = {}
    counts: dict[tuple[str, int, str, str], list[int]] = {}
    for mix in ("H", "M"):
        for root in range(1, 9):
            for seat in range(4):
                for arm in ARMS:
                    unit = (mix, root, seat, arm, 2026123101)
                    before = json.loads(g14.paired.unit_path(OLD, unit).read_text(
                        encoding="utf-8"))
                    after = json.loads(g14.paired.unit_path(NEW, unit).read_text(
                        encoding="utf-8"))
                    g14.verify_unit(after, unit=unit, tables_per_stage=2)
                    for field in ("mix", "root_index", "focal_seat", "arm"):
                        if before[field] != after[field]:
                            raise ValueError("G134 阶段身份漂移：" + field)
                    a, b = before["stage"], after["stage"]
                    for field in ("status", "focal_stage_score", "execution_review",
                                  "stage_totals_by_participant", "u_interval"):
                        if a[field] != b[field]:
                            raise ValueError("G134 阶段结果漂移：" + field)
                    if len(a["tables"]) != len(b["tables"]) != 2:
                        raise ValueError("G134 每阶段完整桌数漂移")
                    stage_count += 1
                    for old_table, new_table in zip(a["tables"], b["tables"]):
                        for field in ("table_id", "seed", "scores_by_seat",
                                      "policy_execution"):
                            if old_table[field] != new_table[field]:
                                raise ValueError("G134 桌级身份或策略执行漂移：" + field)
                        for field in ("game_key", "runtime_counts", "completed_hands",
                                      "expected_hands"):
                            if old_table["result"][field] != new_table["result"][field]:
                                raise ValueError("G134 完整桌运行结果漂移：" + field)
                        account = new_table["hand_account"]
                        independent = summarize_hands(
                            new_table["hand_records"], focal_seat=account["focal_seat"],
                            initial_scores=(0, 0, 0, 0),
                            final_scores=new_table["scores_by_seat"], expected_hands=8)
                        if account != independent:
                            raise ValueError("G134 逐局拆账不能独立复算")
                        table_count += 1
                        hand_count += len(new_table["hand_records"])
                        for name in COMPONENTS:
                            components.setdefault((mix, root, arm, name), []).append(account[name])
                        for name in ("plain_self_wins", "special_self_wins", "other_wins", "draws"):
                            counts.setdefault((mix, root, arm, name), []).append(account[name])
    if (stage_count, table_count, hand_count) != (192, 384, 3072):
        raise ValueError("G134 阶段/完整桌/单局数不守恒")
    old_roots = {(row["mix"], row["root_index"]): row
                 for row in old_result["root_clusters"]}
    new_roots = {(row["mix"], row["root_index"]): row
                 for row in new_result["root_clusters"]}
    if set(old_roots) != set(new_roots) or len(old_roots) != 16:
        raise ValueError("G134 根身份不符")
    root_rows = []
    for mix, root in sorted(old_roots):
        for arm in ARMS[1:]:
            expected_net = old_roots[(mix, root)]["delta_vs_baseline_per_table"][arm]
            actual_net = new_roots[(mix, root)]["delta_vs_baseline_per_table"][arm]
            if abs(expected_net - actual_net) > 1e-9:
                raise ValueError("G134 根级净分与原桌不符")
            deltas = {
                name: (sum(components[(mix, root, arm, name)])
                       - sum(components[(mix, root, "r18_v2", name)])) / 8
                for name in COMPONENTS}
            if abs(sum(deltas.values()) - actual_net) > 1e-9:
                raise ValueError("G134 收入分量与净分不守恒")
            win_counts = {
                name: (sum(counts[(mix, root, arm, name)])
                       - sum(counts[(mix, root, "r18_v2", name)])) / 8
                for name in ("plain_self_wins", "special_self_wins", "other_wins", "draws")}
            root_rows.append({"mix": mix, "root_index": root, "arm": arm,
                              "net_delta_per_table": actual_net,
                              "component_delta_per_table": deltas,
                              "outcome_count_delta_per_table": win_counts})
    mean_by_mix = {}
    for mix in ("H", "M"):
        mean_by_mix[mix] = {}
        for arm in ARMS[1:]:
            rows = [row for row in root_rows if row["mix"] == mix and row["arm"] == arm]
            mean_by_mix[mix][arm] = {
                "net_delta_per_table": sum(row["net_delta_per_table"] for row in rows) / 8,
                "component_delta_per_table": {
                    name: sum(row["component_delta_per_table"][name] for row in rows) / 8
                    for name in COMPONENTS},
                "outcome_count_delta_per_table": {
                    name: sum(row["outcome_count_delta_per_table"][name] for row in rows) / 8
                    for name in ("plain_self_wins", "special_self_wins", "other_wins", "draws")},
            }
    result = {
        "schema": "g134-g133-hand-accounting-verification/1",
        "input_sha256": {"old_manifest": sha(OLD / "manifest.json"),
                         "old_result": sha(OLD / "result.json"),
                         "new_manifest": sha(_project_file(_PROJECT_ROOT, NEW / "manifest.json")),
                         "new_result": sha(_project_file(_PROJECT_ROOT, NEW / "result.json")),
                         "script": sha(Path(__file__))},
        "same_stage_table_score_execution": True,
        "stages": stage_count, "complete_tables": table_count,
        "complete_hands": hand_count, "roots": 16,
        "root_rows": root_rows, "mean_by_mix": mean_by_mix,
        "boundary": "同一已看开发根的事后归因，非新候选、新根或独立确认。",
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps({"stages": stage_count, "complete_tables": table_count,
                      "mean_by_mix": mean_by_mix}, ensure_ascii=False,
                     sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
