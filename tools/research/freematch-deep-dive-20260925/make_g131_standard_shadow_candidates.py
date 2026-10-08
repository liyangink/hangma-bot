#!/usr/bin/env python3
"""从冻结 R18 v2 机械生成两档普通型影子宽度研究候选。"""

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

from pathlib import Path

from hangma_bot.policy.action_value_executor import static_check
from hangma_bot.policy.r18_integrated_positive_v2 import R18_INTEGRATED_POSITIVE_V2_SOURCE


HERE = Path(__file__).resolve().parent
TARGETS = (
    ("G131-STANDARD-SHADOW-LOW-V1.py", 1.0, 0.125),
    ("G131-STANDARD-SHADOW-HIGH-V1.py", 2.0, 0.25),
)

WRAPPER = '''

def score_actions(view):
    """保留 R18 v2 全部原评分，只追加规则事实已知的普通型影子宽度。"""
    result = r18_parent_score_actions(view)
    if result.get("status") != "SCORED":
        return result
    visible = view.get("visible_state")
    actions = view.get("actions")
    if visible is None or actions is None or visible.get("phase") != "draw":
        return result
    seat = visible.get("seat")
    melds = visible.get("melds")
    hand = visible.get("my_hand")
    if (seat is None or seat is True or seat is False or seat < 0 or seat > 3
            or melds is None or hand is None):
        return result
    if len(melds) != 4 or len(melds[seat]) != 0:
        return result
    drawn = visible.get("drawn_tile")
    white_count = hand.count("白")
    if drawn == "白" and len(hand) != 14:
        white_count += 1
    if white_count != 1:
        return result
    eligible = []
    for action in actions:
        if (action.get("action_type") != "discard" or action.get("is_legal") is not True
                or action.get("fact_kind") != "hand_progress"):
            continue
        standard = action.get("standard_shanten_after")
        seven = action.get("seven_pairs_shanten_after")
        std_tiles = action.get("standard_useful_tiles")
        seven_tiles = action.get("seven_pairs_useful_tiles")
        if (standard is None or standard is True or standard is False
                or standard not in (1, 2, 3)
                or seven is None or seven is True or seven is False
                or seven < 0 or seven >= standard
                or std_tiles is None or seven_tiles is None):
            continue
        std_capacity = 0
        seven_capacity = 0
        valid = True
        for tile in std_tiles:
            remaining = tile.get("remaining_estimate")
            if remaining is None or remaining is True or remaining is False or remaining < 0:
                valid = False
                break
            std_capacity += remaining
        if not valid:
            continue
        for tile in seven_tiles:
            remaining = tile.get("remaining_estimate")
            if remaining is None or remaining is True or remaining is False or remaining < 0:
                valid = False
                break
            seven_capacity += remaining
        if not valid:
            continue
        key = action.get("action_key")
        group = (standard, seven)
        eligible.append((key, group, len(std_tiles), std_capacity, seven_capacity))
    if not eligible:
        return result
    entries = []
    changed = False
    for entry in result["entries"]:
        key = entry.get("action_key")
        bonus = 0.0
        for item in eligible:
            if item[0] == key:
                group, codes, capacity, seven_capacity = item[1:]
                maximum = seven_capacity
                for other in eligible:
                    if other[1] == group and other[4] > maximum:
                        maximum = other[4]
                if seven_capacity + 2 >= maximum:
                    bonus = min(120.0, __CODE_WEIGHT__ * codes + __CAP_WEIGHT__ * capacity)
                break
        trace = dict(entry.get("trace") or {}, g131_standard_shadow={
            "version": "g131-standard-shadow-v1", "bonus": bonus,
            "scope": "one_white_no_meld_seven_closer"})
        entries.append({"action_key": key, "score": entry["score"] + bonus,
                        "trace": trace})
        if bonus != 0.0:
            changed = True
    if not changed:
        return result
    return {"status": "SCORED", "entries": entries,
            "reason": result.get("reason", "") + "；G131 普通型影子宽度已按七对容量门控计分"}
'''


def main() -> None:
    """要求父代唯一入口、静态合规、目标文件均未存在才写源码。"""
    source = R18_INTEGRATED_POSITIVE_V2_SOURCE
    marker = "def score_actions(view):"
    if source.count(marker) != 1:
        raise ValueError("G131 冻结父代入口不唯一")
    parent = source.replace(marker, "def r18_parent_score_actions(view):", 1)
    created = []
    for name, code_weight, cap_weight in TARGETS:
        body = (WRAPPER.replace("__CODE_WEIGHT__", repr(code_weight))
                       .replace("__CAP_WEIGHT__", repr(cap_weight)))
        candidate = parent + body
        compile(candidate, name, "exec")
        static_check(candidate)
        path = _project_file(_PROJECT_ROOT, HERE / "candidates" / name)
        if path.exists():
            raise FileExistsError("G131 候选已存在，拒绝覆盖：" + name)
        created.append((path, candidate))
    for path, source in created:
        path.write_text(source, encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
