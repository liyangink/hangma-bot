
from pathlib import Path as _StoragePath
import sys as _storage_sys
_PROJECT_ROOT = next(p for p in _StoragePath(__file__).resolve().parents
                     if (p / "src/hangma_bot/bootstrap.py").is_file())
_storage_sys.path.insert(0, str(_PROJECT_ROOT / "src"))
from hangma_bot.adapters.recording.project_storage import project_file as _resolve_project_file
_PROJECT_STORAGE_ORIGIN = 'review/r18-four-arm-evaluation-2026-09-23'

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
import sys
from collections import Counter
from pathlib import Path


def rows_for_slot(root, slot):
    rows = []
    for path in glob.glob(str(Path(root) / slot / "runs" / "*" / "participants" / "*" / "raw" / "*.jsonl")):
        for line in open(path):
            record = json.loads(line)
            payload = record.get("payload") or {}
            endpoint = str(payload.get("endpoint") or "")
            if not endpoint.endswith("/state"):
                continue
            timing = payload.get("request_timing") or {}
            q, g = timing.get("queued_at_monotonic"), timing.get("granted_at_monotonic")
            st, end = timing.get("transport_started_at_monotonic"), timing.get("completed_at_monotonic")
            if not all(isinstance(v, (int, float)) for v in (q, g, st, end)):
                continue
            rows.append({"q": q, "g": g, "st": st, "end": end,
                         "status": payload.get("http_status"),
                         "purpose": timing.get("query_purpose"),
                         "game": endpoint.split("/games/")[-1].split("/state")[0]})
    return sorted(rows, key=lambda row: row["q"])


def report(root):
    print("ROOT", root)
    for slot in ["slot-baihu", "slot-qinglong", "slot-xuanwu", "slot-zhuque"]:
        rows = rows_for_slot(root, slot)
        if not rows:
            continue
        slow = [r for r in rows if r["g"] - r["q"] >= 1.0]
        half = [r for r in rows if r["g"] - r["q"] >= 0.5]
        episodes = []
        for r in slow:
            if not episodes or r["q"] - episodes[-1][-1]["q"] > 1.05:
                episodes.append([r])
            else:
                episodes[-1].append(r)
        rejects = [r for r in rows if r["status"] == 429]
        freezes = []
        for reject in rejects:
            next_start = min((r["st"] for r in rows if r["st"] > reject["end"]), default=reject["end"])
            freezes.append((reject["end"], next_start))
        overlap = []
        for r in slow:
            durations = [max(0.0, min(r["g"], e) - max(r["q"], s)) for s, e in freezes]
            overlap.append(max(durations, default=0.0))
        print(slot,"GET",len(rows),"duration_s",round(max(r['end'] for r in rows)-min(r['st'] for r in rows),1),
              ">500",len(half),">1000",len(slow),"episodes",len(episodes),
              "max_episode_size",max((len(x) for x in episodes),default=0),
              "429",len(rejects),"slow_freeze_overlap_>=500ms",sum(x>=.5 for x in overlap),
              "slow_near_freeze",sum(x>0 for x in overlap),
              "slow_purposes",dict(Counter(r['purpose'] for r in slow)),
              "episode_sizes",[len(x) for x in episodes][:25])


for arg in sys.argv[1:]:
    report(arg)
