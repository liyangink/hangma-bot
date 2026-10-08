#!/usr/bin/env python3
"""分牌型向听（standard / seven_pairs）是否携带父代丢掉的信息（只读）。

父代只读综合 `shanten_after`，把普通型与七对两个分牌型向听塌缩成一个数。
七对是真实的番值来源（七对 ×2、豪华 ×4，七对形爆头 ×4），所以「塌缩是否丢信息」
是一个可以量化的具体问题。

本脚本测三种项形态的首选改选率：
  R1：偏好七对向听更低（或相等且更近）的候选
  R2：偏好两型向听更接近的候选（保留双路线）
  R3：偏好普通型向听更低的候选

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/route_shanten_reach.py \
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


def iter_windows(audit_root):
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
                    out.append({
                        "action_key": cand.get("action_key"),
                        "shanten": shanten,
                        "support": support,
                        "standard": facts.get("standard_shanten_after"),
                        "seven": facts.get("seven_pairs_shanten_after"),
                    })
                if len(out) >= 2:
                    yield out


def _term(candidate, kind, weight):
    standard = candidate["standard"]
    seven = candidate["seven"]
    if kind == "seven_lower":
        if type(seven) is not int:
            return 0.0
        return weight * (8 - min(seven, 8))
    if kind == "standard_lower":
        if type(standard) is not int:
            return 0.0
        return weight * (8 - min(standard, 8))
    if kind == "keep_both":
        if type(standard) is not int or type(seven) is not int:
            return 0.0
        return -weight * abs(standard - seven)
    return 0.0


def pick(candidates, kind, weight):
    best = None
    for candidate in candidates:
        score = (-SHANTEN_COEFFICIENT * candidate["shanten"] + candidate["support"]
                 + _term(candidate, kind, weight))
        key = (score, str(candidate["action_key"]))
        if best is None or key > best[0]:
            best = (key, candidate)
    return best[1]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-root", required=True, action="append")
    ap.add_argument("--weights", default="2,5,15,40")
    args = ap.parse_args(argv)

    windows = []
    for root in args.audit_root:
        windows.extend(iter_windows(root))
    weights = [float(x) for x in args.weights.split(",") if x.strip()]
    kinds = [("seven_lower", "偏好七对向听更低"), ("standard_lower", "偏好普通型向听更低"),
             ("keep_both", "偏好两型向听接近（保留双路线）")]

    both = 0
    differ = 0
    for win in windows:
        for candidate in win:
            if type(candidate["standard"]) is int and type(candidate["seven"]) is int:
                both += 1
                if candidate["standard"] != candidate["seven"]:
                    differ += 1
                break

    baseline = [pick(w, "none", 0.0)["action_key"] for w in windows]
    print("窗口数 %d" % len(windows))
    print("窗口内首个同时有两型向听的候选：普通型与七对向听不相等的窗口 %d (%.2f%%)"
          % (differ, 100.0 * differ / len(windows)))
    print()
    print("| 项形态 | " + " | ".join("W=%g" % w for w in weights) + " |")
    print("| --- | " + " | ".join("---" for _ in weights) + " |")
    for kind, label in kinds:
        cells = []
        for weight in weights:
            changed = sum(1 for win, base in zip(windows, baseline)
                          if pick(win, kind, weight)["action_key"] != base)
            cells.append("%.2f%%" % (100.0 * changed / len(windows)))
        print("| %s | %s |" % (label, " | ".join(cells)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())