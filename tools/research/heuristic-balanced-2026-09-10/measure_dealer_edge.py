#!/usr/bin/env python3
"""庄位优势诊断：同一批牌山下逐策略测量"庄胡率 - 闲胡率"。

动机（round 17）：模拟里我方庄位优势 +11.3~11.8pp，真实两夜只有 -0.75 / +0.71pp，
真实各对手组 +1.5~5.4pp。猜测是**模拟对手不抢庄**（V2 克隆座位盲打），庄家白拿结构性优势。
本工具让"庄位优势"变成可直接对照、可扫描的读数。

做法：每桌固定四名策略（默认同池），四换座各跑一次，**统计全部四个座位**。
输出每个策略的：庄手数/庄胡率、闲手数/闲胡率、庄位优势、庄手占比、流局率。

口径警告：庄家身份由 next_dealer 决定（庄赢或流局连庄），所以"庄手占比"高于 25%，
这是**选择效应**不是 bug。比较不同策略时**必须同时看庄手占比**，否则会把选择效应当能力。

用法：
  measure_dealer_edge.py --seats A B C D --roots 96 --seed-start 5000000 --out <dir>
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
import asyncio
import collections
import json
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

WORK = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')
sys.path.insert(0, str(WORK))

from gate_candidate import ROTATION_SETS, ValuesWhenNeeded, build_policy  # noqa: E402
from lab import ROOT, RULESET, HangmaRules, RuleConfig  # noqa: E402
from run_tables import RecordingEngine  # noqa: E402
from hangma_bot.application.deadline import BudgetPolicy  # noqa: E402
from hangma_bot.kernel.config import TournamentConfig, TimingConfig  # noqa: E402
from hangma_bot.offline.evaluate import (MatchExperiment, PolicyDeclaration, MatchSeedSpec,  # noqa: E402
                                         run_match_experiment)
from hangma_bot.simulation.artifacts import compute_rules_hash  # noqa: E402
from hangma_bot.simulation.engine import SimulationEngine  # noqa: E402
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice  # noqa: E402

HANDS_PER_TABLE = 8
ARM_LABELS = ("arm-base", "arm-chal", "opp-1", "opp-2", "opp-3")


class HandRecordingEngine(RecordingEngine):
    """在公开导出结果上补记坐庄座位，供庄位统计使用；不读 WorldState 内部字段。"""

    def frame(self, world):
        before = len(self.hands)
        frame = super().frame(world)
        for index in range(before, len(self.hands)):
            exported = self.engine.export_hand(world, self.hands[index]["round_no"])
            self.hands[index]["dealer_seat"] = (exported.get("initial") or {}).get("dealer_seat")
            self.hands[index]["is_draw"] = exported.get("is_draw")
        return frame


def label_map(seats):
    """结果行里的 policy_id 标签 -> 策略名；两臂坐的是同一名策略。"""

    return {ARM_LABELS[0]: seats[0], ARM_LABELS[1]: seats[0],
            ARM_LABELS[2]: seats[1], ARM_LABELS[3]: seats[2], ARM_LABELS[4]: seats[3]}


def root_run(item):
    """一个根组：四换座各跑一次，返回逐局记录与结果行。

    两臂声明**不同的 policy_id 标签但同一个策略名**：MatchExperiment 要求基线/候选的
    policy_id 不同；此处两臂策略名相同 ⇒ 两张桌是同一局的副本，只有 1 张带信息。

    换座（cyclic 四移位）在本引擎里是**纯重标号**：置换同时作用于策略与发牌，整局同构，
    逐位结果相同（1524/1524 根实测；`gate_candidate.py` 的帮助文本亦注明"零信息"）。
    因此默认 `rotations=1`——4 个换座 x 2 个同策略臂 = 8 桌中 7 桌冗余，砍掉即 8 倍提效。
    座位效应改由 `initial_dealer = index % 4` 跨根轮转来平衡。
    """

    seats, index, seed, scenario_prefix, rotations = item
    raw = HangmaRules(RuleConfig(RULESET, 1, False))
    rules_hash = compute_rules_hash(ROOT)
    config = TournamentConfig(1, HANDS_PER_TABLE, raw.config, TimingConfig(1, 1, 3))
    names = [seats[0], seats[0], seats[1], seats[2], seats[3]]
    policies = {pid: build_policy(name) for pid, name in zip(ARM_LABELS, names)}
    experiment = MatchExperiment(
        "matches", "logical", PolicyDeclaration(ARM_LABELS[0], seats[0]),
        PolicyDeclaration(ARM_LABELS[1], seats[0]),
        tuple(PolicyDeclaration(pid, name) for pid, name in zip(ARM_LABELS[2:], seats[1:])),
        config, (MatchSeedSpec(seed, "{0}-{1}".format(scenario_prefix, index)),),
        ROTATION_SETS["cyclic"][:rotations], index % 4, (0, 0, 0, 0),
        simulation_version="simulation-v1", match_id_prefix=scenario_prefix)
    engine = HandRecordingEngine(SimulationEngine(raw, rules_hash=rules_hash))
    out = asyncio.run(run_match_experiment(
        experiment, engine=engine, spec_factory=MatchSpec, choice_factory=SimulationChoice,
        policies_by_id=policies, rules=ValuesWhenNeeded(raw), rules_hash=rules_hash,
        now_monotonic=lambda: 0, wall_clock=None, budget_policy=BudgetPolicy()))
    return out.results, engine.hands, label_map(seats), list(out.excluded)


def root_ci(samples, seed, draws=4000):
    """按根聚类自助 95% 区间。

    有效样本量是**根数**而不是手数：同一根内 4 个座位共享牌山与对手，不独立。
    缺省 4000 次重抽足以稳定到 3 位小数（区间本身只用于判方向）。
    """

    if len(samples) < 2:
        return None, None
    rng = random.Random(seed)
    n = len(samples)
    means = []
    for _ in range(draws):
        means.append(sum(samples[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    return means[int(0.025 * len(means))], means[int(0.975 * len(means))]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seats", nargs=4, required=True, help="四个座位的策略名")
    parser.add_argument("--roots", type=int, default=96)
    parser.add_argument("--seed-start", type=int, default=5000000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--scenario-prefix", default="dealer-edge")
    parser.add_argument("--rotations", type=int, default=1, choices=[1, 2, 3, 4],
                        help="cyclic 换座个数；零信息，缺省 1（见 root_run docstring）")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    directory = Path(args.out)
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    results, hands, excluded = [], [], []
    hand_root = []  # 与 hands 逐位对应：该局属于哪一根（净分按根聚类要用）
    labels = None
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = [(tuple(args.seats), i, args.seed_start + i, args.scenario_prefix, args.rotations)
                for i in range(args.roots)]
        for index, (rows, hand_rows, mapping, bad) in enumerate(pool.map(root_run, jobs)):
            results.extend(rows)
            hands.extend(hand_rows)
            hand_root.extend([index] * len(hand_rows))
            labels = mapping
            excluded.extend(bad)
            if (index + 1) % 16 == 0:
                print("dealer-edge", index + 1, "/", args.roots, "hands", len(hands), flush=True)
    # 座位 -> 策略：**必须逐场连接**。手牌记录里的 seat 是物理座位，而物理座位上坐谁
    # 随换座变化；把物理座位当策略会得出完全错误的归属（首版就踩了这个坑）。
    seat_by_match = {}
    for row in results:
        game_key = row.game_key
        match_id = getattr(game_key, "game_id", None) if game_key is not None else None
        if match_id is not None:
            seat_by_match[match_id] = row.policy_ids_by_seat
    stats = collections.defaultdict(lambda: dict(dealer_hands=0, dealer_wins=0, plain_hands=0,
                                                 plain_wins=0, draws=0, hands=0))
    # 焦点口径：只统计 seat_permutation[0] 那一个座位（与 measure_mechanism_effect.py 同口径），
    # 用来与"全座位池化"对拍。两者在同一批桌上应当接近，若不接近则座位归属逻辑有问题。
    focal = collections.defaultdict(lambda: dict(dealer_hands=0, dealer_wins=0, plain_hands=0,
                                                 plain_wins=0))
    focal_seat_of_match = {}
    for row in results:
        game_key = row.game_key
        match_id = getattr(game_key, "game_id", None) if game_key is not None else None
        if match_id is None:
            continue
        permutation = tuple(row.seat_permutation)
        focal_seat_of_match[match_id] = (permutation[0], row.policy_ids_by_seat[permutation[0]])
    # 每臂净分：按根累积，才能给出与门禁同口径的**根聚类**区间（有效样本量是根数）。
    net = collections.defaultdict(lambda: collections.defaultdict(float))
    net_hands = collections.defaultdict(lambda: collections.defaultdict(int))
    unmatched = 0
    for position, hand in enumerate(hands):
        ids_by_seat = seat_by_match.get(hand.get("game_id"))
        if ids_by_seat is None:
            unmatched += 1
            continue
        seat = hand.get("dealer_seat")
        winner = hand.get("winner")
        is_draw = hand.get("is_draw")
        delta = hand.get("score_delta") or (0, 0, 0, 0)
        root = hand_root[position] if position < len(hand_root) else 0
        for index in range(4):
            raw_label = ids_by_seat[index] or "seat-{0}".format(index)
            name = labels.get(raw_label, raw_label) if labels else raw_label
            entry = stats[name]
            entry["hands"] += 1
            net[name][root] += delta[index]
            net_hands[name][root] += 1
            if is_draw:
                entry["draws"] += 1
            won = (winner == index) and not is_draw
            if index == seat:
                entry["dealer_hands"] += 1
                entry["dealer_wins"] += 1 if won else 0
            else:
                entry["plain_hands"] += 1
                entry["plain_wins"] += 1 if won else 0
        # 焦点口径：每局只算 seat_permutation[0] 那一个座位（与机制工具同口径）。
        seat_info = focal_seat_of_match.get(hand.get("game_id"))
        if seat_info is not None:
            seat_index, label = seat_info
            bucket = focal[labels.get(label, label) if labels else label]
            won_focal = (winner == seat_index) and not is_draw
            if seat_index == seat:
                bucket["dealer_hands"] += 1
                bucket["dealer_wins"] += 1 if won_focal else 0
            else:
                bucket["plain_hands"] += 1
                bucket["plain_wins"] += 1 if won_focal else 0
    report = dict(schema="dealer-edge/1", seats=list(args.seats), roots=args.roots,
                  seed_range=[args.seed_start, args.seed_start + args.roots - 1],
                  hands_recorded=len(hands), unmatched_hands=unmatched, excluded=len(excluded),
                  elapsed_seconds=time.monotonic() - started, stats={}, focal_stats={})
    for name, entry in sorted(stats.items()):
        dh, dw = entry["dealer_hands"], entry["dealer_wins"]
        ph, pw = entry["plain_hands"], entry["plain_wins"]
        dealer_rate = dw / dh if dh else None
        plain_rate = pw / ph if ph else None
        report["stats"][name] = dict(
            hands=entry["hands"], dealer_hands=dh, dealer_win_rate=dealer_rate,
            plain_hands=ph, plain_win_rate=plain_rate,
            dealer_advantage=((dealer_rate - plain_rate)
                              if (dealer_rate is not None and plain_rate is not None) else None),
            dealer_share=dh / entry["hands"] if entry["hands"] else None,
            draw_rate=entry["draws"] / entry["hands"] if entry["hands"] else None)
        # 同台四臂的净分之和恒为 ~0（零和），所以绝对值无意义，**臂间差**才有意义。
        per_root = []
        for root, total in sorted(net.get(name, {}).items()):
            count = net_hands[name][root]
            if count:
                per_root.append(total / count)
        lo, hi = root_ci(per_root, 20260911)
        report["stats"][name]["net_per_hand"] = (
            sum(per_root) / len(per_root) if per_root else None)
        report["stats"][name]["net_ci95"] = [lo, hi]
        report["stats"][name]["net_roots"] = len(per_root)
        report["stats"][name]["net_by_root"] = per_root
    for name, entry in sorted(focal.items()):
        dh, dw = entry["dealer_hands"], entry["dealer_wins"]
        ph, pw = entry["plain_hands"], entry["plain_wins"]
        dr = dw / dh if dh else None
        pr = pw / ph if ph else None
        report["focal_stats"][name] = dict(dealer_hands=dh, dealer_win_rate=dr, plain_hands=ph,
                                           plain_win_rate=pr,
                                           dealer_advantage=(dr - pr) if (dr is not None and pr is not None) else None)
    (directory / "dealer-edge.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("hands_recorded", "unmatched_hands",
                                                 "excluded", "elapsed_seconds")},
                     ensure_ascii=False))
    for name, entry in report["stats"].items():
        print("%-26s 手=%5d 庄手占比=%.3f 庄胡率=%.4f 闲胡率=%.4f 庄位优势=%+.4f 流局率=%.3f" % (
            name, entry["hands"], entry["dealer_share"] or 0, entry["dealer_win_rate"] or 0,
            entry["plain_win_rate"] or 0, entry["dealer_advantage"] or 0, entry["draw_rate"] or 0))
    print()
    print("同台净分（每手，零和；区间为按根聚类自助 95%）")
    for name, entry in report["stats"].items():
        ci = entry.get("net_ci95") or [None, None]
        print("  %-26s %+7.4f  [%s, %s]  根=%d" % (
            name, entry.get("net_per_hand") or 0,
            "None" if ci[0] is None else "%+.4f" % ci[0],
            "None" if ci[1] is None else "%+.4f" % ci[1], entry.get("net_roots") or 0))
    for name, entry in report["focal_stats"].items():
        print("%-26s [焦点口径] 庄手=%5d 庄胡率=%.4f 闲手=%5d 闲胡率=%.4f 庄位优势=%+.4f" % (
            name, entry["dealer_hands"], entry["dealer_win_rate"] or 0,
            entry["plain_hands"], entry["plain_win_rate"] or 0, entry["dealer_advantage"] or 0))


if __name__ == "__main__":
    main()
