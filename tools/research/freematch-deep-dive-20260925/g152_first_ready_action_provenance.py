#!/usr/bin/env python3
"""G152：核对强手一白普通听牌首次动作与冻结父代在同一观察的首选。"""

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
import gzip
import hashlib
import json
from pathlib import Path

import g151_one_white_ready_lifecycle as g151
import g145_opportunity_exposure_and_entry_audit as g145


HERE = Path(__file__).resolve().parent
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g152-first-ready-action-provenance-20260928/result.json')


def sha(path: Path) -> str:
    """绑定已冻结的官方窗口和 G151 行动链字节。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row: dict) -> tuple:
    """强手同房某座位单局中的一个已确认正常摸打窗口。"""
    return (row["peer"], row["room"], row["game_id"], row["round_no"],
            row["actor"], row["draw_seq"])


def main() -> None:
    """不读取未来牌山；G151 后续机会只用于历史分层而非在线输入。"""
    if OUT.exists():
        raise FileExistsError("G152 已有证据，拒绝覆盖")
    windows = {}
    for row in g145.lines(g145.G69_WINDOWS):
        marker = key(row)
        if marker in windows:
            raise ValueError("G69 窗口重复")
        windows[marker] = row
    if len(windows) != 36080:
        raise ValueError("G69 窗口数漂移")
    groups: dict[str, Counter] = defaultdict(Counter)
    rooms: dict[str, set[str]] = defaultdict(set)
    selected = 0
    with gzip.open(g151.ROWS, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            selected += 1
            if row["actor"] != "peer":
                continue
            marker = (row["peer"], row["room"], row["game_id"],
                      row["round_no"], row["actor"], row["first_draw_seq"])
            first = windows.get(marker)
            if first is None or first["white_before"] != 1 or first[
                    "actual"]["plain_capacity"] <= 0:
                raise ValueError("G151 首次一白普通听牌动作无法与 G69 对账")
            parent = first["parent_action"]
            actual = first["actual_action"]
            state = ("same" if parent == actual else
                     "different_discard" if parent.startswith("discard:")
                     else "different_non_discard")
            if state == "different_discard" and first["parent"] is None:
                raise ValueError("父代另弃牌缺少 G69 规则事实")
            for suffix in ("all", "later_baotou" if row[
                    "first_baotou_after_ready"] else "no_later_baotou"):
                name = f"{row['peer']}/{suffix}"
                groups[name]["hands"] += 1
                groups[name][state] += 1
                rooms[name].add(row["room"])
    if selected != 1372:
        raise ValueError("G151 首次一白入口数量漂移")
    for peer, expected in (("xuanwu_2346", 343), ("tengshe_0638", 365)):
        all_group = groups[f"{peer}/all"]
        if all_group["hands"] != expected or all_group["hands"] != sum(
                all_group[state] for state in
                ("same", "different_discard", "different_non_discard")):
            raise ValueError("强手首次一白入口动作分类不守恒")
    result = {
        "schema": "g152-first-ready-action-provenance/1",
        "exploratory": True,
        "source_sha256": {"g151_result": sha(g151.RESULT),
                          "g151_rows": sha(g151.ROWS),
                          "g69_windows": sha(g145.G69_WINDOWS),
                          "script": sha(Path(__file__))},
        "groups": {name: {**dict(sorted(counter.items())),
                          "rooms": len(rooms[name])}
                   for name, counter in sorted(groups.items())},
        "boundary": "同一可见观察的首次普通听牌动作一致性；强手后续机会由赛后路径分层，不能推断父代能到达该手牌，也不能归因于当前动作。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=False)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True,
                              indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["groups"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
