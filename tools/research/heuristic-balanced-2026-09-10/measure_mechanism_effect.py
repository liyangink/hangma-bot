#!/usr/bin/env python3
"""机制级效果测量：把门禁只报净分的缺口补上。

动机：门禁 (`gate_candidate.py`) 的判据只有两项——桌内积分差与第一名比例。它能回答
"候选是否更强"，但不能回答"候选动没动它声称要动的机制"。对庄位节奏类候选这尤其致命：
若候选完全没有改变庄胡率/连庄长度，那真实房 A/B 只是白烧时间。

本脚本对同一批根组同时跑"基线臂"与"候选臂"，保存**逐局**记录（坐庄座位、胡家、番、
按座位的积分增量），再按真实房记分卡 (`capability_gaps.py` / `capability-gaps.json`) 的
同一批口径聚合：

- `dealer/win_rate`：候选坐庄的局里，庄家胡牌的比例（庄胡率）；
- `dealer/net_per_hand`：候选坐庄局的候选场均得分；
- `stint/*`：候选连续坐庄的**连续段**长度分布（连庄长度的直接度量）；
- `big_hand/*`：候选胡牌局中 番>=4/8/16 的占比（做大牌能力）；
- `win_kind/*`：爆头/财飘/Piao 占候选胜局的比例。

统计纪律与门禁一致：指标先按根组 (scenario_id) 求均值，再对根组做自助聚类区间；
配对口径为 (scenario_id, seat_permutation) 上"候选臂 − 基线臂"。本脚本**不做通过/否决
判定**，只产出机制读数；门禁仍是判定入口。

用法：
  measure_mechanism_effect.py --baseline weighted_heuristic_v2 \
      --candidate v2_hu_upgrade_dealer_v1 --roots 32 --seed-start 1390000 \
      --record v2_hu_upgrade_v1 --out review/.../mechanism-dealer-dev32

`--record` 可选，指定"同时作为参照记录"的策略名（例如现役实验版），只影响报告里的对照列。
本脚本只读模拟公开接口，不改变线上动作、生产枚举与默认配置。
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
from concurrent.futures import ProcessPoolExecutor
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

WORK = _project_file(_PROJECT_ROOT, 'review/heuristic-balanced-2026-09-10')
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WORK))

from gate_candidate import SEAT_ROTATIONS, ValuesWhenNeeded, bootstrap_ci, build_policy  # noqa: E402
from lab import ROOT, RULESET, HangmaRules, RuleConfig  # noqa: E402
from run_tables import RecordingEngine  # noqa: E402
from hangma_bot.application.deadline import BudgetPolicy  # noqa: E402
from hangma_bot.kernel.config import TournamentConfig, TimingConfig  # noqa: E402
from hangma_bot.offline.evaluate import (MatchExperiment, PolicyDeclaration, MatchSeedSpec,  # noqa: E402
                                         run_match_experiment)
from hangma_bot.simulation.artifacts import compute_rules_hash  # noqa: E402
from hangma_bot.simulation.engine import SimulationEngine  # noqa: E402
from hangma_bot.simulation.interface import MatchSpec, SimulationChoice  # noqa: E402

HANDS_PER_TABLE = 8  # 与运行时 config.Rounds 一致：真实房实测每场 8 单局、每房 10 场
SEVEN_PAIR_MARKERS = ("七对",)
BAOTOU_MARKERS = ("爆头",)
PIAO_MARKERS = ("飘",)


class HandRecordingEngine(RecordingEngine):
    """在公开导出结果上补记坐庄座位与流局标志；不读 WorldState 内部字段。"""

    def frame(self, world):
        before = len(self.hands)
        frame = super().frame(world)
        for index in range(before, len(self.hands)):
            number = self.hands[index]["round_no"]
            exported = self.engine.export_hand(world, number)
            initial = exported.get("initial") or {}
            self.hands[index]["dealer_seat"] = initial.get("dealer_seat")
            self.hands[index]["is_draw"] = exported.get("is_draw")
            # 记录引擎把它存成 `winner` 而不是 `winner_seat`；这里补齐，
            # 否则胜局统计恒为 0，庄胡率会输出假的 0.0。
            self.hands[index]["winner_seat"] = exported.get("winner_seat")
        return frame


def root_run(item):
    """一个进程顺序完成一个根组的全部配对桌赛，返回逐局记录与结果行。

    【口径陷阱】牌山由 `(scenario_id, seed, round_no)` 派生（`shuffle.deal-v1`，
    `simulation/engine.py`）。因此 `scenario_prefix` 是**牌山的组成部分**，
    不是展示标签：换前缀等于换整副牌。要与 `gate_candidate.py` 的既有门禁对拍，
    必须传同一个前缀（门禁用 `gate`）。
    """
    baseline, candidate, opponents, scenario_prefix, index, seed = item
    raw = HangmaRules(RuleConfig(RULESET, 1, False))
    rules_hash = compute_rules_hash(ROOT)
    config = TournamentConfig(1, HANDS_PER_TABLE, raw.config, TimingConfig(1, 1, 3))
    ids = [baseline, candidate, "opp-1", "opp-2", "opp-3"]
    policies = {baseline: build_policy(baseline), candidate: build_policy(candidate),
                **{pid: build_policy(name) for pid, name in zip(ids[2:], opponents)}}
    experiment = MatchExperiment(
        "matches", "logical", PolicyDeclaration(baseline, baseline), PolicyDeclaration(candidate, candidate),
        tuple(PolicyDeclaration(pid, name) for pid, name in zip(ids[2:], opponents)), config,
        (MatchSeedSpec(seed, "{0}-{1}".format(scenario_prefix, index)),), SEAT_ROTATIONS, index % 4, (0, 0, 0, 0),
        simulation_version="simulation-v1", match_id_prefix=scenario_prefix)
    engine = HandRecordingEngine(SimulationEngine(raw, rules_hash=rules_hash))
    out = asyncio.run(run_match_experiment(
        experiment, engine=engine, spec_factory=MatchSpec, choice_factory=SimulationChoice,
        policies_by_id=policies, rules=ValuesWhenNeeded(raw), rules_hash=rules_hash,
        now_monotonic=lambda: 0, wall_clock=None, budget_policy=BudgetPolicy()))
    return out.results, engine.hands, list(out.excluded)


def hands_by_match(hands):
    grouped = {}
    for hand in hands:
        grouped.setdefault(hand["game_id"], []).append(hand)
    for rows in grouped.values():
        rows.sort(key=lambda row: row["round_no"])
    return grouped


def seat_of(row, policy_id):
    for seat, pid in enumerate(row.policy_ids_by_seat):
        if pid == policy_id:
            return seat
    return None


def summarize_hand(rows, seat, acc):
    """累计一场桌赛内的机制计数；seat 为该场被测评策略的实际座位。"""
    stint = 0
    for row in rows:
        delta = row.get("score_delta") or (0, 0, 0, 0)
        won = row.get("winner_seat") == seat and not row.get("is_draw")
        is_dealer = row.get("dealer_seat") == seat
        acc["hands"] += 1
        acc["net_total"] += int(delta[seat])
        acc["fan_samples"].append(int(delta[seat]))
        if is_dealer:
            acc["dealer_hands"] += 1
            acc["dealer_net_total"] += int(delta[seat])
            stint += 1
            if won:
                acc["dealer_wins"] += 1
        else:
            if stint:
                acc["stints"].append(stint)
                stint = 0
            acc["nondealer_hands"] += 1
            acc["nondealer_net_total"] += int(delta[seat])
        if won:
            acc["wins"] += 1
            fan = row.get("fan") or 0
            details = {str(item) for item in (row.get("details") or ())}
            for threshold in (4, 8, 16):
                if fan >= threshold:
                    acc["big_{0}".format(threshold)] += 1
            # 严格按真实记分卡的集合命中口径（不用子串）：官方明细里
            # 豪华七对不会同时出现“七对”，子串匹配会把两边算法拉开。
            if "爆头" in details:
                acc["baotou"] += 1
            if "七对" in details or any(item.startswith("豪华七对") for item in details):
                acc["seven_pairs"] += 1
            if "财飘" in details:
                acc["piao"] += 1
            if any("飘" in item for item in details):
                acc["piao_any"] += 1
            acc["fan_wins"].append(fan)
    if stint:
        acc["stints"].append(stint)
    return acc


def new_acc():
    return dict(hands=0, wins=0, net_total=0, dealer_hands=0, dealer_wins=0, dealer_net_total=0,
                nondealer_hands=0, nondealer_net_total=0, big_4=0, big_8=0, big_16=0,
                baotou=0, piao=0, piao_any=0, seven_pairs=0, stints=[], fan_samples=[], fan_wins=[])


def safe_div(numerator, denominator):
    return (numerator / denominator) if denominator else None


def derive(acc):
    """把累计计数转成与真实房记分卡同名的比率；缺样本返回 None，不填 0。"""
    stints = acc["stints"]
    return dict(
        hands=acc["hands"],
        wins=acc["wins"],
        win_rate=safe_div(acc["wins"], acc["hands"]),
        net_per_hand=safe_div(acc["net_total"], acc["hands"]),
        dealer_hands=acc["dealer_hands"],
        dealer_win_rate=safe_div(acc["dealer_wins"], acc["dealer_hands"]),
        dealer_net_per_hand=safe_div(acc["dealer_net_total"], acc["dealer_hands"]),
        nondealer_net_per_hand=safe_div(acc["nondealer_net_total"], acc["nondealer_hands"]),
        stint_count=len(stints),
        stint_mean=safe_div(sum(stints), len(stints)),
        stint_share_ge2=safe_div(sum(1 for value in stints if value >= 2), len(stints)),
        stint_share_ge3=safe_div(sum(1 for value in stints if value >= 3), len(stints)),
        big_hand_share_4=safe_div(acc["big_4"], acc["wins"]),
        big_hand_share_8=safe_div(acc["big_8"], acc["wins"]),
        big_hand_share_16=safe_div(acc["big_16"], acc["wins"]),
        baotou_share=safe_div(acc["baotou"], acc["wins"]),
        piao_share=safe_div(acc["piao"], acc["wins"]),
        piao_any_share=safe_div(acc["piao_any"], acc["wins"]),
        seven_pairs_share=safe_div(acc["seven_pairs"], acc["wins"]),
    )


def collect(results, hands):
    """按「根 × 换座 × 被测策略」归组，复刻门禁的配对口径。

    每张桌只有 4 席却声明 5 个策略，但 `run_match_experiment` 每桌只放
    「本臂被测策略（逻辑身份 0）+ 三名对手」，被测策略**恒在**
    `seat_permutation[0]`。因此必须按该座位取记录，不能全桌搜政策名：
    候选臂里也可能坐着别人的同名策略，按名字搜会把两臂混成同一条。
    """
    grouped = hands_by_match(hands)
    per_table = {}
    totals = {}
    mismatches = []
    for row in results:
        game_key = row.game_key
        match_id = getattr(game_key, "game_id", None) if game_key is not None else None
        records = grouped.get(match_id)
        if not records:
            continue
        seat = row.seat_permutation[0]
        focus = row.policy_ids_by_seat[seat]
        if focus is None:
            continue
        acc = new_acc()
        summarize_hand(records, seat, acc)
        # 逐场自校验：逐局增量之和必须等于该座位终局分；不等说明记录归属错了，
        # 后续任何比率都不能信（这条检查是发现"假 0.0"那次事故后补上的）。
        if row.scores_after is not None and acc["net_total"] != row.scores_after[seat]:
            mismatches.append(dict(match_id=match_id, seat=seat,
                                   from_hands=acc["net_total"], from_row=row.scores_after[seat]))
        per_table[(row.scenario_id, tuple(row.seat_permutation), focus)] = derive(acc)
        entry = totals.setdefault(focus, new_acc())
        for key in ("hands", "wins", "net_total", "dealer_hands", "dealer_wins",
                    "dealer_net_total", "nondealer_hands", "nondealer_net_total",
                    "big_4", "big_8", "big_16", "baotou", "piao", "piao_any", "seven_pairs"):
            entry[key] += acc[key]
        entry["stints"].extend(acc["stints"])
    return per_table, {name: derive(acc) for name, acc in totals.items()}, mismatches


def paired(per_table, baseline, candidate, metric):
    """返回 {根: [候选 − 基线]}；按 (根, 换座) 配对，缺任一侧则跳过。"""
    deltas = {}
    for (scenario, permutation, focus), values in per_table.items():
        if focus != candidate:
            continue
        other = per_table.get((scenario, permutation, baseline))
        if other is None:
            continue
        base_value = other.get(metric)
        cand_value = values.get(metric)
        if base_value is None or cand_value is None:
            continue
        deltas.setdefault(scenario, []).append(cand_value - base_value)
    return deltas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--roots", type=int, default=32)
    parser.add_argument("--seed-start", type=int, default=1390000)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--record", default="", help="可选：额外作为参照列记录的策略名")
    parser.add_argument("--scenario-prefix", default="mechanism",
                        help="牌山前缀（组成牌山本身！与既有门禁对拍须传同一个，门禁用 gate）")
    parser.add_argument("--opponents", action="append", default=[])
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    directory = Path(args.out)
    directory.mkdir(parents=True, exist_ok=False)
    opponents = args.opponents or ["weighted_heuristic_v2"] * 3
    if len(opponents) != 3:
        raise ValueError("--opponents 必须给出三名（或省略使用缺省）")
    started = time.monotonic()
    results, hands, excluded = [], [], []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = [(args.baseline, args.candidate, tuple(opponents), args.scenario_prefix, i,
                 args.seed_start + i) for i in range(args.roots)]
        for index, (rows, hand_rows, bad) in enumerate(pool.map(root_run, jobs)):
            results.extend(rows)
            hands.extend(hand_rows)
            excluded.extend(bad)
            if (index + 1) % 8 == 0:
                print("mechanism", index + 1, "/", args.roots, "hands", len(hands), flush=True)
    per_table, totals, mismatches = collect(results, hands)
    base_total = totals.get(args.baseline) or {}
    cand_total = totals.get(args.candidate) or {}
    if not base_total or not cand_total:
        raise SystemExit("未采集到两臂的逐局记录：" + ", ".join(sorted(totals)))
    metrics = [name for name in cand_total if isinstance(cand_total[name], (int, float))]
    deltas, intervals = {}, {}
    for metric in metrics:
        by_root = paired(per_table, args.baseline, args.candidate, metric)
        flat = [value for values in by_root.values() for value in values]
        deltas[metric] = (sum(flat) / len(flat)) if flat else None
        intervals[metric] = bootstrap_ci(by_root) if len(by_root) >= 2 else [None, None]
    record_total = totals.get(args.record) if args.record else None
    report = dict(
        schema="mechanism-effect/1", baseline=args.baseline, candidate=args.candidate,
        record=args.record or None, roots=args.roots,
        seed_range=[args.seed_start, args.seed_start + args.roots - 1],
        hands_per_table=HANDS_PER_TABLE, opponents=list(opponents),
        matched_hands=len(hands), excluded=len(excluded),
        score_consistency_mismatches=len(mismatches), mismatch_examples=mismatches[:5],
        baseline_observed=base_total, candidate_observed=cand_total,
        record_observed=record_total, delta=deltas, delta_ci95=intervals,
        elapsed_seconds=time.monotonic() - started)
    (directory / "mechanism.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + chr(10), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("matched_hands", "excluded", "elapsed_seconds")},
                     ensure_ascii=False), flush=True)
    for metric in ("net_per_hand", "dealer_win_rate", "dealer_net_per_hand", "stint_mean",
                   "stint_share_ge2", "big_hand_share_4", "big_hand_share_8", "baotou_share"):
        delta = deltas.get(metric)
        print("{0:24s} base={1} cand={2} delta={3} ci={4}".format(
            metric, base_total.get(metric), cand_total.get(metric),
            None if delta is None else round(delta, 4), intervals.get(metric)), flush=True)


if __name__ == "__main__":
    main()
