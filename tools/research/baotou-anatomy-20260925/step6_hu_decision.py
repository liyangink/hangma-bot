#!/usr/bin/env python3
"""第 6 步（主审质询后的修正）：真正的决策轴 —— 自摸胡 vs 弃胡换爆头。

质询揭露的问题：第 4 步的「改选率 0.0000%」只覆盖了**弃牌窗口内部**的候选选择，
而爆头真正的决策点在**摸牌窗口**：手里 14 张已成胡时，是立刻自摸胡，还是弃一张
把暗牌做成爆头、下一摸拿 ×2。

本脚本回答：
1. 这样的摸牌窗口有多少（我方 / 对手）；
2. 其中「存在一张能让弃后暗牌变成爆头的合法弃牌」的有多少（= 靶子）；
3. 父代在这些窗口上实际选了什么；**有靶子却选胡** 的就是这条轴上的改选率；
4. 弃胡却**没有**进入爆头（白弃一手胡）的有多少；
5. 与第 4 步的弃牌窗口改选率并列，给出「整条爆头通道」决策层的上界。

口径说明（必须与结论一起读）：本批数据各房 manifest 的 you_cai_bi_kao 全为
False（第 5 步实测），因此「成胡 + 手留财神 + 未爆头」时自摸胡是**合法**动作，
弃胡是一个真实可选、且被父代实际使用过的选择。
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from stats_lib import group_ratio_diff_ci, paired_difference  # noqa: E402


def mean(values):
    return sum(values) / len(values) if values else None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="infile", default="rounds.jsonl")
    parser.add_argument("--out", dest="outfile", default="hu-decision.json")
    args = parser.parse_args(argv)

    rows = []
    with open(_project_file(_PROJECT_ROOT, HERE / args.infile), encoding="utf-8") as handle:
        for line in handle:
            rows.append(json.loads(line))
    rounds = []
    for row in rows:
        me = next((s["seat"] for s in row["seats"] if s["is_me"]), None)
        if me is None:
            continue
        rounds.append({"room": row["room_id"], "me": me, "winner": row["winner_seat"],
                       "seats": {s["seat"]: s for s in row["seats"]}})
    clusters = [r["room"] for r in rounds]
    print("含我方局 %d；房 %d" % (len(rounds), len(set(clusters))))

    def collect(group):
        out = []
        for r in rounds:
            for seat, s in r["seats"].items():
                if (seat == r["me"]) != (group == "me"):
                    continue
                out.append((r, seat, s))
        return out

    payload = {}
    for group, label in (("me", "我方"), ("opp", "对手三座")):
        counter = Counter()
        per_round = defaultdict(float)
        for r, seat, s in collect(group):
            counter["seat_rounds"] += 1
            for w in s["hu_windows"]:
                _seq, _turn, melds, whites, baotou_after, n_targets, chosen, _t = w
                counter["hu_windows"] += 1
                per_round[r["room"]] += 0
                if n_targets > 0:
                    counter["with_target"] += 1
                if chosen == "hu":
                    counter["chose_hu"] += 1
                    if n_targets > 0:
                        counter["missed_target"] += 1
                elif str(chosen).startswith("discard"):
                    counter["chose_discard"] += 1
                    if n_targets > 0:
                        counter["discard_enters"] += 1
                    else:
                        counter["discard_no_target"] += 1
                else:
                    counter["unresolved"] += 1
                if baotou_after:
                    counter["already_baotou"] += 1
        payload[label] = dict(counter)
        print()
        print("### %s" % label)
        print()
        print("| 量 | 计数 | 分母 |")
        print("| --- | --- | --- |")
        print("| 家-局数 | %d | — |" % counter["seat_rounds"])
        print("| 摸牌窗口里 14 张已成胡 | %d | %.4f / 家-局 |" % (
            counter["hu_windows"], counter["hu_windows"] / max(1, counter["seat_rounds"])))
        print("| 其中存在「弃后即爆头」的合法弃牌 | %d | %.4f / 家-局 |" % (
            counter["with_target"], counter["with_target"] / max(1, counter["seat_rounds"])))
        print("| 父代选胡 | %d | — |" % counter["chose_hu"])
        print("| **有靶子却选胡（这条轴上的改选机会）** | **%d** | %.4f / 家-局 |" % (
            counter["missed_target"], counter["missed_target"] / max(1, counter["seat_rounds"])))
        print("| 父代弃胡 | %d | — |" % counter["chose_discard"])
        print("| 其中弃后确实进入爆头 | %d | — |" % counter["discard_enters"])
        print("| 其中弃后**没有**进入爆头（白弃一手胡） | %d | — |" % counter["discard_no_target"])
        print("| 该窗口弃胡前已是爆头态（弃胡=财飘加链） | %d | — |" % counter["already_baotou"])

    me = payload["我方"]
    op = payload["对手三座"]
    print()
    print("### 改选率对照（分母都是我方的决策窗口）")
    print()
    print("| 轴 | 我方机会 | 对手机会（每个座位，同局均值口径另见下） |")
    print("| --- | --- | --- |")
    total_discard_windows_me = sum(
        int(r["seats"][r["me"]]["reach_summary"]["windows"]) for r in rounds)
    print("| 弃牌窗口内部的候选改选率（第 4 步） | 0 / %d = 0.0000%% | — |" % total_discard_windows_me)
    print("| **摸牌窗口上的「弃胡换爆头」改选机会** | **%d / %d = %.4f%%** | %d / %d = %.4f%% |" % (
        me["missed_target"], me["hu_windows"],
        100.0 * me["missed_target"] / max(1, me["hu_windows"]),
        op["missed_target"], op["hu_windows"],
        100.0 * op["missed_target"] / max(1, op["hu_windows"])))
    print("| 父代实际弃胡率（弃胡 / 已成胡的摸牌窗口） | %d / %d = %.4f%% | %d / %d = %.4f%% |" % (
        me["chose_discard"], me["hu_windows"],
        100.0 * me["chose_discard"] / max(1, me["hu_windows"]),
        op["chose_discard"], op["hu_windows"],
        100.0 * op["chose_discard"] / max(1, op["hu_windows"])))

    # 按局配对的「已成胡摸牌窗口数」与「弃胡数」
    print()
    print("### 按局配对（每局：我方值 − 对手三座均值）")
    print()
    print("| 量 | 我方每局 | 对手三座每局 | 配对差 | 95% CI（房聚类） |")
    print("| --- | --- | --- | --- | --- |")
    for key, label in (("hu_windows", "已成胡的摸牌窗口"), ("missed_target", "有靶子却选胡"),
                       ("chose_discard", "弃胡次数"), ("with_target", "摸牌窗口有爆头靶子")):
        m, o = [], []
        for r in rounds:
            mine = r["seats"][r["me"]]
            others = [s for seat, s in r["seats"].items() if seat != r["me"]]
            m.append(float(count_key(mine, key)))
            o.append(mean([float(count_key(s, key)) for s in others]))
        ci = paired_difference([a - b for a, b in zip(m, o)], clusters)
        print("| %s | %.4f | %.4f | %.4f | [%.4f, %.4f] |" % (
            label, mean(m), mean(o), ci["mean"], ci["lo"], ci["hi"]))
        payload["paired_" + key] = {"me": mean(m), "opp": mean(o), "diff": ci}

    ratio = group_ratio_diff_ci(
        [(1.0 if count_key(r["seats"][r["me"]], "missed_target") else 0.0, r["room"]) for r in rounds],
        [(1.0 if count_key(s, "missed_target") else 0.0, r["room"])
         for r in rounds for seat, s in r["seats"].items() if seat != r["me"]])
    print()
    print("「本局至少出现一次有靶子却选胡」比例差（我方 − 对手三座，房级 bootstrap）：%.4f [%.4f, %.4f]"
          % (ratio["mean"], ratio["lo"], ratio["hi"]))
    payload["missed_round_ratio_diff"] = ratio
    payload["me_hu_windows_by_room"] = dict(
        Counter(r["room"] for r in rounds))

    (_project_file(_PROJECT_ROOT, HERE / args.outfile)).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("已写出 %s" % (_project_file(_PROJECT_ROOT, HERE / args.outfile)))
    return 0


def count_key(seat_facts, key):
    """按 per_seat 里的 hu_windows 现场统计某一类的家-局计数（0/1）。"""

    windows = seat_facts["hu_windows"]
    if key == "hu_windows":
        return len(windows)
    if key == "missed_target":
        return sum(1 for w in windows if w[5] > 0 and w[6] == "hu")
    if key == "with_target":
        return sum(1 for w in windows if w[5] > 0)
    if key == "chose_discard":
        return sum(1 for w in windows if str(w[6]).startswith("discard"))
    raise KeyError(key)


if __name__ == "__main__":
    raise SystemExit(main())
