#!/usr/bin/env python3
"""第 3 步：Q1 进入率 / Q2 转换率 / Q3 财神账 / Q5 归因。

全部口径：
- 统计单位：单局（round）；对手侧恒取「同局另外三座」，与座位无关；
- 配对：每一局算「我方值 − 对手三座均值」，再对该配对差做统计；
- 置信区间：按**房**（room_id）聚类的 CR0 稳健区间 + 房级 bootstrap 对照；
- 全部规则判定来自 rounds.jsonl（由 hangma 产出），本脚本不重算规则。

用法：.venv/bin/python step3_anatomy.py [--in rounds.jsonl] [--out anatomy.json]
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
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stats_lib import (  # noqa: E402
    cluster_bootstrap,
    cluster_ci,
    group_ratio_diff_ci,
    paired_difference,
)

HERE = Path(__file__).resolve().parent


def load_rows(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))
    return rows


def mean(values):
    return sum(values) / len(values) if values else None


def describe(metric_rows, clusters, alpha=0.05):
    """一串配对差的描述 + 双口径 CI。"""

    values = [float(x) for x in metric_rows]
    result = cluster_ci(values, clusters, alpha)
    boot = cluster_bootstrap(values, clusters)
    result["boot_lo"], result["boot_hi"] = boot["lo"], boot["hi"]
    return result


def rate_stats(flags, clusters, alpha=0.05):
    """0/1 比例的聚类 CI。"""

    return cluster_ci([float(x) for x in flags], clusters, alpha)


def table_row(label, ci, denominator, extra=""):
    if ci.get("mean") is None:
        return "| %s | — | — | — | %s |" % (label, extra)
    rng = "聚类不足" if ci.get("lo") is None else "[%.4f, %.4f]" % (ci["lo"], ci["hi"])
    return "| %s | %.4f | %s | %s | %s |" % (label, ci["mean"], rng, denominator, extra)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="infile", default="rounds.jsonl")
    parser.add_argument("--out", dest="outfile", default="anatomy.json")
    args = parser.parse_args(argv)

    rows = load_rows(_project_file(_PROJECT_ROOT, HERE / args.infile))
    print("载入单局 %d" % len(rows))
    out = {"rounds": len(rows)}

    rounds = []
    for row in rows:
        me = next((s["seat"] for s in row["seats"] if s["is_me"]), None)
        if me is None:
            continue
        rounds.append({
            "room": row["room_id"], "game": row["game_id"], "round_no": row["round_no"],
            "me": me, "dealer": row["dealer"], "winner": row["winner_seat"],
            "detail": row["detail"] or [], "fan": row["fan"], "is_draw": row["is_draw"],
            "seats": {s["seat"]: s for s in row["seats"]},
        })
    clusters = [r["room"] for r in rounds]
    print("含我方局 %d；房 %d" % (len(rounds), len(set(clusters))))
    out["rounds_with_me"] = len(rounds)
    out["rooms"] = len(set(clusters))

    # =====================================================================
    print()
    print("## Q1 进入率")
    me_flags = [1.0 if r["seats"][r["me"]]["entered_baotou"] else 0.0 for r in rounds]
    opp_means = []
    for r in rounds:
        others = [s for seat, s in r["seats"].items() if seat != r["me"]]
        opp_means.append(mean([1.0 if s["entered_baotou"] else 0.0 for s in others]))
    diffs = [a - b for a, b in zip(me_flags, opp_means)]
    ci_me = rate_stats(me_flags, clusters)
    ci_opp = rate_stats(opp_means, clusters)
    ci_diff = describe(diffs, clusters)
    out["q1_overall"] = {
        "me_rate": ci_me, "opp_rate": ci_opp, "paired_diff": ci_diff,
        "me_entered_rounds": int(sum(me_flags)), "denominator_rounds": len(rounds),
    }
    print()
    print("| 口径 | 值 | 95% CI（房聚类） | 分母 | 备注 |")
    print("| --- | --- | --- | --- | --- |")
    print(table_row("我方进入率", ci_me, len(rounds)))
    print(table_row("对手三座（同局均值）", ci_opp, len(rounds)))
    print("| **配对差** | %.4f | [%.4f, %.4f] | %d | bootstrap [%.4f, %.4f] |" % (
        ci_diff["mean"], ci_diff["lo"], ci_diff["hi"], len(rounds),
        ci_diff["boot_lo"], ci_diff["boot_hi"]))

    print()
    print("按座位（官方 seat 下标）：")
    print()
    print("| 座位 | 全样本进入率 | 分母 | 我方在该座位的进入率 | 我方分母 | 同座位对手进入率 |")
    print("| --- | --- | --- | --- | --- | --- |")
    by_seat = {}
    for seat in range(4):
        all_flags = [1.0 if r["seats"][seat]["entered_baotou"] else 0.0 for r in rounds]
        mine = [1.0 if r["seats"][seat]["entered_baotou"] else 0.0 for r in rounds if r["me"] == seat]
        theirs = [1.0 if r["seats"][seat]["entered_baotou"] else 0.0 for r in rounds if r["me"] != seat]
        by_seat[seat] = {"all": mean(all_flags), "n_all": len(all_flags),
                         "me": mean(mine), "n_me": len(mine),
                         "opp": mean(theirs), "n_opp": len(theirs)}
        print("| %d | %.4f | %d | %.4f | %d | %.4f |" % (
            seat, mean(all_flags), len(all_flags), mean(mine) if mine else float("nan"),
            len(mine), mean(theirs) if theirs else float("nan")))
    out["q1_by_seat"] = by_seat

    print()
    print("按「我方是否坐庄」分层：")
    print()
    print("| 分层 | 我方进入率 | 对手三座均值 | 配对差 | 95% CI（房聚类） | 分母 |")
    print("| --- | --- | --- | --- | --- | --- |")
    strat = {}
    for label, keep in (("我方坐庄", True), ("我方非坐庄", False)):
        subset = [r for r in rounds if (r["dealer"] == r["me"]) == keep]
        m = [1.0 if r["seats"][r["me"]]["entered_baotou"] else 0.0 for r in subset]
        o = []
        for r in subset:
            others = [s for seat, s in r["seats"].items() if seat != r["me"]]
            o.append(mean([1.0 if s["entered_baotou"] else 0.0 for s in others]))
        ci = describe([a - b for a, b in zip(m, o)], [r["room"] for r in subset])
        strat[label] = {"me": mean(m), "opp": mean(o), "diff": ci, "n": len(subset)}
        print("| %s | %.4f | %.4f | %.4f | [%.4f, %.4f] | %d |" % (
            label, mean(m), mean(o), ci["mean"], ci["lo"], ci["hi"], len(subset)))
    out["q1_by_dealer"] = strat
    dealer_rate = mean([1.0 if r["dealer"] == r["me"] else 0.0 for r in rounds])
    out["q1_dealer_rate"] = dealer_rate
    print()
    print("（我方坐庄占比 %.4f）" % dealer_rate)

    our_wait_states = sum(len(r["seats"][r["me"]]["waits"]) for r in rounds)
    our_baotou_wait_states = sum(sum(1 for w in r["seats"][r["me"]]["waits"] if w[2]) for r in rounds)
    out["q1_anchor"] = {
        "me_entered_rate": ci_me["mean"], "me_entered_rounds": int(sum(me_flags)),
        "rounds": len(rounds), "me_wait_states": our_wait_states,
        "me_baotou_wait_states": our_baotou_wait_states,
        "me_baotou_wait_rate": (our_baotou_wait_states / our_wait_states) if our_wait_states else None,
        "p6_anchor_round_rate": 0.0768, "p6_anchor_window_rate": 0.0085,
    }
    print()
    print("### Q1 锚点对账")
    print()
    print("| 量 | 本次重建 | P6 审计锚点 |")
    print("| --- | --- | --- |")
    print("| 我方曾进入爆头的单局占比 | %.4f（%d/%d 局） | 0.0768（86/1120 局） |" % (
        ci_me["mean"], int(sum(me_flags)), len(rounds)))
    print("| 窗口级爆头占比（口径=我方每个出牌前等待态） | %.4f（%d/%d） | 0.0085（274/32374 决策窗口） |" % (
        our_baotou_wait_states / our_wait_states, our_baotou_wait_states, our_wait_states))
    print()
    print("注：P6 的窗口分母包含平台固定走满的响应窗（每张他家弃牌都会给我方开一次"
          "吃/碰响应窗），本表窗口只数我方自己的出牌前等待态，分母不可直接比；"
          "可比的是单局级比例。")

    # =====================================================================
    print()
    print("## Q2 转换率（条件在进入过爆头）")
    me_entries = [r for r in rounds if r["seats"][r["me"]]["entered_baotou"]]
    me_entry_wins = [r for r in me_entries if r["winner"] == r["me"]]
    opp_entries = []
    for r in rounds:
        for seat, s in r["seats"].items():
            if seat != r["me"] and s["entered_baotou"]:
                opp_entries.append((r, seat))
    opp_entry_wins = [(r, s) for r, s in opp_entries if r["winner"] == s]
    ci_me_conv = rate_stats([1.0 if r["winner"] == r["me"] else 0.0 for r in me_entries],
                            [r["room"] for r in me_entries])
    ci_opp_conv = rate_stats([1.0 if r["winner"] == s else 0.0 for r, s in opp_entries],
                             [r["room"] for r, s in opp_entries])
    print()
    print("| 量 | 我方 | 对手三座 |")
    print("| --- | --- | --- |")
    print("| 进入过爆头的家-局数 | %d | %d |" % (len(me_entries), len(opp_entries)))
    print("| 其中胡牌 | %d | %d |" % (len(me_entry_wins), len(opp_entry_wins)))
    print("| **条件胡牌率** | %.4f [%.4f, %.4f] | %.4f [%.4f, %.4f] |" % (
        ci_me_conv["mean"], ci_me_conv["lo"], ci_me_conv["hi"],
        ci_opp_conv["mean"], ci_opp_conv["lo"], ci_opp_conv["hi"]))
    both = []
    for r in rounds:
        if not r["seats"][r["me"]]["entered_baotou"]:
            continue
        entered_opp = [s for seat, s in r["seats"].items() if seat != r["me"] and s["entered_baotou"]]
        if not entered_opp:
            continue
        mine = 1.0 if r["winner"] == r["me"] else 0.0
        theirs = mean([1.0 if r["winner"] == s["seat"] else 0.0 for s in entered_opp])
        both.append((mine - theirs, r["room"]))
    ci_both = paired_difference([x for x, _ in both], [c for _, c in both])
    print("| **配对差（双方都进入的局）** | %.4f [%.4f, %.4f]（仅 %d 局） | |" % (
        ci_both["mean"], ci_both["lo"], ci_both["hi"], len(both)))
    ratio_diff = group_ratio_diff_ci(
        [(1.0 if r["winner"] == r["me"] else 0.0, r["room"]) for r in me_entries],
        [(1.0 if r["winner"] == s else 0.0, r["room"]) for r, s in opp_entries])
    print("| 比例差（分母不同，房级 bootstrap） | %.4f [%.4f, %.4f] | |" % (
        ratio_diff["mean"], ratio_diff["lo"], ratio_diff["hi"]))
    out["q2_ratio_diff"] = ratio_diff

    def lag_counter(entries, me_side):
        """进入后到胡牌的本人摸牌次数；1 = 进入后的下一摸即胡。"""

        counter = Counter()
        pairs = [(r, r["me"]) for r in entries] if me_side else list(entries)
        for r, seat in pairs:
            if r["winner"] != seat:
                continue
            facts = r["seats"][seat]
            entry_draws = next((item[9] for item in facts["waits"] if item[2]), None)
            if entry_draws is None:
                continue
            counter[facts["draws_n"] - entry_draws] += 1
        return counter
    lag_me = lag_counter(me_entries, True)
    lag_opp = lag_counter(opp_entries, False)
    print()
    print("进入后到胡牌的本人摸牌次数分布（1 = 进入后的下一摸即胡）：")
    print()
    print("| 摸牌次数 | 我方 | 对手三座 |")
    print("| --- | --- | --- |")
    for key in sorted(set(lag_me) | set(lag_opp)):
        print("| %d | %d | %d |" % (key, lag_me[key], lag_opp[key]))
    out["q2"] = {
        "me_entries": len(me_entries), "me_entry_wins": len(me_entry_wins),
        "opp_entries": len(opp_entries), "opp_entry_wins": len(opp_entry_wins),
        "me_conv": ci_me_conv, "opp_conv": ci_opp_conv, "paired": ci_both,
        "me_lag": dict(lag_me), "opp_lag": dict(lag_opp),
    }
    unfilled = Counter()
    for r in me_entries:
        if r["winner"] == r["me"]:
            continue
        unfilled["流局" if r["is_draw"] else "他家先胡"] += 1
    print()
    print("我方进入但没胡的 %d 局构成：%s" % (len(me_entries) - len(me_entry_wins), dict(unfilled)))
    out["q2_unfilled"] = dict(unfilled)

    # =====================================================================
    print()
    print("## Q3 财神账")
    print()
    print("| 量 | 我方（家-局均值） | 对手三座（同局均值） | 配对差 | 95% CI（房聚类） | 我方合计 | 对手合计 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    q3 = {}
    for field, label in (("whites_drawn", "摸到财神"), ("whites_discarded", "打出财神"),
                         ("whites_end", "终局手留财神")):
        m = [float(r["seats"][r["me"]][field]) for r in rounds]
        o = []
        for r in rounds:
            others = [s for seat, s in r["seats"].items() if seat != r["me"]]
            o.append(mean([float(s[field]) for s in others]))
        ci = describe([a - b for a, b in zip(m, o)], clusters)
        q3[field] = {"me": mean(m), "opp": mean(o), "diff": ci,
                     "me_total": int(sum(m)), "opp_total": int(sum(o))}
        print("| %s | %.4f | %.4f | %.4f | [%.4f, %.4f] | %d | %d |" % (
            label, mean(m), mean(o), ci["mean"], ci["lo"], ci["hi"], sum(m), sum(o)))
    out["q3_counts"] = q3

    white_discards_me = sum(r["seats"][r["me"]]["whites_discarded"] for r in rounds)
    white_discards_opp = sum(s["whites_discarded"] for r in rounds
                             for seat, s in r["seats"].items() if seat != r["me"])
    print()
    print("弃白锚点对账：本次重建我方弃白 %d 次 / %d 局（对手三座合计 %d 次 / %d 家-局）。"
          % (white_discards_me, len(rounds), white_discards_opp, 3 * len(rounds)))
    out["q3_white_discards"] = {"me": white_discards_me, "opp": white_discards_opp,
                                "rounds": len(rounds)}

    roles = {"me": Counter(), "opp": Counter()}
    role_n = {"me": 0, "opp": 0}
    for r in rounds:
        if r["winner"] is None:
            continue
        s = r["seats"][r["winner"]]
        group = "me" if r["winner"] == r["me"] else "opp"
        if s["white_in_face"] is None:
            continue
        role_n[group] += 1
        roles[group]["面子内白"] += s["white_in_face"]
        roles[group]["将牌白"] += s["white_in_pair"]
        roles[group]["浮牌白"] += s["white_float"]
    print()
    print("胡牌家的财神用法（hangma win_split 分解证据）：")
    print()
    print("| 角色 | 我方 | 对手三座 |")
    print("| --- | --- | --- |")
    for key in ("面子内白", "将牌白", "浮牌白"):
        print("| %s | %d | %d |" % (key, roles["me"][key], roles["opp"][key]))
    print()
    print("（分母：我方胡 %d 局、对手胡 %d 局）" % (role_n["me"], role_n["opp"]))
    out["q3_white_roles"] = {k: dict(v) for k, v in roles.items()}
    out["q3_white_role_denominator"] = role_n

    # =====================================================================
    print()
    print("## Q5 归因")
    print()
    print("### Q5(a) 手牌成型速度")
    print()
    print("| 量 | 我方 | 对手三座 | 配对差 | 95% CI | 曾达到（我方/对手） |")
    print("| --- | --- | --- | --- | --- | --- |")
    q5a = {}
    for field, label in (("first_std_tenpai_turn", "首次普通型听牌巡数（含财神折算）"),
                         ("first_natural_tenpai_turn", "首次「手留财神=0 的普通型听牌」巡数"),
                         ("first_tenpai_turn", "首次听牌巡数（两种牌型取优）")):
        m, o, cl = [], [], []
        for r in rounds:
            mine = r["seats"][r["me"]][field]
            others = [s[field] for seat, s in r["seats"].items() if seat != r["me"]]
            valid_opp = [x for x in others if x is not None]
            if mine is None or not valid_opp:
                continue
            m.append(float(mine))
            o.append(mean([float(x) for x in valid_opp]))
            cl.append(r["room"])
        reached_me = sum(1 for r in rounds if r["seats"][r["me"]][field] is not None)
        reached_opp = sum(1 for r in rounds for seat, s in r["seats"].items()
                          if seat != r["me"] and s[field] is not None)
        if m:
            ci = paired_difference([a - b for a, b in zip(m, o)], cl)
            q5a[field] = {"me": mean(m), "opp": mean(o), "diff": ci,
                          "reached_me": reached_me, "reached_opp": reached_opp, "pairs": len(m)}
            print("| %s | %.3f | %.3f | %.3f | [%.3f, %.3f] | %d/%d |" % (
                label, mean(m), mean(o), ci["mean"], ci["lo"], ci["hi"], reached_me, reached_opp))
        else:
            print("| %s | 无可配对 | | | | %d/%d |" % (label, reached_me, reached_opp))
    reach_me = mean([1.0 if r["seats"][r["me"]]["first_std_tenpai_turn"] is not None else 0.0
                     for r in rounds])
    reach_opp_pairs = []
    for r in rounds:
        others = [s for seat, s in r["seats"].items() if seat != r["me"]]
        reach_opp_pairs.append(mean([1.0 if s["first_std_tenpai_turn"] is not None else 0.0
                                     for s in others]))
    ci_reach = describe([1.0 if r["seats"][r["me"]]["first_std_tenpai_turn"] is not None else 0.0
                         for r in rounds], clusters)
    print("| 本局曾达到普通型听牌的占比 | %.4f | %.4f | %.4f | [%.4f, %.4f] | %d |" % (
        reach_me, mean(reach_opp_pairs), ci_reach["mean"], ci_reach["lo"], ci_reach["hi"], len(rounds)))

    # 听牌宽度：shanten==0 的等待态上，hangma 列出的有效牌种数均值。
    # 这是「同样跑到听牌，等待面是否更窄」的规则口径量，解释成胡完成率差异。
    width_me, width_opp, width_cl = [], [], []
    for r in rounds:
        mine = [item[7] for item in r["seats"][r["me"]]["waits"] if item[4] == 0]
        if not mine:
            continue
        opp_widths = []
        for seat, s in r["seats"].items():
            if seat == r["me"]:
                continue
            theirs = [item[7] for item in s["waits"] if item[4] == 0]
            if theirs:
                opp_widths.append(mean([float(x) for x in theirs]))
        if not opp_widths:
            continue
        width_me.append(mean([float(x) for x in mine]))
        width_opp.append(mean(opp_widths))
        width_cl.append(r["room"])
    ci_width = paired_difference([a - b for a, b in zip(width_me, width_opp)], width_cl)
    print("| 听牌态平均有效牌种数（hangma useful_tiles） | %.4f | %.4f | %.4f | [%.4f, %.4f] | %d |" % (
        mean(width_me), mean(width_opp), ci_width["mean"], ci_width["lo"], ci_width["hi"],
        len(width_me)))
    q5a["tenpai_width"] = {"me": mean(width_me), "opp": mean(width_opp), "diff": ci_width,
                           "pairs": len(width_me)}

    # 听牌宽度按巡段分层：排除「听的早晚不同」造成的构成差异。
    width_panel = defaultdict(lambda: {"me": [], "opp": []})
    for r in rounds:
        for seat, s in r["seats"].items():
            group = "me" if seat == r["me"] else "opp"
            for item in s["waits"]:
                turn, shanten, useful_n = item[1], item[4], item[7]
                if shanten == 0 and 0 <= turn <= 11:
                    width_panel[turn // 3]["me"].append(float(useful_n)) if group == "me" \
                        else width_panel[turn // 3]["opp"].append(float(useful_n))
    print()
    print("听牌宽度按巡段分层（仅 shanten==0 的等待态）：")
    print()
    print("| 巡段 | 我方均值（n） | 对手均值（n） | 差 |")
    print("| --- | --- | --- | --- |")
    width_json = {}
    for bucket in sorted(width_panel):
        m, o = width_panel[bucket]["me"], width_panel[bucket]["opp"]
        if len(m) < 30 or len(o) < 90:
            continue
        width_json[str(bucket)] = {"me": mean(m), "opp": mean(o), "n_me": len(m), "n_opp": len(o)}
        print("| 第%d-%d手 | %.4f（%d） | %.4f（%d） | %+.4f |" % (
            bucket * 3, bucket * 3 + 2, mean(m), len(m), mean(o), len(o), mean(m) - mean(o)))
    q5a["tenpai_width_panel"] = width_json
    q5a["reach_std_tenpai"] = {"me": reach_me, "opp": mean(reach_opp_pairs), "diff": ci_reach}
    out["q5a"] = q5a

    panel = defaultdict(lambda: {"me": [], "opp": []})
    for r in rounds:
        for seat, s in r["seats"].items():
            group = "me" if seat == r["me"] else "opp"
            for item in s["waits"]:
                turn, whites, std = item[1], item[3], item[5]
                if whites == 0 and 0 <= turn <= 9:
                    panel[turn][group].append(std)
    print()
    print("面板（仅手留财神=0 的等待态）：第 k 手弃牌后 hangma 普通型向听均值")
    print()
    print("| 第 k 手 | 我方 | 对手三座 | 差 |")
    print("| --- | --- | --- | --- |")
    panel_json = {}
    for turn in sorted(panel):
        m, o = panel[turn]["me"], panel[turn]["opp"]
        if len(m) < 30 or len(o) < 90:
            continue
        panel_json[turn] = {"me": mean(m), "opp": mean(o), "n_me": len(m), "n_opp": len(o)}
        print("| %d | %.4f | %.4f | %+.4f |" % (turn, mean(m), mean(o), mean(m) - mean(o)))
    out["q5a_panel_nowhite"] = panel_json

    # Q5(b)
    strata = defaultdict(lambda: {"me": [0, 0], "opp": [0, 0]})
    for r in rounds:
        for seat, s in r["seats"].items():
            group = "me" if seat == r["me"] else "opp"
            for item in s["discard_profile"]:
                turn, whites, chose_white = item["turn"], item["whites"], item["chose_white"]
                if whites < 1:
                    continue
                key = ("第%d-%d手" % (turn // 3 * 3, turn // 3 * 3 + 2), whites)
                strata[key][group][0] += chose_white
                strata[key][group][1] += 1
    print()
    print("### Q5(b) 手上有财神时的弃白率（分层）")
    print()
    print("| 分层（巡段, 手留白数） | 我方弃白/窗口 | 对手弃白/窗口 |")
    print("| --- | --- | --- |")
    q5b = {}
    agg_me = [0, 0]
    agg_opp = [0, 0]
    for key in sorted(strata, key=lambda k: (k[1], k[0])):
        cell = strata[key]
        agg_me[0] += cell["me"][0]
        agg_me[1] += cell["me"][1]
        agg_opp[0] += cell["opp"][0]
        agg_opp[1] += cell["opp"][1]
        label = "%s 白=%d" % key
        q5b[label] = {"me": cell["me"], "opp": cell["opp"]}
        if cell["me"][1] and cell["opp"][1]:
            print("| %s | %d/%d = %.4f | %d/%d = %.4f |" % (
                label, cell["me"][0], cell["me"][1], cell["me"][0] / cell["me"][1],
                cell["opp"][0], cell["opp"][1], cell["opp"][0] / cell["opp"][1]))
    print("| **合计** | %d/%d = %.4f | %d/%d = %.4f |" % (
        agg_me[0], agg_me[1], agg_me[0] / max(1, agg_me[1]),
        agg_opp[0], agg_opp[1], agg_opp[0] / max(1, agg_opp[1])))
    out["q5b"] = q5b
    out["q5b_total"] = {"me": agg_me, "opp": agg_opp}

    pairs, cl = [], []
    for r in rounds:
        mine_w = [x for x in r["seats"][r["me"]]["discard_profile"] if x["whites"] >= 1]
        if not mine_w:
            continue
        opp_rates = []
        for seat, s in r["seats"].items():
            if seat == r["me"]:
                continue
            theirs = [x for x in s["discard_profile"] if x["whites"] >= 1]
            if theirs:
                opp_rates.append(mean([x["chose_white"] for x in theirs]))
        if not opp_rates:
            continue
        pairs.append(mean([x["chose_white"] for x in mine_w]) - mean(opp_rates))
        cl.append(r["room"])
    ci_white = paired_difference(pairs, cl)
    print()
    print("配对（仅双方在该局都有「手上有白」的弃牌窗口）：弃白率差 = %.4f，95%% CI [%.4f, %.4f]，%d 局"
          % (ci_white["mean"], ci_white["lo"], ci_white["hi"], len(pairs)))
    out["q5b_paired"] = ci_white

    (_project_file(_PROJECT_ROOT, HERE / args.outfile)).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("已写出 %s" % (_project_file(_PROJECT_ROOT, HERE / args.outfile)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
