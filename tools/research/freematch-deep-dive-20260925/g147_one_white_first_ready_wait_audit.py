#!/usr/bin/env python3
"""G147：首次一白普通听牌窗口的普通胡等待面与父代同窗选择。"""

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

import g138_official_plain_baotou_opportunity as g138
import g61_strong_draw_batch as g61
import g69_route_chain_analysis as g69
from hangma_bot.kernel.serialization import observation_from_json


HERE = Path(__file__).resolve().parent
G69_WINDOWS = g69.G69 / "route_windows.jsonl.gz"
G145 = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g145-opportunity-exposure-and-entry-20260928/result.json')
OUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g147-one-white-first-ready-wait-20260928/result.json')


def sha(path: Path) -> str:
    """计算冻结官方证据与本程序的字节摘要。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row: dict, peer: str, room: str, actor: str) -> tuple:
    """唯一标识一个本人已确认正常摸打窗口。"""
    return (peer, room, row["game_id"], row["round_no"], actor,
            row["draw_seq"])


def main() -> None:
    """首次普通胡入口仅按已经冻结的 G69 行动前事实选择。"""
    if OUT.exists():
        raise FileExistsError("G147 已有结果，拒绝覆盖")
    first_by_hand = {}
    with gzip.open(G69_WINDOWS, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            hand = (row["peer"], row["room"], row["game_id"],
                    row["round_no"], row["actor"])
            if row["actual"]["plain_capacity"] > 0:
                prior = first_by_hand.get(hand)
                if prior is None or row["draw_seq"] < prior["draw_seq"]:
                    first_by_hand[hand] = row
    expected = json.loads(G145.read_text(encoding="utf-8"))["peers"]
    wanted = {key(row, hand[0], hand[1], hand[4]): row
              for hand, row in first_by_hand.items() if row["white_before"] == 1}
    for peer, item in expected.items():
        for actor, facts in item["actors"].items():
            observed = sum(k[0] == peer and k[4] == actor for k in wanted)
            if observed != facts["first_plain_ready_by_white"]["1"]:
                raise ValueError("G145 首次一白普通胡入口数漂移")

    counters: dict[str, Counter] = defaultdict(Counter)
    source_hashes = {}
    seen = set()
    for peer, room in sorted({(k[0], k[1]) for k in wanted}):
        for actor, path in (
            ("peer", g61.room_dir((peer, room)) / "windows.json"),
            ("us", g69.G69 / "rooms" / room / "windows.json.gz"),
        ):
            rows, source_hashes[f"{peer}/{room}/{actor}"] = g69.load_windows(path)
            for row in rows:
                marker = key(row, peer, room, actor)
                if marker not in wanted:
                    continue
                if marker in seen:
                    raise ValueError("G147 首次入口窗口重复")
                seen.add(marker)
                observation = observation_from_json(row["observation"])
                rules = g138.c31.RULES.analyze(
                    observation, value_limits=g138.c31.VALUE_LIMITS)
                discards = {candidate.action_key: candidate
                            for candidate in rules.legal_candidates
                            if candidate.action_key.startswith("discard:")}
                capacities = {}
                for action_key, candidate in discards.items():
                    fact, complete = g138.action_opportunity(candidate)
                    if not complete:
                        raise ValueError("G147 合法弃牌一摸条件路线不完整")
                    capacities[action_key] = fact["plain"]
                actual = row["actual_action"]
                if actual not in capacities or capacities[actual] != wanted[marker][
                        "actual"]["plain_capacity"]:
                    raise ValueError("G147 官方弃牌普通胡容量与 G69 不同")
                counter = counters[f"{peer}/{actor}"]
                counter["first_ready_one_white_windows"] += 1
                counter["actual_plain_capacity_sum"] += capacities[actual]
                counter["actual_below_legal_max"] += capacities[actual] < max(
                    capacities.values())
                if actor == "peer":
                    parent = row["parent_top_action"]
                    if parent in capacities:
                        counter["parent_discard_known"] += 1
                        counter["peer_parent_different"] += parent != actual
                        counter["peer_plain_capacity_gt_parent"] += (
                            capacities[actual] > capacities[parent])
                        counter["peer_plain_capacity_lt_parent"] += (
                            capacities[actual] < capacities[parent])
                        counter["parent_below_legal_max"] += (
                            capacities[parent] < max(capacities.values()))
                    else:
                        counter["parent_not_legal_discard"] += 1
    if seen != wanted.keys():
        raise ValueError("G147 首次一白普通胡入口未全量复核")
    result = {
        "schema": "g147-one-white-first-ready-wait/1",
        "inputs_sha256": {"g69_windows": sha(G69_WINDOWS),
                          "g145": sha(G145),
                          "g138_result": sha(g138.OUT),
                          "hangma_value_analysis": sha(
                              _project_file(_PROJECT_ROOT, HERE.parents[1] / "src/hangma_bot/hangma/value_analysis.py")),
                          "script": sha(Path(__file__))},
        "window_source_sha256": source_hashes,
        "groups": {name: dict(value) for name, value in sorted(counters.items())},
        "boundary": "首次普通胡入口为赛后识别的本人历史状态，行动前可见事实只用于同窗规则重判；强手动作和后续首次爆头均非反事实收益标签。公开未见容量不是牌墙概率。",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    print(json.dumps(result["groups"], ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
