#!/usr/bin/env python3
"""实验功效分析：真实房 A/B 到底需要多大样本，以及门禁需要多少对桌赛。

动机：本工作线长期用"效应量"讨论候选（Tier-A +4.19/场、庄位变体 -1.06/场…），却从未算过
**这些效应量在当前样本量下能否被检出**。功效不足会把"没测出来"误读成"没有效果"，也会让
真实房实验白烧一个晚上。

输入：
- 真实：两夜自由房逐场净分（主仓 datasets/derived/auto-match-v10-2026-09-10/features-*.jsonl）；
- 模拟：门禁 results.jsonl 的配对差值（同牌山配对把牌运方差消掉，方差结构完全不同）。

统计口径（双侧 alpha=0.05、功效 0.80、z 和 = 2.8016）：
- 按房双臂（一房整晚只跑一个臂）：n_房/臂 = 2 z^2 sigma_房^2 / delta^2；
- 房内配对（同一房内两个臂各跑 m 场）：n_房 = 2 z^2 sigma_房内^2 / (m delta^2)；
- 最小可检出效应（给定预算）：delta_min = z_se * SE。

注意：真实房方差必须按**房间聚类**估计（本工作线实测 ICC ~0.53），按单场算会严重高估功效。

用法：
  measure_experiment_power.py --out review/.../experiment-power.json
本脚本只读主仓产物，不写主仓、不改线上代码。
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
import math
import statistics
from pathlib import Path

MAIN = Path("/Users/liyang/Projects/Opensource/hangma-bot")
FEATURES = _project_file(_PROJECT_ROOT, MAIN / "datasets/derived/auto-match-v10-2026-09-10")
Z_SUM = 1.959964 + 0.841621  # 双侧 0.05 + 功效 0.80
NIGHTS = {"v2": _project_file(_PROJECT_ROOT, FEATURES / "features-v2.jsonl"), "tier_a": _project_file(_PROJECT_ROOT, FEATURES / "features-v10.jsonl")}


def per_game_net(path):
    """按场累计我方净分，返回 [(net, room)]。"""
    games = collections.defaultdict(lambda: [0, None])
    for line in path.open(encoding="utf-8"):
        row = json.loads(line)
        entry = games[row["game_id"]]
        entry[0] += row["own_score"]
        entry[1] = row["room"]
    return [(value[0], value[1]) for value in games.values()]


def variance_components(games):
    """返回 (每场净分 sd, 房间均值 sd, 房内 sd, ICC, 每房场数)。"""
    by_room = collections.defaultdict(list)
    for net, room in games:
        by_room[room].append(net)
    nets = [net for net, _ in games]
    room_means = [statistics.mean(values) for values in by_room.values()]
    within = statistics.mean([statistics.variance(values) for values in by_room.values()
                              if len(values) > 1])
    between = statistics.variance(room_means) * len(nets) / len(by_room)
    icc = between / (between + within) if (between + within) else None
    return dict(
        games=len(nets), rooms=len(by_room),
        per_game_sd=statistics.stdev(nets),
        per_room_mean_sd=statistics.stdev(room_means),
        within_room_var=within, within_room_sd=math.sqrt(within),
        between_room_var=between, icc=icc,
        games_per_room=len(nets) / len(by_room),
    )


def rooms_for_effect(per_room_sd, effect):
    """按房双臂设计：每臂所需房间数。"""
    if effect <= 0:
        return None
    return 2 * Z_SUM ** 2 * per_room_sd ** 2 / effect ** 2


def rooms_for_effect_paired(within_sd, games_per_arm, effect):
    """房内配对设计：每房两个臂各跑 games_per_arm 场，所需房间数（两臂合计）。"""
    if effect <= 0 or games_per_arm <= 0:
        return None
    return 2 * Z_SUM ** 2 * within_sd ** 2 / (games_per_arm * effect ** 2)


def min_detectable(se):
    return Z_SUM * se


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = {"z_sum": Z_SUM, "alpha": 0.05, "power": 0.80}
    components = {}
    for name, path in NIGHTS.items():
        components[name] = variance_components(per_game_net(path))
    report["real_nights"] = components

    # 用两夜的平均方差结构做规划（两夜数值接近，说明结构稳定）。
    per_room_sd = statistics.mean([components[name]["per_room_mean_sd"] for name in components])
    within_sd = statistics.mean([components[name]["within_room_sd"] for name in components])
    games_per_room = statistics.mean([components[name]["games_per_room"] for name in components])
    report["planning"] = dict(per_room_mean_sd=per_room_sd, within_room_sd=within_sd,
                              games_per_room=games_per_room)

    effects = [2.0, 4.188, 6.875, 11.0]
    table = {}
    for effect in effects:
        table["{0:.2f}".format(effect)] = dict(
            rooms_per_arm_by_room=rooms_for_effect(per_room_sd, effect),
            rooms_total_paired_full=rooms_for_effect_paired(within_sd, games_per_room, effect),
        )
    report["required_sample"] = table

    budgets = {
        "one_night_40_rooms_per_arm": 40,
        "one_night_47_rooms_per_arm": 47,
        "two_nights_80_rooms_per_arm": 80,
        "four_nights_160_rooms_per_arm": 160,
        "paired_45_rooms_full": 45,
    }
    detectable = {}
    for name, rooms in budgets.items():
        if name.startswith("paired"):
            detectable[name] = dict(
                rooms=rooms,
                min_detectable_effect=min_detectable(
                    within_sd * math.sqrt(2 / (games_per_room * rooms))))
        else:
            detectable[name] = dict(
                rooms_per_arm=rooms,
                min_detectable_effect=min_detectable(per_room_sd * math.sqrt(2 / rooms)))
    report["min_detectable"] = detectable

    # 模拟门禁：配对差值方差（同牌山配对已消掉牌运），给出所需对数。
    review = Path(__file__).resolve().parent
    sim = {}
    for name, baseline, candidate in [
            ("gate-hu-vs-v2-development", "weighted_heuristic_v2", "v2_hu_upgrade_v1"),
            ("gate-pool-homogeneous", "weighted_heuristic_v2", "v2_hu_upgrade_v1"),
            ("gate-dealer-dev32", "v2_hu_upgrade_v1", "v2_hu_upgrade_dealer_v1"),
            ("gate-value-dev32", "v2_hu_upgrade_v1", "v2_value_upgrade_v1")]:
        path = review / name / "results.jsonl"
        if not path.exists():
            continue
        rows = [json.loads(line) for line in path.open(encoding="utf-8")]
        pairs = collections.defaultdict(dict)
        for row in rows:
            key = (row["scenario_id"], tuple(row["seat_permutation"]))
            pairs[key][row["policy_ids_by_seat"][row["seat_permutation"][0]]] = row
        values = []
        by_root = collections.defaultdict(list)
        for key, arms in pairs.items():
            base_row, cand_row = arms.get(baseline), arms.get(candidate)
            if base_row is None or cand_row is None:
                continue
            delta = (cand_row["scores_after"][cand_row["seat_permutation"][0]]
                     - base_row["scores_after"][base_row["seat_permutation"][0]])
            values.append(delta)
            by_root[key[0]].append(delta)
        if len(values) < 2 or len(by_root) < 2:
            continue
        # 门禁的区间按 **根** 聚类自助：有效样本量是根数，不是对数。
        # 用对级方差估功效会显著高估（同根内 4 次换座高度相关）。
        root_means = [statistics.mean(group) for group in by_root.values()]
        root_sd = statistics.stdev(root_means)
        roots = len(root_means)
        observed = statistics.mean(values)
        delta_sd = statistics.stdev(values)
        se_clustered = root_sd / math.sqrt(roots)
        sim[name] = dict(
            pairs=len(values), roots=roots, mean=observed,
            delta_sd_pairs=delta_sd, root_mean_sd=root_sd,
            se_clustered=se_clustered, t_clustered=observed / se_clustered,
            se_pair_naive=delta_sd / math.sqrt(len(values)),
            roots_for_80pct=(2 * Z_SUM ** 2 * root_sd ** 2 / observed ** 2
                             if observed > 0 else None),
            min_detectable_at_roots={str(count): Z_SUM * root_sd / math.sqrt(count)
                                     for count in (32, 128, 512, 2048)})
    report["sim_gates"] = sim

    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + chr(10),
                              encoding="utf-8")
    print(json.dumps(report["real_nights"], ensure_ascii=False, indent=2))
    print()
    for label, entry in report["required_sample"].items():
        print("效应 %-6s 按房双臂需 %7.1f 房/臂 ；房内配对（每臂 %d 场/房）需 %6.1f 房" % (
            label, entry["rooms_per_arm_by_room"] or -1, games_per_room,
            entry["rooms_total_paired_full"] or -1))
    print()
    for label, entry in report["min_detectable"].items():
        print("%-34s 最小可检出效应 %6.2f" % (label, entry["min_detectable_effect"]))
    print()
    for label, entry in sim.items():
        print("%-30s 根=%2d 对=%3d 效应=%7.3f 根级sd=%6.2f t=%5.2f  |  最小可检出(根级)：32=%5.2f 128=%5.2f 512=%5.2f" % (
            label, entry["roots"], entry["pairs"], entry["mean"], entry["root_mean_sd"],
            entry["t_clustered"], entry["min_detectable_at_roots"]["32"],
            entry["min_detectable_at_roots"]["128"],
            entry["min_detectable_at_roots"]["512"]))


if __name__ == "__main__":
    main()
