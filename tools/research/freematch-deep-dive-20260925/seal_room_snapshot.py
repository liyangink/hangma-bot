#!/usr/bin/env python3
"""主审（回应独立复审第 1 条）：把 59 房官方牌谱重生为**不可变房级快照**。

每一行绑定：房 id、我方场分、场数、**该房实际跑的策略身份**（policy_version + release_package_id）、
指南版本、时间块、以及**去重后的 game_id 清单**。策略身份来自该房对应 run 的 manifest；
房↔run 的对应优先用 manifest 的 expected_tournament_id，缺失时回落到决策记录里的 context.tournament_id。
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

import glob
import json
import os
import statistics
import sys
from collections import defaultdict

ROOT = "."
OUT = "review/freematch-deep-dive-20260925/room-policy-snapshot.json"


def room_from_decisions(run_dir):
    for path in glob.glob(os.path.join(run_dir, "participants", "*", "decisions.jsonl")):
        try:
            with open(path, "r", errors="ignore") as fh:
                for line in fh:
                    if '"tournament_id"' not in line:
                        continue
                    d = json.loads(line)
                    tid = ((d.get("context") or {}).get("tournament_id"))
                    if tid:
                        return tid
        except Exception:
            continue
    return None


def main() -> int:
    runs = {}
    for man in glob.glob("artifacts/sessions/*/audit/runs/*/manifest.json"):
        run_dir = os.path.dirname(man)
        try:
            p = json.load(open(man))["payload"]
        except Exception:
            continue
        room = p.get("expected_tournament_id") or room_from_decisions(run_dir)
        runs[run_dir] = {
            "campaign": man.split("/")[2],
            "room": room,
            "policy_version": p.get("policy_version"),
            "release_package_id": (p.get("policy_release") or {}).get("release_package_id"),
            "guide": p.get("known_guide_version"),
            "ruleset": p.get("ruleset_version"),
            "wall_time_ms": (json.load(open(man)) or {}).get("wall_time_unix_ms"),
        }
    by_room = defaultdict(list)
    for info in runs.values():
        if info["room"]:
            by_room[info["room"]].append(info)
    print("run 数 %d，可映射到房 %d 个" % (len(runs), len(by_room)), flush=True)

    scores = json.load(open("review/freematch-deep-dive-20260925/room-scores.json"))
    games_by_room = defaultdict(list)
    for g in scores["games"]:
        games_by_room[g["room_id"]].append(g)

    rows = []
    for rid, gs in sorted(games_by_room.items()):
        infos = by_room.get(rid) or []
        policies = sorted({i["policy_version"] for i in infos if i["policy_version"]})
        releases = sorted({i["release_package_id"] for i in infos if i["release_package_id"]})
        rows.append({
            "room_id": rid,
            "games": len(gs),
            "my_total": sum(g["my_total"] for g in gs),
            "policy_version": policies[0] if len(policies) == 1 else policies,
            "release_package_id": releases[0] if len(releases) == 1 else releases,
            "game_ids": sorted({g["game_id"] for g in gs}),
            "session_tag": gs[0].get("session_tag"),
        })
    unknown = [r for r in rows if not r["policy_version"]]
    print("房 %d，其中策略身份未解析 %d" % (len(rows), len(unknown)))

    groups = defaultdict(list)
    for r in rows:
        key = r["policy_version"] if isinstance(r["policy_version"], str) else "未知"
        groups[key].append(r["my_total"])
    print()
    print("| 策略身份 | 房 | 场 | 总分 | 场均 | 按房重抽样 95% CI |")
    print("| --- | --- | --- | --- | --- | --- |")
    import random
    for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        m = statistics.fmean(v)
        rng = random.Random(20260926)
        boots = []
        for _ in range(20000):
            s = [v[rng.randrange(len(v))] for _ in range(len(v))]
            boots.append(statistics.fmean(s))
        boots.sort()
        lo, hi = boots[int(0.025 * len(boots))], boots[int(0.975 * len(boots))]
        print("| %s | %d | %d | %+d | %+.3f | [%+.2f, %+.2f] |"
              % (k, len(v), len(v) * 10, sum(v), m / 10.0, lo / 10.0, hi / 10.0))

    snapshot = {
        "schema": "freematch-room-policy-snapshot/1",
        "as_of": "2026-09-26T00:10:00+0800",
        "scoring": "每房 my_total 为该房 10 场的我方累加分；场均 = my_total / 10",
        "dedup": "按 game_id 去重，保 mtime 最新一份（由 extract_room_scores.load_rooms 完成）",
        "rooms": rows,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, indent=1)
    print()
    print("写出 %s" % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
