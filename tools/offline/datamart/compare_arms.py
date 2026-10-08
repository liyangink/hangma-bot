#!/usr/bin/env python3
"""按臂对比阅读器：从评估库读一个房间（或数据池）的多臂座位事实，多角度出结论。

设计要点
--------
- **配对优先**：四条臂坐在同一张桌的同一个单局里（官方每场重新随机换座），
  所以每个单局天然是一组配对观测。显著性用「单局差值」而不是两条独立均值，
  置信区间按 **完整桌赛（game_id）聚类自举**，避免把同场内的相关单局当独立样本。
- **只读**：本脚本不写库、不联网、不读 Token；所有口径与 datamart/schema.sql 一致。
- **术语**：遵守 UBIQUITOUS_LANGUAGE.md——不单独说「胜率」，一律写「胡牌率」
  「一位率」「庄家胡牌率」；桌内积分不跨座位求和。

用法：
  python3 datamart/compare_arms.py --room t_056b9e218e4e
  python3 datamart/compare_arms.py --room t_056b9e218e4e --baseline v2_hu_upgrade_v1 --json out.json
  python3 datamart/compare_arms.py --pool testroom-campaign-20260914 --mode test
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'datamart'

def _project_file(root, source):
    """共享脚本的相邻数据沿用原逻辑目录，相邻代码从共享目录读取。"""
    source = _StoragePath(source)
    here = _StoragePath(__file__).resolve().parent
    if source.is_absolute() and source.is_relative_to(here):
        if not source.is_dir() and not (source.suffix == ".py" and source.is_file()):
            source = root / _PROJECT_STORAGE_ORIGIN / source.relative_to(here)
    return _resolve_project_file(root, source)

import argparse
import json
import math
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = _PROJECT_ROOT
DB_PATH = _project_file(_PROJECT_ROOT, REPO_ROOT / "datamart" / "hangma-eval.db")
BOOTSTRAP_ITERS = 2000
BOOTSTRAP_SEED = 20260914
# 官方单局得分向量固定对应座位 0—3；名次按本单局得分排（并列取平均名次）。
SEATS = 4

ROWS_SQL = """
    SELECT h.hand_key, h.game_id, h.round_no, h.dealer_seat, h.winner_seat, h.is_draw,
           h.fan, h.fan_detail, h.played_date,
           s.seat, s.strategy_key, s.is_winner, s.is_local_first, s.is_dealer,
           s.god_count, s.score_delta
    FROM fact_hand h JOIN fact_hand_seat s ON s.hand_key = h.hand_key
    WHERE h.tournament_key = ?
    ORDER BY h.game_id, h.round_no, s.seat
"""

POOL_SQL = """
    SELECT h.hand_key, h.game_id, h.round_no, h.dealer_seat, h.winner_seat, h.is_draw,
           h.fan, h.fan_detail, h.played_date,
           s.seat, s.strategy_key, s.is_winner, s.is_local_first, s.is_dealer,
           s.god_count, s.score_delta
    FROM fact_hand h JOIN fact_hand_seat s ON s.hand_key = h.hand_key
    WHERE h.source_pool = ?
    ORDER BY h.game_id, h.round_no, s.seat
"""


# ---------------------------------------------------------------------------
# 统计小工具
# ---------------------------------------------------------------------------


def mean(values) -> float:
    return sum(values) / len(values) if values else 0.0


def percentile(values, fraction: float) -> float:
    """线性插值分位；样本为空返回 0。"""

    if not values:
        return 0.0
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    low = int(math.floor(position))
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def wilson_ci(successes: int, total: int, z: float = 1.96):
    """Wilson 95% 区间（比例）；返回 (下界, 上界) 百分数。"""

    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (100.0 * (center - margin), 100.0 * (center + margin))


def cluster_bootstrap_ci(per_game: dict, rng: random.Random, iters: int = BOOTSTRAP_ITERS):
    """按完整桌赛聚类自举：重采样的是「桌赛」，不是单局。

    同场内的单局共享对手、牌山和当局状态，独立同分布假设不成立；按 game_id
    整簇重采样给出的区间更保守，不会把相关性伪装成样本量。
    """

    games = [values for values in per_game.values() if values]
    if len(games) < 2:
        return None
    draws = []
    for _ in range(iters):
        total, count = 0.0, 0
        for _ in range(len(games)):
            bucket = games[rng.randrange(len(games))]
            total += sum(bucket)
            count += len(bucket)
        draws.append(total / count if count else 0.0)
    draws.sort()
    return (draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws)) - 1])


def sign_test_p(positive: int, negative: int) -> float:
    """精确二项符号检验（双侧）；忽略并列。n 上限 = 本战役的单局数，直接精确算。"""

    total = positive + negative
    if total == 0:
        return 1.0
    tail = sum(math.comb(total, k) for k in range(0, min(positive, negative) + 1)) / (2 ** total)
    return min(1.0, 2 * tail)


# ---------------------------------------------------------------------------
# 读数据
# ---------------------------------------------------------------------------


def load_rows(room: str | None, pool: str | None):
    if not DB_PATH.is_file():
        raise SystemExit("评估库不存在：%s" % DB_PATH)
    connection = sqlite3.connect(str(DB_PATH))
    connection.row_factory = sqlite3.Row
    try:
        if pool:
            cursor = connection.execute(POOL_SQL, (pool,))
        else:
            cursor = connection.execute(ROWS_SQL, (room,))
        return [dict(row) for row in cursor]
    finally:
        connection.close()


def load_reliability(room: str):
    """房间级运行健康（429/超时/降级）。注意：这是**整房**计数，四条臂共享同一组值。"""

    if not DB_PATH.is_file():
        return None
    connection = sqlite3.connect(str(DB_PATH))
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM fact_room_reliability WHERE tournament_key = ?", (room,)).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------


def rank_within_hand(seat_deltas: dict) -> dict:
    """按本单局得分给四个座位排名次，返回 座位 -> (平均名次, 位次份额)。

    并列时平均名次用于均值统计，份额用于位次分布：两人并列第 2 各得 0.5 个
    二位与 0.5 个三位，四条份额之和恒等于单局数（直接按整数名次分桶会让
    并列名次掉进桶外的缝里，看着像样本丢失）。
    """

    if len(seat_deltas) != SEATS:
        return {}
    ordered = sorted(seat_deltas.items(), key=lambda item: -item[1])
    out, index = {}, 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        average = (index + end) / 2 + 1
        span = end - index + 1
        share = {position + 1: 1.0 / span for position in range(index, end + 1)}
        for position in range(index, end + 1):
            out[ordered[position][0]] = (average, dict(share))
        index = end + 1
    return out


def aggregate(rows: list) -> dict:
    """把座位行折成按臂的指标集合。"""

    hands = defaultdict(dict)          # hand_key -> seat -> row
    for row in rows:
        hands[row["hand_key"]][row["seat"]] = row
    arm_rows = defaultdict(list)       # strategy -> [row]（一行 = 一臂的一个单局）
    for hand_rows in hands.values():
        deltas = {seat: (row["score_delta"] or 0) for seat, row in hand_rows.items()}
        ranks = rank_within_hand(deltas)
        for seat, row in hand_rows.items():
            ranked = ranks.get(seat)
            row["rank"] = ranked[0] if ranked else None
            row["rank_share"] = ranked[1] if ranked else {}
            row["hand_key"] = next(iter(hand_rows.values()))["hand_key"]
            arm_rows[row["strategy_key"]].append(row)

    out = {}
    for strategy, entries in arm_rows.items():
        deltas = [row["score_delta"] or 0 for row in entries]
        winners = [row for row in entries if row["is_winner"]]
        dealers = [row for row in entries if row["is_dealer"]]
        dealer_wins = [row for row in dealers if row["is_winner"]]
        ranks = [row["rank"] for row in entries if row["rank"]]
        fans = [row["fan"] for row in winners if row["fan"]]
        baotou = [row for row in winners if row["fan_detail"] and "爆头" in row["fan_detail"]]

        # 连庄率 = P(本单局坐庄 | 同场上一单局也坐庄)；最长连庄 = 最长连续坐庄段
        chains, longest = [], 0
        chain_hits = chain_opportunities = 0
        for _game, group in _by_game(entries):
            run = 0
            previous_dealer = False
            for row in group:
                if previous_dealer:
                    chain_opportunities += 1
                    if row["is_dealer"]:
                        chain_hits += 1
                if row["is_dealer"]:
                    run += 1
                else:
                    if run:
                        chains.append(run)
                    run = 0
                previous_dealer = bool(row["is_dealer"])
            longest = max(longest, run)
            if run:
                chains.append(run)
        god_buckets = defaultdict(list)
        for row in entries:
            god = row["god_count"]
            god_buckets[min(god, 4) if god is not None else -1].append(row)

        out[strategy] = {
            "hands": len(entries),
            "games": len({row["game_id"] for row in entries}),
            "net": sum(deltas),
            "net_per_hand": mean(deltas),
            "net_max": max(deltas) if deltas else 0,
            "net_min": min(deltas) if deltas else 0,
            "net_median": percentile(deltas, 0.5),
            "net_p95": percentile(deltas, 0.95),
            "wins": len(winners),
            "hu_rate": 100.0 * len(winners) / len(entries) if entries else 0.0,
            "hu_ci": wilson_ci(len(winners), len(entries)),
            "firsts": sum(1 for row in entries if row["is_local_first"]),
            "first_rate": 100.0 * sum(1 for row in entries if row["is_local_first"]) / len(entries) if entries else 0.0,
            "rank_counts": {str(position): sum(row["rank_share"].get(position, 0.0) for row in entries)
                            for position in (1, 2, 3, 4)},
            "rank_mean": mean(ranks),
            "rank_p95": percentile(ranks, 0.95),
            "dealer_hands": len(dealers),
            "dealer_rate": 100.0 * len(dealers) / len(entries) if entries else 0.0,
            "dealer_wins": len(dealer_wins),
            "dealer_hu_rate": 100.0 * len(dealer_wins) / len(dealers) if dealers else 0.0,
            "dealer_net_per_hand": mean([row["score_delta"] or 0 for row in dealers]),
            "dealer_chain_lengths": chains,
            "dealer_chain_max": longest,
            "dealer_chain_rate": 100.0 * chain_hits / chain_opportunities if chain_opportunities else 0.0,
            "fan_mean": mean(fans),
            "fan_top": sorted(fans, reverse=True)[:1][0] if fans else 0,
            "fan_labels": _fan_counts(winners),
            "baotou_wins": len(baotou),
            "baotou_rate": 100.0 * len(baotou) / len(winners) if winners else 0.0,
            "baotou_per_hand": len(baotou) / len(entries) if entries else 0.0,
            "god_buckets": {
                str(bucket): {
                    "hands": len(group),
                    "hu_rate": 100.0 * sum(1 for row in group if row["is_winner"]) / len(group),
                    "net_per_hand": mean([row["score_delta"] or 0 for row in group]),
                }
                for bucket, group in sorted(god_buckets.items())
            },
            "entries": entries,
        }
    return out


def _by_game(entries: list):
    grouped = defaultdict(list)
    for row in entries:
        grouped[row["game_id"]].append(row)
    for game, group in sorted(grouped.items()):
        yield game, sorted(group, key=lambda row: row["round_no"])


def _fan_counts(winners: list) -> dict:
    counts = defaultdict(int)
    for row in winners:
        if not row["fan_detail"]:
            continue
        try:
            for label in json.loads(row["fan_detail"]):
                counts[label] += 1
        except (ValueError, TypeError):
            continue
    return dict(sorted(counts.items(), key=lambda item: -item[1]))


# ---------------------------------------------------------------------------
# 配对检验
# ---------------------------------------------------------------------------


def paired(stats: dict, baseline: str, rng: random.Random) -> dict:
    """每个单局做「挑战臂 − 基线」差值；输出均值、聚类自举区间、符号检验。"""

    if baseline not in stats:
        return {}
    base = {row["hand_key"]: row for row in stats[baseline]["entries"]}
    results = {}
    for strategy, arms in sorted(stats.items()):
        if strategy == baseline:
            continue
        challenger = {row["hand_key"]: row for row in arms["entries"]}
        shared = sorted(set(base) & set(challenger))
        if not shared:
            continue
        axes = {
            "net": lambda row: row["score_delta"] or 0,
            "hu": lambda row: 1 if row["is_winner"] else 0,
            "first": lambda row: 1 if row["is_local_first"] else 0,
            "rank": lambda row: -(row["rank"] or 0),
        }
        block = {"paired_hands": len(shared), "axes": {}}
        for name, pick in axes.items():
            per_game = defaultdict(list)
            positive = negative = 0
            values = []
            for hand_key in shared:
                delta = pick(challenger[hand_key]) - pick(base[hand_key])
                values.append(delta)
                per_game[challenger[hand_key]["game_id"]].append(delta)
                if delta > 0:
                    positive += 1
                elif delta < 0:
                    negative += 1
            ci = cluster_bootstrap_ci(per_game, rng)
            block["axes"][name] = {
                "mean": mean(values),
                "ci95": ci,
                "positive": positive,
                "negative": negative,
                "ties": len(shared) - positive - negative,
                "sign_p": sign_test_p(positive, negative),
                "significant": bool(ci and (ci[0] > 0 or ci[1] < 0)),
            }
        results[strategy] = block
    return results


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------


def render(meta: dict, stats: dict, pairs: dict, reliability: dict, baseline: str) -> None:
    print("=" * 96)
    print("多臂对比报告  %s" % meta["title"])
    print("=" * 96)
    print("样本：%d 个单局 / %d 场完整桌赛；臂 %s"
          % (meta["hands"], meta["games"], "、".join(sorted(stats))))
    print("配对基线：%s（等胡）。差值按单局配对，置信区间按完整桌赛聚类自举 %d 次。"
          % (baseline, BOOTSTRAP_ITERS))
    print()

    keys = ["hands", "hu_rate", "net", "net_per_hand", "net_median", "net_p95", "net_max", "net_min"]
    header = "%-30s %6s %8s %8s %9s %9s %9s %8s %8s"
    print("【1. 积分与胡牌】")
    print(header % ("策略", "单局", "胡牌率%", "一位率%", "净分", "局均", "中位", "p95", "最低"))
    for strategy in sorted(stats, key=lambda name: -stats[name]["net"]):
        row = stats[strategy]
        print(header % (strategy, row["hands"], "%.2f" % row["hu_rate"], "%.2f" % row["first_rate"],
                        row["net"], "%.2f" % row["net_per_hand"], "%.0f" % row["net_median"],
                        "%.0f" % row["net_p95"], row["net_min"]))
    print("  胡牌率 95% 区间（Wilson）：" + "；".join(
        "%s [%.2f, %.2f]" % (name, stats[name]["hu_ci"][0], stats[name]["hu_ci"][1])
        for name in sorted(stats)))
    print()

    print("【2. 单局名次分布】名次按本单局得分排名（并列取平均名次）")
    print("%-30s %10s %10s %10s %10s %10s %10s" %
          ("策略", "一位率%", "二位率%", "三位率%", "四位率%", "平均名次", "名次p95"))
    for strategy in sorted(stats, key=lambda name: stats[name]["rank_mean"]):
        row = stats[strategy]
        counts = row["rank_counts"]
        share = lambda position: 100.0 * counts[position] / row["hands"] if row["hands"] else 0.0
        print("%-30s %10.2f %10.2f %10.2f %10.2f %10.3f %10.2f"
              % (strategy, share("1"), share("2"), share("3"), share("4"),
                 row["rank_mean"], row["rank_p95"]))
    print()

    if pairs:
        print("【3. 配对检验】每个单局做「本臂 − 基线」的差值（net=得分，hu=是否胡牌，first=是否桌内最高分）")
        print("%-30s %8s %10s %22s %8s %8s %10s" %
              ("策略 vs 基线", "配对局", "口径", "均值 [95% 聚类区间]", "正", "负", "符号检验p"))
        for strategy in sorted(pairs):
            block = pairs[strategy]
            for index, axis in enumerate(("net", "hu", "first")):
                value = block["axes"][axis]
                interval = value["ci95"]
                text = ("%+.3f [%+.3f, %+.3f]" % (value["mean"], interval[0], interval[1])
                        if interval else "样本不足")
                print("%-30s %8s %10s %22s %8d %8d %10.4f%s" %
                      (strategy if index == 0 else "", block["paired_hands"] if index == 0 else "",
                       axis, text, value["positive"], value["negative"], value["sign_p"],
                       "  ★" if value["significant"] else ""))
        print("  ★ = 该口径的 95% 聚类自举区间不跨零（同时看符号检验的 p 值，两者不一致要当不确定处理）")
        print()

    print("【4. 白板利用】起手白板档位 × 胡牌率 / 局均分")
    buckets = sorted({key for row in stats.values() for key in row["god_buckets"]}, key=int)
    for strategy in sorted(stats):
        row = stats[strategy]
        parts = []
        for bucket in buckets:
            entry = row["god_buckets"].get(bucket)
            if entry:
                label = "无白" if bucket == "0" else ("%s白" % bucket if bucket != "-1" else "未知")
                parts.append("%s %d局 胡%.0f%% 均%+.1f"
                             % (label, entry["hands"], entry["hu_rate"], entry["net_per_hand"]))
        print("%-30s %s" % (strategy, " | ".join(parts)))
    print()

    print("【5. 庄家运营】坐庄率 / 庄家胡牌率 / 庄局均 / 连庄率 / 最长连庄")
    print("%-30s %9s %11s %9s %9s %9s" % ("策略", "坐庄率%", "庄家胡牌%", "庄局均", "连庄率%", "最长连庄"))
    for strategy in sorted(stats, key=lambda name: -stats[name]["dealer_net_per_hand"]):
        row = stats[strategy]
        print("%-30s %9.2f %11.2f %9.2f %9.2f %9d"
              % (strategy, row["dealer_rate"], row["dealer_hu_rate"],
                 row["dealer_net_per_hand"], row["dealer_chain_rate"], row["dealer_chain_max"]))
    print()

    print("【6. 番型结构】只统计本臂胡出的单局（番数来自 round_ended 结算）")
    print("%-30s %9s %9s %8s %s" % ("策略", "番均", "最高番", "爆头占胡%", "番型标签"))
    for strategy in sorted(stats):
        row = stats[strategy]
        labels = "、".join("%s×%d" % (name, count) for name, count in row["fan_labels"].items()) or "-"
        print("%-30s %9.3f %9d %8.2f %s"
              % (strategy, row["fan_mean"], row["fan_top"], row["baotou_rate"], labels))
    print()

    print("【7. 运行健康】房间级计数，四条臂共享——不能归因到单条臂")
    if reliability:
        attempts = reliability.get("attempts") or 0
        http_total = reliability.get("http_total") or 0
        games = reliability.get("games_total") or 0
        print("  提交尝试 %s / HTTP %s / 429 %s (%.3f%%) / 非200-429 %s"
              % (attempts, http_total, reliability.get("http_429"),
                 100.0 * (reliability.get("http_429") or 0) / http_total if http_total else 0.0,
                 reliability.get("http_other")))
        print("  未发送 %s / 未发送超时 %s / 拒绝 %s / 模糊 %s"
              % (reliability.get("not_sent"), reliability.get("not_sent_timeouts"),
                 reliability.get("rejected"), reliability.get("ambiguous")))
        print("  规则降级 %s / 决策 %s (%.3f%%)  / 时延 p95 %sms / 审计完整 %s"
              % (reliability.get("rule_degradations"), reliability.get("decisions_planned"),
                 100.0 * (reliability.get("rule_degradations") or 0) / (reliability.get("decisions_planned") or 1),
                 reliability.get("latency_p95_ms"), reliability.get("audit_complete")))
        print("  场次 %s（完成 %s）" % (games, reliability.get("games_finished")))
    else:
        print("  库里没有该房的审计聚合（validations/*.audit.json 未落库）")
    print()

    print("【8. 读法】")
    print("  - 单局样本 < 200 时不要下结论；区间宽度才是真实的不确定性，点估计会动。")
    print("  - 三条模型臂与等胡共用同一套 V2+等胡 保底，差别只在网络对候选的重排上。")
    print("  - 运行健康与白板档位是描述性的，不是显著性结论。")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="按臂对比阅读器（只读评估库）")
    parser.add_argument("--room", help="tournament_key，例如 t_056b9e218e4e")
    parser.add_argument("--pool", help="按 source_pool 过滤（跨房汇总时用）")
    parser.add_argument("--baseline", default="v2_hu_upgrade_v1", help="配对基线策略名")
    parser.add_argument("--json", help="把结构化结果另存为 JSON")
    args = parser.parse_args(argv)
    if not args.room and not args.pool:
        parser.error("至少要给 --room 或 --pool")

    rows = load_rows(args.room, args.pool)
    if not rows:
        print("没有匹配的座位行：room=%s pool=%s" % (args.room, args.pool))
        return 1
    stats = aggregate(rows)
    rng = random.Random(BOOTSTRAP_SEED)
    pairs = paired(stats, args.baseline, rng)
    if args.baseline not in stats:
        print("注意：基线臂 %s 不在本房间的臂里（%s），第 3 节配对检验整节省略。\n"
              % (args.baseline, "、".join(sorted(stats))))
    reliability = load_reliability(args.room) if args.room else None
    meta = {
        "title": "房间 %s" % args.room if args.room else "数据池 %s" % args.pool,
        "hands": len({row["hand_key"] for row in rows}),
        "games": len({row["game_id"] for row in rows}),
    }
    render(meta, stats, pairs, reliability, args.baseline)
    if args.json:
        payload = {
            "meta": meta, "baseline": args.baseline, "reliability": reliability,
            "arms": {name: {key: value for key, value in row.items() if key != "entries"}
                     for name, row in stats.items()},
            "paired": pairs,
        }
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                                   encoding="utf-8")
        print("结构化结果已写入 %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
