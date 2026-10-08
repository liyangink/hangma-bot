#!/usr/bin/env python3
"""C36 Q6（主审第二轮增补）：爆头收入增量 vs 普通胡收入位移，显式分开算。

口径见 C36-PREREG-DEEP-BAND-CARDS.md 第 7b 节（在该脚本任何运行之前落盘）。
本脚本**只读**已冻结的 .team-work/c36-deep-band/windows.jsonl.gz，不重新重建、不改 src/。

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/c36_q6_accounting.py
"""

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

import collections
import gzip
import json
import math
import random
import statistics
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c36-deep-band")
WINDOWS = _project_file(_PROJECT_ROOT, OUT / "windows.jsonl.gz")

TENG = "u_b2aa6abe7811"
ASTRA = "u_a24596248186"
ME = "u_13495c3d79c8"
L2_ROOMS = ("a_53f4861835b9", "a_5e16dfc1305b", "a_d773a8e428a0", "a_d8e15fe8bc96")
L3_ROOMS = ("a_b0d2cf5da218", "a_d7c3190a1422")
BOOTSTRAP_DRAWS = 1200
BOOTSTRAP_SEED = 20260926


def rate(rows, predicate):
    if not rows:
        return None
    return sum(1 for row in rows if predicate(row)) / len(rows)


def fmt(value, digits=3, signed=False):
    if value is None:
        return "-"
    return ("%+.*f" if signed else "%.*f") % (digits, value)


def quantile(values, probability):
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    low = int(math.floor(position))
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def cluster_bootstrap(rows, statistic, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED):
    by_room = collections.defaultdict(list)
    for row in rows:
        by_room[row["room"]].append(row)
    rooms = sorted(by_room)
    if not rooms:
        return {"lo": None, "hi": None, "mean": None, "rooms": 0}
    rng = random.Random(seed)
    values = []
    for _ in range(draws):
        pool = []
        for _ in rooms:
            pool.extend(by_room[rng.choice(rooms)])
        value = statistic(pool)
        if value is not None:
            values.append(value)
    if not values:
        return {"lo": None, "hi": None, "mean": None, "rooms": len(rooms)}
    values.sort()
    return {"lo": values[int(0.025 * len(values))],
            "hi": values[min(len(values) - 1, int(0.975 * len(values)))],
            "mean": statistics.fmean(values), "rooms": len(rooms)}


FEATURES = collections.OrderedDict((
    ("listening（过牌向听 0）", lambda r: r["pass_shanten"] == 0),
    ("dw>=1", lambda r: r["dw"] is not None and r["dw"] >= 1.0),
    ("dw>=3", lambda r: r["dw"] is not None and r["dw"] >= 3.0),
    ("dw>=6", lambda r: r["dw"] is not None and r["dw"] >= 6.0),
    ("W_pass>=16", lambda r: (r["pass_W"] or 0) >= 16.0),
    ("whites>=1", lambda r: r["whites"] >= 1),
    ("whites>=2", lambda r: r["whites"] >= 2),
    ("melds<=1", lambda r: r["melds"] <= 1),
    ("wall>=40", lambda r: (r["wall"] or 0) >= 40),
    ("turn<=6", lambda r: r["turn"] <= 6),
    ("is_dealer", lambda r: bool(r["is_dealer"])),
    ("bt_now（鸣前已爆头）", lambda r: r["pass_bt"] is True),
    ("margin>0（父代也会鸣）", lambda r: (r["margin"] or 0) > 0),
    ("claim=碰", lambda r: r["claim_type"] == "peng"),
))
# 判据全部来自候选面可读的公开事实；「鸣前已爆头」在动作层继承态里可得。


def main():
    rows = []
    with gzip.open(WINDOWS, "rt", encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))
    print("逐窗记录 %d" % len(rows))

    # ---- 局 x 座 去重 ----
    rounds = {}
    for row in rows:
        key = (row["game_id"], row["round_no"], row["seat"])
        entry = rounds.get(key)
        if entry is None:
            delta = row["outcome"]["seat_delta"]
            detail = row["outcome"]["detail"] or []
            won = bool(row["outcome"]["winner_seat"] == row["seat"])
            entry = {
                "key": key, "room": row["room"], "group": row["group"],
                "user_id": row["user_id"], "room_version": row["room_version"],
                "seat_delta": delta, "won": won,
                "baotou_win": bool(won and "爆头" in detail),
                "fan": row["outcome"]["fan"], "draw": row["outcome"]["draw"],
                "windows": 0, "claimed_windows": 0, "baotou_entry": False,
                "baotou_claim_features": None,
            }
            rounds[key] = entry
        entry["windows"] += 1
        if row["claimed"]:
            entry["claimed_windows"] += 1
            if row["any_fu_baotou"]:
                entry["baotou_entry"] = True
                if entry["baotou_claim_features"] is None:
                    entry["baotou_claim_features"] = row
    ledger = [entry for entry in rounds.values() if entry["seat_delta"] is not None]
    print("局 x 座 行 %d（全部有得分标签）" % len(ledger))

    def account(rows_):
        bao = sum(r["seat_delta"] for r in rows_ if r["baotou_win"])
        plain = sum(r["seat_delta"] for r in rows_
                    if r["won"] and not r["baotou_win"])
        pay = sum(r["seat_delta"] for r in rows_ if not r["won"])
        n = len(rows_)
        wins = [r["seat_delta"] for r in rows_ if r["won"]]
        return {
            "rounds": n,
            "baotou_win": sum(1 for r in rows_ if r["baotou_win"]),
            "plain_win": sum(1 for r in rows_ if r["won"] and not r["baotou_win"]),
            "no_win": sum(1 for r in rows_ if not r["won"]),
            "baotou_income": bao, "plain_income": plain, "pay": pay,
            "net": bao + plain + pay,
            "baotou_income_per_round": (bao / n) if n else None,
            "plain_income_per_round": (plain / n) if n else None,
            "pay_per_round": (pay / n) if n else None,
            "net_per_round": ((bao + plain + pay) / n) if n else None,
            "baotou_win_rate": rate(rows_, lambda r: r["baotou_win"]),
            "plain_win_rate": rate(rows_, lambda r: r["won"] and not r["baotou_win"]),
            "win_rate": rate(rows_, lambda r: r["won"]),
            "avg_win": (statistics.fmean(wins) if wins else None),
            "ge2fan_share": (rate([r for r in rows_ if r["won"]],
                                  lambda r: (r["fan"] or 0) >= 2)),
        }

    g1 = [r for r in ledger if r["baotou_entry"]]
    g2 = [r for r in ledger if r["claimed_windows"] > 0 and not r["baotou_entry"]]
    g3 = [r for r in ledger if r["windows"] > 0 and r["claimed_windows"] == 0]
    print()
    print("== Q6 局 x 座 账本分组（赛后标签；每局只有一个胡家）")
    payload = {"rows": len(ledger), "groups": {}}
    print("  %-34s %7s %7s %7s %9s %9s %8s %8s %8s %8s %7s"
          % ("组", "局", "爆头胡", "普通胡", "爆头收入", "普通胡收", "付分", "每局净",
             "爆头胡率", "胡率", "赢均"))
    for label, subset in (("G1 鸣->进爆头", g1),
                          ("G2 鸣了但没进爆头", g2),
                          ("G3 有机会但没鸣", g3),
                          ("全部局 x 座", ledger)):
        entry = account(subset)
        payload["groups"][label] = entry
        print("  %-34s %7d %7d %7d %9.1f %9.1f %8.1f %8.3f %8.4f %8.4f %7.2f"
              % (label, entry["rounds"], entry["baotou_win"], entry["plain_win"],
                 entry["baotou_income"], entry["plain_income"], entry["pay"],
                 entry["net_per_round"], entry["baotou_win_rate"], entry["win_rate"],
                 entry["avg_win"] or 0.0))
    print("  ⇒ 爆头收入增量（G1 − G3，每局）= %s；普通胡收入位移（G1 − G3，每局）= %s；"
          "付分差 = %s"
          % (fmt((payload["groups"]["G1 鸣->进爆头"]["baotou_income_per_round"] or 0)
                 - (payload["groups"]["G3 有机会但没鸣"]["baotou_income_per_round"] or 0), 3, True),
             fmt((payload["groups"]["G1 鸣->进爆头"]["plain_income_per_round"] or 0)
                 - (payload["groups"]["G3 有机会但没鸣"]["plain_income_per_round"] or 0), 3, True),
             fmt((payload["groups"]["G1 鸣->进爆头"]["pay_per_round"] or 0)
                 - (payload["groups"]["G3 有机会但没鸣"]["pay_per_round"] or 0), 3, True)))

    # ---- 同房内的真人三层对照（复现 C35 的账本形状）----
    print()
    print("== Q6b 同房内「腾蛇 / Astra / 我方」账本对照")
    payload["players"] = {}
    for rooms, label in ((L2_ROOMS, "腾蛇 4 房（R18 v2）"), (L3_ROOMS, "Astra 2 房（R18 v2）")):
        for name, uid in (("腾蛇", TENG), ("Astra", ASTRA), ("我方", ME)):
            subset = [r for r in ledger if r["room"] in rooms and r["user_id"] == uid]
            if not subset:
                continue
            entry = account(subset)
            payload["players"]["%s / %s" % (label, name)] = entry
            print("  [%s] %-5s 局 %4d｜爆头胡 %3d（%s）｜普通胡 %3d（%s）｜"
                  "爆头收入每局 %s｜普通胡收每局 %s｜付分每局 %s｜每局净 %s｜赢时均分 %s"
                  % (label, name, entry["rounds"], entry["baotou_win"],
                     fmt(entry["baotou_win_rate"], 4), entry["plain_win"],
                     fmt(entry["plain_win_rate"], 4),
                     fmt(entry["baotou_income_per_round"], 2),
                     fmt(entry["plain_income_per_round"], 2),
                     fmt(entry["pay_per_round"], 2), fmt(entry["net_per_round"], 2),
                     fmt(entry["avg_win"], 2)))

    # ---- (a) G1 里「最终仍为正收益」的占比与特征差 ----
    print()
    print("== Q6a G1（鸣->进爆头）里，该局该座最终为正收益的窗")
    g1_windows = [r for r in rows if r["claimed"] and r["any_fu_baotou"]]
    pos = [r for r in g1_windows if (r["outcome"]["seat_delta"] or 0) > 0]
    neg = [r for r in g1_windows if (r["outcome"]["seat_delta"] or 0) <= 0]
    print("  鸣->进爆头窗 %d；其中该座当局为正 %d（%s）、非正 %d"
          % (len(g1_windows), len(pos), fmt(rate(g1_windows,
                                                 lambda r: (r["outcome"]["seat_delta"] or 0) > 0), 4),
             len(neg)))
    payload["g1_windows"] = {"windows": len(g1_windows), "positive": len(pos),
                             "negative": len(neg),
                             "positive_share": rate(g1_windows,
                                                    lambda r: (r["outcome"]["seat_delta"] or 0) > 0)}
    for name, predicate in FEATURES.items():
        row = {"positive_hit": rate(pos, predicate), "negative_hit": rate(neg, predicate)}
        row["delta"] = (None if (not pos or not neg)
                        else row["positive_hit"] - row["negative_hit"])
        payload.setdefault("g1_features", {})[name] = row
    for name, row in payload["g1_features"].items():
        print("     %-22s 正 %s｜非正 %s｜差 %s"
              % (name, fmt(row["positive_hit"], 3), fmt(row["negative_hit"], 3),
                 fmt(row["delta"], 3, True)))

    # ---- (b) 决定性检验：在实际鸣了的窗上能否分出「进爆头」----
    print()
    print("== Q6b 决定性检验：实际鸣了的窗上，行动前可算特征能否分出「进爆头」")
    claimed = [r for r in rows if r["claimed"]]
    hit = [r for r in claimed if r["any_fu_baotou"]]
    base = rate(claimed, lambda r: r["any_fu_baotou"])
    print("  实际鸣窗 %d；其中进爆头 %d（基准率 %s）"
          % (len(claimed), len(hit), fmt(base, 4)))
    payload["separability"] = {"claimed": len(claimed), "baotou": len(hit),
                               "base_rate": base, "features": {}}
    for name, predicate in FEATURES.items():
        picked = [r for r in claimed if predicate(r)]
        precision = rate(picked, lambda r: r["any_fu_baotou"])
        recall = rate(hit, predicate)
        lift = None if (not precision or not base) else precision / base
        payload["separability"]["features"][name] = {
            "picked_windows": len(picked), "precision": precision, "recall": recall,
            "lift": lift}
        print("     %-22s 命中 %6d｜precision %s｜recall %s｜lift %s"
              % (name, len(picked), fmt(precision, 4), fmt(recall, 3), fmt(lift, 3)))
    best = max(payload["separability"]["features"].items(),
               key=lambda item: (item[1]["lift"] or 0.0))
    payload["separability"]["best"] = {"feature": best[0], **best[1]}
    print("  最高 lift = %s（%s）" % (fmt(best[1]["lift"], 3), best[0]))
    if hit and claimed:
        ci = cluster_bootstrap(claimed, lambda pool: (
            None if not [r for r in pool if r["any_fu_baotou"]] else
            rate([r for r in pool if r["any_fu_baotou"]], lambda r: r["pass_bt"] is True)))
        payload["separability"]["baotou_window_bt_now"] = ci
        print("  进爆头窗里「鸣前已爆头」的比例 %s（房级区间 [%s, %s]）"
              % (fmt(rate(hit, lambda r: r["pass_bt"] is True), 4),
                 fmt(ci["lo"], 4), fmt(ci["hi"], 4)))


    # ---- (c) 补充读数：判据的「账本代价」——只在该判据为真的窗鸣，会砍掉多少普通胡收入 ----
    print()
    print("== Q6c 补充读数：只在该判据为真的窗鸣，账本会怎么变（局 x 座口径）")
    conj = collections.OrderedDict((
        ("listening", FEATURES["listening（过牌向听 0）"]),
        ("listening ∧ whites>=2", lambda r: (FEATURES["listening（过牌向听 0）"](r)
                                             and FEATURES["whites>=2"](r))),
        ("listening ∧ dw>=6", lambda r: (FEATURES["listening（过牌向听 0）"](r)
                                         and FEATURES["dw>=6"](r))),
        ("listening ∧ bt_now", lambda r: (FEATURES["listening（过牌向听 0）"](r)
                                          and FEATURES["bt_now（鸣前已爆头）"](r))),
        ("listening ∧ melds<=1 ∧ wall>=40",
         lambda r: (FEATURES["listening（过牌向听 0）"](r) and FEATURES["melds<=1"](r)
                    and FEATURES["wall>=40"](r))),
    ))
    payload["conjunctions"] = {}
    for name, predicate in conj.items():
        picked = [r for r in claimed if predicate(r)]
        precision = rate(picked, lambda r: r["any_fu_baotou"])
        recall = rate(hit, predicate)
        keep_keys = {(r["game_id"], r["round_no"], r["seat"]) for r in picked}
        drop_keys = {(r["game_id"], r["round_no"], r["seat"]) for r in claimed
                     if not predicate(r)}
        keep = [r for r in ledger if r["key"] in keep_keys]
        drop = [r for r in ledger if r["key"] in drop_keys and r["key"] not in keep_keys]
        entry = {
            "picked_windows": len(picked), "precision": precision, "recall": recall,
            "lift": None if (not precision or not base) else precision / base,
            "kept_rounds": len(keep), "dropped_rounds": len(drop),
            "kept": account(keep), "dropped": account(drop)}
        payload["conjunctions"][name] = entry
        print("  %-32s 命中 %5d｜precision %s｜recall %s｜lift %s"
              % (name, len(picked), fmt(precision, 4), fmt(recall, 3),
                 fmt(entry["lift"], 2)))
        print("     保留局 %5d：爆头收入/局 %s｜普通胡收入/局 %s｜付分/局 %s｜净/局 %s｜胡率 %s"
              % (len(keep), fmt(entry["kept"]["baotou_income_per_round"], 2),
                 fmt(entry["kept"]["plain_income_per_round"], 2),
                 fmt(entry["kept"]["pay_per_round"], 2),
                 fmt(entry["kept"]["net_per_round"], 2), fmt(entry["kept"]["win_rate"], 3)))
        print("     砍掉局 %5d：爆头收入/局 %s｜普通胡收入/局 %s｜付分/局 %s｜净/局 %s｜胡率 %s"
              % (len(drop), fmt(entry["dropped"]["baotou_income_per_round"], 2),
                 fmt(entry["dropped"]["plain_income_per_round"], 2),
                 fmt(entry["dropped"]["pay_per_round"], 2),
                 fmt(entry["dropped"]["net_per_round"], 2),
                 fmt(entry["dropped"]["win_rate"], 3)))

    (_project_file(_PROJECT_ROOT, OUT / "q6.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                            default=str), encoding="utf-8")
    print()
    print("结果写入 %s" % (_project_file(_PROJECT_ROOT, OUT / "q6.json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
