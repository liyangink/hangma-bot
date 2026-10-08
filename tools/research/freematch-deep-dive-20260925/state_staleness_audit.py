#!/usr/bin/env python3
"""主审：决策是否建立在「过期状态」上——snapshot_seq 落后 trigger_seq 的分布，按房分期对照。

动机：v2 期「接线修复前」的 5 个房是 −7.22 分/局，而修复后的 campaign b 是 +1.8~+2.6 分/局，
配置完全相同。修复的核心是**状态查询排队饥饿**（曾出现 7.58 秒零授权）。
若修复前存在「用落后快照决策」，那才是真正可能的机制。
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
import glob
import json
from concurrent.futures import ProcessPoolExecutor

POST = "r18-sse-freematch-campaign-20260925b"


def scan(path):
    camp = path.split("/")[2] if path.startswith("artifacts/") else path.split("/")[3]
    c = collections.Counter()
    lags = []
    try:
        with open(path, "r", errors="ignore") as fh:
            for line in fh:
                if '"kind"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("kind") != "decision_input":
                    continue
                pay = d.get("payload") or {}
                req = pay.get("request") or {}
                obs = req.get("observation") or {}
                ss = obs.get("snapshot_seq")
                ts = req.get("trigger_seq")
                if ss is None or ts is None:
                    continue
                try:
                    lag = int(ts) - int(ss)
                except Exception:
                    continue
                lags.append(lag)
    except Exception as exc:
        c["error_" + type(exc).__name__] += 1
    hist = collections.Counter(lags)
    tag = "post" if camp == POST else ("pre" if "20260925" in camp else "other")
    return camp, tag, len(lags), dict(hist)


def main() -> int:
    files = sorted(glob.glob("artifacts/sessions/**/participants/u_13495c3d79c8/decisions.jsonl", recursive=True))
    print("文件数 %d" % len(files), flush=True)
    by_tag = collections.defaultdict(collections.Counter)
    tot = collections.Counter()
    with ProcessPoolExecutor(max_workers=6) as ex:
        for camp, tag, n, hist in ex.map(scan, files, chunksize=4):
            tot[tag] += n
            for k, v in hist.items():
                by_tag[tag][k] += v
    print()
    for tag in ("pre", "post", "other"):
        n = tot[tag]
        if not n:
            continue
        dist = by_tag[tag]
        zero = dist.get(0, 0)
        print("## %s：%d 个决策" % (tag, n))
        print("- snapshot_seq == trigger_seq：%d（%.4f%%）" % (zero, 100.0 * zero / n))
        for k in sorted(dist)[:8]:
            print("    lag=%+d : %d" % (k, dist[k]))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
