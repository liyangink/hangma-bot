#!/usr/bin/env python3
"""第0步trace普查：弃牌窗口的步数次优率、同距支持次优率与听口白容量占比。

冻结口径（运行前声明，对应 SINGLEWHITE-160-GAP-AND-DIRECTION.md §5 第0步）：
- 范围：readiness-audit-cache.json 中 phase=="draw" 且 selected 为合法弃牌的窗口；
  候选限定 kind=="discard" 且 completeness=="complete" 且 replacement_unknown 为假。
  响应窗（吃/碰后弃牌）与吃碰/杠/胡选择窗不在本普查，另行分析。
- 综合向听取候选的 combined；普通型向听取 standard；支持摘要分别用 useful（自然进张）
  与 standard_useful（生产口径，含白板百搭）。容量与码宽是公开未见计数，不是概率。
- 三分支判据：
  ①步数次优：selected.combined 严格大于候选最小 combined；
  ②同距支持次优：selected.combined 等于最小，但同距候选中存在 useful 码宽更大，
    或码宽相同而容量更大的候选（自然与生产两口径分别判定，任一成立即记该口径次优）；
  ③步数与同距支持均最优。
- 分层：当前实持白数（0/1/≥2）×庄闲（seat==dealer）×墙余三段（≥61/41–60/≤40）
  ×窗口综合向听（0/1/2/3+）。
- 听口白容量占比：selected 弃后 combined==0 的窗口，白码容量/selected 支持总容量
  （自然与生产两口径）。单局胡标记取该单局是否存在本家 hu 选择，仅作诊断分账，
  受他家先胡截尾，不当策略损失。
只读缓存，输出 JSON；不联网、不启动模拟、不改任何策略或发布包。
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def wall_band(wall):
    if wall is None:
        return "unknown"
    if wall >= 61:
        return "early"
    if wall >= 41:
        return "mid"
    return "late"


def shanten_band(steps):
    if steps is None:
        return "unknown"
    if steps <= 0:
        return "0"
    if steps == 1:
        return "1"
    if steps == 2:
        return "2"
    return "3+"


def support_summary(candidate, field):
    info = candidate.get(field) or {}
    codes = info.get("codes") or {}
    return int(info.get("width") or 0), float(info.get("capacity") or 0.0), codes


def classify_window(record):
    """返回 (三分支, 普通型次优, 详情)；无法比较返回 None。"""
    legal = [c for c in (record.get("legal") or [])
             if c.get("kind") == "discard"
             and c.get("completeness") == "complete"
             and not c.get("replacement_unknown")]
    if not legal:
        return None
    selected_key = record.get("selected") or ""
    chosen = None
    for cand in legal:
        if cand.get("key") == selected_key:
            chosen = cand
            break
    if chosen is None:
        return None
    steps = [c.get("combined") for c in legal if c.get("combined") is not None]
    if not steps or chosen.get("combined") is None:
        return None
    best = min(steps)
    detail = {
        "whites": record.get("current_whites"),
        "dealer": record.get("seat") == record.get("dealer"),
        "wall_band": wall_band(record.get("wall")),
        "shanten": shanten_band(chosen.get("combined")),
        "n_candidates": len(legal),
    }
    std_steps = [c.get("standard") for c in legal if c.get("standard") is not None]
    standard_sub = bool(std_steps and chosen.get("standard") is not None
                        and chosen["standard"] > min(std_steps))
    if chosen["combined"] > best:
        return "step_suboptimal", standard_sub, detail
    tied = [c for c in legal if c.get("combined") == best]
    support_sub = {}
    for field in ("useful", "standard_useful"):
        ranked = []
        for cand in tied:
            width, capacity, _ = support_summary(cand, field)
            ranked.append((width, capacity, cand.get("key")))
        ranked.sort(reverse=True)
        best_w, best_p, _ = ranked[0]
        my_w, my_p, _ = support_summary(chosen, field)[0], support_summary(chosen, field)[1], None
        support_sub[field] = {
            "suboptimal": (my_w, my_p) < (best_w, best_p),
            "width_gap": best_w - my_w,
            "capacity_gap": round(best_p - my_p, 2),
        }
    speedof_sub = {}
    for field in ("useful", "standard_useful"):
        best_core = max(speedof_core(c, field) for c in tied)
        my_core = speedof_core(chosen, field)
        speedof_sub[field] = {
            "suboptimal": my_core < best_core - 1e-9,
            "core_gap": round(best_core - my_core, 4),
        }
    detail["support"] = support_sub
    detail["speedof"] = speedof_sub
    if any(v["suboptimal"] for v in speedof_sub.values()):
        return "support_suboptimal", standard_sub, detail
    return "both_optimal", standard_sub, detail


SPEEDCAP, SPEEDREF, VARREF, LINKCAP = 4.8, 12.0, 4.0, 2.0


def speedof_core(candidate, field):
    """与 RF1 speedof 同构的支持核（scale 同窗相同，置 1）；mass=Σmin(容量,2)。"""
    width, capacity, codes = support_summary(candidate, field)
    mass = sum(min(float(v), LINKCAP) for v in codes.values() if v > 0)
    return SPEEDCAP * mass / (SPEEDREF + mass) * float(width) / (VARREF + float(width)) if width else 0.0


def white_share(candidate, field):
    width, capacity, codes = support_summary(candidate, field)
    if capacity <= 0:
        return None
    return codes.get("白", 0) / capacity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True, help="readiness-audit-cache.json 路径")
    parser.add_argument("--out", required=True, help="输出 JSON 路径（目录需存在或可创建）")
    args = parser.parse_args()

    data = json.loads(Path(args.cache).read_text())
    decisions = data["decisions"]

    # 单局是否本家胡（诊断分账用；受截尾）。
    hu_hands = set()
    for rec in decisions:
        if (rec.get("selected") or "").startswith("hu"):
            hu_hands.add((rec.get("game_id"), rec.get("round_no")))

    windows = []
    branch_by = defaultdict(Counter)
    standard_sub_by = defaultdict(Counter)
    ready_white_share = []
    hand_ready = defaultdict(list)
    skipped = Counter()
    for rec in decisions:
        if rec.get("phase") != "draw":
            continue
        result = classify_window(rec)
        if result is None:
            skipped["uncomparable"] += 1
            continue
        branch, standard_sub, detail = result
        whites = detail["whites"]
        if whites is None:
            skipped["whites_missing"] += 1
            continue
        group = "0w" if whites == 0 else ("1w" if whites == 1 else "2w+")
        seatgroup = "dealer" if detail["dealer"] else "nondealer"
        for key in (group, f"{group}/{seatgroup}"):
            branch_by[key][branch] += 1
            if standard_sub:
                standard_sub_by[key]["standard_sub"] += 1
        # 听口白容量占比（弃后综合向听==0 的 selected）。
        sel_key = rec.get("selected")
        chosen = next((c for c in rec.get("legal") or [] if c.get("key") == sel_key), None)
        if chosen is not None and chosen.get("combined") == 0:
            shares = {"useful": white_share(chosen, "useful"),
                      "standard_useful": white_share(chosen, "standard_useful")}
            entry = {
                "group": group, "seat": seatgroup, "wall_band": detail["wall_band"],
                "hu_this_hand": (rec.get("game_id"), rec.get("round_no")) in hu_hands,
                "useful_share": None if shares["useful"] is None else round(shares["useful"], 4),
                "standard_useful_share": None if shares["standard_useful"] is None else round(shares["standard_useful"], 4),
                "useful_width": (chosen.get("useful") or {}).get("width"),
                "decision_id": rec.get("decision_id"),
            }
            ready_white_share.append(entry)
            hand_ready[(rec.get("game_id"), rec.get("round_no"))].append(entry)
        windows.append({"decision_id": rec.get("decision_id"), "group": group,
                        "branch": branch, "standard_sub": standard_sub, **{
                            k: v for k, v in detail.items() if k not in ("support", "speedof")}})

    # 次优窗口清单（speedof 核口径），供探针活动检查做对照窗。
    suboptimal_windows = []
    for rec in decisions:
        if rec.get("phase") != "draw":
            continue
        result = classify_window(rec)
        if result is None or result[0] != "support_suboptimal":
            continue
        branch, standard_sub, detail = result
        whites = detail["whites"]
        group = "0w" if whites == 0 else ("1w" if whites == 1 else "2w+")
        suboptimal_windows.append({
            "decision_id": rec.get("decision_id"), "group": group,
            "dealer": detail["dealer"], "wall_band": detail["wall_band"],
            "shanten": detail["shanten"],
            "speedof": detail.get("speedof"),
            "support": detail.get("support"),
        })

    def pct(counter, key):
        total = sum(counter.values())
        return round(100.0 * counter.get(key, 0) / total, 2) if total else None

    summary = {}
    for key, counter in sorted(branch_by.items()):
        total = sum(counter.values())
        summary[key] = {
            "windows": total,
            "step_suboptimal_pct": pct(counter, "step_suboptimal"),
            "support_suboptimal_pct": pct(counter, "support_suboptimal"),
            "both_optimal_pct": pct(counter, "both_optimal"),
            "standard_shanten_suboptimal_windows": standard_sub_by[key].get("standard_sub", 0),
        }

    # 听后转胡（诊断）：首听窗口所在单局是否本家胡，按白数分组。
    conversion = defaultdict(lambda: {"ready_hands": 0, "hu_hands": 0})
    seen_hands = set()
    for (game, rnd), entries in hand_ready.items():
        group = entries[0]["group"]
        conversion[group]["ready_hands"] += 1
        if (game, rnd) in hu_hands:
            conversion[group]["hu_hands"] += 1
        seen_hands.add((game, rnd))

    share_stats = defaultdict(list)
    for entry in ready_white_share:
        if entry["useful_share"] is not None:
            share_stats[f'{entry["group"]}/useful'].append(entry["useful_share"])
        if entry["standard_useful_share"] is not None:
            share_stats[f'{entry["group"]}/standard_useful'].append(entry["standard_useful_share"])
    share_summary = {}
    for key, values in sorted(share_stats.items()):
        values = sorted(values)
        share_summary[key] = {
            "n": len(values),
            "mean": round(sum(values) / len(values), 4),
            "median": round(values[len(values) // 2], 4),
            "p90": round(values[int(0.9 * (len(values) - 1))], 4),
            "zero_share_windows": sum(1 for v in values if v == 0),
        }

    output = {
        "scope": "phase==draw 弃牌窗；候选=完整弃牌；口径见脚本 docstring",
        "total_windows": len(windows),
        "skipped": dict(skipped),
        "branch_summary_pct": summary,
        "ready_wait_white_share": share_summary,
        "ready_hand_conversion_diagnostic": {k: dict(v) for k, v in conversion.items()},
        "hu_windows_total": len(hu_hands),
        "suboptimal_windows_speedof": suboptimal_windows,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(json.dumps(output["branch_summary_pct"], ensure_ascii=False, indent=1))
    print("ready_wait_white_share:", json.dumps(share_summary, ensure_ascii=False))
    print("conversion_diagnostic:", json.dumps(output["ready_hand_conversion_diagnostic"], ensure_ascii=False))
    print("skipped:", dict(skipped), "windows:", len(windows))


if __name__ == "__main__":
    main()
