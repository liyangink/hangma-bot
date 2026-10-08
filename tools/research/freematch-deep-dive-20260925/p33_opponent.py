#!/usr/bin/env python3
"""P33 步骤 3：对手使用率对照（我方 7.14% vs 对手 18.31%）。

数据：review/baotou-anatomy-20260925/rounds.jsonl（3,920 局 / 49 房，逐座 hu_windows 元组）。
特征映射口径见预登记 §五；不可映射的特征必须如实标注。
只读既有文件，输出到 .team-work/p33-deferral-heterogeneity/。
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

import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = _PROJECT_ROOT
ROUNDS = _project_file(_PROJECT_ROOT, 'review/baotou-anatomy-20260925/rounds.jsonl')
OUT = _project_file(_PROJECT_ROOT, ROOT / ".team-work/p33-deferral-heterogeneity")
SEED = 20260925
BOOT = 10000
WALL = 83  # 由 P24 暴露面板 16 个状态标定：remaining_tile_count + 该时刻总摸牌数 = 83（16/16 恒定）


def room_family(session: str) -> str:
    return "sse-freematch" if "sse-freematch" in session else "auto-match"


def load_windows():
    rows = []
    with open(ROUNDS, encoding="utf-8") as handle:
        for line in handle:
            d = json.loads(line)
            dealer = d["dealer"]
            for seat_info in d["seats"]:
                seat = seat_info["seat"]
                is_me = bool(seat_info["is_me"])
                # 其他三座的副露数（近似：取他们各自 discard_profile 中 turn ≤ 本窗 turn 的最后一条）
                others = [s for s in d["seats"] if s["seat"] != seat]
                for w in seat_info["hu_windows"]:
                    seq, turn, melds, whites, baotou_after, n_targets, chosen, targets = (
                        w[0], w[1], w[2], w[3], w[4], w[5], w[6], w[7] if len(w) > 7 else ""
                    )
                    other_lo, other_hi = 0, 0
                    for o in others:
                        prof = o.get("discard_profile") or []
                        lo = max([e["melds"] for e in prof if e["turn"] <= turn], default=0)
                        hi = max([e["melds"] for e in prof if e["turn"] <= turn + 1], default=0)
                        hi = max(hi, lo)
                        other_lo += lo
                        other_hi += hi
                    j = (seat - dealer) % 4
                    remaining_est = WALL - (4 * turn + j + 1)
                    rows.append(
                        {
                            "room_id": d["room_id"],
                            "session": d["session"],
                            "family": room_family(d["session"]),
                            "round_no": d["round_no"],
                            "side": "me" if is_me else "opp",
                            "seat": seat,
                            "is_dealer": int(seat == dealer),
                            "turn": turn,
                            "remaining_est": remaining_est,
                            "own_melds": melds,
                            "other_meld_sum_lo": other_lo,
                            "other_meld_sum_hi": other_hi,
                            "whites": whites,
                            "baotou_after": int(bool(baotou_after)),
                            "n_targets": n_targets,
                            "deferred": int(str(chosen).startswith("discard")),
                            "seq": seq,
                        }
                    )
    return rows


def prop_ci(rows, mask, clusters="room_id", b=BOOT, seed=SEED):
    """簇（房）级 bootstrap 的比例 CI。"""
    by_room = defaultdict(list)
    for r in rows:
        by_room[r[clusters]].append(1.0 if mask(r) else 0.0)
    rooms = list(by_room.values())
    point = sum(sum(v) for v in rooms) / sum(len(v) for v in rooms)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(rooms), size=(b, len(rooms)))
    vals = []
    for i in range(b):
        pick = [rooms[k] for k in idx[i]]
        flat = [x for v in pick for x in v]
        vals.append(sum(flat) / len(flat) if flat else float("nan"))
    vals = np.array(vals)
    return point, float(np.nanquantile(vals, 0.025)), float(np.nanquantile(vals, 0.975))


def main() -> int:
    rows = load_windows()
    lines = []

    def say(msg=""):
        print(msg)
        lines.append(msg)

    me_all = [r for r in rows if r["side"] == "me"]
    op_all = [r for r in rows if r["side"] == "opp"]
    me_def = [r for r in me_all if r["deferred"]]
    op_def = [r for r in op_all if r["deferred"]]
    say("## 0. 口径复核（与 baotou-anatomy 报告对账）")
    say(f"- 我方已成胡摸牌窗口 {len(me_all)}，弃胡 {len(me_def)} ⇒ {len(me_def)/len(me_all)*100:.4f}%（报告 78/1,093 = 7.14%）")
    say(f"- 对手三座已成胡摸牌窗口 {len(op_all)}，弃胡 {len(op_def)} ⇒ {len(op_def)/len(op_all)*100:.4f}%（报告 647/3,534 = 18.31%）")
    say(f"- 房聚类 49；本表按 room_id 聚类（我方 {len({r['room_id'] for r in me_all})} 房）")

    # ---------------- 1. 可映射特征上的分布对照
    say()
    say("## 1. 弃胡窗在可映射公开特征上的分布（对手 vs 我方 vs 本底）")

    defs = {
        "非坐庄": lambda r: r["is_dealer"] == 0,
        "墙剩余估计 >20（≈己方第 16 摸之前）": lambda r: r["remaining_est"] > 20,
        "墙剩余估计 >51（≈己方第 8 摸之前）": lambda r: r["remaining_est"] > 51,
        "己方副露=1": lambda r: r["own_melds"] == 1,
        "三家副露合计≤1（近似下界口径）": lambda r: r["other_meld_sum_lo"] <= 1,
        "三家副露合计≤1（近似上界口径）": lambda r: r["other_meld_sum_hi"] <= 1,
        "本窗已无爆头靶（n_targets=0）": lambda r: r["n_targets"] == 0,
        "本窗已有爆头靶（n_targets>0）": lambda r: r["n_targets"] > 0,
        "弃胡前已是爆头态": lambda r: r["baotou_after"] == 1,
        "手留财神≥1": lambda r: r["whites"] >= 1,
    }
    table = {}
    for name, fn in defs.items():
        row = {}
        for side, pool in (("对手弃胡窗", op_def), ("我方弃胡窗", me_def),
                           ("对手全部胡窗（本底）", op_all), ("我方全部胡窗（本底）", me_all)):
            p, lo, hi = prop_ci(pool, fn)
            row[side] = {"share": p, "ci95": [lo, hi], "n_hit": sum(1 for r in pool if fn(r)), "n": len(pool)}
        # 浓度比：弃胡窗占比 ÷ 同侧本底占比
        row["对手浓度比"] = row["对手弃胡窗"]["share"] / row["对手全部胡窗（本底）"]["share"] \
            if row["对手全部胡窗（本底）"]["share"] else None
        row["我方浓度比"] = row["我方弃胡窗"]["share"] / row["我方全部胡窗（本底）"]["share"] \
            if row["我方全部胡窗（本底）"]["share"] else None
        table[name] = row
        say(f"- **{name}**")
        for side in ("对手弃胡窗", "我方弃胡窗", "对手全部胡窗（本底）", "我方全部胡窗（本底）"):
            e = row[side]
            say(f"    - {side}: {e['share']*100:.1f}%（{e['n_hit']}/{e['n']}），房聚类 95% CI "
                f"[{e['ci95'][0]*100:.1f}%, {e['ci95'][1]*100:.1f}%]")
        say(f"    - 浓度比（弃胡窗÷本底）：对手 {row['对手浓度比']:.2f}，我方 {row['我方浓度比']:.2f}")

    # ---------------- 2. 分层：房族
    say()
    say("## 2. 房族分层（对手来源不同）")
    fam = {}
    for family in ("sse-freematch", "auto-match"):
        sub_me = [r for r in me_all if r["family"] == family]
        sub_op = [r for r in op_all if r["family"] == family]
        me_r = sum(1 for r in sub_me if r["deferred"]) / len(sub_me) if sub_me else None
        op_r = sum(1 for r in sub_op if r["deferred"]) / len(sub_op) if sub_op else None
        fam[family] = {"me_windows": len(sub_me), "me_defer_rate": me_r,
                       "opp_windows": len(sub_op), "opp_defer_rate": op_r,
                       "rooms": len({r["room_id"] for r in sub_me + sub_op})}
        say(f"- {family}: 房 {fam[family]['rooms']}，我方 {len(sub_me)} 窗 / 弃胡率 {me_r*100:.2f}%，"
            f"对手 {len(sub_op)} 窗 / 弃胡率 {op_r*100:.2f}%")

    # ---------------- 2b. 条件弃胡率分解（按「本窗是否有爆头靶」）
    say()
    say("## 2b. 条件弃胡率分解：使用率差距落在哪一类窗口")
    decomp = {}
    for label, tag in (("有靶（n_targets>0）", "t>0"), ("无靶（n_targets=0）", "t=0")):
        entry = {}
        for side, pool in (("me", me_all), ("opp", op_all)):
            sub = [r for r in pool if (r["n_targets"] > 0) == (tag == "t>0")]
            p, lo, hi = prop_ci(sub, lambda r: r["deferred"])
            entry[side] = {"windows": len(sub), "defers": sum(1 for r in sub if r["deferred"]),
                           "rate": p, "ci95": [lo, hi]}
        decomp[label] = entry
        say(f"- **{label}**：我方 {entry['me']['defers']}/{entry['me']['windows']} = "
            f"{entry['me']['rate']*100:.2f}% [{entry['me']['ci95'][0]*100:.2f}, {entry['me']['ci95'][1]*100:.2f}]；"
            f"对手 {entry['opp']['defers']}/{entry['opp']['windows']} = {entry['opp']['rate']*100:.2f}% "
            f"[{entry['opp']['ci95'][0]*100:.2f}, {entry['opp']['ci95'][1]*100:.2f}]")
    say("- 读法：总体 7.14% vs 18.31% 的 2.6 倍差距，**几乎全部来自「有靶」这一类**"
        "（P86-02 已测：有靶弃胡是赚的）；在「无靶」这一类上双方都极少弃胡（我们 0，对手 1.4%），"
        "而 P24 已证无靶弃胡平均亏 10.4 分/桌。")

    # ---------------- 3. P24 候选规则在对手侧的落地
    say()
    say("## 3. P24 候选/正相关规则在对手侧的落地比例")
    say("（P24 的胜出规则含 mix 或 hu_score/useful_kinds，这些**在对手侧不可观测**，逐条标注）")
    rules = {
        "A8 round_no≤2（精确）": lambda r: r["round_no"] <= 2,
        "A3 非坐庄（精确）": lambda r: r["is_dealer"] == 0,
        "A2 三家副露合计≤1（近似下界）": lambda r: r["other_meld_sum_lo"] <= 1,
        "S6a 己方副露=1（精确）": lambda r: r["own_melds"] == 1,
        "A1 墙剩余>20（近似，turn≤15）": lambda r: r["turn"] <= 15,
        "FamilyB 最优非 mix 规则的墙剩余部分 >51（turn≤7）": lambda r: r["turn"] <= 7,
    }
    out3 = {}
    for name, fn in rules.items():
        e = {}
        for side, pool in (("opp_def", op_def), ("me_def", me_def), ("opp_all", op_all), ("me_all", me_all)):
            p, lo, hi = prop_ci(pool, fn)
            e[side] = {"share": p, "ci95": [lo, hi], "n_hit": sum(1 for r in pool if fn(r)), "n": len(pool)}
        e["opp_concentration"] = e["opp_def"]["share"] / e["opp_all"]["share"] if e["opp_all"]["share"] else None
        e["me_concentration"] = e["me_def"]["share"] / e["me_all"]["share"] if e["me_all"]["share"] else None
        out3[name] = e
        say(f"- **{name}**：对手弃胡窗落点 {e['opp_def']['share']*100:.1f}% "
            f"[{e['opp_def']['ci95'][0]*100:.1f}, {e['opp_def']['ci95'][1]*100:.1f}]，"
            f"我方弃胡窗 {e['me_def']['share']*100:.1f}% "
            f"[{e['me_def']['ci95'][0]*100:.1f}, {e['me_def']['ci95'][1]*100:.1f}]；"
            f"浓度比 对手 {e['opp_concentration']:.2f} / 我方 {e['me_concentration']:.2f}")

    # ---------------- 4. mix 不可映射的显式说明
    say()
    say("## 4. 不可映射项（必须如实报告）")
    say("- P24 的 `mix`（H/M）不是牌局内可观测特征，而是**实验的对手池构成**："
        "H = 三家 weighted_heuristic_v2，M = V2 / white_guard / V1 各一家。对手侧无对应量，**无法对照**。")
    say("- P24 的 `hu_score`（立刻胡的分数）与 `intervention_useful_kinds`（弃后听口宽度）在对手的 "
        "`hu_windows` 元组里不存在，**无法对照**；只能用 `whites`（手留财神数）与 `n_targets` 作粗代理。")

    payload = {
        "counts": {"me_windows": len(me_all), "me_defer": len(me_def), "opp_windows": len(op_all),
                   "opp_defer": len(op_def), "rooms": len({r["room_id"] for r in rows}),
                   "wall_constant": WALL},
        "distribution": table,
        "conditional_deferral_by_target": decomp,
        "room_family": fam,
        "rules": out3,
    }
    (_project_file(_PROJECT_ROOT, OUT / "opponent.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (_project_file(_PROJECT_ROOT, OUT / "opponent.log")).write_text("\n".join(lines) + "\n", encoding="utf-8")
    say()
    say(f"写出 {_project_file(_PROJECT_ROOT, OUT/'opponent.json')} / {_project_file(_PROJECT_ROOT, OUT/'opponent.log')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
