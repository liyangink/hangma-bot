#!/usr/bin/env python3
"""G75：按本局曾吃碰与终胡前末次弃牌来源拆分同房胡牌路线。"""

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
import random


HERE = Path(__file__).resolve().parent
ROUND_SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g69-same-room-route-chain-20260928/claim_terminal_rounds.jsonl.gz')
WIN_SOURCE = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g72-win-route-provenance-20260928/result.json')
OUTPUT = _project_file(_PROJECT_ROOT, 'review/freematch-deep-dive-20260925/evidence/g75-claim-lifecycle-attribution-20260928/result.json')
PEERS = {"xuanwu_2346": 15, "tengshe_0638": 17}
REPLICATES = 20_000


def key(row: dict) -> tuple[str, str, str, str, int]:
    """同房、同座、同单局的唯一键；强手重合房保留两个独立对照单位。"""
    return row["peer"], row["actor"], row["room"], row["game_id"], row["round_no"]


def percentile(values: list[float], proportion: float) -> float:
    """对房级自助采样给出描述性分位数，不解释为因果区间。"""
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * proportion)]


def main() -> None:
    if OUTPUT.exists():
        raise SystemExit("G75 证据已存在，拒绝覆盖")
    round_rows = [json.loads(line) for line in gzip.open(ROUND_SOURCE, "rt", encoding="utf-8")]
    wins = json.loads(WIN_SOURCE.read_text(encoding="utf-8"))["rows"]
    if len(round_rows) != 5_120 or len(wins) != 1_361:
        raise ValueError("G69/G72 冻结输入漂移")
    win_index = {key(row): row for row in wins}
    if len(win_index) != len(wins):
        raise ValueError("胡牌单局键重复")
    room_counts: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    initial_white_counts: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    found_wins = set()
    for row in round_rows:
        counts = room_counts[(row["peer"], row["room"], row["actor"])]
        white_group = "start_white_0" if row["initial_white"] == 0 else "start_white_1plus"
        stratum_counts = initial_white_counts[(row["peer"], row["actor"], white_group)]
        counts["rounds"] += 1
        stratum_counts["rounds"] += 1
        any_chi_peng = row["own_chi"] + row["own_peng"] > 0
        counts["chi_peng_events"] += row["own_chi"] + row["own_peng"]
        counts["chi_peng_rounds"] += any_chi_peng
        stratum_counts["chi_peng_rounds"] += any_chi_peng
        won = win_index.get(key(row))
        if won is None:
            if row["status"] == "win":
                raise ValueError("官方获胜单局缺 G72 溯源")
            continue
        found_wins.add(key(row))
        if row["status"] != "win" or row["fan"] != won["fan"]:
            raise ValueError("G69/G72 番数或终局状态不一致")
        last_claim = won["origin"] in ("chi", "peng")
        if last_claim and not any_chi_peng:
            raise ValueError("末次弃牌来自吃碰，但本局吃碰数为零")
        if won["origin"] != "tile_drawn" and not last_claim:
            raise ValueError("意外的终胡前末次弃牌来源")
        fan_group = "high" if won["fan"] >= 2 else "plain"
        if won["fan"] < 1:
            raise ValueError("获胜番数非正")
        route = "claim_last" if last_claim else ("claim_then_draw" if any_chi_peng else "no_chi_peng")
        counts[f"{fan_group}_{route}"] += 1
        stratum_counts[f"{fan_group}_{route}"] += 1
    if found_wins != set(win_index):
        raise ValueError("G72 胡牌行未完整匹配")

    totals = {}
    room_deltas = {}
    intervals = {}
    categories = ("chi_peng_events", "chi_peng_rounds", "high_claim_last",
                  "high_claim_then_draw", "high_no_chi_peng", "plain_claim_last",
                  "plain_claim_then_draw", "plain_no_chi_peng")
    rng = random.Random(20260928)
    for peer, room_count in PEERS.items():
        rooms = sorted({room for name, room, _ in room_counts if name == peer})
        if len(rooms) != room_count:
            raise ValueError("同房强手房数漂移")
        paired = []
        for room in rooms:
            peer_counts = room_counts[(peer, room, "peer")]
            us_counts = room_counts[(peer, room, "us")]
            if peer_counts["rounds"] != 80 or us_counts["rounds"] != 80:
                raise ValueError("同房双方不是各 80 个单局")
            paired.append({"room": room, "peer": dict(peer_counts), "us": dict(us_counts),
                           "peer_minus_us": {k: peer_counts[k] - us_counts[k] for k in categories}})
        totals[peer] = {
            actor: {k: sum(room_counts[(peer, room, actor)][k] for room in rooms)
                    for k in ("rounds",) + categories}
            for actor in ("peer", "us")
        }
        room_deltas[peer] = paired
        intervals[peer] = {}
        for category in ("high_claim_last", "high_claim_then_draw", "high_no_chi_peng"):
            samples = [sum(paired[rng.randrange(room_count)]["peer_minus_us"][category]
                           for _ in rooms) / (80 * room_count) * 100
                       for _ in range(REPLICATES)]
            intervals[peer][category] = [percentile(samples, 0.025), percentile(samples, 0.975)]
        if sum(totals[peer]["peer"]["high_" + category] for category in
               ("claim_last", "claim_then_draw", "no_chi_peng")) != (
                   108 if peer == "xuanwu_2346" else 140):
            raise ValueError("强手高番终局合计未对齐 G60")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": "g75-claim-lifecycle-attribution/1", "exploratory": True,
               "source_sha256": {"rounds": hashlib.sha256(ROUND_SOURCE.read_bytes()).hexdigest(),
                                 "wins": hashlib.sha256(WIN_SOURCE.read_bytes()).hexdigest()},
               "room_units": room_deltas, "totals": totals,
               "initial_white_strata": {
                   peer: {actor: {group: dict(initial_white_counts[(peer, actor, group)])
                                 for group in ("start_white_0", "start_white_1plus")}
                          for actor in ("peer", "us")}
                   for peer in PEERS},
               "room_bootstrap_replicates": REPLICATES,
               "room_bootstrap_seed": 20260928, "room_bootstrap_95_percent": intervals,
               "boundary": "本局曾吃碰是策略影响的赛后条件，末次弃牌来源也不是因果归因；"
                           "每类除以全体单局仅为同房描述，除以吃碰局会有选择偏差。"}
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"totals": totals, "intervals": intervals}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
