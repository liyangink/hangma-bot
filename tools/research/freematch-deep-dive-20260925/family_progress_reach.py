#!/usr/bin/env python3
"""family_progress 的决策可达性：规则模块已算好、而父代完全没用的一整组信号。

规则模块为每个候选产出 `family_progress`，含四个族：
  branch（平胡/七对分支）、chain（飘/杠动作链）、four_white（四白板距离）、baotou（爆头）。
每个族给出 progress ∈ {advance, same, retreat} 与 route_status。

冻结父代的评分只用 `shanten_after` 与 `useful_tiles`，**四个族一个都没用**。
本脚本测量：如果在评分里加入族进度项，最多能区分多少窗口。

判读：只要某个族在窗口内取值不一致，它就能区分候选，
那么「把该族写进评分」就至少是可写的；不一致率就是可达性的上界。

用法：
    .venv/bin/python review/freematch-deep-dive-20260925/family_progress_reach.py \
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

FAMILIES = ("branch", "chain", "four_white", "baotou")


def iter_family_windows(audit_root):
    """产出每个决策窗口的 {family: set(progress)}。"""
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
                per_family = {name: set() for name in FAMILIES}
                usable = 0
                for cand in candidates:
                    facts = cand.get("facts")
                    if not isinstance(facts, dict):
                        continue
                    groups = facts.get("family_progress")
                    if not isinstance(groups, list):
                        continue
                    usable += 1
                    for entry in groups:
                        family = entry.get("family")
                        if family in per_family:
                            per_family[family].add(entry.get("progress"))
                if usable >= 2:
                    yield per_family


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-root", required=True, action="append")
    args = ap.parse_args(argv)

    windows = 0
    varies = {name: 0 for name in FAMILIES}
    any_varies = 0
    for root in args.audit_root:
        for per_family in iter_family_windows(root):
            windows += 1
            hit = False
            for name in FAMILIES:
                if len(per_family[name]) > 1:
                    varies[name] += 1
                    hit = True
            if hit:
                any_varies += 1

    print("窗口数（>=2 个带 family_progress 的候选）：%d" % windows)
    print()
    print("| 族 | 窗口内取值不一致的窗口数 | 占比 |")
    print("| --- | --- | --- |")
    for name in FAMILIES:
        print("| %s | %d | %.2f%% |" % (name, varies[name], 100.0 * varies[name] / windows))
    print("| **至少一族不一致** | **%d** | **%.2f%%** |"
          % (any_varies, 100.0 * any_varies / windows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())