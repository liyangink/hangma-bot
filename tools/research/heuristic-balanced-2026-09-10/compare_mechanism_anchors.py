#!/usr/bin/env python3
"""机制读数对照：模拟（修好庄家轮转后） vs 真实夜战同池内部锚点。

为什么需要它：门禁只报净分，无法回答"模拟像不像真实"。而庄家轮转规则修好之后，
庄位份额/庄胡率/连庄这些读数第一次可以与真实**同池内部**对照（不做跨夜比较——
两天之间对手也在进步，跨夜差不可归因）。

真实锚点取自 2026-09-10 夜（我方 = v2_hu_upgrade_v1），按 `dealer` 字段与 `winner`
字段逐座位统计；模拟侧取 measure_dealer_edge.py 的输出。

用法：compare_mechanism_anchors.py --sim review/.../dealer-edge-fixed2-tierA/dealer-edge.json
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
from pathlib import Path

MAIN = Path("/Users/liyang/Projects/Opensource/hangma-bot")
FEATURES = _project_file(_PROJECT_ROOT, MAIN / "datasets/derived/auto-match-v10-2026-09-10")
ME = "u_13495c3d79c8"


def real_anchors():
    """真实夜战的池内读数：我方与"除我方外全部对手"。"""

    doms = {row["user_id"] for row in
            json.loads((_project_file(_PROJECT_ROOT, FEATURES / "opponents.json")).read_text())["dominators"]
            if row.get("paired_diff_per_game", 0) <= -8.0}
    stat = collections.defaultdict(lambda: dict(dh=0, dw=0, ph=0, pw=0, draws=0, hands=0))
    for line in (_project_file(_PROJECT_ROOT, FEATURES / "features-v10.jsonl")).open(encoding="utf-8"):
        row = json.loads(line)
        users = row.get("seat_users") or []
        dealer, winner, is_draw = row.get("dealer"), row.get("winner"), bool(row.get("is_draw"))
        for seat, user in enumerate(users):
            if user == ME:
                group = "我方（Tier-A）"
            elif user in doms:
                group = "压制组"
            else:
                group = "其他对手"
            entry = stat[group]
            entry["hands"] += 1
            if is_draw:
                entry["draws"] += 1
            won = (winner == seat) and not is_draw
            if seat == dealer:
                entry["dh"] += 1
                entry["dw"] += 1 if won else 0
            else:
                entry["ph"] += 1
                entry["pw"] += 1 if won else 0
    out = {}
    for group, entry in stat.items():
        dr = entry["dw"] / entry["dh"] if entry["dh"] else None
        pr = entry["pw"] / entry["ph"] if entry["ph"] else None
        out[group] = dict(hands=entry["hands"], dealer_share=entry["dh"] / entry["hands"],
                          dealer_win_rate=dr, plain_win_rate=pr,
                          dealer_advantage=(dr - pr) if (dr is not None and pr is not None) else None,
                          draw_rate=entry["draws"] / entry["hands"])
    return out


def sim_anchors(path):
    doc = json.loads(path.read_text(encoding="utf-8"))
    stats = doc["stats"]
    focal = (doc.get("focal_stats") or {})
    # 同池同策略时四席对称，池化读数即该策略的读数；焦点读数用于交叉核对。
    pooled = next(iter(stats.values()))
    focal_one = next(iter(focal.values())) if focal else None
    return dict(roots=doc["roots"], hands=pooled["hands"],
                dealer_share=pooled["dealer_share"], dealer_win_rate=pooled["dealer_win_rate"],
                plain_win_rate=pooled["plain_win_rate"],
                dealer_advantage=pooled["dealer_advantage"], draw_rate=pooled["draw_rate"],
                focal_dealer_advantage=(focal_one or {}).get("dealer_advantage"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim", required=True)
    parser.add_argument("--out", default="mechanism-anchor-comparison.json")
    args = parser.parse_args()
    report = dict(schema="mechanism-anchor-comparison/1",
                  note="跨夜不可比；这里只做同池内部读数与模拟对照",
                  real=real_anchors(), sim=sim_anchors(Path(args.sim)))
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + chr(10),
                              encoding="utf-8")
    print("%-16s %10s %10s %10s %12s %10s" % ("组/来源", "庄手份额", "庄胡率", "闲胡率", "庄位优势", "流局率"))
    for group, entry in report["real"].items():
        print("%-16s %10.4f %10.4f %10.4f %+11.4f %10.4f" % (
            group, entry["dealer_share"], entry["dealer_win_rate"] or 0,
            entry["plain_win_rate"] or 0, entry["dealer_advantage"] or 0, entry["draw_rate"]))
    sim = report["sim"]
    print("%-16s %10.4f %10.4f %10.4f %+11.4f %10.4f" % (
        "模拟（Tier-A 池）", sim["dealer_share"], sim["dealer_win_rate"],
        sim["plain_win_rate"], sim["dealer_advantage"], sim["draw_rate"]))
    print("（模拟焦点口径庄位优势 %+.4f；%d 根 / %d 手）" % (
        sim["focal_dealer_advantage"] or 0, sim["roots"], sim["hands"]))


if __name__ == "__main__":
    main()
