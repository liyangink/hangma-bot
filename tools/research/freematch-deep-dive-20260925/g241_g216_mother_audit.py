#!/usr/bin/env python3
"""G241：按物理摸牌定义复核冻结 G216 母体，不修改旧证据。"""

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

from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import g216_visible_reach_calibration as old_measure
import g241_multi_action_competing_reach as corrected


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g241-g216-mother-audit-20260929/result.json')


def _key(row: dict, table_id: str | None = None) -> tuple:
    """用官方事件和动作身份关联两次同牌山父代运行。"""
    return (table_id if table_id is not None else row["table_id"],
            row["round_no"], row["trigger_seq"], row["chosen_action"])


def run_unit(unit: tuple[str, int, int]) -> dict:
    """同源重跑旧阶段，逐桌对账后只纠正旧母体和后继类别。"""
    mix, root, seat = unit
    contract = json.loads(corrected.panel.paired.CONTRACT.read_text(encoding="utf-8"))
    plans = corrected.panel.natural.build_seat_stage_plans(
        contract=contract, opponent=mix, root_index=root, focal_seat=seat,
        panel_seed=old_measure.SEED)
    captured: list[dict] = []

    def factory(monotonic: Any) -> corrected.CapturingPolicy:
        return corrected.CapturingPolicy(corrected.parent.parent_factory(monotonic),
                                         captured)

    stage = corrected.accounted.run_accounted_stage(
        plans=plans, candidate_policy_factory=factory,
        opponent_policies=contract["panel"]["opponent_scenarios"][mix][
            "opponent_policies"],
        versions_block=corrected.panel.natural.stage.contract_versions_block(contract),
        step_limit=int(contract["stop"]["step_limit"]),
        value_limits=corrected.panel.paired.LIMITS)
    source_path = old_measure.stage_path(mix, root, seat)
    old = json.loads(source_path.read_text(encoding="utf-8"))
    if stage["status"] != "complete" or len(stage["tables"]) != 2:
        raise ValueError("G216 同源重跑阶段未完成")
    for left, right in zip(stage["tables"], old["stage"]["tables"]):
        for key in ("table_id", "seed", "scores_by_seat", "policy_execution",
                    "hand_account", "hand_records"):
            if left[key] != right[key]:
                raise ValueError(f"G216 同源父代 {unit} 的 {key} 不恒等")
        if left["result"]["runtime_counts"] != right["result"]["runtime_counts"]:
            raise ValueError("G216 同源父代运行计数不恒等")
    timeline = defaultdict(list)
    capture_map = {}
    for row in captured:
        table_id = corrected._table_id(row)
        timeline[(table_id, row["round_no"])].append(row)
        if row["phase"] == "draw" and row["chosen_action"].startswith("discard:"):
            key = _key(row, table_id)
            if key in capture_map:
                raise ValueError("G216 同源弃牌决策键重复")
            capture_map[key] = row
    old_labels = old["normal_discard_labels"]
    replay_roots = set(capture_map)
    old_roots = {_key(row) for row in old_labels}
    if len(old_roots) != len(old_labels) or old_roots != replay_roots:
        raise ValueError("G216 同源正常弃牌根不恒等")
    terminal_by_hand = {}
    for table in stage["tables"]:
        focal = table["hand_account"]["focal_seat"]
        for hand in table["hand_records"]:
            terminal_by_hand[(table["table_id"], hand["round_no"])] = (
                corrected.g216._terminal(hand, focal))
    position = {}
    for hand_key, rows in timeline.items():
        rows.sort(key=lambda row: row["order"])
        for index, row in enumerate(rows):
            if row["phase"] == "draw" and row["chosen_action"].startswith("discard:"):
                position[_key(row, hand_key[0])] = (rows, index)
    counts = Counter()
    before = Counter()
    after = Counter()
    mismatch_samples = []
    for old_row in old_labels:
        key = _key(old_row)
        row = capture_map[key]
        before[old_row["first_successor"]] += 1
        counts["old_windows"] += 1
        if old_row["white_before"] != row["white_before"]:
            counts["white_count_changed_all"] += 1
        if row["drawn_tile"] is None:
            counts["excluded_no_draw_followup"] += 1
            continue
        if row["gang_draw"]:
            counts["excluded_gang_replacement_draw"] += 1
            continue
        counts["physical_normal_draw_windows"] += 1
        if old_row["white_before"] != row["white_before"]:
            counts["white_count_changed_kept"] += 1
        rows, index = position[key]
        future = corrected._future_events(
            rows, index, terminal_by_hand[(key[0], key[1])])
        first = next((item["kind"] for item in future["events"]
                      if item["kind"] != "no_draw_followup_discard"), None)
        category = {"own_draw": "next_own_draw", "own_claim": "own_claim",
                    "own_win": "own_win", "other_win": "other_win",
                    "draw": "draw"}.get(first)
        if category is None:
            raise ValueError("G216 纠正后的首后继未知")
        after[category] += 1
        if category != old_row["first_successor"]:
            counts["first_successor_changed_kept"] += 1
            if len(mismatch_samples) < 12:
                mismatch_samples.append({"table_id": key[0], "round_no": key[1],
                                         "trigger_seq": key[2],
                                         "old": old_row["first_successor"],
                                         "corrected": category})
    if (counts["physical_normal_draw_windows"]
            + counts["excluded_no_draw_followup"]
            + counts["excluded_gang_replacement_draw"] != counts["old_windows"]):
        raise ValueError("G216 母体分解不守恒")
    return {"mix": mix, "root_index": root, "start_seat": seat,
            "source_stage_sha256": sha256(source_path.read_bytes()).hexdigest(),
            "paired_tables": 2, "counts": dict(counts),
            "old_first_successor": dict(before),
            "corrected_first_successor": dict(after),
            "mismatch_samples": mismatch_samples}


def main() -> None:
    """八个独立根各四座同源复跑，保留分根证据与总体守恒。"""
    units = [(mix, root, seat) for mix in old_measure.MIXES
             for root in old_measure.ROOTS for seat in old_measure.SEATS]
    results = []
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(run_unit, unit): unit for unit in units}
        for future in as_completed(futures):
            unit = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                raise RuntimeError(f"G216 母体复核阶段失败：{unit}") from exc
    results.sort(key=lambda row: (row["mix"], row["root_index"], row["start_seat"]))
    summary = {}
    for mix in old_measure.MIXES:
        group = [row for row in results if row["mix"] == mix]
        merged = Counter()
        before = Counter()
        after = Counter()
        for row in group:
            merged.update(row["counts"])
            before.update(row["old_first_successor"])
            after.update(row["corrected_first_successor"])
        summary[mix] = {"counts": dict(merged),
                        "old_first_successor": dict(before),
                        "corrected_first_successor": dict(after)}
    value = {"schema": "g241-g216-mother-audit/1",
             "old_result_sha256": sha256(old_measure.OUT.joinpath("result.json").read_bytes()).hexdigest(),
             "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
             "units": results, "by_mix": summary,
             "boundary": "只修正 G216 父代观察母体；不估计备选弃牌因果收益。"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        raise FileExistsError(OUT)
    OUT.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
                   + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
