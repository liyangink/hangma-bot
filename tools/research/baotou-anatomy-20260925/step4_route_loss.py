#!/usr/bin/env python3
"""第 4 步：Q4 路线丢失点 —— 每个弃牌窗口上「能否改选进入爆头」。

判定链（全部经 hangma，并在此脚本内做暴力对拍）：
1. 窗口的 14 张暗牌先交给 hand_analysis.win_split 判定是否本身已胡；
   不胡则该窗口**任何**合法弃牌都不可能进入爆头（必要条件，理由见
   anatomy_lib.reachability 的 docstring）；
2. 对每个合法弃牌候选，用 progression.baotou_after_discard 判定弃后是否爆头；
3. 改选率 = 「存在进入爆头的合法弃牌，但父代没选它」的窗口 / 全部窗口
   （与 l1_reach.py 的 10% 门槛同分母口径）。

暴力对拍（--verify）：随机抽取弃牌窗口，**不做**第 1 步过滤，直接把每个候选
弃牌算一遍，统计有多少窗口在「14 张不胡」的前提下仍然存在爆头候选。理论上
必须为 0；不为 0 说明必要条件写错，Q4 的所有数字作废。

用法：
    .venv/bin/python step4_route_loss.py                 # 出表
    .venv/bin/python step4_route_loss.py --verify 20000  # 对拍必要条件
"""

from __future__ import annotations

from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/baotou-anatomy-20260925'

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
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import anatomy_lib as lib  # noqa: E402
from stats_lib import cluster_ci, group_ratio_diff_ci, paired_difference  # noqa: E402


def mean(values):
    return sum(values) / len(values) if values else None


def load_rows(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def brute_force(rows, sample_size, seed):
    """对拍：不设必要条件，直接枚举候选。返回 (抽样窗口, 违例窗口)。"""

    rng = random.Random(seed)
    games = {g["game_id"]: g for g in lib.load_games()}
    wanted = {}
    for row in rows:
        wanted.setdefault(row["game_id"], set()).add(row["round_no"])
    windows = []
    for game_id in sorted(wanted):
        game = games.get(game_id)
        if game is None:
            continue
        for round_no, events, start_hands in lib.round_blocks(game["doc"]):
            if round_no not in wanted[game_id]:
                continue
            recon = lib.reconstruct_round(events, start_hands)
            windows.extend(recon["discard_windows"])
    print("可暴力枚举的弃牌窗口 %d" % len(windows))
    if sample_size and sample_size < len(windows):
        picked = rng.sample(windows, sample_size)
    else:
        picked = windows
    violations = []
    counter = Counter()
    for window in picked:
        hand = window["hand_before"]
        melds = window["meld_count"]
        from hangma_bot.hangma import hand_analysis
        from hangma_bot.hangma.progression import baotou_after_discard
        is_win = hand_analysis.win_split(hand, melds) is not None
        counter["is_win" if is_win else "not_win"] += 1
        targets = 0
        for code in sorted({tile.code for tile in hand}):
            after = lib.drop_tile(hand, code)
            if after is not None and baotou_after_discard(after, melds):
                targets += 1
        if targets:
            counter["has_target"] += 1
            if not is_win:
                counter["violation"] += 1
                if len(violations) < 10:
                    violations.append({
                        "seq": window["seq"], "seat": window["seat"],
                        "hand": [t.code for t in hand], "melds": melds,
                        "targets": targets,
                    })
    print("抽样 %d；其中 14 张已胡 %d、存在爆头候选 %d、违例 %d" % (
        len(picked), counter["is_win"], counter["has_target"], counter["violation"]))
    if violations:
        print("违例样例：")
        for item in violations:
            print("  ", json.dumps(item, ensure_ascii=False))
    return counter


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="infile", default="rounds.jsonl")
    parser.add_argument("--out", dest="outfile", default="route-loss.json")
    parser.add_argument("--verify", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260925)
    args = parser.parse_args(argv)

    rows = load_rows(_project_file(_PROJECT_ROOT, HERE / args.infile))

    if args.verify:
        counter = brute_force(rows, args.verify, args.seed)
        (_project_file(_PROJECT_ROOT, HERE / "route-loss-verify.json")).write_text(
            json.dumps(dict(counter), ensure_ascii=False, indent=2), encoding="utf-8")
        return 0 if counter["violation"] == 0 else 1

    rounds = []
    for row in rows:
        me = next((s["seat"] for s in row["seats"] if s["is_me"]), None)
        if me is None:
            continue
        rounds.append({
            "room": row["room_id"], "me": me, "winner": row["winner_seat"],
            "detail": row["detail"] or [], "is_draw": row["is_draw"],
            "seats": {s["seat"]: s for s in row["seats"]},
        })
    clusters = [r["room"] for r in rounds]
    print("含我方局 %d；房 %d" % (len(rounds), len(set(clusters))))

    print()
    print("## Q4 路线丢失点")
    print()
    print("### Q4.1 前提窗口率：14 张暗牌本身已胡的弃牌窗口")
    print()
    print("| 口径 | 我方 | 对手三座（同局均值） | 配对差 | 95% CI（房聚类） | 分母（我方/对手） |")
    print("| --- | --- | --- | --- | --- | --- |")
    payload = {}
    fields = [
        ("windows", "弃牌窗口"),
        ("win_hand_windows", "其中 14 张已胡（进爆头的前提）"),
        ("target_windows", "其中存在「弃后即爆头」的合法弃牌"),
        ("chosen_target_windows", "父代实际选中了那种弃牌"),
        ("missed_windows", "父代没选中（改选可进入爆头）"),
    ]
    for field, label in fields:
        m = [float(r["seats"][r["me"]]["reach_summary"][field]) for r in rounds]
        o = []
        for r in rounds:
            others = [s for seat, s in r["seats"].items() if seat != r["me"]]
            o.append(mean([float(s["reach_summary"][field]) for s in others]))
        ci = paired_difference([a - b for a, b in zip(m, o)], clusters)
        # o 是「每局对手三座均值」，其和是全样本对手家-局总数的 1/3；
        # 表里报真实家-局总数，避免把 1/3 当成总数读。
        opp_total = int(round(sum(o) * 3))
        payload[field] = {"me": mean(m), "opp": mean(o), "diff": ci,
                          "me_total": int(sum(m)), "opp_total": opp_total}
        print("| %s | %.4f | %.4f | %.4f | [%.4f, %.4f] | %d / %d |" % (
            label, mean(m), mean(o), ci["mean"], ci["lo"], ci["hi"], sum(m), opp_total))

    total_windows = sum(int(r["seats"][r["me"]]["reach_summary"]["windows"]) for r in rounds)
    target_windows = sum(int(r["seats"][r["me"]]["reach_summary"]["target_windows"]) for r in rounds)
    missed = sum(int(r["seats"][r["me"]]["reach_summary"]["missed_windows"]) for r in rounds)
    chosen = sum(int(r["seats"][r["me"]]["reach_summary"]["chosen_target_windows"]) for r in rounds)
    better = sum(int(r["seats"][r["me"]]["reach_summary"]["better_than_chosen_windows"]) for r in rounds)

    print()
    print("我方合计：弃牌窗口 %d；其中存在进入爆头的合法弃牌 %d；父代选中 %d；没选中 %d"
          % (total_windows, target_windows, chosen, missed))
    print()
    print("| 改选率口径 | 分子 | 分母 | 比率 |")
    print("| --- | --- | --- | --- |")
    print("| 改选率（对全部弃牌窗口，与 l1_reach.py 同分母） | %d | %d | **%.4f%%** |" % (
        missed, total_windows, 100.0 * missed / max(1, total_windows)))
    print("| 改选率（对「有靶子」的窗口） | %d | %d | %.4f%% |" % (
        missed, target_windows, 100.0 * missed / max(1, target_windows)))
    print("| 描述性：存在 hangma 口径上更优候选的已胡窗口 | %d | %d | %.4f%% |" % (
        better, total_windows, 100.0 * better / max(1, total_windows)))

    # 有靶子的窗口明细（我方）
    detail = []
    for row in rows:
        me = next((s for s in row["seats"] if s["is_me"]), None)
        if me is None:
            continue
        for item in me["reach_windows"]:
            if item[2] > 0:
                detail.append({
                    "game_id": row["game_id"], "round_no": row["round_no"], "seq": item[0],
                    "turn": item[1], "n_targets": item[2], "chosen_target": item[3],
                    "better_than_chosen": item[4], "whites_held": item[5],
                    "melds": item[6], "chosen": item[7],
                    "winner": row["winner_seat"], "me_is_winner": row["winner_seat"] == me["seat"],
                    "detail": row["detail"],
                })
    print()
    print("有靶子窗口逐条（我方，共 %d 条）：" % len(detail))
    print()
    print("| # | game_id | 局 | 巡 | 候选命中数 | 父代命中 | 门清? 副露 | 手留白 | 弃牌 | 本局结果 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for index, item in enumerate(detail, 1):
        print("| %d | %s | %d | %d | %d | %s | %d | %d | %s | %s%s |" % (
            index, item["game_id"], item["round_no"], item["turn"], item["n_targets"],
            "是" if item["chosen_target"] else "**否**", item["melds"], item["whites_held"],
            item["chosen"], "我方胡 " if item["me_is_winner"] else "",
            ",".join(item["detail"] or [])))

    # 全座位对照的改选率（对手侧）
    opp_windows = opp_target = opp_missed = 0
    for r in rounds:
        for seat, s in r["seats"].items():
            if seat == r["me"]:
                continue
            opp_windows += s["reach_summary"]["windows"]
            opp_target += s["reach_summary"]["target_windows"]
            opp_missed += s["reach_summary"]["missed_windows"]
    print()
    print("对手侧同口径：弃牌窗口 %d；有靶子 %d；改选率（全部窗口）%.4f%%；（有靶子窗口）%.4f%%" % (
        opp_windows, opp_target, 100.0 * opp_missed / max(1, opp_windows),
        100.0 * opp_missed / max(1, opp_target)))

    # ---- Q4.2 前提窗口的来路分解 + 副露率 ----
    print()
    print("### Q4.2 前提窗口的来路分解（摸牌后 vs 鸣牌后）与副露率")
    print()
    print("| 量（每局均值） | 我方 | 对手三座（同局均值） | 配对差 | 95% CI（房聚类） |")
    print("| --- | --- | --- | --- | --- |")
    origin_fields = [
        ("windows_draw", "摸牌后的弃牌窗口"),
        ("windows_meld", "鸣牌后的弃牌窗口"),
        ("win_hand_draw", "其中 14 张已胡（摸牌后）"),
        ("win_hand_meld", "其中 14 张已胡（鸣牌后）"),
        ("target_draw", "其中可进爆头（摸牌后）"),
        ("target_meld", "其中可进爆头（鸣牌后）"),
    ]
    payload["origin"] = {}
    for field, label in origin_fields:
        m = [float(r["seats"][r["me"]]["reach_summary"][field]) for r in rounds]
        o = []
        for r in rounds:
            others = [s for seat, s in r["seats"].items() if seat != r["me"]]
            o.append(mean([float(s["reach_summary"][field]) for s in others]))
        ci = paired_difference([a - b for a, b in zip(m, o)], clusters)
        payload["origin"][field] = {"me": mean(m), "opp": mean(o), "diff": ci}
        print("| %s | %.4f | %.4f | %.4f | [%.4f, %.4f] |" % (
            label, mean(m), mean(o), ci["mean"], ci["lo"], ci["hi"]))
    m = [float(r["seats"][r["me"]]["melds_end"]) for r in rounds]
    o = []
    for r in rounds:
        others = [s for seat, s in r["seats"].items() if seat != r["me"]]
        o.append(mean([float(s["melds_end"]) for s in others]))
    ci = paired_difference([a - b for a, b in zip(m, o)], clusters)
    payload["melds_end"] = {"me": mean(m), "opp": mean(o), "diff": ci}
    print("| 终局副露数 | %.4f | %.4f | %.4f | [%.4f, %.4f] |" % (
        mean(m), mean(o), ci["mean"], ci["lo"], ci["hi"]))
    ratio_meld = group_ratio_diff_ci(
        [(1.0 if r["seats"][r["me"]]["melds_end"] > 0 else 0.0, r["room"]) for r in rounds],
        [(1.0 if s["melds_end"] > 0 else 0.0, r["room"])
         for r in rounds for seat, s in r["seats"].items() if seat != r["me"]])
    print()
    print("「本局有副露」比例差（我方 − 对手三座，房级 bootstrap）：%.4f [%.4f, %.4f]" % (
        ratio_meld["mean"], ratio_meld["lo"], ratio_meld["hi"]))
    payload["meld_round_ratio_diff"] = ratio_meld

    # ---- Q1 的量级分解：进入率 = 前提窗口率 × 前提内转化率 ----
    def agg(group):
        windows = precursor = targets = entries = 0
        for r in rounds:
            for seat, s in r["seats"].items():
                if (seat == r["me"]) != (group == "me"):
                    continue
                windows += s["reach_summary"]["windows"]
                precursor += s["reach_summary"]["win_hand_windows"]
                targets += s["reach_summary"]["target_windows"]
                if s["entered_baotou"]:
                    entries += 1
        return windows, precursor, targets, entries
    w_me, p_me, t_me, e_me = agg("me")
    w_op, p_op, t_op, e_op = agg("opp")
    conv_me = t_me / max(1, p_me)
    conv_op = t_op / max(1, p_op)
    print()
    print("### Q4.3 Q1 的量级分解（进入率 = 前提窗口率 × 前提内转化率）")
    print()
    print("| 量 | 我方 | 对手三座 |")
    print("| --- | --- | --- |")
    print("| 弃牌窗口 | %d | %d |" % (w_me, w_op))
    print("| 前提窗口（14 张已胡） | %d（每窗口 %.5f） | %d（每窗口 %.5f） |" % (
        p_me, p_me / w_me, p_op, p_op / w_op))
    print("| 可进爆头窗口 | %d | %d |" % (t_me, t_op))
    print("| 前提内转化率 | %.4f | %.4f |" % (conv_me, conv_op))
    print("| 曾进入爆头的家-局数 | %d | %d |" % (e_me, e_op))
    print()
    print("反事实（把前提窗口率与转化率分别换成对手水平）：")
    print()
    print("| 反事实 | 进入率（每家-局） | 相对对手 |")
    print("| --- | --- | --- |")
    opp_rate = p_op / w_op * conv_op
    print("| 对手实际（%.5f × %.4f） | %.5f | — |" % (p_op / w_op, conv_op, opp_rate))
    print("| 我方实际（%.5f × %.4f） | %.5f | %.2f× |" % (
        p_me / w_me, conv_me, p_me / w_me * conv_me, (p_me / w_me * conv_me) / opp_rate))
    print("| 换成对手前提窗口率、保留我方转化率 | %.5f | %.2f× |" % (
        p_op / w_op * conv_me, (p_op / w_op * conv_me) / opp_rate))
    print("| 保留我方前提窗口率、换成对手转化率 | %.5f | %.2f× |" % (
        p_me / w_me * conv_op, (p_me / w_me * conv_op) / opp_rate))
    # ---- Q4.4 按副露数分层的「窗口 → 已胡」转化率 ----
    print()
    print("### Q4.4 前提窗口率按副露数分层（同样的副露数下比牌）")
    print()
    print("| 副露数 | 我方窗口 | 我方已胡 | 我方已胡率 | 对手窗口 | 对手已胡 | 对手已胡率 | 对手/我方 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    strat = {}
    for level in range(5):
        key = str(level)
        mw = sum(r["seats"][r["me"]]["reach_summary"]["windows_by_melds"][key] for r in rounds)
        mh = sum(r["seats"][r["me"]]["reach_summary"]["win_by_melds"][key] for r in rounds)
        ow = oh = 0
        for r in rounds:
            for seat, s in r["seats"].items():
                if seat == r["me"]:
                    continue
                ow += s["reach_summary"]["windows_by_melds"][key]
                oh += s["reach_summary"]["win_by_melds"][key]
        rate_me = mh / max(1, mw)
        rate_op = oh / max(1, ow)
        strat[key] = {"me_windows": mw, "me_win": mh, "me_rate": rate_me,
                      "opp_windows": ow, "opp_win": oh, "opp_rate": rate_op}
        print("| %d | %d | %d | %.4f%% | %d | %d | %.4f%% | %.2f× |" % (
            level, mw, mh, 100 * rate_me, ow, oh, 100 * rate_op,
            rate_op / rate_me if rate_me else float("inf")))
    payload["meld_strata"] = strat

    # ---- Q4.5 前提窗口的财神携带率（解释「为什么摸牌后窗口必然有白」） ----
    print()
    print("### Q4.5 前提窗口（14 张已胡）的财神携带率")
    print()
    print("| 组 | 副露=0 已胡窗口 | 其中手留财神≥1 | 占比 | 副露>0 已胡窗口 | 其中手留财神≥1 | 占比 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    carry = {}
    for group in ("me", "opp"):
        counts = {}
        for m0 in (True, False):
            total = keep = 0
            for row in rows:
                me_seat = next((s["seat"] for s in row["seats"] if s["is_me"]), None)
                if me_seat is None:
                    continue
                for s in row["seats"]:
                    if (s["seat"] == me_seat) != (group == "me"):
                        continue
                    for w in s["reach_windows"]:
                        if (w[6] == 0) != m0:
                            continue
                        total += 1
                        if w[5] >= 1:
                            keep += 1
            counts["melds0" if m0 else "melds_pos"] = {
                "windows": total, "with_white": keep, "rate": keep / max(1, total)}
        carry[group] = counts
        print("| %s | %d | %d | %.4f%% | %d | %d | %.4f%% |" % (
            "我方" if group == "me" else "对手三座",
            counts["melds0"]["windows"], counts["melds0"]["with_white"],
            100 * counts["melds0"]["rate"],
            counts["melds_pos"]["windows"], counts["melds_pos"]["with_white"],
            100 * counts["melds_pos"]["rate"]))
    payload["precursor_white_carry"] = carry

    payload["decomposition"] = {
        "windows": {"me": w_me, "opp": w_op},
        "precursor": {"me": p_me, "opp": p_op},
        "targets": {"me": t_me, "opp": t_op},
        "entries": {"me": e_me, "opp": e_op},
        "conversion": {"me": conv_me, "opp": conv_op},
        "precursor_per_window": {"me": p_me / w_me, "opp": p_op / w_op},
    }

    payload["totals_me"] = {
        "windows": total_windows, "target_windows": target_windows,
        "chosen": chosen, "missed": missed, "better_than_chosen": better,
        "reselect_rate_all_windows": missed / max(1, total_windows),
        "reselect_rate_target_windows": missed / max(1, target_windows),
    }
    payload["totals_opp"] = {
        "windows": opp_windows, "target_windows": opp_target, "missed": opp_missed,
        "reselect_rate_all_windows": opp_missed / max(1, opp_windows),
        "reselect_rate_target_windows": opp_missed / max(1, opp_target),
    }
    payload["detail"] = detail

    # 比例差：进爆头的前提窗口率（我方 vs 对手，分母不同）
    ratio = group_ratio_diff_ci(
        [(1.0 if r["seats"][r["me"]]["reach_summary"]["win_hand_windows"] else 0.0, r["room"])
         for r in rounds],
        [(1.0 if s["reach_summary"]["win_hand_windows"] else 0.0, r["room"])
         for r in rounds for seat, s in r["seats"].items() if seat != r["me"]])
    print()
    print("「本局至少出现一个前提窗口」比例差（我方 − 对手三座，房级 bootstrap）：%.4f [%.4f, %.4f]"
          % (ratio["mean"], ratio["lo"], ratio["hi"]))
    payload["win_hand_round_ratio_diff"] = ratio

    (_project_file(_PROJECT_ROOT, HERE / args.outfile)).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("已写出 %s" % (_project_file(_PROJECT_ROOT, HERE / args.outfile)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
