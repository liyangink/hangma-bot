#!/usr/bin/env python3
"""C26：**对手池稳健性审计**——我们所有「关闭」结论是否依赖对手池？

配对工装（paired_study.py）本来就有两个对手场景 **H / M**（`contract["panel"]["opponent_scenarios"]`），
统计单位是「mix × root」，根内四座位先平均。也就是说：**每一次完整桌门禁其实都在两个不同对手池上跑过。**

本脚本把 `review/freematch-deep-dive-20260925/p*/stages/` 下**全部历史批次**的逐阶段产物读回来，
对每个候选臂分别给出 H 池与 M 池的效应、各自按根聚类的 bootstrap 95% CI，以及两池之差。

判据（预先写在本文档里）：若某个臂的两池效应**反号**且两池 CI 都不含 0 ⇒ 该结论是**池特异**的，需要重开。
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
import os
import random
import statistics
import sys
from pathlib import Path

ROOT = _PROJECT_ROOT
BASELINES = ("baseline", "r18_v2", "reference:v2", "reference-v2")


def load_batches():
    batches = {}
    patterns = [
        str(_project_file(_PROJECT_ROOT, ROOT / "review" / "freematch-deep-dive-20260925" / "p*" / "stages")),
        str(_project_file(_PROJECT_ROOT, ROOT / "review" / "llm-guided-heuristic-route-2026-09-15" / "evidence" / "r10-supervised-evolution" / "*" / "stages")),
    ]
    for pattern in patterns:
        for directory in sorted(glob.glob(pattern)):
            scores = {}
            for path in glob.glob(os.path.join(directory, "*.json")):
                try:
                    row = json.load(open(path, encoding="utf-8"))
                except Exception:
                    continue
                stage = row.get("stage") or {}
                score = stage.get("focal_stage_score")
                if not isinstance(score, (int, float)):
                    continue
                mix = row.get("mix")
                root = row.get("root_index")
                seat = row.get("focal_seat")
                arm = row.get("arm")
                if mix is None or root is None or seat is None:
                    # 文件名回退：<arm>-<MIX>-r<NN>-s<SEAT>.json
                    stem = os.path.basename(path)[:-5]
                    parts = stem.split("-")
                    if len(parts) >= 4:
                        arm = arm if arm is not None else "-".join(parts[:-3])
                        mix = mix if mix is not None else parts[-3]
                        if parts[-2].startswith("r"):
                            root = root if root is not None else int(parts[-2][1:])
                        if parts[-1].startswith("s"):
                            seat = seat if seat is not None else int(parts[-1][1:])
                key = (mix, root, seat, arm)
                scores[key] = float(score)
            if scores:
                batches[directory] = scores
    return batches


def boot(values, iters=2000, seed=13):
    if len(values) < 3:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = []
    for _ in range(iters):
        picked = [rng.choice(values) for _ in values]
        means.append(statistics.fmean(picked))
    means.sort()
    return (means[int(0.025 * iters)], means[int(0.975 * iters)])


def main() -> int:
    batches = load_batches()
    print("批次目录 =", len(batches))
    print()
    print("| 批次 | 候选臂 | 根(H/M) | H 池效应 | H 95% CI | M 池效应 | M 95% CI | 同号 | H−M |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    flips = []
    total = 0
    for directory, scores in sorted(batches.items()):
        arms = sorted({key[3] for key in scores if key[3]})
        baseline = None
        for candidate_name in BASELINES:
            if candidate_name in arms:
                baseline = candidate_name
                break
        if baseline is None:
            continue
        name = Path(directory).parent.name
        for arm in arms:
            if arm == baseline:
                continue
            effects = {}
            for mix in ("H", "M"):
                per_root = collections.defaultdict(dict)
                for (m, root, seat, a), value in scores.items():
                    if m != mix:
                        continue
                    per_root[root][(seat, a)] = value
                deltas = []
                for root, cell in per_root.items():
                    pairs = []
                    for seat in range(4):
                        if (seat, arm) in cell and (seat, baseline) in cell:
                            pairs.append(cell[(seat, arm)] - cell[(seat, baseline)])
                    if pairs:
                        deltas.append(statistics.fmean(pairs))
                effects[mix] = deltas
            if not effects.get("H") or not effects.get("M"):
                continue
            total += 1
            h = statistics.fmean(effects["H"])
            m = statistics.fmean(effects["M"])
            hci = boot(effects["H"])
            mci = boot(effects["M"])
            same = "是" if (h > 0) == (m > 0) else "**否**"
            short_arm = os.path.basename(arm).replace("OPTY-R18-", "")
            if (h > 0) != (m > 0):
                flips.append((name, short_arm, h, hci, m, mci))
            print("| %s | %s | %d/%d | %+.2f | [%+.2f, %+.2f] | %+.2f | [%+.2f, %+.2f] | %s | %+.2f |"
                  % (name[:26], short_arm[:34], len(effects["H"]), len(effects["M"]), h, hci[0], hci[1],
                     m, mci[0], mci[1], same, h - m))
    print()
    print("有 H/M 两池读数的臂 =", total, "；**反号**的臂 =", len(flips))
    for item in flips:
        print("  反号：", item[0], item[1], "H=%+.2f%s  M=%+.2f%s" % (item[2], item[3], item[4], item[5]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
