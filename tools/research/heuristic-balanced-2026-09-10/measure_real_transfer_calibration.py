#!/usr/bin/env python3
"""真实迁移标定：用两个真实自由房夜晚约束门禁的外推幅度。

背景：门禁（同牌山、完整桌赛、V2 对手池）是本工作线唯一的准入判据，但它的**外推能力**
从未被检验。手上唯一的真实自然实验是两夜：

- 2026-09-08 夜：features-v2.jsonl，我方 = 加权启发式 V2（40 房 / 400 场）；
- 2026-09-10 夜：features-v10.jsonl，我方 = v2_hu_upgrade_v1 = Tier-A（47 房 / 470 场）。

**这不是受控 A/B**：两夜的对手池、房间组成、平台状态与运气都不同，跨夜差不构成 Tier-A 的
因果效应估计。它能回答的是一个更弱但仍有用的问题——**真实数据能否排除门禁给出的效应量**。
因此本脚本给的是"可容许区间"，不是"真实效应"。

控制手段：按**对手逐人配对**。对两夜都出现过的对手，分别算我方在其桌上的场均净分，
取差值后按对手聚类做自助区间。这能一阶消掉"对手池构成不同"。

口径与 capability_gap_scorecard.py 保持同名：场均净分、严格第一名比例、庄胡率、连庄均长、
爆头占胜局、番 >= 4 占胜局。严格第一名用**场终局累计分**比较（不是单局）。

用法：
  measure_real_transfer_calibration.py --out review/.../real-transfer-calibration.json
本脚本只读主仓夜间产物，不写主仓、不改线上代码。
"""
from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/heuristic-balanced-2026-09-10'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import collections
import json
import random
from pathlib import Path

MAIN = Path("/Users/liyang/Projects/Opensource/hangma-bot")
FEATURES = _project_file(_PROJECT_ROOT, MAIN / "datasets/derived/auto-match-v10-2026-09-10")
ME = "u_13495c3d79c8"
NIGHTS = {
    "v2_baseline_20260908": _project_file(_PROJECT_ROOT, FEATURES / "features-v2.jsonl"),
    "tier_a_20260910": _project_file(_PROJECT_ROOT, FEATURES / "features-v10.jsonl"),
}


def load(path):
    """按场聚合一个夜晚；返回 {game_id: 场记录} 与对手出现次数。"""
    games = {}
    opponents = collections.Counter()
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        seat = row["my_seat"]
        users = row.get("seat_users") or []
        game = games.setdefault(row["game_id"], dict(
            room=row["room"], my_seat=seat, hands=[], opponents=tuple(sorted(
                users[index] for index in range(len(users)) if index != seat))))
        for index, user in enumerate(users):
            if index != seat:
                opponents[user] += 1
        detail = set(row.get("detail") or ())
        game["hands"].append(dict(
            round_no=row["round_no"], score=row["own_score"], won=bool(row.get("own_win")),
            scores=list(row["scores"]), dealer=row["dealer"] == seat, fan=row.get("fan") or 0,
            baotou="爆头" in detail))
    for game in games.values():
        game["hands"].sort(key=lambda hand: hand["round_no"])
    return games, opponents


def game_metrics(game):
    """一场（8 单局）的读数；严格第一名按场终局累计分判定。"""
    hands = game["hands"]
    net = sum(hand["score"] for hand in hands)
    wins = [hand for hand in hands if hand["won"]]
    dealer = [hand for hand in hands if hand["dealer"]]
    totals = [sum(hand["scores"][index] for hand in hands) for index in range(4)]
    mine = totals[game["my_seat"]]
    first = all(mine > other for index, other in enumerate(totals) if index != game["my_seat"])
    stints, run = [], 0
    for hand in hands:
        if hand["dealer"]:
            run += 1
        elif run:
            stints.append(run)
            run = 0
    if run:
        stints.append(run)
    return dict(net=net, wins=len(wins), dealer_hands=len(dealer),
                dealer_wins=sum(1 for hand in dealer if hand["won"]),
                stints=stints, totals=totals, first=first,
                baotou=sum(1 for hand in wins if hand["baotou"]),
                big4=sum(1 for hand in wins if hand["fan"] >= 4))


def summarize(games):
    """一个夜晚的总体读数（与真实房记分卡同名口径）；games 为 {game_id: 场记录}。"""
    metrics = [game_metrics(game) for game in games.values()]
    hands = sum(len(game["hands"]) for game in games.values())
    wins = sum(metric["wins"] for metric in metrics)
    dealer_hands = sum(metric["dealer_hands"] for metric in metrics)
    dealer_wins = sum(metric["dealer_wins"] for metric in metrics)
    stints = [length for metric in metrics for length in metric["stints"]]
    return dict(
        rooms=len({game["room"] for game in games.values()}),
        games=len(games),
        hands=hands,
        net_per_game=sum(metric["net"] for metric in metrics) / len(metrics),
        first_rate=sum(1 for metric in metrics if metric["first"]) / len(metrics),
        win_rate=wins / hands if hands else None,
        dealer_win_rate=dealer_wins / dealer_hands if dealer_hands else None,
        stint_mean=sum(stints) / len(stints) if stints else None,
        baotou_share=sum(metric["baotou"] for metric in metrics) / wins if wins else None,
        big4_share=sum(metric["big4"] for metric in metrics) / wins if wins else None,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = {}
    loaded = {}
    for name, path in NIGHTS.items():
        games, opponents = load(path)
        loaded[name] = (games, opponents)
        report[name] = summarize(games)
        report[name]["distinct_opponents"] = len(opponents)
    shared = set(loaded["v2_baseline_20260908"][1]) & set(loaded["tier_a_20260910"][1])
    report["shared_opponents"] = len(shared)
    per_opponent = {}
    for opponent in sorted(shared):
        entry = {}
        for name, (games, _) in loaded.items():
            picked = [game for game in games.values() if opponent in game["opponents"]]
            if not picked:
                continue
            entry[name] = (len(picked),
                           sum(game_metrics(game)["net"] for game in picked) / len(picked))
        if len(entry) == 2:
            per_opponent[opponent] = entry
    deltas = {opponent: values["tier_a_20260910"][1] - values["v2_baseline_20260908"][1]
              for opponent, values in per_opponent.items()}
    values = list(deltas.values())
    rng = random.Random(20260911)
    samples = []
    if len(values) >= 2:
        for _ in range(10000):
            picked = [rng.choice(values) for _ in values]
            samples.append(sum(picked) / len(picked))
        samples.sort()
    report["opponent_matched"] = dict(
        opponents=len(values),
        mean_delta=(sum(values) / len(values)) if values else None,
        delta_ci95=([samples[int(10000 * 0.025)], samples[int(10000 * 0.975)]]
                    if samples else [None, None]),
        per_opponent={opponent: dict(v2=entry["v2_baseline_20260908"][1],
                                     tier_a=entry["tier_a_20260910"][1],
                                     games_v2=entry["v2_baseline_20260908"][0],
                                     games_tier_a=entry["tier_a_20260910"][0],
                                     delta=deltas[opponent])
                      for opponent, entry in per_opponent.items()},
    )
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + chr(10),
                              encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("v2_baseline_20260908", "tier_a_20260910", "shared_opponents")},
                     ensure_ascii=False, indent=2))
    matched = report["opponent_matched"]
    print("对手匹配差（Tier-A 减 V2，场均净分/场）：", matched["mean_delta"],
          matched["delta_ci95"], "对手数", matched["opponents"])


if __name__ == "__main__":
    main()
