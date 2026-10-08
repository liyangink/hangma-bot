#!/usr/bin/env python3
"""C32 事后读法：行动前可计算判据的**区分度**、新窗审计与重点格清单。

只读 .team-work/c32-cards/windows.jsonl.gz（c32_cards.py 的紧凑产物），不改任何冻结口径；
输出 .team-work/c32-cards/judgements.json。

三件事：
1. 判据区分度：玄武「实际鸣而父代过」对「同意过」、我方同两类上的命中率差（描述性）；
2. 新窗审计：过牌向听 0 且真实张数净增 >= 6 但父代 margin <= -6 的窗，按 margin 分箱
   看需要多高的剂量才越线（回答「有界剂量能否开出 CELL-R6 未触发的窗」）；
3. 重点格清单：玄武桶与我方同类桶的逐窗明细（含各臂是否改选）。

用法：
    UV_CACHE_DIR=/tmp/uv-cache .venv/bin/python \
        review/freematch-deep-dive-20260925/c32_judgements.py
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
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "c32-cards")
ROWS = _project_file(_PROJECT_ROOT, OUT / "windows.jsonl.gz")
CARDS = _project_file(_PROJECT_ROOT, OUT / "cards.jsonl.gz")

import c32_cards as C32  # noqa: E402  —— 复用同一份抽样代码，保证抽到的卡逐张一致

BT = chr(96)


def code(text):
    return BT + str(text) + BT


def render_compact(card, tags, index):
    """结果文档里的紧凑人可读卡（完整版在 cards.md）。"""

    claims = []
    for item in card["claims"]:
        piece = "%s 鸣后向听%s W%s Δ%s" % (code(item["action_key"]),
                                       item["shanten_after"], item["W_after"],
                                       item["dw_vs_pass"])
        if item.get("fu_discard"):
            piece += "｜跟打 %s（向听%s 张%s 爆头%s 公开%s）" % (
                code(item["fu_discard"]), item.get("fu_shanten"), item.get("fu_W"),
                item.get("fu_baotou"), item.get("fu_exposed"))
        if item["is_parent_pick"]:
            piece += " ★"
        if item.get("baotou_after") is not None:
            piece += "｜动作层爆头 %s" % item["baotou_after"]
        claims.append(piece)
    arms = [name for name, info in sorted(card["arms"].items()) if info["changed_vs_r6"]]
    lines = [
        "#### 卡 %d｜%s r%s seq%s 座%s（%s%s）｜桶 %s" % (
            index, card["game_id"], card["round_no"], card["seq"], card["seat"],
            card["group"], "·玄武" if card["is_xuanwu"] else "", ", ".join(tags) or "-"),
        "- 层：房 %s / %s / 白%s / %s / %s；触发：座 %s 打 %s；墙余 %s；巡目 %s；"
        "自有副露 %s；他家副露 %s 家；持白 %s"
        % (card["room"], "庄" if card["is_dealer"] else "闲", min(2, card["whites"]),
           card["labels"].get("F1"), card["labels"].get("F6"), card["discarder"],
           code(card["tile"]), card["wall"], card["turn"], card["melds"],
           card["opp_meld_seats"], card["whites"]),
        "- 暗牌 %s；过牌向听 %s；格标签 %s"
        % (code("".join(card["my_hand_codes"])), card["pass_shanten"],
           " ".join("%s=%s" % (key, value) for key, value in sorted(card["labels"].items()))),
        "- 父代首选 %s（margin %s）｜R6 首选 %s（margin_r6 %s，%s）｜真实动作 %s"
        % (code(card["parent_plan_first"]), card["margin"], code(card["r6_plan_first"]),
           card["margin_r6"], "改选" if card["r6_changed"] else "不变",
           card["actual"] or "过"),
        "- 候选：%s" % "；".join(claims),
        "- C32 臂相对 R6 改选：%s｜赛后（不作特征）：番 %s／%s／流局 %s／本座当局 %s"
        % ("、".join(arms) or "无", card["outcome"]["fan"],
           "、".join(card["outcome"]["detail"] or []) or "-", card["outcome"]["draw"],
           card["outcome"]["seat_delta"]),
        "",
    ]
    return "\n".join(lines)


def load_rows():
    with gzip.open(ROWS, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def pct(hits, total):
    return None if not total else 100.0 * hits / total


def main():
    rows = list(load_rows())
    print("紧凑行 %d" % len(rows))
    payload = {"windows": len(rows)}

    def pick(predicate, subset):
        return sum(1 for row in subset if row["pred"].get(predicate))

    def group(name, condition):
        return [row for row in rows if condition(row)]

    x_focus = group("X_focus", lambda r: r["is_xuanwu"] and r["claimed"]
                    and not r["parent_claims"])
    x_pass = group("X_agree_pass", lambda r: r["is_xuanwu"] and not r["claimed"]
                   and not r["parent_claims"])
    me_focus = group("ME_focus", lambda r: r["group"] == "me" and r["claimed"]
                     and not r["parent_claims"])
    me_pass = group("ME_agree_pass", lambda r: r["group"] == "me" and not r["claimed"]
                    and not r["parent_claims"])
    print()
    print("== 判据区分度（命中率 %%）：玄武「鸣而父代过」%d vs「同意过」%d；"
          "我方 %d vs %d" % (len(x_focus), len(x_pass), len(me_focus), len(me_pass)))
    print("| 判据 | 玄武·鸣父过 | 玄武·同意过 | 差 | 我方·鸣父过 | 我方·同意过 | 差 |")
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    table = {}
    for predicate in sorted(rows[0]["pred"]):
        xa, xb = pct(pick(predicate, x_focus), len(x_focus)), pct(pick(predicate, x_pass), len(x_pass))
        ma, mb = pct(pick(predicate, me_focus), len(me_focus)), pct(pick(predicate, me_pass), len(me_pass))
        table[predicate] = {"x_focus": xa, "x_pass": xb, "me_focus": ma, "me_pass": mb,
                            "x_delta": None if (xa is None or xb is None) else xa - xb,
                            "me_delta": None if (ma is None or mb is None) else ma - mb}
        print("| %s | %s | %s | %s | %s | %s | %s |"
              % (predicate, "-" if xa is None else "%.1f" % xa,
                 "-" if xb is None else "%.1f" % xb,
                 "-" if table[predicate]["x_delta"] is None else "%+.1f" % table[predicate]["x_delta"],
                 "-" if ma is None else "%.1f" % ma,
                 "-" if mb is None else "%.1f" % mb,
                 "-" if table[predicate]["me_delta"] is None else "%+.1f" % table[predicate]["me_delta"]))
    payload["discrimination"] = table

    print()
    print("== 新窗审计：听牌窗 ∧ 真实张数净增 >= 6 ∧ 父代 margin <= -6")
    new_windows = [row for row in rows
                   if row["pass_shanten"] == 0 and row["dw"] is not None
                   and row["dw"] >= 6.0 and (row["margin"] or 0) <= -6.0]
    bins = collections.Counter()
    for row in new_windows:
        margin = row["margin"]
        if margin > -9.0:
            bins["(-9,-6] 剂量 +7..+9 可越线"] += 1
        elif margin > -12.0:
            bins["(-12,-9] 剂量 +10..+12"] += 1
        else:
            bins["<=-12 剂量需 >= +13"] += 1
    same_cell = sum(1 for row in new_windows if row["labels"].get("F3") == "F3:same")
    print("  窗数 %d（其中 F3:same 标签 %d，说明这些窗父代标签不是「鸣后同向听」）"
          % (len(new_windows), same_cell))
    for key, value in sorted(bins.items(), key=lambda item: -item[1]):
        print("   %s：%d" % (key, value))
    payload["new_window_audit"] = {"windows": len(new_windows), "f3_same": same_cell,
                                   "bins": dict(bins)}

    print()
    print("== 玄武桶 A（实际鸣 ∧ 父代 margin <= 0 ∧ F3:same ∧ F4:wider）")
    focus = [row for row in rows if row["is_xuanwu"] and row["claimed"]
             and (row["margin"] or 0) <= 0 and row["labels"].get("F3") == "F3:same"
             and row["labels"].get("F4") == "F4:wider"]
    detail = []
    for row in sorted(focus, key=lambda item: tuple(item["key"])):
        arms = {name: info["changed_vs_r6"] for name, info in row["arms"].items()}
        detail.append({"key": row["key"], "margin": row["margin"], "dw": row["dw"],
                       "W_after": row["W_after"], "melds": row["melds"], "wall": row["wall"],
                       "pass_shanten": row["pass_shanten"], "r6_changed": row["r6_changed"],
                       "arms_changed_vs_r6": arms, "seat_delta": row["seat_delta"],
                       "fan": row["fan"]})
        print("  %s seq%s 座%s｜margin %s｜dw %s｜W %s｜副露 %s｜墙 %s｜R6 改选 %s｜臂改选 %s｜当局 %s"
              % (row["key"][0][:18], row["key"][2], row["key"][3], row["margin"],
                 row["dw"], row["W_after"], row["melds"], row["wall"], row["r6_changed"],
                 {name: value for name, value in arms.items() if value}, row["seat_delta"]))
    payload["focus_a"] = detail

    print()
    print("== 我方同类桶（F3:same ∩ F4:wider，我方实际鸣）")
    mine = [row for row in rows if row["group"] == "me"
            and row["labels"].get("F3") == "F3:same" and row["labels"].get("F4") == "F4:wider"
            and row["claimed"]]
    delta = collections.Counter("<=0（失败）" if (row["seat_delta"] or 0) <= 0 else ">0（成功）"
                               for row in mine)
    r6_changed = sum(1 for row in mine if row["r6_changed"])
    print("  我方同类鸣牌窗 %d；当局得分分布 %s；其中 CELL-R6 会改选 %d"
          % (len(mine), dict(delta), r6_changed))
    print("  各臂在该桶的改选数：%s"
          % {name: sum(1 for row in mine
                       if row["arms"].get(name, {}).get("changed_vs_parent"))
             for name in sorted(mine[0]["arms"]) if mine})
    payload["me_same_cell"] = {"windows": len(mine), "outcome": dict(delta),
                               "r6_changed": r6_changed}

    print()
    print("== 结果文档用紧凑卡（与 cards.md 同一批抽样）")
    chosen, report = C32.sample_cards(rows)
    wanted = {tuple(rows[index]["key"]) for index in chosen}
    tag_by_key = collections.defaultdict(list)
    for name, indices in C32.bucket_ids(rows).items():
        for index in indices:
            tag_by_key[tuple(rows[index]["key"])].append(name)
    blocks = []
    with gzip.open(CARDS, "rt", encoding="utf-8") as handle:
        for line in handle:
            card = json.loads(line)
            key = (card["game_id"], card["round_no"], card["seq"], card["seat"])
            if key not in wanted:
                continue
            blocks.append((key, card, tag_by_key.get(key, [])))
    blocks.sort(key=lambda item: tuple(item[0]))
    rendered = [render_compact(card, tags, index)
                for index, (_key, card, tags) in enumerate(blocks, start=1)]
    (_project_file(_PROJECT_ROOT, OUT / "cards-compact.md")).write_text("\n".join(rendered), encoding="utf-8")
    payload["sample_report"] = report
    payload["sample_kinds"] = {index: [card["group"], "玄武" if card["is_xuanwu"] else "",
                                       tags] for index, (key, card, tags)
                               in enumerate(blocks, start=1)}
    print("  紧凑卡 %d 张 → %s" % (len(rendered), _project_file(_PROJECT_ROOT, OUT / "cards-compact.md")))

    (_project_file(_PROJECT_ROOT, OUT / "judgements.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2,
                                                    default=str), encoding="utf-8")
    print()
    print("结果写入 %s" % (_project_file(_PROJECT_ROOT, OUT / "judgements.json")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
