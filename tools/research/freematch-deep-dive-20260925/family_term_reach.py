#!/usr/bin/env python3
"""路线族进展项（family term）的决策可达性网格扫描（只读）。

父代只用 shanten_after 与 useful_tiles；本脚本测量「把 family_progress 写进评分」
在各种取族与权重下的**首选改选率**。改选率 <10% 的设定不进完整桌。

规则模块为每个候选给出四族进度（branch/chain/four_white/baotou），
progress ∈ {advance, same, retreat}。本脚本的项定义为：

    family_term = W × Σ_family  sign(family)      # advance 记 +1，retreat/close 记 -1，其余 0

并允许排除 branch——因为 branch 自述与分牌型最优向听共线，
包含它可能只是把向听项换个写法（会报出虚假改选率）。

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/family_term_reach.py \
        --audit-root <audit> [--audit-root ...]
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

import argparse
import glob
import json
import os

SHANTEN_COEFFICIENT = 100.0
ALL_FAMILIES = ("branch", "chain", "four_white", "baotou")


def _sign(progress):
    text = str(progress or "").strip().lower()
    if text == "advance":
        return 1.0
    if text in ("retreat", "close"):
        return -1.0
    return 0.0


def iter_windows(audit_root):
    """产出每个窗口的候选 (action_key, shanten, support, family_signs)。"""
    pattern = os.path.join(audit_root, "runs", "*", "participants", "*", "decisions.jsonl")
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("kind") != "decision_input":
                    continue
                request = ((row.get("payload") or {}).get("request") or {})
                candidates = (request.get("rules") or {}).get("legal_candidates") or []
                out = []
                for cand in candidates:
                    facts = cand.get("facts")
                    if not isinstance(facts, dict):
                        continue
                    shanten = facts.get("shanten_after")
                    tiles = facts.get("useful_tiles")
                    if type(shanten) is not int or not isinstance(tiles, list):
                        continue
                    support = 0
                    ok = True
                    for tile in tiles:
                        amount = tile.get("remaining_estimate")
                        if type(amount) is not int:
                            ok = False
                            break
                        support += amount
                    if not ok:
                        continue
                    signs = {name: 0.0 for name in ALL_FAMILIES}
                    for entry in facts.get("family_progress") or []:
                        family = entry.get("family")
                        if family in signs:
                            signs[family] = _sign(entry.get("progress"))
                    out.append({"action_key": cand.get("action_key"), "shanten": shanten,
                                "support": support, "signs": signs})
                if len(out) >= 2:
                    yield out


def pick(candidates, weight, families):
    best = None
    for candidate in candidates:
        bonus = weight * sum(candidate["signs"][name] for name in families)
        score = -SHANTEN_COEFFICIENT * candidate["shanten"] + candidate["support"] + bonus
        key = (score, str(candidate["action_key"]))
        if best is None or key > best[0]:
            best = (key, candidate)
    return best[1]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-root", required=True, action="append")
    ap.add_argument("--weights", default="5,15,40,100")
    args = ap.parse_args(argv)

    windows = []
    for root in args.audit_root:
        windows.extend(iter_windows(root))
    weights = [float(x) for x in args.weights.split(",") if x.strip()]
    variants = {
        "不含 branch（chain+four_white+baotou）": ("chain", "four_white", "baotou"),
        "仅 four_white": ("four_white",),
        "仅 baotou": ("baotou",),
        "仅 chain": ("chain",),
        "全部四族": ALL_FAMILIES,
    }

    baseline = [pick(w, 0.0, ("branch",))["action_key"] for w in windows]
    print("窗口数 %d" % len(windows))
    print()
    header = "| 取族 | " + " | ".join("W=%g" % w for w in weights) + " |"
    print(header)
    print("| --- | " + " | ".join("---" for _ in weights) + " |")
    for label, families in variants.items():
        cells = []
        for weight in weights:
            changed = sum(1 for win, base in zip(windows, baseline)
                          if pick(win, weight, families)["action_key"] != base)
            cells.append("%.2f%%" % (100.0 * changed / len(windows)))
        print("| %s | %s |" % (label, " | ".join(cells)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())