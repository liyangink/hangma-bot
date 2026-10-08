#!/usr/bin/env python3
"""G241：按公开墙余与实持白板数分层三次物理摸牌可达性。"""

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
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean, stdev

import g241_multi_action_competing_reach as g241


OUT = g241.OUT / "strata.json"


def wall_bin(value: int | None) -> str:
    """固定公开剩余牌墙张数分箱，不读取真实未来牌墙。"""
    if value is None:
        return "unknown"
    for upper in (32, 48, 64, 80, 96):
        if value <= upper:
            return f"<= {upper}"
    return "> 96"


def white_bin(value: int) -> str:
    """白板数超过两张时合并稀疏层，避免伪精度。"""
    return str(value) if value < 3 else ">= 3"


def describe(rows: list[dict]) -> dict:
    """窗口数描述经验路径，方差只以独立牌山根为单位。"""
    by_root = defaultdict(list)
    for row in rows:
        by_root[row["root_index"]].append(row)
    rates = [mean(row["third_own_draw_reached"] for row in group)
             for group in by_root.values()]
    return {
        "windows": len(rows), "independent_roots_with_coverage": len(by_root),
        "first_successor": dict(sorted(Counter(
            row["first_successor"] for row in rows).items())),
        "third_own_draw_reached": sum(row["third_own_draw_reached"] for row in rows),
        "window_weighted_third_reach_rate": mean(
            row["third_own_draw_reached"] for row in rows),
        "root_equal_third_reach_rate": mean(rates),
        "root_rate_standard_deviation": stdev(rates) if len(rates) > 1 else None,
        "own_claim_windows_before_horizon": sum(
            row["own_claims_before_horizon"] > 0 for row in rows),
        "no_draw_followup_windows_before_horizon": sum(
            row["no_draw_followups_before_horizon"] > 0 for row in rows),
        "no_draw_followup_events": sum(
            row["no_draw_followups_before_horizon"] for row in rows),
        "no_draw_gang_events": sum(
            row["no_draw_gangs_before_horizon"] for row in rows),
    }


def main() -> None:
    """读取冻结阶段，校验逐文件摘要后写入唯一分层证据。"""
    source_path = g241.OUT / "result.json"
    result = json.loads(source_path.read_text(encoding="utf-8"))
    rows = []
    for name, expected_hash in result["stage_sha256"].items():
        path = g241.OUT / "stages" / name
        if sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError("G241 阶段文件摘要不符：" + name)
        stage = json.loads(path.read_text(encoding="utf-8"))
        rows.extend({"mix": stage["mix"], "root_index": stage["root_index"],
                     "start_seat": stage["start_seat"], **row}
                    for row in stage["normal_discard_labels"])
    if len(rows) != result["normal_discard_windows"]:
        raise ValueError("G241 分层母体与冻结汇总不一致")
    grouped = {mix: {"by_wall": defaultdict(list), "by_white": defaultdict(list)}
               for mix in g241.MIXES}
    for row in rows:
        grouped[row["mix"]]["by_wall"][wall_bin(row["remaining_tile_count"])].append(row)
        grouped[row["mix"]]["by_white"][white_bin(row["white_before"])].append(row)
    unique_future = {mix: {"no_draw_followup_discard": set(),
                           "no_draw_followup_gang": set()} for mix in g241.MIXES}
    for row in rows:
        for event in row["events"]:
            kind = ("no_draw_followup_gang" if event["kind"] == "own_claim"
                    and event.get("on_no_draw_followup")
                    else event["kind"])
            if kind in unique_future[row["mix"]]:
                unique_future[row["mix"]][kind].add(
                    (row["root_index"], row["start_seat"], event["decision_id"]))
    strata = {}
    for mix in g241.MIXES:
        strata[mix] = {
            axis: {key: describe(group) for key, group in sorted(bins.items())}
            for axis, bins in grouped[mix].items()}
    value = {"schema": "g241-competing-reach-strata/1",
             "source_result_sha256": sha256(source_path.read_bytes()).hexdigest(),
             "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
             "by_mix": strata,
             "distinct_future_event_ids_by_mix": {
                 mix: {kind: len(identities) for kind, identities in kinds.items()}
                 for mix, kinds in unique_future.items()},
             "boundary": "父代实际路径的描述性分层；根内窗口高度相关。"}
    if OUT.exists():
        raise FileExistsError(OUT)
    OUT.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
                   + "\n", encoding="utf-8")
    print(json.dumps({mix: {axis: {key: item["windows"]
                                   for key, item in bins.items()}
                            for axis, bins in group.items()}
                      for mix, group in strata.items()}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
