#!/usr/bin/env python3
"""第 1b 步：Q1 锚点对账 —— 用 P6 审计窗口（平台权威观察）验重建口径。

P6 在自己报告里用的两个数字（274/32,374 = 0.85% 的决策窗口、86/1,120 = 7.68%
的单局）来自 `.team-work/p6-baotou-route/cache/*.jsonl.gz`。这些缓存里每个窗口都带
**平台权威**的 `rule_state.baotou` 与当时的 `my_hand` / `drawn_tile` / 副露数。

本脚本做两件对账，都不重算规则：
(1) **规则口径对账**：把缓存里的 my_hand 归一成「摸前 13 张」，交给 hangma 的
    `any_tile_win` 判定，与平台权威 rule_state.baotou 逐窗对比。若一致率高，
    说明「爆头 = 摸前 13 张任意听」这条口径在本数据上成立；
(2) **重建对账**：把同一 (game_id, round_no) 上的本库重建结果与审计的窗口级
    爆头事实对齐，比较单局级进入率。

用法：.venv/bin/python step1b_anchor_reconcile.py [--out anchor.json]
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
import glob
import gzip
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = _PROJECT_ROOT
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(_project_file(_PROJECT_ROOT, ROOT / "src")))

from anatomy_lib import ME, TILE_ORDER  # noqa: E402
from hangma_bot.hangma import hand_analysis  # noqa: E402
from hangma_bot.kernel.actions import Tile  # noqa: E402

P6_CACHE = _project_file(_PROJECT_ROOT, ROOT / ".team-work" / "p6-baotou-route" / "cache")


def iter_cached_windows():
    for path in sorted(glob.glob(str(_project_file(_PROJECT_ROOT, P6_CACHE / "*.jsonl.gz")))):
        room = os.path.basename(path)[: -len(".jsonl.gz")]
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                row["room"] = room
                yield row


def hand_baotou(view):
    """由窗口观察算「摸前 13 张任意听」；不是本人观察时返回 None。"""

    visible = view["visible_state"]
    hand = list(visible["my_hand"])
    drawn = visible["drawn_tile"]
    melds = len(visible["melds"][visible["seat"]])
    if len(hand) == 14 - 3 * melds:
        # 摸牌窗口：my_hand 已含刚摸牌，去掉它得到摸前 13 张。
        if drawn is None:
            return None, "draw_window_without_drawn_tile"
        held = list(hand)
        held.remove(drawn)
        pre = held
    elif len(hand) == 13 - 3 * melds:
        pre = hand
    else:
        return None, "hand_size_%d_melds_%d" % (len(hand), melds)
    if any(code not in TILE_ORDER for code in pre):
        return None, "unknown_tile_code"
    return hand_analysis.any_tile_win(tuple(Tile(c) for c in pre), melds), None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="anchor.json")
    args = parser.parse_args(argv)

    windows = 0
    agree = disagree = unknown = 0
    by_phase = defaultdict(Counter)
    round_windows = defaultdict(lambda: {"windows": 0, "baotou": 0})
    disagree_rows = []
    for row in iter_cached_windows():
        view = row["view"]
        visible = view["visible_state"]
        if visible["seat"] is None:
            continue
        windows += 1
        mine, why = hand_baotou(view)
        platform = visible["rule_state"]["baotou"]
        phase = visible["phase"]
        by_phase[phase]["windows"] += 1
        key = (row["game_id"], row["round_no"])
        round_windows[key]["windows"] += 1
        if platform:
            round_windows[key]["baotou"] += 1
            by_phase[phase]["platform_baotou"] += 1
        if mine is None:
            unknown += 1
            by_phase[phase]["unknown"] += 1
            continue
        if bool(mine) == bool(platform):
            agree += 1
            if platform:
                by_phase[phase]["both_baotou"] += 1
        else:
            disagree += 1
            by_phase[phase]["disagree"] += 1
            if len(disagree_rows) < 20:
                disagree_rows.append({
                    "room": row["room"], "game_id": row["game_id"], "round_no": row["round_no"],
                    "phase": phase, "platform": platform, "recomputed": bool(mine),
                    "hand": list(visible["my_hand"]), "drawn": visible["drawn_tile"],
                    "melds": visible["melds"][visible["seat"]],
                    "chain_count": visible["rule_state"]["chain_count"],
                })

    print("P6 审计窗口 %d" % windows)
    print("规则口径（hangma any_tile_win vs 平台 rule_state.baotou）：")
    print("  一致 %d（%.6f）  不一致 %d  无法判定 %d" % (
        agree, agree / max(1, agree + disagree), disagree, unknown))
    print()
    print("| 阶段 | 窗口 | 平台爆头 | 重建爆头 | 一致 | 不一致 | 无法判定 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for phase, counter in sorted(by_phase.items()):
        print("| %s | %d | %d | %d | %d | %d | %d |" % (
            phase, counter["windows"], counter["platform_baotou"],
            counter["both_baotou"], counter["both_baotou"], counter["disagree"], counter["unknown"]))
    baotou_rounds = sum(1 for item in round_windows.values() if item["baotou"])
    print()
    print("审计口径：单局 %d，其中出现爆头窗口 %d（%.4f）；爆头窗口 %d/%d（%.4f）" % (
        len(round_windows), baotou_rounds, baotou_rounds / max(1, len(round_windows)),
        sum(item["baotou"] for item in round_windows.values()), windows,
        sum(item["baotou"] for item in round_windows.values()) / max(1, windows)))

    # ---- 与重建结果对齐 ----
    recon_rounds = {}
    with open(_project_file(_PROJECT_ROOT, HERE / "rounds.jsonl"), encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            me = next((s for s in row["seats"] if s["is_me"]), None)
            if me is None:
                continue
            recon_rounds[(row["game_id"], row["round_no"])] = bool(me["entered_baotou"])
    common = [key for key in round_windows if key in recon_rounds]
    audit_yes = sum(1 for key in common if round_windows[key]["baotou"])
    recon_yes = sum(1 for key in common if recon_rounds[key])
    both = sum(1 for key in common if round_windows[key]["baotou"] and recon_rounds[key])
    only_audit = [key for key in common if round_windows[key]["baotou"] and not recon_rounds[key]]
    only_recon = [key for key in common if recon_rounds[key] and not round_windows[key]["baotou"]]
    print()
    print("单局级对齐（P6 审计 ∩ 本库重建，game_id+round_no 为键）：")
    print("  可比单局 %d；审计有爆头 %d（%.4f）；重建有爆头 %d（%.4f）；两者都有 %d" % (
        len(common), audit_yes, audit_yes / max(1, len(common)),
        recon_yes, recon_yes / max(1, len(common)), both))
    print("  仅审计有 %d；仅重建有 %d" % (len(only_audit), len(only_recon)))
    for key in only_audit[:10]:
        print("    仅审计: %s 局 %s（窗口 %d 爆头 %d）" % (
            key[0], key[1], round_windows[key]["windows"], round_windows[key]["baotou"]))
    for key in only_recon[:10]:
        print("    仅重建: %s 局 %s" % (key[0], key[1]))

    # ---- 与审计同口径的窗口级对账（限可比单局） ----
    common_keys = set(round_windows) & set(recon_rounds)
    wait_total = wait_baotou = 0
    with open(_project_file(_PROJECT_ROOT, HERE / "rounds.jsonl"), encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            key = (row["game_id"], row["round_no"])
            if key not in common_keys:
                continue
            me = next((s for s in row["seats"] if s["is_me"]), None)
            if me is None:
                continue
            for item in me["waits"]:
                wait_total += 1
                if item[2]:
                    wait_baotou += 1
    print()
    print("同口径窗口级（限可比单局）：我方出牌前等待态 %d，其中爆头态 %d（%.4f）" % (
        wait_total, wait_baotou, wait_baotou / max(1, wait_total)))

    payload = {
        "comparable_wait_states": wait_total,
        "comparable_baotou_wait_states": wait_baotou,
        "comparable_baotou_wait_rate": wait_baotou / max(1, wait_total),
        "audit_windows": windows, "rule_agree": agree, "rule_disagree": disagree,
        "rule_unknown": unknown,
        "by_phase": {k: dict(v) for k, v in by_phase.items()},
        "audit_rounds": len(round_windows), "audit_rounds_with_baotou": baotou_rounds,
        "audit_baotou_windows": sum(item["baotou"] for item in round_windows.values()),
        "recon_comparable_rounds": len(common),
        "recon_rounds_with_baotou": recon_yes,
        "both": both, "only_audit": len(only_audit), "only_recon": len(only_recon),
        "disagree_examples": disagree_rows,
    }
    (_project_file(_PROJECT_ROOT, HERE / args.out)).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print("已写出 %s" % (_project_file(_PROJECT_ROOT, HERE / args.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
